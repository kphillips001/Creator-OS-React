from datetime import datetime, timezone
import threading
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.developer_authorization import require_developer_authorization
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.services.commerce_signal_service import CommerceSignalService
from app.services.conversation_gateway import ConversationGateway
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.purchase_intent_service import PurchaseIntentService
from app.workers.commerce_reconciliation import CommerceReconciliationWorker
from app.engine.decision_engine import DecisionEngine


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


def decision():
    return CustomerSalesDecision(
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_buyer_uuid=uuid4(), telegram_user_id=22,
        identity_resolved=True,
        decision=CustomerSalesDecisionType.PRESENT_OFFER,
        reason_code=CustomerSalesReasonCode.NO_ACTIVE_OFFER,
        reason_summary="fixture", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=immutable_mapping({}),
        active_purchase_intent_id=None, active_offering_id=None,
        active_offer_status=None,
        active_offer_conversion_state="NO_ACTIVE_OFFER",
        recommended_offering_id=uuid4(),
        recommended_publication_id=uuid4(),
        recommended_delivery_url="https://fanvue.com/link",
        sell_allowed=True, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=NOW,
        decision_metadata=immutable_mapping({}),
    )


def test_readiness_refinement_blocks_greeting_and_allows_buying_intent():
    original = decision()
    greeting = CustomerSalesBrainService.refine_for_readiness(
        original, {"conversation_ready_for_offer": False}
    )
    buying = CustomerSalesBrainService.refine_for_readiness(
        original, {"conversation_ready_for_offer": True}
    )
    assert greeting.decision is CustomerSalesDecisionType.NO_SALE
    assert greeting.reason_code is CustomerSalesReasonCode.CURRENT_TURN_NOT_READY
    assert greeting.sell_allowed is False
    assert buying is original


def test_decision_engine_readiness_is_deterministic_for_greeting_and_purchase():
    greeting = DecisionEngine._commerce_readiness("Hi", {}, {})
    purchase = DecisionEngine._commerce_readiness(
        "How much is that photo set? Send me the unlock link.", {}, {}
    )
    assert greeting["conversation_ready_for_offer"] is False
    assert greeting["current_buying_intent"] is False
    assert purchase == {
        "conversation_ready_for_offer": True,
        "current_buying_intent": True,
        "customer_requested_content": True,
        "customer_requested_price": True,
        "customer_requested_purchase": True,
        "customer_requested_link": True,
    }


def test_resolved_new_telegram_user_is_onboarded_as_zero_purchase_prospect():
    buyer = uuid4()
    identity = SimpleNamespace(
        id=11, fanvue_account_id=7, external_fanvue_user_uuid=buyer,
        telegram_user_id=22,
    )
    profile = SimpleNamespace(
        customer_commerce_profile_id=uuid4(),
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_user_uuid=buyer, purchase_count=0,
        lifetime_gross_minor=0, lifetime_net_minor=0,
        last_purchase_at=None, display_name=None, handle=None,
        profile_state=SimpleNamespace(value="PROSPECT"),
    )

    class Customers:
        current = None
        purchases = 0

        def get_by_buyer_uuid(self, **_kwargs):
            return self.current

        def get_or_create(self, **_kwargs):
            self.current = profile
            return profile

        def update_profile(self, *_args, **_kwargs):
            return self.current

    customers = Customers()
    brain = CustomerSalesBrainService(
        customer_repository=customers,
        identity_repository=SimpleNamespace(
            get_by_telegram_user_id=lambda _user: identity
        ),
        intent_repository=SimpleNamespace(
            get_latest_for_buyer=lambda **_kwargs: None,
            get_active_for_buyer=lambda **_kwargs: None,
        ),
        commerce_signal_service=SimpleNamespace(
            get_signal=lambda **_kwargs: None
        ),
        offering_selector_service=SimpleNamespace(
            select=lambda **_kwargs: SimpleNamespace(
                offering_id=None, publication_id=None, delivery_url=None,
                title=None, short_description=None, price_minor=None,
                currency=None, selection_reason=SimpleNamespace(
                    value="NO_ELIGIBLE_OFFERING"
                ), exclusion_reasons=(), selector_metadata={},
            )
        ),
        clock=lambda: NOW,
    )
    result = brain.evaluate_for_telegram_user(
        creator_profile_id=2, telegram_user_id=22
    )
    assert customers.current.purchase_count == 0
    assert customers.current.lifetime_gross_minor == 0
    assert result.buyer_stage is CustomerBuyerStage.PROSPECT
    assert customers.purchases == 0


def test_developer_api_requires_explicit_authorization(monkeypatch):
    monkeypatch.delenv("CREATOR_OS_DEVELOPER_KEY", raising=False)
    router = APIRouter(
        prefix="/api/v1/developer/example",
        dependencies=[Depends(require_developer_authorization)],
    )

    @router.get("")
    def read():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/v1/developer/example").status_code == 403
    assert client.get(
        "/api/v1/developer/example",
        headers={"X-Creator-OS-Developer": "true"},
    ).status_code == 200
    remote_client = TestClient(app, base_url="https://public.example")
    assert remote_client.get(
        "/api/v1/developer/example",
        headers={
            "X-Creator-OS-Developer": "true",
            "X-Forwarded-Host": "localhost",
            "X-Forwarded-For": "127.0.0.1",
        },
    ).status_code == 403


def test_configured_developer_key_rejects_missing_invalid_and_proxy_fallback(
    monkeypatch,
):
    monkeypatch.setenv("CREATOR_OS_DEVELOPER_KEY", "temporary-test-key")
    router = APIRouter(
        prefix="/api/v1/developer/example",
        dependencies=[Depends(require_developer_authorization)],
    )

    @router.get("")
    def read():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    assert client.get("/api/v1/developer/example").status_code == 403
    assert client.get(
        "/api/v1/developer/example",
        headers={
            "X-Creator-OS-Developer": "true",
            "X-Forwarded-Host": "localhost",
            "X-Forwarded-For": "127.0.0.1",
        },
    ).status_code == 403
    assert client.get(
        "/api/v1/developer/example",
        headers={"X-Creator-OS-Developer-Key": "wrong"},
    ).status_code == 403
    assert client.get(
        "/api/v1/developer/example",
        headers={"X-Creator-OS-Developer-Key": "temporary-test-key"},
    ).status_code == 200


def test_authoritative_delivery_url_uses_existing_security_rules():
    gateway = ConversationGateway(
        SimpleNamespace(process_message=lambda *_args, **_kwargs: None),
        allowed_fanvue_hostnames=(
            "fanvue.com", "www.fanvue.com", "share.fanvue.com",
        ),
    )
    assert gateway._is_allowed_link("https://share.fanvue.com/offer")
    assert gateway._is_allowed_link("https://www.fanvue.com/offer")
    assert not gateway._is_allowed_link("http://fanvue.com/offer")
    assert not gateway._is_allowed_link("https://user@fanvue.com/offer")
    assert not gateway._is_allowed_link("https://evil.example/offer")


def test_reconciliation_worker_recovers_retries_and_expires():
    calls = []
    processor = SimpleNamespace(
        process_pending_events=lambda: calls.append("processed") or []
    )
    intents = SimpleNamespace(
        expire_due=lambda: calls.append("expired") or [object()]
    )
    worker = CommerceReconciliationWorker(
        processor=processor, intent_service=intents,
        heartbeat=SimpleNamespace(), interval_seconds=30,
    )
    import app.workers.commerce_reconciliation as module
    original = module.recover_stale_claims
    module.recover_stale_claims = (
        lambda limit: calls.append(("recovered", limit)) or [object()]
    )
    try:
        diagnostics = worker.run_once()
    finally:
        module.recover_stale_claims = original
    assert calls == [("recovered", 100), "processed", "expired"]
    assert diagnostics["recovered_count"] == 1
    assert diagnostics["expired_intent_count"] == 1


def test_reconciliation_worker_stops_gracefully_and_can_restart():
    lifecycle = []

    class Heartbeat:
        register_startup = lambda self: lifecycle.append("startup")
        record_success = lambda self: lifecycle.append("success")
        record_failure = lambda self, _error: lifecycle.append("failure")
        record_stopping = lambda self: lifecycle.append("stopping")
        record_shutdown = lambda self: lifecycle.append("shutdown")

    stop = threading.Event()
    worker = CommerceReconciliationWorker(
        processor=SimpleNamespace(process_pending_events=lambda: []),
        intent_service=SimpleNamespace(expire_due=lambda: []),
        heartbeat=Heartbeat(),
        interval_seconds=5,
    )
    worker.run_once = lambda: stop.set() or {}
    worker.run(stop)
    assert lifecycle == ["startup", "success", "stopping", "shutdown"]

    restarted = threading.Event()
    worker.run_once = lambda: restarted.set() or stop.set() or {}
    stop.clear()
    worker.run(stop)
    assert restarted.is_set()
    assert lifecycle[-4:] == ["startup", "success", "stopping", "shutdown"]


def test_creator_payment_prefers_creator_uuid_resolution(monkeypatch):
    import app.services.commerce_signal_service as module
    monkeypatch.setattr(
        module, "get_account_by_creator_uuid",
        lambda value: {"id": 7} if value == "creator-1" else None,
    )
    assert CommerceSignalService._account("creator-1", None)["id"] == 7


def test_purchase_acknowledgement_write_is_idempotent():
    stored = SimpleNamespace(
        purchase_intent_id=uuid4(), purchase_acknowledged_at=None
    )

    class Repository:
        def mark_purchase_acknowledged(self, intent_id, *, at):
            assert intent_id == stored.purchase_intent_id
            if stored.purchase_acknowledged_at is None:
                stored.purchase_acknowledged_at = at
            return stored

    service = PurchaseIntentService(repository=Repository(), clock=lambda: NOW)
    first = service.acknowledge_purchase(stored.purchase_intent_id)
    second = service.acknowledge_purchase(stored.purchase_intent_id)
    assert first.purchase_acknowledged_at == NOW
    assert second.purchase_acknowledged_at == NOW


def test_webhook_handler_queues_without_inline_reconciliation():
    source = open(
        "app/fanvue_callback_server.py", encoding="utf-8"
    ).read()
    handler = source[source.index('@app.post("/webhooks/fanvue")'):]
    assert "processor.process_pending_events()" not in handler
    assert '"queued": True' in handler
    assert 'print("\\nRAW PAYLOAD:")' not in handler


def test_webhook_uniqueness_is_structural_and_public_route_is_unchanged():
    migration = open(
        "migrations/forward/20260725_009_launch_blocker_hardening.sql",
        encoding="utf-8",
    ).read()
    repository = open(
        "app/repositories/webhook_event_repository.py", encoding="utf-8"
    ).read()
    callback = open("app/fanvue_callback_server.py", encoding="utf-8").read()
    assert "CREATE UNIQUE INDEX" in migration
    assert "external_event_id" in migration
    assert "ON CONFLICT (external_event_id)" in repository
    assert '@app.post("/webhooks/fanvue")' in callback
    assert "require_developer_authorization" not in callback

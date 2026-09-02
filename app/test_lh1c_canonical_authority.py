from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.one_on_one_ppv_send_service import OneOnOnePPVSendService


ROOT = Path(__file__).resolve().parents[1]


class Engine:
    def process_message(self, user_id, message, chat_history=None, runtime_injection=None):
        return {"response": "hello", "send_offer": False}


class Sessions:
    def __init__(self, order=None, *, active=True):
        self.calls = []
        self.order = order if order is not None else []
        self.session = SimpleNamespace(sales_session_id=uuid4()) if active else None

    def resolve_active_conversation(self, **values):
        self.calls.append(values)
        self.order.append("session")
        return self.session

    def resolve_or_start_conversation(self, **values):
        self.calls.append(values)
        self.order.append("session")
        return self.session

    def associate_purchase_intent(self, **values):
        self.order.append("associate")
        self.association = values


def test_gateway_resolves_only_an_active_canonical_session_before_engine():
    sessions = Sessions()
    gateway = ConversationGateway(
        Engine(), allowed_fanvue_hostnames=["fanvue.com"],
        sales_session_service=sessions,
    )
    gateway.execute(ConversationGatewayInput(
        engine_user_id="4:8", message_text="hello", chat_history=[],
        correlation_id="turn-1",
        brain_context=ConversationBrainContext(
            creator_profile_id=3, customer_identifier="4:8",
            conversation_identifier="thread-11", fanvue_account_id=4,
            fanvue_user_id=8, conversation_thread_id=11,
        ),
    ))
    assert sessions.calls[0]["conversation_thread_id"] == 11
    assert "actor_identifier" not in sessions.calls[0]


def test_gateway_records_sanitized_active_session_lookup_error():
    class BrokenSessions:
        def resolve_active_conversation(self, **_values):
            raise ValueError(
                "lookup failed token=must-not-appear https://private.invalid/path"
            )

    output = ConversationGateway(
        Engine(), allowed_fanvue_hostnames=["fanvue.com"],
        sales_session_service=BrokenSessions(),
    ).execute(ConversationGatewayInput(
        engine_user_id="4:8", message_text="hello", chat_history=[],
        correlation_id="turn-error",
        brain_context=ConversationBrainContext(
            creator_profile_id=3, customer_identifier="synthetic-customer",
            conversation_identifier="thread-11", fanvue_account_id=4,
            fanvue_user_id=8, conversation_thread_id=11,
            developer_mode=True,
        ),
    ))
    evidence = output.diagnostic_metadata["salesSessionError"]
    assert output.error_code == "canonical_sales_session_unavailable"
    assert evidence["exceptionClass"] == "ValueError"
    assert evidence["boundary"] == "ConversationGateway.active_sales_session_lookup"
    assert evidence["scenarioIdentity"] == "synthetic-customer"
    assert "must-not-appear" not in evidence["message"]
    assert "private.invalid" not in evidence["message"]


def _ppv_service(*, dry_run, order, active_session=True):
    sessions = Sessions(order, active=active_session)
    offering_id = uuid4()
    publication_id = uuid4()
    decision = SimpleNamespace(
        sell_allowed=True, recommended_offering_id=offering_id,
        recommended_offering_price_minor=2500,
        recommended_offering_currency="USD", decision_id=uuid4(),
        decision=SimpleNamespace(value="PRESENT_OFFER"),
        reason_code=SimpleNamespace(value="NO_ACTIVE_OFFER"),
    )

    class Brain:
        def evaluate_for_buyer(self, **_values):
            order.append("authorize")
            return decision

    identity = SimpleNamespace(
        id=5, telegram_user_id=6, telegram_chat_id=7,
        external_fanvue_user_uuid=uuid4(),
    )

    class Intents:
        def __init__(self): self.calls = []
        def replace_active_intent(self, **values):
            order.append("intent")
            self.calls.append(values)
            return SimpleNamespace(purchase_intent_id=uuid4())

    intents = Intents()
    service = OneOnOnePPVSendService(
        4, sales_session_service=sessions,
        customer_sales_brain_service=Brain(),
        purchase_intent_service=intents,
        identity_repository=SimpleNamespace(
            get_by_local_user_id=lambda *_values: identity
        ),
        creator_profile_resolver=lambda _value: {"id": 3},
        customer_fetcher=lambda *_values: {
            "fanvue_account_id": 4,
            "fanvue_user_uuid": str(identity.external_fanvue_user_uuid),
        },
        thread_resolver=lambda **_values: {"id": 11},
        caption_service=SimpleNamespace(
            generate_context_aware_caption=lambda **_values: "caption"
        ),
        payload_builder=SimpleNamespace(
            build_paid_ppv_payload=lambda *_values: {"message": "caption"}
        ),
        content_guard=SimpleNamespace(
            can_deliver_content=lambda **_values: {"allowed": True}
        ),
        global_safety=SimpleNamespace(
            can_send_monetization=lambda: {"allowed": True}
        ),
        global_execution_guard=SimpleNamespace(
            validate_execution=lambda **_values: {"blocked": False}
        ),
        fanvue_api=SimpleNamespace(
            send_chat_message=lambda **_values: order.append("send") or {"success": True}
        ),
    )
    content = {
        "commercial_offering_id": str(offering_id),
        "commercial_publication_id": str(publication_id),
        "provider_resource_id": "resource-1",
        "delivery_url": "https://fanvue.com/item/1", "provider": "FANVUE",
    }
    result = service.send_ppv_to_user(
        fanvue_account_id=4, fanvue_user_uuid=8, thread_id="provider-thread",
        content_item=content, price=1.0, dry_run=dry_run,
    )
    return result, sessions, intents


def test_one_on_one_dry_run_uses_session_and_authorization_without_persistence():
    order = []
    result, _sessions, intents = _ppv_service(dry_run=True, order=order)
    assert result["status"] == "dry_run"
    assert order == ["session", "authorize"]
    assert intents.calls == []


def test_one_on_one_creates_intent_after_authorization_and_before_delivery():
    order = []
    result, sessions, intents = _ppv_service(dry_run=False, order=order)
    assert result["success"] is True
    assert order == ["session", "authorize", "intent", "associate", "send"]
    assert intents.calls[0]["expected_price_minor"] == 2500
    assert sessions.association["purchase_intent_id"] is not None


def test_one_on_one_single_sale_does_not_implicitly_start_session():
    order = []
    result, sessions, intents = _ppv_service(
        dry_run=False, order=order, active_session=False,
    )
    assert result["success"] is True
    assert result["sales_session_id"] is None
    assert order == ["session", "authorize", "intent", "send"]
    assert len(intents.calls) == 1
    assert not hasattr(sessions, "association")


def test_supported_production_authority_import_guards():
    decision = (ROOT / "app/engine/decision_engine.py").read_text(encoding="utf-8")
    ppv = (ROOT / "app/services/one_on_one_ppv_send_service.py").read_text(encoding="utf-8")
    canonical = "\n".join(
        (ROOT / name).read_text(encoding="utf-8") for name in (
            "app/services/conversation_gateway.py",
            "app/services/customer_sales_brain_service.py",
            "app/services/commercial_intelligence_service.py",
            "app/services/commercial_offering_selector_service.py",
        )
    )
    assert "BuyerSessionService" not in decision
    assert "BuyerSessionService" not in ppv
    assert "ContentOwnershipService" not in canonical
    assert "CustomerIntelligenceCompatibilityAdapter" not in canonical

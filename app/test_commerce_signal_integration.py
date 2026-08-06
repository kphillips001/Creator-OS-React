from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commerce_signals as signal_api
from app.models.purchase_intent import (
    AttributionResult,
    PurchaseIntent,
    PurchaseIntentStatus,
)
from app.services.commerce_signal_service import CommerceSignalService
from app.services.fanvue_official_client import FanvueOfficialClient
from app.services.telegram_purchase_intent_service import (
    TelegramPurchaseIntentService,
)
from app.services.webhook_normalizer_service import WebhookNormalizerService


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)
BUYER = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


def test_current_webhook_topics_normalize_without_breaking_legacy():
    service = WebhookNormalizerService()
    assert service.normalize({}, {"x-fanvue-topic": "purchase.new"})[
        "event_type"
    ] == "purchase_new"
    assert service.normalize({}, {
        "x-fanvue-topic": "creator.payment.succeeded"
    })["event_type"] == "creator_payment_succeeded"
    assert service.normalize({}, {
        "x-fanvue-topic": "purchase.created"
    })["event_type"] == "purchase_created"


def test_official_client_uses_documented_earnings_transaction_filter():
    client = FanvueOfficialClient.__new__(FanvueOfficialClient)
    calls = []
    client.request = lambda method, path, **kwargs: calls.append(
        (method, path, kwargs)
    ) or type("Response", (), {"json": lambda self: {"data": []}})()
    assert client.get_earnings_by_transaction("order-1") == {"data": []}
    assert calls == [(
        "GET", "/insights/earnings",
        {"params": {"transactionOrderIds": "order-1"}},
    )]


class Reconciliations:
    def __init__(self):
        self.row = None
        self.verified = []
        self.pending = []

    def get_or_create_reconciliation(self, **values):
        if self.row:
            return self.row, False
        self.row = {
            **values, "reconciliation_id": uuid4(), "state": "PENDING",
        }
        return self.row, True

    def mark_verified(self, item_id, **values):
        self.verified.append((item_id, values))
        self.row["state"] = "VERIFIED"

    def mark_pending(self, item_id, **values):
        self.pending.append((item_id, values))

    def get_signal(self, **lookup):
        return {
            "external_fanvue_user_uuid": BUYER,
            "telegram_user_id": 22, "identity_resolved": True,
            "lifetime_gross_minor": 999, "purchase_count": 1,
            "last_purchase_at": NOW, "commercial_offering_id": uuid4(),
            "current_offer_status": "PURCHASED",
            "attribution_result": "ATTRIBUTED",
            "last_transaction_order_id": "order-1",
            "reconciliation_state": "VERIFIED",
        }


class Client:
    calls = []

    def __init__(self, account_id):
        self.account_id = account_id

    def get_earnings_by_transaction(self, transaction_id):
        self.calls.append((self.account_id, transaction_id))
        return {"data": [{
            "transactionOrderId": transaction_id, "gross": 999, "net": 800,
            "date": NOW.isoformat(), "source": "mediaLink",
            "status": "succeeded",
        }]}


@dataclass
class Identity:
    id: int = 11
    telegram_user_id: int = 22
    telegram_chat_id: int = 22
    fanvue_account_id: int = 7
    external_fanvue_user_uuid: UUID = BUYER


class Identities:
    def get_by_external_fanvue_user_uuid(self, account, buyer):
        assert (account, buyer) == (7, BUYER)
        return Identity()

    def get_by_telegram_user_id(self, user):
        return Identity() if user == 22 else None


class Customers:
    def __init__(self):
        self.calls = []
        self.identity_updates = []

    def record_verified_purchase(self, **values):
        self.calls.append(values)
        profile = type("Profile", (), {
            "customer_commerce_profile_id": uuid4(),
        })()
        return type("Result", (), {
            "profile": profile, "transaction_recorded": len(self.calls) == 1,
        })()

    def update_identity(self, *args, **kwargs):
        self.identity_updates.append((args, kwargs))


def purchase_intent():
    return PurchaseIntent(
        purchase_intent_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=7, telegram_identity_mapping_id=11,
        telegram_user_id=22, telegram_chat_id=22,
        external_fanvue_user_uuid=BUYER, commercial_offering_id=uuid4(),
        commercial_publication_id=uuid4(), provider="FANVUE",
        provider_resource_id="link-1", delivery_url="https://fanvue.com/link",
        telegram_message_id=30, conversation_id="conversation",
        correlation_id=uuid4(), expected_price_minor=999,
        expected_currency="USD", status=PurchaseIntentStatus.PRESENTED,
        created_at=NOW - timedelta(minutes=2),
        presented_at=NOW - timedelta(minutes=1), clicked_at=None,
        expires_at=NOW + timedelta(hours=1), abandoned_at=None,
        purchased_at=None, provider_transaction_order_id=None,
        provider_payment_id=None, provider_event_id=None,
        attribution_result=AttributionResult.PENDING,
        attribution_reason=None, created_metadata={}, updated_at=NOW,
    )


class IntentRepository:
    def __init__(self, items):
        self.items = items
        self.purchased = []

    def list_candidates(self, **lookup):
        return self.items

    def mark_purchased(self, item_id, **values):
        self.purchased.append((item_id, values))
        item = next(item for item in self.items if item.purchase_intent_id == item_id)
        return replace(
            item, status=PurchaseIntentStatus.PURCHASED,
            attribution_result=AttributionResult.ATTRIBUTED,
            purchased_at=values["at"],
        )


class Intents:
    def __init__(self):
        self.references = []
        self.unknown = []

    def record_payment_reference(self, item_id, **values):
        self.references.append((item_id, values))

    def mark_unknown(self, item_id, **values):
        self.unknown.append((item_id, values))


class PhotoshootLifecycles:
    def __init__(self):
        self.calls = []

    def synchronize_attributed_purchase(self, **values):
        self.calls.append(values)
        return object()


def service(monkeypatch, candidates):
    reconciliation = Reconciliations()
    customers = Customers()
    intent_service = Intents()
    intent_repository = IntentRepository(candidates)
    monkeypatch.setattr(
        "app.services.commerce_signal_service.get_account_by_fanvue_user_uuid",
        lambda value: {"id": 7},
    )
    monkeypatch.setattr(
        "app.services.commerce_signal_service.get_active_creator_profile",
        lambda value: {"id": 2},
    )
    lifecycles = PhotoshootLifecycles()
    return CommerceSignalService(
        repository=reconciliation, identity_repository=Identities(),
        customer_service=customers, purchase_intent_service=intent_service,
        purchase_intent_repository=intent_repository,
        photoshoot_lifecycle_service=lifecycles, client_factory=Client,
    ), reconciliation, customers, intent_service, intent_repository


def test_verified_earnings_updates_customer_and_attributes_one_hard_match(monkeypatch):
    candidate = purchase_intent()
    integration, ledger, customers, intents, intent_repository = service(
        monkeypatch, [candidate]
    )
    payload = {
        "recipientUuid": str(uuid4()), "price": 999, "purchaseType": "media",
        "sender": {"uuid": str(BUYER), "handle": "buyer"},
        "timestamp": NOW.isoformat(), "transactionOrderId": "order-1",
        "transactionOrderStatus": "pendingBalance", "eventId": "event-1",
    }
    result = integration.process_webhook({
        "event_type": "purchase_new", "payload": payload,
        "external_event_id": "event-1", "fanvue_account_id": str(uuid4()),
    })
    assert result["state"] == "VERIFIED"
    assert result["attribution"]["state"] == "ATTRIBUTED"
    assert customers.calls[0]["gross_minor"] == 999
    assert customers.calls[0]["transaction_order_id"] == "order-1"
    assert len(intents.references) == 1
    assert len(intent_repository.purchased) == 1
    assert len(integration.photoshoot_lifecycles.calls) == 1
    assert ledger.verified

    duplicate = integration.process_webhook({
        "event_type": "purchase_new", "payload": payload,
        "external_event_id": "event-1", "fanvue_account_id": str(uuid4()),
    })
    assert duplicate["duplicate"] is True
    assert len(customers.calls) == 1


def test_multiple_hard_matches_are_unknown_without_guessing(monkeypatch):
    first, second = purchase_intent(), purchase_intent()
    integration, _, _, intents, repository = service(
        monkeypatch, [first, second]
    )
    result = integration._attribute(
        creator_profile_id=2, fanvue_account_id=7, buyer_uuid=BUYER,
        amount_minor=999, payment_timestamp=NOW,
        transaction_id="order-1", payment_id="payment-1",
        event_id="event-1", media_link_purchase=True,
        customer_commerce_profile_id=uuid4(),
    )
    assert result == {
        "state": "UNKNOWN",
        "reason": "MULTIPLE_HARD_MATCHING_CANDIDATES",
        "candidateCount": 2,
    }
    assert len(intents.unknown) == 2
    assert repository.purchased == []
    assert integration.photoshoot_lifecycles.calls == []


def test_retry_resynchronizes_already_attributed_purchase(monkeypatch):
    candidate = replace(
        purchase_intent(), status=PurchaseIntentStatus.PURCHASED,
        attribution_result=AttributionResult.ATTRIBUTED,
        provider_transaction_order_id="order-1", purchased_at=NOW,
    )
    integration, _, _, _, repository = service(monkeypatch, [candidate])

    result = integration._attribute(
        creator_profile_id=2, fanvue_account_id=7, buyer_uuid=BUYER,
        amount_minor=999, payment_timestamp=NOW,
        transaction_id="order-1", payment_id="payment-1",
        event_id="event-1", media_link_purchase=True,
        customer_commerce_profile_id=uuid4(),
    )

    assert result["state"] == "ATTRIBUTED"
    assert result["lifecycleSynchronized"] is True
    assert repository.purchased == []
    assert len(integration.photoshoot_lifecycles.calls) == 1


def test_creator_payment_id_converges_through_canonical_earnings(monkeypatch):
    integration, ledger, customers, *_ = service(monkeypatch, [])
    creator_uuid = uuid4()
    result = integration.process_webhook({
        "event_type": "creator_payment_succeeded",
        "external_event_id": "payment-event-1",
        "fanvue_account_id": str(creator_uuid),
        "payload": {"data": {
            "id": "order-1", "status": "succeeded",
            "purchaser": {"uuid": str(BUYER)},
            "creator": {"uuid": str(creator_uuid)},
            "gross": 999, "net": 800,
        }},
    })
    assert result["state"] == "VERIFIED"
    assert ledger.row["observed_transaction_id"] == "order-1"
    assert customers.calls[0]["transaction_order_id"] == "order-1"


def test_bot_facing_signal_is_read_only_projection(monkeypatch):
    integration, *_ = service(monkeypatch, [])
    signal = integration.get_signal(
        creator_profile_id=2, external_fanvue_user_uuid=BUYER,
    )
    assert signal.identity_resolved is True
    assert signal.conversion_state == "PURCHASED"
    assert signal.latest_transaction == "order-1"


def test_bot_facing_signal_api_is_read_only(monkeypatch):
    signal = type("Signal", (), {
        "buyer_uuid": str(BUYER), "telegram_user_id": 22,
        "identity_resolved": True, "lifetime_spend_minor": 999,
        "purchase_count": 1, "last_purchase_at": NOW,
        "current_active_offer_id": "offering-1",
        "current_offer_status": "PRESENTED",
        "conversion_state": "OFFER_PRESENTED",
        "latest_transaction": "order-1",
        "attribution_state": "PENDING",
        "reconciliation_state": "VERIFIED",
    })()
    fake = type("Service", (), {"get_signal": lambda self, **kwargs: signal})
    monkeypatch.setattr(signal_api, "CommerceSignalService", fake)
    monkeypatch.setattr(signal_api, "_creator_profile", lambda: {"id": 2})
    app = FastAPI()
    app.include_router(signal_api.router)
    client = TestClient(app)
    response = client.get(
        f"/api/v1/developer/commerce-signals?buyer_uuid={BUYER}",
        headers={"X-Creator-OS-Developer": "true"},
    )
    assert response.status_code == 200
    assert response.json()["conversionState"] == "OFFER_PRESENTED"
    assert client.post(
        "/api/v1/developer/commerce-signals",
        headers={"X-Creator-OS-Developer": "true"},
    ).status_code == 405


def test_telegram_intent_wraps_delivery_without_exposing_id():
    class PurchaseIntents:
        def __init__(self):
            self.created = []
            self.presented = []
            self.abandoned = []

        def replace_active_intent(self, **values):
            self.created.append(values)
            return type("Intent", (), {"purchase_intent_id": uuid4()})()

        def confirm_presented(self, item_id, **values):
            self.presented.append((item_id, values))

        def mark_abandoned(self, item_id):
            self.abandoned.append(item_id)

    intents = PurchaseIntents()
    service = TelegramPurchaseIntentService(
        creator_profile_id=2, fanvue_account_id=7,
        identity_repository=Identities(), purchase_intent_service=intents,
        clock=lambda: NOW,
    )
    result = type("Result", (), {
        "correlation_id": "telegram:22:5",
        "diagnostic_metadata": {
            "final_offer_authorized": True,
            "customer_sales_brain_evaluated": True,
            "offering_selected": True, "offering_id": str(uuid4()),
            "publication_id": str(uuid4()), "provider": "FANVUE",
            "provider_resource_id": "link-1",
            "delivery_url": "https://fanvue.com/link",
            "price_minor": 999, "currency": "USD",
        },
    })()
    payload = type("Payload", (), {
        "telegram_user_id": 22, "message_id": 5,
    })()
    created = service.create_before_delivery(result, payload)
    service.confirm_delivery(created, telegram_message_id=30)
    assert intents.created[0]["external_fanvue_user_uuid"] == BUYER
    assert intents.presented[0][1]["telegram_message_id"] == 30

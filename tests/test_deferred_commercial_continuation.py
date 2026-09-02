from types import SimpleNamespace
from uuid import uuid4

from app.services.telegram_purchase_intent_service import (
    TelegramPurchaseIntentService,
)
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult


class DeferredContinuationSpy:
    def __init__(self):
        self.ready_calls = []

    def ready_deferred_continuation(self, **values):
        self.ready_calls.append(values)
        return True

    def claim_deferred_continuation(self, **values):
        self.claim_call = values
        return SimpleNamespace()

    def consume_deferred_continuation(self, **values):
        self.consume_call = values
        return SimpleNamespace()


def test_durable_purchase_acknowledgement_releases_deferred_continuation():
    intent_id = uuid4()
    acknowledged = SimpleNamespace(
        purchase_intent_id=intent_id,
        telegram_user_id=7_857_064_998,
    )
    intents = SimpleNamespace(
        acknowledge_purchase=lambda received: (
            acknowledged if received == intent_id else None
        )
    )
    deferred = DeferredContinuationSpy()
    service = TelegramPurchaseIntentService.__new__(
        TelegramPurchaseIntentService
    )
    service.creator_profile_id = 11
    service.fanvue_account_id = 22
    service.intents = intents
    service.deferred_continuations = deferred
    service.sales_sessions = SimpleNamespace(repository=None)

    result = service.acknowledge_purchase(intent_id)

    assert result is acknowledged
    assert deferred.ready_calls == [{
        "creator_profile_id": 11,
        "fanvue_account_id": 22,
        "telegram_user_id": 7_857_064_998,
    }]


def test_failed_acknowledgement_does_not_release_deferred_continuation():
    deferred = DeferredContinuationSpy()
    service = TelegramPurchaseIntentService.__new__(
        TelegramPurchaseIntentService
    )
    service.creator_profile_id = 11
    service.fanvue_account_id = 22
    service.intents = SimpleNamespace(acknowledge_purchase=lambda _intent: None)
    service.deferred_continuations = deferred
    service.sales_sessions = SimpleNamespace(repository=None)

    assert service.acknowledge_purchase(uuid4()) is None
    assert deferred.ready_calls == []


def test_authorized_presentation_claims_then_consumes_deferred_intent(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "false"
    )
    offering_id, publication_id, intent_id = uuid4(), uuid4(), uuid4()
    stored = SimpleNamespace(
        purchase_intent_id=intent_id, status="CREATED",
        commercial_offering_id=offering_id,
    )

    class Repository:
        def get_by_correlation(self, _correlation): return None

    class Intents:
        repository = Repository()
        def __init__(self): self.created = 0
        def replace_active_intent(self, **_values):
            self.created += 1
            return stored

    identity = SimpleNamespace(
        id=uuid4(), telegram_user_id=77, telegram_chat_id=77,
        external_fanvue_user_uuid=uuid4(), fanvue_account_id=22,
    )
    identities = SimpleNamespace(
        get_by_telegram_user_id=lambda _user_id: identity,
        get_verified_by_telegram_user_id=lambda _user_id: identity,
    )
    deferred = DeferredContinuationSpy()
    intents = Intents()
    service = TelegramPurchaseIntentService(
        creator_profile_id=11, fanvue_account_id=22,
        identity_repository=identities,
        purchase_intent_service=intents,
        sales_session_service=SimpleNamespace(repository=None),
        deferred_continuation_service=deferred,
    )
    result = TelegramInboundResult(
        correlation_id="telegram:77:9001", telegram_chat_id=77,
        telegram_user_id=77, message_id=9001, engine_user_id="22:77",
        response_text="come see", offer_authorized=True, offer_link=None,
        blocked=False, error_code=None, delivery_payload={"metadata": {}},
        diagnostic_metadata={
            "final_offer_authorized": True,
            "customer_sales_brain_evaluated": True,
            "offering_selected": True,
            "offering_id": str(offering_id),
            "publication_id": str(publication_id),
            "delivery_url": "https://fanvue.com/example",
            "provider_resource_id": "provider-resource",
            "provider": "FANVUE", "price_minor": 999, "currency": "USD",
            "deferred_continuation": {"state": "READY"},
        },
    )
    payload = TelegramInboundPayload(
        telegram_user_id=77, telegram_chat_id=77,
        message_text="anything else", message_id=9001,
    )

    assert service.create_before_delivery(result, payload) is stored
    assert intents.created == 1
    assert deferred.claim_call["correlation_id"] == "telegram:77:9001"
    assert deferred.consume_call["correlation_id"] == "telegram:77:9001"
    assert result.diagnostic_metadata["deferred_continuation_claimed"] is True
    assert result.diagnostic_metadata["deferred_continuation_consumed"] is True

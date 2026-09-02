from types import SimpleNamespace
from uuid import uuid4

from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_purchase_intent_service import (
    TelegramPurchaseIntentService,
)
from app.services.telegram_sales_delivery_service import (
    TelegramSalesDeliveryService,
)


def _offering():
    return SimpleNamespace(
        offering_id=uuid4(), publication_id=uuid4(),
        offering_type="SINGLE_IMAGE",
        title="CONTROLLED SMOKE TEST — $3 SINGLE",
        description="Operator-controlled test. Do not use for production sales.",
        price_minor=300, currency="USD", provider="FANVUE",
        provider_resource_id="canonical-link-id",
        delivery_url="https://fanvue.example/direct-media-link",
    )


def test_unmapped_authoritative_delivery_is_unlock_pending_and_price_neutral():
    offering = _offering()
    decision = SimpleNamespace(
        identity_resolved=False, bundle_sales_context={},
        next_sales_action=None, decision_metadata={},
    )
    gateway = ConversationGateway.__new__(ConversationGateway)

    offer_link, delivery_type, delivery_mode, requires_payment, payload = (
        gateway._authoritative_delivery(
            response_text="I saved a private one I think you'll love. Ready?",
            offering=offering,
            customer_sales_decision=decision,
        )
    )

    assert offer_link is None
    assert delivery_type == "SINGLE_IMAGE"
    assert delivery_mode == "unlock_gateway"
    assert requires_payment is True
    assert payload["message_text"] == (
        "I saved a private one I think you'll love. Ready?"
    )
    assert "media_link" not in payload
    assert offering.delivery_url not in str(payload)
    assert offering.title not in str(payload)
    assert offering.description not in str(payload)
    assert payload["metadata"]["price_minor"] == 300
    assert payload["metadata"]["customer_facing_price_status"] == (
        "ESTABLISHED_BY_UNLOCK_FLOW"
    )


def test_unmapped_purchase_intent_keeps_base_internal_and_prepares_unlock(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true",
    )
    offering = _offering()
    created_values = []
    intent = SimpleNamespace(
        purchase_intent_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
        telegram_chat_id=7_857_064_998,
        commercial_offering_id=offering.offering_id,
        commercial_publication_id=offering.publication_id,
        expected_price_minor=300, expected_currency="USD",
    )

    class Intents:
        def replace_active_intent(self, **values):
            created_values.append(values)
            return intent

    issued = []

    class Gateway:
        def issue(self, received):
            issued.append(received.purchase_intent_id)
            return None, "https://creator.example/api/v1/commerce/unlock/token"

    service = TelegramPurchaseIntentService(
        creator_profile_id=2,
        fanvue_account_id=2,
        identity_repository=SimpleNamespace(
            get_verified_by_telegram_user_id=lambda _user_id: None,
            get_by_telegram_user_id=lambda _user_id: None,
        ),
        purchase_intent_service=Intents(),
        unlock_gateway_service=Gateway(),
        sales_session_service=SimpleNamespace(),
    )
    result = SimpleNamespace(
        correlation_id="telegram:7857064998:future-test",
        delivery_payload={
            "message_text": "I saved a private one. Ready?",
            "metadata": {"price_minor": 300},
        },
        diagnostic_metadata={
            "final_offer_authorized": True,
            "customer_sales_brain_evaluated": True,
            "offering_selected": True,
            "offering_id": str(offering.offering_id),
            "publication_id": str(offering.publication_id),
            "provider": "FANVUE",
            "provider_resource_id": offering.provider_resource_id,
            "delivery_url": offering.delivery_url,
            "price_minor": 300,
            "currency": "USD",
        },
    )
    payload = SimpleNamespace(
        telegram_user_id=7_857_064_998,
        telegram_chat_id=7_857_064_998,
        message_id=6000,
    )

    assert service.create_before_delivery(result, payload) is intent
    assert created_values[0]["expected_price_minor"] == 300
    assert issued == [intent.purchase_intent_id]
    assert result.delivery_payload["media_link"].startswith(
        "https://creator.example/api/v1/commerce/unlock/"
    )
    assert offering.delivery_url not in str(result.delivery_payload)
    assert result.delivery_payload["metadata"]["private_chat_unlock_button"][
        "url"
    ] == result.delivery_payload["media_link"]


def test_unmapped_bootstrap_uses_durable_prospect_dispatch_namespace():
    result = SimpleNamespace(diagnostic_metadata={
        "telegram_identity_eligibility": "UNMAPPED_BOOTSTRAP",
    })
    operation, created = TelegramSalesDeliveryService().prepare(
        intent=SimpleNamespace(), result=result, payload=SimpleNamespace(),
    )
    assert operation is None
    assert created is False


def test_purchase_intent_same_correlation_is_reused_exactly_once(monkeypatch):
    monkeypatch.setenv(
        "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true",
    )
    offering = _offering()
    stored = {}
    replacements = []
    intent = SimpleNamespace(
        purchase_intent_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=2, telegram_user_id=7_857_064_998,
        telegram_chat_id=7_857_064_998,
        commercial_offering_id=offering.offering_id,
        commercial_publication_id=offering.publication_id,
        status=SimpleNamespace(value="CREATED"),
    )

    class Repository:
        def get_by_correlation(self, correlation):
            return stored.get(correlation)

    class Intents:
        repository = Repository()
        def replace_active_intent(self, **values):
            replacements.append(values)
            stored[values["correlation_id"]] = intent
            return intent

    service = TelegramPurchaseIntentService(
        creator_profile_id=2, fanvue_account_id=2,
        identity_repository=SimpleNamespace(
            get_verified_by_telegram_user_id=lambda _user_id: None,
            get_by_telegram_user_id=lambda _user_id: None,
        ),
        purchase_intent_service=Intents(),
        unlock_gateway_service=SimpleNamespace(
            issue=lambda _intent: (
                None, "https://creator.example/api/v1/commerce/unlock/token"
            ),
        ),
        sales_session_service=SimpleNamespace(),
    )
    payload = SimpleNamespace(
        telegram_user_id=7_857_064_998,
        telegram_chat_id=7_857_064_998,
        message_id=6001,
    )

    def result():
        return SimpleNamespace(
            correlation_id="telegram:7857064998:6001",
            delivery_payload={"message_text": "Here you go.", "metadata": {}},
            diagnostic_metadata={
                "final_offer_authorized": True,
                "customer_sales_brain_evaluated": True,
                "offering_selected": True,
                "offering_id": str(offering.offering_id),
                "publication_id": str(offering.publication_id),
                "provider": "FANVUE",
                "provider_resource_id": offering.provider_resource_id,
                "delivery_url": offering.delivery_url,
                "price_minor": 300,
                "currency": "USD",
            },
        )

    first = result()
    second = result()
    assert service.create_before_delivery(first, payload) is intent
    assert service.create_before_delivery(second, payload) is intent
    assert len(replacements) == 1
    assert first.diagnostic_metadata["purchase_intent_created"] is True
    assert second.diagnostic_metadata["purchase_intent_reused"] is True

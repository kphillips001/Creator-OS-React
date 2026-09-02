from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.chat_commerce_service import ChatCommerceService


def offering(offering_type="SINGLE_IMAGE"):
    return SimpleNamespace(
        offering_id=uuid4(), offering_type=offering_type,
        title="Private Beach Photo", description="A sunny beach portrait",
        price_minor=999, currency="USD", primary_sales_channel="AI_CHAT",
        delivery_url="https://fanvue.com/fvml-active", provider="FANVUE",
        provider_resource_id="link-1", hero_asset_id=42,
        published_at=datetime.now(timezone.utc),
    )


class Sales:
    def __init__(self, result=None):
        self.result = result
        self.calls = []

    def recommend_best(self, **values):
        self.calls.append(values)
        return self.result


def context(service, message, purchase=True):
    return service.build_context(
        creator_profile_id=2, purchase_intent=purchase,
        message_text=message, diagnostics={"intent": {"themes": ["beach"]}},
        customer_identifier="customer-1", conversation_identifier="conversation-1",
        relationship_level="sales", recommendation_reason="Buying intent detected",
    )


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Can I buy one picture?", "SINGLE_IMAGE"),
        ("Do you have a photoset?", "PHOTOSET"),
        ("I want a video", "VIDEO"),
        ("What do you have?", None),
    ],
)
def test_media_type_translation(message, expected):
    service = ChatCommerceService(
        sales_service=Sales(), commerce_mode="COMPATIBILITY"
    )
    assert service.requested_media_type(message) == expected


def test_purchase_intent_triggers_ai_chat_lookup_and_projects_active_offer():
    sales = Sales(offering())
    service = ChatCommerceService(
        sales_service=sales, commerce_mode="COMPATIBILITY"
    )
    result = service.recommend(context(service, "Can I buy one image?"))
    assert result.lookup_attempted is True
    assert result.offering.title == "Private Beach Photo"
    assert sales.calls[0]["primary_sales_channel"] == "AI_CHAT"
    assert sales.calls[0]["requested_media_type"] == "SINGLE_IMAGE"
    assert sales.calls[0]["requested_themes"] == ("beach",)


def test_casual_media_mention_does_not_trigger_lookup():
    sales = Sales(offering())
    service = ChatCommerceService(
        sales_service=sales, commerce_mode="COMPATIBILITY"
    )
    result = service.recommend(context(service, "Nice photo today", purchase=False))
    assert result.lookup_attempted is False
    assert result.no_offering_reason == "SALE_NOT_AUTHORIZED_BY_DECISION_ENGINE"
    assert sales.calls == []


def test_story_is_structurally_rejected_without_lookup():
    sales = Sales(offering())
    service = ChatCommerceService(
        sales_service=sales, commerce_mode="COMPATIBILITY"
    )
    result = service.recommend(context(service, "Can I buy a story?"))
    assert result.lookup_attempted is False
    assert result.requested_media_type == "STORY"
    assert result.no_offering_reason == "UNSUPPORTED_OFFERING_TYPE"
    assert sales.calls == []


def test_no_eligible_offering_is_safe_and_does_not_invent_or_reuse_a_link():
    service = ChatCommerceService(
        sales_service=Sales(None), commerce_mode="COMPATIBILITY"
    )
    result = service.recommend(context(service, "What can I buy?"))
    assert result.offering is None
    assert result.no_offering_reason == "NO_ELIGIBLE_OFFERING"
    assert service.compose_reply("Let me see what suits you.", result) == (
        "Let me see what suits you."
    )


def test_configured_runtime_fails_closed_without_authoritative_selection():
    sales = Sales(offering())
    service = ChatCommerceService(
        sales_service=sales,
        commerce_mode="AUTHORITATIVE",
    )

    result = service.recommend(context(service, "What can I buy?"))

    assert result.offering is None
    assert result.lookup_attempted is False
    assert (
        result.no_offering_reason
        == "AUTHORITATIVE_COMMERCE_CONTEXT_REQUIRED"
    )
    assert result.selection_source == "NONE"
    assert result.legacy_recommendation_used is False
    assert sales.calls == []


def test_compatibility_mode_must_be_explicit():
    with pytest.raises(TypeError):
        ChatCommerceService(sales_service=Sales())


def test_compatibility_fallback_is_explicitly_diagnosed():
    sales = Sales(offering())
    service = ChatCommerceService(
        sales_service=sales, commerce_mode="COMPATIBILITY"
    )

    result = service.recommend(context(service, "What can I buy?"))

    assert result.selection_source == "COMPATIBILITY_RECOMMEND_BEST"
    assert result.legacy_recommendation_used is True
    assert len(sales.calls) == 1


def test_reply_context_uses_real_metadata_and_omits_internal_terminology():
    service = ChatCommerceService(
        sales_service=Sales(offering()), commerce_mode="COMPATIBILITY"
    )
    result = service.recommend(context(service, "Can I buy one image?"))
    reply = service.compose_reply("I found something for you.", result)
    assert reply == "I found something for you."
    assert "USD 9.99" not in reply
    assert "https://fanvue.com/fvml-active" not in reply
    for forbidden in (
        "Commercial Offering", "Commercial Publication",
        "Media Link UUID", "Provider resource", "Fulfillment",
    ):
        assert forbidden not in reply


def test_unmapped_reply_preserves_provider_copy_without_commerce_metadata_leakage():
    item = offering()
    item.title = "CONTROLLED SMOKE TEST — $3 SINGLE"
    item.description = "Operator-controlled test offering. Do not use in production."
    decision = SimpleNamespace(offering=item, product_context={})
    provider_copy = "I saved a private one I think you'll love. Ready to unlock?"

    reply = ChatCommerceService.compose_reply(
        provider_copy, decision, price_neutral=True,
    )

    assert reply == provider_copy
    assert "USD 9.99" not in reply
    assert item.delivery_url not in reply
    assert item.title not in reply
    assert item.description not in reply


def test_bundle_reply_keeps_price_and_destination_out_of_ava_prose():
    item = offering("BUNDLE")
    decision = SimpleNamespace(
        offering=item,
        product_context={"bundleOffer": {"paidMemberCount": 3}},
    )
    reply = ChatCommerceService.compose_reply("I picked this for you.", decision)
    assert reply == "I picked this for you."
    assert "USD 9.99" not in reply
    assert item.delivery_url not in reply


def test_session_reply_does_not_add_generic_progression_language():
    item = offering("SINGLE_IMAGE")
    decision = SimpleNamespace(
        offering=item, product_context={"sellingMode": "SESSION"},
    )
    reply = ChatCommerceService.compose_reply("Ready for the next part?", decision)
    assert reply == "Ready for the next part?"
    assert "USD 9.99" not in reply
    assert item.delivery_url not in reply
    assert "Your next unlock" not in reply
    assert "complete" not in reply.lower()


def test_adapter_has_no_direct_provider_or_publication_dependencies():
    source = open("app/services/chat_commerce_service.py", encoding="utf-8").read()
    assert "CommerceSalesService" in source
    assert "fanvue" not in source.lower()
    assert "commercial_publication" not in source.lower()
    assert "commercial_fulfillment" not in source.lower()

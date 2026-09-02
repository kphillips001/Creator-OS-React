from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.chat_commerce_service import ChatCommerceService
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


class Brain:
    def __init__(self, *, sell=True, provider="OPENAI", error=None):
        self.sell = sell
        self.provider = provider
        self.error = error
        self.calls = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append((user_id, message, chat_history))
        if self.error:
            raise self.error
        return {
            "response": "Ava's original reply.",
            "send_offer": self.sell,
            "blocked": False,
            "route": {"route": "sales" if self.sell else "chat", "reason": "fixture"},
            "intent": {"tier": "high" if self.sell else "low", "themes": ["lace"]},
            "selected_provider": self.provider,
            "provider": self.provider,
        }


class Sales:
    def __init__(self, offering):
        self.offering = offering
        self.calls = []

    def recommend_best(self, **values):
        self.calls.append(values)
        return self.offering


def sale(offering_type="SINGLE_IMAGE"):
    return SimpleNamespace(
        offering_id=uuid4(),
        title=f"{offering_type.title()} Release",
        description="A private release.",
        offering_type=offering_type,
        price_minor=999,
        currency="USD",
        primary_sales_channel="AI_CHAT",
        hero_asset_id=42,
        delivery_url="https://share.fanvue.com/ava/release",
        provider="FANVUE",
        provider_resource_id="media-link-1",
        published_at=datetime.now(timezone.utc),
    )


def gateway(brain, sales, *, developer=False):
    return ConversationGateway(
        brain,
        allowed_fanvue_hostnames=("fanvue.com", "share.fanvue.com"),
        creator_profile_id=7,
        chat_commerce_service=ChatCommerceService(
            sales_service=sales, commerce_mode="COMPATIBILITY"
        ),
    ), ConversationBrainContext(
        creator_profile_id=7,
        customer_identifier="7:9" if developer else "7:-123",
        conversation_identifier="shared-conversation",
        developer_mode=developer,
    )


def execute_direct(brain, sales, message, *, developer=False):
    brain_gateway, context = gateway(brain, sales, developer=developer)
    return brain_gateway.execute(ConversationGatewayInput(
        engine_user_id=context.customer_identifier,
        message_text=message,
        chat_history=[{"role": "user", "content": "Earlier"}],
        correlation_id="shared-correlation",
        brain_context=context,
    ))


def execute_telegram(brain, sales, message):
    brain_gateway, _ = gateway(brain, sales)
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=7),
        conversation_gateway=brain_gateway,
    )
    return adapter.execute(TelegramInboundPayload(
        telegram_user_id=123,
        telegram_chat_id=123,
        message_text=message,
        message_id=1,
        chat_history=[{"role": "user", "content": "Earlier"}],
        correlation_id="shared-correlation",
    ))


@pytest.mark.parametrize(
    ("offering_type", "message"),
    [
        ("SINGLE_IMAGE", "Send me one image"),
        ("PHOTOSET", "Show me a photoset"),
        ("VIDEO", "Send me a video"),
    ],
)
def test_developer_and_telegram_paths_have_commerce_reply_parity(
    offering_type, message,
):
    selected = sale(offering_type)
    developer_sales = Sales(selected)
    telegram_sales = Sales(selected)
    developer = execute_direct(Brain(), developer_sales, message, developer=True)
    telegram = execute_telegram(Brain(), telegram_sales, message)

    assert developer.response_text == telegram.response_text
    assert developer.response_text == ""
    assert developer.blocked is telegram.blocked is True
    assert developer.offer_authorized is telegram.offer_authorized is False
    assert developer.error_code == telegram.error_code == (
        "PAID_PRESENTATION_NOT_AN_OFFER"
    )
    assert selected.delivery_url not in developer.response_text
    for key in (
        "selected_provider", "commerce_lookup_attempted",
        "requested_media_type", "offering_id", "offering_type",
        "price_minor", "primary_sales_channel", "provider",
        "fulfillable", "recommendation_reason", "delivery_url",
    ):
        assert developer.diagnostic_metadata[key] == telegram.diagnostic_metadata[key]
    assert developer.diagnostic_metadata["paid_presentation_validated"] is False
    assert telegram.diagnostic_metadata["paid_presentation_validated"] is False
    assert developer.diagnostic_metadata["presentation_copy_failure_reason"] == (
        "PAID_PRESENTATION_NOT_AN_OFFER"
    )
    assert telegram.diagnostic_metadata["presentation_copy_failure_reason"] == (
        "PAID_PRESENTATION_NOT_AN_OFFER"
    )
    assert len(developer_sales.calls) == 1
    assert len(telegram_sales.calls) == 1


def test_casual_turn_does_not_query_sales_or_change_reply():
    sales = Sales(sale())
    output = execute_direct(Brain(sell=False), sales, "How are you?", developer=True)
    assert output.response_text == "Ava's original reply."
    assert output.diagnostic_metadata["commerce_lookup_attempted"] is False
    assert output.diagnostic_metadata["no_offering_reason"] == "SALE_NOT_AUTHORIZED_BY_DECISION_ENGINE"
    assert sales.calls == []


def test_no_offering_and_story_leave_original_reply_unchanged():
    no_offering = Sales(None)
    output = execute_direct(Brain(), no_offering, "Send me one image")
    assert output.response_text == "Ava's original reply."
    assert output.diagnostic_metadata["no_offering_reason"] == "NO_ELIGIBLE_OFFERING"
    assert len(no_offering.calls) == 1

    story_sales = Sales(sale())
    story = execute_direct(Brain(), story_sales, "Tell me a story")
    assert story.response_text == "Ava's original reply."
    assert story.diagnostic_metadata["no_offering_reason"] == "UNSUPPORTED_OFFERING_TYPE"
    assert story_sales.calls == []


@pytest.mark.parametrize("provider", ["OPENAI", "GROK"])
def test_gateway_preserves_decision_engine_provider_selection(provider):
    output = execute_direct(Brain(provider=provider), Sales(None), "Hello")
    assert output.diagnostic_metadata["selected_provider"] == provider


def test_provider_failure_is_normalized_without_commerce_query():
    sales = Sales(sale())
    output = execute_direct(
        Brain(error=RuntimeError("provider failed")), sales, "Hello"
    )
    assert output.error_code == "decision_engine_exception"
    assert output.blocked is True
    assert sales.calls == []


def test_live_runtime_source_does_not_select_legacy_telegram_commerce():
    source = open(
        "app/integrations/telegram/telethon_runtime.py", encoding="utf-8"
    ).read()
    assert "TelegramCommerceService" not in source
    assert "telegram_commerce_service=" not in source
    assert "ChatCommerceService(" in source
    assert "commerce_mode=ChatCommerceService.AUTHORITATIVE_MODE" in source

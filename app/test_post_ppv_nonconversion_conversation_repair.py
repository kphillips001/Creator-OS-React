from types import SimpleNamespace

import pytest

from app.models.telegram_inbound import TelegramInboundResult
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.ordinary_reply_delivery_quality_gate import (
    OrdinaryReplyDeliveryQualityGate,
)


def result(text, diagnostics=None):
    return TelegramInboundResult(
        correlation_id="c", telegram_chat_id=2, telegram_user_id=2,
        message_id=3, engine_user_id="e", response_text=text,
        offer_authorized=False, offer_link=None, blocked=False,
        error_code=None, delivery_type="MESSAGE_TEXT",
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": text},
        diagnostic_metadata=dict(diagnostics or {}),
    )


@pytest.mark.parametrize("source", ["provider", "repair", "deterministic"])
def test_policy_narration_is_blocked_at_final_gate_for_every_candidate_source(source):
    candidate = result(
        "Let's keep it nonsexual and talk about your day.",
        {"candidateSource": source},
    )
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(candidate)
    assert not decision.allowed
    assert "UNNECESSARY_POLICY_NARRATION" in decision.reasons


def test_independently_required_safety_boundary_is_not_misclassified():
    candidate = result(
        "Let's keep things appropriate.",
        {"independentSafetyBoundaryRequired": True},
    )
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(candidate)
    assert decision.allowed
    assert "UNNECESSARY_POLICY_NARRATION" not in decision.reasons


def test_authorized_premium_value_boundary_allows_value_not_nonsexual_policy():
    diagnostics = {"post_nudge_conversation_policy": {
        "responsePurpose": "PREMIUM_VALUE_BOUNDARY",
        "premiumValueBoundaryAuthorized": True,
    }}
    value = OrdinaryReplyDeliveryQualityGate().evaluate(result(
        "I save that more intimate side of me for supporters 😉",
        diagnostics,
    ))
    moderation = OrdinaryReplyDeliveryQualityGate().evaluate(result(
        "Let's keep it nonsexual.", diagnostics,
    ))
    assert value.allowed
    assert not moderation.allowed
    assert "UNNECESSARY_POLICY_NARRATION" in moderation.reasons


def test_warm_nonexplicit_redirect_passes_without_granting_content():
    text = "You really know how to turn up the heat 😏 how's your day going?"
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(result(text))
    assert decision.allowed


def test_presentation_specific_guidance_is_carried_to_generation():
    operation = SimpleNamespace(
        delivery_payload={"postNudgeConversationPolicy": {
            "active": True,
            "responsePurpose": "POST_PPV_RELATIONSHIP_CONTINUATION",
            "nonconversionScope": "PRESENTATION_SPECIFIC",
            "providerAllowed": True,
            "providerSemanticGuidance": {"policyNarrationAllowed": False},
        }},
        operation_id="00000000-0000-0000-0000-000000000001",
        inbound_sender_telegram_user_id=2,
        telegram_chat_id=2,
        inbound_message_text="you're gorgeous",
        inbound_telegram_message_id=3,
        inbound_received_at=None,
        conversation_burst_id=None,
    )
    payload = OrdinaryChatReplyService(repository=SimpleNamespace()).retry_payload(operation)
    policy = payload.quality_correction_context["postPpvNonconversionConversation"]
    assert policy["nonconversionScope"] == "PRESENTATION_SPECIFIC"
    assert policy["providerAllowed"] is True


def test_benign_current_turn_carries_no_boundary_response():
    operation = SimpleNamespace(
        delivery_payload={"postNudgeConversationPolicy": {
            "active": True,
            "responsePurpose": "CASUAL_BACKOFF_CONVERSATION",
            "nonconversionScope": "PRESENTATION_SPECIFIC",
            "providerAllowed": True,
        }},
        operation_id="00000000-0000-0000-0000-000000000002",
        inbound_sender_telegram_user_id=2, telegram_chat_id=2,
        inbound_message_text="Hi Ava how are you doing today",
        inbound_telegram_message_id=4, inbound_received_at=None,
        conversation_burst_id=None,
    )
    service = OrdinaryChatReplyService(repository=SimpleNamespace())
    payload = service.retry_payload(operation)
    assert payload.quality_correction_context[
        "postPpvNonconversionConversation"
    ]["responsePurpose"] == "CASUAL_BACKOFF_CONVERSATION"
    assert service.post_nudge_policy_result(operation, payload) is None

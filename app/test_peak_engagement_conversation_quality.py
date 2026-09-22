from types import SimpleNamespace

from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.peak_engagement_conversation_service import (
    PeakEngagementConversationDirective,
)


ELIGIBLE = {
    "policy": "PEAK_ENGAGEMENT_V1",
    "active": True,
    "investmentAdjustment": "ORDINARY_BALANCED_TO_ENGAGED",
    "suppressedBy": None,
    "continuationGrace": False,
}


def project(**overrides):
    values = dict(decision=ELIGIBLE, ordinary_generation=True,
                  protected_commercial_semantics=False,
                  effort_mode="balanced", sleep_state="AWAKE")
    values.update(overrides)
    return PeakEngagementConversationDirective.from_phase1(**values)


def test_eligible_phase1_decision_supplies_subtle_generation_guidance():
    directive = project()
    assert directive.active is True
    assert directive.diagnostics()["suppliedToGeneration"] is True
    prompt = directive.prompt_block()
    assert "Continue the topic the customer just supplied" in prompt
    assert "A question is optional" in prompt
    assert "at most one" in prompt
    assert "more sales-oriented" in prompt
    assert "sentence can fully satisfy it" in prompt
    assert "non-question" in prompt


def test_outside_peak_consumes_phase1_suppression_without_recalculation():
    decision = {**ELIGIBLE, "active": False, "investmentAdjustment": None,
                "suppressedBy": "OUTSIDE_PEAK_WINDOW",
                "continuationGrace": True}
    directive = project(decision=decision)
    assert directive.active is False
    assert directive.prompt_block() == ""
    assert directive.diagnostics()["phase1SuppressedBy"] == "OUTSIDE_PEAK_WINDOW"


def test_midnight_continuation_is_accepted_only_from_phase1_decision():
    directive = project(decision={**ELIGIBLE, "continuationGrace": True})
    assert directive.active is True
    assert directive.diagnostics()["phase1DecisionReceived"] is True


def test_commercial_reduced_investment_and_sleep_supersede_peak():
    cases = (
        ({"protected_commercial_semantics": True}, "CURRENT_COMMERCIAL_AUTHORITY"),
        ({"effort_mode": "minimal"}, "REDUCED_INVESTMENT"),
        ({"effort_mode": "compressed"}, "REDUCED_INVESTMENT"),
        ({"sleep_state": "SLEEP_PENDING_SIGNOFF"},
         "CONVERSATIONAL_AVAILABILITY_AUTHORITY"),
    )
    for overrides, reason in cases:
        directive = project(**overrides)
        assert directive.active is False
        assert directive.diagnostics()["supersededBy"] == reason
        assert directive.prompt_block() == ""


def test_buyer_or_control_suppression_from_phase1_is_never_reactivated():
    for reason in ("BUYER_AUTHORITY", "HUMAN_TAKEOVER", "RELATIONSHIP_IGNORED",
                   "BACKOFF", "HOSTILITY_RESTRAINT", "SEND_UNCERTAIN"):
        directive = project(decision={**ELIGIBLE,
            "investmentAdjustment": None, "suppressedBy": reason})
        assert directive.active is False
        assert directive.diagnostics()["phase1SuppressedBy"] == reason


def test_retry_payload_carries_exact_durable_phase1_decision():
    operation = SimpleNamespace(
        operation_id="operation-1", inbound_sender_telegram_user_id=1,
        telegram_chat_id=2, inbound_message_text="hello", inbound_telegram_message_id=3,
        inbound_received_at=None, conversation_burst_id=None,
        delivery_payload={"availability": {"peakEngagement": ELIGIBLE}},
    )
    payload = OrdinaryChatReplyService.__new__(OrdinaryChatReplyService).retry_payload(
        operation
    )
    assert payload.quality_correction_context["peakEngagement"] == ELIGIBLE


def test_projection_is_side_effect_free_and_does_not_mutate_state():
    decision = {**ELIGIBLE}
    before = dict(decision)
    first = project(decision=decision)
    second = project(decision=decision)
    assert decision == before
    assert first == second

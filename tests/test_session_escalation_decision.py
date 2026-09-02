import pytest

from app.services.session_escalation_decision_service import (
    SessionEscalationDecisionService,
)


def project(message, **changes):
    values = {
        "active_buying_window": True,
        "purchase_count": 2,
        "recent_purchase_count": 2,
        "current_message": message,
        "explicit_continuation_count": 2,
        "session_inventory_available": True,
        "ordinary_inventory_available": True,
    }
    values.update(changes)
    return SessionEscalationDecisionService.project(**values)


def test_one_purchase_send_another_remains_discrete():
    value = project("send me another one", purchase_count=1)
    assert value["sessionCandidate"] is False
    assert value["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"
    assert value["sessionProposalPending"] is False


def test_two_purchases_discrete_language_remains_discrete_with_session_inventory():
    value = project("got another one?")
    assert value["sessionCandidate"] is False
    assert value["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"


@pytest.mark.parametrize("message", (
    "don't stop, I want to keep this going with you",
    "take me through the rest",
    "keep showing me more",
))
def test_two_purchases_ongoing_experience_authorizes_proposal(message):
    value = project(message)
    assert value["sessionCandidate"] is True
    assert value["sessionProposalAuthorized"] is True
    assert value["sessionEscalationDecision"] == "PROPOSE_SESSION"
    assert value["sessionStarted"] is False


def test_session_unavailable_falls_back_to_owned_safe_discrete_inventory():
    value = project("take me through the rest", session_inventory_available=False)
    assert value["sessionCandidate"] is True
    assert value["sessionProposalAuthorized"] is False
    assert value["sessionUnavailableFallback"] is True
    assert value["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"


def test_session_declined_but_discrete_more_requested_keeps_window():
    value = project(
        "I'd rather just get another one instead", proposal_pending=True,
    )
    assert value["sessionProposalCustomerReaction"] == (
        "DECLINE_SESSION_BUT_WANTS_MORE"
    )
    assert value["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"
    assert value["sessionProposalPending"] is False


def test_session_acceptance_reaches_entry_boundary_without_starting():
    value = project("yeah I'm in", proposal_pending=True)
    assert value["sessionProposalCustomerReaction"] == "ACCEPT_OR_LEAN_IN"
    assert value["sessionEscalationDecision"] == "SESSION_ACCEPTED"
    assert value["sessionStartAuthorityEligible"] is True
    assert value["sessionProposalPending"] is False
    assert value["sessionStarted"] is False


def test_acceptance_wording_without_visible_proposal_cannot_accept_session():
    value = project("yeah I'm in, let's keep it going")
    assert value["sessionProposalCustomerReaction"] == "NONE"
    assert value["sessionEscalationDecision"] == "PROPOSE_SESSION"
    assert value["sessionStartAuthorityEligible"] is False


def test_session_decline_and_stop_closes_pending_proposal():
    value = project("no more, stop", proposal_pending=True)
    assert value["sessionProposalCustomerReaction"] == "DECLINE_AND_STOP"
    assert value["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"
    assert value["sessionProposalPending"] is False


def test_pending_proposal_does_not_repeat_or_create_competing_ppv():
    value = project("tell me more about that", proposal_pending=True)
    assert value["sessionProposalPending"] is True
    assert value["sessionProposalAuthorized"] is False
    assert value["continueDiscretePpvsAuthorized"] is False
    assert value["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"


def test_sexuality_or_value_without_explicit_continuation_cannot_escalate():
    value = project("that was so hot", purchase_count=8)
    assert value["sessionCandidate"] is False
    assert value["sessionProposalAuthorized"] is False
    assert value["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"


def test_rejection_and_active_session_have_precedence():
    rejected = project("stop", rejection_or_back_off=True)
    assert rejected["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"
    active = project("keep going", active_session=True)
    assert active["activeSessionPrecedence"] is True
    assert active["sessionProposalAuthorized"] is False


def test_deferred_ongoing_continuation_survives_acknowledgement():
    value = project(
        "", current_message="", deferred_continuation={
            "state": "READY", "continuationType": "ONGOING_EXPERIENCE",
        },
    )
    assert value["currentContinuationIntent"] == "ONGOING_EXPERIENCE"
    assert value["sessionEscalationDecision"] == "PROPOSE_SESSION"

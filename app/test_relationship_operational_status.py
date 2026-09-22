from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.relationships_service import RelationshipsService


NOW = datetime(2026, 9, 13, 20, 0, tzinfo=timezone.utc)


def inbox(**values):
    result = {
        "telegram_chat_id": 42,
        "last_inbound_message_id": 100,
        "last_customer_inbound_at": NOW - timedelta(minutes=10),
        "last_visible_outbound_at": NOW - timedelta(minutes=20),
        "database_now": NOW,
        "control_mode": "AVA_AUTO",
        "operation_id": uuid4(),
        "operation_state": "RETRYABLE",
        "operation_last_error": "availability_deferred",
        "next_retry_at": NOW + timedelta(minutes=5),
        "has_response_payload": False,
        "pending_reply_preview": None,
        "generation_attempt_count": 0,
        "max_generation_attempts": 5,
        "send_attempt_count": 0,
        "max_send_attempts": 5,
        "claim_owner": None,
        "lease_expires_at": None,
        "generated_at": None,
        "sending_at": None,
        "sent_confirmed_at": None,
        "outbound_telegram_message_id": None,
        "operation_updated_at": NOW - timedelta(minutes=5),
        "acknowledged_occurrence_id": None,
        "acknowledged_at": None,
        "acknowledged_by": None,
        "has_active_response_operation": False,
        "has_unresolved_meaningful_obligation": False,
        "operation_has_meaningful_obligation": False,
    }
    result.update(values)
    return result


def status(**values):
    return RelationshipsService._operational_projection(inbox(**values))


def test_future_availability_is_one_server_authoritative_schedule():
    item = status()
    assert item["operationalStatus"] == "REPLY_SCHEDULED"
    assert item["nextAutomaticAttemptAt"] == NOW + timedelta(minutes=5)
    assert item["pendingReplyPreview"] is None


def test_two_minute_overdue_grace_is_not_premature():
    assert status(next_retry_at=NOW - timedelta(seconds=119))[
        "operationalStatus"] == "REPLY_SCHEDULED"
    overdue = status(next_retry_at=NOW - timedelta(minutes=3))
    assert overdue["operationalStatus"] == "OVERDUE"
    assert overdue["overdueSince"] == NOW - timedelta(minutes=1)


def test_generated_send_retry_is_scheduled_and_then_overdue():
    future = status(has_response_payload=True, send_attempt_count=1,
                    pending_reply_preview="the persisted Ava reply",
                    operation_last_error="definitive provider failure")
    assert future["operationalStatus"] == "REPLY_READY"
    assert future["operationalStatusReason"] == "Delivery retry scheduled."
    assert future["pendingReplyPreview"] == "the persisted Ava reply"
    overdue = status(has_response_payload=True, send_attempt_count=1,
                     pending_reply_preview="the persisted Ava reply",
                     operation_last_error="definitive provider failure",
                     next_retry_at=NOW - timedelta(minutes=3))
    assert overdue["operationalStatus"] == "OVERDUE"
    assert overdue["pendingReplyPreview"] is None


def test_payload_without_authoritative_customer_visible_text_is_not_ready():
    item = status(has_response_payload=True, send_attempt_count=1,
                  pending_reply_preview="",
                  operation_last_error="definitive provider failure")
    assert item["operationalStatus"] == "SYSTEM_INCIDENT"
    assert item["pendingReplyPreview"] is None


@pytest.mark.parametrize("state", ["SENT_CONFIRMED", "SUPPRESSED", "TERMINAL_FAILED"])
def test_terminal_or_invalidated_operation_never_projects_pending_preview(state):
    item = status(
        operation_state=state,
        has_response_payload=True,
        pending_reply_preview="stale response from an old operation",
        next_retry_at=None,
        operation_last_error=("intentional_suppression:safety"
                              if state == "SUPPRESSED" else None),
        last_visible_outbound_at=(NOW if state == "SENT_CONFIRMED" else
                                  NOW - timedelta(minutes=20)),
    )
    assert item["operationalStatus"] != "REPLY_READY"
    assert item["pendingReplyPreview"] is None


def test_generated_retry_at_attempt_limit_is_not_scheduled():
    item = status(has_response_payload=True, send_attempt_count=5,
                  max_send_attempts=5,
                  operation_last_error="definitive provider failure")
    assert item["operationalStatus"] == "SYSTEM_INCIDENT"


def test_valid_generation_claim_and_confirmed_outbound_are_not_overdue():
    generating = status(
        operation_state="GENERATING", operation_last_error=None,
        next_retry_at=None, claim_owner="worker",
        lease_expires_at=NOW + timedelta(minutes=2),
    )
    assert generating["operationalStatus"] == "RECOVERY_PENDING"
    assert generating["hasActiveClaim"] is True
    assert status(
        operation_state="SENT_CONFIRMED", operation_last_error=None,
        next_retry_at=None, last_visible_outbound_at=NOW,
    )["operationalStatus"] == "NONE"


def test_stranded_generated_requires_attention_after_pacing_grace():
    item = status(operation_state="GENERATED", has_response_payload=True,
                  operation_last_error=None, next_retry_at=None)
    assert item["operationalStatus"] == "SYSTEM_INCIDENT"
    assert item["operationalStatusReason"] == (
        "Generated response was not delivered and requires recovery.")


def test_fresh_generated_inside_pacing_window_is_not_stranded():
    item = status(operation_state="GENERATED", has_response_payload=True,
                  operation_last_error=None, next_retry_at=None,
                  operation_updated_at=NOW - timedelta(seconds=10))
    assert item["operationalStatus"] == "RECOVERY_PENDING"


@pytest.mark.parametrize("values", [
    {"outbound_telegram_message_id": 9001},
    {"sent_confirmed_at": NOW - timedelta(seconds=2)},
    {"sending_at": NOW - timedelta(seconds=2)},
    {"claim_owner": "sender", "lease_expires_at": NOW + timedelta(minutes=1)},
])
def test_generated_with_delivery_boundary_is_not_stranded(values):
    assert status(operation_state="GENERATED", has_response_payload=True,
                  operation_last_error=None, next_retry_at=None,
                  **values)["operationalStatus"] == ("RECOVERY_PENDING" if values.get("claim_owner") else "DELIVERY_UNCERTAIN")


def test_corrective_retry_is_scheduled_not_attention():
    item = status(
        operation_last_error="quality_corrective_retry_scheduled",
        generation_attempt_count=1, max_generation_attempts=2,
    )
    assert item["operationalStatus"] == "REPLY_SCHEDULED"


def test_decision_engine_retry_projects_scheduled_then_immediately_overdue():
    future = status(
        operation_last_error="DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.",
        next_retry_at=NOW + timedelta(seconds=30), generation_attempt_count=1,
    )
    assert future["operationalStatus"] == "REPLY_SCHEDULED"
    assert future["operationalStatusReason"] == "Generation retry scheduled."
    due = status(
        operation_last_error="DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.",
        next_retry_at=NOW, generation_attempt_count=1,
    )
    assert due["operationalStatus"] == "OVERDUE"
    assert due["overdueSince"] == NOW


def test_decision_engine_retry_without_action_or_with_exhausted_budget_needs_attention():
    missing = status(
        operation_last_error="DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.",
        next_retry_at=None, generation_attempt_count=1,
    )
    assert missing["operationalStatus"] == "SYSTEM_INCIDENT"
    exhausted = status(
        operation_last_error="DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.",
        generation_attempt_count=5, max_generation_attempts=5,
    )
    assert exhausted["operationalStatus"] == "SYSTEM_INCIDENT"
    assert exhausted["systemIncidentReason"].startswith("DECISION_ENGINE_EXCEPTION:")


def test_non_meaningful_terminal_history_is_not_actionable_attention():
    item = status(
        operation_state="TERMINAL_FAILED",
        operation_last_error="EMPTY_GENERATION: Automatic reply could not be completed.",
        generation_attempt_count=5,
        max_generation_attempts=5,
        has_unresolved_meaningful_obligation=False,
        delivery_payload={"attentionInvestment": {"meaningfulObligation": False}},
    )
    assert item["operationalStatus"] == "SYSTEM_INCIDENT"


def test_unknown_retry_reason_never_silently_projects_none():
    item = status(operation_last_error="ARBITRARY_INTERNAL_FAILURE")
    assert item["operationalStatus"] == "SYSTEM_INCIDENT"


@pytest.mark.parametrize("state,error", [
    ("TERMINAL_FAILED", "provider failed"),
    ("SEND_UNCERTAIN", "acceptance unknown"),
    ("SUPPRESSED", "quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED"),
    ("SUPPRESSED", "quality_blocked_before_delivery:TURN_OBLIGATIONS_UNSATISFIED"),
])
def test_terminal_required_reply_conditions_need_attention(state, error):
    item = status(operation_state=state, operation_last_error=error,
                  next_retry_at=None,inbound_message_text="Hey")
    assert item["operationalStatus"] == {"TERMINAL_FAILED":"SYSTEM_INCIDENT","SEND_UNCERTAIN":"DELIVERY_UNCERTAIN","SUPPRESSED":"NEEDS_ATTENTION"}[state]
    assert len(item["attentionOccurrenceId"]) == 64


@pytest.mark.parametrize("error", [
    "availability_burst_coalesced", "NO_RESPONSE_REQUIRED",
    "intentional_suppression:safety", "RELATIONSHIP_HUMAN_OPERATOR_ACTIVE",
])
def test_intentional_or_coalesced_suppression_is_not_attention(error):
    assert status(operation_state="SUPPRESSED", operation_last_error=error,
                  next_retry_at=None)["operationalStatus"] == "NONE"


def test_terminal_dead_end_with_meaningful_obligation_needs_attention():
    item = status(
        operation_state="SUPPRESSED",
        operation_last_error="availability_burst_coalesced",
        next_retry_at=None,
        has_active_response_operation=False,
        has_unresolved_meaningful_obligation=True,
        operation_has_meaningful_obligation=True,
    )
    assert item["operationalStatus"] == "NEEDS_ATTENTION"
    assert item["operationalStatusReason"] == (
        "A response obligation survives and no automatic correction remains actionable."
    )


def test_closing_acknowledgement_terminalized_without_obligation_is_not_attention():
    item = status(
        operation_state="SUPPRESSED",
        operation_last_error="IMMUTABLE_DELIVERY_PAYLOAD_TEXT_MISMATCH",
        next_retry_at=None,
        has_active_response_operation=False,
        has_unresolved_meaningful_obligation=True,
        operation_has_meaningful_obligation=False,
    )
    assert item["operationalStatus"] == "NONE"
    assert item["attentionOccurrenceId"] is None


def test_terminal_member_is_not_dead_end_when_survivor_is_active():
    item = status(
        operation_state="SUPPRESSED",
        operation_last_error="availability_burst_coalesced",
        next_retry_at=None,
        has_active_response_operation=True,
        has_unresolved_meaningful_obligation=True,
    )
    assert item["operationalStatus"] == "NONE"


def test_manual_mode_has_highest_precedence():
    item = status(control_mode="HUMAN_OPERATOR", operation_state="TERMINAL_FAILED",
                  next_retry_at=None)
    assert item["operationalStatus"] == "MANUAL_MODE"


def test_acknowledgement_hides_only_matching_occurrence_and_new_inbound_reappears():
    source = inbox(operation_state="TERMINAL_FAILED", operation_last_error="failed",
                   next_retry_at=None)
    first = RelationshipsService._operational_projection(source)
    source["acknowledged_occurrence_id"] = first["attentionOccurrenceId"]
    assert RelationshipsService._operational_projection(source)[
        "operationalStatus"] == "NONE"
    source["last_inbound_message_id"] += 1
    assert RelationshipsService._operational_projection(source)[
        "operationalStatus"] == "SYSTEM_INCIDENT"


class AckRepository:
    def __init__(self, source):
        self.source = source
        self.calls = []

    def inbox_state(self, **_):
        return {7: dict(self.source)}

    def acknowledge_attention(self, **values):
        self.calls.append(values)
        return {"acknowledged_at": NOW, "acknowledged_by": values["acknowledged_by"]}


def test_acknowledge_is_scoped_idempotent_projection_without_chat_mutation():
    source = inbox(telegram_chat_id=77, operation_state="TERMINAL_FAILED",
                   operation_last_error="failed", next_retry_at=None)
    repository = AckRepository(source)
    service = RelationshipsService(
        people_repository=SimpleNamespace(), messages_repository=repository,
    )
    service._person = lambda *_: {"telegramUserId": 7, "lastChatAt": NOW}
    occurrence = service._operational_projection(source)["attentionOccurrenceId"]
    result = service.acknowledge_attention(
        creator_profile_id=1, fanvue_account_id=2, telegram_user_id=7,
        occurrence_id=occurrence,
    )
    assert result["operationalStatus"] == "NONE"
    assert repository.calls[0]["telegram_chat_id"] == 77
    assert repository.calls[0]["triggering_inbound_message_id"] == 100
    assert not hasattr(repository, "ordinary_operation_update")

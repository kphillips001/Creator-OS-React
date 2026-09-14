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
        "generation_attempt_count": 0,
        "max_generation_attempts": 5,
        "send_attempt_count": 0,
        "max_send_attempts": 5,
        "claim_owner": None,
        "lease_expires_at": None,
        "acknowledged_occurrence_id": None,
        "acknowledged_at": None,
        "acknowledged_by": None,
    }
    result.update(values)
    return result


def status(**values):
    return RelationshipsService._operational_projection(inbox(**values))


def test_future_availability_is_one_server_authoritative_schedule():
    item = status()
    assert item["operationalStatus"] == "REPLY_SCHEDULED"
    assert item["nextAutomaticAttemptAt"] == NOW + timedelta(minutes=5)


def test_two_minute_overdue_grace_is_not_premature():
    assert status(next_retry_at=NOW - timedelta(seconds=119))[
        "operationalStatus"] == "REPLY_SCHEDULED"
    overdue = status(next_retry_at=NOW - timedelta(minutes=3))
    assert overdue["operationalStatus"] == "OVERDUE"
    assert overdue["overdueSince"] == NOW - timedelta(minutes=1)


def test_generated_send_retry_is_scheduled_and_then_overdue():
    future = status(has_response_payload=True, send_attempt_count=1,
                    operation_last_error="definitive provider failure")
    assert future["operationalStatus"] == "REPLY_SCHEDULED"
    assert future["operationalStatusReason"] == "Delivery retry scheduled."
    overdue = status(has_response_payload=True, send_attempt_count=1,
                     operation_last_error="definitive provider failure",
                     next_retry_at=NOW - timedelta(minutes=3))
    assert overdue["operationalStatus"] == "OVERDUE"


def test_generated_retry_at_attempt_limit_is_not_scheduled():
    item = status(has_response_payload=True, send_attempt_count=5,
                  max_send_attempts=5,
                  operation_last_error="definitive provider failure")
    assert item["operationalStatus"] == "NONE"


def test_valid_generation_claim_and_confirmed_outbound_are_not_overdue():
    generating = status(
        operation_state="GENERATING", operation_last_error=None,
        next_retry_at=None, claim_owner="worker",
        lease_expires_at=NOW + timedelta(minutes=2),
    )
    assert generating["operationalStatus"] == "NONE"
    assert generating["hasActiveClaim"] is True
    assert status(
        operation_state="SENT_CONFIRMED", operation_last_error=None,
        next_retry_at=None, last_visible_outbound_at=NOW,
    )["operationalStatus"] == "NONE"


def test_corrective_retry_is_scheduled_not_attention():
    item = status(
        operation_last_error="quality_corrective_retry_scheduled",
        generation_attempt_count=1, max_generation_attempts=2,
    )
    assert item["operationalStatus"] == "REPLY_SCHEDULED"


@pytest.mark.parametrize("state,error", [
    ("TERMINAL_FAILED", "provider failed"),
    ("SEND_UNCERTAIN", "acceptance unknown"),
    ("SUPPRESSED", "quality_corrective_retry_exhausted:CUSTOMER_QUESTION_UNANSWERED"),
    ("SUPPRESSED", "quality_blocked_before_delivery:TURN_OBLIGATIONS_UNSATISFIED"),
])
def test_terminal_required_reply_conditions_need_attention(state, error):
    item = status(operation_state=state, operation_last_error=error,
                  next_retry_at=None)
    assert item["operationalStatus"] == "NEEDS_ATTENTION"
    assert len(item["attentionOccurrenceId"]) == 64


@pytest.mark.parametrize("error", [
    "availability_burst_coalesced", "NO_RESPONSE_REQUIRED",
    "intentional_suppression:safety", "RELATIONSHIP_HUMAN_OPERATOR_ACTIVE",
])
def test_intentional_or_coalesced_suppression_is_not_attention(error):
    assert status(operation_state="SUPPRESSED", operation_last_error=error,
                  next_retry_at=None)["operationalStatus"] == "NONE"


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
        "operationalStatus"] == "NEEDS_ATTENTION"


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

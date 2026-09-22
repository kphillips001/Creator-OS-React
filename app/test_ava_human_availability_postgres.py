"""Isolated PostgreSQL certification for Session 1 availability delivery."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, row_factory=dict_row) as connection:
        yield connection


@pytest.fixture
def durable():
    scope = f"SESSION1_TEST_{uuid4()}"
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    service = OrdinaryChatReplyService(repository=repository, worker_id=f"worker-{uuid4()}")
    service.ACCOUNT_SCOPE = scope
    yield service, repository, scope
    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s", (scope,))


def inbound(chat, message_id, text, now):
    return TelegramInboundPayload(
        telegram_user_id=chat, telegram_chat_id=chat, message_text=text,
        message_id=message_id, received_at=now,
    )


def decision(available_at, category="NORMAL"):
    return SimpleNamespace(
        available_at=available_at, category=category,
        diagnostics=lambda: {"category": category, "availableAt": available_at.isoformat()},
    )


def generated_result(payload, text="bounded reply"):
    return TelegramInboundResult(
        correlation_id=f"result:{payload.telegram_chat_id}:{payload.message_id}",
        telegram_chat_id=payload.telegram_chat_id, telegram_user_id=payload.telegram_user_id,
        message_id=payload.message_id, engine_user_id="synthetic", response_text=text,
        offer_authorized=False, offer_link=None, blocked=False, error_code=None,
        delivery_payload={}, diagnostic_metadata={},
    )


def test_anthony_burst_preserves_separate_evidence_and_direct_question_authority(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    messages = [(100, "Haha 😄"), (101, "Can you remember me from before?"), (102, "Always babe 😘")]
    created = []
    for message_id, text in messages:
        operation, is_new = service.begin(inbound(810001, message_id, text, now))
        assert is_new
        created.append(service.defer_for_availability(operation, decision(now - timedelta(seconds=1))))

    payloads = service.due_availability_payloads(now=now + timedelta(seconds=21))
    assert len(payloads) == 1
    assert payloads[0].message_id == 101
    assert payloads[0].message_text == "Can you remember me from before?"
    assert [item["content"] for item in payloads[0].chat_history] == ["Haha 😄", "Always babe 😘"]
    rows = [repository.get(item.operation_id) for item in created]
    assert [row.inbound_message_text for row in rows] == [item[1] for item in messages]
    assert sum(row.state.value == "SUPPRESSED" for row in rows) == 2
    assert all(row.last_error == "availability_burst_coalesced" for row in (rows[0], rows[2]))
    claimed = service.claim_generation(rows[1])
    assert claimed.generation_attempt_count == 1
    rows = [repository.get(item.operation_id) for item in created]
    assert sum(row.generation_attempt_count for row in rows) == 1


def test_final_clearance_twenty_message_burst_compresses_before_generation(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    texts = [
        "Haha", "😘", "❤️", "Always babe", "🔥", "ok", "yeah", "lol",
        "you've gone quiet", "hello?", "😘🔥", "nice", "haha again", "babe",
        "Can you remember me from before?", "❤️❤️", "I finally finished my project",
        "cool", "😘", "always",
    ]
    operations = []
    available_at = now + timedelta(minutes=5, seconds=10)
    for message_id, text in enumerate(texts, start=2000):
        operation, created = service.begin(inbound(812000, message_id, text, now))
        assert created is True
        operations.append(service.defer_for_availability(
            operation, decision(available_at, "BUSY")))

    # Preparation eligibility is computed from database NOW() for every
    # durable defer. Creating twenty rows can take longer than the historical
    # fixed three-second margin, so derive the canonical quiet-window boundary
    # from the persisted newest member rather than Python fixture wall time.
    persisted = [repository.get(item.operation_id) for item in operations]
    expected_due_time = max(item.next_retry_at for item in persisted)
    assert service.due_availability_payloads(
        now=expected_due_time - timedelta(microseconds=1)) == []
    due = service.due_availability_payloads(
        now=expected_due_time + timedelta(microseconds=1))
    assert len(due) == 1
    assert due[0].message_text == "Can you remember me from before?"
    assert len(due[0].chat_history) == 19

    rows = [repository.get(item.operation_id) for item in operations]
    assert len(rows) == 20
    assert sum(row.state.value == "SUPPRESSED" for row in rows) == 19
    assert sum(row.last_error == "NO_RESPONSE_REQUIRED" for row in rows) == 0
    assert sum(row.generation_attempt_count for row in rows) == 0

    authority = next(row for row in rows if row.state.value == "PENDING_GENERATION")
    claimed = service.claim_generation(authority)
    assert claimed.generation_attempt_count == 1
    generated = service.generated(
        claimed, generated_result(due[0], "Yes—I remember what you've shared."))
    assert generated.state.value == "RETRYABLE"
    assert generated.next_retry_at == available_at
    assert service.claim_send(generated) is None
    final_rows = [repository.get(item.operation_id) for item in operations]
    assert sum(row.generation_attempt_count for row in final_rows) == 1
    assert sum(row.send_attempt_count for row in final_rows) == 0


def test_commercial_referent_survives_trailing_emoji_without_purchase_intent(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    messages = [(200, "Love your content"), (201, "Do I get a special photo babe 😘"), (202, "😘")]
    for message_id, text in messages:
        operation, _ = service.begin(inbound(810002, message_id, text, now))
        service.defer_for_availability(operation, decision(now + timedelta(seconds=10)))
    payload = service.due_availability_payloads(now=now + timedelta(seconds=11))[0]
    assert payload.message_id == 201
    assert "special photo" in payload.message_text
    with connection_factory() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM purchase_intents WHERE correlation_id::text LIKE %s",
            (f"%{810002}%",),
        ).fetchone()["count"]
    assert count == 0


def test_restart_boundaries_remain_exactly_once_and_fail_closed(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    first, _ = service.begin(inbound(810003, 300, "Question?", now))
    deferred = service.defer_for_availability(first, decision(now - timedelta(seconds=1), "DIRECT_QUESTION"))
    restarted = OrdinaryChatReplyService(repository=repository, worker_id="restart-a")
    restarted.ACCOUNT_SCOPE = scope
    assert repository.get(deferred.operation_id).next_retry_at is not None
    due = restarted.due_availability_payloads(now=now + timedelta(seconds=10))[0]
    authoritative = repository.get(deferred.operation_id)
    claimed = restarted.claim_generation(authoritative)
    stored = restarted.generated(claimed, generated_result(due))
    assert stored.state.value == "GENERATED"
    restarted_b = OrdinaryChatReplyService(repository=repository, worker_id="restart-b")
    restarted_b.ACCOUNT_SCOPE = scope
    sending = restarted_b.claim_send(repository.get(stored.operation_id))
    assert sending.state.value == "SENDING"
    assert restarted_b.claim_send(sending) is None
    recovered = restarted_b.recover_startup()
    recovered_current = [item for item in recovered if item.operation_id == stored.operation_id]
    assert [item.state.value for item in recovered_current] == ["SEND_UNCERTAIN"]
    assert restarted_b.claim_send(repository.get(stored.operation_id)) is None

    confirmed_op, _ = service.begin(inbound(810003, 301, "Another question?", now))
    claimed_generation = service.claim_generation(confirmed_op)
    generated = service.generated(claimed_generation, generated_result(inbound(810003, 301, "Another question?", now)))
    sending = service.claim_send(generated)
    confirmed = service.confirmed(sending, 99001)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert service.claim_send(confirmed) is None


def test_two_chats_have_independent_due_authority(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    slow, _ = service.begin(inbound(810004, 400, "slow chat", now))
    fast, _ = service.begin(inbound(810005, 500, "fast question?", now))
    service.defer_for_availability(slow, decision(now + timedelta(minutes=10)))
    service.defer_for_availability(fast, decision(now + timedelta(minutes=6)))
    due = service.due_availability_payloads(now=now + timedelta(minutes=1, seconds=1))
    assert [(item.telegram_chat_id, item.message_id) for item in due] == [(810005, 500)]
    assert repository.get(slow.operation_id).state.value == "RETRYABLE"


@pytest.mark.parametrize("reason", [
    "MANUFACTURED_ENGAGEMENT_QUESTION",
])
def test_hard_quality_failure_is_terminally_suppressed_before_send(durable, reason):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    operation, _ = service.begin(inbound(810006, 600, "question?", now))
    claimed = service.claim_generation(operation)
    result = generated_result(inbound(810006, 600, "question?", now), "bad candidate")
    result.diagnostic_metadata["conversationQualityReasons"] = [reason]
    suppressed = service.generated(claimed, result)
    assert suppressed.state.value == "SUPPRESSED"
    assert suppressed.last_error.startswith("quality_blocked_before_delivery:")
    assert service.claim_send(suppressed) is None
    service.recover_startup()
    assert repository.get(suppressed.operation_id).state.value == "SUPPRESSED"


def test_final_turn_obligation_failure_gets_one_correction_then_terminal(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    payload = inbound(810006, 601, "question?", now)
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    rejected = generated_result(payload, "bad candidate")
    rejected.diagnostic_metadata["conversationQualityReasons"] = [
        "FINAL_TURN_OBLIGATION_FAILURE"
    ]
    correction = service.generated(first, rejected)
    assert correction.state.value == "RETRYABLE"
    assert correction.generation_attempt_count == 1
    assert correction.send_attempt_count == 0
    assert correction.response_payload is None
    assert service.claim_send(correction) is None

    due = service.due_availability_payloads(
        now=correction.next_retry_at + timedelta(seconds=1),
    )
    assert len(due) == 1
    second = service.claim_generation(repository.get(operation.operation_id))
    assert second.generation_attempt_count == 2
    repeated = generated_result(payload, "still bad")
    repeated.diagnostic_metadata["conversationQualityReasons"] = [
        "FINAL_TURN_OBLIGATION_FAILURE"
    ]
    terminal = service.generated(second, repeated)
    assert terminal.state.value == "SUPPRESSED"
    assert terminal.last_error.startswith("quality_corrective_retry_exhausted:")
    assert terminal.send_attempt_count == 0
    assert service.claim_generation(terminal) is None
    assert service.claim_send(terminal) is None


def test_repetition_failure_persists_exclusions_and_allows_one_fresh_attempt(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    rejected_text = "then don't make it too easy for me"
    for message_id, historical_text in (
        (2598, rejected_text), (2599, "A different recent answer"),
    ):
        historical_payload = inbound(810026, message_id, "earlier turn", now)
        historical, _ = service.begin(historical_payload)
        historical = service.generated(
            service.claim_generation(historical),
            generated_result(historical_payload, historical_text),
        )
        service.confirmed(service.claim_send(historical), 990000 + message_id)
    payload = inbound(810026, 2600, "How's my tease today", now)
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    rejected = generated_result(payload, rejected_text)
    rejected.diagnostic_metadata["conversationQualityReasons"] = [
        "FINAL_REPETITION_FAILURE"
    ]
    scheduled = service.generated(first, rejected)

    assert scheduled.state.value == "RETRYABLE"
    assert scheduled.generation_attempt_count == 1
    assert scheduled.max_generation_attempts == 2
    assert scheduled.send_attempt_count == 0
    correction = scheduled.delivery_payload["qualityCorrectiveRetry"]
    assert correction["attempt"] == 2
    assert correction["previousCandidateText"] == rejected_text
    assert correction["excludedExactResponses"] == [
        rejected_text, "A different recent answer",
    ]
    assert correction["exclusionAuthority"] == "FINAL_RESPONSE_EXACT_NOVELTY"
    attempts = repository.generation_attempts(operation.operation_id)
    assert [(item["attempt_number"], item["candidate_text"]) for item in attempts] == [
        (1, rejected_text),
    ]
    assert attempts[0]["quality_reasons"] == ["FINAL_REPETITION_FAILURE"]
    assert attempts[0]["quality_disposition"] == "BLOCKED_BEFORE_DELIVERY"

    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW() "
            "WHERE operation_id=%s", (operation.operation_id,),
        )
    retry_payload = service.retry_payload(repository.get(operation.operation_id))
    assert retry_payload.quality_correction_context["excludedExactResponses"] == [
        rejected_text, "A different recent answer",
    ]
    second = service.claim_generation(repository.get(operation.operation_id))
    assert second.generation_attempt_count == 2
    fresh = service.generated(second, generated_result(
        payload, "You definitely know how to keep me curious today.",
    ))
    assert fresh.state.value == "GENERATED"
    assert fresh.generation_attempt_count == 2
    assert fresh.send_attempt_count == 0
    assert service.claim_generation(fresh) is None
    attempts = repository.generation_attempts(operation.operation_id)
    assert [item["attempt_number"] for item in attempts] == [1, 2]
    assert attempts[1]["quality_disposition"] == "ALLOWED_BEFORE_DELIVERY"
    assert attempts[1]["sent_confirmed"] is False


@pytest.mark.parametrize("reasons", [
    ("CUSTOMER_QUESTION_UNANSWERED",),
    ("TURN_OBLIGATIONS_UNSATISFIED",),
    ("CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED"),
])
def test_required_quality_failure_gets_one_durable_corrective_attempt(durable, reasons):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    payload = inbound(810016, 1600, "What did you mean?", now)
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    bad = generated_result(payload, "bad candidate")
    bad.diagnostic_metadata["conversationQualityReasons"] = list(reasons)
    scheduled = service.generated(first, bad)
    assert scheduled.state.value == "RETRYABLE"
    assert scheduled.last_error == "quality_corrective_retry_scheduled"
    assert scheduled.generation_attempt_count == 1
    assert scheduled.max_generation_attempts == 2
    assert scheduled.next_retry_at is not None
    assert scheduled.response_payload is None
    assert scheduled.send_attempt_count == 0

    due = service.due_availability_payloads(
        now=scheduled.next_retry_at + timedelta(seconds=1),
    )
    assert len(due) == 1
    assert due[0].quality_correction_context["required"] is True
    second = service.claim_generation(repository.get(operation.operation_id))
    assert second.generation_attempt_count == 2
    still_bad = generated_result(payload, "still bad")
    still_bad.diagnostic_metadata["conversationQualityReasons"] = list(reasons)
    terminal = service.generated(second, still_bad)
    assert terminal.state.value == "SUPPRESSED"
    assert terminal.last_error.startswith("quality_corrective_retry_exhausted:")
    assert terminal.next_retry_at is None
    assert terminal.send_attempt_count == 0
    assert service.claim_generation(terminal) is None


@pytest.mark.parametrize("reason", [
    "CUSTOMER_QUESTION_UNANSWERED", "FINAL_REPETITION_FAILURE",
])
def test_newer_inbound_supersedes_quality_correction_atomically(durable, reason):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    old_payload = inbound(810017, 1700, "What do you mean?", now)
    old, _ = service.begin(old_payload)
    claimed = service.claim_generation(old)
    newer, _ = service.begin(inbound(
        810017, 1701, "Actually, tell me something else", now + timedelta(seconds=1),
    ))
    bad = generated_result(old_payload, "bad")
    bad.diagnostic_metadata["conversationQualityReasons"] = [reason]
    superseded = service.generated(claimed, bad)
    assert superseded.state.value == "SUPPRESSED"
    assert superseded.last_error == "quality_correction_superseded_by_newer_inbound"
    assert superseded.next_retry_at is None
    assert repository.get(newer.operation_id).state.value == "PENDING_GENERATION"


def test_corrective_candidate_passes_and_confirms_exactly_once(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    payload = inbound(810018, 1800, "Can you answer that?", now)
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    bad = generated_result(payload, "bad")
    bad.diagnostic_metadata["conversationQualityReasons"] = [
        "CUSTOMER_QUESTION_UNANSWERED"
    ]
    scheduled = service.generated(first, bad)
    service.due_availability_payloads(
        now=scheduled.next_retry_at + timedelta(seconds=1),
    )
    second = service.claim_generation(repository.get(operation.operation_id))
    generated = service.generated(second, generated_result(payload, "Direct answer."))
    assert generated.state.value == "GENERATED"
    assert generated.generation_attempt_count == 2
    sending = service.claim_send(generated)
    assert sending.send_attempt_count == 1
    assert service.claim_send(sending) is None
    confirmed = service.confirmed(sending, 991800)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert service.claim_send(confirmed) is None


def test_corrective_provider_failure_exhausts_two_generation_claims(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    payload = inbound(810019, 1900, "What is the answer?", now)
    operation, _ = service.begin(payload)
    first = service.claim_generation(operation)
    bad = generated_result(payload, "bad")
    bad.diagnostic_metadata["conversationQualityReasons"] = [
        "TURN_OBLIGATIONS_UNSATISFIED"
    ]
    scheduled = service.generated(first, bad)
    service.due_availability_payloads(
        now=scheduled.next_retry_at + timedelta(seconds=1),
    )
    second = service.claim_generation(repository.get(operation.operation_id))
    failed = service.generation_failed(second, TimeoutError("provider unavailable"))
    assert failed.state.value == "TERMINAL_FAILED"
    assert failed.generation_attempt_count == 2
    assert failed.next_retry_at is None
    assert failed.send_attempt_count == 0
    assert service.claim_generation(failed) is None


def test_fallbacks_do_not_create_retryable_debt(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    for index, text in enumerate(("Can you answer this?", "😘"), start=700):
        operation, _ = service.begin(inbound(810007 + index, index, text, now))
        claimed = service.claim_generation(operation)
        empty = generated_result(inbound(810007 + index, index, text, now), "")
        retryable = service.generated(claimed, empty)
        assert retryable.state.value == "RETRYABLE"
        assert retryable.generation_attempt_count == 1
        assert retryable.send_attempt_count == 0
        assert not retryable.response_text
        assert service.claim_send(retryable) is None

        exhausted = retryable
        while exhausted.state.value == "RETRYABLE":
            next_claim = service.claim_generation(
                repository.get(operation.operation_id)
            )
            assert next_claim is not None
            assert next_claim.send_attempt_count == 0
            fresh_empty = generated_result(
                inbound(810007 + index, index, text, now), ""
            )
            exhausted = service.generated(next_claim, fresh_empty)
        assert exhausted.state.value == "TERMINAL_FAILED"
        assert exhausted.generation_attempt_count == exhausted.max_generation_attempts
        assert exhausted.send_attempt_count == 0
        assert not exhausted.response_text
        assert service.claim_generation(exhausted) is None
        assert service.claim_send(exhausted) is None


def test_busy_availability_is_not_accelerated_by_priority(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    original_check = now + timedelta(minutes=12)
    messages = [
        (800, "❤️"),
        (801, "Can you answer me?"),
        (802, "What is the price of that set?"),
    ]
    operations = []
    for index, (message_id, text) in enumerate(messages):
        operation, _ = service.begin(inbound(810800, message_id, text, now))
        scheduled = original_check if index == 0 else now + timedelta(seconds=30)
        operations.append(service.defer_for_availability(operation, decision(scheduled, "BUSY")))

    persisted = [repository.get(item.operation_id) for item in operations]
    assert all(item.scheduled_delivery_at == original_check for item in persisted)
    assert all(item.next_retry_at == persisted[0].next_retry_at for item in persisted)
    assert persisted[0].next_retry_at == original_check - timedelta(minutes=5)
    assert service.due_availability_payloads(now=now + timedelta(minutes=2)) == []

    due = service.due_availability_payloads(
        now=original_check - timedelta(minutes=5) + timedelta(seconds=1))
    assert len(due) == 1
    assert due[0].message_id == 802
    assert "price" in due[0].message_text


def test_sustained_low_information_is_intentionally_suppressed_without_debt(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    texts = ["❤️", "you've gone quiet", "😘", "hello?", "🔥", "love you babe", "❤️❤️"]
    operations = []
    for offset, text in enumerate(texts, start=900):
        operation, _ = service.begin(inbound(810900, offset, text, now))
        operations.append(service.defer_for_availability(
            operation, decision(now - timedelta(seconds=30), "BUSY")))

    assert service.due_availability_payloads(now=now + timedelta(seconds=20)) == []
    persisted = [repository.get(item.operation_id) for item in operations]
    assert all(item.state.value == "SUPPRESSED" for item in persisted)
    assert sum(item.generation_attempt_count for item in persisted) == 0
    authority = next(item for item in persisted if item.last_error == "NO_RESPONSE_REQUIRED")
    assert authority.delivery_payload["attentionInvestment"]["investment"] == "MINIMAL_NURTURE"
    assert authority.delivery_payload["attentionInvestment"]["permanentCustomerLabel"] is False


def test_historical_retryable_suppression_preserves_failure_and_never_sends(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    operation, _ = service.begin(inbound(811000, 1000, "old question?", now))
    claimed = service.claim_generation(operation)
    retryable = service.generation_failed(claimed, RuntimeError("historical empty"))

    suppressed = service.suppress_historical_retryable(
        retryable, reason="HISTORICAL_RETRYABLE_SUPERSEDED", disposition_at=now,
    )
    audit = suppressed.delivery_payload
    assert suppressed.state.value == "SUPPRESSED"
    assert suppressed.last_error == "HISTORICAL_RETRYABLE_SUPERSEDED"
    assert suppressed.send_attempt_count == 0
    assert suppressed.outbound_telegram_message_id is None
    assert "historical empty" in audit["historicalRetryableFailure"]["originalLastError"]
    assert audit["historicalRetryableFailure"]["originalGenerationAttempts"] == 1
    assert audit["historicalRetryableDisposition"]["noDeliveryConfirmed"] is True
    assert service.claim_send(repository.get(operation.operation_id)) is None


def test_repeated_flirt_function_is_repaired_durably_before_send(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    for message_id, reply, outbound_id in (
        (1100, "You're making me curious.", 91100),
        (1101, "You've got me wondering.", 91101),
    ):
        payload = inbound(811100, message_id, "nice", now)
        operation, _ = service.begin(payload)
        generated = service.generated(
            service.claim_generation(operation), generated_result(payload, reply),
        )
        service.confirmed(service.claim_send(generated), outbound_id)

    current_payload = inbound(811100, 1102, "always", now)
    current, _ = service.begin(current_payload)
    repaired = service.generated(
        service.claim_generation(current),
        generated_result(current_payload, "Now I'm intrigued."),
    )
    assert repaired.state.value == "GENERATED"
    assert repaired.response_text == "You're sweet 😘"
    diagnostics = repaired.response_payload["diagnostic_metadata"]["naturalConversation"]
    assert diagnostics["repairReasons"] == ["REPEATED_FLIRT_FUNCTION"]

    restarted = OrdinaryChatReplyService(repository=repository, worker_id="natural-restart")
    restarted.ACCOUNT_SCOPE = scope
    sending = restarted.claim_send(repository.get(repaired.operation_id))
    assert sending.send_attempt_count == 1
    confirmed = restarted.confirmed(sending, 91102)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert restarted.claim_send(confirmed) is None

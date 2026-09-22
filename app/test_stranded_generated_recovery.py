"""Isolated certification for stranded ordinary GENERATED recovery."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from types import SimpleNamespace

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.operator_delivery_resolution_repository import OperatorDeliveryResolutionRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.testing.postgres_safety import (
    isolated_application_database_scope,
    isolated_test_connection,
    require_isolated_test_database_url,
)


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
PRODUCTION_DATABASE_URL = (
    os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL")
)
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL,
        PRODUCTION_DATABASE_URL,
    )
    with isolated_test_connection(url, PRODUCTION_DATABASE_URL) as connection:
        yield connection


@pytest.fixture(autouse=True)
def bind_all_dependencies_to_isolated_database():
    with isolated_application_database_scope(
            TEST_DATABASE_URL, PRODUCTION_DATABASE_URL):
        yield


@pytest.fixture
def authority():
    suffix = uuid4().int % 100000000
    user_id = 7000000000 + suffix
    scope = f"STRANDED_TEST_{uuid4()}"
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    service = OrdinaryChatReplyService(
        repository=repository, worker_id="stranded-test",
        creator_profile_id=2, fanvue_account_id=2,
    )
    service.ACCOUNT_SCOPE = scope
    with connection_factory() as connection:
        connection.execute("""INSERT INTO telegram_sales_prospects(
            telegram_sales_prospect_id,creator_profile_id,fanvue_account_id,
            telegram_user_id,telegram_chat_id,relationship_state,preference_state,
            inbound_message_count,first_observed_at,last_observed_at)
            VALUES (%s,2,2,%s,%s,'{}'::jsonb,'{}'::jsonb,1,NOW(),NOW())""",
            (uuid4(), user_id, user_id))
    yield service, repository, scope, user_id
    with connection_factory() as connection:
        connection.execute("""DELETE FROM market_tier_confirmed_reply_events
            WHERE operation_id IN (
              SELECT operation_id FROM ordinary_chat_reply_operations
              WHERE telegram_account_scope=%s)""", (scope,))
        connection.execute("""DELETE FROM operator_delivery_resolutions
            WHERE ordinary_operation_id IN (
              SELECT operation_id FROM ordinary_chat_reply_operations
              WHERE telegram_account_scope=%s)""", (scope,))
        connection.execute(
            "DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s",
            (scope,),
        )
        connection.execute(
            "DELETE FROM telegram_sales_prospects WHERE creator_profile_id=2 AND fanvue_account_id=2 AND telegram_user_id=%s",
            (user_id,),
        )


def generated(authority, *, fallback=False, message_id=1):
    service, repository, _, user_id = authority
    payload = TelegramInboundPayload(
        telegram_user_id=user_id, telegram_chat_id=user_id,
        message_text="hello", message_id=message_id,
        received_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    operation, _ = service.begin(payload)
    repository.record_pre_generation_commercial_decision(
        operation.operation_id, {"decision": "ORDINARY_NONCOMMERCIAL"})
    repository.record_attention(operation.operation_id, {"outcome": "RESPOND"})
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=delivery_payload||%s::jsonb WHERE operation_id=%s""",
            ('{"availability":{"availabilityState":"ACTIVE"},"marketResourcePolicy":{"allowed":true}}',
             operation.operation_id))
    claimed = service.claim_generation(repository.get(operation.operation_id))
    result = TelegramInboundResult(
        correlation_id=f"test:{message_id}", telegram_chat_id=user_id,
        telegram_user_id=user_id, message_id=message_id, engine_user_id="test",
        response_text="fallback" if fallback else "valid reply",
        offer_authorized=False, offer_link=None, blocked=False,
        error_code="decision_engine_exception" if fallback else None,
        delivery_payload={"type": "MESSAGE_TEXT"},
        diagnostic_metadata=({"generation_fallback": {
            "applied": True, "reason": "DECISION_ENGINE_EXCEPTION"}}
            if fallback else {"delivery_quality_gate": {"disposition": "ALLOWED"}}),
    )
    stored = service.generated(claimed, result)
    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET updated_at=NOW()-INTERVAL '2 minutes' WHERE operation_id=%s",
            (stored.operation_id,),
        )
    return repository.get(stored.operation_id)


def recover(authority):
    service, _, _, _ = authority
    return service.recover_stranded_generated(now=datetime.now(timezone.utc))


def uncertain_operation(authority, *, message_id=70):
    operation = generated(authority, message_id=message_id)
    service, repository, _, _ = authority
    sending = service.claim_send(operation)
    assert sending is not None
    return service.uncertain(sending, TimeoutError("ambiguous test send"))


def attest(authority, operation, outcome="NOT_DELIVERED"):
    _, _, _, user_id = authority
    return OperatorDeliveryResolutionRepository(connection_factory).resolve(
        operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2,
        relationship_key=f"telegram:2:2:{user_id}",
        telegram_user_id=user_id, telegram_chat_id=user_id,
        purchase_intent_id=None, outcome=outcome,
        presentation_mode="ORDINARY_TEXT",
        provider_acceptance_evidence=False,
        provider_readback_evidence=False,
        resolved_by="focused-recovery-test",
        evidence={"source": "isolated_telegram_history"},
    )


def recover_attested(authority, operation):
    service, repository, _, user_id = authority
    return repository.recover_attested_not_delivered(
        operation_id=operation.operation_id,
        creator_profile_id=2, fanvue_account_id=2,
        telegram_account_scope=operation.telegram_account_scope,
        telegram_user_id=user_id, telegram_chat_id=user_id,
        inbound_message_id=operation.inbound_telegram_message_id,
    )


def pending(authority, *, message_id=1):
    service, repository, _, user_id = authority
    operation, created = service.begin(TelegramInboundPayload(
        telegram_user_id=user_id, telegram_chat_id=user_id,
        message_text="preserved ordinary inbound", message_id=message_id,
        received_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    ))
    assert created
    return repository.get(operation.operation_id)


def reclaim_pending(authority, *, worker_id="pending-reclaimer"):
    service, repository, scope, _ = authority
    worker = OrdinaryChatReplyService(
        repository=repository, worker_id=worker_id,
        creator_profile_id=2, fanvue_account_id=2,
    )
    worker.ACCOUNT_SCOPE = scope
    return worker, worker.reclaim_stranded_pending_payloads(
        now=datetime.now(timezone.utc)
    )


def maintain(authority, *, worker_id="lifecycle-maintainer"):
    service, repository, scope, _ = authority
    worker = OrdinaryChatReplyService(
        repository=repository, worker_id=worker_id,
        creator_profile_id=2, fanvue_account_id=2,
    )
    worker.ACCOUNT_SCOPE = scope
    return worker.maintain_stranded_lifecycle(now=datetime.now(timezone.utc))


def expire_generation(authority, operation):
    service, repository, _, _ = authority
    claimed = service.claim_generation(operation)
    assert claimed is not None
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations
            SET lease_expires_at=NOW()-INTERVAL '1 minute'
            WHERE operation_id=%s""", (claimed.operation_id,))
    return repository.get(claimed.operation_id)


def test_expired_current_generation_is_discovered_and_existing_claim_is_single_winner(authority):
    operation = expire_generation(authority, pending(authority, message_id=801))
    first = maintain(authority)
    assert first["expiredGeneratingFound"] == 1
    assert first["expiredGeneratingReclaimed"] == 1
    assert [item.message_id for item in first["payloads"]] == [801]
    worker_a = OrdinaryChatReplyService(
        repository=authority[1], worker_id="reclaim-a")
    worker_b = OrdinaryChatReplyService(
        repository=authority[1], worker_id="reclaim-b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda worker: worker.claim_generation(operation),
                               (worker_a, worker_b)))
    assert sum(item is not None for item in claims) == 1
    current = authority[1].get(operation.operation_id)
    assert current.state.value == "GENERATING"
    assert current.generation_attempt_count == 2


def test_active_or_exhausted_generation_is_not_discovered(authority):
    active = authority[0].claim_generation(pending(authority, message_id=802))
    assert maintain(authority)["expiredGeneratingFound"] == 0
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
            lease_expires_at=NOW()-INTERVAL '1 minute',
            generation_attempt_count=max_generation_attempts
            WHERE operation_id=%s""", (active.operation_id,))
    assert maintain(authority)["expiredGeneratingFound"] == 0


def test_superseded_expired_generation_terminalizes_with_audit_and_never_reclaims(authority):
    old = expire_generation(authority, pending(authority, message_id=803))
    pending(authority, message_id=804)
    result = maintain(authority)
    assert result["expiredGeneratingSuperseded"] == 1
    assert result["expiredGeneratingReclaimed"] == 0
    current = authority[1].get(old.operation_id)
    assert current.state.value == "SUPPRESSED"
    assert current.last_error == "SUPERSEDED_AFTER_EXPIRED_GENERATION_CLAIM"
    audit = current.delivery_payload["expiredGenerationSupersession"]
    assert audit["originalState"] == "GENERATING"
    assert audit["originalGenerationAttempts"] == 1
    assert audit["newerOperation"] is True


def test_superseded_pending_terminalizes_concurrently_and_records_authority(authority):
    old = pending(authority, message_id=805)
    pending(authority, message_id=806)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: maintain(authority, worker_id=name),
                                ("maintain-a", "maintain-b")))
    assert sum(item["pendingSupersededFinalized"] for item in results) == 1
    current = authority[1].get(old.operation_id)
    assert current.state.value == "SUPPRESSED"
    audit = current.delivery_payload["pendingGenerationSupersession"]
    assert audit["originalState"] == "PENDING_GENERATION"
    assert audit["supersedingInboundId"] == 806


def test_relationship_control_block_is_terminal_and_cannot_revive(authority):
    operation = generated(authority, message_id=807)
    sending = authority[0].claim_send(operation)
    blocked = authority[0].deterministic_delivery_blocked(
        sending, reason="RELATIONSHIP_HUMAN_OPERATOR_ACTIVE",
        metadata={"capturedControlVersion": 2, "currentControlVersion": 4},
    )
    assert blocked.state.value == "RETRYABLE" and blocked.next_retry_at is None
    result = maintain(authority)
    assert result["unscheduledRetryableFound"] == 1
    assert result["unscheduledRetryableFinalizedOrRescheduled"] == 1
    current = authority[1].get(operation.operation_id)
    assert current.state.value == "SUPPRESSED"
    assert current.response_payload is not None
    assert current.last_error == "AUTOMATIC_REPLY_INVALIDATED_BY_RELATIONSHIP_CONTROL"
    assert authority[0].claim_send(current) is None
    assert current.delivery_payload["relationshipControlInvalidation"][
        "automaticResumptionAllowed"] is False


def test_error_fallback_is_rejected_before_stranded_delivery_recovery(authority):
    operation = generated(authority, fallback=True)
    first = recover(authority)
    second = recover(authority)
    assert first == [] and second == []
    recovered = authority[1].get(operation.operation_id)
    assert recovered.state.value == "SUPPRESSED"
    assert recovered.response_payload is not None
    assert recovered.response_text == "fallback"
    assert recovered.last_error == (
        "quality_blocked_before_delivery:INTERNAL_FAILURE_PAYLOAD"
    )
    assert "message_text" not in recovered.delivery_payload
    assert "strandedGeneratedRecovery" not in recovered.delivery_payload
    assert recovered.generation_attempt_count == 1
    assert recovered.send_attempt_count == 0


def test_valid_payload_reenters_existing_send_retry_and_preserves_evidence(authority):
    operation = generated(authority)
    recovered = recover(authority)
    assert len(recovered) == 1
    current = authority[1].get(operation.operation_id)
    assert current.state.value == "RETRYABLE"
    assert current.response_text == "valid reply" and current.response_payload is not None
    assert current.last_error == "stranded_generated_recovery"
    assert current.delivery_payload["availability"]["availabilityState"] == "ACTIVE"
    assert current.delivery_payload["attentionInvestment"]["outcome"] == "RESPOND"
    assert current.delivery_payload["preGenerationCommercialDecision"]["decision"] == "ORDINARY_NONCOMMERCIAL"
    assert current.delivery_payload["marketResourcePolicy"]["allowed"] is True
    due = authority[0].due_generated_send_payloads(now=datetime.now(timezone.utc))
    assert [item.message_id for item in due] == [operation.inbound_telegram_message_id]


def test_attested_not_delivered_recovery_preserves_payload_hash_and_generation(authority):
    operation = uncertain_operation(authority)
    original_payload = operation.response_payload
    original_text = operation.response_text
    original_hash = operation.response_content_sha256
    attest(authority, operation)
    recovered = recover_attested(authority, operation)
    assert recovered.state.value == "RETRYABLE"
    assert recovered.response_payload == original_payload
    assert recovered.response_text == original_text
    assert recovered.response_content_sha256 == original_hash
    assert recovered.generation_attempt_count == 1
    assert recovered.send_attempt_count == 1
    due = authority[0].due_generated_send_payloads(now=datetime.now(timezone.utc))
    assert [item.message_id for item in due] == [operation.inbound_telegram_message_id]


def test_unreconciled_or_ambiguous_send_uncertain_remains_blocked(authority):
    operation = uncertain_operation(authority)
    with pytest.raises(ValueError, match="NOT_DELIVERED"):
        recover_attested(authority, operation)
    assert authority[0].due_generated_send_payloads(now=datetime.now(timezone.utc)) == []


def test_delivered_attestation_cannot_unlock_retry(authority):
    operation = uncertain_operation(authority)
    attest(authority, operation, outcome="DELIVERED")
    with pytest.raises(ValueError, match="NOT_DELIVERED"):
        recover_attested(authority, operation)


@pytest.mark.parametrize("assignment", [
    "response_payload=NULL", "response_text=NULL",
    "response_content_sha256='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'",
    "claim_owner='active',lease_expires_at=NOW()+INTERVAL '5 minutes'",
    "outbound_telegram_message_id=99991",
])
def test_attested_recovery_rejects_missing_identity_active_lease_or_delivery(authority, assignment):
    operation = uncertain_operation(authority)
    attest(authority, operation)
    with connection_factory() as connection:
        connection.execute(
            f"UPDATE ordinary_chat_reply_operations SET {assignment} WHERE operation_id=%s",
            (operation.operation_id,),
        )
    with pytest.raises(ValueError):
        recover_attested(authority, operation)


def test_attested_recovery_rejects_newer_inbound(authority):
    operation = uncertain_operation(authority, message_id=80)
    attest(authority, operation)
    pending(authority, message_id=81)
    with pytest.raises(ValueError, match="stale"):
        recover_attested(authority, operation)


def test_attested_recovery_is_single_winner_and_restart_safe(authority):
    operation = uncertain_operation(authority)
    attest(authority, operation)
    recovered = recover_attested(authority, operation)
    with pytest.raises(ValueError, match="SEND_UNCERTAIN"):
        recover_attested(authority, operation)
    restarted = OrdinaryChatReplyService(
        repository=authority[1], worker_id="restarted",
        creator_profile_id=2, fanvue_account_id=2,
    )
    restarted.ACCOUNT_SCOPE = authority[2]
    due = restarted.due_generated_send_payloads(now=datetime.now(timezone.utc))
    assert [item.message_id for item in due] == [operation.inbound_telegram_message_id]
    assert recovered.generation_attempt_count == 1


def test_attested_recovery_concurrent_callers_have_exactly_one_winner(authority):
    operation = uncertain_operation(authority)
    attest(authority, operation)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(recover_attested, authority, operation) for _ in range(2)]
    outcomes = []
    for future in futures:
        try:
            outcomes.append(future.result().state.value)
        except ValueError as error:
            outcomes.append(str(error))
    assert outcomes.count("RETRYABLE") == 1
    assert sum("SEND_UNCERTAIN" in outcome for outcome in outcomes) == 1


def test_attested_retry_uses_existing_confirmation_semantics(authority):
    operation = uncertain_operation(authority)
    attest(authority, operation)
    sending = authority[0].claim_send(recover_attested(authority, operation))
    confirmed = authority[0].confirmed(sending, telegram_message_id=99992)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert confirmed.outbound_telegram_message_id == 99992
    assert confirmed.response_text == operation.response_text
    assert confirmed.response_content_sha256 == operation.response_content_sha256
    assert confirmed.generation_attempt_count == 1
    assert confirmed.send_attempt_count == 2


def test_attested_retry_uses_existing_send_confirmation_and_failure_semantics(authority):
    operation = uncertain_operation(authority)
    attest(authority, operation)
    recovered = recover_attested(authority, operation)
    sending = authority[0].claim_send(recovered)
    assert sending.response_text == operation.response_text
    assert sending.response_content_sha256 == operation.response_content_sha256
    assert sending.generation_attempt_count == 1
    assert sending.send_attempt_count == 2
    failed = authority[0].failed(
        sending, ConnectionError("definitely not sent"),
        definitive=True, recoverable=True,
    )
    assert failed.state.value == "RETRYABLE"
    assert failed.response_text == operation.response_text
    assert failed.generation_attempt_count == 1


def test_newer_inbound_prevents_recovery(authority):
    old = generated(authority, message_id=10)
    service, repository, _, user_id = authority
    service.begin(TelegramInboundPayload(
        telegram_user_id=user_id, telegram_chat_id=user_id,
        message_text="new authority", message_id=11,
        received_at=datetime.now(timezone.utc),
    ))
    assert recover(authority) == []
    assert repository.get(old.operation_id).state.value == "SUPPRESSED"


def test_pending_generation_reclamation_is_single_winner_and_reschedules_normally(authority):
    operation = pending(authority)
    first, payloads = reclaim_pending(authority, worker_id="pending-a")
    _, competing = reclaim_pending(authority, worker_id="pending-b")
    assert [payload.message_id for payload in payloads] == [operation.inbound_telegram_message_id]
    assert competing == []

    reserved = authority[1].get(operation.operation_id)
    assert reserved.state.value == "PENDING_GENERATION"
    assert reserved.generation_attempt_count == 0
    assert reserved.send_attempt_count == 0
    assert reserved.response_payload is None and reserved.response_text is None
    assert reserved.outbound_telegram_message_id is None
    assert reserved.claim_owner == "pending-a"

    delivery_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    scheduled = first.defer_for_availability(reserved, SimpleNamespace(
        available_at=delivery_at,
        category="NORMAL",
        diagnostics=lambda: {"category": "NORMAL", "quietPeriodSeconds": 8},
    ))
    assert scheduled.state.value == "RETRYABLE"
    assert scheduled.claim_owner is None
    assert scheduled.generation_attempt_count == 0
    assert scheduled.send_attempt_count == 0
    assert scheduled.scheduled_delivery_at == delivery_at
    assert scheduled.preparation_eligible_at == delivery_at - timedelta(minutes=5)


def test_pending_generation_with_newer_inbound_is_not_reclaimed(authority):
    old = pending(authority, message_id=20)
    pending(authority, message_id=21)
    _, payloads = reclaim_pending(authority)
    assert [payload.message_id for payload in payloads] == [21]
    assert authority[1].get(old.operation_id).claim_owner is None


@pytest.mark.parametrize("boundary", ["claim", "payload", "text", "outbound", "sent", "suppressed"])
def test_pending_generation_delivery_boundaries_are_not_reclaimed(authority, boundary):
    operation = pending(authority)
    assignments = {
        "claim": "claim_owner='active',lease_expires_at=NOW()+INTERVAL '5 minutes'",
        "payload": "response_payload='{}'::jsonb",
        "text": "response_text='already generated'",
        "outbound": "outbound_telegram_message_id=9912",
        "sent": "send_attempt_count=1",
        "suppressed": "state='SUPPRESSED'",
    }
    with connection_factory() as connection:
        connection.execute(
            f"UPDATE ordinary_chat_reply_operations SET {assignments[boundary]} WHERE operation_id=%s",
            (operation.operation_id,),
        )
    _, payloads = reclaim_pending(authority)
    assert payloads == []


def test_legacy_retryable_null_preparation_timestamps_uses_next_retry_at(authority):
    operation = pending(authority)
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',last_error='availability_deferred',next_retry_at=NOW(),
            scheduled_delivery_at=NULL,preparation_eligible_at=NULL
            WHERE operation_id=%s""", (operation.operation_id,))
    legacy_service = OrdinaryChatReplyService(
        repository=authority[1], worker_id="legacy-compatibility-test",
    )
    legacy_service.ACCOUNT_SCOPE = authority[2]
    due = legacy_service.due_availability_payloads(
        now=datetime.now(timezone.utc) + timedelta(seconds=1)
    )
    assert [payload.message_id for payload in due] == [operation.inbound_telegram_message_id]
    current = authority[1].get(operation.operation_id)
    assert current.state.value == "PENDING_GENERATION"
    assert current.scheduled_delivery_at is None
    assert current.preparation_eligible_at is None


@pytest.mark.parametrize("boundary", ["sending", "outbound", "confirmed", "claim"])
def test_delivery_boundary_is_not_recovered(authority, boundary):
    operation = generated(authority)
    assignments = {
        "sending": "sending_at=NOW()",
        "outbound": "outbound_telegram_message_id=9911",
        "confirmed": "sent_confirmed_at=NOW()",
        "claim": "claim_owner='active',lease_expires_at=NOW()+INTERVAL '5 minutes'",
    }
    with connection_factory() as connection:
        connection.execute(
            f"UPDATE ordinary_chat_reply_operations SET {assignments[boundary]} WHERE operation_id=%s",
            (operation.operation_id,),
        )
    assert recover(authority) == []

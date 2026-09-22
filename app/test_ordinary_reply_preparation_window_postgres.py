"""Isolated PostgreSQL certification for the pre-generation preview window."""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import (
    isolated_application_database_scope,
    isolated_test_connection,
    require_isolated_test_database_url,
)


MIGRATION = "20260916_139_ordinary_reply_preparation_window.sql"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


def isolated_url():
    return require_isolated_test_database_url(
        TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )


@contextmanager
def connection_factory():
    with isolated_test_connection(
        isolated_url(),
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    ) as connection:
        yield connection


@pytest.fixture(autouse=True)
def bind_all_dependencies_to_isolated_database():
    with isolated_application_database_scope(
        isolated_url(),
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    ):
        yield


@pytest.fixture
def durable():
    scope = f"PREPARATION_TEST_{uuid4()}"
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    service = OrdinaryChatReplyService(repository=repository, worker_id=f"worker-{uuid4()}")
    service.ACCOUNT_SCOPE = scope
    yield service, repository, scope
    with connection_factory() as connection:
        connection.execute(
            "DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s",
            (scope,),
        )


def inbound(chat, message_id, text, now):
    return TelegramInboundPayload(
        telegram_user_id=chat,
        telegram_chat_id=chat,
        message_text=text,
        message_id=message_id,
        received_at=now,
    )


def result(payload, text):
    return TelegramInboundResult(
        correlation_id=f"result:{payload.telegram_chat_id}:{payload.message_id}",
        telegram_chat_id=payload.telegram_chat_id,
        telegram_user_id=payload.telegram_user_id,
        message_id=payload.message_id,
        engine_user_id="isolated-test",
        response_text=text,
        offer_authorized=False,
        offer_link=None,
        blocked=False,
        error_code=None,
        delivery_payload={},
        diagnostic_metadata={},
    )


def availability(delivery_at):
    return SimpleNamespace(
        available_at=delivery_at,
        category="NORMAL",
        diagnostics=lambda: {
            "category": "NORMAL",
            "availableAt": delivery_at.isoformat(),
            "quietPeriodSeconds": 8,
        },
    )


def test_migration_forward_rollback_reforward_isolated_only():
    manager = SchemaManagerService(connection_factory=connection_factory)
    manager.reconcile_one(MIGRATION)
    with connect(isolated_url(), autocommit=True) as connection:
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='ordinary_chat_reply_operations'"
            )
        }
        assert {"scheduled_delivery_at", "preparation_eligible_at"} <= columns
        rollback = Path("migrations/rollback") / MIGRATION
        connection.execute(rollback.read_text(encoding="utf-8"))
        connection.execute(
            "DELETE FROM schema_migrations WHERE migration_name=%s", (MIGRATION,)
        )
        columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='ordinary_chat_reply_operations'"
            )
        }
        assert "scheduled_delivery_at" not in columns
        assert "preparation_eligible_at" not in columns
    report = manager.reconcile_one(MIGRATION)
    assert MIGRATION in report.migrations_applied


def test_prepare_once_then_send_exact_persisted_text_at_original_time(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    delivery_at = now + timedelta(minutes=10)
    payload = inbound(920001, 1, "How are you?", now)
    operation, created = service.begin(payload)
    assert created
    deferred = service.defer_for_availability(operation, availability(delivery_at))
    assert deferred.scheduled_delivery_at == delivery_at
    assert deferred.preparation_eligible_at == delivery_at - timedelta(minutes=5)
    assert deferred.next_retry_at == deferred.preparation_eligible_at

    due = service.due_availability_payloads(
        now=deferred.preparation_eligible_at + timedelta(milliseconds=1)
    )
    assert [item.message_id for item in due] == [1]
    claimed = service.claim_generation(repository.get(operation.operation_id))
    assert claimed.generation_attempt_count == 1
    prepared = service.generated(claimed, result(payload, "The exact prepared reply."))
    assert prepared.state.value == "RETRYABLE"
    assert prepared.response_text == "The exact prepared reply."
    assert prepared.next_retry_at == delivery_at
    assert service.claim_generation(prepared) is None
    assert service.claim_send(prepared) is None

    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW(), "
            "scheduled_delivery_at=NOW() WHERE operation_id=%s",
            (operation.operation_id,),
        )
    restarted = OrdinaryChatReplyService(repository=repository, worker_id="worker-restarted")
    restarted.ACCOUNT_SCOPE = service.ACCOUNT_SCOPE
    due_send = restarted.due_generated_send_payloads(
        now=datetime.now(timezone.utc) + timedelta(seconds=1)
    )
    assert [item.message_id for item in due_send] == [1]
    sending = restarted.claim_send(repository.get(operation.operation_id))
    assert sending.state.value == "SENDING"
    assert sending.response_text == "The exact prepared reply."
    assert sending.generation_attempt_count == 1
    assert sending.send_attempt_count == 1
    retryable = restarted.failed(
        sending, RuntimeError("definitely not sent"), definitive=True, recoverable=True
    )
    assert retryable.state.value == "RETRYABLE"
    assert retryable.response_text == "The exact prepared reply."
    assert retryable.generation_attempt_count == 1
    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET next_retry_at=NOW() "
            "WHERE operation_id=%s", (operation.operation_id,),
        )
    sending_again = restarted.claim_send(repository.get(operation.operation_id))
    confirmed = restarted.confirmed(sending_again, 880001)
    assert confirmed.state.value == "SENT_CONFIRMED"
    assert confirmed.response_text == "The exact prepared reply."
    assert confirmed.generation_attempt_count == 1


def test_prepared_payload_integrity_mismatch_is_terminal_and_not_rediscovered(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    operation, _ = service.begin(inbound(920011, 1, "Yes", now))
    claimed = service.claim_generation(operation)
    generated = service.generated(claimed, result(
        inbound(920011, 1, "Yes", now), "Authoritative prepared reply",
    ))
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations
            SET state='RETRYABLE', last_error='prepared_for_scheduled_delivery',
                next_retry_at=NOW() - INTERVAL '1 second',
                delivery_payload=jsonb_set(delivery_payload,'{message_text}',
                    to_jsonb('Stale payload text'::text),true)
            WHERE operation_id=%s""", (generated.operation_id,))
    prepared = repository.get(generated.operation_id)
    assert prepared.state.value == "RETRYABLE"
    assert service.authorize_customer_visible_delivery(prepared) is False
    terminal = repository.get(generated.operation_id)
    assert terminal.state.value == "SUPPRESSED"
    assert terminal.last_error == "IMMUTABLE_DELIVERY_PAYLOAD_TEXT_MISMATCH"
    assert terminal.generation_attempt_count == 1
    assert terminal.send_attempt_count == 0
    assert terminal.outbound_telegram_message_id is None
    assert terminal.claim_owner is None
    assert terminal.next_retry_at is None
    assert service.due_generated_send_payloads(
        now=datetime.now(timezone.utc) + timedelta(days=1)
    ) == []
    assert service.claim_send(terminal) is None


def test_repeated_availability_check_preserves_original_preparation_window(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    original_delivery = now + timedelta(minutes=10)
    operation, _ = service.begin(inbound(920004, 30, "preserve my schedule", now))
    first = service.defer_for_availability(operation, availability(original_delivery))

    with connection_factory() as connection:
        connection.execute(
            "UPDATE ordinary_chat_reply_operations SET state='PENDING_GENERATION', "
            "next_retry_at=NULL WHERE operation_id=%s", (operation.operation_id,),
        )
    repeated = service.defer_for_availability(
        repository.get(operation.operation_id),
        availability(original_delivery + timedelta(minutes=20)),
    )

    assert repeated.scheduled_delivery_at == original_delivery
    assert repeated.preparation_eligible_at == first.preparation_eligible_at
    assert repeated.next_retry_at == first.preparation_eligible_at


def test_new_inbound_after_preparation_suppresses_old_preview(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    delivery_at = now + timedelta(minutes=10)
    old_payload = inbound(920002, 10, "old turn", now)
    old, _ = service.begin(old_payload)
    deferred = service.defer_for_availability(old, availability(delivery_at))
    due = service.due_availability_payloads(
        now=deferred.preparation_eligible_at + timedelta(milliseconds=1)
    )[0]
    prepared = service.generated(
        service.claim_generation(repository.get(old.operation_id)),
        result(due, "old prepared reply"),
    )
    assert prepared.state.value == "RETRYABLE"

    newer, created = service.begin(inbound(920002, 11, "new turn", now + timedelta(minutes=6)))
    assert created
    assert newer.state.value == "PENDING_GENERATION"
    invalidated = repository.get(old.operation_id)
    assert invalidated.state.value == "SUPPRESSED"
    assert invalidated.last_error == "superseded_by_newer_inbound_after_preparation"
    assert service.claim_send(invalidated) is None


def test_competing_generation_claims_and_failure_are_atomic(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    operation, _ = service.begin(inbound(920003, 20, "one provider call", now))
    first = OrdinaryChatReplyService(repository=repository, worker_id="worker-a")
    second = OrdinaryChatReplyService(repository=repository, worker_id="worker-b")
    first.ACCOUNT_SCOPE = second.ACCOUNT_SCOPE = scope
    claimed = first.claim_generation(operation)
    assert claimed.generation_attempt_count == 1
    assert second.claim_generation(operation) is None
    failed = first.generation_failed(claimed, RuntimeError("isolated generation failure"))
    assert failed.state.value == "RETRYABLE"
    assert failed.response_payload is None
    assert failed.send_attempt_count == 0

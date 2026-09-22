"""Disposable-PostgreSQL certification for durable conversation bursts."""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.telegram_inbound import TelegramInboundPayload
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, row_factory=dict_row) as connection:
        yield connection


@pytest.fixture(scope="module", autouse=True)
def durable_schema():
    SchemaManagerService(connection_factory=connection_factory).reconcile_one(
        "20260918_142_ordinary_reply_conversation_bursts.sql"
    )


@pytest.fixture
def durable():
    scope = f"BURST_TEST_{uuid4()}"
    repository = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    service = OrdinaryChatReplyService(repository=repository, worker_id=f"worker-{uuid4()}")
    service.ACCOUNT_SCOPE = scope
    yield service, repository, scope
    with connection_factory() as connection:
        connection.execute(
            "DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s",
            (scope,),
        )


def inbound(chat, message_id, text, at):
    return TelegramInboundPayload(
        telegram_user_id=chat,
        telegram_chat_id=chat,
        message_text=text,
        message_id=message_id,
        received_at=at,
    )


def decision(at):
    return SimpleNamespace(
        available_at=at,
        category="NORMAL",
        diagnostics=lambda: {
            "category": "NORMAL",
            "availableAt": at.isoformat(),
            "quietPeriodSeconds": 8,
        },
    )


def _deferred_burst(service, *, chat, texts, now):
    rows = []
    for offset, text in enumerate(texts):
        operation, created = service.begin(inbound(chat, 100 + offset, text, now))
        assert created is True
        rows.append(service.defer_for_availability(
            operation, decision(now - timedelta(seconds=1)),
        ))
    return rows


@pytest.mark.parametrize("reaction", ["🫣", "ok", "haha"])
def test_direct_question_survives_reaction_and_preserves_union(durable, reaction):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    rows = _deferred_burst(
        service,
        chat=880000 + ord(reaction[0]),
        texts=["Hey honey, did I say something wrong?", reaction],
        now=now,
    )

    payloads = service.due_availability_payloads(now=now + timedelta(seconds=20))
    assert len(payloads) == 1
    assert payloads[0].message_id == 100
    assert [item["content"] for item in payloads[0].chat_history] == [reaction]

    current = [repository.get(row.operation_id) for row in rows]
    survivor = next(item for item in current if item.burst_role == "SURVIVOR")
    member = next(item for item in current if item.burst_role == "MEMBER")
    assert survivor.operation_id == rows[0].operation_id
    assert member.last_error == "availability_burst_coalesced"
    assert survivor.conversation_burst_id == member.conversation_burst_id
    assert survivor.burst_survivor_operation_id == survivor.operation_id
    assert survivor.burst_freshness_telegram_message_id == 101
    assert "ANSWER_DIRECT_QUESTION" in survivor.burst_obligations
    assert "RESPOND_TO_GREETING" in survivor.burst_obligations
    assert payloads[0].quality_correction_context["conversationBurst"][
        "freshnessMessageId"
    ] == 101

    result = repository.maintain_stranded_lifecycle(
        account_scope=service.ACCOUNT_SCOPE,
        creator_profile_id=None,
        fanvue_account_id=None,
        now=now + timedelta(minutes=10),
    )
    assert result["pendingSupersededFinalized"] == 0
    assert repository.get(survivor.operation_id).state.value == "PENDING_GENERATION"


def test_multiple_substantive_messages_union_obligations_deterministically(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    rows = _deferred_burst(
        service,
        chat=881100,
        texts=["Hi", "What did you mean?", "How much is that set?"],
        now=now,
    )
    payload = service.due_availability_payloads(now=now + timedelta(seconds=20))[0]
    current = [repository.get(row.operation_id) for row in rows]
    survivors = [item for item in current if item.burst_role == "SURVIVOR"]
    assert len(survivors) == 1
    assert payload.message_id == 102
    assert set(survivors[0].burst_obligations) >= {
        "RESPOND_TO_GREETING", "ANSWER_DIRECT_QUESTION", "HONOR_COMMERCIAL_REQUEST",
    }


def test_genuine_new_inbound_after_burst_still_supersedes(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    rows = _deferred_burst(
        service,
        chat=881200,
        texts=["Did I upset you?", "🫣"],
        now=now,
    )
    service.due_availability_payloads(now=now + timedelta(seconds=20))
    survivor = repository.get(rows[0].operation_id)
    newer, _ = service.begin(inbound(
        881200, 102, "Actually I need to ask something else", now + timedelta(minutes=1),
    ))
    assert newer.conversation_burst_id != survivor.conversation_burst_id
    result = repository.maintain_stranded_lifecycle(
        account_scope=service.ACCOUNT_SCOPE,
        creator_profile_id=None,
        fanvue_account_id=None,
        now=now + timedelta(minutes=2),
    )
    assert result["pendingSupersededFinalized"] == 1
    assert repository.get(survivor.operation_id).last_error == (
        "SUPERSEDED_PENDING_GENERATION"
    )


def test_archive_freshness_uses_durable_burst_watermark(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    rows = _deferred_burst(
        service, chat=881250,
        texts=["Did I upset you?", "just clarifying"], now=now,
    )
    service.due_availability_payloads(now=now + timedelta(seconds=20))
    survivor = next(repository.get(row.operation_id) for row in rows
                    if repository.get(row.operation_id).burst_role == "SURVIVOR")
    with connection_factory() as connection:
        for message_id, text in ((100, "Did I upset you?"), (101, "just clarifying")):
            connection.execute("""INSERT INTO telegram_private_inbound_messages(
              inbound_id,telegram_account_scope,telegram_user_id,telegram_chat_id,
              telegram_message_id,received_at,customer_text,has_media,media_types,
              ingestion_provenance,automation_state_at_receipt,reconciliation_state)
              VALUES(%s,%s,%s,%s,%s,%s,%s,FALSE,'[]'::jsonb,'TEST','ON','LIVE_HANDLED')
              ON CONFLICT DO NOTHING""", (
                uuid4(), service.ACCOUNT_SCOPE, 881250, 881250,
                message_id, now, text,
            ))
    result = repository.archive_freshness(survivor.operation_id)
    assert result["authoritativeForegroundInboundId"] == 101
    assert result["newestRelevantArchivedInboundId"] == 101
    assert result["archiveFreshnessSatisfied"] is True


def test_burst_processing_never_regresses_reconciliation_watermark(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    operation = _deferred_burst(
        service, chat=881275, texts=["Did I upset you?"], now=now,
    )[0]
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          burst_freshness_telegram_message_id=101,
          delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||
            jsonb_build_object('historicalSurvivorReconciliation',
              jsonb_build_object('freshnessMessageId',101))
          WHERE operation_id=%s""", (operation.operation_id,))

    payloads = service.due_availability_payloads(now=now + timedelta(seconds=20))
    assert len(payloads) == 1
    persisted = repository.get(operation.operation_id)
    assert persisted.burst_freshness_telegram_message_id == 101
    assert payloads[0].quality_correction_context["conversationBurst"][
        "freshnessMessageId"
    ] == 101


def test_monotonic_watermark_accepts_newer_and_is_idempotent(durable):
    service, repository, _ = durable
    now = datetime.now(timezone.utc)
    operation = _deferred_burst(
        service, chat=881276, texts=["Can you answer me?"], now=now,
    )[0]
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          burst_freshness_telegram_message_id=99 WHERE operation_id=%s""",
                           (operation.operation_id,))
    service.due_availability_payloads(now=now + timedelta(seconds=20))
    assert repository.get(operation.operation_id).burst_freshness_telegram_message_id == 100


def test_concurrent_burst_writers_cannot_regress_newer_watermark(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    operation = _deferred_burst(
        service, chat=881277, texts=["Are you there?"], now=now,
    )[0]
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          burst_freshness_telegram_message_id=101 WHERE operation_id=%s""",
                           (operation.operation_id,))

    def release():
        worker = OrdinaryChatReplyService(
            repository=OrdinaryChatReplyRepository(connection_factory=connection_factory),
            worker_id=f"monotonic-{uuid4()}",
        )
        worker.ACCOUNT_SCOPE = scope
        return worker.due_availability_payloads(now=now + timedelta(seconds=20))

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: release(), range(2)))
    assert repository.get(operation.operation_id).burst_freshness_telegram_message_id == 101


def _archive_inbound(service, *, chat, message_id, text, now):
    with connection_factory() as connection:
        connection.execute("""INSERT INTO telegram_private_inbound_messages(
          inbound_id,telegram_account_scope,telegram_user_id,telegram_chat_id,
          telegram_message_id,received_at,customer_text,has_media,media_types,
          ingestion_provenance,automation_state_at_receipt,reconciliation_state)
          VALUES(%s,%s,%s,%s,%s,%s,%s,FALSE,'[]'::jsonb,'TEST','ON','LIVE_HANDLED')
          ON CONFLICT DO NOTHING""", (
            uuid4(), service.ACCOUNT_SCOPE, chat, chat, message_id, now, text,
        ))


def _prepared_send_candidate(service, repository, *, chat, watermark):
    now = datetime.now(timezone.utc)
    operation = _deferred_burst(
        service, chat=chat, texts=["Did I upset you?"], now=now,
    )[0]
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          state='RETRYABLE',burst_freshness_telegram_message_id=%s,
          response_payload='{"response_text":"fresh reply"}'::jsonb,
          response_text='fresh reply',next_retry_at=NOW()-INTERVAL '1 second'
          WHERE operation_id=%s""", (watermark, operation.operation_id))
    return operation, now


def test_atomic_send_claim_accepts_incorporated_burst_member(durable):
    service, repository, _ = durable
    operation, now = _prepared_send_candidate(
        service, repository, chat=881278, watermark=101,
    )
    _archive_inbound(service, chat=881278, message_id=101,
                     text="incorporated clarification", now=now)
    claimed = repository.claim_send(operation.operation_id, owner="winner")
    assert claimed is not None
    assert claimed.state.value == "SENDING"
    assert claimed.generation_attempt_count == 0
    assert claimed.send_attempt_count == 1
    assert repository.claim_send(operation.operation_id, owner="loser") is None


def test_atomic_send_claim_blocks_genuinely_newer_inbound(durable):
    service, repository, _ = durable
    operation, now = _prepared_send_candidate(
        service, repository, chat=881279, watermark=101,
    )
    _archive_inbound(service, chat=881279, message_id=101,
                     text="incorporated clarification", now=now)
    _archive_inbound(service, chat=881279, message_id=102,
                     text="genuinely newer question", now=now + timedelta(seconds=1))
    assert repository.claim_send(operation.operation_id, owner="blocked") is None
    current = repository.get(operation.operation_id)
    assert current.state.value == "RETRYABLE"
    assert current.send_attempt_count == 0


def test_atomic_send_claim_without_burst_watermark_uses_original_inbound(durable):
    service, repository, _ = durable
    operation, now = _prepared_send_candidate(
        service, repository, chat=881280, watermark=None,
    )
    _archive_inbound(service, chat=881280, message_id=101,
                     text="newer than original", now=now)
    assert repository.claim_send(operation.operation_id, owner="blocked") is None


def test_concurrent_atomic_send_claim_has_one_winner(durable):
    service, repository, _ = durable
    operation, now = _prepared_send_candidate(
        service, repository, chat=881281, watermark=101,
    )
    _archive_inbound(service, chat=881281, message_id=101,
                     text="incorporated clarification", now=now)

    def claim(owner):
        return OrdinaryChatReplyRepository(
            connection_factory=connection_factory,
        ).claim_send(operation.operation_id, owner=owner)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("one", "two")))
    assert sum(item is not None for item in results) == 1
    current = repository.get(operation.operation_id)
    assert current.state.value == "SENDING"
    assert current.send_attempt_count == 1
    # Repeated processing cannot lower or otherwise perturb the settled value.
    service.due_availability_payloads(now=now + timedelta(seconds=20))
    assert repository.get(operation.operation_id).burst_freshness_telegram_message_id == 101


def test_concurrent_resolution_has_exactly_one_durable_survivor(durable):
    service, repository, scope = durable
    now = datetime.now(timezone.utc)
    rows = _deferred_burst(
        service,
        chat=881300,
        texts=["Hi", "Can you answer me?", "🫣"],
        now=now,
    )

    def release():
        worker = OrdinaryChatReplyService(
            repository=OrdinaryChatReplyRepository(connection_factory=connection_factory),
            worker_id=f"concurrent-{uuid4()}",
        )
        worker.ACCOUNT_SCOPE = scope
        return worker.due_availability_payloads(now=now + timedelta(seconds=20))

    with ThreadPoolExecutor(max_workers=2) as pool:
        batches = list(pool.map(lambda _: release(), range(2)))
    assert sum(len(batch) for batch in batches) == 1
    current = [repository.get(row.operation_id) for row in rows]
    assert sum(item.burst_role == "SURVIVOR" for item in current) == 1
    assert sum(item.state.value == "PENDING_GENERATION" for item in current) == 1
    assert sum(item.state.value == "SUPPRESSED" for item in current) == 2

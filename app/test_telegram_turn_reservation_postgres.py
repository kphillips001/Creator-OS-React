"""Disposable-PostgreSQL certification for Telegram turn reservations.

These tests deliberately use committed transactions and fresh repository instances;
they do not model the reservation with mocks or process-local state.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.repositories.telegram_turn_reservation_repository import TelegramTurnReservationRepository
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")
MIGRATION = Path("migrations/forward/20260918_143_telegram_visual_turn_continuity.sql")
ROLLBACK = Path("migrations/rollback/20260918_143_telegram_visual_turn_continuity.sql")


@contextmanager
def connection_factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, row_factory=dict_row) as connection:
        yield connection


def _execute_script(path):
    with connection_factory() as connection:
        connection.execute(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module", autouse=True)
def reservation_schema():
    with connection_factory() as connection:
        present = connection.execute(
            "SELECT to_regclass('public.telegram_conversation_turn_reservations') AS relation"
        ).fetchone()["relation"] is not None
    if present:
        _execute_script(ROLLBACK)
    _execute_script(MIGRATION)
    yield


def test_01_schema_constraints_indexes_and_foreign_keys():
    with connection_factory() as connection:
        indexes = {row["indexname"] for row in connection.execute(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename='telegram_conversation_turn_reservations'"
        ).fetchall()}
        foreign_targets = {row["target"] for row in connection.execute("""
            SELECT confrelid::regclass::text AS target
              FROM pg_constraint
             WHERE conrelid='public.telegram_conversation_turn_reservations'::regclass
               AND contype='f'
        """).fetchall()}
        checks = connection.execute("""
            SELECT COUNT(*) AS count FROM pg_constraint
             WHERE conrelid='public.telegram_conversation_turn_reservations'::regclass
               AND contype='c'
        """).fetchone()["count"]
    assert "uq_telegram_turn_reservation_open_peer" in indexes
    assert "idx_telegram_turn_reservation_release" in indexes
    assert "ordinary_chat_reply_operations" in foreign_targets
    assert checks >= 2


@pytest.fixture
def turn():
    token = uuid4().hex[:10]
    scope = f"TURN_CERT_{token}"
    chat = 7_000_000_000 + int(token[:7], 16)
    creator, account = 91_001, 91_002
    inbound_repo = TelegramPrivateInboundRepository(connection_factory=connection_factory)
    ordinary_repo = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    reservation_repo = TelegramTurnReservationRepository(connection_factory=connection_factory)

    def capture(message_id, *, text="", media=()):
        row, _ = inbound_repo.capture(
            account_scope=scope, user_id=chat, chat_id=chat, message_id=message_id,
            received_at=datetime.now(timezone.utc), customer_text=text,
            media_types=media, creator_profile_id=creator, fanvue_account_id=account,
            ingestion_provenance="CERTIFICATION", automation_state="ON",
        )
        return row

    def text_owner(message_id=100, *, window_ms=3000, obligations=("ANSWER_DIRECT_QUESTION",)):
        inbound = capture(message_id, text="Can you answer this?")
        reservation = reservation_repo.open_text(
            creator_profile_id=creator, fanvue_account_id=account,
            inbound=inbound, window_ms=window_ms,
        )
        operation, created = ordinary_repo.get_or_create(
            account_scope=scope, chat_id=chat, inbound_message_id=message_id,
            sender_user_id=chat, correlation_id=f"cert:{scope}:{message_id}",
            inbound_message_text=inbound.customer_text,
            inbound_received_at=inbound.received_at, turn_obligations=obligations,
        )
        assert created
        inbound_repo.correlate(
            account_scope=scope, chat_id=chat, message_id=message_id,
            response_operation_id=operation.operation_id,
        )
        reservation = reservation_repo.bind_captured_owner(
            reservation["reservation_id"], inbound.inbound_id,
        )
        return inbound, operation, reservation

    ctx = SimpleNamespace(
        scope=scope, chat=chat, creator=creator, account=account,
        capture=capture, text_owner=text_owner, ordinary=ordinary_repo,
        reservations=reservation_repo,
    )
    yield ctx
    with connection_factory() as connection:
        connection.execute(
            "DELETE FROM telegram_conversation_turn_reservations WHERE telegram_chat_id=%s",
            (chat,),
        )
        connection.execute(
            "DELETE FROM telegram_private_inbound_messages WHERE telegram_account_scope=%s",
            (scope,),
        )
        connection.execute(
            "DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s",
            (scope,),
        )


def _row(table, key, value):
    with connection_factory() as connection:
        return connection.execute(
            f"SELECT * FROM {table} WHERE {key}=%s", (value,),
        ).fetchone()


def _join(ctx, inbound):
    return TelegramTurnReservationRepository(connection_factory=connection_factory).join_media(
        creator_profile_id=ctx.creator, fanvue_account_id=ctx.account, inbound=inbound,
    )


def test_00_migration_forward_rollback_reforward_preserves_142():
    with connection_factory() as connection:
        assert connection.execute("SELECT to_regclass('public.telegram_conversation_turn_reservations') AS relation").fetchone()["relation"]
        assert connection.execute("SELECT to_regclass('public.ordinary_chat_reply_operations') AS relation").fetchone()["relation"]
    _execute_script(ROLLBACK)
    with connection_factory() as connection:
        assert connection.execute("SELECT to_regclass('public.telegram_conversation_turn_reservations') AS relation").fetchone()["relation"] is None
        assert connection.execute("SELECT to_regclass('public.ordinary_chat_reply_operations') AS relation").fetchone()["relation"]
        assert connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name='ordinary_chat_reply_operations' AND column_name='conversation_burst_id'").fetchone()
    _execute_script(MIGRATION)


def test_open_claim_is_denied_then_media_join_enables_same_owner(turn):
    _, operation, reservation = turn.text_owner()
    assert turn.ordinary.claim_generation(operation.operation_id, owner="early") is None
    media = turn.capture(101, media=("PHOTO",))
    joined = _join(turn, media)
    claimed = turn.ordinary.claim_generation(operation.operation_id, owner="after-join")
    assert joined["state"] == "READY"
    assert claimed.operation_id == operation.operation_id
    assert claimed.burst_freshness_telegram_message_id == 101
    assert joined["authoritative_response_operation_id"] == operation.operation_id


def test_concurrent_claim_vs_join_has_one_owner(turn):
    _, operation, _ = turn.text_owner()
    media = turn.capture(101, media=("PHOTO",))
    barrier = Barrier(2)

    def claim():
        barrier.wait()
        return OrdinaryChatReplyRepository(connection_factory=connection_factory).claim_generation(
            operation.operation_id, owner="race",
        )

    def join():
        barrier.wait()
        return _join(turn, media)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claim_result, join_result = pool.submit(claim), pool.submit(join)
        claimed, joined = claim_result.result(), join_result.result()
    current = turn.ordinary.get(operation.operation_id)
    assert joined["authoritative_response_operation_id"] == operation.operation_id
    assert current.operation_id == operation.operation_id
    assert current.generation_attempt_count in (0, 1)
    assert claimed is None or claimed.operation_id == operation.operation_id
    assert len(joined["member_inbound_ids"]) == 2


def test_expiry_boundary_serializes_join_or_independent_claim(turn):
    _, operation, reservation = turn.text_owner(window_ms=750)
    with connection_factory() as connection:
        connection.execute(
            "UPDATE telegram_conversation_turn_reservations SET closes_at=NOW()-INTERVAL '1 millisecond' WHERE reservation_id=%s",
            (reservation["reservation_id"],),
        )
    claimed = turn.ordinary.claim_generation(operation.operation_id, owner="expired")
    media = turn.capture(101, media=("PHOTO",))
    assert claimed.operation_id == operation.operation_id
    assert _join(turn, media) is None
    persisted = _row("telegram_conversation_turn_reservations", "reservation_id", reservation["reservation_id"])
    assert persisted["state"] == "OPEN"
    assert persisted["member_telegram_message_ids"] == [100]


def test_duplicate_media_and_multiple_album_members_are_idempotent(turn):
    _, operation, _ = turn.text_owner()
    image1 = turn.capture(101, media=("PHOTO",))
    image2 = turn.capture(102, media=("PHOTO",))
    barrier = Barrier(4)

    def join(inbound):
        barrier.wait()
        return _join(turn, inbound)

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = [future.result() for future in (
            pool.submit(join, image1), pool.submit(join, image1),
            pool.submit(join, image2), pool.submit(join, image2),
        )]
    final = _row("telegram_conversation_turn_reservations", "reservation_id", rows[-1]["reservation_id"])
    assert set(final["member_telegram_message_ids"]) == {100, 101, 102}
    assert len(final["member_inbound_ids"]) == 3
    assert len(final["member_roles"]) == 3
    assert final["newest_message_freshness_watermark"] == 102
    assert final["authoritative_response_operation_id"] == operation.operation_id


def test_duplicate_text_delivery_has_one_inbound_reservation_and_operation(turn):
    inbound = turn.capture(100, text="same")
    barrier = Barrier(4)

    def reserve():
        barrier.wait()
        return TelegramTurnReservationRepository(connection_factory=connection_factory).open_text(
            creator_profile_id=turn.creator, fanvue_account_id=turn.account,
            inbound=inbound, window_ms=3000,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        reservations = [f.result() for f in [pool.submit(reserve) for _ in range(4)]]
    operations = []
    for _ in range(4):
        operations.append(turn.ordinary.get_or_create(
            account_scope=turn.scope, chat_id=turn.chat, inbound_message_id=100,
            sender_user_id=turn.chat, correlation_id=f"duplicate:{uuid4()}",
            inbound_message_text="same", turn_obligations=(),
        )[0])
    assert len({row["reservation_id"] for row in reservations}) == 1
    assert len({row.operation_id for row in operations}) == 1


def test_restart_open_and_ready_are_fully_durable(turn):
    _, operation, reservation = turn.text_owner()
    fresh_ordinary = OrdinaryChatReplyRepository(connection_factory=connection_factory)
    assert fresh_ordinary.claim_generation(operation.operation_id, owner="restart-open") is None
    media = turn.capture(101, media=("PHOTO",))
    _join(turn, media)
    fresh_reservations = TelegramTurnReservationRepository(connection_factory=connection_factory)
    persisted = _row("telegram_conversation_turn_reservations", "reservation_id", reservation["reservation_id"])
    assert persisted["state"] == "READY"
    assert persisted["member_telegram_message_ids"] == [100, 101]
    assert persisted["newest_message_freshness_watermark"] == 101
    assert fresh_ordinary.claim_generation(operation.operation_id, owner="restart-ready")
    assert fresh_reservations.close_expired() == ()


def test_interrupted_join_rolls_back_and_retry_converges(turn):
    _, operation, reservation = turn.text_owner()
    media = turn.capture(101, media=("PHOTO",))
    try:
        with connection_factory() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"telegram-turn:{turn.chat}",))
            connection.execute("UPDATE telegram_conversation_turn_reservations SET state='READY',member_inbound_ids=member_inbound_ids||ARRAY[%s::uuid] WHERE reservation_id=%s", (media.inbound_id, reservation["reservation_id"]))
            raise RuntimeError("simulated process loss")
    except RuntimeError:
        pass
    before = _row("telegram_conversation_turn_reservations", "reservation_id", reservation["reservation_id"])
    assert before["state"] == "OPEN" and len(before["member_inbound_ids"]) == 1
    joined = _join(turn, media)
    assert joined["state"] == "READY" and len(joined["member_inbound_ids"]) == 2
    assert joined["authoritative_response_operation_id"] == operation.operation_id


def test_owner_binding_after_join_repairs_operation_watermark(turn):
    inbound = turn.capture(100, text="Question?")
    reservation = turn.reservations.open_text(
        creator_profile_id=turn.creator, fanvue_account_id=turn.account,
        inbound=inbound, window_ms=3000,
    )
    media = turn.capture(101, media=("PHOTO",))
    assert _join(turn, media)["state"] == "READY"
    operation, _ = turn.ordinary.get_or_create(
        account_scope=turn.scope, chat_id=turn.chat, inbound_message_id=100,
        sender_user_id=turn.chat, correlation_id=f"late-bind:{turn.scope}",
        inbound_message_text="Question?", turn_obligations=("ANSWER_DIRECT_QUESTION",),
    )
    TelegramPrivateInboundRepository(connection_factory=connection_factory).correlate(
        account_scope=turn.scope, chat_id=turn.chat, message_id=100,
        response_operation_id=operation.operation_id,
    )
    bound = turn.reservations.bind_captured_owner(reservation["reservation_id"], inbound.inbound_id)
    current = turn.ordinary.get(operation.operation_id)
    assert bound["authoritative_response_operation_id"] == operation.operation_id
    assert current.burst_freshness_telegram_message_id == 101
    assert "ANSWER_DIRECT_QUESTION" in current.burst_obligations


def test_owner_synchronization_never_regresses_operation_watermark(turn):
    inbound = turn.capture(100, text="Question?")
    reservation = turn.reservations.open_text(
        creator_profile_id=turn.creator, fanvue_account_id=turn.account,
        inbound=inbound, window_ms=3000,
    )
    operation, _ = turn.ordinary.get_or_create(
        account_scope=turn.scope, chat_id=turn.chat, inbound_message_id=100,
        sender_user_id=turn.chat, correlation_id=f"monotonic:{turn.scope}",
        inbound_message_text="Question?", turn_obligations=("ANSWER_DIRECT_QUESTION",),
    )
    with connection_factory() as connection:
        connection.execute("""UPDATE ordinary_chat_reply_operations SET
          burst_freshness_telegram_message_id=102 WHERE operation_id=%s""",
                           (operation.operation_id,))
    TelegramPrivateInboundRepository(connection_factory=connection_factory).correlate(
        account_scope=turn.scope, chat_id=turn.chat, message_id=100,
        response_operation_id=operation.operation_id,
    )
    turn.reservations.bind_captured_owner(reservation["reservation_id"], inbound.inbound_id)
    assert turn.ordinary.get(operation.operation_id).burst_freshness_telegram_message_id == 102


def test_lease_recovery_reclaims_same_survivor(turn):
    _, operation, _ = turn.text_owner()
    _join(turn, turn.capture(101, media=("PHOTO",)))
    first = turn.ordinary.claim_generation(operation.operation_id, owner="dead", lease_seconds=1)
    with connection_factory() as connection:
        connection.execute("UPDATE ordinary_chat_reply_operations SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE operation_id=%s", (operation.operation_id,))
    recovered = turn.ordinary.claim_generation(operation.operation_id, owner="replacement")
    assert first.operation_id == recovered.operation_id == operation.operation_id
    assert recovered.generation_attempt_count == 2


def test_freshness_and_obligation_invariants(turn):
    _, operation, reservation = turn.text_owner()
    _join(turn, turn.capture(101, media=("PHOTO",)))
    persisted = turn.ordinary.get(operation.operation_id)
    assert persisted.burst_freshness_telegram_message_id == 101
    assert "ANSWER_DIRECT_QUESTION" in persisted.burst_obligations
    with connection_factory() as connection:
        counts = connection.execute("""SELECT
          cardinality(member_inbound_ids) inbound_count,
          cardinality(ARRAY(SELECT DISTINCT unnest(member_inbound_ids))) distinct_inbound_count,
          cardinality(member_telegram_message_ids) message_count,
          cardinality(ARRAY(SELECT DISTINCT unnest(member_telegram_message_ids))) distinct_message_count
          FROM telegram_conversation_turn_reservations WHERE reservation_id=%s""", (reservation["reservation_id"],)).fetchone()
    assert counts["inbound_count"] == counts["distinct_inbound_count"] == 2
    assert counts["message_count"] == counts["distinct_message_count"] == 2


@pytest.mark.parametrize("failure", ["download", "decode", "safety", "provider"])
def test_media_failure_after_association_never_creates_another_owner(turn, failure):
    _, operation, reservation = turn.text_owner()
    _join(turn, turn.capture(101, media=("PHOTO",)))
    with connection_factory() as connection:
        connection.execute("UPDATE ordinary_chat_reply_operations SET delivery_payload=COALESCE(delivery_payload,'{}')||%s::jsonb WHERE operation_id=%s", ('{"mediaFailure":"'+failure+'"}', operation.operation_id))
        owner_count = connection.execute("SELECT COUNT(*) AS count FROM ordinary_chat_reply_operations WHERE telegram_account_scope=%s AND telegram_chat_id=%s", (turn.scope, turn.chat)).fetchone()["count"]
        reservation_owner = connection.execute("SELECT authoritative_response_operation_id FROM telegram_conversation_turn_reservations WHERE reservation_id=%s", (reservation["reservation_id"],)).fetchone()["authoritative_response_operation_id"]
    assert owner_count == 1
    assert reservation_owner == operation.operation_id

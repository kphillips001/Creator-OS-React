import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.services.schema_manager_service import SchemaManagerService
from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.repositories.ava_availability_session_repository import AvaAvailabilitySessionRepository
from app.models.ava_availability_session import AvaAvailabilityState
from app.testing.postgres_safety import require_current_telegram_test_schema

ROOT = Path(__file__).resolve().parents[1]
ROLLBACK = ROOT / "migrations/rollback/20260913_119_ava_availability_and_private_inbound_backlog.sql"
NAME = "20260913_119_ava_availability_and_private_inbound_backlog.sql"


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
def test_availability_and_backlog_forward_and_rollback():
    url = require_current_telegram_test_schema(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
    @contextmanager
    def factory():
        with connect(url, row_factory=dict_row) as connection: yield connection
    with connect(url, autocommit=True) as connection:
        if connection.execute("SELECT to_regclass('public.ava_availability_sessions')").fetchone()[0]:
            connection.execute(ROLLBACK.read_text())
        connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope='TEST_AVA'")
        connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))
    try:
        report = SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        assert NAME in report.migrations_applied
        with connect(url) as connection:
            assert connection.execute("SELECT to_regclass('public.ava_availability_sessions')").fetchone()[0]
            assert connection.execute("SELECT to_regclass('public.telegram_private_inbound_messages')").fetchone()[0]
        repository = TelegramPrivateInboundRepository(connection_factory=factory)
        at = __import__("datetime").datetime(2026, 9, 13, tzinfo=__import__("datetime").timezone.utc)
        sessions = AvaAvailabilitySessionRepository(connection_factory=factory)
        session = sessions.current_or_transition(account_scope="TEST_AVA", now=at,
            initial_state=lambda _: AvaAvailabilityState.BUSY,
            next_state=lambda *_: AvaAvailabilityState.ACTIVE,
            duration=lambda _state, instant: instant + __import__("datetime").timedelta(minutes=22),
            daypart=lambda _: "AFTERNOON")
        restarted = AvaAvailabilitySessionRepository(connection_factory=factory).current_or_transition(
            account_scope="TEST_AVA", now=at + __import__("datetime").timedelta(minutes=5),
            initial_state=lambda _: AvaAvailabilityState.AVAILABLE,
            next_state=lambda *_: AvaAvailabilityState.ACTIVE,
            duration=lambda _state, instant: instant + __import__("datetime").timedelta(minutes=22),
            daypart=lambda _: "AFTERNOON")
        assert restarted.session_id == session.session_id and restarted.state is AvaAvailabilityState.BUSY
        _, created = repository.capture(account_scope="TEST_AVA", user_id=991, chat_id=991,
            message_id=501, received_at=at, customer_text="Can you remember me?",
            automation_state="OFF")
        _, duplicate_created = repository.capture(account_scope="TEST_AVA", user_id=991, chat_id=991,
            message_id=501, received_at=at, customer_text="Can you remember me?",
            automation_state="OFF")
        assert created is True and duplicate_created is False
        rows, operation_id, stale = repository.reconcile(account_scope="TEST_AVA", chat_id=991,
            authoritative_message_id=501, outcome="RESPOND", reconciliation_id=__import__("uuid").uuid4())
        assert stale is True and rows == [] and operation_id is None
        rows, operation_id, stale = repository.reconcile(account_scope="TEST_AVA", chat_id=991,
            authoritative_message_id=501, outcome="RESPOND", reconciliation_id=__import__("uuid").uuid4(),
            expected_message_ids=(501,))
        assert len(rows) == 1 and operation_id is not None and stale is False
    finally:
        with connect(url, autocommit=True) as connection:
            if connection.execute("SELECT to_regclass('public.ava_availability_sessions')").fetchone()[0]:
                connection.execute(ROLLBACK.read_text())
            connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope='TEST_AVA'")
            connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))

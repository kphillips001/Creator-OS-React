import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.telegram_relationship_control_repository import TelegramRelationshipControlRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema


ROOT = Path(__file__).resolve().parents[1]
NAME = "20260913_128_relationship_ignore_control.sql"
ROLLBACK = ROOT / "migrations/rollback" / NAME


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
def test_ignore_migration_atomic_neutralization_restart_and_resume_boundary():
    url = require_current_telegram_test_schema(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
    @contextmanager
    def factory():
        with connect(url, row_factory=dict_row) as connection: yield connection
    manager = SchemaManagerService(connection_factory=factory)
    with connect(url, autocommit=True) as connection:
        has_controls = connection.execute("SELECT to_regclass('public.telegram_relationship_controls')").fetchone()[0]
        has_backlog = connection.execute("SELECT to_regclass('public.telegram_private_inbound_messages')").fetchone()[0]
    if has_controls is None:
        manager.reconcile_one("20260909_105_relationship_manual_control.sql")
        manager.reconcile_one("20260911_113_customer_automation_selling_controls.sql")
        manager.reconcile_one("20260913_120_customer_selling_permissions_default_on.sql")
    if has_backlog is None:
        manager.reconcile_one("20260913_119_ava_availability_and_private_inbound_backlog.sql")
    with connect(url, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS telegram_relationship_ignore_events")
        for column in ("resume_after_inbound_message_id","unignored_by","unignored_at",
                       "ignore_reason","ignored_by","ignored_at","ignore_version",
                       "communication_disposition"):
            connection.execute(f"ALTER TABLE telegram_relationship_controls DROP COLUMN IF EXISTS {column}")
        connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))
    try:
        assert NAME in manager.reconcile_one(NAME).migrations_applied
        with connect(url, row_factory=dict_row) as connection:
            creator = connection.execute("SELECT id FROM creator_profiles ORDER BY id LIMIT 1").fetchone()["id"]
            account = connection.execute("SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1").fetchone()["id"]
        scope = dict(creator_profile_id=creator, fanvue_account_id=account,
                     telegram_user_id=980000001, telegram_chat_id=980000001)
        replies = OrdinaryChatReplyRepository(connection_factory=factory)
        pending, _ = replies.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=scope["telegram_chat_id"], inbound_message_id=41,
            sender_user_id=scope["telegram_user_id"], correlation_id="ignore:pending",
            inbound_message_text="question")
        generated, _ = replies.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=scope["telegram_chat_id"], inbound_message_id=42,
            sender_user_id=scope["telegram_user_id"], correlation_id="ignore:generated",
            inbound_message_text="price?")
        with connect(url, autocommit=True) as connection:
            connection.execute("UPDATE ordinary_chat_reply_operations SET state='GENERATED',response_text='reply',response_payload='{}'::jsonb WHERE operation_id=%s", (generated.operation_id,))
        repository = TelegramRelationshipControlRepository(connection_factory=factory)
        ignored, changed, evidence = repository.set_ignored(**scope, ignored=True,
            changed_by="test", expected_control_version=0)
        assert changed and ignored.ignored and evidence["ordinary"] == 2
        assert replies.get(pending.operation_id).state.value == "SUPPRESSED"
        assert replies.get(generated.operation_id).state.value == "SUPPRESSED"
        duplicate, changed, evidence = repository.set_ignored(**scope, ignored=True,
            changed_by="test", expected_control_version=0)
        assert not changed and duplicate.ignore_version == 1 and evidence["ordinary"] == 0
        restarted = TelegramRelationshipControlRepository(connection_factory=factory)
        assert restarted.get(**scope).ignored
        active, changed, _ = restarted.set_ignored(**scope, ignored=False,
            changed_by="test", expected_control_version=ignored.control_version)
        assert changed and not active.ignored
        assert active.resume_after_inbound_message_id == 42
        assert replies.get(pending.operation_id).state.value == "SUPPRESSED"
        with connect(url, row_factory=dict_row) as connection:
            events = connection.execute("SELECT action FROM telegram_relationship_ignore_events WHERE telegram_user_id=%s ORDER BY ignore_version", (scope["telegram_user_id"],)).fetchall()
        assert [row["action"] for row in events] == ["IGNORED", "UNIGNORED"]
    finally:
        with connect(url, autocommit=True) as connection:
            connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'ignore:%'")
            connection.execute("DELETE FROM telegram_relationship_controls WHERE telegram_user_id=980000001")
            if connection.execute("SELECT to_regclass('public.telegram_relationship_ignore_events')").fetchone()[0]:
                connection.execute(ROLLBACK.read_text())
            connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))

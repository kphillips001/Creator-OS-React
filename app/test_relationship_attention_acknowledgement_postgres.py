import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.relationships_repository import RelationshipsRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema


NAME = "20260913_121_conversation_attention_acknowledgements.sql"
ROLLBACK = Path(__file__).resolve().parents[1] / "migrations/rollback" / NAME


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required")
def test_attention_acknowledgement_migration_and_idempotent_repository():
    url = require_current_telegram_test_schema(
        os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"),
    )

    @contextmanager
    def factory():
        with connect(url, row_factory=dict_row) as connection:
            yield connection

    with connect(url, autocommit=True) as connection:
        if connection.execute(
            "SELECT to_regclass('public.conversation_attention_acknowledgements')"
        ).fetchone()[0]:
            connection.execute(ROLLBACK.read_text(encoding="utf-8"))
        connection.execute(
            "DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,)
        )
    try:
        report = SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        assert NAME in report.migrations_applied
        with connect(url) as connection:
            ordinary_before = connection.execute(
                "SELECT COUNT(*) FROM ordinary_chat_reply_operations"
            ).fetchone()[0]
        repository = RelationshipsRepository(connection_factory=factory)
        values = dict(
            occurrence_id="opaque-occurrence", creator_profile_id=2,
            fanvue_account_id=2, telegram_user_id=7001,
            telegram_chat_id=7001, triggering_inbound_message_id=44,
            causal_operation_id=None, attention_reason="Operator review required.",
            predicate_version="CHAT_OPERATIONAL_STATUS_V1",
            acknowledged_by="TEST_OPERATOR",
        )
        first = repository.acknowledge_attention(**values)
        second = RelationshipsRepository(connection_factory=factory).acknowledge_attention(
            **values
        )
        assert first["acknowledgement_id"] == second["acknowledgement_id"]
        with connect(url) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM conversation_attention_acknowledgements"
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT COUNT(*) FROM ordinary_chat_reply_operations"
            ).fetchone()[0] == ordinary_before
    finally:
        with connect(url, autocommit=True) as connection:
            if connection.execute(
                "SELECT to_regclass('public.conversation_attention_acknowledgements')"
            ).fetchone()[0]:
                connection.execute(ROLLBACK.read_text(encoding="utf-8"))
            connection.execute(
                "DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,)
            )

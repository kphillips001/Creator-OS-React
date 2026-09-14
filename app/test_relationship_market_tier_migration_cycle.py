import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema


ROOT = Path(__file__).resolve().parents[1]
NAME = "20260913_125_relationship_market_tiers.sql"
ROLLBACK = ROOT / "migrations/rollback" / NAME


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL is required")
def test_market_tier_migration_cycle_isolation_history_and_restart():
    url = require_current_telegram_test_schema(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))

    @contextmanager
    def factory():
        with connect(url, row_factory=dict_row) as connection:
            yield connection

    with connect(url, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS telegram_relationship_market_tiers")
        connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))
    try:
        report = SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        assert NAME in report.migrations_applied
        with connect(url, row_factory=dict_row) as connection:
            creator = connection.execute("SELECT id FROM creator_profiles ORDER BY id LIMIT 1").fetchone()
            account = connection.execute("SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1").fetchone()
        assert creator and account
        base = dict(creator_profile_id=creator["id"], fanvue_account_id=account["id"],
                    telegram_user_id=910000001, telegram_chat_id=920000001)
        repository = RelationshipMarketTierRepository(connection_factory=factory)
        row, changed = repository.set(**base, market_tier="HIGH", changed_by="test")
        assert changed and row.version == 1
        other_chat = {**base, "telegram_chat_id": 920000002}
        other, _ = repository.set(**other_chat, market_tier="LOW", changed_by="test")
        assert other.market_tier.value == "LOW"
        restarted = RelationshipMarketTierRepository(connection_factory=factory)
        assert restarted.active(**base).market_tier.value == "HIGH"
        replacement, changed = restarted.set(**base, market_tier="MEDIUM", changed_by="test")
        assert changed and replacement.version == 2
        history = restarted.history(**base)
        assert len(history) == 2 and history[0].removed_at and history[0].replaced_by == replacement.market_tier_id
        assert restarted.active(**other_chat).market_tier.value == "LOW"
        restarted.remove(**base, removed_by="test")
        assert restarted.active(**base) is None and len(restarted.history(**base)) == 2
        with pytest.raises(Exception):
            restarted.set(**base, market_tier="VIP", changed_by="test")

        operations = OrdinaryChatReplyRepository(connection_factory=factory)
        older, _ = operations.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=930000001, inbound_message_id=1, sender_user_id=940000001,
            correlation_id="market-tier:older", inbound_message_text="older")
        latest, _ = operations.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=930000001, inbound_message_id=2, sender_user_id=940000001,
            correlation_id="market-tier:latest", inbound_message_text="latest")
        claimed, _ = operations.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=930000002, inbound_message_id=1, sender_user_id=940000002,
            correlation_id="market-tier:claimed", inbound_message_text="claimed")
        terminal, _ = operations.get_or_create(account_scope="AVA_TELETHON_PRIVATE",
            chat_id=930000003, inbound_message_id=1, sender_user_id=940000003,
            correlation_id="market-tier:terminal", inbound_message_text="terminal")
        with connect(url, autocommit=True) as connection:
            connection.execute("""UPDATE ordinary_chat_reply_operations SET
                state='RETRYABLE',last_error='availability_deferred',
                next_retry_at=NOW()+INTERVAL '1 hour'
                WHERE correlation_id LIKE 'market-tier:%'""")
            connection.execute("""UPDATE ordinary_chat_reply_operations SET
                claim_owner='worker',claimed_at=NOW()
                WHERE operation_id=%s""", (claimed.operation_id,))
            connection.execute("""UPDATE ordinary_chat_reply_operations SET
                state='TERMINAL_FAILED',next_retry_at=NULL
                WHERE operation_id=%s""", (terminal.operation_id,))
        advanced = restarted.advance_eligible(telegram_user_id=940000001,
            telegram_chat_id=930000001,
            available_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)+__import__("datetime").timedelta(minutes=5))
        assert advanced and advanced["operation_id"] == latest.operation_id
        assert operations.get(older.operation_id).next_retry_at is not None
        assert restarted.advance_eligible(telegram_user_id=940000002,
            telegram_chat_id=930000002,
            available_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)) is None
        assert restarted.advance_eligible(telegram_user_id=940000003,
            telegram_chat_id=930000003,
            available_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc)) is None
    finally:
        with connect(url, autocommit=True) as connection:
            connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE correlation_id LIKE 'market-tier:%'")
            if connection.execute("SELECT to_regclass('public.telegram_relationship_market_tiers')").fetchone()[0]:
                connection.execute(ROLLBACK.read_text())
            connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s", (NAME,))

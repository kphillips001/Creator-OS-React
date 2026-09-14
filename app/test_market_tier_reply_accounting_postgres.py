import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.market_tier_reply_accounting_repository import MarketTierReplyAccountingRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema


NAME="20260913_126_market_tier_confirmed_reply_accounting.sql"
ROLLBACK=Path(__file__).resolve().parents[1]/"migrations"/"rollback"/NAME


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL is required")
def test_confirmed_accounting_is_atomic_idempotent_scoped_and_restart_safe():
    url=require_current_telegram_test_schema(os.getenv("TEST_DATABASE_URL"),os.getenv("DATABASE_URL"))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as connection: yield connection
    with connect(url,autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS market_tier_confirmed_reply_events")
        connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))
    try:
        assert NAME in SchemaManagerService(connection_factory=factory).reconcile_one(NAME).migrations_applied
        with connect(url,row_factory=dict_row) as connection:
            creator=connection.execute("SELECT id FROM creator_profiles ORDER BY id LIMIT 1").fetchone()["id"]
            account=connection.execute("SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1").fetchone()["id"]
        repo=OrdinaryChatReplyRepository(connection_factory=factory)
        operations=[]
        for number in range(1,6):
            item,_=repo.get_or_create(account_scope="TEST_ACCOUNTING",chat_id=88001,
                inbound_message_id=number,sender_user_id=77001,
                correlation_id=f"accounting:{number}",inbound_message_text="hello")
            with connect(url,autocommit=True) as connection:
                connection.execute("UPDATE ordinary_chat_reply_operations SET state='SENDING',claim_owner='worker',send_attempt_count=1 WHERE operation_id=%s",(item.operation_id,))
            confirmed=repo.confirm_sent(item.operation_id,owner="worker",telegram_message_id=99000+number,
                creator_profile_id=creator,fanvue_account_id=account,
                resource_classification="ORDINARY_NONCOMMERCIAL")
            assert confirmed.state.value == "SENT_CONFIRMED"
            operations.append(item)
        assert repo.confirm_sent(operations[0].operation_id,owner="worker",telegram_message_id=99001,
            creator_profile_id=creator,fanvue_account_id=account,
            resource_classification="ORDINARY_NONCOMMERCIAL") is None
        accounting=MarketTierReplyAccountingRepository(connection_factory=factory)
        from datetime import datetime,timezone,timedelta
        start=datetime.now(timezone.utc)-timedelta(days=1);end=start+timedelta(days=2)
        scope=dict(creator_profile_id=creator,fanvue_account_id=account,
                   telegram_user_id=77001,telegram_chat_id=88001)
        assert accounting.count_between(**scope,business_day_start=start,business_day_end=end)==5
        assert MarketTierReplyAccountingRepository(connection_factory=factory).count_between(
            **scope,business_day_start=start,business_day_end=end)==5
        assert accounting.count_between(**{**scope,"telegram_chat_id":88002},
            business_day_start=start,business_day_end=end)==0

        duplicate,_=repo.get_or_create(account_scope="TEST_ACCOUNTING",chat_id=88003,
            inbound_message_id=1,sender_user_id=77003,correlation_id="accounting:concurrent",
            inbound_message_text="hello")
        with connect(url,autocommit=True) as connection:
            connection.execute("UPDATE ordinary_chat_reply_operations SET state='SENDING',claim_owner='worker',send_attempt_count=1 WHERE operation_id=%s",(duplicate.operation_id,))
        def confirm(_):
            return OrdinaryChatReplyRepository(connection_factory=factory).confirm_sent(
                duplicate.operation_id,owner="worker",telegram_message_id=99100,
                creator_profile_id=creator,fanvue_account_id=account,
                resource_classification="ORDINARY_NONCOMMERCIAL")
        with ThreadPoolExecutor(max_workers=2) as pool: list(pool.map(confirm,range(2)))
        assert accounting.count_between(creator_profile_id=creator,fanvue_account_id=account,
            telegram_user_id=77003,telegram_chat_id=88003,
            business_day_start=start,business_day_end=end)==1
    finally:
        with connect(url,autocommit=True) as connection:
            if connection.execute("SELECT to_regclass('public.market_tier_confirmed_reply_events')").fetchone()[0]: connection.execute(ROLLBACK.read_text())
            connection.execute("DELETE FROM ordinary_chat_reply_operations WHERE telegram_account_scope='TEST_ACCOUNTING'")
            connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))

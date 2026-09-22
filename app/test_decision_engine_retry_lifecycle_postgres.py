from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.testing.postgres_safety import require_isolated_test_database_url

TEST_DATABASE_URL=os.getenv("TEST_DATABASE_URL")
pytestmark=pytest.mark.skipif(not TEST_DATABASE_URL,reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    url=require_isolated_test_database_url(
      TEST_DATABASE_URL,os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"))
    with connect(url,row_factory=dict_row) as connection: yield connection


def fixture(*,due=True,attempts=1):
    user=970000+int(str(uuid4().int)[-5:])
    TelegramSalesProspectRepository(connection_factory=connection_factory).observe(
      creator_profile_id=2,fanvue_account_id=2,telegram_user_id=user,telegram_chat_id=user)
    repo=OrdinaryChatReplyRepository(connection_factory=connection_factory)
    operation,_=repo.get_or_create(account_scope="AVA_TELETHON_PRIVATE",chat_id=user,
      inbound_message_id=1,sender_user_id=user,correlation_id=f"engine-retry:{uuid4()}",
      inbound_message_text="Good morning",inbound_received_at=datetime.now(timezone.utc))
    with connection_factory() as c:
        c.execute("""update ordinary_chat_reply_operations set state='RETRYABLE',
          generation_attempt_count=%s,max_generation_attempts=5,send_attempt_count=0,
          next_retry_at=%s,last_error=
          'DECISION_ENGINE_EXCEPTION: Automatic reply could not be completed.'
          where operation_id=%s""",(attempts,datetime.now(timezone.utc)+(
            timedelta(minutes=-1) if due else timedelta(minutes=5)),operation.operation_id))
    return repo,operation,user


def cleanup(user):
    with connection_factory() as c:
        c.execute("delete from ordinary_chat_reply_operations where telegram_chat_id=%s",(user,))
        c.execute("""delete from telegram_sales_prospects where creator_profile_id=2
          and fanvue_account_id=2 and telegram_user_id=%s""",(user,))


def release():
    return OrdinaryChatReplyRepository(connection_factory=connection_factory).release_due_availability(
      account_scope="AVA_TELETHON_PRIVATE",now=datetime.now(timezone.utc),
      creator_profile_id=2,fanvue_account_id=2)


def test_concurrent_due_engine_retry_releases_same_operation_once():
    repo,operation,user=fixture()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            batches=list(pool.map(lambda _:release(),range(2)))
        released=[item for batch in batches for item in batch]
        assert [item.operation_id for item in released]==[operation.operation_id]
        current=repo.get(operation.operation_id)
        assert current.state.value=="PENDING_GENERATION"
        assert current.generation_attempt_count==1
    finally: cleanup(user)


def test_future_engine_retry_waits_and_exhausted_retry_terminalizes():
    repo,future,user=fixture(due=False)
    try:
        assert release()==[]
        assert repo.get(future.operation_id).state.value=="RETRYABLE"
    finally: cleanup(user)
    repo,exhausted,user=fixture(attempts=5)
    try:
        assert release()==[]
        current=repo.get(exhausted.operation_id)
        assert current.state.value=="TERMINAL_FAILED"
        assert current.next_retry_at is None
        assert current.last_error=="GENERATION_RETRY_BUDGET_EXHAUSTED"
    finally: cleanup(user)


def test_newer_inbound_invalidates_due_engine_retry_before_generation():
    repo,operation,user=fixture()
    try:
        repo.get_or_create(account_scope="AVA_TELETHON_PRIVATE",chat_id=user,
          inbound_message_id=2,sender_user_id=user,correlation_id=f"newer:{uuid4()}",
          inbound_message_text="Newer message",inbound_received_at=datetime.now(timezone.utc))
        assert release()==[]
        current=repo.get(operation.operation_id)
        assert current.state.value=="SUPPRESSED"
        assert current.last_error=="retry_invalidated_before_generation"
    finally: cleanup(user)

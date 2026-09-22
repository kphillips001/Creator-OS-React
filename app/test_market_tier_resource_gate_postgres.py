import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date,datetime,timezone
from pathlib import Path
import pytest
from psycopg import connect
from psycopg.rows import dict_row
from app.repositories.market_tier_resource_gate_repository import MarketTierResourceGateRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema

NAME='20260913_127_market_tier_daily_resource_gate.sql'
ROLLBACK=Path(__file__).resolve().parents[1]/'migrations'/'rollback'/NAME
@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_medium_budget_concurrent_stable_restart_and_new_day():
 url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
 @contextmanager
 def factory():
  with connect(url,row_factory=dict_row) as c:yield c
 creator=account=None
 try:
  assert SchemaManagerService(connection_factory=factory).reconcile_one(NAME).status=='PASS'
  with connect(url,row_factory=dict_row) as c:
   account=c.execute("INSERT INTO fanvue_accounts(account_name) VALUES('isolated market fixture') RETURNING id").fetchone()['id']
   creator=c.execute("INSERT INTO creator_profiles(fanvue_account_id,persona_name,display_name,age,gender,location) VALUES(%s,'Fixture','Fixture',25,'test','test') RETURNING id",(account,)).fetchone()['id']
  scope=dict(creator_profile_id=creator,fanvue_account_id=account,telegram_user_id=987001,telegram_chat_id=987001)
  def assign(value):return MarketTierResourceGateRepository(factory).medium_budget(**scope,business_date=date(2026,9,13),business_day_start=datetime(2026,9,13,5,tzinfo=timezone.utc),business_day_end=datetime(2026,9,14,5,tzinfo=timezone.utc),sampled_budget=value)['daily_reply_budget']
  with ThreadPoolExecutor(max_workers=6) as pool:values=list(pool.map(assign,range(5,11)))
  assert len(set(values))==1 and 5<=values[0]<=10
  assert assign(10)==values[0]
  tomorrow=MarketTierResourceGateRepository(factory).medium_budget(**scope,business_date=date(2026,9,14),business_day_start=datetime(2026,9,14,5,tzinfo=timezone.utc),business_day_end=datetime(2026,9,15,5,tzinfo=timezone.utc),sampled_budget=10)
  assert tomorrow['daily_reply_budget']==10
 finally:
  with connect(url,autocommit=True) as c:
   if creator is not None:
    c.execute('DELETE FROM market_tier_daily_budgets WHERE creator_profile_id=%s AND fanvue_account_id=%s',(creator,account))
    c.execute('DELETE FROM creator_profiles WHERE id=%s',(creator,))
   if account is not None:c.execute('DELETE FROM fanvue_accounts WHERE id=%s',(account,))
  # This concurrency test owns rows, not global schema/history. Subsequent
  # governance tests must see the same valid canonical migration graph.
  assert SchemaManagerService(connection_factory=factory).reconcile_one(NAME).status=='PASS'

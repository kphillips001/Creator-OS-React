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
 with connect(url,autocommit=True) as c:
  c.execute('DROP TABLE IF EXISTS market_tier_resource_policy_events');c.execute('DROP TABLE IF EXISTS market_tier_daily_budgets');c.execute('DELETE FROM schema_migrations WHERE migration_name=%s',(NAME,))
 try:
  SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
  with connect(url,row_factory=dict_row) as c:
   creator=c.execute('SELECT id FROM creator_profiles ORDER BY id LIMIT 1').fetchone()['id'];account=c.execute('SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1').fetchone()['id']
  scope=dict(creator_profile_id=creator,fanvue_account_id=account,telegram_user_id=987001,telegram_chat_id=987001)
  def assign(value):return MarketTierResourceGateRepository(factory).medium_budget(**scope,business_date=date(2026,9,13),business_day_start=datetime(2026,9,13,5,tzinfo=timezone.utc),business_day_end=datetime(2026,9,14,5,tzinfo=timezone.utc),sampled_budget=value)['daily_reply_budget']
  with ThreadPoolExecutor(max_workers=6) as pool:values=list(pool.map(assign,range(5,11)))
  assert len(set(values))==1 and 5<=values[0]<=10
  assert assign(10)==values[0]
  tomorrow=MarketTierResourceGateRepository(factory).medium_budget(**scope,business_date=date(2026,9,14),business_day_start=datetime(2026,9,14,5,tzinfo=timezone.utc),business_day_end=datetime(2026,9,15,5,tzinfo=timezone.utc),sampled_budget=10)
  assert tomorrow['daily_reply_budget']==10
 finally:
  with connect(url,autocommit=True) as c:
   c.execute(ROLLBACK.read_text());c.execute('DELETE FROM schema_migrations WHERE migration_name=%s',(NAME,))

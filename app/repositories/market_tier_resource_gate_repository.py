import json
from collections.abc import Mapping
from datetime import datetime
from uuid import uuid4
from app.database import get_db_connection


def durable_resource_gate_evidence(value):
 """Normalize only resource-gate JSON evidence at its persistence boundary."""
 if isinstance(value, datetime):
  if value.tzinfo is None or value.utcoffset() is None:
   raise ValueError("Market-tier resource-gate evidence datetime must be timezone-aware")
  return value.isoformat()
 if isinstance(value, Mapping):
  return {str(key):durable_resource_gate_evidence(item) for key,item in value.items()}
 if isinstance(value, (list,tuple)):
  return [durable_resource_gate_evidence(item) for item in value]
 if value is None or isinstance(value,(str,int,float,bool)):
  return value
 raise TypeError(
  f"Unsupported market-tier resource-gate evidence type: {type(value).__name__}")

class MarketTierResourceGateRepository:
 def __init__(self,connection_factory=get_db_connection): self.connection_factory=connection_factory
 def medium_budget(self,*,business_date,business_day_start,business_day_end,sampled_budget,**scope):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""INSERT INTO market_tier_daily_budgets(budget_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,business_date,market_tier,daily_reply_budget,business_day_start,business_day_end)
    VALUES(%s,%s,%s,%s,%s,%s,'MEDIUM',%s,%s,%s) ON CONFLICT(creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,business_date)
    DO UPDATE SET business_date=EXCLUDED.business_date RETURNING *,(xmax=0) AS created""",(uuid4(),scope['creator_profile_id'],scope['fanvue_account_id'],scope['telegram_user_id'],scope['telegram_chat_id'],business_date,sampled_budget,business_day_start,business_day_end));return dict(q.fetchone())
 def read_medium_budget(self,*,business_date,**scope):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT * FROM market_tier_daily_budgets
    WHERE creator_profile_id=%s AND fanvue_account_id=%s
      AND telegram_user_id=%s AND telegram_chat_id=%s
      AND business_date=%s AND market_tier='MEDIUM'""",
    (scope['creator_profile_id'],scope['fanvue_account_id'],scope['telegram_user_id'],scope['telegram_chat_id'],business_date))
   row=q.fetchone();return dict(row) if row else None
 def event(self,*,idempotency_key,event_type,operation_id,evidence,**scope):
  durable_evidence=durable_resource_gate_evidence(evidence)
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""INSERT INTO market_tier_resource_policy_events(event_id,idempotency_key,operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,event_type,evidence)
    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(idempotency_key) DO NOTHING RETURNING *""",(uuid4(),idempotency_key,operation_id,scope['creator_profile_id'],scope['fanvue_account_id'],scope['telegram_user_id'],scope['telegram_chat_id'],event_type,json.dumps(durable_evidence)));row=q.fetchone();return dict(row) if row else None
 def latest_limited(self,**scope):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT * FROM ordinary_chat_reply_operations o WHERE o.telegram_account_scope='AVA_TELETHON_PRIVATE' AND o.telegram_chat_id=%s AND o.inbound_sender_telegram_user_id=%s AND o.state='SUPPRESSED' AND o.last_error IN ('MEDIUM_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED','LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED') AND o.response_payload IS NULL AND o.generation_attempt_count=0 AND o.send_attempt_count=0 AND o.outbound_telegram_message_id IS NULL AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations n WHERE n.telegram_account_scope=o.telegram_account_scope AND n.telegram_chat_id=o.telegram_chat_id AND n.inbound_telegram_message_id>o.inbound_telegram_message_id) ORDER BY o.inbound_telegram_message_id DESC LIMIT 1""",(scope['telegram_chat_id'],scope['telegram_user_id']));row=q.fetchone();return dict(row) if row else None
 def release(self,operation_id,available_at):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""UPDATE ordinary_chat_reply_operations SET state='RETRYABLE',last_error='availability_deferred',next_retry_at=%s,updated_at=NOW() WHERE operation_id=%s AND state='SUPPRESSED' AND last_error IN ('MEDIUM_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED','LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED') AND response_payload IS NULL AND generation_attempt_count=0 AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL RETURNING *""",(available_at,operation_id));row=q.fetchone();return dict(row) if row else None

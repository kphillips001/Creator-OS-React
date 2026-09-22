import hashlib, os, sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import psycopg
from psycopg.rows import dict_row
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[1]; env=dotenv_values(ROOT/'.env'); lab=dotenv_values(ROOT/'.env.session5.local')
sys.path.insert(0,str(ROOT))
prod=str(env['DATABASE_URL']); name=str(lab['CREATOR_OS_SCENARIO_LAB_DATABASE_NAME']); url=prod.rsplit('/',1)[0]+'/'+name
assert name not in {'fanvue_chatbot','postgres'} and url!=prod
factory=lambda:psycopg.connect(url,row_factory=dict_row)
forward=(ROOT/'migrations/forward/20260914_135_active_offer_follow_through.sql').read_text()
rollback=(ROOT/'migrations/rollback/20260914_135_active_offer_follow_through.sql').read_text()
checksum=hashlib.sha256(forward.encode()).hexdigest()
def apply():
 with factory() as c,c.cursor() as q:
  q.execute(forward);q.execute("DELETE FROM schema_migrations WHERE migration_name=%s",('20260914_135_active_offer_follow_through.sql',));q.execute("INSERT INTO schema_migrations(migration_name,checksum) VALUES(%s,%s)",('20260914_135_active_offer_follow_through.sql',checksum))
def drop():
 with factory() as c,c.cursor() as q:q.execute(rollback);q.execute("DELETE FROM schema_migrations WHERE migration_name=%s",('20260914_135_active_offer_follow_through.sql',))
drop();apply()
with factory() as c,c.cursor() as q:
 q.execute("select current_database(),version()");print('environment',q.fetchone())
 q.execute("select column_name from information_schema.columns where table_name='active_offer_follow_through_events'");cols={r['column_name'] for r in q.fetchall()};assert {'event_id','purchase_intent_id','operation_id','delivery_state','confirmed_at','outbound_telegram_message_id'}<=cols
drop()
with factory() as c,c.cursor() as q:q.execute("select to_regclass('public.active_offer_follow_through_events')");assert q.fetchone()['to_regclass'] is None
apply()
from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
repo=ActiveOfferFollowThroughRepository(connection_factory=factory); intents=PurchaseIntentRepository(connection_factory=factory)
newid=uuid4(); correlation=uuid4(); now=datetime.now(timezone.utc); test_user=8_000_000_000+(newid.int%900_000_000)
with factory() as c,c.cursor() as q:
 q.execute("""INSERT INTO purchase_intents SELECT (jsonb_populate_record(NULL::purchase_intents,to_jsonb(p)||jsonb_build_object('purchase_intent_id',%s::text,'correlation_id',%s::text,'provider_resource_id',%s::text,'telegram_user_id',%s,'telegram_chat_id',%s,'status','PRESENTED','presented_at',%s,'created_at',%s,'updated_at',%s,'expires_at',%s,'purchased_at',NULL,'provider_transaction_order_id',NULL,'provider_payment_id',NULL,'provider_event_id',NULL))).* FROM purchase_intents p LIMIT 1""",(str(newid),str(correlation),'phase1-'+str(newid),test_user,test_user,now-timedelta(hours=25),now-timedelta(hours=25),now,now+timedelta(days=1)))
intent=intents.get(newid); assert intent
texts=('I had a long day at work and wanted to tell you about it','What have you been doing this afternoon?','I really enjoyed our conversation about music yesterday','Tell me what you think about my weekend plans','😘','duplicate/stale fragment')
with factory() as c,c.cursor() as q:
 for i,text in enumerate(texts,1):
  q.execute("""INSERT INTO ordinary_chat_reply_operations(operation_id,telegram_account_scope,telegram_chat_id,inbound_telegram_message_id,inbound_sender_telegram_user_id,correlation_id,inbound_message_text,inbound_received_at,state)
   VALUES(%s,'AVA_TELETHON_PRIVATE',%s,%s,%s,%s,%s,%s,%s)""",(uuid4(),test_user,90_000_000+i,test_user,'phase1:'+str(newid)+':'+str(i),text,now-timedelta(hours=1)+timedelta(seconds=i),'SUPPRESSED' if i==6 else 'PENDING_GENERATION'))
from app.services.active_offer_meaningful_turn_service import ActiveOfferMeaningfulTurnService
p1=ActiveOfferMeaningfulTurnService(operations=__import__('app.repositories.ordinary_chat_reply_repository',fromlist=['OrdinaryChatReplyRepository']).OrdinaryChatReplyRepository(connection_factory=factory)).project(intent=intent)
p2=ActiveOfferMeaningfulTurnService(operations=__import__('app.repositories.ordinary_chat_reply_repository',fromlist=['OrdinaryChatReplyRepository']).OrdinaryChatReplyRepository(connection_factory=factory)).project(intent=intent)
assert p1['meaningful_turns_since_presentation']==4 and p1['included_message_ids']==p2['included_message_ids']
def attempt(op): return repo.reserve(intent=intent,reason='TIMED',eligible_at=now,operation_id=op,now=now)
ops=(uuid4(),uuid4())
with ThreadPoolExecutor(2) as ex: results=list(ex.map(attempt,ops))
assert sum(r is not None for r in results)==1
winner=ops[0] if results[0] else ops[1]; loser=ops[1] if results[0] else ops[0]
provider_calls=0
try:
 provider_calls+=1; raise RuntimeError('controlled provider failure')
except RuntimeError: pass
assert repo.reserve(intent=intent,reason='TIMED',eligible_at=now,operation_id=winner,now=now) is not None
assert repo.reserve(intent=intent,reason='TIMED',eligible_at=now,operation_id=uuid4(),now=now) is None
with factory() as c,c.cursor() as q:
 q.execute("select count(*) n from active_offer_follow_through_events where purchase_intent_id=%s",(newid,));assert q.fetchone()['n']==1
 q.execute("update active_offer_follow_through_events set delivery_state='SENT_CONFIRMED',confirmed_at=%s,outbound_telegram_message_id=999 where operation_id=%s",(now,winner))
 post_id=99_000_000+(newid.int%800_000)
 q.execute("""INSERT INTO ordinary_chat_reply_operations(operation_id,telegram_account_scope,telegram_chat_id,inbound_telegram_message_id,inbound_sender_telegram_user_id,correlation_id,inbound_message_text,inbound_received_at,state) VALUES(%s,'AVA_TELETHON_PRIVATE',%s,%s,%s,%s,%s,%s,'PENDING_GENERATION') RETURNING operation_id""",(uuid4(),test_user,post_id,test_user,'post-nudge:'+str(newid),'I wanted to continue our ordinary conversation about my afternoon',now+timedelta(minutes=1)));post_operation=q.fetchone()['operation_id']
from app.services.post_nudge_nonconversion_service import PostNudgeNonconversionService
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
observer=PostNudgeNonconversionService(ledger=repo,intents=intents)
post=OrdinaryChatReplyRepository(connection_factory=factory).get(post_operation)
assert len(observer.observe(post,creator_profile_id=intent.creator_profile_id,fanvue_account_id=intent.fanvue_account_id))==1
assert repo.relationship_nonconversion(creator_profile_id=intent.creator_profile_id,fanvue_account_id=intent.fanvue_account_id,telegram_user_id=test_user,telegram_chat_id=test_user)['nonconversion_count']==1
assert repo.reserve(intent=intent,reason='TIMED',eligible_at=now,operation_id=uuid4(),now=now+timedelta(minutes=1)) is None
assert repo.reserve(intent=intent,reason='CONTEXTUAL',eligible_at=now,operation_id=uuid4(),now=now+timedelta(minutes=1),direct=True) is not None
with factory() as c,c.cursor() as q:q.execute("update purchase_intents set status='PURCHASED',purchased_at=%s where purchase_intent_id=%s",(now,newid))
assert repo.validate_before_generation(winner) is None
print('single_winner',str(winner),'loser',str(loser),'provider_calls',provider_calls)
print('provider_failure_retry_same_authorization','PASS')
print('post_nudge_nonconversion_observation','PASS')
print('migration_cycle','forward rollback re-forward PASS','cooldown','PASS','settlement_recheck','PASS')
print('restart_meaningful_turns',p2['meaningful_turns_since_presentation'],'PASS')

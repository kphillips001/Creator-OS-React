from uuid import uuid4
from types import SimpleNamespace as NS
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from test_canonical_evergreen_unlock import offer,canonical_db
from test_evergreen_checkout import database
from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
from app.repositories.purchase_intent_repository import PurchaseIntentRepository


def values(o,anchor=7091):
 return dict(correlation_id=str(uuid4()),creator_profile_id=901,fanvue_account_id=901,
 conversation_thread_id=None,fanvue_user_id=None,telegram_chat_id=99001,
 inbound_telegram_message_id=anchor,purchase_intent_id=o.root,commercial_offering_id=o.product,
 commercial_publication_id=o.publication,response_text='Controlled offer test',delivery_payload={})

def manual(o,state='SENDING'):
 op=uuid4()
 with o.db() as c:
  c.execute("INSERT INTO telegram_manual_offer_operations(operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,commercial_offering_id,commercial_publication_id,idempotency_key,message_text,request_sha256,relationship_control_version,state,purchase_intent_id) VALUES(%s,901,901,99001,99001,%s,%s,%s,'Controlled offer test',%s,1,%s,%s)",(op,o.product,o.publication,str(op),'a'*64,state,o.root))
 return op

def prepared(o,op,correlation=None):
 with o.db() as c:intent=PurchaseIntentRepository._intent(c.execute('SELECT * FROM purchase_intents WHERE purchase_intent_id=%s',(o.root,)).fetchone())
 result=NS(correlation_id=correlation or uuid4(),response_text='Controlled offer test',diagnostic_metadata={'conversation_thread_id':None,'conversation_fanvue_account_id':901,'conversation_fanvue_user_id':None},delivery_payload={})
 return TelegramSalesDeliveryService(repository=TelegramSalesDeliveryRepository(o.db)).prepare_operator_offer(intent=intent,result=result,payload=NS(telegram_chat_id=99001,message_id=7091),manual_operation_id=op)

def test_first_inbound_second_conflict_new_inbound(offer):
 o=offer;r=TelegramSalesDeliveryRepository(o.db)
 old,_=r.get_or_create(**values(o))
 with pytest.raises(psycopg.errors.UniqueViolation):r.get_or_create(**values(o))
 second,_=r.get_or_create(**values(o,7092))
 assert old.operation_id!=second.operation_id
 assert r.get_by_correlation(old.correlation_id)==old

def test_operator_uses_operation_not_consumed_inbound(offer):
 o=offer;r=TelegramSalesDeliveryRepository(o.db);old,_=r.get_or_create(**values(o));op=manual(o)
 new,created=prepared(o,op)
 assert created and new.inbound_telegram_message_id is None and new.manual_offer_operation_id==op
 assert new.delivery_payload['metadata']['delivery_anchor']=={'type':'MANUAL_OFFER','manual_operation_id':str(op),'context_inbound_message_id':7091}
 assert r.get_by_correlation(old.correlation_id)==old

@pytest.mark.parametrize('state',['FAILED','AMBIGUOUS','CONFIRMED','PREPARED'])
def test_terminal_or_unclaimed_manual_authority_rejected(offer,state):
 with pytest.raises(ValueError):prepared(offer,manual(offer,state))

def test_restart_and_double_prepare_single_owner(offer):
 op=manual(offer);key=uuid4();first,created=prepared(offer,op,key)
 second,created_again=prepared(offer,op,key)
 assert first==second and created and not created_again
 with pytest.raises(psycopg.errors.UniqueViolation):prepared(offer,op)

def test_concurrent_same_operator_click_single_row_and_claim(offer):
 op=manual(offer);key=uuid4()
 with ThreadPoolExecutor(2) as pool:rows=list(pool.map(lambda _:prepared(offer,op,key),range(2)))
 assert rows[0][0].operation_id==rows[1][0].operation_id
 r=TelegramSalesDeliveryRepository(offer.db)
 with ThreadPoolExecutor(2) as pool:claims=list(pool.map(lambda _:r.claim_created(rows[0][0].operation_id),range(2)))
 assert sum(x is not None for x in claims)==1

def test_distinct_manual_operations_distinct_anchors(offer):
 ops=[manual(offer),manual(offer)]
 with ThreadPoolExecutor(2) as pool:rows=list(pool.map(lambda op:prepared(offer,op),ops))
 assert rows[0][0].operation_id!=rows[1][0].operation_id

@pytest.mark.parametrize('change',[{'inbound_telegram_message_id':None}, {'manual_offer_operation_id':uuid4()}, {'inbound_telegram_message_id':None,'manual_offer_operation_id':uuid4()}])
def test_missing_dual_or_fabricated_authority_rejected(offer,change):
 with pytest.raises(psycopg.Error):TelegramSalesDeliveryRepository(offer.db).get_or_create(**{**values(offer),**change})

def test_history_anchor_cannot_be_reassigned(offer):
 row,_=TelegramSalesDeliveryRepository(offer.db).get_or_create(**values(offer))
 with pytest.raises(psycopg.Error):
  with offer.db() as c:c.execute('UPDATE telegram_sales_delivery_operations SET inbound_telegram_message_id=7092 WHERE operation_id=%s',(row.operation_id,))

def test_ambiguous_claim_never_sent_twice(offer):
 row,_=prepared(offer,manual(offer));s=TelegramSalesDeliveryService(repository=TelegramSalesDeliveryRepository(offer.db))
 row=s.claim(row);assert row is not None
 s.failed(row,TimeoutError('synthetic lost acknowledgement'))
 row=s.repository.get_by_correlation(row.correlation_id)
 assert row.state.value=='AMBIGUOUS' and s.claim(row) is None

def test_schema_certifies_anchor_guard(offer):
 from app.services.schema_manager_service import SchemaManagerService
 from pathlib import Path
 service=SchemaManagerService(migration_dir=Path('migrations/forward'))
 with offer.db() as c:assert service._migration_schema_already_present(c,'20260921_152_manual_offer_delivery_anchor.sql')


def test_concurrent_distinct_operator_requests_only_one_reservation(offer):
 from app.repositories.telegram_manual_offer_repository import TelegramManualOfferRepository
 o=offer;r=TelegramManualOfferRepository(o.db)
 context=dict(creator_profile_id=901,fanvue_account_id=901,telegram_user_id=99001,telegram_chat_id=99001,conversation_thread_id=None)
 product=dict(offering_id=o.product,publication_id=o.publication,price_minor=999,currency='USD')
 def reserve(_):
  try:return r.reserve(context=context,offering=product,business_connection_id=None,idempotency_key=str(uuid4()),message_text='Controlled offer test',expected_control_version=1)
  except ValueError:return None
 with ThreadPoolExecutor(2) as pool:results=list(pool.map(reserve,range(2)))
 assert sum(x is not None for x in results)==1

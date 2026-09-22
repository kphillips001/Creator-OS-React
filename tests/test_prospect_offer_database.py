from pathlib import Path
import pytest
from test_ordinary_generation_budget import connection

def test_certify_migration_and_inspect_fixture_support():
    from app.services.schema_manager_service import SchemaManagerService
    report=SchemaManagerService(connection_factory=connection).reconcile_one('20260921_150_manual_prospect_offers.sql')
    print('SCHEMA',report.status,report.drift)
    with connection() as c:
        cols=c.execute("SELECT table_name,column_name,is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('telegram_manual_offer_operations','telegram_sales_delivery_operations') AND column_name IN ('conversation_thread_id','local_fanvue_user_id','fanvue_user_id','telegram_identity_mapping_id','business_connection_id')").fetchall()
        assert all(x['is_nullable']=='YES' for x in cols)
        print('FIXTURE_SUPPORT', {t:c.execute('SELECT count(*) n FROM '+t).fetchone()['n'] for t in ('creator_profiles','fanvue_accounts','commercial_offerings','commercial_publications')})

from contextlib import contextmanager
from types import SimpleNamespace as NS
from uuid import uuid4
from datetime import datetime,timedelta,timezone
from app.repositories.telegram_manual_offer_repository import TelegramManualOfferRepository
from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
from test_prospect_manual_offers import service,Controls,reachable
from app.services.relationship_manual_offer_service import RelationshipManualOfferError

@pytest.mark.parametrize('outcome',['ok','unknown','ack_persistence_failure'])
@pytest.mark.parametrize('route',['business','telethon'])
def test_real_postgres_prospect_offer_exactly_once_and_immutable_history(outcome,route):
    with connection() as c:
        @contextmanager
        def same():yield c
        try:
            creator=c.execute('SELECT id FROM creator_profiles ORDER BY id LIMIT 1').fetchone()['id']
            account=c.execute('SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1').fetchone()['id']
            offering=c.execute("SELECT o.offering_id,o.hero_asset_id,o.creator_profile_id,p.publication_id FROM commercial_offerings o JOIN commercial_publications p ON p.commercial_offering_id=o.offering_id WHERE p.provider='FANVUE' ORDER BY o.created_at LIMIT 1").fetchone()
            creator=offering['creator_profile_id']
            publication=offering['publication_id']
            user=uuid4().int%100000000000+100000000000
            context=dict(creator_profile_id=creator,fanvue_account_id=account,telegram_user_id=user,telegram_chat_id=user,
                telegram_identity_mapping_id=None,local_fanvue_user_id=None,conversation_thread_id=None,external_fanvue_user_uuid=None,latest_inbound_telegram_message_id=1)
            c.execute("""INSERT INTO telegram_relationship_controls(relationship_control_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,mode,control_version,changed_by)
                VALUES(%s,%s,%s,%s,%s,'HUMAN_OPERATOR',9,'SANITIZED_TEST')""",(uuid4(),creator,account,user,user))
            intents=PurchaseIntentService(repository=PurchaseIntentRepository(connection_factory=same),
                commercial_eligibility=NS(require_offering_id=lambda *a,**k:None),telegram_identity_repository=NS(get_by_telegram_user_id=lambda _:None),learning_service=NS(observe_purchase_intent=lambda *a,**k:None),photoshoot_lifecycle_service=NS(record_presentation=lambda _:None))
            values=dict(creator_profile_id=creator,fanvue_account_id=account,telegram_identity_mapping_id=None,telegram_user_id=user,telegram_chat_id=user,
                external_fanvue_user_uuid=None,commercial_offering_id=offering['offering_id'],commercial_publication_id=publication,provider='FANVUE',provider_resource_id='sanitized-product',delivery_url='https://example.test/current-product',
                expected_price_minor=999,expected_currency='USD',expires_at=datetime.now(timezone.utc)+timedelta(hours=1),correlation_id=uuid4(),conversation_id='sanitized',created_metadata={})
            old=intents.create_before_presentation(**values)
            c.execute("UPDATE purchase_intents SET status='EXPIRED',created_at=now()-interval '2 hours',expires_at=now()-interval '1 hour' WHERE purchase_intent_id=%s",(old.purchase_intent_id,))
            before=c.execute('SELECT md5(to_jsonb(p)::text) digest FROM purchase_intents p WHERE purchase_intent_id=%s',(old.purchase_intent_id,)).fetchone()['digest']
            operations=TelegramManualOfferRepository(same);sales=TelegramSalesDeliveryRepository(same)
            if outcome=='ack_persistence_failure':
                original=sales.record_provider_evidence
                def record(id,evidence):
                    if evidence.get('accepted'):raise RuntimeError('simulated persistence failure')
                    return original(id,evidence)
                sales.record_provider_evidence=record
            deliveries=TelegramSalesDeliveryService(repository=sales,purchase_intent_service=intents)
            calls=[]
            def sender(**kw):
                calls.append(kw)
                if outcome=='unknown':raise TimeoutError('simulated provider ambiguity')
                return NS(id=1234)
            product=dict(offering,publication_id=publication,title='Sanitized kitchen photo',description='',offering_type='SINGLE_IMAGE',price_minor=999,currency='USD',external_product_id='current-product',delivery_url='https://example.test/current-product')
            s=service(operations=operations,intents=intents,deliveries=deliveries,fulfillment=NS(list_fulfillable=lambda **_:([product],1,1)),
                unlocks=NS(issue=lambda intent:(None,'https://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA')),transport=NS(prepare_delivery=reachable,BUTTON_LABEL='Unlock',send_asset=sender))
            if route=='telethon':
                from test_capability_prospect_offers import PrivateSender
                private=PrivateSender()
                async def async_send(**kw):return sender(**kw)
                private.send_asset=async_send
                s.runtime_transport=private
                s._select_transport=lambda *_:None
                def unavailable(**_):raise ValueError('No Business peer')
                s.transport.prepare_delivery=unavailable
            args=dict(context=context,offering_id=offering['offering_id'],expected_control_version=9,business_connection_id=None,idempotency_key='sanitized-one-request',message_text='Picked this for you')
            execute=lambda:s.send(**args)
            if route=='telethon':
                import asyncio
                queued=operations.reserve(context=context,offering=product,business_connection_id=None,
                    idempotency_key=args['idempotency_key'],message_text=args['message_text'],expected_control_version=9,queued=True)
                assert queued['state']=='PREPARED' and queued['send_attempt_count']==0
                assert any(p['operation_id']==queued['operation_id'] for p in operations.pending_private_dispatches())
                duplicate=operations.reserve(context=context,offering=product,business_connection_id=None,
                    idempotency_key=args['idempotency_key'],message_text=args['message_text'],expected_control_version=9,queued=True)
                assert duplicate['operation_id']==queued['operation_id']
                execute=lambda:asyncio.run(s._execute(**args,reserved=queued))
            if outcome=='ok':
                result=execute();assert result['state']=='CONFIRMED'
                assert s.send(**args)['operation_id']==result['operation_id']
            else:
                with pytest.raises(RelationshipManualOfferError):execute()
                with pytest.raises(RelationshipManualOfferError):s.send(**args)
                result=operations.by_key(context=context,idempotency_key=args['idempotency_key'])
                assert result['state']=='AMBIGUOUS'
            assert len(calls)==1 and result['send_attempt_count']==1
            assert result['telegram_identity_mapping_id'] is None and result['local_fanvue_user_id'] is None
            assert result['purchase_intent_id']!=old.purchase_intent_id
            delivery=sales.get_by_purchase_intent(result['purchase_intent_id'])
            assert delivery.conversation_thread_id is None and delivery.fanvue_user_id is None
            if outcome=='ok':
                assert delivery.state.value=='CONFIRMED' and delivery.outbound_telegram_message_id==1234
                assert delivery.delivery_payload['provider_delivery_evidence']['accepted'] is True
                if route=='telethon':assert delivery.delivery_payload['operator_rendered_send']['caption_entities'][0]['url'].startswith('https://unlock.example.test/u/')
            else:assert delivery.state.value=='AMBIGUOUS'
            assert c.execute('SELECT md5(to_jsonb(p)::text) digest FROM purchase_intents p WHERE purchase_intent_id=%s',(old.purchase_intent_id,)).fetchone()['digest']==before
            assert not c.execute('SELECT 1 FROM telegram_identity_map WHERE telegram_user_id=%s',(user,)).fetchone()
        finally:c.rollback()

def test_migration_rollback_forward_effects_preserve_history():
    from app.services.schema_manager_service import SchemaManagerService
    name='20260921_150_manual_prospect_offers.sql'
    with connection() as c:
        @contextmanager
        def same():yield c
        manager=SchemaManagerService(connection_factory=same)
        try:
            assert manager._migration_schema_already_present(c,name)
            c.execute((Path('migrations/rollback')/name).read_text().replace('BEGIN;','').replace('COMMIT;',''))
            assert not manager._migration_schema_already_present(c,name)
            c.execute((Path('migrations/forward')/name).read_text().replace('BEGIN;','').replace('COMMIT;',''))
            assert manager._migration_schema_already_present(c,name)
        finally:c.rollback()


@pytest.fixture(autouse=True)
def trusted_unlock_origin(monkeypatch):
    monkeypatch.setenv("CREATOR_OS_PUBLIC_API_URL", "https://unlock.example.test")



def test_concurrent_reservation_claim_and_stale_dispatch_quarantine():
    from concurrent.futures import ThreadPoolExecutor
    user=uuid4().int%100000000000+200000000000
    with connection() as c:
        product=dict(c.execute("SELECT o.offering_id,p.publication_id,o.creator_profile_id,o.price_minor,o.currency FROM commercial_offerings o JOIN commercial_publications p ON p.commercial_offering_id=o.offering_id WHERE p.provider='FANVUE' LIMIT 1").fetchone())
        account=c.execute('SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1').fetchone()['id']
        creator=product['creator_profile_id']
        c.execute("INSERT INTO telegram_relationship_controls(relationship_control_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,mode,control_version,changed_by) VALUES(%s,%s,%s,%s,%s,'HUMAN_OPERATOR',9,'SANITIZED_TEST')",(uuid4(),creator,account,user,user))
    repo=TelegramManualOfferRepository(connection)
    context=dict(creator_profile_id=creator,fanvue_account_id=account,telegram_user_id=user,telegram_chat_id=user,conversation_thread_id=None)
    args=dict(context=context,offering=product,business_connection_id=None,idempotency_key='concurrent-test',message_text='Neutral offer',expected_control_version=9,queued=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reserved=list(pool.map(lambda _:repo.reserve(**args),range(2)))
            assert reserved[0]['operation_id']==reserved[1]['operation_id']
            claims=list(pool.map(lambda _:repo.claim(reserved[0]['operation_id'],9),range(2)))
        assert sum(value is not None for value in claims)==1
        operation=repo.get(reserved[0]['operation_id'])
        assert operation['send_attempt_count']==1
        assert not any(p['operation_id']==operation['operation_id'] for p in repo.pending_private_dispatches())
        with connection() as c:
            c.execute("UPDATE telegram_manual_offer_operations SET sending_at=NOW()-INTERVAL '6 minutes' WHERE operation_id=%s",(operation['operation_id'],))
        repo.quarantine_stale_dispatches()
        assert repo.get(operation['operation_id'])['state']=='AMBIGUOUS'
        assert repo.claim(operation['operation_id'],9) is None
    finally:
        with connection() as c:
            c.execute('DELETE FROM telegram_manual_offer_operations WHERE telegram_user_id=%s',(user,))
            c.execute('DELETE FROM telegram_relationship_controls WHERE telegram_user_id=%s',(user,))

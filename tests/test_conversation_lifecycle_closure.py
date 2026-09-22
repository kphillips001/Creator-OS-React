from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from contextlib import nullcontext
from uuid import uuid4
from copy import deepcopy
import asyncio
import pytest
from app.services.relationships_service import RelationshipsService
from app.services.telegram_transport_boundary import RoutedTelegramSender,TelegramAcknowledgementPersistenceError
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.testing.telegram_transport_fixtures import ReachableTestSender

NOW=datetime.now(timezone.utc)
def inbox(**changes):
    value=dict(telegram_chat_id=420,last_inbound_message_id=20,operation_inbound_message_id=20,
        last_customer_inbound_at=NOW,last_visible_outbound_at=NOW-timedelta(hours=1),
        database_now=NOW,operation_id=uuid4(),operation_state='SUPPRESSED',
        inbound_message_text='Hey',operation_last_error='quality_corrective_retry_exhausted:MANUFACTURED_ENGAGEMENT_QUESTION',
        candidate_count=2,provider_attempt_count=2,generation_attempt_count=2,max_generation_attempts=2,
        send_attempt_count=0,max_send_attempts=3,prospective_generation_eligible=True)
    value.update(changes);return value

def project(**values):return RelationshipsService._operational_projection(inbox(**values))

@pytest.mark.parametrize('text,error,category',[
    ('lol','quality_blocked_before_delivery:MANUFACTURED_ENGAGEMENT_QUESTION','NO_REPLY_REQUIRED'),
    ('Hey','quality_blocked_before_delivery:MANUFACTURED_ENGAGEMENT_QUESTION','HUMAN_ATTENTION_REQUIRED'),
    ('Would you like that?','quality_corrective_retry_exhausted:FINAL_REPETITION_FAILURE','HUMAN_ATTENTION_REQUIRED'),
])
def test_surviving_obligation_controls_quality_escalation(text,error,category):
    result=project(inbound_message_text=text,operation_last_error=error,
        delivery_payload={'attentionInvestment':{'meaningfulObligation':False}})
    assert result['operationalCategory']==category
    assert result['candidateBudgetRemaining']==0
    assert result['responseProviderAttempts']==2

@pytest.mark.parametrize('text,error',[
    ('Would you like breakfast?','EMPTY_GENERATION:EMPTY'),
    ('Good morning sexy','DECISION_ENGINE_EXCEPTION:UNKNOWN'),
    ('Good morning beautiful, how are you?','DECISION_ENGINE_EXCEPTION:UNKNOWN')])
def test_sanitized_empty_and_engine_failures_are_incidents(text,error):
    result=project(inbound_message_text=text,operation_state='TERMINAL_FAILED',operation_last_error=error)
    assert result['operationalCategory']=='SYSTEM_INCIDENT'
    assert result['operationalStatus']=='SYSTEM_INCIDENT'
    assert result['automaticRecoveryEligible'] is False

@pytest.mark.parametrize('state',['GENERATING','SENDING'])
def test_current_active_claim_is_recovery_pending(state):
    result=project(operation_state=state,claim_owner='worker',lease_expires_at=NOW+timedelta(minutes=1))
    assert result['operationalCategory']=='RECOVERY_PENDING'

@pytest.mark.parametrize('new_text,category',[('Guess','NO_REPLY_REQUIRED'),('Hey','SYSTEM_INCIDENT')])
def test_stu_class_newer_inbound_supersedes_old_definite_transport_failure(new_text,category):
    result=project(operation_state='TERMINAL_FAILED',operation_last_error='PEER_ID_INVALID',
        operation_inbound_message_id=18,latest_inbound_text=new_text)
    assert result['operationalCategory']==category
    assert result['causalOperationId'] is None
    assert result['supersededOperationId']

@pytest.mark.parametrize('mode',['AVA_AUTO','HUMAN_OPERATOR'])
@pytest.mark.parametrize('answered',[True,False])
def test_uncertain_history_is_not_hidden_by_new_inbound_outbound_or_manual_mode(mode,answered):
    result=project(control_mode=mode,last_visible_outbound_at=NOW+timedelta(seconds=1) if answered else None,
        uncertain_operations=[{'operationId':'historical','reason':'unknown'}])
    assert result['operationalCategory']=='DELIVERY_UNCERTAIN'
    assert not result['automaticRecoveryEligible']

@pytest.mark.parametrize('state,error',[('SUPPRESSED','quality_corrective_retry_exhausted:FINAL_REPETITION_FAILURE'),
                                        ('TERMINAL_FAILED','EMPTY_GENERATION:EMPTY'),
                                        ('GENERATED','stranded')])
def test_acknowledgement_clears_alert_only_and_new_material_failure_reappears(state,error):
    source=inbox(operation_state=state,operation_last_error=error,has_response_payload=True,
        operation_updated_at=NOW-timedelta(minutes=4))
    original=deepcopy(source)
    first=RelationshipsService._operational_projection(source)
    source.update(acknowledged_occurrence_id=first['attentionOccurrenceId'],acknowledged_at=NOW,
        acknowledged_by='TEST',acknowledgement_id=uuid4())
    acknowledged=RelationshipsService._operational_projection(source)
    assert acknowledged['operationalStatus']=='NONE'
    assert acknowledged['operationState']==state
    assert source['candidate_count']==original['candidate_count']
    assert acknowledged['attentionAcknowledgementId']
    source['operation_last_error']='new material failure'
    assert RelationshipsService._operational_projection(source)['operatorAlertActive']


def test_uncertain_cannot_be_hidden_by_acknowledgement():
    source=inbox(operation_state='SEND_UNCERTAIN')
    first=RelationshipsService._operational_projection(source)
    source['acknowledged_occurrence_id']=first['attentionOccurrenceId']
    assert RelationshipsService._operational_projection(source)['operationalStatus']=='DELIVERY_UNCERTAIN'


def test_historical_retry_not_reenrolled_and_future_inbound_is_eligible():
    old=project(operation_state='PENDING_GENERATION',prospective_generation_eligible=False,candidate_count=None)
    assert old['operationalCategory']=='SYSTEM_INCIDENT' and not old['automaticRecoveryEligible']
    new=project(operation_state='PENDING_GENERATION',prospective_generation_eligible=True,candidate_count=None)
    assert new['operationalCategory']=='RECOVERY_PENDING' and new['automaticRecoveryEligible']


def test_disabled_compatibility_fails_before_any_sender_or_safety_call():
    executor=TelegramDeliveryExecutor(global_safety_service=object(),customer_safety_service=object())
    result=executor.execute({},context={'customer_delivery_disabled':True})
    assert not result.executed and result.status=='DISABLED'


def test_teaser_uses_real_boundary_and_persistence_failure_never_replays():
    from tests.test_free_engagement_teaser_service import MemoryRepository,operation,service
    class Repo(MemoryRepository):
        def record_transport_evidence(self,operation_id,evidence):
            if evidence.get('accepted'):raise RuntimeError('isolated persistence failure')
            return self.item
    class Sender(ReachableTestSender):
        count=0
        def send_text(self,**values):self.count+=1;return 88
    class Executor:
        async def execute_async(self,payload,*,context):
            sender=RoutedTelegramSender(context['transport'],context=context,metadata={})
            sender.send_text(chat_id=5,message_text='Neutral teaser test')
    repo=Repo(operation());sender=Sender();subject=service(repo,delivery=Executor())
    first=asyncio.run(subject.execute_async(repo.item.operation_id,transport=sender))
    assert first.status=='AMBIGUOUS' and sender.count==1
    second=asyncio.run(subject.execute_async(repo.item.operation_id,transport=sender))
    assert second.status=='AMBIGUOUS' and sender.count==1


def test_projection_migration_history_constraints_and_repeat_reconciliation():
    import os,psycopg,json
    from psycopg.rows import dict_row
    from psycopg.conninfo import conninfo_to_dict
    from app.services.schema_manager_service import SchemaManagerService
    from app.repositories.relationships_repository import RelationshipsRepository
    from app.testing.postgres_safety import require_isolated_test_database_url
    url=require_isolated_test_database_url(os.environ['TEST_DATABASE_URL'],os.environ['DATABASE_URL'])
    def factory():return psycopg.connect(url,row_factory=dict_row)
    manager=SchemaManagerService(connection_factory=factory)
    name='20260920_149_conversation_projection_history.sql'
    assert manager.reconcile_one(name).status=='PASS'
    assert manager.reconcile_one(name).migrations_applied==()
    scope=dict(creator_profile_id=90001,fanvue_account_id=90001,telegram_user_id=90001,telegram_chat_id=90001)
    repo=RelationshipsRepository(connection_factory=factory)
    try:
        first=project()
        assert repo.record_projection_transition(**scope,projection=first)
        assert repo.record_projection_transition(**scope,projection=first) is None
        second={**first,'operationalStatus':'NONE','operatorAlertActive':False,'attentionAcknowledgementId':'ack'}
        assert repo.record_projection_transition(**scope,projection=second)
        with factory() as c:
            assert c.execute("SELECT count(*) n FROM conversation_projection_events WHERE telegram_user_id=90001").fetchone()['n']==2
            assert c.execute("SELECT 1 FROM pg_indexes WHERE indexname='conversation_projection_events_relationship_idx'").fetchone()
        with pytest.raises(psycopg.errors.CheckViolation):
            with factory() as c:
                c.execute("INSERT INTO conversation_projection_events(creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,projection_hash,projection) VALUES(1,1,1,1,'bad','{}')")
        with factory() as c:
            from pathlib import Path
            c.execute(Path('migrations/rollback/'+name).read_text())
        assert manager.reconcile_one(name).status=='PASS'
        assert repo.inbox_state(creator_profile_id=90001,fanvue_account_id=90001)=={}
    finally:
        with factory() as c:c.execute('DELETE FROM conversation_projection_events WHERE telegram_user_id=90001')


@pytest.mark.parametrize('failure',['none','ack_persistence','accepted_persistence','confirm_persistence','missing_id','claim_lost'])
def test_manual_offer_canonical_evidence_and_quarantine(failure,monkeypatch):
    monkeypatch.setenv('CREATOR_OS_PUBLIC_API_URL','https://unlock.example.test')
    from tests.test_relationship_manual_offers import service,Operations,context,OFFER_ID
    from app.services.relationship_manual_offer_service import RelationshipManualOfferError
    from app.models.telegram_transport_contract import TelegramReachability
    operations=Operations();events=[];sends=[]
    intent=SimpleNamespace(purchase_intent_id=uuid4())
    delivery=SimpleNamespace(operation_id=uuid4(),state="CONFIRMED")
    def record(op,evidence):
        events.append(evidence)
        if failure=='ack_persistence' and evidence.get('accepted'):raise RuntimeError('ack DB failure')
        return op
    def accepted(op,message_id):return None if failure=='accepted_persistence' else op
    def confirm(op):
        if failure=='confirm_persistence':raise RuntimeError('confirm DB failure')
        return op
    class Sender(ReachableTestSender):
        BUTTON_LABEL='Unlock'
        def send_asset(self,**values):
            sends.append(values)
            assert events[0]['transport_route']['required_capabilities']['url_action']
            return None if failure=='missing_id' else 99
    sender=Sender()
    deliveries=SimpleNamespace(prepare_operator_offer=lambda **_:(delivery,True),
        claim=lambda _:None if failure=='claim_lost' else delivery,
        record_provider_evidence=record,accepted=accepted,confirm=confirm,failed=lambda *_:None)
    subject=service(operations=operations,transport=sender,deliveries=deliveries,
        intents=SimpleNamespace(create_before_presentation=lambda **_:intent,mark_delivery_failed=lambda *_:None),
        unlocks=SimpleNamespace(issue=lambda _:(None,'https://unlock.example.test/u/AAAAAAAAAAAAAAAAAAAAAA')))
    values=dict(context=context(),offering_id=OFFER_ID,expected_control_version=9,
                business_connection_id=None,idempotency_key='isolated-key',message_text='Neutral offer test')
    if failure=='none':
        assert subject.send(**values)['state']=='CONFIRMED'
        assert subject.send(**values)['state']=='CONFIRMED'
        assert len(sends)==1
        assert events[0]['transport_route']['transport']=='BOT_API'
        assert events[0]['transport_route']['operation_id']==str(delivery.operation_id)
        assert events[-1]['telegram_message_id']==99
    else:
        with pytest.raises(RelationshipManualOfferError):subject.send(**values)
        if failure=='claim_lost':assert not sends
        else:
            assert operations.item['state']=='AMBIGUOUS'
            with pytest.raises(RelationshipManualOfferError):subject.send(**values)
            assert len(sends)==1


def test_manual_offer_does_not_treat_mapping_as_peer_reachability():
    from tests.test_relationship_manual_offers import service,context,OFFER_ID
    from app.services.relationship_manual_offer_service import RelationshipManualOfferError
    with pytest.raises(RelationshipManualOfferError,match='No reachable transport'):
        service(transport=object()).prepare(context=context(),offering_id=OFFER_ID,
            expected_control_version=9,business_connection_id=None)


@pytest.mark.parametrize('state,flags,category',[
 ('GENERATING',{'initial_started':True},'SYSTEM_INCIDENT'),
 ('RETRYABLE',{'correction_started':True,'candidate_count':1},'SYSTEM_INCIDENT'),
 ('RETRYABLE',{'correction_started':True,'candidate_count':2},'HUMAN_ATTENTION_REQUIRED')])
def test_recovery_projection_respects_durable_started_phases_and_lifetime_budget(state,flags,category):
    result=project(operation_state=state,operation_last_error='quality_corrective_retry_scheduled',
        generation_attempt_count=1,max_generation_attempts=2,next_retry_at=NOW+timedelta(minutes=1),**flags)
    assert result['operationalCategory']==category
    assert not result['automaticRecoveryEligible']


@pytest.mark.parametrize('domain',['teaser','sales'])
def test_real_postgres_transport_recorder_one_invocation_and_durable_ack(domain):
    from concurrent.futures import ThreadPoolExecutor
    from app.test_private_chat_settlement_postgres import fixture,connection_factory
    from app.repositories.free_engagement_teaser_repository import FreeEngagementTeaserRepository
    from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
    value=fixture();operation_id=uuid4()
    with connection_factory() as c:
        thread=c.execute("INSERT INTO chat_threads(fanvue_account_id,fanvue_user_id,thread_status) VALUES(%s,%s,'ACTIVE') RETURNING id",
            (value['account'],value['user'])).fetchone()['id']
        if domain=='teaser':
            c.execute("""INSERT INTO telegram_engagement_teaser_delivery_operations(operation_id,correlation_id,
              creator_profile_id,fanvue_account_id,fanvue_user_id,conversation_thread_id,telegram_chat_id,
              teaser_asset_id,media_reference,state) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'isolated.png','SENDING')""",
              (operation_id,str(operation_id),value['creator'],value['account'],value['user'],thread,value['telegram'],value['asset']))
        else:
            c.execute("""INSERT INTO telegram_sales_delivery_operations(operation_id,correlation_id,
              creator_profile_id,fanvue_account_id,fanvue_user_id,conversation_thread_id,telegram_chat_id,
              inbound_telegram_message_id,purchase_intent_id,commercial_offering_id,commercial_publication_id,
              response_text,state) VALUES(%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,'Neutral test','SENDING')""",
              (operation_id,str(operation_id),value['creator'],value['account'],value['user'],thread,value['telegram'],
               value['intent_id'],value['offering_id'],value['publication_id']))
    repo=FreeEngagementTeaserRepository(connection_factory) if domain=='teaser' else TelegramSalesDeliveryRepository(connection_factory)
    record=repo.record_transport_evidence if domain=='teaser' else repo.record_provider_evidence
    evidence={'transport_route':{'operation_id':str(operation_id),'provider_attempt_id':str(uuid4()),'transport':'BOT_API'}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:record(operation_id,evidence),range(4)))
    assert sum(result is not None for result in results)==1
    record(operation_id,{'telegram_message_id':987,'certainty':'ACCEPTED','accepted':True})
    table='telegram_engagement_teaser_delivery_operations' if domain=='teaser' else 'telegram_sales_delivery_operations'
    column='decision_evidence' if domain=='teaser' else 'delivery_payload'
    with connection_factory() as c:
        stored=c.execute(f'SELECT {column} evidence FROM {table} WHERE operation_id=%s',(operation_id,)).fetchone()['evidence']['provider_delivery_evidence']
        assert stored['transport_route']==evidence['transport_route']
        assert stored['telegram_message_id']==987
        c.execute(f'DELETE FROM {table} WHERE operation_id=%s',(operation_id,))


def test_149_clean_forward_schema_indexes_and_nullable_route_hint():
    from app.test_private_chat_settlement_postgres import connection_factory
    from pathlib import Path
    schema='closure_'+uuid4().hex
    with connection_factory() as c:
        c.execute(f'CREATE SCHEMA {schema}')
        c.execute(f'CREATE TABLE {schema}.telegram_manual_offer_operations(business_connection_id TEXT NOT NULL)')
        sql=Path('migrations/forward/20260920_149_conversation_projection_history.sql').read_text()
        c.execute(sql.replace('public.',schema+'.'))
        assert c.execute("SELECT 1 FROM pg_indexes WHERE schemaname=%s AND indexname='conversation_projection_events_relationship_idx'",(schema,)).fetchone()
        c.execute(f'INSERT INTO {schema}.telegram_manual_offer_operations VALUES(NULL)')
        c.rollback()



def test_definite_rejection_is_incident_and_old_send_timestamp_does_not_override_new_inbound():
    result=project(operation_state='TERMINAL_FAILED',operation_last_error='PEER_ID_INVALID',sending_at=NOW)
    assert result['operationalCategory']=='SYSTEM_INCIDENT'
    result=project(operation_state='TERMINAL_FAILED',operation_last_error='PEER_ID_INVALID',sending_at=NOW,
        operation_inbound_message_id=18,latest_inbound_text='Guess')
    assert result['operationalCategory']=='NO_REPLY_REQUIRED'



def test_confirmed_outbound_resolves_projected_debt_without_mutating_durable_obligation():
    obligation={'required':True,'version':'ORDINARY_OBLIGATION_V1','obligations':['RESPOND_TO_GREETING']}
    result=project(last_visible_outbound_at=NOW+timedelta(seconds=1),generation_obligation=obligation)
    assert result['operationalCategory']=='NO_REPLY_REQUIRED'
    assert result['responseObligation']['required'] is False
    assert result['responseObligation']['requiredBeforeResolution'] is True
    assert obligation['required'] is True

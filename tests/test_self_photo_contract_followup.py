from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4
import hashlib
import pytest
from app.models.telegram_inbound import canonical_text_delivery_type
from app.models.conversation_gateway import ConversationGatewayOutput
from app.services.recovery_execution_constraint_service import RecoveryExecutionConstraintService as Constraint
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService as Obligations
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService, durable_plain_data
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.test_telegram_inbound_adapter import RecordingIdentityAdapter, RecordingConversationGateway, inbound_payload
from test_ordinary_generation_budget import setup, connection
from test_decimal_self_photo_repair import initial_visual

LIVE = "Love the relaxed vibe you're giving off here\u2014definitely not ugly at all! This is a great way to put a face to the chat."

@pytest.mark.parametrize('text',[LIVE,"You're not ugly.","Definitely not ugly at all!","You're not bad-looking.","You're not remotely unattractive.","You're anything but ugly.","Hardly ugly!","Not an ugly mug!","Nothing ugly about you.","Nice to put a face to the chat."])
def test_positive_negation_and_acknowledgement(text):
    style=Obligations.validate_self_photo({},text,{'obligations':['ACKNOWLEDGE_SELF_PHOTO']})
    assert style['turnObligationsSatisfied'] and style['turnObligations']==['ACKNOWLEDGE_SELF_PHOTO']

@pytest.mark.parametrize('text',["You're ugly.","Your face is hideous.","You're not handsome.","Not ugly, but your face is disgusting.","I won't say you're not ugly.","You're not good-looking."])
def test_actual_insult_or_denied_compliment_rejected(text):
    assert not Obligations.validate_self_photo({},text,{'obligations':['ACKNOWLEDGE_SELF_PHOTO']})['turnObligationsSatisfied']

@pytest.mark.parametrize('outer,inner,allowed', [('MESSAGE_TEXT','MESSAGE_TEXT',True),('text','text',True),(' TEXT ','MESSAGE_TEXT',True),('photo','photo',False),('video','video',False),('unknown','unknown',False),('text','photo',False)])
def test_contract_aliases_do_not_mask_media(outer,inner,allowed):
    op=SimpleNamespace(delivery_payload={'recoveryExecutionConstraint':Constraint.authority()})
    result=SimpleNamespace(delivery_type=outer,delivery_payload={'delivery_type':inner,'message_text':'hi'},diagnostic_metadata={},delivery_mode='conversation',offer_authorized=False,delivery_requires_payment=False)
    assert Constraint.validate_result(op,result)[0] is allowed
    assert canonical_text_delivery_type(outer)==('MESSAGE_TEXT' if outer.strip().upper() in {'TEXT','MESSAGE_TEXT'} else outer)

def normalized_gateway_result(op, original):
    gateway=RecordingConversationGateway(ConversationGatewayOutput(correlation_id=op.correlation_id,
        response_text=original.response_text,offer_authorized=False,offer_link=None,blocked=False,error_code=None,
        delivery_type='text',delivery_mode='conversation',delivery_requires_payment=False,
        delivery_payload={'message_text':original.response_text,'delivery_type':'text','delivery_method':'text','delivery_reason':'CUSTOMER_MEDIA_RESPONSE'},
        diagnostic_metadata=original.diagnostic_metadata))
    adapter=TelegramInboundAdapter(identity_adapter=RecordingIdentityAdapter(),conversation_gateway=gateway)
    return adapter.execute(inbound_payload(telegram_user_id=op.inbound_sender_telegram_user_id,
        telegram_chat_id=op.telegram_chat_id,message_id=op.inbound_telegram_message_id,message_text=op.inbound_message_text))

def test_exact_live_scenario_adapter_ledger_and_final_gate(setup):
    ordinary,budget,owner,make=setup;op=make('My ugly mug! Thought you might want to see who is chatting you up!')
    op=replace(op,delivery_payload={'recoveryExecutionConstraint':Constraint.authority()})
    def initial(payload):return normalized_gateway_result(op,initial_visual(op,LIVE)(payload))
    out=OrdinaryReplyGenerationService(budget,authorize=Mock()).execute(op,None,owner=owner,initial=initial)
    assert out.delivery_type==out.delivery_payload['delivery_type']=='MESSAGE_TEXT'
    assert out.diagnostic_metadata['conversationStyle']['turnObligationsSatisfied']
    assert budget.read(op.operation_id)['obligation']['required']
    final=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(op,out)
    assert final.state.value=='GENERATED' and final.send_attempt_count==0
    assert final.response_payload['delivery_type']=='MESSAGE_TEXT'
    assert Constraint.validate_persisted_delivery(final)[0]


def test_one_followup_preserves_both_historical_operations(setup,tmp_path):
    from test_ordinary_generation_budget import connection
    ordinary,budget,owner,make=setup
    op=make('This is me')
    image=tmp_path/'sanitized.jpg';image.write_bytes(b'not-used-by-provider')
    occurrence=str(uuid4());media=uuid4();attachment=uuid4();approval=uuid4()
    budget.begin(op.operation_id,owner,Obligations.decide(op))
    budget.save(op.operation_id,owner,result={'diagnostic_metadata':{'exception_type':'TypeError'}})
    ordinary.fail_generation(op.operation_id,owner=owner,reason='DECISION_ENGINE_EXCEPTION:TypeError')
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET telegram_account_scope='AVA_TELETHON_PRIVATE' WHERE operation_id=%s",(op.operation_id,))
        c.execute("""INSERT INTO conversation_attention_acknowledgements(acknowledgement_id,occurrence_id,creator_profile_id,fanvue_account_id,
            telegram_account_scope,telegram_chat_id,telegram_user_id,triggering_inbound_message_id,causal_operation_id,
            attention_reason,predicate_version,acknowledged_by) VALUES (%s,%s,1,2,'AVA_TELETHON_PRIVATE',%s,%s,100,%s,'SYSTEM_INCIDENT','test','operator')""",
            (uuid4(),occurrence,op.telegram_chat_id,op.inbound_sender_telegram_user_id,op.operation_id))
        c.execute("""INSERT INTO telegram_private_inbound_messages(inbound_id,telegram_account_scope,telegram_user_id,telegram_chat_id,
            telegram_message_id,received_at,customer_text,has_media,creator_profile_id,fanvue_account_id,ingestion_provenance,automation_state_at_receipt)
            VALUES(%s,'AVA_TELETHON_PRIVATE',%s,%s,100,now(),'This is me',true,1,2,'LIVE_EVENT','AVA_AUTO')""",(uuid4(),op.inbound_sender_telegram_user_id,op.telegram_chat_id))
        c.execute("""INSERT INTO telegram_inbound_media_operations(operation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,telegram_user_id,
            logical_turn_key,caption_text,state,safety_state,response_policy,retention_expires_at)
            VALUES(%s,1,2,%s,%s,%s,'This is me','SAFETY_CLASSIFIED','NORMAL_NON_EXPLICIT','SELFIE_COMPLIMENT_ELIGIBLE',now()+interval '1 hour')""",
            (media,op.telegram_chat_id,op.inbound_sender_telegram_user_id,str(media)))
        c.execute("""INSERT INTO telegram_inbound_media_attachments(attachment_id,operation_id,telegram_message_id,telegram_media_id,media_kind,position,normalized_path,state)
            VALUES(%s,%s,100,'sanitized','PHOTO',0,%s,'READY_FOR_ANALYSIS')""",(attachment,media,str(image)))
        before=c.execute('SELECT md5(to_jsonb(o)::text) hash FROM ordinary_chat_reply_operations o WHERE operation_id=%s',(op.operation_id,)).fetchone()['hash']
    kwargs=dict(failed_operation_id=op.operation_id,creator_profile_id=1,fanvue_account_id=2,telegram_user_id=op.inbound_sender_telegram_user_id,
                occurrence_id=occurrence,approved_by='operator',approval_reference=approval)
    child=ordinary.create_controlled_fresh_response(**kwargs)
    assert child.operation_id!=op.operation_id and ordinary.create_controlled_fresh_response(**kwargs).operation_id==child.operation_id
    assert child.max_send_attempts==1 and child.causal_operation_id==op.operation_id
    payload=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).retry_payload(child)
    assert payload.current_turn_visual_context['attachment_ids']==[str(attachment)]
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET next_retry_at=now() WHERE operation_id=%s",(child.operation_id,))
    claimed=ordinary.claim_generation(child.operation_id,owner=owner)
    service=OrdinaryReplyGenerationService(budget,authorize=Mock())
    out=service.execute(claimed,payload,owner=owner,initial=initial_visual(claimed,'Nice to finally put a face to the name!'))
    assert budget.read(child.operation_id)['candidate_count']==1
    legacy=replace(out,delivery_type='text',delivery_mode='conversation')
    suppressed=ordinary.store_suppressed_generation(child.operation_id,owner=owner,
        response_payload=durable_plain_data(legacy),response_text=legacy.response_text,
        content_sha256=hashlib.sha256(legacy.response_text.encode()).hexdigest(),
        delivery_payload=claimed.delivery_payload,
        reason='recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY',conversation_thread_id=None)
    with connection() as c:
        first_hash=c.execute('select md5(to_jsonb(o)::text) h from ordinary_chat_reply_operations o where operation_id=%s',(child.operation_id,)).fetchone()['h']
    follow_kwargs={**kwargs,'failed_operation_id':child.operation_id,'occurrence_id':str(uuid4()),'approval_reference':uuid4()}
    fresh=ordinary.create_controlled_fresh_response(**follow_kwargs)
    assert ordinary.create_controlled_fresh_response(**follow_kwargs).operation_id==fresh.operation_id
    assert fresh.operation_id not in (op.operation_id,child.operation_id)
    assert fresh.delivery_payload['controlledFreshResponse']['version']=='TEXT_CONTRACT_FOLLOWUP_V2'
    assert Obligations.decide(fresh)['required']
    with connection() as c:c.execute('update ordinary_chat_reply_operations set next_retry_at=now() where operation_id=%s',(fresh.operation_id,))
    fresh=ordinary.claim_generation(fresh.operation_id,owner=owner)
    new=service.execute(fresh,None,owner=owner,initial=lambda payload:normalized_gateway_result(fresh,initial_visual(fresh,LIVE)(payload)))
    final=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(fresh,new)
    assert final.state.value in {'GENERATED','RETRYABLE'}
    assert final.last_error in (None,'prepared_for_scheduled_delivery')
    assert final.response_payload['diagnostic_metadata']['delivery_quality_gate']['disposition']=='ALLOWED'
    assert budget.read(fresh.operation_id)['candidate_count']==1
    with connection() as c:
        assert c.execute('select md5(to_jsonb(o)::text) h from ordinary_chat_reply_operations o where operation_id=%s',(child.operation_id,)).fetchone()['h']==first_hash
        c.execute('delete from ordinary_generation_budgets where operation_id=%s',(fresh.operation_id,))
        c.execute('delete from ordinary_chat_reply_operations where operation_id=%s',(fresh.operation_id,))
    with connection() as c:
        after=c.execute('SELECT md5(to_jsonb(o)::text) hash FROM ordinary_chat_reply_operations o WHERE operation_id=%s',(op.operation_id,)).fetchone()['hash']
    assert before==after
    with connection() as c:
        c.execute('DELETE FROM conversation_attention_acknowledgements WHERE occurrence_id=%s',(occurrence,))
        c.execute('DELETE FROM ordinary_generation_budgets WHERE operation_id=%s',(child.operation_id,))
        c.execute('DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s',(child.operation_id,))
        c.execute('DELETE FROM telegram_private_inbound_messages WHERE telegram_chat_id=%s',(op.telegram_chat_id,))
        c.execute('DELETE FROM telegram_inbound_media_operations WHERE operation_id=%s',(media,))

from decimal import Decimal
from datetime import datetime, date, time, timezone
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from app.services.ordinary_chat_reply_service import durable_plain_data, OrdinaryChatReplyService
from app.services.customer_media_multimodal_decision_engine import CustomerMediaMultimodalDecisionEngine as Engine
from app.services.customer_visual_evidence_policy import CustomerVisualEvidencePolicy as Visual
from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService as Obligations
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.ordinary_generation_context import current_generation
from app.services.gpt_service import GPTService
from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed
from test_ordinary_generation_budget import setup, Provider, result, claim_correction

@pytest.mark.parametrize('value',['0.00','1','1.234','-2.375','12345678901234567890.12345678901234567890'])
def test_decimal_exact(value):
    original=Decimal(value)
    durable=json.loads(json.dumps(durable_plain_data({'nested':[original]})))['nested'][0]
    assert durable==value and Decimal(durable).as_tuple()==original.as_tuple()

@pytest.mark.parametrize('value',[object(),Decimal('NaN'),Decimal('Infinity')])
def test_unsupported_fails_closed(value):
    with pytest.raises(TypeError): durable_plain_data(value)

def test_supported_types_preserved():
    uid=uuid4(); now=datetime.now(timezone.utc)
    source={'s':'text','i':1,'f':1.5,'b':True,'n':None,'date':date(2026,1,1),'time':time(12,30),'dt':now,'id':uid,'tuple':(1,2),'set':frozenset([2,1])}
    value=durable_plain_data(source)
    assert value=={**source,'date':'2026-01-01','time':'12:30:00','dt':now.isoformat(),'id':str(uid),'tuple':[1,2],'set':[1,2]}

def observation(person=True,meme=False):
    return {'attachment_id':'image-1','person_visible':person,'person_count':1 if person else 0,
            'dog_visible':False,'animal_visible':False,'animals':[],'objects':[],'activity':None,
            'broad_scene':'portrait','smiling':True,'style_or_clothing_summary':'casual shirt',
            'screenshot_or_meme':meme,'visible_text_summary':None,'confidence':.95}

def engine_result(text, response="Nice to finally put a face to the name!", *, person=True,meme=False):
    runner=Mock(return_value={'response_text':response,'observations':[observation(person,meme)]})
    engine=Engine(runner=runner)
    value=engine.process_message('sanitized',text,runtime_injection={'current_turn_visual_context':{
        'operation_id':'media-1','response_policy':'SELFIE_COMPLIMENT_ELIGIBLE',
        'attachment_ids':['image-1'],'attachment_paths':['unused.jpg']}})
    assert runner.call_count==1
    return value

@pytest.mark.parametrize('text',["This is me","Here's me","That's me","My ugly mug", "Finally putting a face to the name", "Thought you might want to see who you're talking to", "Thought you might want to see who is chatting you up!", "Here's what I look like", "A photo of me"])
def test_positive_self_photo(text):
    value=engine_result(text)
    context=Visual.minimum_persisted_result(value['current_turn_visual_context'])
    assert Visual.self_photo_established(context)
    assert 'ACKNOWLEDGE_SELF_PHOTO' in GPTService.authoritative_turn_obligations(text,visual_context=context)
    assert context['customer_identity_authority'] is False

@pytest.mark.parametrize('text,person,meme',[("Look at this",True,False),("This is my friend",True,False),("My brother",True,False),("Celebrity photo",True,False),("This is me",True,True),("Could be me",True,False),("Not me",True,False),("This is me",False,False),("This is my friend, not me",True,False),("Random person",True,False)])
def test_negative_self_photo(text,person,meme):
    assert not Visual.self_photo_established(engine_result(text,person=person,meme=meme)['current_turn_visual_context'])

@pytest.mark.parametrize('response',["You look great!","Nice to finally put a face to the name!","You're handsome.","That smile suits you."])
def test_acknowledgement_requires_no_question(response):
    style=Obligations.validate_self_photo({},response,{'obligations':['ACKNOWLEDGE_SELF_PHOTO']})
    assert style['turnObligationsSatisfied'] and '?' not in response

def test_missing_acknowledgement_rejected():
    assert not Obligations.validate_self_photo({},'What are you up to?',{'obligations':['ACKNOWLEDGE_SELF_PHOTO']})['turnObligationsSatisfied']

def initial_visual(op, text):
    def initial(_):
        value=engine_result(op.inbound_message_text,text)
        return TelegramInboundResult(correlation_id=op.correlation_id,telegram_chat_id=op.telegram_chat_id,
            telegram_user_id=op.inbound_sender_telegram_user_id,message_id=op.inbound_telegram_message_id,
            engine_user_id='sanitized',response_text=value['response'],offer_authorized=False,offer_link=None,
            blocked=False,error_code=None,delivery_type='MESSAGE_TEXT',delivery_payload={'type':'MESSAGE_TEXT','message_text':value['response']},
            diagnostic_metadata={'current_turn_visual_context':Visual.minimum_persisted_result(value['current_turn_visual_context'])})
    return initial

def test_visual_candidate_one_durable_and_no_detection_call(setup):
    ordinary,budget,owner,make=setup;op=make('This is me')
    service=OrdinaryReplyGenerationService(budget,authorize=Mock())
    out=service.execute(op,None,owner=owner,initial=initial_visual(op,'Nice to finally put a face to the name!'))
    row=budget.read(op.operation_id)
    assert row['candidate_count']==row['provider_attempt_count']==1
    assert row['obligation']['required'] and row['obligation']['obligations']==['ACKNOWLEDGE_SELF_PHOTO']
    assert row['context_snapshot']['messages'] and row['result_snapshot']['diagnostic_metadata']['conversationStyle']['turnObligationsSatisfied']
    assert not any(e['kind']=='ANALYSIS_STARTED' for e in row['events'])
    final=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(op,out)
    assert final.state.value=='GENERATED'

@pytest.mark.parametrize('second,expected',[('Nice to finally put a face to the name!','GENERATED'),('Okay.','SUPPRESSED')])
def test_one_consolidated_visual_correction(setup,second,expected):
    ordinary,budget,owner,make=setup;op=make('This is me')
    provider=Provider(second)
    service=OrdinaryReplyGenerationService(budget,authorize=Mock(),client_factory=lambda _:provider)
    first=service.execute(op,None,owner=owner,initial=initial_visual(op,'Okay.'))
    lifecycle,op2=claim_correction(setup,op,first)
    corrected=service.execute(op2,None,owner=owner,initial=Mock(side_effect=AssertionError('Pipeline replay')))
    final=lifecycle.generated(op2,corrected)
    assert final.state.value==expected
    row=budget.read(op.operation_id)
    assert row['candidate_count']==2 and row['provider_attempt_count']==2
    assert corrected.diagnostic_metadata['ordinaryGeneration']['contextSnapshotReused']
    assert provider.options==[{'max_retries':0}]
    with pytest.raises(GenerationBudgetClosed): service.execute(op2,None,owner=owner,initial=Mock())

def test_decimal_memory_snapshot_correction_reuse(setup):
    ordinary,budget,owner,make=setup;op=make('How are you?')
    provider=Provider('Doing well, thanks.')
    service=OrdinaryReplyGenerationService(budget,authorize=Mock(),client_factory=lambda _:provider)
    memory={k:Decimal(v) for k,v in zip(('connection_score','time_waster_score','sexual_intensity','heat_score'),('0.00','1','-0.25','0.123456789012345678901'))}
    def initial(_):
        session=current_generation()
        session.snapshot(durable_plain_data({'version':'ORDINARY_CONTEXT_V1','model':'fake','provider':'OPENAI',
            'messages':[{'role':'user','content':op.inbound_message_text}], 'userMemory':memory}))
        return result(op,'What are you up to?',['CUSTOMER_QUESTION_UNANSWERED'])
    first=service.execute(op,None,owner=owner,initial=initial)
    lifecycle,op2=claim_correction(setup,op,first)
    saved=budget.read(op.operation_id)['context_snapshot']
    second=service.execute(op2,None,owner=owner,initial=Mock(side_effect=AssertionError('Replay')))
    assert provider.calls[0]['messages'][:1]==saved['messages']
    assert all(Decimal(saved['userMemory'][k]).as_tuple()==v.as_tuple() for k,v in memory.items())
    assert second.diagnostic_metadata['ordinaryGeneration']['contextSnapshotReused']


def test_controlled_fresh_preserves_history_and_uses_existing_scheduler(setup,tmp_path):
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
    with connection() as c:
        after=c.execute('SELECT md5(to_jsonb(o)::text) hash FROM ordinary_chat_reply_operations o WHERE operation_id=%s',(op.operation_id,)).fetchone()['hash']
    assert before==after
    with connection() as c:
        c.execute('DELETE FROM conversation_attention_acknowledgements WHERE occurrence_id=%s',(occurrence,))
        c.execute('DELETE FROM ordinary_generation_budgets WHERE operation_id=%s',(child.operation_id,))
        c.execute('DELETE FROM ordinary_chat_reply_operations WHERE operation_id=%s',(child.operation_id,))
        c.execute('DELETE FROM telegram_private_inbound_messages WHERE telegram_chat_id=%s',(op.telegram_chat_id,))
        c.execute('DELETE FROM telegram_inbound_media_operations WHERE operation_id=%s',(media,))


@pytest.mark.parametrize('text',["Pretend this is me", "This is me, joking", "This is me in a meme"])
def test_explicit_ambiguity_is_not_self_photo(text):
    assert not Visual.self_presentation(text)

@pytest.mark.parametrize('response',["You're not handsome.","You look disgusting."])
def test_negative_reaction_does_not_satisfy_positive_self_photo(response):
    assert not Obligations.validate_self_photo({},response,{'obligations':['ACKNOWLEDGE_SELF_PHOTO']})['turnObligationsSatisfied']


def test_controlled_fresh_missing_self_photo_evidence_stops_before_delivery(setup):
    from dataclasses import replace
    ordinary,budget,owner,make=setup;op=make('Look at this')
    op=replace(op,delivery_payload={'controlledFreshResponse':{'version':'ZERO_CANDIDATE_SNAPSHOT_REPAIR_V1'}})
    outcome=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(op,result(op,'Okay.'))
    assert outcome.state.value=='TERMINAL_FAILED'
    assert outcome.last_error=='SELF_PHOTO_EVIDENCE_NOT_ESTABLISHED' and outcome.send_attempt_count==0

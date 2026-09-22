from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from test_ordinary_generation_budget import setup, connection, Provider, pipeline
from test_conversation_lifecycle_closure import inbox
from app.services.gpt_service import GPTService
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService, durable_plain_data
from app.services.ordinary_quality_rejection import normalize
from app.services.ordinary_quality_recovery_service import OrdinaryQualityRecoveryService
from app.repositories.relationships_repository import RelationshipsRepository
from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed
from app.services.customer_heat_signal_service import CustomerHeatSignalService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.sexual_sales_opportunity_service import SexualSalesOpportunityService

OLD='That is a vivid image. You certainly keep things intriguing.'
QUESTION='What do you want from me?'

def withheld(result):
    diagnostics=dict(result.diagnostic_metadata)
    diagnostics['conversationStyle']={
        'combinedObligationRepairOutcome':'UNRESOLVED_OPTIONAL_RESPONSE_WITHHELD',
        'combinedObligationInitialViolations':['FOREGROUND_OBLIGATION_ANSWER_DIRECT_QUESTION'],
        'providerReturnedUsableText':True,'providerCandidateCount':1,
        'finalValidationOriginalCandidate':OLD,
        'turnObligations':['ANSWER_DIRECT_QUESTION'],
        'unsatisfiedTurnObligations':['ANSWER_DIRECT_QUESTION'],
        'customerQuestionAnswered':False,'turnObligationsSatisfied':False}
    return replace(result,response_text='',delivery_payload={'type':'MESSAGE_TEXT','message_text':''},diagnostic_metadata=diagnostics)

@pytest.mark.parametrize('candidate,expected',[
    ('I want to get to know you better, without rushing things.','GENERATED'),
    (OLD,'SUPPRESSED')])
def test_withheld_candidate_gets_only_one_correction(setup,candidate,expected):
    ordinary,budget,owner,make=setup;op=make(QUESTION)
    provider=Provider(OLD,candidate)
    generation=OrdinaryReplyGenerationService(budget,authorize=Mock(),client_factory=lambda _:provider)
    initial=Mock(side_effect=lambda payload:withheld(pipeline(op,provider)(payload)))
    result=generation.execute(op,None,owner=owner,initial=initial)
    assert result.response_text==OLD and result.diagnostic_metadata['qualityRejectionHandoff']
    lifecycle=OrdinaryChatReplyService(repository=ordinary,worker_id=owner)
    scheduled=lifecycle.generated(op,result)
    assert scheduled.state.value=='RETRYABLE' and scheduled.last_error=='quality_corrective_retry_scheduled'
    assert 'EMPTY' not in scheduled.last_error
    assert ordinary.generation_attempts(op.operation_id)[0]['candidate_text']==OLD
    with connection() as c:c.execute('UPDATE ordinary_chat_reply_operations SET next_retry_at=now() WHERE operation_id=%s',(op.operation_id,))
    second=ordinary.claim_generation(op.operation_id,owner=owner)
    result=generation.execute(second,None,owner=owner,initial=initial)
    final=lifecycle.generated(second,result)
    assert final.state.value==expected,(final.last_error,result.diagnostic_metadata.get('conversationStyle'))
    assert budget.read(op.operation_id)['candidate_count']==2
    assert budget.read(op.operation_id)['provider_attempt_count']==2
    assert initial.call_count==1 and len(provider.calls)==2
    with pytest.raises(GenerationBudgetClosed):generation.execute(second,None,owner=owner,initial=initial)
    assert len(provider.calls)==2

@pytest.mark.parametrize('history',['older','current','unknown','newer'])
def test_explicit_historical_recovery_scopes_uncertainty(setup,monkeypatch,history):
    ordinary,budget,owner,make=setup;op=make(QUESTION)
    provider=Provider(OLD)
    generation=OrdinaryReplyGenerationService(budget,authorize=Mock())
    output=generation.execute(op,None,owner=owner,initial=pipeline(op,provider))
    saved=withheld(output)
    budget.save(op.operation_id,owner,result=durable_plain_data(saved))
    ordinary.fail_empty_generation(op.operation_id,owner=owner,reason='EMPTY_GENERATION: Automatic reply could not be completed.')
    assert ordinary.get(op.operation_id).delivery_payload['generationFailurePolicy']['outcome']=='NO_USABLE_GENERATION_RESULT'
    uncertain={'operationId':'older-operation','inboundMessageId':op.inbound_telegram_message_id-1}
    if history=='current':uncertain['operationId']=str(op.operation_id)
    if history=='unknown':uncertain.pop('inboundMessageId')
    if history=='newer':uncertain['inboundMessageId']+=2
    source=inbox(operation_id=op.operation_id,operation_state='TERMINAL_FAILED',
        operation_last_error='EMPTY_GENERATION: Automatic reply could not be completed.',
        control_mode='AVA_AUTO',communication_disposition='ACTIVE',
        last_inbound_message_id=op.inbound_telegram_message_id,operation_inbound_message_id=op.inbound_telegram_message_id,
        generation_obligation={'required':True},candidate_count=1,uncertain_operations=[uncertain])
    monkeypatch.setattr(RelationshipsRepository,'inbox_state',lambda *a,**k:{op.inbound_sender_telegram_user_id:source})
    service=OrdinaryQualityRecoveryService(connection)
    if history!='older':
        with pytest.raises(ValueError):service.resume(op.operation_id,creator_profile_id=2,fanvue_account_id=2,owner=owner)
        return
    result=service.resume(op.operation_id,creator_profile_id=2,fanvue_account_id=2,owner=owner)
    assert result.state.value=='RETRYABLE' and result.max_send_attempts==1
    assert budget.read(op.operation_id)['candidate_count']==1 and len(provider.calls)==1

@pytest.mark.parametrize('text,location',[
    ('Where are you from?',True),('Are you from Florida?',True),('Where do you live?',True),
    ('What do you want from me?',False),('Do you know what I want from you?',False),
    ('Where did that come from?',False),('Your clothes get wet from the rain, then?',False)])
def test_contextual_location(text,location):
    result=GPTService._style_analysis('I want to get to know you.',text,
        pressure={},ordinary=True,memory_callback=False)
    assert (result['customerQuestionDomain']=='LOCATION')==location

def hot_context():
    message='I am describing a much more intimate scene with you, then what happens?'
    heat=CustomerHeatSignalService().project(message=message,classifier_result={
        'sexual_engagement':True,'escalation_ready':True,'explicit_without_buying_intent':True,
        'confidence':.95,'engagement_level':'high'},recent_transcript=[{'role':'assistant','content':'You are trouble'}])
    intents=SimpleNamespace(list_confirmed_presentations_for_buyer=lambda **kwargs:[])
    sexual=SexualSalesOpportunityService(intents=intents,cooldown=timedelta(hours=72)).project(
        creator_profile_id=2,fanvue_account_id=2,telegram_user_id=7,latest_message=message,
        now=datetime.now(timezone.utc),customer_heat_signal=heat)
    return dict(customer_heat_signal=heat,sexual_sales_opportunity=sexual,
        inbound_message_count=46,sexual_engagement_count=3,contextual_customer_tone={'sexualOrProvocative':False},
        effective_content_selling_allowed=True,sales_progression={'phase':'PRESENT_OFFER'})

@pytest.mark.parametrize('blocker',[None,'cooldown','permission','active_intent','weak'])
def test_semantic_escalation_authorizes_evaluation_only(blocker):
    from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
    brain=object.__new__(CustomerSalesBrainService);brain.config=CustomerSalesBrainConfig.from_environment()
    context=hot_context()
    if blocker=='cooldown':context['purchase_cooldown_active']=True
    if blocker=='permission':context['effective_content_selling_allowed']=False
    if blocker=='weak':context['customer_heat_signal']={'detected':False}
    result=brain._proactive_hot_opportunity_assessment(context,active_purchase_intent=blocker=='active_intent',active_sales_session=False)
    assert result['proactiveHotOpportunityAuthorized']==(blocker is None)
    assert not result['offerAuthorized'] and not result['purchaseIntentCreated']
    assert brain.config.sexual_receptiveness_min_engagements==4

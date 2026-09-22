from dataclasses import replace
from unittest.mock import Mock
import pytest
import json
from test_ordinary_generation_budget import setup, Provider, pipeline, connection
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService

def owed_operation(setup):
    ordinary,_,_,make=setup
    op=make('I manage beach condominiums and do not want more work.')
    delivery={'attentionInvestment':{'meaningfulObligation':True,'outcome':'RESPOND'}}
    with connection() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET delivery_payload=%s::jsonb WHERE operation_id=%s',
                  (json.dumps(delivery),op.operation_id))
    return ordinary.get(op.operation_id)

FAILURE = {
    'authority': 'ConversationProgressionQualityService',
    'rejectedCandidateText': "sounds like you've had a lot keeping you busy",
    'candidateDialogueFunction': 'ACKNOWLEDGEMENT_REACTION',
    'recentDialogueFunctions': ['OBSERVATION']*3,
    'rewriteAttempted': True, 'rewriteResult': 'NONCOMPLIANT_REWRITE',
    'finalBlockingReasons': ['SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP',
                             'FOREGROUND_SEMANTIC_RELEVANCE'],
}

def failure_pipeline(op, provider):
    def initial(payload):
        result = pipeline(op, provider, nested=4)(payload)
        return replace(result, response_text='', blocked=True,
            error_code='decision_engine_exception', diagnostic_metadata={
                'conversationProgressionFailure': FAILURE,
                'internal_generation_failure': {'errorType': 'UNKNOWN'},
                'status': 'engine_exception'})
    return initial

def test_exact_sanitized_progression_failure_reaches_correction(setup):
    ordinary,budget,owner,make=setup
    op=owed_operation(setup)
    provider=Provider(FAILURE['rejectedCandidateText'])
    generation=OrdinaryReplyGenerationService(budget,authorize=Mock())
    output=generation.execute(op,None,owner=owner,initial=failure_pipeline(op,provider))
    row=budget.read(op.operation_id)
    assert row['candidate_count']==1 and row['provider_attempt_count']==1
    assert not row['correction_started'] and len(provider.calls)==1
    assert sum(e['kind']=='REWRITE_DEFERRED' for e in row['events'])==4
    final=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(op,output)
    assert final.send_attempt_count==0 and final.outbound_telegram_message_id is None
    assert final.state.value=='RETRYABLE'

@pytest.mark.parametrize('corrected,expected',[
    ('Keeping your work manageable makes sense, even when more beach properties are on offer.','GENERATED'),
    (FAILURE['rejectedCandidateText'],'SUPPRESSED'),
])
def test_saved_correction_is_single_and_quality_checked(setup,corrected,expected):
    from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed
    ordinary,budget,owner,_=setup
    op=owed_operation(setup)
    provider=Provider(FAILURE['rejectedCandidateText'],corrected)
    service=OrdinaryReplyGenerationService(budget,authorize=Mock(),client_factory=lambda _:provider)
    initial=Mock(side_effect=failure_pipeline(op,provider))
    output=service.execute(op,None,owner=owner,initial=initial)
    lifecycle=OrdinaryChatReplyService(repository=ordinary,worker_id=owner)
    scheduled=lifecycle.generated(op,output)
    assert scheduled.delivery_payload['attentionInvestment']['meaningfulObligation']
    with connection() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET next_retry_at=now() WHERE operation_id=%s',(op.operation_id,))
    second=ordinary.claim_generation(op.operation_id,owner=owner)
    result=service.execute(second,None,owner=owner,initial=initial)
    final=lifecycle.generated(second,result)
    assert final.state.value==expected, (final.last_error, result.diagnostic_metadata)
    assert initial.call_count==1 and len(provider.calls)==2
    assert provider.options==[{'max_retries':0}]*2
    assert budget.read(op.operation_id)['candidate_count']==2
    assert budget.read(op.operation_id)['provider_attempt_count']==2
    assert result.diagnostic_metadata['ordinaryGeneration']['contextSnapshotReused']
    assert 'SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP' in provider.calls[1]['messages'][-1]['content']
    with pytest.raises(GenerationBudgetClosed):
        service.execute(second,None,owner=owner,initial=initial)
    assert len(provider.calls)==2 and final.send_attempt_count==0

def test_no_obligation_has_no_correction(setup):
    ordinary,budget,owner,make=setup
    op=make('lol');provider=Provider(FAILURE['rejectedCandidateText'])
    service=OrdinaryReplyGenerationService(budget,authorize=Mock())
    output=service.execute(op,None,owner=owner,initial=failure_pipeline(op,provider))
    final=OrdinaryChatReplyService(repository=ordinary,worker_id=owner).generated(op,output)
    assert final.state.value=='SUPPRESSED' and final.next_retry_at is None
    assert not budget.read(op.operation_id)['correction_started'] and len(provider.calls)==1

@pytest.mark.parametrize('changes,expected',[
    ({},'NONE'),
    ({'generation_obligation':{'required':True}},'SYSTEM_INCIDENT'),
    ({'uncertain_operations':[{'operationId':'protected'}]},'DELIVERY_UNCERTAIN'),
    ({'operation_last_error':'DatabaseUnavailable'},'SYSTEM_INCIDENT'),
    ({'operation_state':'RETRYABLE'},'SYSTEM_INCIDENT'),
])
def test_optional_peer_failure_projection_preserves_history(changes,expected):
    from copy import deepcopy
    from test_conversation_lifecycle_closure import inbox
    from app.services.relationships_service import RelationshipsService
    values=dict(operation_state='TERMINAL_FAILED',
        operation_last_error='TelegramPreflightError: No current Business peer reply evidence.',
        generation_obligation={'required':False},candidate_count=1,send_attempt_count=1,
        projection_history=[{'event':'historical failure'}])
    values.update(changes);source=inbox(**values);before=deepcopy(source)
    projection=RelationshipsService._operational_projection(source)
    assert projection['operationalStatus']==expected
    assert source==before and projection['projectionHistory']==before['projection_history']

@pytest.mark.parametrize('changed',['none','new_inbound','answered','uncertain','manual','exhausted'])
def test_same_operation_recovery_preserves_budget_and_refuses_replay(setup,monkeypatch,changed):
    from app.services.ordinary_quality_recovery_service import OrdinaryQualityRecoveryService
    from app.repositories.relationships_repository import RelationshipsRepository
    from test_conversation_lifecycle_closure import inbox
    from app.services.ordinary_chat_reply_service import durable_plain_data
    ordinary,budget,owner,_=setup;op=owed_operation(setup)
    provider=Provider(FAILURE['rejectedCandidateText'])
    service=OrdinaryReplyGenerationService(budget,authorize=Mock())
    output=service.execute(op,None,owner=owner,initial=failure_pipeline(op,provider))
    historical=replace(output,response_text='',blocked=True,error_code='decision_engine_exception')
    budget.save(op.operation_id,owner,result=durable_plain_data(historical))
    ordinary.fail_generation(op.operation_id,owner=owner,reason='DECISION_ENGINE_EXCEPTION:UNKNOWN')
    source=inbox(operation_id=op.operation_id,operation_state='TERMINAL_FAILED',
        operation_last_error='DECISION_ENGINE_EXCEPTION:UNKNOWN',control_mode='AVA_AUTO',
        communication_disposition='ACTIVE',last_inbound_message_id=op.inbound_telegram_message_id,
        operation_inbound_message_id=op.inbound_telegram_message_id,generation_obligation={'required':True},
        candidate_count=1)
    monkeypatch.setattr(RelationshipsRepository,'inbox_state',lambda *a,**k:{op.inbound_sender_telegram_user_id:source})
    recovery=OrdinaryQualityRecoveryService(connection)
    if changed!='none':
        if changed=='new_inbound':source['last_inbound_message_id']+=1
        if changed=='answered':source['last_visible_outbound_at']=source['last_customer_inbound_at']
        if changed=='uncertain':source['uncertain_operations']=[{'operationId':'protected'}]
        if changed=='manual':source['control_mode']='HUMAN_OPERATOR'
        if changed=='exhausted':
            with connection() as c:
                c.execute('UPDATE ordinary_generation_budgets SET candidate_count=2 WHERE operation_id=%s',(op.operation_id,))
        before=ordinary.get(op.operation_id)
        with pytest.raises(ValueError):
            recovery.resume(op.operation_id,creator_profile_id=2,fanvue_account_id=2,owner=owner)
        assert ordinary.get(op.operation_id)==before and len(provider.calls)==1
        return
    scheduled=recovery.resume(op.operation_id,creator_profile_id=2,fanvue_account_id=2,owner=owner)
    assert scheduled.operation_id==op.operation_id and scheduled.state.value=='RETRYABLE'
    assert budget.read(op.operation_id)['candidate_count']==1
    assert budget.read(op.operation_id)['provider_attempt_count']==1
    assert scheduled.delivery_payload['qualityFailureRecoveryHistory']['lastError']=='DECISION_ENGINE_EXCEPTION:UNKNOWN'
    assert not budget.read(op.operation_id)['correction_started']
    with pytest.raises(ValueError,match='NOT_ELIGIBLE'):
        recovery.resume(op.operation_id,creator_profile_id=2,fanvue_account_id=2,owner=owner)

import hashlib
import json
from dataclasses import replace
from unittest.mock import Mock
import pytest
from test_ordinary_generation_budget import setup, connection, Provider, pipeline
from test_conversation_lifecycle_closure import inbox
from test_relevance_repair import WORK, CANDIDATE
from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.ordinary_candidate_revalidation_service import OrdinaryCandidateRevalidationService
from app.repositories.relationships_repository import RelationshipsRepository


def exhausted(setup,monkeypatch):
    ordinary,budget,owner,make=setup
    op=make(WORK)
    with connection() as c:
        c.execute("UPDATE ordinary_chat_reply_operations SET delivery_payload=%s::jsonb WHERE operation_id=%s",
                  (json.dumps({'attentionInvestment':{'meaningfulObligation':True}}),op.operation_id))
    op=ordinary.get(op.operation_id)
    provider=Provider('Your work sounds busy.',CANDIDATE)
    service=OrdinaryReplyGenerationService(budget,authorize=Mock(),client_factory=lambda _:provider)
    lifecycle=OrdinaryChatReplyService(repository=ordinary,worker_id=owner)
    result=service.execute(op,None,owner=owner,initial=pipeline(op,provider,['FOREGROUND_SEMANTIC_RELEVANCE']))
    lifecycle.generated(op,result)
    with connection() as c:
        c.execute('UPDATE ordinary_chat_reply_operations SET next_retry_at=now() WHERE operation_id=%s',(op.operation_id,))
    op=ordinary.claim_generation(op.operation_id,owner=owner)
    result=service.execute(op,None,owner=owner,initial=Mock(side_effect=AssertionError('new pipeline')))
    result.diagnostic_metadata['conversationQualityReasons']=['FOREGROUND_SEMANTIC_RELEVANCE']
    result.diagnostic_metadata['qualityRejectionHandoff']={'authority':'sanitized_fixture'}
    final=lifecycle.generated(op,result)
    assert final.state.value=='SUPPRESSED'
    source=inbox(operation_id=op.operation_id,operation_state='SUPPRESSED',
        operation_last_error=final.last_error,control_mode='AVA_AUTO',communication_disposition='ACTIVE',
        last_inbound_message_id=op.inbound_telegram_message_id,operation_inbound_message_id=op.inbound_telegram_message_id,
        generation_obligation={'required':True},candidate_count=2)
    monkeypatch.setattr(RelationshipsRepository,'inbox_state',lambda *a,**k:{op.inbound_sender_telegram_user_id:source})
    return final,provider,source


@pytest.mark.parametrize('changed',['none','new_inbound','answered','uncertain','manual','hash','remaining_quality','candidate_change','rewrite'])
def test_immutable_zero_generation(setup,monkeypatch,changed):
    ordinary,budget,owner,_=setup
    op,provider,source=exhausted(setup,monkeypatch)
    sha=hashlib.sha256(CANDIDATE.encode()).hexdigest()
    if changed=='new_inbound':source['last_inbound_message_id']+=1
    if changed=='answered':source['last_visible_outbound_at']=source['last_customer_inbound_at']
    if changed=='uncertain':source['uncertain_operations']=[{'operationId':'protected'}]
    if changed=='manual':source['control_mode']='HUMAN_OPERATOR'
    if changed=='hash':sha='0'*64
    if changed=='candidate_change':
        with connection() as c:
            c.execute("UPDATE ordinary_chat_reply_operations SET response_text='changed' WHERE operation_id=%s",(op.operation_id,))
    if changed=='remaining_quality':
        with connection() as c:
            c.execute("""UPDATE ordinary_generation_budgets SET result_snapshot=jsonb_set(result_snapshot,
                '{diagnostic_metadata,conversationQualityReasons}',%s::jsonb) WHERE operation_id=%s""",
                (json.dumps(['FOREGROUND_SEMANTIC_RELEVANCE','UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM']),op.operation_id))
    if changed=='rewrite':
        from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
        original=AvaNaturalConversationPolicy.evaluate
        def rewrite(self,**kwargs):
            value=original(self,**kwargs)
            return replace(value,text='Changed by natural policy.',repaired=True)
        monkeypatch.setattr(AvaNaturalConversationPolicy,'evaluate',rewrite)
    before=ordinary.get(op.operation_id);before_budget=budget.read(op.operation_id)
    attempts=ordinary.generation_attempts(op.operation_id)
    recovery=OrdinaryCandidateRevalidationService(connection)
    def invoke():return recovery.revalidate(op.operation_id,expected_sha256=sha,
        creator_profile_id=2,fanvue_account_id=2,owner=owner)
    if changed!='none':
        with pytest.raises(ValueError):invoke()
        assert ordinary.get(op.operation_id)==before
        assert budget.read(op.operation_id)==before_budget
    else:
        final=invoke()
        assert final.state.value=='RETRYABLE' and final.response_text==CANDIDATE
        assert not final.delivery_payload['qualityCorrectiveRetry']['required']
        assert final.send_attempt_count==0 and final.next_retry_at==final.scheduled_delivery_at
        assert final.max_send_attempts==1
        after=budget.read(op.operation_id)
        assert after['candidate_count']==2 and after['provider_attempt_count']==2
        assert after['events'][:len(before_budget['events'])]==before_budget['events']
        assert ordinary.generation_attempts(op.operation_id)==attempts
        assert after['context_snapshot']==before_budget['context_snapshot']
        with pytest.raises(ValueError):invoke()
    assert len(provider.calls)==2

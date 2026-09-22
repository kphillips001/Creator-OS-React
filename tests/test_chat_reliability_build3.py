from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
import pytest

from app.models.telegram_inbound import TelegramInboundPayload
from app.models.telegram_media_turn_input import TelegramMediaTurnInput
from app.services.telegram_inbound_adapter import TelegramInboundAdapter, InvalidTelegramInboundError
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.stranded_reply_assessment import StrandedReplyEvidence, StrandedReplyAssessment
from app.services.customer_media_multimodal_decision_engine import CustomerMediaMultimodalDecisionEngine
from app.services.relationships_service import RelationshipsService
from test_conversation_lifecycle_closure import inbox


def visual():
    owner = str(uuid4())
    return dict(operation_id=str(uuid4()), media_turn_id=str(uuid4()),
        response_policy='SELFIE_COMPLIMENT_ELIGIBLE', attachment_ids=[str(uuid4())],
        attachment_paths=['isolated-image.jpg'], turn_authority=dict(
            response_operation_id=owner, telegram_user_id=42, telegram_chat_id=42,
            member_message_ids=[100,101,102], obligations=['ACKNOWLEDGE_SELF_PHOTO'], associated_text=''))


@pytest.mark.parametrize('text', ['', "that's me", "that's me\nPutting a face to the name"])
def test_typed_media_roundtrip_no_fabrication(text):
    v=visual(); v['turn_authority']['associated_text']=text
    op=SimpleNamespace(operation_id=v['turn_authority']['response_operation_id'],
        delivery_payload={'current_turn_visual_context':v}, inbound_message_text='',
        inbound_sender_telegram_user_id=42,telegram_chat_id=42,inbound_telegram_message_id=100,
        inbound_received_at=None)
    payload=OrdinaryChatReplyService.retry_payload(None,op)
    TelegramInboundAdapter._validate_payload(payload)
    assert payload.message_text=='' and payload.media_turn_input.associated_text==text
    assert payload.media_turn_input.obligations==('ACKNOWLEDGE_SELF_PHOTO',)
    assert payload.current_turn_visual_context==v
    request=CustomerMediaMultimodalDecisionEngine()._request('',[],{},v)
    assert request['customer_text']==(text or None)
    assert request['image_paths']==('isolated-image.jpg',)
    assert request['conversation_momentum']['meaningfulInvestment']
    assert 'ACKNOWLEDGE_SELF_PHOTO' in request['system']


@pytest.mark.parametrize('field,value', [('telegram_user_id',7),('telegram_chat_id',7),
    ('response_operation_id',str(uuid4())),('member_message_ids',[103])])
def test_media_authority_rejects_mismatched_identity(field,value):
    v=visual(); owner=v['turn_authority']['response_operation_id'];v['turn_authority'][field]=value
    with pytest.raises(ValueError):
        TelegramMediaTurnInput.from_context(v,operation_id=owner,user_id=42,chat_id=42,message_id=100)


def test_empty_untyped_rejected_and_text_unchanged():
    payload=TelegramInboundPayload(42,42,'',100)
    with pytest.raises(InvalidTelegramInboundError): TelegramInboundAdapter._validate_payload(payload)
    TelegramInboundAdapter._validate_payload(replace(payload,message_text='Hello'))


@pytest.mark.parametrize('latest,required',[(102,True),(103,False)])
def test_later_member_does_not_hide_media_obligation(latest,required):
    source=inbox(last_inbound_message_id=latest,operation_inbound_message_id=100,
        burst_freshness_telegram_message_id=100,media_turn_member_watermark=102,
        control_mode='AVA_AUTO',communication_disposition='ACTIVE',inbound_message_text='',
        latest_inbound_text='lol',operation_state='TERMINAL_FAILED',candidate_count=0,
        generation_obligation={'required':True,'obligations':['ACKNOWLEDGE_SELF_PHOTO']})
    assert RelationshipsService._operational_projection(source)['responseObligation']['required']==required


def evidence(**kw):
    value=dict(operation_id='isolated',state='SUPPRESSED',reason='QUALITY_REJECTED',
        obligations=('RESPOND_TO_GREETING',),fresh=True,control_eligible=True,market_allowed=True)
    value.update(kw);return StrandedReplyEvidence(**value)


@pytest.mark.parametrize('attempts',[0,1,2,5])
def test_missing_row_never_unused_budget(attempts):
    result=StrandedReplyAssessment.assess(evidence(legacy_generation_attempts=attempts))
    assert result['classification']=='UNKNOWN_LINEAGE_HUMAN_REQUIRED'
    assert result['historicalCandidateConsumption'] is None
    assert result['remainingProvenCandidateBudget'] is None


@pytest.mark.parametrize('count,category,remaining',[(0,'RECOVERABLE_WITH_REMAINING_BUDGET',2),
    (1,'RECOVERABLE_WITH_REMAINING_BUDGET',1),(2,'EXHAUSTED',0)])
def test_complete_consumption_preserved(count,category,remaining):
    r=StrandedReplyAssessment.assess(evidence(candidate_count=count,provider_attempt_count=count,
        complete_lifetime_evidence=True,correction_started=False))
    assert r['classification']==category and r['remainingProvenCandidateBudget']==remaining
    assert not r['executionAuthorized']


@pytest.mark.parametrize('changes,category',[
    ({'reason':'quality_corrective_retry_exhausted:FINAL_REPETITION_FAILURE'},'EXHAUSTED'),
    ({'correction_started':True},'EXHAUSTED'),
    ({'provider_attempt_count':3},'EXHAUSTED'),
    ({'state':'SEND_UNCERTAIN'},'POLICY_BLOCKED'),
    ({'delivery_uncertain':True},'POLICY_BLOCKED'),
    ({'reason':'OPERATOR_CANCELLED_PREPARED_REPLY'},'POLICY_BLOCKED'),
    ({'control_eligible':False},'POLICY_BLOCKED'),
    ({'control_eligible':None},'POLICY_BLOCKED'),
    ({'fresh':False},'POLICY_BLOCKED'),
    ({'obligations':()},'POLICY_BLOCKED'),
    ({'market_allowed':False},'POLICY_BLOCKED'),
    ({'market_allowed':None},'POLICY_BLOCKED'),
    ({'active_owner':True},'POLICY_BLOCKED'),
    ({'provider_in_flight':True},'POLICY_BLOCKED'),
    ({'send_attempt_count':1},'POLICY_BLOCKED'),
])
def test_blockers_are_not_recovery_permission(changes,category):
    e=evidence(candidate_count=1,provider_attempt_count=1,complete_lifetime_evidence=True)
    r=StrandedReplyAssessment.assess(replace(e,**changes))
    assert r['classification']==category
    assert r['recoveryMechanism'] is None


def test_exact_candidate_supported_revalidation_only():
    e=evidence(candidate_count=2,provider_attempt_count=2,complete_lifetime_evidence=True,
        retained_candidate_hash='a'*64, reason='quality_corrective_retry_exhausted:FOREGROUND_SEMANTIC_RELEVANCE',
        certified_revalidation_mechanism=StrandedReplyAssessment.REVALIDATION)
    assert StrandedReplyAssessment.assess(e)['classification']=='REVALIDATABLE_EXISTING_CANDIDATE'
    assert StrandedReplyAssessment.assess(replace(e,reason='quality_corrective_retry_exhausted:FINAL_REPETITION_FAILURE'))['classification']=='EXHAUSTED'


def test_market_reset_does_not_reset_lifetime_or_authorize_commerce():
    e=evidence(reason='MEDIUM_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED')
    r=StrandedReplyAssessment.assess(e)
    assert r['classification']=='UNKNOWN_LINEAGE_HUMAN_REQUIRED'
    assert r==StrandedReplyAssessment.assess(e)
    assert not r['historicalOfferAuthority']
    exhausted=replace(e,candidate_count=2,provider_attempt_count=2,complete_lifetime_evidence=True)
    assert StrandedReplyAssessment.assess(exhausted)['classification']=='EXHAUSTED'


def test_started_zero_candidate_phase_is_not_silently_replayed():
    r=StrandedReplyAssessment.assess(evidence(candidate_count=0,provider_attempt_count=0,
        complete_lifetime_evidence=True,initial_started=True))
    assert r['recoveryMechanism'] is None and not r['executionAuthorized']


def test_associated_self_presentation_reaches_one_existing_model_call():
    from unit.test_customer_media_vision_response import sdk_output, observation
    v=visual(); v['turn_authority']['associated_text']="that's me"
    calls=[]
    def runner(request):
        calls.append(request)
        return sdk_output('Great smile.',[observation(attachment_id=v['attachment_ids'][0],
            person_visible=True,person_count=1,smiling=True)])
    result=CustomerMediaMultimodalDecisionEngine(runner=runner).process_message('42','',[],
        {'current_turn_visual_context':v,'persona':{'name':'Ava'}})
    assert len(calls)==1
    assert calls[0]['business_context']['persona']=={'name':'Ava'}
    assert calls[0]['customer_text']=="that's me"
    assert result['visual_analysis']['visual_attestation']['self_presentation_authority']


@pytest.mark.parametrize('count,category',[(1,'UNKNOWN_LINEAGE_HUMAN_REQUIRED'),(2,'EXHAUSTED')])
def test_retained_legacy_candidates_prove_lower_bound_only(count,category):
    op={'operation_id':'legacy','state':'SUPPRESSED','generation_attempt_count':5}
    attempts=[{'operation_id':'legacy','candidate_text':'retained'} for _ in range(count)]
    r=StrandedReplyAssessment.from_persisted(op,None,attempts,obligations=['ANSWER_DIRECT_QUESTION'],
        fresh=True,control_eligible=True,market_allowed=True)
    assert r['classification']==category
    assert r['historicalCandidateConsumption'] is None
    assert r['provenCandidateLowerBound']==count

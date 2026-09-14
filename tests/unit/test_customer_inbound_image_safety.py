import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models.customer_inbound_image_safety import (
    CustomerImageResponsePolicy, CustomerImageSafetyState,
    clear_ava_explicit_solicitation,
)
from app.services.customer_inbound_image_safety_service import CustomerInboundImageSafetyService
from app.repositories.customer_inbound_image_safety_repository import CustomerInboundImageSafetyRepository


def service(detections, **thresholds):
    return CustomerInboundImageSafetyService(
        repository=object(), runner=lambda _path:detections, **thresholds)


@pytest.mark.parametrize("fixture_name",("ordinary_male_selfie","ordinary_person","clothed_customer","no_person"))
def test_synthetic_normal_fixtures_are_non_explicit(fixture_name):
    result=service([]).classify(fixture_name,"synthetic.jpg")
    assert result.state is CustomerImageSafetyState.NORMAL_NON_EXPLICIT


def test_suggestive_and_non_genital_nudity_remain_distinct():
    suggestive=service([{'class':'MALE_GENITALIA_COVERED','score':.70}]).classify('a','x')
    nudity=service([{'class':'FEMALE_BREAST_EXPOSED','score':.82}]).classify('b','x')
    assert suggestive.state is CustomerImageSafetyState.SUGGESTIVE_NON_EXPLICIT
    assert nudity.state is CustomerImageSafetyState.NUDITY_NON_GENITAL


@pytest.mark.parametrize("label",("MALE_GENITALIA_EXPOSED","FEMALE_GENITALIA_EXPOSED","ANUS_EXPOSED"))
def test_explicit_genital_labels_cross_calibrated_threshold(label):
    result=service([{'class':label,'score':.66}]).classify('a','x')
    assert result.state is CustomerImageSafetyState.EXPLICIT_GENITAL
    assert result.labels[0].threshold==.35
    assert result.classifier=='nudenet'


def test_low_nonzero_score_is_not_explicit_and_material_score_is_explicit():
    low=service([{'class':'MALE_GENITALIA_EXPOSED','score':.12}]).classify('a','x')
    near=service([{'class':'MALE_GENITALIA_EXPOSED','score':.58}]).classify('b','x')
    assert low.state is CustomerImageSafetyState.NORMAL_NON_EXPLICIT
    assert near.state is CustomerImageSafetyState.EXPLICIT_GENITAL


def test_live_explicit_signal_regression_is_explicit():
    result=service([{'class':'MALE_GENITALIA_EXPOSED','score':.4434622526}]).classify('a','x')
    assert result.state is CustomerImageSafetyState.EXPLICIT_GENITAL
    assert result.state is not CustomerImageSafetyState.NORMAL_NON_EXPLICIT
    policy=CustomerInboundImageSafetyService.policy(result.state,prior_boundaries=1)
    assert policy.policy is CustomerImageResponsePolicy.FIRM_EXPLICIT_BOUNDARY
    assert not policy.selfie_eligible
    assert CustomerInboundImageSafetyRepository.serialized_labels(result.labels)==[{
        'label':'MALE_GENITALIA_EXPOSED','confidence':.4434622526,
        'threshold':.35}]


@pytest.mark.parametrize('score',(.0,.05,.12,.20,.34))
def test_incidental_explicit_label_noise_below_floor_may_remain_normal(score):
    result=service([{'class':'MALE_GENITALIA_EXPOSED','score':score}]).classify('a','x')
    assert result.state is CustomerImageSafetyState.NORMAL_NON_EXPLICIT


@pytest.mark.parametrize('label',(
    'MALE_GENITALIA_EXPOSED','FEMALE_GENITALIA_EXPOSED','ANUS_EXPOSED'))
def test_material_explicit_signal_for_every_exposed_class_is_explicit(label):
    assert service([{'class':label,'score':.40}]).classify(
        'a','x').state is CustomerImageSafetyState.EXPLICIT_GENITAL


def test_exposed_genital_threshold_must_be_bounded():
    with pytest.raises(ValueError):
        service([],exposed_genital_threshold=1.01)


@pytest.mark.parametrize('label',(
    'MALE_GENITALIA_EXPOSED','FEMALE_GENITALIA_EXPOSED','ANUS_EXPOSED'))
@pytest.mark.parametrize('score,explicit',(
    (.0,False),(.10,False),(.20,False),(.34,False),(.3499,False),
    (.35,True),(.3501,True),(.4434622526,True),(.50,True),(.65,True),(.90,True)))
def test_exposed_genital_threshold_boundaries(label,score,explicit):
    result=service([{'class':label,'score':score}]).classify('a','x')
    expected=(CustomerImageSafetyState.EXPLICIT_GENITAL if explicit
              else CustomerImageSafetyState.NORMAL_NON_EXPLICIT)
    assert result.state is expected


def test_classifier_failure_is_unclassifiable_and_contains_no_description():
    result=service([{'error':'decode failed'}]).classify('a','x')
    assert result.state is CustomerImageSafetyState.UNCLASSIFIABLE
    assert result.labels==()
    assert not hasattr(result,'description')


def test_album_aggregation_is_conservative():
    s=CustomerInboundImageSafetyService.aggregate
    assert s([CustomerImageSafetyState.NORMAL_NON_EXPLICIT,CustomerImageSafetyState.EXPLICIT_GENITAL]) is CustomerImageSafetyState.EXPLICIT_GENITAL
    assert s([CustomerImageSafetyState.NORMAL_NON_EXPLICIT,CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED]) is CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED


def test_album_material_explicit_signal_fails_closed():
    states=(service([]).classify('safe','a').state,
            service([{'class':'ANUS_EXPOSED','score':.40}]).classify('signal','b').state)
    aggregate=CustomerInboundImageSafetyService.aggregate(states)
    assert aggregate is CustomerImageSafetyState.EXPLICIT_GENITAL
    assert CustomerInboundImageSafetyService.policy(
        aggregate).policy is CustomerImageResponsePolicy.POLITE_EXPLICIT_BOUNDARY


def test_only_structured_immediate_ava_evidence_solicits_explicit_media():
    assert clear_ava_explicit_solicitation([{'direction':'outbound','sender_type':'ava','metadata':{'customer_image_solicitation':'EXPLICIT_GENITAL_IMAGE'}}])
    assert not clear_ava_explicit_solicitation([{'direction':'outbound','sender_type':'ava','text':'you are so hot','metadata':{'flirty':True,'customer_purchased_explicit':True}}])


def test_explicit_policy_overrides_selfie_and_repeats_become_firmer():
    policy=CustomerInboundImageSafetyService.policy(CustomerImageSafetyState.EXPLICIT_GENITAL)
    repeated=CustomerInboundImageSafetyService.policy(CustomerImageSafetyState.EXPLICIT_GENITAL,prior_boundaries=1)
    solicited=CustomerInboundImageSafetyService.policy(CustomerImageSafetyState.EXPLICIT_GENITAL,clearly_solicited=True)
    assert policy.policy is CustomerImageResponsePolicy.POLITE_EXPLICIT_BOUNDARY
    assert repeated.policy is CustomerImageResponsePolicy.FIRM_EXPLICIT_BOUNDARY
    assert solicited.policy is CustomerImageResponsePolicy.SOLICITED_EXPLICIT_MEDIA
    assert not policy.selfie_eligible
    assert not policy.generation_allowed and policy.response_text==''


@pytest.mark.parametrize("state,expected",(
 (CustomerImageSafetyState.NORMAL_NON_EXPLICIT,True),
 (CustomerImageSafetyState.SUGGESTIVE_NON_EXPLICIT,False),
 (CustomerImageSafetyState.NUDITY_NON_GENITAL,False),
 (CustomerImageSafetyState.AMBIGUOUS_REVIEW_REQUIRED,False),
 (CustomerImageSafetyState.UNCLASSIFIABLE,False)))
def test_selfie_gate_is_explicit(state,expected):
    assert CustomerInboundImageSafetyService.policy(state).selfie_eligible is expected


class Repo:
    def __init__(self):self.claims=0;self.saved=[];self.finished=[]
    def schedule_and_claim(self,operation_id,**_):self.claims+=1;return ({'operation_id':operation_id,'album_finalize_after':datetime.now(timezone.utc)-timedelta(seconds=1),'grouped_id':'g','creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3},self.claims==1)
    def ready_attachments(self,_):return [{'attachment_id':'normal','position':0,'normalized_path':'a'},{'attachment_id':'explicit','position':1,'normalized_path':'b'}]
    def attachment_states(self,_):return ('READY_FOR_ANALYSIS','READY_FOR_ANALYSIS')
    def existing_results(self,_):return []
    def save_result(self,**values):self.saved.append(values);return values
    def boundary_count(self,**_):return 0
    def finish(self,*args,**values):self.finished.append(values)
    def fail(self,*_):raise AssertionError('unexpected failure')


def test_album_finalizes_once_orders_all_attachments_and_persists_one_aggregate():
    repo=Repo()
    def runner(path):return [{'class':'MALE_GENITALIA_EXPOSED','score':.9}] if str(path)=='b' else []
    svc=CustomerInboundImageSafetyService(repository=repo,runner=runner,album_window_ms=1)
    operation={'operation_id':'op','grouped_id':'g','creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3}
    first=asyncio.run(svc.process_operation(operation));second=asyncio.run(svc.process_operation(operation))
    assert first.policy is CustomerImageResponsePolicy.POLITE_EXPLICIT_BOUNDARY
    assert second is None
    assert [x['position'] for x in repo.saved]==[0,1]
    assert len(repo.finished)==1 and repo.finished[0]['state']=='EXPLICIT_GENITAL'


def test_persisted_explicit_result_survives_recovery_without_nudenet_rerun():
    class RecoveryRepo(Repo):
        def ready_attachments(self,_):
            return [{'attachment_id':'signal','position':0,'normalized_path':'missing'}]
        def attachment_states(self,_):return ('READY_FOR_ANALYSIS',)
        def existing_results(self,_):
            return [{'attachment_id':'signal','safety_state':'EXPLICIT_GENITAL',
                     'classifier':'nudenet','classifier_version':'3.4.2',
                     'classified_at':datetime.now(timezone.utc)}]
    repo=RecoveryRepo()
    svc=CustomerInboundImageSafetyService(
        repository=repo,runner=lambda _:pytest.fail('NudeNet must not rerun'))
    result=asyncio.run(svc.process_operation({
        'operation_id':'recovered','grouped_id':'g','creator_profile_id':1,
        'fanvue_account_id':2,'telegram_user_id':3}))
    assert result.policy is CustomerImageResponsePolicy.POLITE_EXPLICIT_BOUNDARY
    assert repo.saved==[]
    assert repo.finished[0]['state']=='EXPLICIT_GENITAL'

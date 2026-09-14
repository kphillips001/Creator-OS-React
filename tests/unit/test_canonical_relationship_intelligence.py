from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.services.canonical_relationship_fact_service import CanonicalRelationshipFactService,CanonicalRelationshipContextPreviewService

def fact(subject_type,subject_id,obj,category='RELATIONSHIP',relation='owns_pet',policy='NORMAL_CONTEXT',aliases=()):
 return {'fact_id':uuid4(),'subject_type':subject_type,'subject_id':subject_id,'relation':relation,'object_type':'ENTITY','object_value':obj,'object_data':{'aliases':list(aliases)},'attributes':{'species':'dog'},'category':category,'source_platform':'FANVUE','source_type':'OPERATOR_VERIFIED','verification_method':'OPERATOR_REVIEW','confidence':1,'usage_policy':policy}
class Repo:
 def __init__(self,rows=(),valid=True):self.rows=list(rows);self.valid=valid
 def list_current(self,**_):return self.rows
 def validate_subject(self,**_):return self.valid

def test_bully_and_jojo_preserve_subject_ownership_and_alias():
 s=CanonicalRelationshipFactService(Repo([fact('CUSTOMER',7245,'Bully'),fact('CREATOR',2,'JoJo',category='CREATOR_SELF',aliases=['Joey'])]))
 bully=s.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='Bully was crazy')
 assert bully['facts'][0]['subject']=={'type':'CUSTOMER','id':'7245'}
 joey=s.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message="How's Joey?")
 assert joey['facts'][0]['object']['value']=='JoJo' and joey['facts'][0]['subject']['type']=='CREATOR'

def test_silent_context_is_not_recited_and_preview_is_production_retrieval():
 s=CanonicalRelationshipFactService(Repo([fact('CUSTOMER',7245,'Ava is virtual',category='SILENT_CONTEXT',relation='understands',policy='SILENT_CONTEXT')]))
 assert s.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='hello')['facts']==[]
 values=dict(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='virtual creator')
 assert s.context_preview(**values)==s.retrieve(**values)
 assert s.retrieve(**values)['facts']==[] and len(s.retrieve(**values)['silentFacts'])==1

def test_unrelated_facts_excluded_and_result_bounded():
 rows=[fact('CUSTOMER',1,f'Bully {i}') for i in range(8)]
 result=CanonicalRelationshipFactService(Repo(rows),max_facts=4).retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=1,message='Bully')
 assert len(result['facts'])==4 and any(x['reason']=='BOUNDED_LIMIT' for x in result['exclusions'])

def test_wrong_scope_and_raw_x_promotion_fail_closed():
 values=dict(creator_profile_id=2,fanvue_account_id=2,subject_type='CUSTOMER',subject_id=7245,relation='owns_pet',object_type='ENTITY',object_value='Bully',category='RELATIONSHIP',source_platform='X',source_type='X_OBSERVATION',verification_method='RAW_OBSERVATION',confidence=.5,usage_policy='NORMAL_CONTEXT',idempotency_key='x')
 with pytest.raises(ValueError,match='subject'):CanonicalRelationshipFactService(Repo(valid=False)).preview_create(**values)
 with pytest.raises(ValueError,match='Raw observation'):CanonicalRelationshipFactService(Repo()).preview_create(**values)

def test_financial_dossier_is_not_supported_taxonomy():
 values=dict(creator_profile_id=2,fanvue_account_id=2,subject_type='CUSTOMER',subject_id=7245,relation='lifetime_spend',object_type='CONCEPT',object_value='$119.96',category='RELATIONSHIP',source_platform='PROVIDER',source_type='PROVIDER_VERIFIED',verification_method='PROVIDER',confidence=1,usage_policy='NORMAL_CONTEXT',idempotency_key='money')
 with pytest.raises(ValueError,match='taxonomy'):CanonicalRelationshipFactService(Repo()).preview_create(**values)

def test_context_preview_reuses_fact_path_and_keeps_commerce_external():
 facts=CanonicalRelationshipFactService(Repo([fact('CUSTOMER',7245,'Bully')]))
 customer=SimpleNamespace(customer_id='2:7245',provider_identities=(SimpleNamespace(provider='fanvue',provider_customer_id='ae25'),))
 customers=SimpleNamespace(get_by_legacy_fanvue_user=lambda **_:customer)
 profile=SimpleNamespace(purchase_count=5,lifetime_gross_minor=11996,lifetime_net_minor=9596,last_purchase_at='Aug 29')
 commerce=SimpleNamespace(get_by_buyer_uuid=lambda **_:profile)
 snapshot=SimpleNamespace(sections={},excluded_items=())
 snapshots=SimpleNamespace(for_customer=lambda **_:snapshot)
 preview=CanonicalRelationshipContextPreviewService(facts,customers,commerce,snapshots).preview(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='Bully')
 assert preview['relationshipContext']==facts.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='Bully')
 assert preview['commerceSummary']['lifetimeGrossMinor']==11996
 assert preview['customerSnapshot'] is snapshot
 assert all(item['relation']!='lifetime_spend' for item in preview['relationshipContext']['facts'])

def test_isolated_wally_examples_are_selective_and_avoid_dossier_dump():
 rows=[fact('CUSTOMER',7245,'Bully'),fact('CREATOR',2,'JoJo',category='CREATOR_SELF',aliases=['Joey']),fact('CUSTOMER',7245,'Recurring AI Edits',category='RECURRING_BEHAVIOR',relation='frequently_creates'),fact('CUSTOMER',7245,'AI Awareness',category='SILENT_CONTEXT',relation='understands',policy='SILENT_CONTEXT')]
 service=CanonicalRelationshipFactService(Repo(rows))
 bully=service.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='Bully made another appearance')
 assert {item['object']['value'] for item in bully['facts']}=={'Bully','Recurring AI Edits'}
 assert all(item['object']['value']!='JoJo' for item in bully['facts']) and bully['silentFacts']==[]
 joey=service.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message="How's Joey?")
 assert [item['object']['value'] for item in joey['facts']]==['JoJo']
 ai=service.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='AI is getting crazy good lately')
 assert [item['object']['value'] for item in ai['silentFacts']]==['AI Awareness']
 hello=service.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message='Hey')
 assert hello['facts']==[] and hello['silentFacts']==[] and len(hello['exclusions'])==4

def test_wally_context_examples_preserve_ownership_qualifiers_and_silent_usage():
 bully=fact('CUSTOMER',7245,'Bully');bully['attributes']={'type':'dog','gender':'female'}
 jojo=fact('CREATOR',2,'JoJo',category='CREATOR_SELF',aliases=['Joey']);jojo['attributes']={'type':'dog','breed':'Staffordshire Bull Terrier','nickname':'Joey'}
 edits=fact('CUSTOMER',7245,'AI images of Wally with Ava',category='RECURRING_BEHAVIOR',relation='frequently_creates',aliases=['AI images','another one']);edits['object_type']='ACTIVITY'
 dogs=fact('CUSTOMER',7245,'Dogs sometimes included in Wally and Ava AI images',category='RECURRING_BEHAVIOR',relation='frequently_creates',aliases=['both dogs']);dogs['object_type']='ACTIVITY';dogs['attributes']={'inclusion_frequency':'sometimes','possible_participants':['Bully','JoJo','both'],'required':False}
 flirting=fact('CUSTOMER',7245,'AI-image flirting with Ava',relation='relationship_dynamic',aliases=['visual flirting']);flirting['object_type']='CONCEPT'
 exclusive=fact('CUSTOMER',7245,'Less commonly seen Ava content',category='PREFERENCE',relation='prefers',aliases=['something I do not normally get to see']);exclusive['object_type']='CONTENT_PREFERENCE'
 smile=fact('CUSTOMER',7245,"Facial beauty, especially a woman's smile",category='PREFERENCE',relation='prefers',aliases=['smile']);smile['object_type']='CONCEPT'
 awareness=fact('CUSTOMER',7245,"Ava's virtual and AI nature",category='IDENTITY_CONTEXT',relation='understands',policy='SILENT_CONTEXT',aliases=['AI awareness'])
 service=CanonicalRelationshipFactService(Repo([bully,jojo,edits,dogs,flirting,exclusive,smile,awareness]))
 values=lambda message:service.retrieve(creator_profile_id=2,fanvue_account_id=2,customer_id=7245,message=message)
 assert {x['object']['value'] for x in values('I made another one of us')['facts']}=={'AI images of Wally with Ava','AI-image flirting with Ava'}
 both=values('Got both dogs in this one')['facts'];assert {x['object']['value'] for x in both}=={'Bully','JoJo','AI images of Wally with Ava','Dogs sometimes included in Wally and Ava AI images'}
 joey=values("How's Joey?")['facts'];assert [x['object']['value'] for x in joey]==['JoJo']
 ai=values('AI is getting crazy good lately');assert [x['object']['value'] for x in ai['silentFacts']]==["Ava's virtual and AI nature"] and all(x['object']['value']!='Dogs sometimes included in Wally and Ava AI images' for x in ai['facts'])
 assert [x['object']['value'] for x in values("I want to see something I don't normally get to see")['facts']]==['Less commonly seen Ava content']
 hello=values('Hey');assert hello['facts']==[] and hello['silentFacts']==[]

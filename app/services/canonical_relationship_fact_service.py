"""Selective, non-recitative canonical relationship context."""
import re
from app.repositories.canonical_relationship_fact_repository import CanonicalRelationshipFactRepository

ALLOWED_RELATIONS={'owns_pet','prefers','frequently_creates','understands','knows','relationship_dynamic'}
ALLOWED_CATEGORIES={'IDENTITY_CONTEXT','RELATIONSHIP','PREFERENCE','RECURRING_BEHAVIOR','CREATOR_SELF','SILENT_CONTEXT'}
ALLOWED_SUBJECTS={'CUSTOMER','CREATOR'};ALLOWED_OBJECTS={'ENTITY','CONCEPT','ACTIVITY','CONTENT_PREFERENCE'}
ALLOWED_PLATFORMS={'FANVUE','TELEGRAM','X','CREATOR_OS','PROVIDER'}
ALLOWED_SOURCES={'OPERATOR_VERIFIED','FANVUE_CONVERSATION','TELEGRAM_CONVERSATION','X_OBSERVATION','CREATOR_CANONICAL','PROVIDER_VERIFIED'}
class CanonicalRelationshipFactService:
 def __init__(self,repository=None,max_facts=4):self.repository=repository or CanonicalRelationshipFactRepository();self.max_facts=max_facts
 def preview_create(self,**v):self._validate(v);return {'status':'READY','mutationPerformed':False,'fact':v}
 def create_verified(self,**v):self._validate(v);return self.repository.create(operator_source='CREATOR_OS_OPERATIONS',**v)
 def list_facts(self,*,creator_profile_id,fanvue_account_id,customer_id=None):return self.repository.list_current(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,customer_id=customer_id)
 def history(self,*,fact_id,creator_profile_id,fanvue_account_id):
  row=self.repository.history(fact_id=fact_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if not row:raise LookupError('Fact not found')
  return row
 def correct(self,*,fact_id,replacement,reason):self._validate(replacement);return self.repository.supersede(fact_id=fact_id,replacement={**replacement,'operator_source':'CREATOR_OS_OPERATIONS'},reason=reason,operator_source='CREATOR_OS_OPERATIONS')
 def deactivate(self,*,fact_id,reason):return self.repository.deactivate(fact_id=fact_id,reason=reason,operator_source='CREATOR_OS_OPERATIONS')
 def retrieve(self,*,creator_profile_id,fanvue_account_id,customer_id,message):
  facts=self.repository.list_current(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,customer_id=customer_id);tokens=set(re.findall(r"[a-z0-9]+",(message or '').lower()));selected=[];silent=[];excluded=[]
  for f in facts:
   relevant=self._relevant(f,tokens)
   if f['usage_policy']=='SILENT_CONTEXT':
    if not tokens&{'ai','virtual','creator'}:excluded.append({'factId':str(f['fact_id']),'reason':'SILENT_CONTEXT_NOT_RELEVANT'})
    else:silent.append(self._project(f))
    continue
   if not relevant:excluded.append({'factId':str(f['fact_id']),'reason':'NOT_RELEVANT'});continue
   if len(selected)>=self.max_facts:excluded.append({'factId':str(f['fact_id']),'reason':'BOUNDED_LIMIT'});continue
   selected.append(self._project(f))
  return {'facts':selected,'silentFacts':silent[:self.max_facts],'exclusions':excluded,'guidance':['Use only when naturally relevant.','Never recite a dossier or mention tracking.','Silent facts inform interpretation only; never state them proactively.','Do not mention financial values from relationship facts.']}
 def context_preview(self,**v):return self.retrieve(**v)
 def _validate(self,v):
  for k in ('creator_profile_id','fanvue_account_id','subject_type','subject_id','relation','object_type','object_value','category','source_platform','source_type','verification_method','confidence','usage_policy','idempotency_key'):
   if v.get(k) in (None,''):raise ValueError(f'{k} is required')
  if v['relation'] not in ALLOWED_RELATIONS or v['category'] not in ALLOWED_CATEGORIES or v['usage_policy'] not in {'NORMAL_CONTEXT','SILENT_CONTEXT'} or v['subject_type'] not in ALLOWED_SUBJECTS or v['object_type'] not in ALLOWED_OBJECTS or v['source_platform'] not in ALLOWED_PLATFORMS or v['source_type'] not in ALLOWED_SOURCES:raise ValueError('Unsupported fact taxonomy')
  if not 0<=float(v['confidence'])<=1:raise ValueError('confidence must be between 0 and 1')
  if not self.repository.validate_subject(creator_profile_id=v['creator_profile_id'],fanvue_account_id=v['fanvue_account_id'],subject_type=v['subject_type'],subject_id=v['subject_id']):raise ValueError('Canonical subject does not exist in scope')
  if v['source_type']=='X_OBSERVATION' and 'OPERATOR' not in v['verification_method'].upper():raise ValueError('Raw observation cannot be promoted to canonical fact')
 @staticmethod
 def _relevant(f,tokens):
  meaningful=lambda value:{token for token in re.findall(r"[a-z0-9]+",str(value).lower()) if len(token)>2 and token not in {'the','and','with','ava','wally','this','that','one'}}
  aliases=f.get('object_data',{}).get('aliases',[]);terms=meaningful(f['object_value'])
  for alias in aliases:terms|=meaningful(alias)
  attributes=f.get('attributes',{}) or {}
  pet_tokens={'dog','dogs','pet','pets'}
  if f['relation']=='owns_pet':
   names=meaningful(f['object_value'])
   for alias in aliases:names|=meaningful(alias)
   return bool(tokens&names) or bool(tokens&pet_tokens)
  if f['category']=='RECURRING_BEHAVIOR':
   if attributes.get('inclusion_frequency')=='sometimes':
    participants=set()
    for value in attributes.get('possible_participants',[]):participants|=meaningful(value)
    return bool(tokens&(pet_tokens|participants))
   return bool(tokens&terms) or bool(tokens&{'made','another','one','edit','edited','variation','variations','image','images','ai'})
  if f['relation']=='relationship_dynamic':
   return bool(tokens&terms) or bool(tokens&{'made','another','edit','edited','variation','variations','image','images','ai','flirt','flirting'})
  return bool(tokens&terms)
 @staticmethod
 def _project(f):return {'factId':str(f['fact_id']),'subject':{'type':f['subject_type'],'id':str(f['subject_id'])},'relation':f['relation'],'object':{'type':f['object_type'],'value':f['object_value'],'data':f.get('object_data',{})},'attributes':f.get('attributes',{}),'category':f['category'],'provenance':{'platform':f['source_platform'],'type':f['source_type'],'verificationMethod':f['verification_method'],'confidence':float(f['confidence'])},'usagePolicy':f['usage_policy']}

class CanonicalRelationshipContextPreviewService:
 def __init__(self,facts=None,customers=None,commerce=None,snapshots=None):
  self.facts=facts or CanonicalRelationshipFactService()
  if customers is None:
   from app.repositories.customer_repository import CustomerRepository
   customers=CustomerRepository()
  if commerce is None:
   from app.repositories.customer_commerce_repository import CustomerCommerceRepository
   commerce=CustomerCommerceRepository()
  if snapshots is None:
   from app.services.customer_snapshot_service import CustomerSnapshotService
   snapshots=CustomerSnapshotService()
  self.customers=customers;self.commerce=commerce;self.snapshots=snapshots
 def preview(self,*,creator_profile_id,fanvue_account_id,customer_id,message=''):
  customer=self.customers.get_by_legacy_fanvue_user(fanvue_account_id=fanvue_account_id,fanvue_user_id=customer_id)
  if not customer:raise LookupError('Canonical customer not found')
  fanvue=next(x for x in customer.provider_identities if x.provider=='fanvue')
  profile=self.commerce.get_by_buyer_uuid(creator_profile_id=creator_profile_id,external_fanvue_user_uuid=fanvue.provider_customer_id)
  snapshot=self.snapshots.for_customer(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,customer_id=customer_id)
  return {'relationshipContext':self.facts.retrieve(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,customer_id=customer_id,message=message),'customerSnapshot':snapshot,'conversationMemory':snapshot.sections.get('PERSONAL',())+snapshot.sections.get('INTERESTS',())+snapshot.sections.get('PREFERENCES',())+snapshot.sections.get('THINGS_TO_REMEMBER',()),'silentContext':snapshot.sections.get('SILENT_CONTEXT',()),'creatorContext':snapshot.sections.get('RELEVANT_CREATOR_FACTS',()),'excludedIntelligence':snapshot.excluded_items,'identitySummary':{'customerId':customer.customer_id,'providers':[x.provider for x in customer.provider_identities]},'commerceSummary':None if not profile else {'buyerStatus':profile.purchase_count>0,'lifetimeGrossMinor':profile.lifetime_gross_minor,'lifetimeNetMinor':profile.lifetime_net_minor,'purchaseCount':profile.purchase_count,'lastPurchaseAt':profile.last_purchase_at},'effectivePermissions':{'included':False,'reason':'CHANNEL_IDENTITY_REQUIRED'}}

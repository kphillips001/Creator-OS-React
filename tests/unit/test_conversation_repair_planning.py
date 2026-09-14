from copy import deepcopy
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.conversation_repair_proposal import RepairCategory,RepairRisk
from app.services.conversation_repair_planning_service import ConversationRepairPlanningService

SCOPE={'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,'telegram_chat_id':3,'relationship_key':'telegram:1:2:3'}

def analysis(scope='CONVERSATION_ONLY',root='COMMERCIAL_CLASSIFICATION',stale='CURRENT'):
 return {'analysisId':str(uuid4()),'staleState':stale,'findings':[{'findingId':'finding-1',
  'validatedScope':scope,'rootCauseCategory':root,'authoritativeEvidenceSummary':'COMPLIMENT_AVAILABILITY_CONTRADICTION',
  'whatHappened':'Availability language answered a compliment.','suggestedCorrection':'Require current evidence.',
  'severity':'MATERIAL','repairCandidate':scope in {'MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM'}}],
  'similarCaseSummary':{'similarCaseCount':0}}

class Analyses:
 def __init__(self,value):self.value=value
 def retrieve(self,*args,**kwargs):return deepcopy(self.value)
class AnalysisRepo:
 def __init__(self,count=0,fingerprint='a'*64):self.count=count;self.fingerprint=fingerprint
 def get(self,*args,**kwargs):return {'evidence_fingerprint':self.fingerprint}
 def similar(self,*args,**kwargs):return [{'relationship_key':f'r:{i}'} for i in range(self.count)]
 def structural_similar(self,*args,**kwargs):return []
class Repo:
 def __init__(self):self.rows={};self.events=[];self.authorizations={}
 def create(self,**v):
  row={**v,'created_at':datetime.now(timezone.utc),'expires_at':datetime.now(timezone.utc)+timedelta(minutes=20),
       'status':'PROPOSED','approved_by':None,'approved_at':None,'rejected_by':None,'rejected_at':None,'stale_reason':None}
  self.rows[str(v['proposal_id'])]=row;return row
 def event(self,*args,**kwargs):self.events.append((args,kwargs))
 def get(self,pid,**kwargs):return self.rows.get(str(pid))
 def approve(self,pid,*,current,operator,baseline_sha,**kwargs):
  row=self.rows[str(pid)]
  if str(pid) in self.authorizations:return self.authorizations[str(pid)],True
  if any(row[k]!=current[k] for k in ('evidence_fingerprint','failure_signature','validated_scope','signature')) or current['similar_case_count']<row['affected_relationship_count']-1:
   raise RuntimeError('REPAIR PROPOSAL OUT OF DATE')
  auth={'authorization_id':uuid4(),'proposal_id':pid,'repair_category':row['repair_category'],
   'validated_scope':row['validated_scope'],'behavioral_invariant':row['proposed_invariant'],
   'regression_requirements':row['regression_requirements'],'risk':row['risk'],
   'evidence_fingerprint':row['evidence_fingerprint'],'baseline_sha':baseline_sha,'approved_by':operator,'approved_at':datetime.now(timezone.utc),
   'expires_at':row['expires_at'],'consumed_at':None}
  self.authorizations[str(pid)]=auth;return auth,False

def service(value,count=0,repo=None):
 return ConversationRepairPlanningService(analyses=Analyses(value),analysis_repository=AnalysisRepo(count),
  repository=repo or Repo(),secret='test-secret',baseline_reader=lambda:'56ddbff52ba6136673dbeb82ab8c1f322f47b867')

@pytest.mark.parametrize('scope,reason',[
 ('CONVERSATION_ONLY','No structural evidence'),('OBSOLETE','superseded'),('AMBIGUOUS','Manual review')])
def test_ineligible_scopes_never_create_proposal(scope,reason):
 repo=Repo();result=service(analysis(scope),repo=repo).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 assert result['proposal'] is None and result['globalRepair']=='NOT_RECOMMENDED'
 assert reason in result['reason'] and repo.rows=={}

def test_multiple_without_current_shared_cause_has_no_candidate():
 result=service(analysis('MULTIPLE_CUSTOMERS'),0).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 assert result['proposal'] is None and result['globalRepair']=='NOT_RECOMMENDED'

@pytest.mark.parametrize('scope,count,expected', [('MULTIPLE_CUSTOMERS',1,2),('GLOBAL_SYSTEM',3,4)])
def test_systemic_scope_creates_frozen_server_owned_candidate(scope,count,expected):
 repo=Repo();result=service(analysis(scope),count,repo).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 proposal=result['proposal'];assert result['globalRepair']=='CANDIDATE'
 assert proposal['affected_relationship_count']==expected
 assert proposal['repair_category']=='COMMERCIAL_CLASSIFICATION_POLICY'
 assert proposal['risk'] in {'MEDIUM','HIGH'} and len(proposal['signature'])==64 if 'signature' in proposal else True
 assert 'Content-availability language requires authoritative current commercial evidence.'==proposal['proposed_invariant']
 assert any('genuine price' in item.lower() for item in proposal['regression_requirements'])
 assert 'customer' not in str(proposal.get('expected_mutation_entities','')).lower()

def test_stale_analysis_and_incompatible_root_cause_are_rejected():
 with pytest.raises(RuntimeError,match='RE-ANALYZE'):service(analysis('GLOBAL_SYSTEM',stale='STALE'),3).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 with pytest.raises(ValueError,match='compatible'):service(analysis('GLOBAL_SYSTEM',root='UNKNOWN'),3).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)

def test_closed_categories_and_server_risk_cannot_be_lowered():
 assert len(RepairCategory)==13 and {r.value for r in RepairRisk}=={'LOW','MEDIUM','HIGH'}
 assert ConversationRepairPlanningService._risk('SALES_BRAIN_POLICY','MULTIPLE_CUSTOMERS')=='HIGH'
 assert ConversationRepairPlanningService._risk('QUALITY_GATE_POLICY','GLOBAL_SYSTEM')=='HIGH'

def test_miroslav_isolated_vs_systemic_behavior():
 isolated=service(analysis('CONVERSATION_ONLY')).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 systemic=service(analysis('GLOBAL_SYSTEM'),3).plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)
 assert isolated['proposal'] is None
 assert systemic['proposal']['proposed_invariant'].startswith('Content-availability language requires')
 assert 'compliments' in systemic['proposal']['regression_requirements'][-1]

def test_source_finding_and_fingerprint_are_frozen_not_client_parameters():
 repo=Repo();aid=uuid4();result=service(analysis('GLOBAL_SYSTEM'),3,repo).plan(aid,finding_id='finding-1',operator='op',**SCOPE)
 row=repo.rows[str(result['proposal']['proposal_id'])]
 assert row['analysis_id']==aid and row['evidence_fingerprint']=='a'*64
 assert row['validated_scope']=='GLOBAL_SYSTEM' and row['failure_signature']=='COMPLIMENT_AVAILABILITY_CONTRADICTION'
 assert not any(word in str(row).lower() for word in ('powershell','apply_patch','delete from'))

def test_approval_is_idempotent_and_authorization_contains_only_frozen_fields():
 repo=Repo();analyses=Analyses(analysis('GLOBAL_SYSTEM'));ar=AnalysisRepo(3)
 svc=ConversationRepairPlanningService(analyses=analyses,analysis_repository=ar,repository=repo,secret='test-secret',baseline_reader=lambda:'56ddbff52ba6136673dbeb82ab8c1f322f47b867')
 planned=svc.plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE);pid=planned['proposal']['proposal_id']
 first=svc.approve(pid,operator='operator',**SCOPE);second=svc.approve(pid,operator='operator',**SCOPE)
 assert first['status']=='APPROVED_FOR_EXECUTION' and first['idempotentReplay'] is False
 assert second['idempotentReplay'] is True
 assert first['authorization']==second['authorization']
 assert first['authorization']['baseline_sha']=='56ddbff52ba6136673dbeb82ab8c1f322f47b867'
 assert 'violated_invariant' not in first['authorization'] and 'relationship_key' not in first['authorization']

@pytest.mark.parametrize('change',('fingerprint','signature','scope','threshold'))
def test_approval_revalidates_every_frozen_authority(change):
 repo=Repo();value=analysis('GLOBAL_SYSTEM');analyses=Analyses(value);ar=AnalysisRepo(3)
 svc=ConversationRepairPlanningService(analyses=analyses,analysis_repository=ar,repository=repo,secret='test-secret',baseline_reader=lambda:'56ddbff52ba6136673dbeb82ab8c1f322f47b867')
 pid=svc.plan(uuid4(),finding_id='finding-1',operator='op',**SCOPE)['proposal']['proposal_id']
 if change=='fingerprint':ar.fingerprint='d'*64
 elif change=='signature':value['findings'][0]['authoritativeEvidenceSummary']='CHANGED'
 elif change=='scope':value['findings'][0]['validatedScope']='MULTIPLE_CUSTOMERS'
 else:ar.count=0
 with pytest.raises(RuntimeError,match='OUT OF DATE'):svc.approve(pid,operator='operator',**SCOPE)

def test_migration_and_rollback_define_frozen_authorization_without_executor():
 forward=open('migrations/forward/20260914_130_conversation_repair_planning.sql',encoding='utf-8').read()
 rollback=open('migrations/rollback/20260914_130_conversation_repair_planning.sql',encoding='utf-8').read()
 for table in ('conversation_repair_proposals','conversation_repair_execution_authorizations','conversation_repair_events'):assert table in forward
 assert 'proposal_id UUID NOT NULL UNIQUE' in forward
 assert rollback.index('conversation_repair_events')<rollback.index('conversation_repair_proposals')

def test_approval_api_accepts_no_client_authority_fields(monkeypatch):
 from app.api import relationships as api
 from app.api.developer_authorization import require_developer_authorization
 class Relationships:
  def control_context(self,**scope):return {'telegram_chat_id':3}
 class Planning:
  def approve(self,pid,**scope):return {'status':'APPROVED_FOR_EXECUTION','seen':scope}
 monkeypatch.setattr(api,'_snapshot_scope',lambda:(1,2));monkeypatch.setattr(api,'RelationshipsService',Relationships)
 monkeypatch.setattr(api,'_repair_planning',lambda:Planning())
 application=FastAPI();application.include_router(api.router);application.dependency_overrides[require_developer_authorization]=lambda:True
 client=TestClient(application);pid=uuid4();url=f'/api/v1/relationships/telegram:1:2:3/conversation-repair-proposals/{pid}/approve'
 assert client.post(url,json={}).status_code==200
 assert client.post(url,json={'risk':'LOW'}).status_code==422

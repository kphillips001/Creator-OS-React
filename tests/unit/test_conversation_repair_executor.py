from datetime import datetime,timezone,timedelta
from uuid import uuid4
import pytest
from app.services.conversation_repair_executor_service import ConversationRepairExecutorService,WORKFLOWS

class EnabledGate:
 def require_enabled(self):return None

class Auths:
 def __init__(self,scope='GLOBAL_SYSTEM',category='QUALITY_GATE_POLICY',expired=False):
  self.auth={'authorization_id':uuid4(),'proposal_id':uuid4(),'repair_category':category,'validated_scope':scope,
   'behavioral_invariant':'Only evidence-grounded language is allowed.','regression_requirements':['original','similar','neighbor'],
   'risk':'HIGH','evidence_fingerprint':'a'*64,'expires_at':datetime.now(timezone.utc)+timedelta(minutes=-1 if expired else 10)}
  self.proposal={'proposal_id':self.auth['proposal_id'],'analysis_id':uuid4(),'status':'APPROVED_FOR_EXECUTION',
   'validated_scope':scope,'evidence_fingerprint':'a'*64,'failure_signature':'SIG','preserved_behavior':['neighbor']}
 def authorization(self,*args,**kwargs):return self.auth
 def get(self,*args,**kwargs):return self.proposal
class Analyses:
 def __init__(self,stale=False):self.stale=stale
 def retrieve(self,*args,**kwargs):return {'staleState':'STALE' if self.stale else 'CURRENT'}
class Repo:
 def __init__(self):self.run=None
 def claim(self,**v):
  if self.run:return self.run,True
  self.run={**v,'execution_id':uuid4(),'state':'AUTHORIZED','rollback_evidence':{}};return self.run,False
 def dispatched(self,eid,**v):self.run.update(v,state='EXECUTING');return self.run
 def get(self,*args,**kwargs):return self.run
 def finish(self,eid,**v):self.run.update(v);return self.run
class DevRepo:
 def __init__(self,result=None):self.result=result or {'status':'COMPLETED','final_report':{'filesModified':['app/services/conversation_quality_watch_service.py'],'tests':[{'exitCode':0}]}}
 def get_execution(self,eid):return self.result
class Developer:
 def __init__(self,result=None):self.calls=[];self.repository=DevRepo(result)
 def create_and_dispatch(self,**v):self.calls.append(v);return {'task':{'task_id':uuid4()},'execution':{'execution_id':uuid4()}}
SCOPE={'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,'telegram_chat_id':3,'relationship_key':'telegram:1:2:3'}
def make(auth=None,**kwargs):
 repo=Repo();dev=Developer(kwargs.pop('dev_result',None));svc=ConversationRepairExecutorService(repository=repo,authorization_repository=auth or Auths(),developer=dev,safety=kwargs.pop('safety',lambda:{'safe':True,'reason':None}),analyses=kwargs.pop('analyses',Analyses()),execution_gate=kwargs.pop('execution_gate',EnabledGate()));return svc,repo,dev

def test_closed_workflow_dispatch_contains_no_transcript_customer_or_arbitrary_parameters():
 assert set(WORKFLOWS)=={'COMMERCIAL_CLASSIFICATION_POLICY','COMMERCIAL_PROGRESSION_POLICY','SALES_BRAIN_POLICY','TURN_OBLIGATION_POLICY','QUALITY_GATE_POLICY','CONTEXT_ASSEMBLY_POLICY','MEMORY_RETRIEVAL_POLICY','TEMPORAL_CONTEXT_POLICY','AVAILABILITY_POLICY','DELIVERY_LIFECYCLE_POLICY','GENERATION_QUALITY_POLICY','TRAINING_EXAMPLE_ONLY'}
 svc,repo,dev=make();result=svc.execute(uuid4(),operator='operator',**SCOPE);prompt=dev.calls[0]['implementation_task']
 assert result['state']=='EXECUTING' and 'allowedPaths' in prompt and 'behavioralInvariant' in prompt
 assert 'telegram:1:2:3' not in prompt and 'customer_text' not in prompt and 'SELECT ' not in prompt

@pytest.mark.parametrize('auth,error',[(Auths(scope='CONVERSATION_ONLY'),'Non-systemic'),(Auths(category='NO_REPAIR'),'Unsupported'),(Auths(expired=True),'expired')])
def test_oneoff_unsupported_and_expired_authorizations_cannot_execute(auth,error):
 svc,_,_=make(auth)
 with pytest.raises((PermissionError,RuntimeError),match=error):svc.execute(uuid4(),operator='op',**SCOPE)

def test_stale_fingerprint_and_active_claim_safety_fail_closed():
 svc,_,_=make(analyses=Analyses(True))
 with pytest.raises(RuntimeError,match='stale'):svc.execute(uuid4(),operator='op',**SCOPE)
 svc,_,_=make(safety=lambda:{'safe':False,'reason':'Active customer generation/send claims block repair execution.'})
 with pytest.raises(RuntimeError,match='Active customer'):svc.execute(uuid4(),operator='op',**SCOPE)

def test_single_use_and_regression_gate_pass_or_require_rollback():
 svc,repo,dev=make();auth=uuid4();first=svc.execute(auth,operator='op',**SCOPE);second=svc.execute(auth,operator='op',**SCOPE)
 assert first['execution_id']==second['execution_id'] and len(dev.calls)==1
 passed=svc.refresh(first['execution_id'],creator_profile_id=1,fanvue_account_id=2)
 assert passed['state']=='PASSED' and passed['deployment']['state']=='NOT_DEPLOYED'
 failing={'status':'COMPLETED','final_report':{'filesModified':['app/services/unrelated.py'],'tests':'Not reported'}}
 svc,repo,_=make(dev_result=failing);run=svc.execute(uuid4(),operator='op',**SCOPE)
 failed=svc.refresh(run['execution_id'],creator_profile_id=1,fanvue_account_id=2)
 assert failed['state']=='FAILED' and failed['rollback']['required'] is True

def test_execution_migration_has_lifecycle_audit_and_rollback():
 f=open('migrations/forward/20260914_131_conversation_repair_execution.sql').read();r=open('migrations/rollback/20260914_131_conversation_repair_execution.sql').read()
 for state in ('AUTHORIZED','EXECUTING','TESTING','PASSED','FAILED','ROLLED_BACK','DEPLOYED','STALE','EXPIRED'):assert state in f
 assert r.index('conversation_repair_execution_events')<r.index('conversation_repair_executions')

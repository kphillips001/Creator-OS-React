from datetime import datetime,timezone,timedelta
from uuid import uuid4
import pytest
from app.services.conversation_repair_executor_service import ConversationRepairExecutorService,WORKFLOWS

BASE='56ddbff52ba6136673dbeb82ab8c1f322f47b867';SCOPE={'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,'telegram_chat_id':3,'relationship_key':'telegram:1:2:3'}
class Gate:
 def require_enabled(self):pass
class Auths:
 def __init__(self,scope='GLOBAL_SYSTEM',category='QUALITY_GATE_POLICY',expired=False):
  self.auth={'proposal_id':uuid4(),'repair_category':category,'behavioral_invariant':'Grounded only.','regression_requirements':['original','similar','neighbor'],'evidence_fingerprint':'a'*64,'baseline_sha':BASE,'expires_at':datetime.now(timezone.utc)+timedelta(minutes=-1 if expired else 10)}
  self.proposal={'analysis_id':uuid4(),'status':'APPROVED_FOR_EXECUTION','validated_scope':scope,'evidence_fingerprint':'a'*64,'failure_signature':'SIG','preserved_behavior':['neighbor']}
 def authorization(self,*_,**__):return self.auth
 def get(self,*_,**__):return self.proposal
class Analyses:
 def __init__(self,stale=False):self.stale=stale
 def retrieve(self,*_,**__):return {'staleState':'STALE' if self.stale else 'CURRENT'}
class Repo:
 def __init__(self):self.run=None;self.events=[]
 def claim(self,**v):
  if self.run:return self.run,True
  self.run={**v,'execution_id':uuid4(),'state':'AUTHORIZED'};return self.run,False
 def staged(self,eid,stage):self.run.update(state='EXECUTING',baseline_sha=stage['baseRevision'],staging_branch=stage['branch'],staging_worktree_path=stage['worktreePath']);return self.run
 def dispatched(self,eid,**v):self.run.update(v);return self.run
 def get(self,*_,**__):return self.run
 def testing(self,*_):self.run['state']='TESTING'
 def finish(self,eid,**v):self.run.update(v);return self.run
 def fail(self,eid,reason):self.run.update(state='FAILED',failure_reason=reason)
 def event(self,*v):self.events.append(v)
class Stage:
 def __init__(self,result=None):self.result=result or {'state':'READY_FOR_DEPLOYMENT','filesChanged':['app/services/conversation_quality_watch_service.py'],'tests':[{'exitCode':0}],'diffDigest':'d'*64};self.discarded=0
 def prepare(self,eid,expected_base):return {'baseRevision':expected_base,'branch':f'repair-{eid}','worktreePath':f'C:/stages/{eid}'}
 def validate(self,*_,**__):return self.result
 def discard(self,*_):self.discarded+=1
class DevRepo:
 def __init__(self,status='COMPLETED'):self.status=status
 def get_execution(self,*_):return {'status':self.status}
class Dev:
 def __init__(self,status='COMPLETED'):self.calls=[];self.repository=DevRepo(status)
 def create_and_dispatch(self,**v):self.calls.append(v);return {'task':{'task_id':uuid4()},'execution':{'execution_id':uuid4()}}
def make(auth=None,stage=None,dev=None,**kw):
 repo=Repo();stage=stage or Stage();dev=dev or Dev();roots=[]
 def factory(value):roots.append(value);return dev
 svc=ConversationRepairExecutorService(repository=repo,authorization_repository=auth or Auths(),developer_factory=factory,staging=stage,safety=kw.pop('safety',lambda:{'safe':True,'reason':None}),analyses=kw.pop('analyses',Analyses()),execution_gate=Gate(),command_resolver=lambda _:[['git','diff','--check']]);return svc,repo,dev,stage,roots

def test_dispatch_is_rooted_only_in_unique_isolated_stage_and_contract_is_bounded():
 svc,repo,dev,_,roots=make();run=svc.execute(uuid4(),operator='op',**SCOPE);prompt=dev.calls[0]['implementation_task']
 assert run['state']=='EXECUTING' and roots[0]['worktreePath'].startswith('C:/stages/')
 assert 'C:\\Creator-OS-React' not in str(roots) and 'telegram:1:2:3' not in prompt and 'allowedPaths' not in prompt and 'SELECT ' not in prompt

@pytest.mark.parametrize('auth,error',[(Auths(scope='CONVERSATION_ONLY'),'Non-systemic'),(Auths(category='NO_REPAIR'),'Unsupported'),(Auths(expired=True),'expired')])
def test_invalid_authority_fails_closed(auth,error):
 with pytest.raises((PermissionError,RuntimeError),match=error):make(auth)[0].execute(uuid4(),operator='op',**SCOPE)

def test_stale_dirty_and_concurrent_execution_fail_or_single_claim():
 with pytest.raises(RuntimeError,match='stale'):make(analyses=Analyses(True))[0].execute(uuid4(),operator='op',**SCOPE)
 with pytest.raises(RuntimeError,match='claims'):make(safety=lambda:{'safe':False,'reason':'Active claims'})[0].execute(uuid4(),operator='op',**SCOPE)
 svc,repo,dev,_,_=make();key=uuid4();one=svc.execute(key,operator='op',**SCOPE);two=svc.execute(key,operator='op',**SCOPE);assert one['execution_id']==two['execution_id'] and len(dev.calls)==1

def test_independent_validation_ready_and_out_of_scope_failure_never_deploy():
 svc,repo,_,stage,_=make();run=svc.execute(uuid4(),operator='op',**SCOPE);ready=svc.refresh(run['execution_id'],creator_profile_id=1,fanvue_account_id=2)
 assert ready['state']=='READY_FOR_DEPLOYMENT' and ready['ready_at'] is True and stage.discarded==0
 failed_stage=Stage({'state':'FAILED','filesChanged':['outside.py'],'reason':'OUT_OF_SCOPE_EDIT','outsideAllowlist':['outside.py']})
 svc,repo,_,_,_=make(stage=failed_stage);run=svc.execute(uuid4(),operator='op',**SCOPE);failed=svc.refresh(run['execution_id'],creator_profile_id=1,fanvue_account_id=2)
 assert failed['state']=='FAILED' and failed_stage.discarded==1

def test_closed_workflows_and_no_deployed_state():
 assert len(WORKFLOWS)==12
 forward=open('migrations/forward/20260914_132_conversation_repair_isolated_staging.sql').read()
 assert 'READY_FOR_DEPLOYMENT' in forward and "'DEPLOYED'" not in forward

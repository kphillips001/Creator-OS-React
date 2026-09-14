import subprocess
from pathlib import Path
from uuid import uuid4
import pytest
from app.services.conversation_repair_staging_service import ConversationRepairStagingService

def git(path,*args):return subprocess.run(['git',*args],cwd=path,text=True,capture_output=True,check=True).stdout.strip()
@pytest.fixture
def repo(tmp_path):
 live=tmp_path/'live';live.mkdir();git(live,'init');git(live,'config','user.email','fixture@example.invalid');git(live,'config','user.name','Fixture')
 (live/'app/services').mkdir(parents=True);(live/'tests').mkdir();(live/'app/services/policy.py').write_text('VALUE = "bad"\n');(live/'tests/test_policy.py').write_text('def test_policy():\n assert True\n')
 git(live,'add','.');git(live,'commit','-m','base');return live,tmp_path/'stages'

def test_unique_isolated_worktree_and_live_untouched_until_second_gate(repo):
 live,stages=repo;svc=ConversationRepairStagingService(live,stages);base=git(live,'rev-parse','HEAD')
 one=svc.prepare(uuid4(),expected_base=base);two=svc.prepare(uuid4(),expected_base=base)
 assert one['worktreePath']!=two['worktreePath'] and one['branch']!=two['branch']
 Path(one['worktreePath'],'app/services/policy.py').write_text('VALUE = "good"\n')
 assert Path(live,'app/services/policy.py').read_text()=='VALUE = "bad"\n'
 ready=svc.validate(one,allowed_paths=('app/services/policy.py','tests/'),commands=[['git','diff','--check']])
 assert ready['state']=='READY_FOR_DEPLOYMENT' and Path(live,'app/services/policy.py').read_text()=='VALUE = "bad"\n'
 with pytest.raises(PermissionError,match='deployment is not enabled'):svc.deploy(one,ready)
 assert 'bad' in Path(live,'app/services/policy.py').read_text()
 svc.discard(one);svc.discard(two)

def test_dirty_out_of_scope_failure_and_health_rollback(repo):
 live,stages=repo;svc=ConversationRepairStagingService(live,stages);base=git(live,'rev-parse','HEAD')
 Path(live,'dirty.txt').write_text('mine')
 with pytest.raises(RuntimeError,match='Clean committed'):svc.prepare(uuid4(),expected_base=base)
 Path(live,'dirty.txt').unlink();stage=svc.prepare(uuid4(),expected_base=base);Path(stage['worktreePath'],'outside.py').write_text('bad')
 failed=svc.validate(stage,allowed_paths=('app/services/',),commands=[]);assert failed['state']=='FAILED' and not Path(live,'outside.py').exists();svc.discard(stage)
 stage=svc.prepare(uuid4(),expected_base=base);Path(stage['worktreePath'],'app/services/policy.py').write_text('VALUE = "good"\n')
 ready=svc.validate(stage,allowed_paths=('app/services/',),commands=[['git','diff','--check']])
 assert ready['state']=='READY_FOR_DEPLOYMENT' and 'bad' in Path(live,'app/services/policy.py').read_text();svc.discard(stage)

def test_missing_regression_gate_fails_closed(repo):
 live,stages=repo;svc=ConversationRepairStagingService(live,stages);base=git(live,'rev-parse','HEAD');stage=svc.prepare(uuid4(),expected_base=base);Path(stage['worktreePath'],'app/services/policy.py').write_text('VALUE = "good"\n')
 assert svc.validate(stage,allowed_paths=('app/services/',),commands=[])['reason']=='MISSING_REGRESSION_GATE';svc.discard(stage)

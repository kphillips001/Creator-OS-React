"""Git-isolated staging and explicit deployment for governed conversation repairs."""
from __future__ import annotations
import hashlib,subprocess,tempfile
from pathlib import Path

class ConversationRepairStagingService:
 def __init__(self,live_root=Path(r'C:\Creator-OS-React'),staging_root=None,runner=None,health=None,claims=None):
  self.live=Path(live_root).resolve();self.root=Path(staging_root or Path(tempfile.gettempdir())/'creator-os-repair-staging').resolve()
  self.runner=runner or self._run;self.health=health or (lambda:{'healthy':True});self.claims=claims or (lambda:0)
 def prepare(self,execution_id,*,expected_base):
  if self._git(self.live,'status','--porcelain'):raise RuntimeError('Clean committed baseline required before repair staging.')
  head=self._git(self.live,'rev-parse','HEAD')
  if head!=expected_base:raise RuntimeError('Live source diverged from the authorized base revision.')
  path=(self.root/str(execution_id)).resolve()
  if self.root not in path.parents or path.exists():raise RuntimeError('Unique unused staging worktree is required.')
  path.parent.mkdir(parents=True,exist_ok=True);branch=f'creator-os-repair-{execution_id}'
  self._git(self.live,'worktree','add','-b',branch,str(path),head)
  return {'baseRevision':head,'branch':branch,'worktreePath':str(path),'state':'EXECUTING'}
 def validate(self,stage,*,allowed_paths,commands):
  path=Path(stage['worktreePath']).resolve();base=stage['baseRevision']
  tracked=[x for x in self._git(path,'diff','--name-only',base).splitlines() if x]
  untracked=[x for x in self._git(path,'ls-files','--others','--exclude-standard').splitlines() if x]
  files=sorted(set(tracked+untracked))
  outside=[x for x in files if not any(x==p or x.startswith(p.rstrip('/')+'/') for p in allowed_paths)]
  results=[]
  if outside:return {'state':'FAILED','filesChanged':files,'reason':'OUT_OF_SCOPE_EDIT','outsideAllowlist':outside,'liveTouched':False}
  for command in commands:
   result=self.runner(command,path);results.append({'command':command,'exitCode':result.returncode})
   if result.returncode:return {'state':'FAILED','filesChanged':files,'reason':'REGRESSION_OR_BUILD_FAILURE','tests':results,'liveTouched':False}
  self._git(path,'add','--',*files)
  patch=self._git_raw(path,'diff','--cached','--binary',base);digest=hashlib.sha256(patch.encode()).hexdigest()
  self._git(path,'commit','-m',f'Certified conversation repair {stage["branch"]}')
  return {'state':'READY_FOR_DEPLOYMENT','filesChanged':files,'tests':results,'diffDigest':digest,
          'stagedRevision':self._git(path,'rev-parse','HEAD'),'baseRevision':base,'liveTouched':False}
 def deploy(self,stage,result):
  if result['state']!='READY_FOR_DEPLOYMENT':raise RuntimeError('Execution is not ready for deployment.')
  if self.claims():raise RuntimeError('Active customer claims block deployment.')
  if self._git(self.live,'status','--porcelain') or self._git(self.live,'rev-parse','HEAD')!=result['baseRevision']:raise RuntimeError('Live source diverged; restaging is required.')
  path=Path(stage['worktreePath']);patch=self._git_raw(path,'diff','--binary',result['baseRevision'],result['stagedRevision'])
  if hashlib.sha256(patch.encode()).hexdigest()!=result['diffDigest']:raise RuntimeError('Staged repair changed after certification.')
  applied=self.runner(['git','apply','-'],self.live,input_text=patch)
  if applied.returncode:raise RuntimeError(f'Certified staged patch could not be applied cleanly: {(applied.stderr or applied.stdout).strip()}')
  self._git(self.live,'add','--',*result['filesChanged'])
  deployed=self._git(self.live,'write-tree')
  health=self.health()
  if not health.get('healthy'):
   self.runner(['git','apply','-R','-'],self.live,input_text=patch);self._git(self.live,'reset','--mixed',result['baseRevision'])
   return {'state':'ROLLED_BACK','rollbackRevision':result['baseRevision'],'rollbackReason':'POST_DEPLOYMENT_HEALTH_FAILED','health':health}
  return {'state':'DEPLOYED','preDeploymentRevision':result['baseRevision'],'stagedRevision':result['stagedRevision'],'deployedRevision':deployed,'health':health}
 def discard(self,stage):
  path=Path(stage['worktreePath']).resolve();self._git(self.live,'worktree','remove','--force',str(path));self._git(self.live,'branch','-D',stage['branch']);return {'state':'DISCARDED'}
 @staticmethod
 def _run(command,cwd,input_text=None):return subprocess.run(command,cwd=str(cwd),input=input_text,text=True,capture_output=True,check=False,timeout=900)
 def _git(self,cwd,*args):
  result=self.runner(['git',*args],cwd)
  if result.returncode:raise RuntimeError((result.stderr or result.stdout or 'Git staging operation failed.').strip())
  return result.stdout.strip()
 def _git_raw(self,cwd,*args):
  result=self.runner(['git',*args],cwd)
  if result.returncode:raise RuntimeError((result.stderr or result.stdout or 'Git staging operation failed.').strip())
  return result.stdout

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
  if not files:return {'state':'FAILED','filesChanged':[],'reason':'NO_STAGED_CHANGES','liveTouched':False}
  outside=[x for x in files if not any(x==p or x.startswith(p.rstrip('/')+'/') for p in allowed_paths)]
  results=[]
  if outside:return {'state':'FAILED','filesChanged':files,'reason':'OUT_OF_SCOPE_EDIT','outsideAllowlist':outside,'liveTouched':False}
  if not commands:return {'state':'FAILED','filesChanged':files,'reason':'MISSING_REGRESSION_GATE','liveTouched':False}
  for command in commands:
   result=self.runner(command,path);results.append({'command':command,'exitCode':result.returncode})
   if result.returncode:return {'state':'FAILED','filesChanged':files,'reason':'REGRESSION_OR_BUILD_FAILURE','tests':results,'liveTouched':False}
  self._git(path,'add','--',*files)
  patch=self._git_raw(path,'diff','--cached','--binary',base);digest=hashlib.sha256(patch.encode()).hexdigest()
  self._git(path,'commit','-m',f'Certified conversation repair {stage["branch"]}')
  if self._git(self.live,'status','--porcelain') or self._git(self.live,'rev-parse','HEAD')!=base:
   return {'state':'STALE','filesChanged':files,'reason':'LIVE_BASELINE_DIVERGED','tests':results,'liveTouched':True}
  return {'state':'READY_FOR_DEPLOYMENT','filesChanged':files,'tests':results,'diffDigest':digest,
          'stagedRevision':self._git(path,'rev-parse','HEAD'),'baseRevision':base,'liveTouched':False}
 def deploy(self,*_args,**_kwargs):
  raise PermissionError('Conversation repair deployment is not enabled.')
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

"""Fail-closed orchestration for isolated conversation-repair staging."""
from datetime import datetime,timezone
from pathlib import Path
from app.database import get_db_connection
from app.services.conversation_analysis_service import ConversationAnalysisService
from app.services.conversation_repair_execution_gate import ConversationRepairExecutionGate
from app.services.conversation_repair_staging_service import ConversationRepairStagingService
from app.services.developer_agent_execution_service import DeveloperAgentExecutionService

WORKFLOWS={
 'COMMERCIAL_CLASSIFICATION_POLICY':('Commercial classification',('app/services/commercial_receptiveness_service.py','app/services/pre_generation_commercial_decision_service.py','tests/')),
 'COMMERCIAL_PROGRESSION_POLICY':('Commercial progression',('app/services/conversational_sales_progression_service.py','tests/')),
 'SALES_BRAIN_POLICY':('Sales Brain',('app/services/customer_sales_brain_service.py','tests/')),
 'TURN_OBLIGATION_POLICY':('Turn obligations',('app/services/gpt_service.py','app/services/conversation_gateway.py','tests/')),
 'QUALITY_GATE_POLICY':('Quality gate',('app/services/conversation_quality_watch_service.py','app/services/ordinary_chat_reply_service.py','tests/')),
 'CONTEXT_ASSEMBLY_POLICY':('Context assembly',('app/services/conversation_gateway.py','tests/')),
 'MEMORY_RETRIEVAL_POLICY':('Memory retrieval',('app/services/conversational_memory_service.py','tests/')),
 'TEMPORAL_CONTEXT_POLICY':('Temporal context',('app/services/ava_sleep_service.py','app/services/gpt_service.py','tests/')),
 'AVAILABILITY_POLICY':('Availability',('app/services/ava_human_availability_service.py','tests/')),
 'DELIVERY_LIFECYCLE_POLICY':('Delivery lifecycle',('app/services/telegram_delivery_executor.py','app/repositories/ordinary_chat_reply_repository.py','tests/')),
 'GENERATION_QUALITY_POLICY':('Generation quality',('app/services/gpt_service.py','tests/')),
 'TRAINING_EXAMPLE_ONLY':('Training example',('app/services/ai_training_service.py','app/api/ai_training.py','tests/'))}
COMMON_COMMANDS=(('python','-m','compileall','-q','app','tests'),('git','diff','--check'))

class ConversationRepairExecutorService:
 def __init__(self,*,repository=None,authorization_repository=None,developer_factory=None,staging=None,safety=None,analyses=None,execution_gate=None,command_resolver=None):
  from app.repositories.conversation_repair_execution_repository import ConversationRepairExecutionRepository
  from app.repositories.conversation_repair_proposal_repository import ConversationRepairProposalRepository
  self.repository=repository or ConversationRepairExecutionRepository();self.authorizations=authorization_repository or ConversationRepairProposalRepository()
  self.staging=staging or ConversationRepairStagingService();self.developer_factory=developer_factory or self._developer_for_stage
  self.safety=safety or self._safety;self.analyses=analyses or ConversationAnalysisService();self.execution_gate=execution_gate or ConversationRepairExecutionGate();self.command_resolver=command_resolver or self._commands
 def execute(self,authorization_id,*,operator,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,relationship_key):
  self.execution_gate.require_enabled();auth=self.authorizations.authorization(authorization_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if not auth:raise LookupError('Repair execution authorization was not found.')
  proposal=self.authorizations.get(auth['proposal_id'],creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if auth['expires_at']<=datetime.now(timezone.utc):raise RuntimeError('Repair authorization is expired or stale.')
  if proposal['status']!='APPROVED_FOR_EXECUTION':raise RuntimeError('Repair authorization is expired or stale.')
  analysis=self.analyses.retrieve(proposal['analysis_id'],creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id,telegram_chat_id=telegram_chat_id,relationship_key=relationship_key)
  if analysis['staleState']!='CURRENT' or auth['evidence_fingerprint']!=proposal['evidence_fingerprint']:raise RuntimeError('Repair authorization is expired or stale.')
  if proposal['validated_scope'] not in {'MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM'}:raise PermissionError('Non-systemic findings cannot execute.')
  workflow=WORKFLOWS.get(auth['repair_category'])
  if not workflow:raise PermissionError('Unsupported repair category.')
  if not auth.get('regression_requirements'):raise PermissionError('Frozen regression requirements are required.')
  baseline=str(auth.get('baseline_sha') or '')
  if len(baseline)!=40:raise RuntimeError('Frozen baseline revision is required.')
  safe=self.safety()
  if not safe['safe']:raise RuntimeError(safe['reason'])
  run,reused=self.repository.claim(authorization_id=authorization_id,proposal_id=auth['proposal_id'],creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,workflow=auth['repair_category'],executor_identity=operator,rollback_evidence=safe,baseline_sha=baseline)
  if reused:return run
  try:
   stage=self.staging.prepare(run['execution_id'],expected_base=baseline);run=self.repository.staged(run['execution_id'],stage)
   contract={'repairCategory':auth['repair_category'],'canonicalSubsystem':workflow[0],'behavioralInvariant':auth['behavioral_invariant'],'regressionRequirements':auth['regression_requirements'],'evidenceSignature':proposal['failure_signature'],'preservedBehavior':proposal['preserved_behavior']}
   self.execution_gate.require_enabled();developer=self.developer_factory(stage)
   task=developer.create_and_dispatch(issue_identifier=f"conversation-repair:{run['execution_id']}",investigation_package='Frozen server-owned structural signature: '+proposal['failure_signature'],implementation_task=self._task(contract),require_manual_approval=False)
   return self.repository.dispatched(run['execution_id'],developer_task_id=task['task']['task_id'],developer_execution_id=task['execution']['execution_id'])
  except Exception as error:self.repository.fail(run['execution_id'],str(error));raise
 def refresh(self,execution_id,*,creator_profile_id,fanvue_account_id):
  run=self.repository.get(execution_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if not run:raise LookupError('Repair execution was not found.')
  if run['state'] not in {'EXECUTING','TESTING'}:return run
  stage=self._stage(run);developer=self.developer_factory(stage);dev=developer.repository.get_execution(run['developer_execution_id'])
  if not dev or dev['status'] not in {'COMPLETED','FAILED','CANCELLED'}:return run
  if dev['status']!='COMPLETED':
   self.staging.discard(stage);return self.repository.finish(execution_id,state='FAILED',files=[],tests={},diff_digest=None,failure_reason='Developer Agent did not complete.')
  self.repository.testing(execution_id);result=self.staging.validate(stage,allowed_paths=WORKFLOWS[run['workflow']][1],commands=self.command_resolver(run['workflow']))
  state=result['state']
  if state!='READY_FOR_DEPLOYMENT':self.staging.discard(stage);self.repository.event(execution_id,'STAGING_DISCARDED',{'reason':result.get('reason')})
  return self.repository.finish(execution_id,state=state,files=result.get('filesChanged',[]),tests=result.get('tests',{}),diff_digest=result.get('diffDigest'),failure_reason=result.get('reason'),ready_at=state=='READY_FOR_DEPLOYMENT')
 @staticmethod
 def _stage(run):return {'baseRevision':run['baseline_sha'],'branch':run['staging_branch'],'worktreePath':run['staging_worktree_path']}
 @staticmethod
 def _developer_for_stage(stage):return DeveloperAgentExecutionService(repository_path=Path(stage['worktreePath']).resolve(),expected_branch=stage['branch'],isolated_repository=True)
 @staticmethod
 def _commands(_workflow):return (('python','-m','pytest','tests','-q'),*COMMON_COMMANDS)
 @staticmethod
 def _task(c):
  import json
  return 'BOUNDED CREATOR-OS REPAIR CONTRACT. Work only in the supplied isolated repository root. Do not access customer data, send messages, change controls, schema, or configuration.\n'+json.dumps(c,sort_keys=True)
 @staticmethod
 def _safety():
  import subprocess
  status=subprocess.run(['git','status','--short'],capture_output=True,text=True,check=False).stdout.strip()
  with get_db_connection() as c,c.cursor() as q:q.execute("SELECT COUNT(*) value FROM ordinary_chat_reply_operations WHERE state IN('GENERATING','SENDING') AND claim_owner IS NOT NULL AND lease_expires_at>NOW()");claims=int(q.fetchone()['value'])
  return {'safe':not status and claims==0,'reason':('Active customer generation/send claims block repair execution.' if claims else 'Clean committed baseline required before repair staging.' if status else None),'activeClaims':claims,'gitStatus':status,'rollbackMode':'ISOLATED_STAGING_ONLY'}

"""Authorization-only adapter for bounded Developer Agent repair workflows."""
from __future__ import annotations
from uuid import uuid4
from app.database import get_db_connection
from app.services.developer_agent_execution_service import DeveloperAgentExecutionService
from app.services.conversation_analysis_service import ConversationAnalysisService
from app.services.conversation_repair_execution_gate import ConversationRepairExecutionGate

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

class ConversationRepairExecutorService:
 def __init__(self,*,repository=None,authorization_repository=None,developer=None,safety=None,analyses=None,execution_gate=None):
  from app.repositories.conversation_repair_execution_repository import ConversationRepairExecutionRepository
  from app.repositories.conversation_repair_proposal_repository import ConversationRepairProposalRepository
  self.repository=repository or ConversationRepairExecutionRepository();self.authorizations=authorization_repository or ConversationRepairProposalRepository()
  self.developer=developer or DeveloperAgentExecutionService();self.safety=safety or self._safety;self.analyses=analyses or ConversationAnalysisService()
  self.execution_gate=execution_gate or ConversationRepairExecutionGate()
 def execute(self,authorization_id,*,operator,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,relationship_key):
  self.execution_gate.require_enabled()
  auth=self.authorizations.authorization(authorization_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if not auth:raise LookupError('Repair execution authorization was not found.')
  proposal=self.authorizations.get(auth['proposal_id'],creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  from datetime import datetime,timezone
  if auth['expires_at']<=datetime.now(timezone.utc) or proposal['status']!='APPROVED_FOR_EXECUTION':raise RuntimeError('Repair authorization is expired or stale.')
  analysis=self.analyses.retrieve(proposal['analysis_id'],creator_profile_id=creator_profile_id,
   fanvue_account_id=fanvue_account_id,telegram_user_id=telegram_user_id,telegram_chat_id=telegram_chat_id,relationship_key=relationship_key)
  if analysis['staleState']!='CURRENT' or auth['evidence_fingerprint']!=proposal['evidence_fingerprint']:raise RuntimeError('Repair authorization is expired or stale.')
  if proposal['validated_scope'] not in {'MULTIPLE_CUSTOMERS','GLOBAL_SYSTEM'}:raise PermissionError('Non-systemic findings cannot execute.')
  workflow=WORKFLOWS.get(auth['repair_category'])
  if not workflow:raise PermissionError('Unsupported repair category.')
  if not auth.get('regression_requirements'):raise PermissionError('Frozen regression requirements are required.')
  safe=self.safety()
  if not safe['safe']:raise RuntimeError(safe['reason'])
  run,reused=self.repository.claim(authorization_id=authorization_id,proposal_id=auth['proposal_id'],
   creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,workflow=auth['repair_category'],
   executor_identity=operator,rollback_evidence=safe)
  if reused:return run
  contract={'repairCategory':auth['repair_category'],'canonicalSubsystem':workflow[0],
   'allowedPaths':list(workflow[1]),'behavioralInvariant':auth['behavioral_invariant'],
   'regressionRequirements':auth['regression_requirements'],'evidenceSignature':proposal['failure_signature'],
   'preservedBehavior':proposal['preserved_behavior'],'forbidden':['customer rows','Telegram sends','SQL','configuration','unlisted paths']}
  self.execution_gate.require_enabled()
  task=self.developer.create_and_dispatch(issue_identifier=f"conversation-repair:{run['execution_id']}",
   investigation_package='Frozen server-owned structural signature: '+proposal['failure_signature'],
   implementation_task=self._task(contract),require_manual_approval=False)
  return self.repository.dispatched(run['execution_id'],developer_task_id=task['task']['task_id'],
                                    developer_execution_id=task['execution']['execution_id'])
 def refresh(self,execution_id,*,creator_profile_id,fanvue_account_id):
  run=self.repository.get(execution_id,creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id)
  if not run:raise LookupError('Repair execution was not found.')
  if run['state'] not in {'EXECUTING','TESTING'}:return run
  dev=self.developer.repository.get_execution(run['developer_execution_id'])
  if not dev or dev['status'] not in {'COMPLETED','FAILED','CANCELLED'}:return run
  report=dict(dev.get('final_report') or {});files=list(report.get('filesModified') or [])
  tests=report.get('tests');allowed=WORKFLOWS[run['workflow']][1]
  outside=[f for f in files if f and not any(path in str(f) for path in allowed)]
  passed=dev['status']=='COMPLETED' and bool(tests) and tests!='Not reported' and not outside
  rollback={**dict(run.get('rollback_evidence') or {}),'required':not passed,
            'reason':None if passed else 'Regression evidence missing/failed or files escaped the workflow allowlist.'}
  return self.repository.finish(execution_id,state='PASSED' if passed else 'FAILED',files=files,
    tests={'reported':tests,'passed':passed,'outsideAllowlist':outside},rollback=rollback,
    deployment={'state':'NOT_DEPLOYED','automaticDeployment':False})
 @staticmethod
 def _task(c):
  import json
  return ('BOUNDED CREATOR-OS REPAIR CONTRACT. Modify only allowed paths. Do not access customer data, send messages, change controls, schema, or config. Run every frozen regression.\n'+json.dumps(c,sort_keys=True))
 @staticmethod
 def _safety():
  import subprocess
  status=subprocess.run(['git','status','--short'],capture_output=True,text=True,check=False).stdout.strip()
  with get_db_connection() as c,c.cursor() as q:
   q.execute("""SELECT COUNT(*) value FROM ordinary_chat_reply_operations WHERE state IN('GENERATING','SENDING') AND claim_owner IS NOT NULL AND lease_expires_at>NOW()""");claims=int(q.fetchone()['value'])
  return {'safe':not status and claims==0,'reason':('Active customer generation/send claims block repair execution.' if claims else 'Clean rollback boundary required before repair execution.' if status else None),'activeClaims':claims,'gitStatus':status,'rollbackMode':'CLEAN_GIT_HEAD'}

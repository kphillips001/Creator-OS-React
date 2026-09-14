"""Atomic persistence for isolated conversation-repair staging."""
import hashlib,json
from uuid import uuid4
from app.database import get_db_connection

class ConversationRepairExecutionRepository:
 def __init__(self,connection_factory=get_db_connection):self.connection_factory=connection_factory
 def claim(self,**v):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(v['authorization_id']),));q.execute('SELECT * FROM conversation_repair_executions WHERE authorization_id=%s',(v['authorization_id'],));old=q.fetchone()
   if old:return dict(old),True
   q.execute("""INSERT INTO conversation_repair_executions(execution_id,authorization_id,proposal_id,creator_profile_id,fanvue_account_id,state,workflow,executor_identity,rollback_evidence,baseline_sha)
    VALUES(%s,%s,%s,%s,%s,'AUTHORIZED',%s,%s,%s::jsonb,%s) RETURNING *""",(uuid4(),v['authorization_id'],v['proposal_id'],v['creator_profile_id'],v['fanvue_account_id'],v['workflow'],v['executor_identity'],json.dumps(v['rollback_evidence']),v['baseline_sha']))
   row=q.fetchone();self._event(q,row['execution_id'],'EXECUTION_STARTED',{'baselineSha':v['baseline_sha']});return dict(row),False
 def staged(self,eid,stage):
  identity=hashlib.sha256(stage['worktreePath'].encode()).hexdigest()
  row=self._one("""UPDATE conversation_repair_executions SET state='EXECUTING',started_at=NOW(),staging_branch=%s,staging_worktree_identity=%s,staging_worktree_path=%s WHERE execution_id=%s RETURNING *""",(stage['branch'],identity,stage['worktreePath'],eid));self.event(eid,'STAGING_CREATED',{'branch':stage['branch'],'worktreeIdentity':identity});return row
 def dispatched(self,eid,**v):
  row=self._one('UPDATE conversation_repair_executions SET developer_task_id=%s,developer_execution_id=%s WHERE execution_id=%s RETURNING *',(v['developer_task_id'],v['developer_execution_id'],eid));self.event(eid,'AGENT_STARTED',{});return row
 def testing(self,eid):
  row=self._one("UPDATE conversation_repair_executions SET state='TESTING' WHERE execution_id=%s RETURNING *",(eid,));self.event(eid,'AGENT_COMPLETED',{});self.event(eid,'TESTING_STARTED',{});return row
 def get(self,eid,*,creator_profile_id,fanvue_account_id):return self._one('SELECT * FROM conversation_repair_executions WHERE execution_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s',(eid,creator_profile_id,fanvue_account_id))
 def finish(self,eid,*,state,files,tests,diff_digest,failure_reason,ready_at=False):
  row=self._one("""UPDATE conversation_repair_executions SET state=%s,files_changed=%s::jsonb,tests_result=%s::jsonb,staged_diff_digest=%s,failure_reason=%s,ready_for_deployment_at=CASE WHEN %s THEN NOW() ELSE NULL END,completed_at=NOW(),deployment_evidence='{"state":"NOT_DEPLOYED","automaticDeployment":false}'::jsonb WHERE execution_id=%s RETURNING *""",(state,json.dumps(files),json.dumps(tests),diff_digest,failure_reason,ready_at,eid))
  event='READY_FOR_DEPLOYMENT' if state=='READY_FOR_DEPLOYMENT' else 'STALE' if state=='STALE' else 'OUT_OF_SCOPE_EDIT' if failure_reason=='OUT_OF_SCOPE_EDIT' else 'TESTS_FAILED';self.event(eid,'TESTS_PASSED' if ready_at else event,{'state':state});
  if ready_at:self.event(eid,'READY_FOR_DEPLOYMENT',{'diffDigest':diff_digest})
  return row
 def fail(self,eid,reason):
  row=self._one("UPDATE conversation_repair_executions SET state='FAILED',failure_reason=%s,completed_at=NOW() WHERE execution_id=%s RETURNING *",(reason,eid));self.event(eid,'FAILED',{'reason':reason});return row
 def mark_authorization(self,_authorization_id,_state,_reason):return None
 def event(self,eid,event_type,data):
  with self.connection_factory() as c,c.cursor() as q:self._event(q,eid,event_type,data)
 @staticmethod
 def _event(q,eid,event_type,data):q.execute('INSERT INTO conversation_repair_execution_events(execution_id,event_type,event_data) VALUES(%s,%s,%s::jsonb)',(eid,event_type,json.dumps(data)))
 def _one(self,s,p):
  with self.connection_factory() as c,c.cursor() as q:q.execute(s,p);r=q.fetchone()
  return dict(r) if r else None

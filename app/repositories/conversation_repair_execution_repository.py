import json
from uuid import uuid4
from app.database import get_db_connection
class ConversationRepairExecutionRepository:
 def __init__(self,connection_factory=get_db_connection):self.connection_factory=connection_factory
 def claim(self,**v):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(str(v['authorization_id']),))
   q.execute('SELECT * FROM conversation_repair_executions WHERE authorization_id=%s',(v['authorization_id'],));old=q.fetchone()
   if old:return dict(old),True
   q.execute("""INSERT INTO conversation_repair_executions(execution_id,authorization_id,proposal_id,creator_profile_id,fanvue_account_id,state,workflow,executor_identity,rollback_evidence)
    VALUES(%s,%s,%s,%s,%s,'AUTHORIZED',%s,%s,%s::jsonb) RETURNING *""",(uuid4(),v['authorization_id'],v['proposal_id'],v['creator_profile_id'],v['fanvue_account_id'],v['workflow'],v['executor_identity'],json.dumps(v['rollback_evidence'])))
   row=q.fetchone();q.execute("INSERT INTO conversation_repair_execution_events(execution_id,event_type,event_data) VALUES(%s,'EXECUTION_STARTED','{}')",(row['execution_id'],));return dict(row),False
 def dispatched(self,eid,**v):return self._one("""UPDATE conversation_repair_executions SET state='EXECUTING',started_at=NOW(),developer_task_id=%s,developer_execution_id=%s WHERE execution_id=%s RETURNING *""",(v['developer_task_id'],v['developer_execution_id'],eid))
 def get(self,eid,*,creator_profile_id,fanvue_account_id):return self._one('SELECT * FROM conversation_repair_executions WHERE execution_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s',(eid,creator_profile_id,fanvue_account_id))
 def finish(self,eid,*,state,files,tests,rollback,deployment):
  row=self._one("""UPDATE conversation_repair_executions SET state=%s,files_changed=%s::jsonb,tests_result=%s::jsonb,rollback_evidence=%s::jsonb,deployment_evidence=%s::jsonb,completed_at=NOW() WHERE execution_id=%s RETURNING *""",(state,json.dumps(files),json.dumps(tests),json.dumps(rollback),json.dumps(deployment),eid))
  event='TESTS_PASSED' if state=='PASSED' else 'TESTS_FAILED'
  with self.connection_factory() as c,c.cursor() as q:q.execute('INSERT INTO conversation_repair_execution_events(execution_id,event_type,event_data) VALUES(%s,%s,%s::jsonb)',(eid,event,json.dumps({'state':state})))
  return row
 def _one(self,s,p):
  with self.connection_factory() as c,c.cursor() as q:q.execute(s,p);r=q.fetchone()
  return dict(r) if r else None

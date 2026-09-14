"""Persistence authority for verified canonical relationship facts."""
import json
from uuid import UUID,uuid4
from app.database import get_db_connection

class RelationshipFactConflictError(ValueError): pass

class CanonicalRelationshipFactRepository:
 def __init__(self,connection_factory=get_db_connection): self.connection_factory=connection_factory
 def validate_subject(self,*,creator_profile_id,fanvue_account_id,subject_type,subject_id):
  with self.connection_factory() as c,c.cursor() as q:
   if subject_type=='CREATOR': q.execute("SELECT 1 FROM creator_profiles WHERE id=%s AND fanvue_account_id::text=%s::text",(subject_id,fanvue_account_id))
   else: q.execute("SELECT 1 FROM fanvue_users u JOIN creator_profiles cp ON cp.id=%s AND cp.fanvue_account_id::text=u.fanvue_account_id::text WHERE u.id=%s AND u.fanvue_account_id=%s",(creator_profile_id,subject_id,fanvue_account_id))
   return q.fetchone() is not None
 def create(self,**v):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(f"fact:{v['creator_profile_id']}:{v['idempotency_key']}",))
   q.execute("SELECT * FROM canonical_relationship_facts WHERE creator_profile_id=%s AND idempotency_key=%s",(v['creator_profile_id'],v['idempotency_key'])); old=q.fetchone()
   if old:return old,True
   fid=uuid4();q.execute("""INSERT INTO canonical_relationship_facts(fact_id,creator_profile_id,fanvue_account_id,subject_type,subject_id,relation,object_type,object_value,object_data,attributes,category,source_platform,source_type,source_reference,verification_method,confidence,usage_policy,observed_at,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) RETURNING *""",(fid,v['creator_profile_id'],v['fanvue_account_id'],v['subject_type'],v['subject_id'],v['relation'],v['object_type'],v['object_value'],json.dumps(v.get('object_data',{})),json.dumps(v.get('attributes',{})),v['category'],v['source_platform'],v['source_type'],json.dumps(v.get('source_reference',{})),v['verification_method'],v['confidence'],v['usage_policy'],v.get('observed_at'),v['idempotency_key']));row=q.fetchone();self._audit(q,row['fact_id'],'CREATED',v['operator_source'],v.get('source_reference',{}));return row,False
 def list_current(self,*,creator_profile_id,fanvue_account_id,customer_id=None):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("SELECT to_regclass('public.canonical_relationship_facts') table_name")
   if q.fetchone()['table_name'] is None:return []
   q.execute("""SELECT * FROM canonical_relationship_facts WHERE creator_profile_id=%s AND fanvue_account_id=%s AND state='CURRENT' AND ((subject_type='CREATOR' AND subject_id=%s) OR (subject_type='CUSTOMER' AND subject_id=%s)) ORDER BY verified_at DESC""",(creator_profile_id,fanvue_account_id,creator_profile_id,customer_id or -1));return q.fetchall()
 def history(self,*,fact_id,creator_profile_id,fanvue_account_id):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("""SELECT f.*,COALESCE(jsonb_agg(jsonb_build_object('action',a.action,'operatorSource',a.operator_source,'evidence',a.evidence,'occurredAt',a.occurred_at) ORDER BY a.occurred_at) FILTER(WHERE a.audit_id IS NOT NULL),'[]'::jsonb) audit FROM canonical_relationship_facts f LEFT JOIN canonical_relationship_fact_audit a ON a.fact_id=f.fact_id WHERE f.fact_id=%s AND f.creator_profile_id=%s AND f.fanvue_account_id=%s GROUP BY f.fact_id""",(UUID(str(fact_id)),creator_profile_id,fanvue_account_id));return q.fetchone()
 def supersede(self,*,fact_id,replacement,reason,operator_source):
  with self.connection_factory() as c,c.cursor() as q:
   q.execute("SELECT * FROM canonical_relationship_facts WHERE fact_id=%s AND state='CURRENT' FOR UPDATE",(UUID(str(fact_id)),));old=q.fetchone()
   if not old:raise LookupError('Current fact not found')
   q.execute("SELECT * FROM canonical_relationship_facts WHERE creator_profile_id=%s AND idempotency_key=%s",(replacement['creator_profile_id'],replacement['idempotency_key']));row=q.fetchone()
   if row:return row,True
   q.execute("UPDATE canonical_relationship_facts SET state='SUPERSEDED',correction_reason=%s,updated_at=NOW() WHERE fact_id=%s",(reason,old['fact_id']))
   fid=uuid4();q.execute("""INSERT INTO canonical_relationship_facts(fact_id,creator_profile_id,fanvue_account_id,subject_type,subject_id,relation,object_type,object_value,object_data,attributes,category,source_platform,source_type,source_reference,verification_method,confidence,usage_policy,observed_at,idempotency_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s) RETURNING *""",(fid,replacement['creator_profile_id'],replacement['fanvue_account_id'],replacement['subject_type'],replacement['subject_id'],replacement['relation'],replacement['object_type'],replacement['object_value'],json.dumps(replacement.get('object_data',{})),json.dumps(replacement.get('attributes',{})),replacement['category'],replacement['source_platform'],replacement['source_type'],json.dumps(replacement.get('source_reference',{})),replacement['verification_method'],replacement['confidence'],replacement['usage_policy'],replacement.get('observed_at'),replacement['idempotency_key']));row=q.fetchone()
   q.execute("UPDATE canonical_relationship_facts SET superseded_by=%s WHERE fact_id=%s",(row['fact_id'],old['fact_id']));self._audit(q,row['fact_id'],'CREATED',operator_source,replacement.get('source_reference',{}));self._audit(q,old['fact_id'],'SUPERSEDED',operator_source,{'reason':reason,'replacement':str(row['fact_id'])});return row,False
 def deactivate(self,*,fact_id,reason,operator_source):
  with self.connection_factory() as c,c.cursor() as q:q.execute("UPDATE canonical_relationship_facts SET state='INACTIVE',correction_reason=%s,updated_at=NOW() WHERE fact_id=%s AND state='CURRENT' RETURNING *",(reason,UUID(str(fact_id))));row=q.fetchone();
  if not row:raise LookupError('Current fact not found')
  with self.connection_factory() as c,c.cursor() as q:self._audit(q,row['fact_id'],'DEACTIVATED',operator_source,{'reason':reason})
  return row
 @staticmethod
 def _audit(q,fid,action,source,evidence):q.execute("INSERT INTO canonical_relationship_fact_audit(audit_id,fact_id,action,operator_source,evidence) VALUES(%s,%s,%s,%s,%s::jsonb)",(uuid4(),fid,action,source,json.dumps(evidence)))

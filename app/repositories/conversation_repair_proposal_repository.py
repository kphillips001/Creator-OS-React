"""Atomic persistence for frozen repair proposals and authorizations."""
from __future__ import annotations
import json
from uuid import uuid4
from app.database import get_db_connection


class ConversationRepairProposalRepository:
 def __init__(self,connection_factory=get_db_connection):self.connection_factory=connection_factory
 def create(self,**v):
  return self._one("""INSERT INTO conversation_repair_proposals(
   proposal_id,analysis_id,finding_id,creator_profile_id,fanvue_account_id,relationship_key,
   validated_scope,root_cause_category,failure_signature,affected_relationship_count,
   violated_invariant,proposed_invariant,expected_effect,preserved_behavior,known_risks,
   regression_requirements,repair_category,evidence_fingerprint,risk,signature,expires_at)
   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,
          NOW()+INTERVAL '20 minutes') RETURNING *""",(
   v['proposal_id'],v['analysis_id'],v['finding_id'],v['creator_profile_id'],v['fanvue_account_id'],
   v['relationship_key'],v['validated_scope'],v['root_cause_category'],v['failure_signature'],
   v['affected_relationship_count'],v['violated_invariant'],v['proposed_invariant'],v['expected_effect'],
   json.dumps(v['preserved_behavior']),json.dumps(v['known_risks']),json.dumps(v['regression_requirements']),
   v['repair_category'],v['evidence_fingerprint'],v['risk'],v['signature']))
 def get(self,proposal_id,*,creator_profile_id,fanvue_account_id,relationship_key=None,lock=False,cursor=None):
  suffix=(" AND relationship_key=%s" if relationship_key else "")+(" FOR UPDATE" if lock else "")
  params=[proposal_id,creator_profile_id,fanvue_account_id]+([relationship_key] if relationship_key else [])
  query="SELECT * FROM conversation_repair_proposals WHERE proposal_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s"+suffix
  if cursor:
   cursor.execute(query,tuple(params));row=cursor.fetchone();return dict(row) if row else None
  return self._one(query,tuple(params))
 def reject(self,proposal_id,*,creator_profile_id,fanvue_account_id,operator):
  row=self._one("""UPDATE conversation_repair_proposals SET status='REJECTED',rejected_by=%s,
   rejected_at=NOW() WHERE proposal_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
   AND status='PROPOSED' RETURNING *""",(operator,proposal_id,creator_profile_id,fanvue_account_id))
  if row:self.event('REJECTED',proposal_id=proposal_id,data={'operator':operator})
  return row
 def approve(self,proposal_id,*,creator_profile_id,fanvue_account_id,operator,current,baseline_sha):
  """One transaction and uniqueness constraint make duplicate/concurrent approval single-use."""
  with self.connection_factory() as connection,connection.cursor() as cursor:
   cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(str(proposal_id),))
   proposal=self.get(proposal_id,creator_profile_id=creator_profile_id,
                     fanvue_account_id=fanvue_account_id,lock=True,cursor=cursor)
   if not proposal:raise LookupError('Repair proposal was not found.')
   cursor.execute("SELECT NOW() value");now=cursor.fetchone()['value']
   cursor.execute("SELECT * FROM conversation_repair_execution_authorizations WHERE proposal_id=%s",(proposal_id,))
   existing=cursor.fetchone()
   if existing:return dict(existing),True
   reason=None
   if proposal['status']!='PROPOSED':reason='REPAIR PROPOSAL OUT OF DATE'
   elif proposal['expires_at']<=now:reason='REPAIR PROPOSAL OUT OF DATE'
   elif any(proposal[k]!=current[k] for k in ('evidence_fingerprint','failure_signature','validated_scope','signature')):reason='REPAIR PROPOSAL OUT OF DATE'
   elif current['similar_case_count']<proposal['affected_relationship_count']-1:reason='REPAIR PROPOSAL OUT OF DATE'
   if reason:
    status='EXPIRED' if proposal['expires_at']<=now else 'STALE'
    cursor.execute("UPDATE conversation_repair_proposals SET status=%s,stale_reason=%s WHERE proposal_id=%s",
                   (status,reason,proposal_id))
    cursor.execute("INSERT INTO conversation_repair_events(proposal_id,event_type,event_data) VALUES(%s,%s,%s::jsonb)",
                   (proposal_id,status,json.dumps({'reason':reason})))
    connection.commit()
    raise RuntimeError(reason)
   authorization_id=uuid4()
   cursor.execute("""INSERT INTO conversation_repair_execution_authorizations(
    authorization_id,proposal_id,repair_category,validated_scope,behavioral_invariant,
    regression_requirements,risk,evidence_fingerprint,baseline_sha,approved_by,expires_at)
    VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,LEAST(%s,NOW()+INTERVAL '20 minutes')) RETURNING *""",
    (authorization_id,proposal_id,proposal['repair_category'],proposal['validated_scope'],
     proposal['proposed_invariant'],json.dumps(proposal['regression_requirements']),proposal['risk'],
     proposal['evidence_fingerprint'],baseline_sha,operator,proposal['expires_at']))
   authorization=cursor.fetchone()
   cursor.execute("""UPDATE conversation_repair_proposals SET status='APPROVED_FOR_EXECUTION',
    approved_by=%s,approved_at=NOW() WHERE proposal_id=%s""",(operator,proposal_id))
   cursor.execute("""INSERT INTO conversation_repair_events(proposal_id,authorization_id,event_type,event_data)
    VALUES(%s,%s,'APPROVED',%s::jsonb),(%s,%s,'EXECUTION_AUTHORIZED',%s::jsonb)""",
    (proposal_id,authorization_id,json.dumps({'operator':operator}),proposal_id,authorization_id,json.dumps({})))
   return dict(authorization),False
 def authorization(self,authorization_id,*,creator_profile_id,fanvue_account_id):
  return self._one("""SELECT a.* FROM conversation_repair_execution_authorizations a
   JOIN conversation_repair_proposals p USING(proposal_id) WHERE a.authorization_id=%s
   AND p.creator_profile_id=%s AND p.fanvue_account_id=%s""",(authorization_id,creator_profile_id,fanvue_account_id))
 def event(self,event_type,*,proposal_id=None,authorization_id=None,data=None):
  return self._one("""INSERT INTO conversation_repair_events(proposal_id,authorization_id,event_type,event_data)
   VALUES(%s,%s,%s,%s::jsonb) RETURNING *""",(proposal_id,authorization_id,event_type,json.dumps(data or {})))
 def count_all(self):return int(self._one('SELECT COUNT(*) value FROM conversation_repair_proposals',())['value'])
 def _one(self,q,p):
  with self.connection_factory() as c,c.cursor() as x:x.execute(q,p);row=x.fetchone()
  return dict(row) if row else None

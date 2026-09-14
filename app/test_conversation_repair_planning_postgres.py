import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.conversation_analysis_repository import ConversationAnalysisRepository
from app.repositories.conversation_repair_proposal_repository import ConversationRepairProposalRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema

M129='20260914_129_conversation_analysis.sql';NAME='20260914_130_conversation_repair_planning.sql'

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_repair_planning_migration_atomic_approval_stale_expiry_and_isolation():
 url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
 @contextmanager
 def factory():
  with connect(url,row_factory=dict_row) as c:yield c
 with connect(url,autocommit=True) as c:
  c.execute('DROP TABLE IF EXISTS conversation_repair_events,conversation_repair_execution_authorizations,conversation_repair_proposals CASCADE')
  c.execute('DROP TABLE IF EXISTS conversation_analyses CASCADE')
  c.execute('DELETE FROM schema_migrations WHERE migration_name IN (%s,%s)',(M129,NAME))
 try:
  manager=SchemaManagerService(connection_factory=factory);manager.reconcile_one(M129);report=manager.reconcile_one(NAME)
  assert NAME in report.migrations_applied
  with connect(url,row_factory=dict_row) as c:
   creator=c.execute('SELECT id FROM creator_profiles ORDER BY id LIMIT 1').fetchone()['id']
   account=c.execute('SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1').fetchone()['id']
  analyses=ConversationAnalysisRepository(connection_factory=factory);aid=uuid4()
  analyses.create(analysis_id=aid,creator_profile_id=creator,fanvue_account_id=account,
   relationship_key='telegram:test',telegram_user_id=9001,telegram_chat_id=9001,target_type='CONVERSATION',
   target_message_reference=None,evidence_fingerprint='a'*64,evidence_digest='b'*64,
   structured_result={'findings':[]},validated_scope='MULTIPLE_CUSTOMERS',failure_signatures=['SIG'],
   similar_case_summary={'similarCaseCount':1},global_repair_candidate=True,
   provider_metadata={'model':'fixture'},schema_version='V1')
  repo=ConversationRepairProposalRepository(connection_factory=factory)
  def create():
   pid=uuid4();row=repo.create(proposal_id=pid,analysis_id=aid,finding_id=str(pid),creator_profile_id=creator,
    fanvue_account_id=account,relationship_key='telegram:test',validated_scope='MULTIPLE_CUSTOMERS',
    root_cause_category='QUALITY_GATE',failure_signature='SIG',affected_relationship_count=2,
    violated_invariant='bad',proposed_invariant='good',expected_effect='fixed',preserved_behavior=['neighbor'],
    known_risks=['risk'],regression_requirements=['original','similar','neighbor'],repair_category='QUALITY_GATE_POLICY',
    evidence_fingerprint='a'*64,risk='MEDIUM',signature='c'*64)
   return pid,row
  pid,_=create();current={'evidence_fingerprint':'a'*64,'failure_signature':'SIG','validated_scope':'MULTIPLE_CUSTOMERS','similar_case_count':1,'signature':'c'*64}
  def approve():return repo.approve(pid,creator_profile_id=creator,fanvue_account_id=account,operator='operator',current=current)
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:approve(),range(2)))
  assert len({r[0]['authorization_id'] for r in results})==1 and sorted(r[1] for r in results)==[False,True]
  assert repo.get(pid,creator_profile_id=creator,fanvue_account_id=account)['status']=='APPROVED_FOR_EXECUTION'
  assert repo.get(pid,creator_profile_id=creator,fanvue_account_id=account+999) is None
  stale,_=create()
  with pytest.raises(RuntimeError,match='OUT OF DATE'):repo.approve(stale,creator_profile_id=creator,fanvue_account_id=account,operator='operator',current={**current,'failure_signature':'CHANGED'})
  assert repo.get(stale,creator_profile_id=creator,fanvue_account_id=account)['status']=='STALE'
  expired,_=create()
  with connect(url,autocommit=True) as c:c.execute("UPDATE conversation_repair_proposals SET expires_at=NOW()-INTERVAL '1 minute' WHERE proposal_id=%s",(expired,))
  with pytest.raises(RuntimeError,match='OUT OF DATE'):repo.approve(expired,creator_profile_id=creator,fanvue_account_id=account,operator='operator',current=current)
  assert repo.get(expired,creator_profile_id=creator,fanvue_account_id=account)['status']=='EXPIRED'
 finally:
  with connect(url,autocommit=True) as c:
   for name in (NAME,M129):
    path=Path('migrations/rollback')/name
    if (name==NAME and c.execute("SELECT to_regclass('public.conversation_repair_proposals')").fetchone()[0]) or (name==M129 and c.execute("SELECT to_regclass('public.conversation_analyses')").fetchone()[0]):c.execute(path.read_text(encoding='utf-8'))
   c.execute('DELETE FROM schema_migrations WHERE migration_name IN (%s,%s)',(M129,NAME))

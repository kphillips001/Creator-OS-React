import os
from contextlib import contextmanager
from pathlib import Path
import pytest
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from app.repositories.canonical_relationship_fact_repository import CanonicalRelationshipFactRepository
from app.services.canonical_relationship_fact_service import CanonicalRelationshipFactService
URL=os.getenv('TEST_DATABASE_URL');ROOT=Path(__file__).resolve().parents[1]
F=(ROOT/'migrations/forward/20260911_115_canonical_relationship_facts.sql').read_text();R=(ROOT/'migrations/rollback/20260911_115_canonical_relationship_facts.sql').read_text()
@pytest.mark.skipif(not URL,reason='TEST_DATABASE_URL required')
def test_fact_mutation_lineage_and_scope_isolated():
 @contextmanager
 def factory():
  with connect(URL,row_factory=dict_row) as c:yield c
 with connect(URL,autocommit=True,row_factory=dict_row) as c:
  c.execute(F);row=c.execute("select cp.id creator,u.fanvue_account_id account,u.id customer from fanvue_users u join creator_profiles cp on cp.fanvue_account_id::text=u.fanvue_account_id::text order by u.id limit 1").fetchone()
 repo=CanonicalRelationshipFactRepository(factory);service=CanonicalRelationshipFactService(repo)
 base=dict(creator_profile_id=row['creator'],fanvue_account_id=row['account'],subject_type='CUSTOMER',subject_id=row['customer'],relation='owns_pet',object_type='ENTITY',object_value='Bully',object_data={},attributes={'sex':'male'},category='RELATIONSHIP',source_platform='FANVUE',source_type='FANVUE_CONVERSATION',source_reference={'fixture':True},verification_method='OPERATOR_VERIFIED',confidence=1,usage_policy='NORMAL_CONTEXT',observed_at=None,idempotency_key='fixture-bully')
 try:
  fact,replay=service.create_verified(**base);assert not replay
  _,replay=service.create_verified(**base);assert replay
  with pytest.raises(UniqueViolation):service.create_verified(**{**base,'idempotency_key':'semantic-duplicate'})
  corrected,replay=service.correct(fact_id=fact['fact_id'],replacement={**base,'attributes':{'sex':'female'},'idempotency_key':'fixture-bully-correction'},reason='correct sex');assert not replay
  with factory() as c:
   old=c.execute('select state,superseded_by from canonical_relationship_facts where fact_id=%s',(fact['fact_id'],)).fetchone();assert old['state']=='SUPERSEDED' and old['superseded_by']==corrected['fact_id']
  service.deactivate(fact_id=corrected['fact_id'],reason='fixture done')
  with factory() as c:
   actions={r['action']:r['n'] for r in c.execute('select action,count(*) n from canonical_relationship_fact_audit group by action')};assert actions=={'CREATED':2,'SUPERSEDED':1,'DEACTIVATED':1}
  with pytest.raises(ValueError,match='subject'):service.preview_create(**{**base,'fanvue_account_id':999999,'idempotency_key':'wrong'})
 finally:
  with connect(URL,autocommit=True) as c:c.execute(R)

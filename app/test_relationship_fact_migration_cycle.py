import os
from pathlib import Path
import pytest
from psycopg import connect

URL=os.getenv('TEST_DATABASE_URL');ROOT=Path(__file__).resolve().parents[1]
F=(ROOT/'migrations/forward/20260911_115_canonical_relationship_facts.sql').read_text();R=(ROOT/'migrations/rollback/20260911_115_canonical_relationship_facts.sql').read_text()
@pytest.mark.skipif(not URL,reason='TEST_DATABASE_URL required')
def test_relationship_fact_forward_rollback_cycle():
 with connect(URL,autocommit=True) as c:
  assert c.execute("select to_regclass('public.canonical_relationship_facts')").fetchone()[0] is None
  try:
   c.execute(F)
   assert c.execute("select to_regclass('public.canonical_relationship_fact_audit')").fetchone()[0]
   indexes={r[0] for r in c.execute("select indexname from pg_indexes where tablename='canonical_relationship_facts'")}
   assert {'canonical_relationship_fact_current_semantic_idx','canonical_relationship_fact_retrieval_idx'}<=indexes
   c.execute(R)
   assert c.execute("select to_regclass('public.canonical_relationship_facts')").fetchone()[0] is None
  finally:
   if c.execute("select to_regclass('public.canonical_relationship_facts')").fetchone()[0]:c.execute(R)

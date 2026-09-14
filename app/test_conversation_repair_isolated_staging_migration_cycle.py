import os
from contextlib import contextmanager
from pathlib import Path
import pytest
from psycopg import connect
from psycopg.rows import dict_row
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_isolated_test_database_url

NAME='20260914_132_conversation_repair_isolated_staging.sql';ROLLBACK=Path('migrations/rollback')/NAME
@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_isolated_staging_forward_and_rollback_cycle():
 url=require_isolated_test_database_url(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
 @contextmanager
 def factory():
  with connect(url,row_factory=dict_row) as connection:yield connection
 manager=SchemaManagerService(connection_factory=factory)
 for migration in ('20260914_129_conversation_analysis.sql','20260914_130_conversation_repair_planning.sql','20260914_131_conversation_repair_execution.sql',NAME):manager.reconcile_one(migration)
 with connect(url,autocommit=True) as connection:
  columns={row[0] for row in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_name='conversation_repair_executions'")}
  assert {'baseline_sha','staging_branch','staged_diff_digest','ready_for_deployment_at'}<=columns
  connection.execute(ROLLBACK.read_text(encoding='utf-8'));connection.execute('DELETE FROM schema_migrations WHERE migration_name=%s',(NAME,))
 try:
  report=manager.reconcile_one(NAME);assert NAME in report.migrations_applied
 finally:
  manager.reconcile_one(NAME)

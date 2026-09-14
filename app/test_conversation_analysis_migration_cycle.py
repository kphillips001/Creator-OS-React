import os
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.conversation_analysis_repository import ConversationAnalysisRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema

NAME="20260914_129_conversation_analysis.sql"
ROLLBACK=Path("migrations/rollback")/NAME


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="TEST_DATABASE_URL is required")
def test_conversation_analysis_forward_rollback_restart_and_isolation():
    url=require_current_telegram_test_schema(os.getenv("TEST_DATABASE_URL"),os.getenv("DATABASE_URL"))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as connection:yield connection
    with connect(url,autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS conversation_analyses")
        connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))
    try:
        report=SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        assert NAME in report.migrations_applied
        with connect(url,row_factory=dict_row) as connection:
            creator=connection.execute("SELECT id FROM creator_profiles ORDER BY id LIMIT 1").fetchone()
            account=connection.execute("SELECT id FROM fanvue_accounts ORDER BY id LIMIT 1").fetchone()
        repository=ConversationAnalysisRepository(connection_factory=factory);analysis_id=uuid4()
        row=repository.create(analysis_id=analysis_id,creator_profile_id=creator["id"],
          fanvue_account_id=account["id"],relationship_key="telegram:test",telegram_user_id=9001,
          telegram_chat_id=9001,target_type="CONVERSATION",target_message_reference=None,
          evidence_fingerprint="a"*64,evidence_digest="b"*64,
          structured_result={"findings":[]},validated_scope="CONVERSATION_ONLY",
          failure_signatures=["FIXTURE"],similar_case_summary={"similarCaseCount":0},
          global_repair_candidate=False,provider_metadata={"model":"fixture"},schema_version="V1")
        assert row["analysis_id"]==analysis_id
        restarted=ConversationAnalysisRepository(connection_factory=factory)
        assert restarted.get(analysis_id,creator_profile_id=creator["id"],fanvue_account_id=account["id"])
        assert restarted.get(analysis_id,creator_profile_id=creator["id"],fanvue_account_id=account["id"]+999) is None
    finally:
        with connect(url,autocommit=True) as connection:
            if connection.execute("SELECT to_regclass('public.conversation_analyses')").fetchone()[0]:
                connection.execute(ROLLBACK.read_text(encoding="utf-8"))
            connection.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))

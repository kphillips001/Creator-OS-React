from pathlib import Path

from app.services.schema_manager_service import SchemaManagerService


FORWARD = Path("migrations/forward/20260910_112_ai_training_implementation_attempts.sql")
ROLLBACK = Path("migrations/rollback/20260910_112_ai_training_implementation_attempts.sql")


def test_attempt_history_migration_enforces_identity_and_relationships():
    sql = FORWARD.read_text(encoding="utf-8")
    for evidence in (
        "UNIQUE (work_item_id, attempt_number)",
        "UNIQUE (developer_agent_task_id)",
    ):
        assert evidence in sql
    assert "UNIQUE (developer_agent_execution_id)" in sql
    assert "FOREIGN KEY (developer_agent_execution_id, developer_agent_task_id)" in sql
    assert "REFERENCES public.developer_agent_executions(execution_id, task_id)" in sql


def test_attempt_history_migration_is_registered_and_rollback_is_bounded():
    metadata = SchemaManagerService.TABLE_OWNERSHIP["ai_training_implementation_attempts"]
    assert metadata["migration"] == FORWARD.name
    assert FORWARD.name in SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS
    rollback = ROLLBACK.read_text(encoding="utf-8")
    assert "DROP TABLE IF EXISTS public.ai_training_implementation_attempts" in rollback
    assert "DROP TABLE IF EXISTS public.developer_agent" not in rollback


def test_prepare_repository_serializes_on_work_item_before_task_creation():
    source = Path("app/repositories/ai_training_implementation_attempt_repository.py").read_text(encoding="utf-8")
    assert source.index("FOR UPDATE") < source.index("task = task_factory")
    assert "MAX(attempt_number)" in source

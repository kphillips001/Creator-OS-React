from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.schema_manager_service import MigrationFile, SchemaManagerService


M111 = "20260910_111_ai_training_implementation_handoff.sql"


def complete_snapshot():
    requirement = SchemaManagerService.MIGRATION_EFFECT_ATTESTATIONS[M111]
    allowed = requirement["checks"]["ai_training_work_items_status_check"][1]
    return {
        "columns": {},
        "checks": {"ai_training_work_items_status_check":
            "CHECK ((status = ANY (ARRAY[" + ",".join(f"'{value}'::text" for value in allowed) + "])))"},
        "indexes": {},
        "foreign_keys": {"ai_training_work_items_linked_future_task_id_fkey":
            "FOREIGN KEY (linked_future_task_id) REFERENCES developer_agent_tasks(task_id)"},
        "invalid_values": {},
    }


def test_constraint_only_migration_requires_complete_effects_not_existing_columns():
    requirement = SchemaManagerService.MIGRATION_EFFECT_ATTESTATIONS[M111]
    snapshot = complete_snapshot()
    snapshot["foreign_keys"] = {}
    assert not SchemaManagerService._schema_attestation_matches(requirement, snapshot)
    snapshot = complete_snapshot()
    snapshot["checks"]["ai_training_work_items_status_check"] = (
        "CHECK ((status = ANY (ARRAY['TODO'::text])))"
    )
    assert not SchemaManagerService._schema_attestation_matches(requirement, snapshot)
    assert SchemaManagerService._schema_attestation_matches(requirement, complete_snapshot())


class Cursor:
    rowcount = 1
    def __init__(self, statements): self.statements=statements
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def execute(self, sql, params=None): self.statements.append((sql, params))


class Connection:
    def __init__(self): self.statements=[]
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def cursor(self): return Cursor(self.statements)


class RepairManager(SchemaManagerService):
    def __init__(self, *, checksum="expected", effects=False):
        self.connection=Connection();self.checksum=checksum;self.effects=effects;self.recorded=[]
        super().__init__(connection_factory=lambda:self.connection)
    def load_forward_migrations(self):
        return (MigrationFile(M111,Path(M111),"expected","ALTER TABLE bounded"),)
    def ensure_history_table(self, connection): pass
    def applied_migrations(self, connection=None): return {M111:self.checksum}
    def _migration_schema_already_present(self, connection, migration_name): return self.effects
    def _record_migration(self, connection, migration): self.recorded.append(migration.name)
    def certify(self, **values): return SimpleNamespace(**values)


def test_false_history_repair_is_allowlisted_checksum_bound_and_reapplies():
    manager=RepairManager()
    result=manager.repair_false_history_and_reconcile_one(M111)
    assert manager.recorded == [M111]
    assert result.migrations_applied == (M111,)
    assert any("DELETE FROM public.schema_migrations" in sql for sql,_ in manager.connection.statements)
    assert any("ALTER TABLE bounded" in sql for sql,_ in manager.connection.statements)


def test_false_history_repair_fails_closed_for_checksum_or_present_effects():
    with pytest.raises(ValueError,match="exact recorded checksum"):
        RepairManager(checksum="wrong").repair_false_history_and_reconcile_one(M111)
    with pytest.raises(RuntimeError,match="already present"):
        RepairManager(effects=True).repair_false_history_and_reconcile_one(M111)

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.schema_manager_service import (
    MigrationFile,
    SchemaManagerService,
)


M102 = "20260901_102_unified_operator_notifications.sql"
M103 = "20260901_103_x_competitor_creator_platform.sql"


def exact_snapshot(migration_name):
    requirement = SchemaManagerService.HISTORY_ONLY_SCHEMA_ATTESTATIONS[
        migration_name
    ]
    checks = {
        name: (
            "CHECK (("
            + column
            + " = ANY (ARRAY["
            + ",".join(f"'{value}'::text" for value in allowed)
            + "])))"
        )
        for name, (column, allowed) in requirement.get("checks", {}).items()
    }
    indexes = {
        name: "CREATE INDEX " + name + " ON relation USING btree ("
        + ", ".join(columns) + ")"
        for name, columns in requirement.get("indexes", {}).items()
    }
    return {
        "columns": dict(requirement.get("columns", {})),
        "checks": checks,
        "indexes": indexes,
        "invalid_values": {
            column: 0 for column in requirement.get("allowed_values", {})
        },
    }


class Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class HistoryOnlyManager(SchemaManagerService):
    def __init__(self, migration_name, *, applied=None, attested=True):
        self.migration = MigrationFile(
            migration_name, Path(migration_name), "expected-checksum",
            "DDL MUST NOT EXECUTE",
        )
        self._applied = dict(applied or {})
        self.attested = attested
        self.recorded = []
        super().__init__(connection_factory=Connection)

    def load_forward_migrations(self):
        return (self.migration,)

    def ensure_history_table(self, connection):
        del connection

    def applied_migrations(self, connection=None):
        del connection
        return self._applied

    def _migration_schema_already_present(self, connection, migration_name):
        del connection, migration_name
        return self.attested

    def _record_migration(self, connection, migration):
        del connection
        self.recorded.append(migration.name)
        self._applied[migration.name] = migration.checksum

    def certify(self, **values):
        return SimpleNamespace(
            migrations_applied=values.get("migrations_applied", ()),
            migrations_recorded=values.get("migrations_recorded", ()),
        )


@pytest.mark.parametrize("migration_name", (M102, M103))
def test_exact_schema_records_history_without_executing_sql(migration_name):
    manager = HistoryOnlyManager(migration_name)

    result = manager.reconcile_one(migration_name)

    assert manager.recorded == [migration_name]
    assert result.migrations_recorded == (migration_name,)
    assert result.migrations_applied == ()


def test_incomplete_102_schema_fails_closed_without_sql_execution():
    requirement = SchemaManagerService.HISTORY_ONLY_SCHEMA_ATTESTATIONS[M102]
    snapshot = exact_snapshot(M102)
    snapshot["columns"].pop("reviewed_at")

    assert not SchemaManagerService._schema_attestation_matches(
        requirement, snapshot
    )
    manager = HistoryOnlyManager(M102, attested=False)
    with pytest.raises(RuntimeError, match="History-only schema attestation"):
        manager.reconcile_one(M102)
    assert manager.recorded == []


def test_exact_schema_qualified_103_attestation_matches():
    requirement = SchemaManagerService.HISTORY_ONLY_SCHEMA_ATTESTATIONS[M103]
    assert requirement["schema"] == "x_intelligence"
    assert SchemaManagerService._relation_parts(
        "x_intelligence.competitors"
    ) == ("x_intelligence", "competitors")
    assert SchemaManagerService._schema_attestation_matches(
        requirement, exact_snapshot(M103)
    )


@pytest.mark.parametrize("mutation", (
    "missing_column", "wrong_default", "nullable", "wrong_constraint",
    "invalid_value",
))
def test_inexact_103_schema_fails_closed(mutation):
    requirement = SchemaManagerService.HISTORY_ONLY_SCHEMA_ATTESTATIONS[M103]
    snapshot = exact_snapshot(M103)
    if mutation == "missing_column":
        snapshot["columns"].pop("platform")
    elif mutation == "wrong_default":
        snapshot["columns"]["platform"] = ("text", "NO", None)
    elif mutation == "nullable":
        snapshot["columns"]["platform"] = (
            "text", "YES", "'FANVUE'::text",
        )
    elif mutation == "wrong_constraint":
        snapshot["checks"]["ck_x_intelligence_competitors_platform"] = (
            "CHECK ((platform = ANY (ARRAY['FANVUE'::text])))"
        )
    else:
        snapshot["invalid_values"]["platform"] = 1

    assert not SchemaManagerService._schema_attestation_matches(
        requirement, snapshot
    )


def test_other_platform_is_valid_and_survives_history_only_reconciliation():
    requirement = SchemaManagerService.HISTORY_ONLY_SCHEMA_ATTESTATIONS[M103]
    assert "OTHER" in requirement["allowed_values"]["platform"]
    distribution = {"FANVUE": 132, "OTHER": 1}
    manager = HistoryOnlyManager(M103)

    manager.reconcile_one(M103)

    assert distribution == {"FANVUE": 132, "OTHER": 1}


def test_already_recorded_history_is_idempotent():
    manager = HistoryOnlyManager(M103, applied={M103: "expected-checksum"})

    result = manager.reconcile_one(M103)

    assert manager.recorded == []
    assert result.migrations_recorded == ()


def test_checksum_mismatch_fails_closed():
    manager = HistoryOnlyManager(M103, applied={M103: "wrong-checksum"})

    with pytest.raises(ValueError, match="checksum differs"):
        manager.reconcile_one(M103)
    assert manager.recorded == []

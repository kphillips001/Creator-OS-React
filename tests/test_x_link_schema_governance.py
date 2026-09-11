from pathlib import Path
from unittest.mock import patch

from app.services.schema_manager_service import SchemaManagerService


MIGRATION = "20260908_104_x_link_performance.sql"
ATTRIBUTIONS = "x_link_attributions"
EVENTS = "x_link_click_events"


def governed_schema():
    return {
        table: set(metadata["columns"])
        for table, metadata in SchemaManagerService.REQUIRED_TABLES.items()
    }


def test_x_link_tables_and_migration_are_canonically_governed():
    for table in (ATTRIBUTIONS, EVENTS):
        metadata = SchemaManagerService.REQUIRED_TABLES[table]
        assert metadata["migration"] == MIGRATION
        assert metadata["repository"] == "XLinkPerformanceRepository"
        assert metadata["service"] == "XLinkPerformanceService"
        assert table in SchemaManagerService.TABLE_OWNERSHIP
    assert set(SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS[MIGRATION]) == {
        ATTRIBUTIONS, EVENTS,
    }


def test_governed_columns_match_forward_migration_and_rollback_order():
    forward = Path("migrations/forward") / MIGRATION
    rollback = Path("migrations/rollback") / MIGRATION
    sql = forward.read_text(encoding="utf-8")
    rollback_sql = rollback.read_text(encoding="utf-8")
    for table in (ATTRIBUTIONS, EVENTS):
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in sql
        for column in SchemaManagerService.REQUIRED_TABLES[table]["columns"]:
            assert column in sql
    assert "x_link_attribution_id UUID PRIMARY KEY" in sql
    assert "event_id UUID PRIMARY KEY" in sql
    assert "attribution_token TEXT NOT NULL UNIQUE" in sql
    assert "cta_x_post_id TEXT NULL UNIQUE" in sql
    assert "uq_x_link_attribution_publish_operation" in sql
    assert "REFERENCES public.x_link_attributions(x_link_attribution_id) ON DELETE RESTRICT" in sql
    assert rollback_sql.index(EVENTS) < rollback_sql.index(ATTRIBUTIONS)


def test_required_reporting_indexes_and_foreign_key_match_migration():
    sql = (Path("migrations/forward") / MIGRATION).read_text(encoding="utf-8")
    for names in (
        SchemaManagerService.REQUIRED_INDEXES[ATTRIBUTIONS],
        SchemaManagerService.REQUIRED_INDEXES[EVENTS],
    ):
        for name in names:
            assert name in sql
    assert SchemaManagerService.CRITICAL_FOREIGN_KEYS[EVENTS] == (
        "x_link_click_events_x_link_attribution_id_fkey",
    )


@patch.object(SchemaManagerService, "detect_repository_schema_creation", return_value=())
@patch.object(SchemaManagerService, "detect_missing_foreign_keys", return_value=())
@patch.object(SchemaManagerService, "detect_missing_indexes", return_value=())
def test_complete_x_link_schema_has_no_unmanaged_drift(_indexes, _foreign_keys, _ddl):
    assert SchemaManagerService().detect_schema_drift(governed_schema()) == ()


@patch.object(SchemaManagerService, "detect_repository_schema_creation", return_value=())
@patch.object(SchemaManagerService, "detect_missing_foreign_keys", return_value=())
@patch.object(SchemaManagerService, "detect_missing_indexes", return_value=())
def test_missing_x_link_table_and_column_are_detected(_indexes, _foreign_keys, _ddl):
    schema = governed_schema()
    del schema[EVENTS]
    schema[ATTRIBUTIONS].remove("attribution_token")
    drift = SchemaManagerService().detect_schema_drift(schema)
    assert "Missing table: x_link_click_events" in drift
    assert "Missing columns on x_link_attributions: attribution_token" in drift

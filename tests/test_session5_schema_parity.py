from pathlib import Path

from app.services.schema_manager_service import SchemaManagerService
from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    SCENARIO_LAB_RUNTIME_MIGRATIONS,
)


def test_scenario_lab_initialization_reconciles_canonical_runtime_migrations():
    calls = []

    class RecordingManager:
        def __init__(self, *, connection_factory):
            assert callable(connection_factory)

        def reconcile_one(self, migration_name):
            calls.append(migration_name)

    harness = CustomerScenarioHarness.__new__(CustomerScenarioHarness)
    harness.connection = lambda: None
    harness._ensure_runtime_schema_parity(RecordingManager)

    assert tuple(calls) == SCENARIO_LAB_RUNTIME_MIGRATIONS


def test_schema_parity_uses_canonical_abuse_review_migrations():
    first, second = SCENARIO_LAB_RUNTIME_MIGRATIONS
    first_sql = Path("migrations/forward", first).read_text(encoding="utf-8")
    second_sql = Path("migrations/forward", second).read_text(encoding="utf-8")

    assert "CREATE TABLE public.customer_abuse_review_incidents" in first_sql
    assert "CREATE TABLE public.operator_notification_operations" in first_sql
    assert "ALTER TABLE public.operator_notification_operations" in second_sql
    assert second in SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS


def test_unified_notification_migration_requirement_covers_companion_columns():
    requirements = SchemaManagerService.MIGRATION_SCHEMA_REQUIREMENTS[
        "20260901_102_unified_operator_notifications.sql"
    ]["operator_notification_operations"]

    assert {
        "creator_profile_id", "fanvue_account_id", "telegram_user_id",
        "telegram_chat_id", "source_correlation_id", "quality_reason",
        "severity", "incident_window_started_at", "reviewed_at",
    }.issubset(requirements)

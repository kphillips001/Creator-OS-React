from pathlib import Path


def test_customer_control_migration_is_fail_closed_and_reversible():
    forward = Path("migrations/forward/20260911_113_customer_automation_selling_controls.sql").read_text()
    rollback = Path("migrations/rollback/20260911_113_customer_automation_selling_controls.sql").read_text()
    assert "content_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "session_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "DROP COLUMN IF EXISTS session_selling_enabled" in rollback
    assert "DROP COLUMN IF EXISTS content_selling_enabled" in rollback


def test_default_on_migration_changes_only_future_row_defaults():
    forward = Path("migrations/forward/20260913_120_customer_selling_permissions_default_on.sql").read_text()
    rollback = Path("migrations/rollback/20260913_120_customer_selling_permissions_default_on.sql").read_text()
    assert "ALTER COLUMN content_selling_enabled SET DEFAULT TRUE" in forward
    assert "ALTER COLUMN session_selling_enabled SET DEFAULT TRUE" in forward
    assert "UPDATE public.telegram_relationship_controls" not in forward
    assert "ALTER COLUMN content_selling_enabled SET DEFAULT FALSE" in rollback
    assert "ALTER COLUMN session_selling_enabled SET DEFAULT FALSE" in rollback

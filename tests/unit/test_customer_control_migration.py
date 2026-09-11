from pathlib import Path


def test_customer_control_migration_is_fail_closed_and_reversible():
    forward = Path("migrations/forward/20260911_113_customer_automation_selling_controls.sql").read_text()
    rollback = Path("migrations/rollback/20260911_113_customer_automation_selling_controls.sql").read_text()
    assert "content_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "session_selling_enabled BOOLEAN NOT NULL DEFAULT FALSE" in forward
    assert "DROP COLUMN IF EXISTS session_selling_enabled" in rollback
    assert "DROP COLUMN IF EXISTS content_selling_enabled" in rollback

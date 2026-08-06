from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sales_opportunity_migration_has_forward_and_rollback():
    forward = ROOT / "migrations/forward/20260804_033_photoshoot_sales_opportunities.sql"
    rollback = ROOT / "migrations/rollback/20260804_033_photoshoot_sales_opportunities.sql"
    assert forward.exists() and rollback.exists()
    sql = forward.read_text(encoding="utf-8")
    for required in ("'ACTIVE','OBJECTION','COMPLETED','CLOSED','DECLINED'", "expires_at", "finale_decision", "objection_attempts", "uq_customer_active_photoshoot_opportunity"):
        assert required in sql

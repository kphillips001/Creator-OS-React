from pathlib import Path


def test_migration_preserves_history_and_marks_legacy_copy_for_regeneration():
    sql = Path("migrations/forward/20260804_034_photoshoot_commercial_intelligence.sql").read_text()
    assert "DROP COLUMN" not in sql.upper()
    assert "deliverable.ai_title" in sql
    assert "deliverable.ai_description" in sql
    assert "generation_status" in sql
    assert "'PENDING'" in sql
    assert "uq_photoshoot_commercial_intelligence" in sql

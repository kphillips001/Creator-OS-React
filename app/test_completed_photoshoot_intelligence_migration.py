from pathlib import Path


def test_canonical_pipeline_migration_has_versioned_unique_shot_identity():
    sql = Path("migrations/forward/20260804_035_canonical_completed_photoshoot_intelligence.sql").read_text()
    assert "photoshoot_shot_intelligence_profiles" in sql
    assert "PRIMARY KEY (photoshoot_session_id, asset_id, intelligence_version)" in sql
    assert "UNIQUE (photoshoot_session_id, intelligence_version, shot_order)" in sql
    assert "pipeline_stage" in sql and "stage_status" in sql

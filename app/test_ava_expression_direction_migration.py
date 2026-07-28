from pathlib import Path


def test_expression_refinement_is_scoped_to_ava_social_creative_direction():
    migration = Path(
        "migrations/forward/20260727_021_ava_expression_direction.sql"
    ).read_text(encoding="utf-8")

    assert "social_creative_directions" in migration
    assert "profile.persona_name = 'Ava Blackthorne'" in migration
    assert "soft smile" in migration
    assert "quiet confidence" in migration
    assert "playful smirk" in migration
    assert "confident eye contact" in migration
    assert "preference, not a neutral-expression rule" in migration
    assert "prompt" not in migration.lower()

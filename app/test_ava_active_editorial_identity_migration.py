from pathlib import Path


def test_active_editorial_identity_is_ava_scoped_and_non_deterministic():
    migration = Path(
        "migrations/forward/20260727_024_ava_active_editorial_identity.sql"
    ).read_text(encoding="utf-8")
    lowered = migration.lower()

    assert migration.count("profile.persona_name = 'Ava Blackthorne'") == 2
    assert "fitness is a natural, recurring part" in lowered
    assert "works out consistently" in lowered
    assert "post-workout coffee" in lowered
    assert "effortless public confidence" in lowered
    assert "never feels arrogant, theatrical, attention-seeking" in lowered
    assert "confident, feminine, flirtatious, playful, approachable" in lowered
    assert "active wardrobe identity" in lowered
    assert "not wardrobe rules or a mechanical rotation" in lowered

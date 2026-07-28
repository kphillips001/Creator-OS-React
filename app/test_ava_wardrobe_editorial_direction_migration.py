from pathlib import Path


def test_wardrobe_refinement_is_editorial_and_scoped_to_ava():
    migration = Path(
        "migrations/forward/20260727_022_ava_wardrobe_editorial_direction.sql"
    ).read_text(encoding="utf-8")
    lowered = migration.lower()

    assert "profile.persona_name = 'Ava Blackthorne'" in migration
    assert "confident, feminine, stylish, figure-flattering" in migration
    assert "silhouette, neckline, garment structure, layering, and coverage" in migration
    assert "do not force exposure" in lowered
    assert "coverage targets" in lowered
    assert "fixed wardrobe formula" in lowered
    assert "%" not in migration.replace("%Brand Styling and Silhouette Direction%", "")

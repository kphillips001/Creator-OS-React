from pathlib import Path


def test_public_wardrobe_brand_is_ava_scoped_and_preserves_manual_intent():
    migration = Path(
        "migrations/forward/20260727_023_ava_public_wardrobe_brand.sql"
    ).read_text(encoding="utf-8")
    lowered = migration.lower()

    assert "profile.persona_name = 'Ava Blackthorne'" in migration
    assert "midriff-visible styling is a normal, recurring part" in lowered
    assert "not a required rotation or wardrobe template" in lowered
    assert "when an autonomously selected scene naturally calls for swimwear" in lowered
    assert "choose a bikini" in lowered
    assert "only when the operator explicitly requests them" in lowered
    assert "never override explicit manual wardrobe intent" in lowered

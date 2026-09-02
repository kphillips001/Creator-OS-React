from app.services.photoshoot_expression_guidance import (
    is_weak_photoshoot_emotion,
    normalize_photoshoot_emotion,
    photoshoot_default_emotion,
)


def test_photoshoot_defaults_are_alluring_for_premium_and_explicit():
    premium = photoshoot_default_emotion("premium")
    explicit = photoshoot_default_emotion("explicit")
    safe = photoshoot_default_emotion("safe")

    assert "teasing" in premium.lower()
    assert "seductive" in premium.lower() or "alluring" in premium.lower()
    assert "parted lips" in explicit.lower() or "seductive" in explicit.lower()
    assert "salacious" in explicit.lower() or "naughty" in explicit.lower()
    assert "vacant" not in premium.lower()
    assert "confident" in safe.lower() or "warm" in safe.lower()


def test_weak_continuity_emotions_are_replaced():
    assert is_weak_photoshoot_emotion("")
    assert is_weak_photoshoot_emotion("natural and connected")
    assert is_weak_photoshoot_emotion(
        "Preserve the latest approved expression with only a subtle evolution."
    )
    assert is_weak_photoshoot_emotion("Confident")
    assert not is_weak_photoshoot_emotion(
        "teasing coy smirk, fully open seductive eyes, soft bitten lip"
    )

    normalized = normalize_photoshoot_emotion(
        "Preserve the latest approved expression with only a subtle evolution.",
        creative_mode="premium",
    )
    assert "teasing" in normalized.lower()
    assert "preserve the latest approved expression" not in normalized.lower()


def test_concrete_operator_emotion_is_preserved():
    text = "locked seductive stare, bitten lip, fully open naughty eyes"
    assert normalize_photoshoot_emotion(text, creative_mode="explicit") == text

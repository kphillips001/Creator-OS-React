"""Photoshoot facial-performance defaults for alluring, sellable creator faces."""

from __future__ import annotations

_WEAK_EMOTION_MARKERS = (
    "preserve the latest approved expression",
    "subtle evolution",
    "natural and connected",
    "keep the expression natural",
    "natural connected",
    "soft smile",
    "neutral",
    "calm expression",
    "blank",
    "vacant",
    "deadpan",
    "same expression",
    "identical expression",
)

_SAFE_DEFAULT = (
    "warm confident eye contact with a soft natural smile, alert fully open eyes, "
    "relaxed cheeks, candid creator-camera energy"
)

_PREMIUM_DEFAULT = (
    "teasing coy smirk, fully open seductive eyes, soft bitten lip or parted lips, "
    "alluring intimate appeal, naughty private PPV energy"
)

_EXPLICIT_DEFAULT = (
    "teasing seductive parted lips, fully open alert eyes, locked naughty intimate "
    "eye contact, salacious wanting, sexually enticing private PPV face"
)


def photoshoot_default_emotion(creative_mode: str | None) -> str:
    mode = str(creative_mode or "").strip().lower()
    if mode in {"explicit"}:
        return _EXPLICIT_DEFAULT
    if mode in {"safe", "standard", "social_safe"}:
        return _SAFE_DEFAULT
    return _PREMIUM_DEFAULT


def is_weak_photoshoot_emotion(emotion: str | None) -> bool:
    text = " ".join(str(emotion or "").split()).strip().lower()
    if not text:
        return True
    if len(text) < 12 and text in {"confident", "natural", "soft", "calm", "happy", "smile"}:
        return True
    return any(marker in text for marker in _WEAK_EMOTION_MARKERS)


def normalize_photoshoot_emotion(
    emotion: str | None,
    *,
    creative_mode: str | None,
) -> str:
    """Return a concrete face performance; never inherit bland continuity defaults."""
    text = " ".join(str(emotion or "").split()).strip()
    if is_weak_photoshoot_emotion(text):
        return photoshoot_default_emotion(creative_mode)
    return text

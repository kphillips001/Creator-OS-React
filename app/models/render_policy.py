"""Explicit render policies shared by generation workflows and providers."""

from enum import Enum


class RenderPolicy(str, Enum):
    CONTENT_STANDARD = "CONTENT_STANDARD"
    CONTENT_SPICY = "CONTENT_SPICY"
    CONTENT_EXPLICIT = "CONTENT_EXPLICIT"
    PHOTOSHOOT_SAFE = "PHOTOSHOOT_SAFE"
    PHOTOSHOOT_PREMIUM = "PHOTOSHOOT_PREMIUM"
    PHOTOSHOOT_EXPLICIT = "PHOTOSHOOT_EXPLICIT"
    EDIT = "EDIT"


def content_render_policy(creative_mode: str) -> RenderPolicy:
    mappings = {
        "standard": RenderPolicy.CONTENT_STANDARD,
        "social_safe": RenderPolicy.CONTENT_STANDARD,
        "spicy": RenderPolicy.CONTENT_SPICY,
        "premium_teaser": RenderPolicy.CONTENT_SPICY,
        "story_sequence": RenderPolicy.CONTENT_SPICY,
        "explicit": RenderPolicy.CONTENT_EXPLICIT,
    }
    try:
        return mappings[str(creative_mode or "").strip().lower()]
    except KeyError as error:
        raise ValueError(f"Unsupported Content Studio creative mode: {creative_mode!r}") from error


def photoshoot_render_policy(creative_mode: str) -> RenderPolicy:
    mappings = {
        "safe": RenderPolicy.PHOTOSHOOT_SAFE,
        "standard": RenderPolicy.PHOTOSHOOT_SAFE,
        "social_safe": RenderPolicy.PHOTOSHOOT_SAFE,
        "premium": RenderPolicy.PHOTOSHOOT_PREMIUM,
        "premium_teaser": RenderPolicy.PHOTOSHOOT_PREMIUM,
        "spicy": RenderPolicy.PHOTOSHOOT_PREMIUM,
        "story_sequence": RenderPolicy.PHOTOSHOOT_PREMIUM,
        "explicit": RenderPolicy.PHOTOSHOOT_EXPLICIT,
    }
    try:
        return mappings[str(creative_mode or "").strip().lower()]
    except KeyError as error:
        raise ValueError(f"Unsupported Photoshoot creative mode: {creative_mode!r}") from error


def photoshoot_planning_mode(creative_mode: str) -> str:
    return {
        RenderPolicy.PHOTOSHOOT_SAFE: "photoshoot_safe",
        RenderPolicy.PHOTOSHOOT_PREMIUM: "photoshoot_premium",
        RenderPolicy.PHOTOSHOOT_EXPLICIT: "photoshoot_explicit",
    }[photoshoot_render_policy(creative_mode)]

"""Dedicated Safe Photoshoot planning adapter."""

from app.services.premium_director_service import generate_premium_prompts


SAFE_PHOTOSHOOT_PLANNING_POLICY = """
SAFE PHOTOSHOOT PLANNING POLICY:
Preserve creator identity, wardrobe, location, lighting, camera continuity, and realism.
Keep styling, posing, mood, and expression natural and non-sensual.
Do not add teasing, erotic, nude, or explicit escalation.
""".strip()


def generate_safe_photoshoot_prompts(
    creative_tags: str,
    prompt_count: int,
    optional_direction: str | None = None,
) -> list[str]:
    return generate_premium_prompts(
        creative_tags=f"{creative_tags}\n\n{SAFE_PHOTOSHOOT_PLANNING_POLICY}",
        prompt_count=prompt_count,
        optional_direction=optional_direction,
    )

"""Shared editorial-quality guidance for distinct Content Studio workflows."""

from __future__ import annotations


def editorial_quality_guidance(*, workflow: str) -> str:
    """Return common quality standards without collapsing workflow policies."""
    scope = str(workflow or "").strip().lower()
    authority = {
        "autonomous": (
            "Originate the scene freely, then review the complete collection "
            "for editorial range and repetition."
        ),
        "canonical_planner": (
            "The selected planner item is authoritative. Refine it without "
            "replacing its wardrobe, activity, setting, mood, narrative, or constraints."
        ),
        "manual_creative_concept": (
            "The operator's Creative Concept is authoritative. Preserve its "
            "wording, wardrobe, activity, requested setting, mood, and explicit constraints."
        ),
    }.get(scope, "Preserve the supplied creative intent as authoritative.")
    return f"""Apply Editorial Cinematography using these shared quality standards.

EDITORIAL CINEMATOGRAPHY — OBSERVED MOMENTS:
- Reason like an editorial photographer following Ava through her day. Internally ask: "What authentic moment would naturally be photographed?" and "What would an editorial photographer naturally capture here?" Do not begin by inventing a pose.
- Prefer observed moments over static portraits. Let Ava move through, react to, or comfortably inhabit the environment so the image feels discovered rather than staged.
- Favor an authentic observed moment with natural movement or environmental interaction.
- Infer natural behavior from the scene: walking, turning, glancing back, stepping into a place, leaning or sitting comfortably, adjusting something she is wearing, carrying something relevant, reacting softly to something nearby, looking toward scenery, stretching after activity, or otherwise interacting with the environment. These are examples, never a pose library or rotation.
- Favor candid energy, authentic body language, natural movement, strong environmental interaction, and asymmetrical compositions when they strengthen the scene.
- Vary the relationship with the viewer. Direct eye contact remains available, but off-camera glances, over-the-shoulder moments, and naturally shifting eye contact should also emerge when authentic.
- Expand the scene intelligently with specific, believable environmental detail, editorial storytelling, and a clear visual reason for the image to exist.
- Choose camera distance, crop, perspective, composition, and lighting as one coherent editorial decision that supports the activity and environment.
- Refine wardrobe through scene-aware creative-director judgment. Keep explicit wardrobe authoritative; infer only unspecified styling details from creator context, season, setting, lighting, mood, and editorial quality.
- Maintain confident premium fashion styling, consistent creator identity, realistic skin, hair and fabric texture, natural shadows, and rich photographic detail.
- Do not collapse the concept into a static centered portrait or generic apartment scene unless the authoritative concept explicitly requires one.
- Avoid stiff catalog posing, theatrical body language, scenery-first composition, and technical prompt-engineering language.
- Do not use pose libraries, movement quotas, eye-contact percentages, deterministic camera patterns, wardrobe templates, or hardcoded styling rotations.
- {authority}""".strip()


UNSUPPORTED_CREATOR_FACT_GUARD = (
    "Do not invent pets, partners, properties, possessions, relationships, "
    "career events, travel history, or biographical facts absent from the "
    "canonical creator documents or the operator's concept."
)

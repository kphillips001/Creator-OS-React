"""Provider render guidance unique to Photoshoot Studio."""

PHOTOSHOOT_SAFE_RENDER_LOCK = """
PHOTOSHOOT SAFE CONTINUITY LOCK - NON-NEGOTIABLE:
Preserve the creator's identity, face, natural body proportions, skin tone, and realistic anatomy from the active reference.
Continue the established wardrobe, hair, makeup, accessories, location, lighting, camera style, and visual tone unless the written Photoshoot direction explicitly changes one of them.
Keep camera distance, lens character, perspective, and image realism consistent with the established shoot.
Vary only the pose, expression, framing, body orientation, hand placement, eye contact, or subtle movement requested by the written direction.
Keep the result natural and non-sensual. Do not escalate wardrobe, exposure, posing, expression, or mood into teasing, erotic, nude, or explicit content.
""".strip()


def enforce_photoshoot_safe_render_lock(prompt: str) -> str:
    cleaned = str(prompt or "").strip()
    if not cleaned or "PHOTOSHOOT SAFE CONTINUITY LOCK" in cleaned:
        return cleaned
    return f"{cleaned}\n\n{PHOTOSHOOT_SAFE_RENDER_LOCK}"

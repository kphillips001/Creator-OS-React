"""Shared provider-neutral facial rendering foundation for canonical Ava."""

CANONICAL_FACIAL_NATURALISM_SECTION = "CANONICAL AVA FACIAL NATURALISM"

CANONICAL_FACIAL_NATURALISM = f"""
{CANONICAL_FACIAL_NATURALISM_SECTION} - NON-NEGOTIABLE:
Preserve Ava's exact facial identity, facial anatomy, proportions, and recognizable features from the canonical reference image.
Render her expression like a real creator camera-roll photo: candid, emotionally alive, slightly asymmetrical, with natural facial muscle tension and believable human expression.
Preserve realistic skin and facial texture, natural pores, and photographic detail without smoothing or reshaping her face.
Expression intent may change her mood, gaze, and emotional performance, but must not redefine her facial geometry or canonical identity.
Identity continuity must never flatten the requested expression into a vacant, blank, deadpan, or catalog-neutral beauty face.
When expression guidance asks for teasing, seductive, alluring, naughty, or intimate energy, deliver that performance clearly in the eyes and mouth while keeping her identity stable.
Avoid mannequin face, pageant smile, frozen expression, plastic symmetry, generic beauty-face replacement, and exaggerated or overacted facial performance.
""".strip()


def ensure_canonical_facial_naturalism(prompt_text: str) -> str:
    """Append the canonical foundation exactly once to a rendered prompt."""
    cleaned = str(prompt_text or "").strip()
    if not cleaned:
        return CANONICAL_FACIAL_NATURALISM
    if CANONICAL_FACIAL_NATURALISM_SECTION in cleaned:
        return cleaned
    return f"{cleaned}\n\n{CANONICAL_FACIAL_NATURALISM}"

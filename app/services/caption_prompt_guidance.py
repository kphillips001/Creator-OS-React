"""Shared prompt guidance for Creator OS caption generation."""

NATURAL_EMOJI_INSTRUCTION = (
    "Every caption MUST include emojis. Use emojis naturally and contextually "
    "inside the caption. Sprinkle 1-4 appropriate emojis throughout the sentence "
    "where they support the meaning, emotion, setting, object, action, or mood. "
    "Place at least one emoji mid-caption among the words — never only a single "
    "emoji stuck on the end, and never leave a caption with zero emojis. "
    "Do not simply append emojis to the beginning or end. Avoid generic emoji "
    "clusters. Emojis should feel like a real creator wrote them."
)


def natural_emoji_instruction_bullet() -> str:
    return f"- {NATURAL_EMOJI_INSTRUCTION}"

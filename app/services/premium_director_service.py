import os
import re

from dotenv import load_dotenv

from app.services.wavespeed_grok_service import generate_prompts_with_grok
from app.prompts.premium_prompt_builder import (
    build_premium_grok_prompt,
)

load_dotenv()


def split_numbered_prompts(raw_text) -> list[str]:
    if not raw_text:
        return []

    if isinstance(raw_text, list):
        return [
            str(item).strip()
            for item in raw_text
            if str(item).strip()
        ]

    parts = re.split(
        r"\n\s*\d+\.\s+",
        "\n" + str(raw_text).strip(),
    )

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


def generate_premium_prompts(
    creative_tags: str,
    prompt_count: int = 10,
    optional_direction: str | None = None,
) -> list[str]:

    api_key = os.getenv("GROK_API_KEY")

    if not api_key:
        raise ValueError(
            "Missing GROK_API_KEY in .env"
        )

    grok_instruction_prompt = build_premium_grok_prompt(
        creative_tags=creative_tags,
        prompt_count=prompt_count,
        optional_direction=optional_direction,
    )

    raw_response = generate_prompts_with_grok(
        grok_instruction_prompt,
        api_key,
    )

    prompts = split_numbered_prompts(
        raw_response
    )

    return prompts[:prompt_count]


def generate_explicit_prompts(
    creative_tags: str,
    prompt_count: int = 10,
) -> list[str]:

    api_key = os.getenv("GROK_API_KEY")

    if not api_key:
        raise ValueError(
            "Missing GROK_API_KEY in .env"
        )

    explicit_instruction = f"""
Generate exactly {prompt_count} bold premium image prompts.

Use the creator tags as the creative seed:

{creative_tags}

Requirements:
- Return exactly {prompt_count} prompts.
- Number each prompt.
- Each prompt must be one single line.
- Each prompt must feature the same woman.
- Preserve identity consistency, face, body shape, hair, skin tone, and overall appearance.
- Make the scenes more daring, intimate, and premium than standard prompts.
- Use adult glamour direction without graphic sexual action.
- Vary setting, pose, wardrobe state, camera angle, body position, mood, and composition.
- Do not repeat the same room twice.
- Do not repeat the same pose twice.
- Do not repeat the same camera angle twice.
- Avoid professional studio photography.
- Make it feel like realistic creator-made premium content for paying subscribers.
- Keep each prompt concise and image-generation ready.
- Do not include markdown.
- Do not include explanations.
"""

    raw_response = generate_prompts_with_grok(
        explicit_instruction,
        api_key,
    )

    prompts = split_numbered_prompts(
        raw_response
    )

    return prompts[:prompt_count]

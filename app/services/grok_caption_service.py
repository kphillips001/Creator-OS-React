import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from app.services.caption_prompt_guidance import natural_emoji_instruction_bullet


class GrokCaptionService:
    def __init__(self):
        load_dotenv()

        api_key = os.getenv("GROK_API_KEY")
        if not api_key:
            raise ValueError("GROK_API_KEY is missing from .env")

        self.model = os.getenv("GROK_MODEL", "grok-4.1-fast-non-reasoning")
        base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    def generate_caption(
        self,
        chat_history: list,
        content_metadata: dict,
    ) -> str:
        system_prompt = f"""
You are writing the NEXT paid PPV message in a private Fanvue conversation.

CRITICAL:
- Continue directly from the last message in the conversation.
- Make it feel natural, personal, and not generic.
- Reference what was just said when possible.
- This is NOT a generic caption.

RULES:
- Keep it to 1 sentence.
- Do NOT sound like marketing.
- Do NOT fully describe the content.
- Maintain a strong curiosity gap.
- Do NOT give away the content for free.
- Do NOT mention AI.
- Slightly bolder and more tempting than GPT, but still controlled.
{natural_emoji_instruction_bullet()}
"""

        metadata_prompt = f"""
Content metadata:
- classification: {content_metadata.get("classification")}
- tier: {content_metadata.get("tier")}
- tags: {content_metadata.get("tags")}
- summary: {content_metadata.get("summary")}

Task:
Write one strong paid PPV message that continues the conversation and makes the locked content hard to resist.
"""

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(chat_history)
        messages.append({"role": "user", "content": metadata_prompt})

        print("\n[GROK CAPTION SERVICE - 1 ON 1]")
        print(f"Model: {self.model}")
        print(f"Messages sent: {len(messages)}")

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.95,
            max_tokens=80,
        )

        return completion.choices[0].message.content.strip()

    def generate_mass_ppv_caption(
        self,
        content_metadata: dict,
        image_url: str,
    ) -> str:
        system_prompt = f"""
You are writing a high-converting mass PPV caption for Fanvue.

GOAL:
Get as many users as possible to unlock the content.

STYLE:
- Bold
- Teasing
- Seductive
- Slightly dominant
- Mass appeal (not personal)

RULES:
- Use the image to inspire the caption
- Focus on tease, body positioning, or tension
- Do NOT describe explicit sexual acts
- Do NOT give everything away
- Create curiosity and desire
- Make them feel like they need to open it
{natural_emoji_instruction_bullet()}
- 1–2 sentences max
"""

        metadata_prompt = f"""
Content metadata:
- classification: {content_metadata.get("classification")}
- tier: {content_metadata.get("tier")}
- tags: {content_metadata.get("tags")}
- summary: {content_metadata.get("summary")}

Write a bold mass PPV caption that makes users want to unlock this immediately.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": metadata_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]

        print("\n[GROK MASS PPV CAPTION]")
        print(f"Model: {self.model}")
        print(f"Messages sent: {len(messages)}")

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=1.0,
            max_tokens=80,
        )

        return completion.choices[0].message.content.strip()

    def generate_wall_captions(
        self,
        content_metadata: dict,
        image_url: str,
    ) -> list[str]:
        system_prompt = f"""
You are generating spicy, flirty social media captions for a Fanvue creator.

GOAL:
Create engaging, seductive captions that attract attention and tease the viewer.

STYLE:
- Playful
- Teasing
- Confident
- Slightly naughty, but not explicit
- High engagement

RULES:
- Generate EXACTLY 5 different captions (no more, no less)
- Each caption must be 1–2 sentences max
{natural_emoji_instruction_bullet()}
- Do NOT describe explicit sexual acts
- Do NOT sound robotic or repetitive
- Make each caption feel natural and unique
- Focus on teasing, curiosity, and attraction
- Avoid generic phrases — make each caption feel specific to the image

OUTPUT FORMAT (STRICT):
- Return ONLY a numbered list
- EXACTLY 5 captions
- No extra text, no explanations

1. caption
2. caption
3. caption
4. caption
5. caption
"""

        metadata_prompt = f"""
Content metadata:
- classification: {content_metadata.get("classification")}
- tags: {content_metadata.get("tags")}
- themes: {content_metadata.get("themes")}
- summary: {content_metadata.get("summary")}

Generate 5 spicy caption options for a wall post.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": metadata_prompt},
                    {"type": "image_url", "image_url": {"url": image_url}},
                ],
            },
        ]

        print("\n[GROK WALL CAPTION GENERATOR]")
        print(f"Model: {self.model}")
        print(f"Messages sent: {len(messages)}")

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=1.1,
            max_tokens=250,
        )

        raw_text = completion.choices[0].message.content.strip()

        print("\n[GROK WALL RAW RESPONSE]")
        print(raw_text)

        captions = []

        for line in raw_text.splitlines():
            line = line.strip()

            if not line:
                continue

            cleaned = re.sub(r"^\d+[\).\-\s]+", "", line).strip()
            cleaned = cleaned.strip('"').strip("'").strip()

            if cleaned:
                captions.append(cleaned)

        print("\n[GROK WALL PARSED CAPTIONS]")
        print(captions)

        return captions

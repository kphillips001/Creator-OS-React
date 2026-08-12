import os
import re
import json
from enum import Enum
from typing import Any, Mapping

from dotenv import load_dotenv
from openai import OpenAI

from app.services.caption_prompt_guidance import natural_emoji_instruction_bullet
from app.services.llm_json_parser import parse_llm_json


class CaptionProfile(str, Enum):
    CONTENT_VAULT_PPV = "CONTENT_VAULT_PPV"
    CONTENT_VAULT_PHOTOSHOOT_BUNDLE = "CONTENT_VAULT_PHOTOSHOOT_BUNDLE"


class CaptionTone(str, Enum):
    CLASSY = "CLASSY"
    RAUNCHY = "RAUNCHY"


_EMOJI_RULES = f"""Emoji rules (mandatory for ALL five captions):
{natural_emoji_instruction_bullet()}
- ALL five captions must include emojis — zero exceptions.
- Put 2-4 relevant emojis woven through the words (for example after a key noun/verb/feeling), not parked only at the end.
- Bad: "Come unlock this nude stare 🔥"
- Good: "Come unlock 🔥 this nude stare while my tongue teases you 👅😈"
- Reject end-only emoji decoration. If an emoji is at the end, there must already be at least one earlier in the caption.

Return strict JSON only:
{{"captions":[{{"text":"..."}},{{"text":"..."}},{{"text":"..."}},{{"text":"..."}},{{"text":"..."}}]}}
Exactly five objects. No style field. No extra keys."""

_SHARED_INTELLIGENCE_RULES = """How to use the intelligence (always):
- No image is attached. Use the full 3-source intelligence package.
- Prefer concrete sexual/exposure evidence from GPT Vision and NudeNet over soft aesthetic language from Grok Vision.
- If operator guidance is provided, treat it as ground truth about the photo and prioritize it even when auto intelligence is softer or incomplete.
- Operator guidance also sets intensity of what to emphasize; do not soft-wash the core act out of the captions.
- Without operator guidance, never invent acts, fluids, partners, toys, or exposure the intelligence does not support.
- Never invent prices, URLs, scarcity counts, purchase numbers, or platform identifiers.

Shared craft rules:
- First-person as the woman in the photo, speaking to him.
- 1-2 short sentences per caption. Specific to THIS image's pose, expression, hands, mouth, and exposure.
- Vary angle across the five captions (eye contact, body/reveal, hands/mouth action, private invitation, unlock urge) without labeling styles.
- Create unlock desire. This is paid PPV wall copy."""

CONTENT_VAULT_PPV_CLASSY_PROMPT = f"""You write paid Content Vault wall captions that make men unlock the photo.

Selected tone: CLASSY — seductive and elevated.
Naughty but classy high-end creator voice: confident, intimate, sexually charged.
Not crude porn spam. Not soft lifestyle fluff. Not corporate marketing.
Your only job: five distinct captions that make a male buyer want to unlock right now.

{_SHARED_INTELLIGENCE_RULES}

Classy language rules:
- Suggestive and salacious, but elevated — tease the hottest detail without sounding trashy.
- Prefer elegant erotic wording over crude slang.
- Allowed when earned by the image/guidance: bare, naked, nude, breasts, body, tongue, fingers, open for you, between my legs, spread for you, every inch, intimate, dripping tension, unlock.
- Avoid crude/porn-spam words: cunt, pussy, tits, cock, fuck, slut, whore, wet hole, tight hole, "see inside", "every wet inch", and similar.
- Do not over-describe genitals in graphic detail. Imply the explicit moment with heat and invitation.
- Bad: "Tits out and pussy exposed as I spread myself... come stare at every wet inch"
- Good: "Eyes on you 👀 while I open myself just enough to make you desperate to unlock 🔥"
- Good: "Tongue out 👅 and completely bare — unlock if you want the full view I'm holding for you 😈"

{_EMOJI_RULES}"""

CONTENT_VAULT_PPV_RAUNCHY_PROMPT = f"""You write paid Content Vault wall captions that make men unlock the photo.

Selected tone: RAUNCHY — direct and dirty.
Still first-person creator unlock copy, but hotter and more explicit about the act.
Not soft lifestyle fluff. Not corporate marketing. Not cartoon degradation spam.
Your only job: five distinct captions that make a male buyer ache to unlock right now.

{_SHARED_INTELLIGENCE_RULES}

Raunchy language rules:
- Be direct about the sexual act when intelligence or operator guidance supports it.
- Allowed when earned: pussy, clit, tits, ass, fingers, rubbing, spreading, dripping, wet, cum, finish, release, squirt, tongue, naked, between my legs.
- Name the hottest supported detail instead of vague "sensual shower" language.
- If guidance says she is touching/rubbing herself, building to climax, wet/dripping, etc., the captions must reflect that act — do not collapse into soft tongue-only tease.
- Still write like a desirable woman selling an unlock, not a spam bot.
- Avoid pure degradation spam and empty shock words with no scene detail (no random slut/whore chains).
- Bad: "Playful wet seduction in the shower 🔥"
- Good: "On the shower floor for you 👀 tongue out while my fingers work my clit 🔥 unlock before I finish 😈"
- Good: "Watch me rub myself open 🔥 dripping down my thighs — unlock if you want the rest 👅"

{_EMOJI_RULES}"""

CONTENT_VAULT_PPV_PROMPTS = {
    CaptionTone.CLASSY: CONTENT_VAULT_PPV_CLASSY_PROMPT,
    CaptionTone.RAUNCHY: CONTENT_VAULT_PPV_RAUNCHY_PROMPT,
}

CONTENT_VAULT_BUNDLE_PROMPTS = {
    tone: prompt.replace(
        "make men unlock the photo", "make men unlock the complete Photoshoot Bundle"
    ).replace(
        "five distinct captions that make a male buyer want to unlock right now",
        "five distinct captions that make a male buyer want to unlock the complete set right now",
    ).replace(
        "five distinct captions that make a male buyer ache to unlock right now",
        "five distinct captions that make a male buyer ache to unlock the complete set right now",
    ) + """

Bundle rules (mandatory):
- This product is one Photoshoot Bundle containing multiple paid images, not one image.
- Every caption must clearly sell the complete multi-image set. It may state the exact paid_image_count or use natural full-set language.
- Make clear the buyer unlocks the complete set/all included photos.
- Never count or imply that the promotional teaser is paid bundle content.
- Never invent a different quantity, price, or URL.
"""
    for tone, prompt in CONTENT_VAULT_PPV_PROMPTS.items()
}

# Backward-compatible alias used by older imports/tests.
CONTENT_VAULT_PPV_SYSTEM_PROMPT = CONTENT_VAULT_PPV_CLASSY_PROMPT

_RETRY_HINTS = {
    CaptionTone.CLASSY: (
        "\n\nRETRY: Your previous JSON failed quality checks. "
        "Return 5 NEW captions. Keep them CLASSY — seductive and elevated, not crude. "
        "EVERY caption must include at least two emojis woven through the words "
        "(not only at the end). "
        "Example shape: 'My eyes 👀 hold you while I open myself just for you 🔥😈'."
    ),
    CaptionTone.RAUNCHY: (
        "\n\nRETRY: Your previous JSON failed quality checks. "
        "Return 5 NEW captions. Keep them RAUNCHY — direct and dirty about the act. "
        "EVERY caption must include at least two emojis woven through the words "
        "(not only at the end). "
        "Example shape: 'My fingers 😈 work my clit while I stare at you 👀🔥'."
    ),
}


class GrokCaptionService:
    def __init__(self, client=None):
        load_dotenv()

        api_key = os.getenv("GROK_API_KEY")
        if not api_key and client is None:
            raise ValueError("GROK_API_KEY is missing from .env")

        self.model = os.getenv("GROK_MODEL", "grok-4.1-fast-non-reasoning")
        base_url = os.getenv("GROK_BASE_URL", "https://api.x.ai/v1")

        self.client = client or OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    _MAX_GENERATE_ATTEMPTS = 3

    def generate(
        self,
        *,
        profile: CaptionProfile | str,
        context: Mapping[str, Any],
        guidance: str | None = None,
        tone: CaptionTone | str = CaptionTone.CLASSY,
    ) -> dict:
        """Generate PPV unlock captions from persisted multi-source intelligence only."""
        selected_profile = CaptionProfile(profile)
        if selected_profile not in {
            CaptionProfile.CONTENT_VAULT_PPV,
            CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE,
        }:
            raise ValueError(f"Unsupported caption profile: {selected_profile.value}")
        if isinstance(tone, CaptionTone):
            selected_tone = tone
        else:
            selected_tone = CaptionTone(str(tone or CaptionTone.CLASSY.value).strip().upper())
        bundle = selected_profile == CaptionProfile.CONTENT_VAULT_PHOTOSHOOT_BUNDLE
        system_prompt = (CONTENT_VAULT_BUNDLE_PROMPTS if bundle else CONTENT_VAULT_PPV_PROMPTS)[selected_tone]
        normalized = {
            key: value for key, value in dict(context).items()
            if value not in (None, "", [], (), {})
        }
        operator_guidance = " ".join(str(guidance or "").split()).strip()
        if len(operator_guidance) > 500:
            raise ValueError("Caption guidance must be 500 characters or fewer.")
        base_user_content = (
            f"Tone selected by operator: {selected_tone.value}.\n"
            + ("Write 5 unlock captions for this complete Photoshoot Bundle using the " if bundle
               else "Write 5 unlock captions for this image using the ")
            + "persisted 3-source intelligence below.\n"
            + json.dumps(normalized, ensure_ascii=False)
        )
        if operator_guidance:
            base_user_content += (
                "\n\nOperator guidance (priority creative direction about what is "
                "visually true / what to emphasize — use this even if auto "
                "intelligence is softer; match this act under the selected tone):\n"
                + operator_guidance
            )
        last_error: Exception | None = None
        for attempt in range(1, self._MAX_GENERATE_ATTEMPTS + 1):
            user_content = base_user_content
            if attempt > 1:
                user_content += _RETRY_HINTS[selected_tone]
            try:
                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=1.0,
                    max_tokens=700,
                    response_format={"type": "json_object"},
                )
                raw = parse_llm_json(
                    completion.choices[0].message.content,
                    model_name=self.model,
                    caller="GrokCaptionService.generate",
                )
                # Prefer woven multi-emoji captions; only hard-require presence on final attempt.
                require_woven = attempt < self._MAX_GENERATE_ATTEMPTS
                captions = self._validate_options(
                    raw, require_woven_emojis=require_woven,
                    paid_image_count=(int(normalized["paid_image_count"]) if bundle else None),
                )
                return {
                    "profile": selected_profile.value,
                    "tone": selected_tone.value,
                    "captions": captions,
                }
            except ValueError as error:
                last_error = error
                continue
        raise ValueError(str(last_error) if last_error else "Grok could not generate captions.")

    # Emoji sequences including common ZWJ / variation-selector forms.
    _EMOJI_RE = re.compile(
        "(?:"
        "[\U0001F1E0-\U0001F1FF]{2}"
        "|[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
        "\U0001F900-\U0001F9FF\U0000200D\U0001F3FB-\U0001F3FF]"
        ")+"
    )
    _TRAILING_EMOJI_CLUSTER_RE = re.compile(
        r"(?:(?:\s)|"
        r"[\U0001F1E0-\U0001F1FF]{2}|"
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0000FE00-\U0000FE0F"
        r"\U0001F900-\U0001F9FF\U0000200D\U0001F3FB-\U0001F3FF]"
        r")+$"
    )

    @classmethod
    def _validate_options(
        cls,
        raw: Mapping[str, Any],
        *,
        require_woven_emojis: bool = True,
        paid_image_count: int | None = None,
    ) -> list[dict[str, str]]:
        values = raw.get("captions") if isinstance(raw, Mapping) else None
        if not isinstance(values, list) or len(values) != 5:
            raise ValueError("Grok must return exactly five caption options.")
        options: list[dict[str, str]] = []
        fingerprints: set[str] = set()
        for value in values:
            if isinstance(value, str):
                text = " ".join(value.split()).strip()
            elif isinstance(value, Mapping):
                text = " ".join(str(value.get("text") or "").split()).strip()
            else:
                raise ValueError("Every Grok caption option must be text.")
            if not text:
                raise ValueError("Grok returned an empty caption.")
            if re.search(r"https?://|www\.|\$\s*\d|\b(?:USD|Fanvue Media Link)\b", text, re.I):
                raise ValueError("Grok captions must not contain URLs or invented prices.")
            if paid_image_count is not None:
                cls.validate_bundle_caption(text, paid_image_count)
            cls._require_emojis(text, require_woven=require_woven_emojis)
            fingerprint = re.sub(r"\W+", "", text).lower()
            if fingerprint in fingerprints:
                raise ValueError("Grok captions must be distinct.")
            fingerprints.add(fingerprint)
            options.append({"text": text})
        return options

    @staticmethod
    def validate_bundle_caption(text: str, paid_image_count: int) -> str:
        value = " ".join(str(text or "").split()).strip()
        if not value:
            raise ValueError("A Bundle caption is required.")
        if re.search(r"https?://|www\.|\$\s*\d|\b(?:USD|Fanvue Media Link)\b", value, re.I):
            raise ValueError("Bundle captions must not contain URLs or invented prices.")
        quantities = {int(item) for item in re.findall(r"\b\d+\b", value)}
        if quantities and any(item != int(paid_image_count) for item in quantities):
            raise ValueError("Bundle captions must not invent a different quantity.")
        number_words = {
            "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
        }
        stated_words = re.findall(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:photos?|images?|pics?|shots?)\b",
            value, re.I,
        )
        if any(number_words[word.lower()] != int(paid_image_count) for word in stated_words):
            raise ValueError("Bundle captions must not invent a different quantity.")
        if not re.search(r"\b(?:photos|images|pics|shots|set|collection|bundle|whole shoot|full shoot)\b", value, re.I):
            raise ValueError("Bundle captions must clearly describe the multi-image product.")
        if re.search(r"\b(?:unlock|buy|get)\s+(?:this|the|one)\s+(?:photo|image|pic)\b", value, re.I):
            raise ValueError("Bundle captions must not imply Single Image delivery.")
        return value

    @staticmethod
    def validate_operator_bundle_caption(text: str) -> str:
        """Validate destination safety without imposing Grok copy-quality rules."""
        value = " ".join(str(text or "").split()).strip()
        if not value:
            raise ValueError("A Content Vault caption is required.")
        if re.search(r"https?://|www\.|\$\s*\d|\b(?:USD|Fanvue Media Link)\b", value, re.I):
            raise ValueError("Content Vault captions must not contain URLs or invented prices.")
        return value

    @classmethod
    def _require_emojis(cls, text: str, *, require_woven: bool) -> None:
        matches = list(cls._EMOJI_RE.finditer(text))
        if not matches:
            raise ValueError("Every Grok caption must include emojis.")
        if not require_woven:
            return
        if len(matches) < 2:
            raise ValueError("Every Grok caption must weave at least two emojis through the text.")
        body = cls._TRAILING_EMOJI_CLUSTER_RE.sub("", text).rstrip()
        if not body or not cls._EMOJI_RE.search(body):
            raise ValueError(
                "Grok captions must place emojis throughout the text, not only at the end."
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

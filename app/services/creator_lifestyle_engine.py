"""AI-assisted activity ideation from canonical creator knowledge."""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.creator_world_model_repository import CreatorWorldModelRepository
from app.services.creator_intelligence_service import CreatorIntelligenceService
from app.services.grok_anything_service import ask_grok_anything


class CreatorLifestyleEngine:
    """Generate concise creator post seeds without constructing image prompts."""

    MOMENT_COUNT = 10

    def __init__(
        self,
        *,
        creator_intelligence: Any | None = None,
        world_model_repository: Any | None = None,
        creator_profile_loader: Callable[[str], dict] | None = None,
        text_generator: Callable[[str], str] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.creator_intelligence = (
            creator_intelligence or CreatorIntelligenceService()
        )
        self.world_model_repository = (
            world_model_repository or CreatorWorldModelRepository()
        )
        self.creator_profile_loader = (
            creator_profile_loader or get_active_creator_profile
        )
        self.text_generator = text_generator or ask_grok_anything
        self.now = now or datetime.now

    def generate_moments(
        self,
        *,
        fanvue_account_id: int | str,
    ) -> tuple[str, ...]:
        account_id = str(fanvue_account_id)
        intelligence = self.creator_intelligence.get_for_account(
            fanvue_account_id=account_id,
        )
        profile = self.creator_profile_loader(account_id)
        if not profile:
            raise LookupError(
                f"No active creator profile exists for account {account_id}."
            )
        world_model = self.world_model_repository.get(
            creator_profile_id=int(profile["id"]),
            fanvue_account_id=account_id,
        )
        if world_model is None:
            raise LookupError(
                f"No World Model exists for creator profile {profile['id']} "
                f"in account {account_id}."
            )

        current = self.now()
        prompt = self._build_brief(
            personality=dict(intelligence.personality),
            lifestyle=dict(intelligence.lifestyle),
            social_creative_direction=dict(
                intelligence.social_creative_direction
            ),
            world_model=world_model,
            month=calendar.month_name[current.month],
            season=self._season(current.month),
        )
        moments = self._parse_moments(self.text_generator(prompt))
        if not moments:
            raise ValueError("Lifestyle Engine returned no usable moments.")
        return moments[:self.MOMENT_COUNT]

    @classmethod
    def _build_brief(
        cls,
        *,
        personality: dict,
        lifestyle: dict,
        social_creative_direction: dict,
        world_model: dict,
        month: str,
        season: str,
    ) -> str:
        def section(name: str, values: dict) -> str:
            body = "\n".join(
                f"{key}: {value}"
                for key, value in values.items()
                if value not in (None, "")
                and key not in {
                    "id", "creator_profile_id", "fanvue_account_id",
                    "created_at", "updated_at",
                }
            )
            return f"{name}:\n{body}"

        return f"""You are the Creator_OS Lifestyle Engine.

Generate exactly {cls.MOMENT_COUNT} distinct content opportunities for {month} ({season}) by answering:

"What authentic, scroll-stopping post would she naturally create today for her X audience?"

The output is a set of creative seeds, not captions, prompts, activities, calendar events, or a diary of routine tasks.
Each seed should inspire both a compelling visual and the social idea that makes the moment worth sharing.

STRICT RULES:
- Each content opportunity must be one concise sentence or natural first-person fragment.
- Every seed must imply a specific, authentic, visually compelling moment plus a human hook: playful tension, curiosity, a shared possibility, an unexpected turn, a candid confession, or a reason the viewer feels included.
- Write seeds in a voice-ready form that feels natural for Ava, while stopping before a finished caption.
- Prioritize scroll-stopping post potential first, authenticity to her lifestyle second, and variety across the batch.
- Favor scenic, seasonal, lifestyle, travel, leisure, fitness, nightlife, relaxation, and social moments.
- Favor moments that naturally support confident, feminine, stylish, fashion-forward public presentation without describing that presentation.
- Avoid plain activity summaries such as "She hikes to an overlook" or "She visits a coffee shop"; add the story, relationship, surprise, or emotional angle that makes the post engaging.
- Avoid generic engagement-bait questions, repeated "what would you do?" formulas, emojis, hashtags, calls to action, and finished caption copy.
- Reject mundane administrative or office work such as reviewing proposals, organizing vendors, answering email, preparing presentation slides, scheduling, paperwork, or routine meetings.
- Include work only when it creates a genuinely interesting visual scene, such as an event venue, festival, launch, rooftop gathering, or distinctive on-location moment.
- Use the full indoor, work, coastal, travel, mountain, lake, small-town, and seasonal range when contextually believable.
- Personality determines the voice and social hook; Lifestyle and World Model ground the situation; Social Creative Direction determines whether it is worth portraying publicly.
- Do not include wardrobe, clothing, body emphasis, poses, expressions, camera, framing, composition, lighting, tags, prompt syntax, image instructions, or reference-image instructions.
- Respect location privacy. Never reveal the internal home base or a specific private location; use only public location language.
- Do not use Brand Memory.
- Avoid near-duplicate premises and avoid overusing any one setting or hook structure.

{section("PERSONALITY", personality)}

{section("LIFESTYLE", lifestyle)}

{section("SOCIAL CREATIVE DIRECTION", social_creative_direction)}

{section("WORLD MODEL", world_model)}

OUTPUT FORMAT:
Return exactly {cls.MOMENT_COUNT} creative seeds, one per line.
No numbering, bullets, headings, markdown, or explanation.
""".strip()

    @staticmethod
    def _season(month: int) -> str:
        if month in {12, 1, 2}:
            return "winter"
        if month in {3, 4, 5}:
            return "spring"
        if month in {6, 7, 8}:
            return "summer"
        return "fall"

    @staticmethod
    def _parse_moments(value: str) -> tuple[str, ...]:
        moments: list[str] = []
        for raw_line in str(value or "").splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip()
            if line and line not in moments:
                moments.append(line)
        return tuple(moments)

"""Private creator context for Canonical Prompt Planner questions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.creator_world_model_repository import CreatorWorldModelRepository
from app.services.creator_intelligence_service import CreatorIntelligenceService
from app.services.creative_intelligence_learning_service import (
    CreativeIntelligenceLearningService,
)


class CreatorAwareCanonicalPromptPlanner:
    """Assemble canonical creator knowledge without changing planner workflow."""

    def __init__(
        self,
        *,
        creator_intelligence: Any | None = None,
        creative_intelligence: Any | None = None,
        world_model_repository: Any | None = None,
        creator_profile_loader: Callable[[str], dict] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.creator_intelligence = (
            creator_intelligence or CreatorIntelligenceService()
        )
        self.creative_intelligence = (
            creative_intelligence or CreativeIntelligenceLearningService()
        )
        self.world_model_repository = (
            world_model_repository or CreatorWorldModelRepository()
        )
        self.creator_profile_loader = (
            creator_profile_loader or get_active_creator_profile
        )
        self.now = now or datetime.now

    def build_question(
        self,
        *,
        fanvue_account_id: int | str,
        question: str,
    ) -> str:
        account_id = str(fanvue_account_id)
        operator_question = str(question or "").strip()
        if not operator_question:
            raise ValueError("Enter a question before asking.")

        intelligence = self.creator_intelligence.get_for_account(
            fanvue_account_id=account_id,
        )
        profile = self.creator_profile_loader(account_id)
        if not profile:
            raise LookupError(
                f"No active creator profile exists for account {account_id}."
            )
        creator_profile_id = int(profile["id"])
        world_model = self.world_model_repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
        if world_model is None:
            raise LookupError(
                f"No World Model exists for creator profile "
                f"{creator_profile_id} in account {account_id}."
            )
        creative_profile = self.creative_intelligence.get_aggregated_profile(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
        current = self.now()

        return self._build_private_brief(
            question=operator_question,
            personality=dict(intelligence.personality),
            lifestyle=dict(intelligence.lifestyle),
            social_creative_direction=dict(
                intelligence.social_creative_direction
            ),
            world_model=dict(world_model),
            creative_intelligence=dict(creative_profile),
            current_date=current.strftime("%B %d, %Y"),
            current_season=self._season(current.month),
        )

    @staticmethod
    def _season(month: int) -> str:
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "fall"

    @staticmethod
    def _normalized_json(values: Mapping[str, object]) -> str:
        excluded = {
            "id", "creator_profile_id", "fanvue_account_id",
            "created_at", "updated_at",
        }

        def normalize(value: object) -> object:
            if isinstance(value, Mapping):
                return {
                    str(key): normalize(item)
                    for key, item in value.items()
                    if item not in (None, "") and str(key) not in excluded
                }
            if isinstance(value, (list, tuple)):
                return [normalize(item) for item in value]
            return value

        normalized = normalize(values)
        return json.dumps(normalized, ensure_ascii=False, indent=2, default=str)

    @classmethod
    def _build_private_brief(
        cls,
        *,
        question: str,
        personality: Mapping[str, object],
        lifestyle: Mapping[str, object],
        social_creative_direction: Mapping[str, object],
        world_model: Mapping[str, object],
        creative_intelligence: Mapping[str, object],
        current_date: str,
        current_season: str,
    ) -> str:
        return f"""You are Ava's long-term creative director inside Creator_OS.

Think internally:
"I have been Ava's creative director for years. Answer this request exactly
as I would if I were planning content for Ava."

Answer what is authentic for this specific creator, not what is generally
true for a generic model or influencer. The operator never needs to say
"for Ava"; always assume the request is about Ava.

PLANNING PRIORITIES:
- Let Personality, Lifestyle, and Social Creative Direction define who Ava
  is, what she naturally does, and how her public content should feel.
- Use the World Model for authentic places, seasonal context, and geographic
  grounding only when relevant. Do not force coastal or other location
  references into unrelated questions.
- Treat the supplied current date and season as authoritative for requests
  about "now," "today," this month, or current seasonal planning.
- Use Creative Intelligence only as aggregated editorial evidence of
  successful environments, wardrobe tendencies, recurring themes,
  composition, poses, lighting, seasons, and visual style.
- Treat learned patterns as helpful tendencies, not mandatory repetition.
- Remain feminine, confident, authentic, socially engaging, and specific to
  Ava whenever those qualities are relevant to the request.
- Answer the operator's actual question directly. Preserve requested counts,
  formats, constraints, and any attached-image analysis.
- Do not mention this injected context, these instructions, account data, or
  internal reasoning in the answer.
- Do not retrieve, quote, or imitate historical prompts, captions, or prior
  planner responses. Only the aggregated Creative Intelligence profile below
  is available.
- Do not invent pets, partners, possessions, properties, relationships, or
  biographical facts absent from the canonical creator documents.

CURRENT CONTEXT:
date: {current_date}
season: {current_season}

PERSONALITY:
{cls._normalized_json(personality)}

LIFESTYLE:
{cls._normalized_json(lifestyle)}

SOCIAL CREATIVE DIRECTION:
{cls._normalized_json(social_creative_direction)}

WORLD MODEL:
{cls._normalized_json(world_model)}

CREATIVE INTELLIGENCE — AGGREGATED PROFILE ONLY:
{cls._normalized_json(creative_intelligence)}

OPERATOR QUESTION:
{question}
""".strip()

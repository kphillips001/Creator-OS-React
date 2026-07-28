"""Creator-aware enhancement isolated to Canonical Planner selections."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.creator_aware_canonical_prompt_planner import (
    CreatorAwareCanonicalPromptPlanner,
)
from app.services.editorial_quality_guidance import (
    UNSUPPORTED_CREATOR_FACT_GUARD,
    editorial_quality_guidance,
)
from app.services.grok_anything_service import ask_grok_anything


class CanonicalPlannerEnhancementService:
    def __init__(
        self,
        *,
        context_builder: Any | None = None,
        text_generator: Callable[[str], str] | None = None,
    ) -> None:
        self.context_builder = (
            context_builder or CreatorAwareCanonicalPromptPlanner()
        )
        self.text_generator = text_generator or ask_grok_anything

    def enhance(
        self,
        *,
        fanvue_account_id: int | str,
        selected_item: str,
    ) -> str:
        concept = str(selected_item or "").strip()
        if not concept:
            raise ValueError("Selected planner item is required.")
        private_brief = self.context_builder.build_question(
            fanvue_account_id=str(fanvue_account_id),
            question=f"""Enhance this selected Canonical Planner concept as Ava's creative director:

{concept}

Return one production-ready creative direction. Preserve every explicit part
of the selected concept as authoritative: wardrobe, setting, activity,
movement, mood, narrative premise, and operator constraints.

Add only relevant canonical Ava context. Ask internally: "How would Ava
naturally bring this selected concept to life?" Do not force coastal,
athletic, or other context when it is unrelated.

{editorial_quality_guidance(workflow="canonical_planner")}

{UNSUPPORTED_CREATOR_FACT_GUARD}

Return only the enhanced creative direction, without headings, analysis,
bullets, or internal context.""",
        )
        enhanced = str(self.text_generator(private_brief) or "").strip()
        return enhanced or concept

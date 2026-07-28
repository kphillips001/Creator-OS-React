"""Creator-aware editorial enhancement for operator-authored Creative Concepts."""

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


class ManualCreativeConceptEnhancementService:
    """Expand a manual concept without surrendering operator authority."""

    def __init__(
        self,
        *,
        context_builder: Any | None = None,
        text_generator: Callable[[str], str] | None = None,
    ) -> None:
        self.context_builder = context_builder or CreatorAwareCanonicalPromptPlanner()
        self.text_generator = text_generator or ask_grok_anything

    def enhance(
        self,
        *,
        fanvue_account_id: int | str,
        creative_concept: str,
    ) -> str:
        concept = str(creative_concept or "").strip()
        if not concept:
            raise ValueError("Creative Concept is required.")
        private_brief = self.context_builder.build_question(
            fanvue_account_id=str(fanvue_account_id),
            question=f"""Enhance this operator-authored Creative Concept as Ava's creative director:

{concept}

Return one production-ready natural-language creative direction. Preserve
every explicit element of the operator's concept. Expansion may enrich the
scene, environment, movement, lighting, camera composition, mood, wardrobe
details left unspecified by the operator, and editorial story, but must not
replace or contradict the original concept.

Use canonical creator context only when relevant to this concept. Do not force
coastal, athletic, premium, or other context into a scene where it does not
naturally belong.

{editorial_quality_guidance(workflow="manual_creative_concept")}

{UNSUPPORTED_CREATOR_FACT_GUARD}

Return only the enhanced creative direction. Do not include headings,
analysis, bullets, hidden context, or internal reasoning.""",
        )
        enhanced = str(self.text_generator(private_brief) or "").strip()
        return enhanced or concept

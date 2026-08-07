"""Creator-aware editorial enhancement for operator-authored Creative Concepts."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.services.canonical_ava_service import CanonicalAvaService
from app.services.creator_aware_canonical_prompt_planner import (
    CreatorAwareCanonicalPromptPlanner,
)
from app.services.editorial_quality_guidance import (
    UNSUPPORTED_CREATOR_FACT_GUARD,
    editorial_quality_guidance,
)
from app.services.grok_anything_service import ask_grok_anything
from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService


class ManualCreativeConceptEnhancementService:
    """Expand a manual concept without surrendering operator authority."""

    def __init__(
        self,
        *,
        context_builder: Any | None = None,
        canonical_ava: Any | None = None,
        text_generator: Callable[[str], str] | None = None,
    ) -> None:
        self.context_builder = context_builder or CreatorAwareCanonicalPromptPlanner()
        self.canonical_ava = canonical_ava or CanonicalAvaService()
        self.text_generator = text_generator or ask_grok_anything

    def enhance(
        self,
        *,
        fanvue_account_id: int | str,
        creative_concept: str,
        include_canonical_ava: bool = True,
        diagnostic_trace_id: str | None = None,
    ) -> str:
        concept = str(creative_concept or "").strip()
        if not concept:
            raise ValueError("Creative Concept is required.")
        diagnostic = GenerationRequestDiagnosticService()
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="manual_creative_concept",
                          stage="1_workflow_origin", value="manual_creative_concept")
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="manual_creative_concept",
                          stage="2_initial_creative_input", value=concept)
        identity_context = (
            f"""\nCANONICAL AVA — IDENTITY AUTHORITY:\n{self.canonical_ava.prompt_context()}\n
Use this identity contract without adding to it, interpreting it, or redefining
Ava. Your only responsibility is creative intent: scene, activity, wardrobe,
pose, location, lighting, expression, composition, and editorial variation.
"""
            if include_canonical_ava else ""
        )
        private_brief = self.context_builder.build_question(
            fanvue_account_id=str(fanvue_account_id),
            question=f"""Enhance this operator-authored Creative Concept as a creative director:

{concept}
{identity_context}

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
        diagnostic.record(
            trace_id=diagnostic_trace_id, workflow_origin="manual_creative_concept",
            stage="3_ava_creator_context_supplied",
            value={"canonicalAvaInjected": include_canonical_ava,
                   "canonicalAvaBlock": identity_context,
                   "completeEnhancerRequest": private_brief},
        )
        enhanced = str(self.text_generator(private_brief) or "").strip()
        diagnostic.record(trace_id=diagnostic_trace_id,
                          workflow_origin="manual_creative_concept",
                          stage="4_enhanced_creative_intent", value=enhanced or concept)
        return enhanced or concept

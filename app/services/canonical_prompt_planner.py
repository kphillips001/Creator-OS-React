"""Canonical prompt planning entrypoint for Creator OS generation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import time
from typing import Any, Mapping

from app.services.explicit_prompt_service import (
    EXPLICIT_EDITORIAL_GUIDANCE,
    extract_editorial_direction,
    generate_explicit_prompts,
)
from app.services.premium_director_service import generate_premium_prompts
from app.services.photoshoot_prompt_service import generate_safe_photoshoot_prompts

LOGGER = logging.getLogger("creator_os.canonical_planner")


@dataclass(frozen=True)
class CanonicalPromptPlanningRequest:
    mode: str
    creative_tags: str
    prompt_count: int = 5
    optional_direction: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CanonicalPromptPlanningResult:
    mode: str
    prompts: tuple[str, ...]
    prompt_builder: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


class CanonicalPromptPlanner:
    """Provider-neutral planning facade used by preview and generation paths."""

    SUPPORTED_MODES = (
        "premium",
        "explicit",
        "video",
        "social",
        "photoshoot_safe",
        "photoshoot_premium",
        "photoshoot_explicit",
    )

    def plan(self, request: CanonicalPromptPlanningRequest) -> CanonicalPromptPlanningResult:
        started = time.perf_counter()
        LOGGER.info("[Planner] START plan() requested_mode=%s timestamp=%.6f", request.mode, time.time())
        mode = self.normalize_mode(request.mode)
        LOGGER.info("[Planner] Planner selected mode=%s elapsed_ms=%.2f", mode, (time.perf_counter() - started) * 1000)
        creative_tags = str(request.creative_tags or "").strip()
        if not creative_tags:
            raise ValueError("Creative tags are required for prompt planning.")
        prompt_count = max(1, min(int(request.prompt_count or 1), 12))

        if mode in {"explicit", "photoshoot_explicit"}:
            LOGGER.info("[Planner] Building explicit prompt mode=%s elapsed_ms=%.2f", mode, (time.perf_counter() - started) * 1000)
            explicit_input = dict(request.metadata or {})
            original_source = str(
                explicit_input.get("original_source")
                or explicit_input.get("source_text")
                or creative_tags
            ).strip()
            prompts = tuple(
                generate_explicit_prompts(
                    enhanced_explicit_tags=creative_tags,
                    prompt_count=prompt_count,
                    optional_setting=request.optional_direction,
                    original_source=original_source,
                    concept_tier=str(
                        explicit_input.get("concept_tier")
                        or explicit_input.get("conceptTier")
                        or "softcore"
                    ),
                    operator_expression=(
                        explicit_input.get("operator_expression")
                        or explicit_input.get("operatorExpression")
                    ),
                )
            )
            prompt_builder = "canonical_explicit_prompt_planner"
            editorial_directions = tuple(
                extract_editorial_direction(prompt)
                for prompt in prompts
            )
        else:
            if mode == "photoshoot_safe":
                LOGGER.info("[Planner] Building safe Photoshoot prompt elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)
                prompts = tuple(
                    generate_safe_photoshoot_prompts(
                        creative_tags=creative_tags,
                        prompt_count=prompt_count,
                        optional_direction=request.optional_direction,
                    )
                )
            else:
                LOGGER.info("[Planner] Building premium prompt mode=%s elapsed_ms=%.2f", mode, (time.perf_counter() - started) * 1000)
                prompts = tuple(
                    generate_premium_prompts(
                        creative_tags=creative_tags,
                        prompt_count=prompt_count,
                        optional_direction=request.optional_direction,
                    )
                )
            prompt_builder = (
                f"canonical_{mode}_prompt_planner"
                if mode.startswith("photoshoot_")
                else "canonical_seedream_premium_planner"
            )
            editorial_directions = ()

        result = CanonicalPromptPlanningResult(
            mode=mode,
            prompts=tuple(prompt for prompt in prompts if str(prompt or "").strip())[:prompt_count],
            prompt_builder=prompt_builder,
            metadata={
                "canonical_planner": "creator_os",
                "planning_mode": mode,
                "provider_target": (
                    "seedream_5_0_pro"
                    if mode not in {"explicit", "photoshoot_explicit"}
                    else "provider_selected"
                ),
                "provider_optimization": (
                    "seedream_5_0_pro_native"
                    if mode not in {"explicit", "photoshoot_explicit"}
                    else "explicit_provider_optimization"
                ),
                **(
                    {
                        "editorial_directions": editorial_directions,
                        "editorial_guidance": (
                            EXPLICIT_EDITORIAL_GUIDANCE.metadata()
                        ),
                        "canonical_planning_order": (
                            "scene",
                            "explicit_editorial_guidance",
                            "editorial_direction",
                            "explicit_expression_profile",
                            "wardrobe",
                            "creator_identity",
                            "visual_quality",
                            "provider_optimization",
                        ),
                        "explicit_input": explicit_input,
                    }
                    if mode in {"explicit", "photoshoot_explicit"}
                    else {}
                ),
                **(
                    {
                        "canonical_planning_order": (
                            "scene",
                            "editorial_guidance",
                            "editorial_direction",
                            "wardrobe",
                            "creator_identity",
                            "visual_quality",
                            "provider_optimization",
                        ),
                        "prompt_architecture": "seedream_premium_canonical",
                    }
                    if mode not in {"explicit", "photoshoot_explicit"}
                    else {}
                ),
                **dict(request.metadata or {}),
            },
        )
        LOGGER.info("[Planner] END plan() mode=%s prompts=%s elapsed_ms=%.2f", mode, len(result.prompts), (time.perf_counter() - started) * 1000)
        return result

    @classmethod
    def normalize_mode(cls, mode: str | None) -> str:
        value = str(mode or "premium").strip().lower()
        aliases = {
            "premium_teaser": "premium",
            "story_sequence": "premium",
            "premium_studio": "premium",
            "prompt_workshop": "premium",
            "nsfw": "explicit",
            "photoshoot": "photoshoot_premium",
        }
        normalized = aliases.get(value, value)
        if normalized not in cls.SUPPORTED_MODES:
            raise ValueError(f"Unsupported canonical planning mode: {mode!r}")
        return normalized

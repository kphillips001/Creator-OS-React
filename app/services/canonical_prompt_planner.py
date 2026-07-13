"""Canonical prompt planning entrypoint for Creator OS generation workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.services.explicit_prompt_service import generate_explicit_prompts
from app.services.premium_director_service import generate_premium_prompts


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

    SUPPORTED_MODES = ("premium", "explicit", "photoshoot", "video", "social")

    def plan(self, request: CanonicalPromptPlanningRequest) -> CanonicalPromptPlanningResult:
        mode = self.normalize_mode(request.mode)
        creative_tags = str(request.creative_tags or "").strip()
        if not creative_tags:
            raise ValueError("Creative tags are required for prompt planning.")
        prompt_count = max(1, min(int(request.prompt_count or 1), 12))

        if mode == "explicit":
            prompts = tuple(
                generate_explicit_prompts(
                    enhanced_explicit_tags=creative_tags,
                    prompt_count=prompt_count,
                    optional_setting=request.optional_direction,
                )
            )
            prompt_builder = "canonical_explicit_prompt_planner"
        else:
            prompts = tuple(
                generate_premium_prompts(
                    creative_tags=creative_tags,
                    prompt_count=prompt_count,
                    optional_direction=request.optional_direction,
                )
            )
            prompt_builder = (
                "canonical_photoshoot_prompt_planner"
                if mode == "photoshoot"
                else "canonical_premium_prompt_planner"
            )

        return CanonicalPromptPlanningResult(
            mode=mode,
            prompts=tuple(prompt for prompt in prompts if str(prompt or "").strip())[:prompt_count],
            prompt_builder=prompt_builder,
            metadata={
                "canonical_planner": "creator_os",
                "planning_mode": mode,
                "renderer_neutral": True,
                **dict(request.metadata or {}),
            },
        )

    @classmethod
    def normalize_mode(cls, mode: str | None) -> str:
        value = str(mode or "premium").strip().lower()
        aliases = {
            "premium_teaser": "premium",
            "story_sequence": "premium",
            "premium_studio": "premium",
            "prompt_workshop": "premium",
            "nsfw": "explicit",
        }
        normalized = aliases.get(value, value)
        if normalized not in cls.SUPPORTED_MODES:
            return "premium"
        return normalized

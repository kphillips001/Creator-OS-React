"""Creative Director domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4


CREATIVE_MODE_OPTIONS = (
    "social_safe",
    "spicy",
    "premium_teaser",
    "story_sequence",
)


@dataclass(frozen=True)
class CreativeDirectorSettings:
    creator_profile_id: int
    default_mode: str = "social_safe"
    default_prompt_count: int = 5
    favorite_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreativeSession:
    session_id: str
    creator_profile_id: int
    creative_tags: tuple[str, ...]
    creative_mode: str
    prompt_count: int
    reference_asset_id: int | None
    status: str = "planned"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str | None = None
    source: str = "creative_director"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PromptPlan:
    plan_id: str
    session_id: str
    creator_profile_id: int
    prompt_text: str
    creative_mode: str
    creative_tags: tuple[str, ...]
    reference_asset_id: int | None
    reference_asset_path: str | None
    creative_rationale: str
    prompt_metadata: Mapping[str, Any]
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "planned"


@dataclass(frozen=True)
class CreativeRecommendation:
    title: str
    tags: tuple[str, ...]
    creative_mode: str
    rationale: str


@dataclass(frozen=True)
class PromptAssistantBatch:
    batch_id: str
    creator_profile_id: int
    request_text: str
    lane: str
    prompts: tuple[str, ...]
    used_prompt_numbers: tuple[int, ...] = ()
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


@dataclass(frozen=True)
class CreativeHistoryEntry:
    session: CreativeSession
    prompt_plan: PromptPlan | None = None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"

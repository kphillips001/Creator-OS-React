"""Provider-neutral Caption Studio models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.generation_engine import utc_now


class CaptionPlatform(str, Enum):
    X = "x"
    INSTAGRAM = "instagram"
    TELEGRAM = "telegram"
    FANVUE = "fanvue"
    PRODUCT = "product"
    STORY = "story"
    MARKETING = "marketing"


class CaptionStyle(str, Enum):
    SOCIAL_SAFE = "social_safe"
    PREMIUM = "premium"
    DIRECT = "direct"
    PLAYFUL = "playful"
    LUXURY = "luxury"
    STORYTELLING = "storytelling"


@dataclass(frozen=True)
class CaptionTemplate:
    template_id: str
    platform: str
    style: str
    body: str
    tone: str = "confident"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptionSession:
    session_id: str
    creator_profile_id: int
    platform: str
    style: str
    tone: str
    source_generated_image_id: str | None = None
    social_queue_item_id: str | None = None
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CaptionRequest:
    caption_request_id: str
    session_id: str
    creator_profile_id: int
    platform: str
    style: str
    tone: str
    source_text: str
    variation_count: int = 3
    source_generated_image_id: str | None = None
    social_queue_item_id: str | None = None
    template_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CaptionResult:
    caption_result_id: str
    caption_request_id: str
    session_id: str
    platform: str
    variations: tuple[str, ...]
    selected_text: str | None = None
    formatter_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CaptionHistory:
    history_id: str
    session_id: str
    caption_request_id: str
    caption_result_id: str
    platform: str
    selected_text: str | None = None
    created_at: str = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

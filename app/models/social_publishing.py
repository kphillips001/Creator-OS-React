"""Provider-neutral Social Publishing models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.generation_engine import utc_now


class SocialPlatform(str, Enum):
    X = "x"
    TELEGRAM = "telegram"
    INSTAGRAM = "instagram"
    THREADS = "threads"
    FACEBOOK = "facebook"
    BLUESKY = "bluesky"
    TIKTOK = "tiktok"
    FUTURE_PROVIDER = "future_provider"


class SocialPublishStatus(str, Enum):
    QUEUED = "queued"
    SCHEDULED = "scheduled"
    POSTED = "posted"
    FAILED = "failed"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class SocialQueueItem:
    queue_item_id: str
    generated_image_id: str
    creator_profile_id: int
    platform: str
    status: str = SocialPublishStatus.QUEUED.value
    scheduled_for: str | None = None
    creator_notes: str | None = None
    caption_id: str | None = None
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)
    reference_asset_id: int | None = None
    creative_mode: str | None = None
    prompt_text: str | None = None
    output_reference: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None


@dataclass(frozen=True)
class SocialPublishingSession:
    session_id: str
    creator_profile_id: int
    queue_item_ids: tuple[str, ...]
    platform: str
    title: str = "Social Publishing Session"
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SocialPublishRequest:
    publish_request_id: str
    queue_item_id: str
    platform: str
    caption_id: str | None = None
    scheduled_for: str | None = None
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SocialPublishHistory:
    history_id: str
    queue_item_id: str
    platform: str
    status: str
    message: str | None = None
    created_at: str = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)

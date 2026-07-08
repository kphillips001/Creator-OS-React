"""Provider-neutral Photoshoot Queue domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


PHOTOSHOOT_ASSET_METADATA_KEY = "photoshoot_session"


@dataclass(frozen=True)
class PhotoshootRequest:
    request_id: str
    session_id: str
    prompt_plan_id: str
    prompt_text: str
    sequence_index: int
    creative_mode: str
    reference_asset_id: int | None
    status: str = "queued"
    generation_job_id: str | None = None
    imported_asset_ids: tuple[int, ...] = ()
    review_status: str | None = None
    review_notes: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None


@dataclass(frozen=True)
class PhotoshootProgress:
    total_prompts: int
    queued_prompts: int
    active_prompts: int
    awaiting_review: int
    approved_images: int
    rejected_images: int
    imported_assets: int
    percent_complete: float


@dataclass(frozen=True)
class PhotoshootResult:
    session_id: str
    approved_asset_ids: tuple[int, ...] = ()
    rejected_asset_ids: tuple[int, ...] = ()
    regenerated_request_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhotoshootSession:
    session_id: str
    creator_profile_id: int
    title: str
    reference_asset_id: int | None
    creative_mode: str
    status: str = "queued"
    provider_id: str = "future_provider"
    creator_notes: str | None = None
    creative_continuity: Mapping[str, Any] = field(default_factory=dict)
    request_ids: tuple[str, ...] = ()
    current_request_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PhotoshootQueue:
    sessions: tuple[PhotoshootSession, ...] = ()
    requests: tuple[PhotoshootRequest, ...] = ()

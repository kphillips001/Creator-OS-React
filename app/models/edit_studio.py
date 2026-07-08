"""Edit Studio domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


EDIT_MODE_OPTIONS = (
    "single_image",
    "multi_image",
    "face_replacement",
    "style_transfer",
    "variation",
)


@dataclass(frozen=True)
class EditSession:
    session_id: str
    creator_profile_id: int
    source_image_ids: tuple[str, ...]
    edit_mode: str
    title: str = "Edit Session"
    status: str = "active"
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EditRequest:
    edit_request_id: str
    session_id: str
    creator_profile_id: int
    source_image_ids: tuple[str, ...]
    edit_mode: str
    edit_prompt: str
    provider_id: str
    reference_image_id: str | None = None
    reference_asset_id: int | None = None
    batch_size: int = 1
    status: str = "queued"
    generation_job_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EditHistoryEntry:
    session: EditSession
    edit_request: EditRequest | None = None

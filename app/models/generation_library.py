"""Generation Library domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


GENERATION_LIBRARY_PAGE_SIZE = 24


@dataclass(frozen=True)
class GeneratedImageRecord:
    image_id: str
    generation_job_id: str
    generation_request_id: str
    generation_result_id: str
    output_reference: str
    creator_profile_id: int
    provider_id: str
    prompt_plan_id: str
    prompt_text: str
    creative_mode: str | None
    reference_asset_id: int | None
    generation_recipe_id: str | None = None
    photoshoot_session_id: str | None = None
    photoshoot_request_id: str | None = None
    generation_date: str = field(default_factory=utc_now)
    status: str = "active"
    review_state: str = "unreviewed"
    selected: bool = False
    imported_asset_id: int | None = None
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    prompt_metadata: Mapping[str, Any] = field(default_factory=dict)
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str | None = None
    is_staged: bool = False
    staged_at: str | None = None
    content_classification: str | None = None
    classification_source: str | None = None


@dataclass(frozen=True)
class GenerationLibraryFilter:
    search: str | None = None
    content_origin: str | None = None
    provider_id: str | None = None
    status: str | None = None
    creative_mode: str | None = None
    photoshoot_session_id: str | None = None
    creator_profile_id: int | None = None
    reference_asset_id: int | None = None
    selected_only: bool = False
    sort: str = "newest"


@dataclass(frozen=True)
class GenerationLibraryResult:
    records: tuple[GeneratedImageRecord, ...]
    filters: GenerationLibraryFilter
    total: int


@dataclass(frozen=True)
class GenerationLibraryActionResult:
    success: bool
    message: str
    image_ids: tuple[str, ...] = ()
    imported_asset_ids: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()

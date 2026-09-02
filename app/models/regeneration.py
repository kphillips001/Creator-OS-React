"""Durable backend workspace for recipe-based regenerated variations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class RegenerationRun:
    operation_id: UUID
    creator_profile_id: int
    source_generated_image_id: str
    source_recipe_id: UUID
    requested_count: int
    status: str
    workspace_dismissed_at: datetime | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RegenerationResult:
    regeneration_result_id: UUID
    operation_id: UUID
    variation_index: int
    status: str
    generation_job_id: str | None = None
    generation_result_id: str | None = None
    generated_image_id: str | None = None
    generation_recipe_id: UUID | None = None
    media_path: str | None = None
    disposition: str = "PENDING_REVIEW"
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class RegenerationEligibility:
    can_regenerate: bool
    reason_code: str | None = None
    reason: str | None = None
    source_generated_image_id: str | None = None
    source_recipe_id: UUID | None = None

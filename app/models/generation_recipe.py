"""Immutable generation-recipe provenance captured at provider submission."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class GenerationRecipeReference:
    recipe_reference_id: UUID
    recipe_id: UUID
    position: int
    role: str
    source_type: str
    source_id: str | None = None
    asset_id: int | None = None
    generated_image_id: str | None = None
    media_type: str | None = None
    content_sha256: str | None = None
    provider_reference_kind: str | None = None
    diagnostic_metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class GenerationRecipe:
    recipe_id: UUID
    schema_version: str
    generation_job_id: str | None
    generation_request_id: str
    prompt_plan_id: str | None
    submission_index: int
    source_workflow: str | None
    workflow_origin: str | None
    provider_id: str
    provider_family: str | None
    provider_adapter: str
    provider_adapter_version: str | None
    provider_endpoint: str | None
    provider_model: str | None
    provider_model_revision: str | None
    generation_type: str
    media_type: str
    planned_prompt: str
    final_prompt: str
    final_prompt_sha256: str
    creative_mode: str | None
    render_policy: str | None
    render_policy_version: str | None
    normalized_settings: Mapping[str, Any]
    output_format: str | None
    width: int | None
    height: int | None
    aspect_ratio: str | None
    resolution: str | None
    seed: str | None
    seed_policy: str
    sanitized_provider_payload: Mapping[str, Any]
    sanitized_payload_sha256: str
    source_generated_image_id: str | None = None
    source_recipe_id: UUID | None = None
    regeneration_operation_id: UUID | None = None
    references: tuple[GenerationRecipeReference, ...] = ()
    created_at: datetime | None = None


@dataclass(frozen=True)
class GenerationRecipeExecution:
    recipe_id: UUID
    status: str
    provider_request_id: str | None = None
    provider_terminal_status: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class GenerationRecipeOutput:
    recipe_output_id: UUID
    recipe_id: UUID
    generation_result_id: str | None
    generated_image_id: str | None
    output_index: int
    output_reference_hash: str | None = None
    created_at: datetime | None = None

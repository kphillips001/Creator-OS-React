"""Presentation models for the Asset Library read surface."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class AssetLibraryFilter:
    search: str | None = None
    media_type: str | None = None
    classification: str | None = None
    eligible_only: bool = True
    limit: int = 500
    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    status: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    creator_profile_id: int | None = None
    product_id: str | None = None
    experience_id: str | None = None
    publishing_status: str | None = None
    has_local_vault_original: bool | None = None
    has_derivative_preview: bool | None = None
    is_reference_image: bool | None = None
    legacy_content_id: int | None = None


@dataclass(frozen=True)
class AssetPublishingSummary:
    status: str
    detail: str = ""
    provider_media_id: str | None = None
    provider_preview_media_id: str | None = None
    provider_full_media_id: str | None = None
    provider_error: str | None = None


@dataclass(frozen=True)
class AssetExperiencePresentation:
    experience_id: str
    title: str | None = None
    experience_type: str | None = None
    summary: str | None = None
    cover_asset_id: int | None = None
    themes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    mood: str | None = None
    story_progression: str | None = None
    publishing_readiness: str | None = None
    relationship_source: str | None = None
    compatibility: bool = False


@dataclass(frozen=True)
class AssetRelationshipSummary:
    product_count: int = 0
    experience_count: int = 0
    legacy_product_id: str | None = None
    product_ids: tuple[str, ...] = ()
    product_delivery_types: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    experience_summaries: tuple[AssetExperiencePresentation, ...] = ()


@dataclass(frozen=True)
class AssetStorageSummary:
    original_path: str | None = None
    original_source: str | None = None
    original_exists: bool = False
    local_vault_path: str | None = None
    legacy_file_path: str | None = None
    media_metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AssetDerivativeSummary:
    preview_path: str | None = None
    derivative_type: str = "blur"
    storage: str | None = None
    generated_at: str | None = None
    source: str | None = None
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class AssetLibraryItem:
    asset_id: int
    file_name: str | None
    media_type: str
    classification: str | None
    status: str | None
    is_active: bool
    created_at: datetime | None
    preview_path: str | None
    original_path: str | None
    tags: tuple[str, ...]
    themes: tuple[str, ...]
    ready_for_rotation: bool
    relationship: AssetRelationshipSummary
    publishing: AssetPublishingSummary
    is_reference_image: bool = False


@dataclass(frozen=True)
class AssetLibraryDetails:
    item: AssetLibraryItem
    creator_profile_id: int | None = None
    confidence: float | None = None
    summary: str | None = None
    reasoning: str | None = None
    risk_flags: tuple[str, ...] = ()
    is_explicit: bool = False
    nudity_labels: tuple[str, ...] = ()
    nudity_level: str | None = None
    sexual_intensity: str | None = None
    storage: AssetStorageSummary | None = None
    derivative: AssetDerivativeSummary | None = None
    relationship: AssetRelationshipSummary | None = None
    publishing: AssetPublishingSummary | None = None
    analysis_provenance: Mapping[str, Any] | None = None
    gpt_vision_result: Mapping[str, Any] | None = None
    nudenet_result: Any = None
    classification_result: Mapping[str, Any] | None = None
    media_metadata: Mapping[str, Any] | None = None
    asset_understanding: Any = None
    intelligence_profile: Any = None


@dataclass(frozen=True)
class AssetLibraryResult:
    items: tuple[AssetLibraryItem, ...]
    filters: AssetLibraryFilter
    total: int


@dataclass(frozen=True)
class AssetLibraryActionResult:
    success: bool
    message: str
    asset_id: int | None = None
    data: Mapping[str, Any] | None = None

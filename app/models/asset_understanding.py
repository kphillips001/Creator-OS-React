"""Canonical normalized understanding of an imported Creator OS Asset."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


@dataclass(frozen=True)
class AssetUnderstandingIdentity:
    asset_id: int
    creator_profile_id: int | None = None
    file_name: str | None = None
    original_filename: str | None = None
    upload_intent: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class AssetUnderstandingMedia:
    media_type: str = "unknown"
    local_vault_path: str | None = None
    legacy_file_path: str | None = None
    runtime_path: str | None = None
    runtime_source: str | None = None
    runtime_exists: bool = False
    mime_type: str | None = None
    file_extension: str | None = None
    size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    duration_seconds: float | None = None
    codec: str | None = None
    frame_rate: float | None = None
    video_analysis_status: str = "not_available"


@dataclass(frozen=True)
class AssetUnderstandingVisual:
    summary: str | None = None
    detected_themes: tuple[str, ...] = ()
    suggested_tags: tuple[str, ...] = ()
    mood: str | None = None
    setting: str | None = None
    outfit: str | None = None
    pose: str | None = None
    activity: str | None = None
    objects: tuple[str, ...] = ()
    gpt_vision_result: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetUnderstandingSafety:
    risk_flags: tuple[str, ...] = ()
    nudity_labels: tuple[str, ...] = ()
    nudity_level: str | None = None
    sexual_intensity: str | None = None
    is_explicit: bool = False
    nudenet_result: Any = None


@dataclass(frozen=True)
class AssetUnderstandingClassification:
    classification: str | None = None
    confidence: float | None = None
    raw_gpt_classification: str | None = None
    final_classification: str | None = None
    rule_applied: str | None = None
    classification_result: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetUnderstandingMetadata:
    media_metadata: Mapping[str, Any] = field(default_factory=dict)
    duplicate_detection_status: str = "not_available"
    similarity_group_id: str | None = None
    perceptual_hash: str | None = None
    checksum: str | None = None


@dataclass(frozen=True)
class AssetUnderstandingProvenance:
    source: str | None = None
    analysis_version: str | None = None
    vision_model: str | None = None
    nudenet_enabled: bool = False
    upload_intent: str | None = None
    analysis_provenance: Mapping[str, Any] = field(default_factory=dict)
    reasoning: str | None = None


@dataclass(frozen=True)
class AssetUnderstandingReadiness:
    status: str | None = None
    is_active: bool = False
    is_test: bool = False
    ready_for_rotation: bool = False
    has_runtime_media: bool = False
    has_local_vault_media: bool = False
    has_visual_summary: bool = False
    has_classification: bool = False
    needs_review: bool = False
    review_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class AssetUnderstanding:
    identity: AssetUnderstandingIdentity
    media: AssetUnderstandingMedia = field(default_factory=AssetUnderstandingMedia)
    visual: AssetUnderstandingVisual = field(default_factory=AssetUnderstandingVisual)
    safety: AssetUnderstandingSafety = field(default_factory=AssetUnderstandingSafety)
    classification: AssetUnderstandingClassification = field(
        default_factory=AssetUnderstandingClassification
    )
    metadata: AssetUnderstandingMetadata = field(
        default_factory=AssetUnderstandingMetadata
    )
    provenance: AssetUnderstandingProvenance = field(
        default_factory=AssetUnderstandingProvenance
    )
    readiness: AssetUnderstandingReadiness = field(
        default_factory=AssetUnderstandingReadiness
    )

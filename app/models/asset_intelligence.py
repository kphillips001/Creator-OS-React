"""Canonical provider-neutral Asset Intelligence contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


ASSET_INTELLIGENCE_SCHEMA_VERSION = "asset_intelligence_profile_v1"


class AssetIntelligenceStatus(str, Enum):
    REGISTERED = "REGISTERED"
    PENDING = "PENDING"
    NUDENET_PENDING = "NUDENET_PENDING"
    NUDENET_RUNNING = "NUDENET_RUNNING"
    NUDENET_COMPLETE = "NUDENET_COMPLETE"
    NUDENET_FAILED = "NUDENET_FAILED"
    VISION_PENDING = "VISION_PENDING"
    VISION_RUNNING = "VISION_RUNNING"
    VISION_COMPLETE = "VISION_COMPLETE"
    VISION_FAILED = "VISION_FAILED"
    GROK_PENDING = "GROK_PENDING"
    GROK_RUNNING = "GROK_RUNNING"
    GROK_COMPLETE = "GROK_COMPLETE"
    GROK_FAILED = "GROK_FAILED"
    CONTENT_INTELLIGENCE_PENDING = "CONTENT_INTELLIGENCE_PENDING"
    CONTENT_INTELLIGENCE_RUNNING = "CONTENT_INTELLIGENCE_RUNNING"
    CONTENT_INTELLIGENCE_COMPLETE = "CONTENT_INTELLIGENCE_COMPLETE"
    CONTENT_INTELLIGENCE_FAILED = "CONTENT_INTELLIGENCE_FAILED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


@dataclass(frozen=True)
class AssetIntelligenceProviderResult:
    asset_id: int
    creator_profile_id: int
    provider: str
    raw_response: Any
    run_id: str | None = None
    execution_id: str | None = None
    normalized_fields: Mapping[str, Any] = field(default_factory=dict)
    field_confidence: Mapping[str, float] = field(default_factory=dict)
    status: AssetIntelligenceStatus = AssetIntelligenceStatus.READY
    provider_version: str | None = None
    result_id: str = field(default_factory=lambda: str(uuid4()))
    analyzed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class AssetIntelligenceProfile:
    asset_id: int
    creator_profile_id: int
    analysis_status: AssetIntelligenceStatus = AssetIntelligenceStatus.PENDING
    schema_version: str = ASSET_INTELLIGENCE_SCHEMA_VERSION
    analyzed_at: datetime | None = None

    title: str | None = None
    short_description: str | None = None
    detailed_description: str | None = None
    content_summary: str | None = None

    setting: str | None = None
    environment: str | None = None
    indoor_outdoor: str | None = None
    location_type: str | None = None
    season: str | None = None
    weather: str | None = None
    lighting: str | None = None
    objects: tuple[str, ...] = ()

    subject_count: int | None = None
    pose: str | None = None
    activity: str | None = None
    expression: str | None = None
    mood: str | None = None
    camera_framing: str | None = None
    camera_angle: str | None = None

    clothing: tuple[str, ...] = ()
    accessories: tuple[str, ...] = ()
    colors: tuple[str, ...] = ()
    hairstyle: str | None = None

    nudity_level: str | None = None
    explicit_content: bool | None = None
    visible_body_regions: tuple[str, ...] = ()
    sexual_intensity: str | None = None
    safety_classification: str | None = None
    risk_flags: tuple[str, ...] = ()

    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    content_categories: tuple[str, ...] = ()
    suggested_collections: tuple[str, ...] = ()

    suggested_use_cases: tuple[str, ...] = ()
    collection_suitability: Mapping[str, Any] = field(default_factory=dict)
    preview_suitability: str | None = None
    content_uniqueness: float | None = None
    quality_score: float | None = None

    overall_confidence: float | None = None
    field_confidence: Mapping[str, float] = field(default_factory=dict)
    provider_agreement: Mapping[str, Any] = field(default_factory=dict)

    created_at: datetime | None = None
    updated_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_payload(self) -> dict[str, Any]:
        excluded = {
            "asset_id",
            "creator_profile_id",
            "analysis_status",
            "schema_version",
            "analyzed_at",
            "created_at",
            "updated_at",
            "error_code",
            "error_message",
        }
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in excluded
        }

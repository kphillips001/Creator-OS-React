"""Provider-neutral Generation Engine domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import uuid4


def utc_now() -> str:
    return datetime.utcnow().isoformat()


def new_generation_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class GenerationStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRY = "retry"


class GenerationMediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class GenerationType(str, Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"


@dataclass(frozen=True)
class GenerationProvider:
    provider_id: str
    display_name: str
    enabled: bool = False
    supports_images: bool = True
    supports_video: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationProgress:
    current: int = 0
    total: int = 1
    percent: float = 0.0
    message: str = "Queued"


@dataclass(frozen=True)
class GenerationFailure:
    reason: str
    retryable: bool = True
    provider_error: str | None = None
    stage: str | None = None
    may_have_been_accepted: bool = False
    failed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class GenerationRequest:
    request_id: str
    creator_profile_id: int
    prompt_plan_id: str
    prompt_text: str
    reference_asset_id: int | None
    reference_asset_path: str | None
    provider_id: str
    generation_type: str
    media_type: str
    image_count: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class GenerationResult:
    result_id: str
    request_id: str
    job_id: str
    provider_id: str
    status: str
    generation_metadata: Mapping[str, Any] = field(default_factory=dict)
    execution_metadata: Mapping[str, Any] = field(default_factory=dict)
    image_metadata: Mapping[str, Any] = field(default_factory=dict)
    output_references: tuple[str, ...] = ()
    duration_seconds: float | None = None
    failure_reason: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class GenerationJob:
    job_id: str
    request: GenerationRequest
    status: str = GenerationStatus.QUEUED.value
    progress: GenerationProgress = field(default_factory=GenerationProgress)
    retry_count: int = 0
    max_retries: int = 0
    queued_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str = field(default_factory=utc_now)
    result: GenerationResult | None = None
    failure: GenerationFailure | None = None


@dataclass(frozen=True)
class GenerationQueue:
    jobs: tuple[GenerationJob, ...] = ()

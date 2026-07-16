"""Provider-neutral contracts for Asset Intelligence analysis runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Protocol, runtime_checkable
from uuid import uuid4


class AssetIntelligenceRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    READY = "READY"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProviderExecutionStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"

    @property
    def settled(self) -> bool:
        return self not in {self.PENDING, self.RUNNING}


class AssetIntelligenceErrorCode(str, Enum):
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"
    MEDIA_NOT_FOUND = "MEDIA_NOT_FOUND"
    UNSUPPORTED_MEDIA = "UNSUPPORTED_MEDIA"
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    NORMALIZATION_ERROR = "NORMALIZATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True)
class AssetIntelligenceProviderRequest:
    run_id: str
    asset_id: int
    creator_profile_id: int
    media_type: str
    managed_media_path: str
    original_filename: str
    schema_version: str
    provider_configuration: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssetIntelligenceProviderResponse:
    run_id: str
    asset_id: int
    provider_name: str
    provider_version: str
    status: ProviderExecutionStatus
    raw_response: Any = None
    normalized_fields: Mapping[str, Any] = field(default_factory=dict)
    field_confidence: Mapping[str, float] = field(default_factory=dict)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    error_code: AssetIntelligenceErrorCode | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None


@runtime_checkable
class AssetIntelligenceProviderAdapter(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def provider_version(self) -> str: ...

    @property
    def supported_media_types(self) -> frozenset[str]: ...

    def is_ready(self) -> bool: ...

    def analyze(
        self, request: AssetIntelligenceProviderRequest
    ) -> AssetIntelligenceProviderResponse: ...

    def normalize(self, raw_response: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AssetIntelligenceProviderPolicy:
    required_providers: tuple[str, ...] = ()
    optional_providers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        overlap = set(self.required_providers) & set(self.optional_providers)
        if overlap:
            raise ValueError(f"Providers cannot be both required and optional: {overlap}")
        if len(set(self.required_providers + self.optional_providers)) != len(
            self.required_providers + self.optional_providers
        ):
            raise ValueError("Provider policy contains duplicate names.")

    @property
    def all_providers(self) -> tuple[str, ...]:
        return self.required_providers + self.optional_providers


@dataclass(frozen=True)
class AssetIntelligenceRun:
    asset_id: int
    creator_profile_id: int
    schema_version: str
    required_providers: tuple[str, ...]
    optional_providers: tuple[str, ...]
    run_id: str = field(default_factory=lambda: str(uuid4()))
    status: AssetIntelligenceRunStatus = AssetIntelligenceRunStatus.PENDING
    is_current: bool = True
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_summary: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class AssetIntelligenceProviderExecution:
    run_id: str
    asset_id: int
    creator_profile_id: int
    provider_name: str
    provider_version: str | None
    attempt_number: int
    is_required: bool
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    status: ProviderExecutionStatus = ProviderExecutionStatus.PENDING
    result_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = None
    error_code: AssetIntelligenceErrorCode | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


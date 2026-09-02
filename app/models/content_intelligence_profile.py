"""Durable Content Intelligence profile contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ContentIntelligenceProfileStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    REANALYSIS_REQUIRED = "REANALYSIS_REQUIRED"


def is_content_intelligence_complete(
    status: ContentIntelligenceProfileStatus | str | None,
) -> bool:
    """Return whether a persisted Content Intelligence status is complete."""
    value = status.value if isinstance(status, ContentIntelligenceProfileStatus) else status
    return str(value or "").upper() == ContentIntelligenceProfileStatus.COMPLETE.value


CONTENT_INTELLIGENCE_SCHEMA_VERSION = "phase_3_10_2_content_intelligence_profile_v1"
CONTENT_INTELLIGENCE_ANALYSIS_VERSION = "content_intelligence_registration_v1"


@dataclass(frozen=True)
class ContentIntelligenceProfile:
    """Canonical persisted content-only intelligence for one Asset."""

    asset_id: int
    status: ContentIntelligenceProfileStatus
    schema_version: str = CONTENT_INTELLIGENCE_SCHEMA_VERSION
    analysis_version: str = CONTENT_INTELLIGENCE_ANALYSIS_VERSION
    required_components: tuple[str, ...] = ()
    completed_components: tuple[str, ...] = ()
    missing_components: tuple[str, ...] = ()
    retry_count: int = 0
    source_workflow: str | None = None
    approval_identity: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    content_profile: Mapping[str, Any] = field(default_factory=dict)
    normalized_context: Mapping[str, Any] = field(default_factory=dict)
    search_document: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    reanalysis_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    analysis_started_at: datetime | None = None
    analysis_completed_at: datetime | None = None
    last_successful_analysis_at: datetime | None = None

    @property
    def ready(self) -> bool:
        return is_content_intelligence_complete(self.status)

    def to_context(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "status": self.status.value,
            "ready": self.ready,
            "schema_version": self.schema_version,
            "analysis_version": self.analysis_version,
            "required_components": self.required_components,
            "completed_components": self.completed_components,
            "missing_components": self.missing_components,
            "retry_count": self.retry_count,
            "source_workflow": self.source_workflow,
            "approval_identity": dict(self.approval_identity),
            "provenance": dict(self.provenance),
            "content_profile": dict(self.content_profile),
            "normalized_context": dict(self.normalized_context),
            "search_document": self.search_document,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "reanalysis_reason": self.reanalysis_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "analysis_started_at": (
                self.analysis_started_at.isoformat()
                if self.analysis_started_at
                else None
            ),
            "analysis_completed_at": (
                self.analysis_completed_at.isoformat()
                if self.analysis_completed_at
                else None
            ),
            "last_successful_analysis_at": (
                self.last_successful_analysis_at.isoformat()
                if self.last_successful_analysis_at
                else None
            ),
        }

"""Provider-neutral Creator OS v1.0 certification read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class CreatorOSCertificationStatus(str, Enum):
    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"


@dataclass(frozen=True)
class CreatorOSValidationEvidence:
    source: str
    summary: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorOSValidationSection:
    name: str
    status: CreatorOSCertificationStatus
    evidence: tuple[CreatorOSValidationEvidence, ...] = ()
    missing_items: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorOSCertificationReport:
    certification_name: str = "Creator OS v1.0"
    status: CreatorOSCertificationStatus = CreatorOSCertificationStatus.FAIL
    sections: tuple[CreatorOSValidationSection, ...] = ()
    evidence: tuple[CreatorOSValidationEvidence, ...] = ()
    missing_items: tuple[str, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

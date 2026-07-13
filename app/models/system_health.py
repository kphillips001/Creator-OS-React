"""Presentation models for Creator OS system health."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str
    summary: str
    detail: str = ""
    value: str = ""
    guidance: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthSection:
    name: str
    checks: tuple[HealthCheck, ...]

    @property
    def status(self) -> str:
        statuses = {check.status for check in self.checks}
        if HealthStatus.CRITICAL.value in statuses:
            return HealthStatus.CRITICAL.value
        if HealthStatus.WARNING.value in statuses:
            return HealthStatus.WARNING.value
        if HealthStatus.UNKNOWN.value in statuses:
            return HealthStatus.UNKNOWN.value
        return HealthStatus.HEALTHY.value


@dataclass(frozen=True)
class QueueHealth:
    name: str
    count: int
    status: str = HealthStatus.HEALTHY.value
    detail: str = ""


@dataclass(frozen=True)
class SystemHealthReport:
    overall_status: str
    score: int
    headline: str
    sections: tuple[HealthSection, ...]
    queues: tuple[QueueHealth, ...] = ()
    warnings: tuple[HealthCheck, ...] = ()

    def section(self, name: str) -> HealthSection | None:
        for section in self.sections:
            if section.name == name:
                return section
        return None

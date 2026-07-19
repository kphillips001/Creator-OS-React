"""Provider-neutral persisted worker heartbeat models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class WorkerHeartbeatStatus(str, Enum):
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    IDLE = "IDLE"
    DEGRADED = "DEGRADED"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class WorkerHealthClassification(str, Enum):
    HEALTHY = "healthy"
    IDLE = "idle"
    STALE = "stale"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class WorkerHeartbeat:
    heartbeat_id: UUID
    worker_name: str
    worker_instance_id: str
    worker_type: str
    host_name: str
    status: WorkerHeartbeatStatus
    started_at: datetime
    last_heartbeat_at: datetime
    creator_profile_id: str | None = None
    account_id: int | None = None
    process_id: int | None = None
    application_version: str | None = None
    last_poll_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_error: str | None = None
    shutdown_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "WorkerHeartbeat":
        return cls(
            heartbeat_id=UUID(str(row["heartbeat_id"])), worker_name=str(row["worker_name"]),
            worker_instance_id=str(row["worker_instance_id"]), worker_type=str(row["worker_type"]),
            creator_profile_id=str(row["creator_profile_id"]) if row.get("creator_profile_id") is not None else None,
            account_id=int(row["account_id"]) if row.get("account_id") is not None else None,
            process_id=int(row["process_id"]) if row.get("process_id") is not None else None,
            host_name=str(row["host_name"]), application_version=row.get("application_version"),
            status=WorkerHeartbeatStatus(str(row["status"])), started_at=row["started_at"],
            last_heartbeat_at=row["last_heartbeat_at"], last_poll_at=row.get("last_poll_at"),
            last_success_at=row.get("last_success_at"), last_failure_at=row.get("last_failure_at"),
            last_error=row.get("last_error"), shutdown_at=row.get("shutdown_at"),
            metadata=dict(row.get("metadata") or {}), created_at=row.get("created_at"), updated_at=row.get("updated_at"),
        )

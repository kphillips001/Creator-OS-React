"""Canonical application-wide background operation model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

ACTIVE_OPERATION_STATUSES = frozenset({"QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED"})
TERMINAL_OPERATION_STATUSES = frozenset({"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"})


@dataclass(frozen=True)
class BackgroundOperation:
    operation_id: UUID
    operation_type: str
    originating_workspace: str
    creator_profile_id: int
    account_id: int | None
    subject_type: str
    subject_id: str
    idempotency_key: str
    executor_key: str
    status: str
    progress_current: int = 0
    progress_total: int = 0
    progress_percent: float = 0.0
    current_stage: str | None = None
    stage_message: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result_location: str | None = None
    result_reference: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancellation_supported: bool = False
    cancellation_requested_at: datetime | None = None
    worker_id: str | None = None
    lease_expires_at: datetime | None = None
    attempt_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)
    operation_version: str = "background_operation_v1"
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "BackgroundOperation":
        return cls(**{name: row.get(name) for name in cls.__dataclass_fields__})

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_OPERATION_STATUSES

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_OPERATION_STATUSES

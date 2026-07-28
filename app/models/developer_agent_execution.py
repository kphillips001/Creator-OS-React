"""Persistent, provider-neutral Developer Agent execution domain."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class DeveloperTaskStatus(str, Enum):
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DeveloperExecutionStatus(str, Enum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_FOR_INPUT = "WAITING_FOR_INPUT"
    TESTING = "TESTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class DeveloperAgentTask:
    task_id: UUID
    issue_identifier: str
    investigation_package: str
    implementation_task: str
    repository_path: str
    expected_branch: str
    status: DeveloperTaskStatus
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DeveloperAgentExecution:
    execution_id: UUID
    task_id: UUID
    status: DeveloperExecutionStatus
    codex_session_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    cancellation_reason: str | None
    final_report: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

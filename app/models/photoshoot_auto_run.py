"""Durable Photoshoot full-plan auto-run state."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class PhotoshootAutoRunState(str, Enum):
    READY = "READY"
    PREPARING = "PREPARING"
    GENERATING = "GENERATING"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    APPROVING = "APPROVING"
    ADVANCING = "ADVANCING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    PLAN_COMPLETE = "PLAN_COMPLETE"
    PHOTOSHOOT_COMPLETE = "PHOTOSHOOT_COMPLETE"


@dataclass(frozen=True)
class PhotoshootAutoRun:
    session_id: str
    state: str
    current_plan_index: int
    total_frames: int
    current_request_id: str | None = None
    worker_id: str | None = None
    claimed_at: Any = None
    lease_expires_at: Any = None
    attempt_count: int = 0
    last_error_code: str | None = None
    last_error_message: str | None = None
    failure_stage: str | None = None
    failed_frame_index: int | None = None
    failed_frame_title: str | None = None
    failed_provider: str | None = None
    failed_request_id: str | None = None
    failed_generation_job_id: str | None = None
    started_at: Any = None
    paused_at: Any = None
    resumed_at: Any = None
    completed_at: Any = None
    updated_at: Any = None
    stop_requested: bool = False
    auto_approve_enabled: bool = True
    review_mode: str = "AUTO_APPROVE"
    metadata: Mapping[str, Any] = field(default_factory=dict)

"""Lifecycle and classification service for independently running processes."""

from __future__ import annotations

import os
import platform
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from app.models.worker_heartbeat import WorkerHealthClassification, WorkerHeartbeat, WorkerHeartbeatStatus
from app.repositories.worker_heartbeat_repository import WorkerHeartbeatRepository


class WorkerHeartbeatService:
    MAX_ERROR_LENGTH = 1000

    def __init__(self, *, worker_name: str, worker_type: str, poll_interval_seconds: int,
                 creator_profile_id: str | int | None = None, account_id: int | None = None,
                 worker_instance_id: str | None = None, repository: Any | None = None,
                 process_id: int | None = None, host_name: str | None = None,
                 application_version: str | None = None, now: Any | None = None) -> None:
        self.worker_name = worker_name; self.worker_type = worker_type
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.stale_threshold_seconds = max(self.poll_interval_seconds * 3, 60)
        self.creator_profile_id = str(creator_profile_id) if creator_profile_id is not None else None
        self.account_id = account_id
        self.worker_instance_id = worker_instance_id or f"{worker_name.lower().replace(' ', '-')}-{uuid4()}"
        self.repository = repository or WorkerHeartbeatRepository()
        self.process_id = process_id if process_id is not None else os.getpid()
        self.host_name = host_name or platform.node() or "unknown"
        self.application_version = application_version or os.getenv("CREATOR_OS_VERSION")
        self.now = now or (lambda: datetime.now(timezone.utc))

    def register_startup(self) -> WorkerHeartbeat:
        at = self.now()
        return self.repository.register(WorkerHeartbeat(heartbeat_id=uuid4(), worker_name=self.worker_name,
            worker_instance_id=self.worker_instance_id, worker_type=self.worker_type,
            creator_profile_id=self.creator_profile_id, account_id=self.account_id, process_id=self.process_id,
            host_name=self.host_name, application_version=self.application_version,
            status=WorkerHeartbeatStatus.STARTING, started_at=at, last_heartbeat_at=at,
            metadata={"poll_interval_seconds": self.poll_interval_seconds, "stale_threshold_seconds": self.stale_threshold_seconds}))

    def heartbeat(self, *, idle: bool = False, metadata: Mapping[str, Any] | None = None):
        return self.repository.record_heartbeat(self.worker_instance_id, status=WorkerHeartbeatStatus.IDLE if idle else WorkerHeartbeatStatus.RUNNING, at=self.now(), metadata=metadata)
    def record_poll(self): return self.repository.record_poll(self.worker_instance_id, at=self.now())
    def record_success(self, *, idle: bool = False): return self.repository.record_success(self.worker_instance_id, at=self.now(), idle=idle)
    def record_failure(self, error: Any): return self.repository.record_failure(self.worker_instance_id, at=self.now(), error=str(error or "unknown_failure")[:self.MAX_ERROR_LENGTH])
    def record_stopping(self): return self.repository.record_shutdown(self.worker_instance_id, at=self.now(), status=WorkerHeartbeatStatus.STOPPING)
    def record_shutdown(self): return self.repository.record_shutdown(self.worker_instance_id, at=self.now(), status=WorkerHeartbeatStatus.STOPPED)
    def get_current(self): return self.repository.get_by_instance(self.worker_instance_id)
    def list_latest(self, *, creator_profile_id: str | None = None, account_id: int | None = None): return self.repository.list_latest_per_worker(creator_profile_id=creator_profile_id, account_id=account_id)

    @staticmethod
    def classify(heartbeat: WorkerHeartbeat | None, *, stale_threshold_seconds: int, now: datetime | None = None) -> WorkerHealthClassification:
        if heartbeat is None: return WorkerHealthClassification.UNKNOWN
        if heartbeat.status == WorkerHeartbeatStatus.STOPPED: return WorkerHealthClassification.STOPPED
        if heartbeat.status == WorkerHeartbeatStatus.FAILED: return WorkerHealthClassification.FAILED
        current = now or datetime.now(timezone.utc)
        last = heartbeat.last_heartbeat_at.replace(tzinfo=timezone.utc) if heartbeat.last_heartbeat_at.tzinfo is None else heartbeat.last_heartbeat_at
        if (current - last).total_seconds() > max(1, stale_threshold_seconds): return WorkerHealthClassification.STALE
        if heartbeat.status == WorkerHeartbeatStatus.IDLE: return WorkerHealthClassification.IDLE
        if heartbeat.status == WorkerHeartbeatStatus.DEGRADED: return WorkerHealthClassification.FAILED
        if heartbeat.status in {WorkerHeartbeatStatus.STARTING, WorkerHeartbeatStatus.RUNNING}: return WorkerHealthClassification.HEALTHY
        return WorkerHealthClassification.UNKNOWN

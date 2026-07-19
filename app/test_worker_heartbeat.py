from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.models.worker_heartbeat import WorkerHealthClassification, WorkerHeartbeatStatus
from app.services.worker_heartbeat_service import WorkerHeartbeatService


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self): self.records = {}
    def register(self, item): self.records[item.worker_instance_id] = item; return item
    def _set(self, instance, **changes): self.records[instance] = replace(self.records[instance], **changes); return self.records[instance]
    def record_heartbeat(self, instance, *, status, at, metadata=None): return self._set(instance, status=status, last_heartbeat_at=at, metadata={**self.records[instance].metadata, **dict(metadata or {})})
    def record_poll(self, instance, *, at): return self._set(instance, status=WorkerHeartbeatStatus.RUNNING, last_poll_at=at, last_heartbeat_at=at)
    def record_success(self, instance, *, at, idle): return self._set(instance, status=WorkerHeartbeatStatus.IDLE if idle else WorkerHeartbeatStatus.RUNNING, last_success_at=at, last_heartbeat_at=at, last_error=None)
    def record_failure(self, instance, *, at, error): return self._set(instance, status=WorkerHeartbeatStatus.DEGRADED, last_failure_at=at, last_heartbeat_at=at, last_error=error)
    def record_shutdown(self, instance, *, at, status): return self._set(instance, status=status, last_heartbeat_at=at, shutdown_at=at if status == WorkerHeartbeatStatus.STOPPED else None)
    def get_by_instance(self, instance): return self.records.get(instance)
    def list_latest_per_worker(self, *, creator_profile_id=None, account_id=None):
        scoped = [item for item in self.records.values() if (item.creator_profile_id in {None, creator_profile_id}) and (item.account_id in {None, account_id})]
        latest = {}
        for item in scoped:
            if item.worker_name not in latest or item.last_heartbeat_at > latest[item.worker_name].last_heartbeat_at: latest[item.worker_name] = item
        return tuple(latest.values())


def build(repository, **kwargs):
    return WorkerHeartbeatService(worker_name="Delayed Messages", worker_type="queue_worker", poll_interval_seconds=15, worker_instance_id=kwargs.pop("worker_instance_id", "delayed-1"), repository=repository, now=lambda: kwargs.pop("now", NOW) if kwargs else NOW, **kwargs)


def test_migration_and_rollback_exist_and_define_required_schema():
    forward = Path("migrations/forward/20260719_001_worker_heartbeats.sql")
    rollback = Path("migrations/rollback/20260719_001_drop_worker_heartbeats.sql")
    assert forward.exists() and rollback.exists()
    sql = forward.read_text(encoding="utf-8")
    for field in ("worker_instance_id", "last_heartbeat_at", "last_poll_at", "last_success_at", "last_failure_at", "shutdown_at", "metadata JSONB"):
        assert field in sql
    assert "DROP TABLE IF EXISTS public.worker_heartbeats" in rollback.read_text(encoding="utf-8")


def test_full_heartbeat_lifecycle_and_bounded_failure():
    repo = MemoryRepository(); service = build(repo)
    startup = service.register_startup(); assert startup.status == WorkerHeartbeatStatus.STARTING
    assert service.stale_threshold_seconds == 60
    assert service.heartbeat().status == WorkerHeartbeatStatus.RUNNING
    assert service.record_poll().last_poll_at == NOW
    assert service.record_success(idle=True).status == WorkerHeartbeatStatus.IDLE
    failed = service.record_failure("x" * 1200); assert failed.status == WorkerHeartbeatStatus.DEGRADED and len(failed.last_error) == 1000
    assert service.record_stopping().status == WorkerHeartbeatStatus.STOPPING
    stopped = service.record_shutdown(); assert stopped.status == WorkerHeartbeatStatus.STOPPED and stopped.shutdown_at == NOW


def test_classification_requires_recent_heartbeat_and_honors_terminal_state():
    repo = MemoryRepository(); service = build(repo); heartbeat = service.register_startup()
    assert service.classify(heartbeat, stale_threshold_seconds=60, now=NOW) == WorkerHealthClassification.HEALTHY
    stale = replace(heartbeat, status=WorkerHeartbeatStatus.RUNNING, last_heartbeat_at=NOW - timedelta(seconds=61))
    assert service.classify(stale, stale_threshold_seconds=60, now=NOW) == WorkerHealthClassification.STALE
    assert service.classify(replace(heartbeat, status=WorkerHeartbeatStatus.STOPPED), stale_threshold_seconds=60, now=NOW) == WorkerHealthClassification.STOPPED
    assert service.classify(replace(heartbeat, status=WorkerHeartbeatStatus.FAILED), stale_threshold_seconds=60, now=NOW) == WorkerHealthClassification.FAILED
    assert service.classify(None, stale_threshold_seconds=60, now=NOW) == WorkerHealthClassification.UNKNOWN


def test_multiple_instances_latest_worker_and_account_isolation():
    repo = MemoryRepository()
    one = WorkerHeartbeatService(worker_name="Outreach", worker_type="worker", poll_interval_seconds=300, account_id=7, worker_instance_id="one", repository=repo, now=lambda: NOW - timedelta(minutes=2)); one.register_startup()
    two = WorkerHeartbeatService(worker_name="Outreach", worker_type="worker", poll_interval_seconds=300, account_id=7, worker_instance_id="two", repository=repo, now=lambda: NOW); two.register_startup()
    other = WorkerHeartbeatService(worker_name="Outreach", worker_type="worker", poll_interval_seconds=300, account_id=8, worker_instance_id="other", repository=repo, now=lambda: NOW + timedelta(minutes=1)); other.register_startup()
    latest = one.list_latest(account_id=7)
    assert len(repo.records) == 3 and len(latest) == 1 and latest[0].worker_instance_id == "two"

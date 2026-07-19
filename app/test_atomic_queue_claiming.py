from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


class Store:
    def __init__(self):
        self.lock = threading.Lock()
        self.rows = [{"id": 1, "status": "pending", "worker_instance_id": None,
                      "claimed_at": None, "lease_expires_at": None, "retry_count": 0}]


class Connection:
    def __init__(self, store): self.store = store
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.store)
    def commit(self): pass


class Cursor:
    def __init__(self, store): self.store = store; self.result = []
    def __enter__(self): return self
    def __exit__(self, *_): return False

    def execute(self, sql, params):
        now = datetime.now(timezone.utc)
        normalized = " ".join(sql.split())
        with self.store.lock:
            if "WITH candidates AS" in normalized:
                limit, owner, lease_seconds = params[-3:]
                available = [row for row in self.store.rows if row["status"] == "pending" or
                             (row["status"] == "processing" and row["lease_expires_at"] < now)][:limit]
                for row in available:
                    row.update(status="processing", worker_instance_id=owner, claimed_at=now,
                               lease_expires_at=now + timedelta(seconds=lease_seconds))
                self.result = [dict(row) for row in available]
            elif "WITH stale AS" in normalized:
                limit, pending = params
                stale = [row for row in self.store.rows if row["status"] == "processing" and
                         row["lease_expires_at"] < now][:limit]
                for row in stale:
                    row.update(status=pending, worker_instance_id=None, claimed_at=None, lease_expires_at=None)
                self.result = [dict(row) for row in stale]
            else:
                item_id, owner = params[-2:]
                row = next((item for item in self.store.rows if item["id"] == item_id and
                            item["status"] == "processing" and item["worker_instance_id"] == owner and
                            item["lease_expires_at"] >= now), None)
                if row and "status = %s" in normalized:
                    row.update(status=params[0], worker_instance_id=None, claimed_at=None, lease_expires_at=None)
                elif row and "lease_expires_at" in normalized:
                    row["lease_expires_at"] = now + timedelta(seconds=params[0])
                self.result = [dict(row)] if row else []

    def fetchall(self): return self.result
    def fetchone(self): return self.result[0] if self.result else None


@pytest.fixture
def queue():
    store = Store()
    repository = AtomicQueueClaimRepository(
        table="test_queue", status_column="status", pending_status="pending",
        completed_status="completed", eligible_predicate="status = 'pending'",
        order_by="id", connection_factory=lambda: Connection(store),
    )
    return store, repository


def test_two_workers_cannot_claim_or_execute_the_same_item(queue):
    _, repository = queue
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(
            lambda owner: repository.claim_due_items(worker_instance_id=owner, lease_seconds=60, limit=1),
            ("worker-a", "worker-b"),
        ))
    claimed = [row for result in results for row in result]
    assert len(claimed) == 1
    assert claimed[0]["worker_instance_id"] in {"worker-a", "worker-b"}


def test_stale_claim_recovers_but_active_lease_does_not(queue):
    store, repository = queue
    repository.claim_due_items(worker_instance_id="worker-a", lease_seconds=60, limit=1)
    assert repository.recover_stale_claims() == []
    store.rows[0]["lease_expires_at"] = datetime.now(timezone.utc) - timedelta(seconds=1)
    recovered = repository.recover_stale_claims()
    assert recovered[0]["status"] == "pending"
    reclaimed = repository.claim_due_items(worker_instance_id="worker-b", lease_seconds=60, limit=1)
    assert reclaimed[0]["worker_instance_id"] == "worker-b"


def test_completion_requires_owner_and_releases_ownership(queue):
    store, repository = queue
    repository.claim_due_items(worker_instance_id="worker-a", lease_seconds=60, limit=1)
    assert repository.complete_claim(1, worker_instance_id="worker-b") == {}
    completed = repository.complete_claim(1, worker_instance_id="worker-a")
    assert completed["status"] == "completed"
    assert completed["worker_instance_id"] is None
    assert store.rows[0]["lease_expires_at"] is None


def test_claim_sql_is_atomic_and_all_queue_repositories_expose_lease_contract():
    import inspect
    from app.repositories import atomic_queue_claim_repository as atomic
    from app.repositories import delayed_message_queue_repository, mass_ppv_campaign_repository
    from app.repositories import outreach_queue_repository, wall_post_repository, webhook_event_repository

    source = inspect.getsource(atomic.AtomicQueueClaimRepository.claim_due_items)
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "UPDATE {self.table}" in source
    assert "RETURNING queue.*" in source
    for module in (outreach_queue_repository, delayed_message_queue_repository,
                   mass_ppv_campaign_repository, wall_post_repository, webhook_event_repository):
        for method in ("claim_due_items", "renew_claim", "release_claim", "complete_claim", "fail_claim", "recover_stale_claims"):
            assert callable(getattr(module, method))


def test_failure_paths_preserve_existing_retry_policies():
    import inspect
    from app.repositories import delayed_message_queue_repository, mass_ppv_campaign_repository
    from app.repositories import outreach_queue_repository, wall_post_repository, webhook_event_repository

    assert "INTERVAL '15 minutes'" in inspect.getsource(outreach_queue_repository.fail_claim)
    assert "INTERVAL '15 minutes'" in inspect.getsource(wall_post_repository.fail_claim)
    assert "retry_count = retry_count + 1" in inspect.getsource(delayed_message_queue_repository.fail_claim)
    assert "retry_count = retry_count + 1" in inspect.getsource(mass_ppv_campaign_repository.fail_claim)
    assert "retry_delay_minutes: int = 5" in inspect.getsource(webhook_event_repository.fail_claim)


def test_workers_execute_only_owned_claims_and_no_longer_fetch_then_mark():
    import inspect
    from app.services.delayed_message_worker_service import DelayedMessageWorkerService
    from app.services.mass_ppv_worker_service import MassPPVWorkerService
    from app.services.outreach_worker_service import OutreachWorkerService
    from app.services.wall_worker_service import WallWorkerService
    from app.services.webhook_event_processor_service import WebhookEventProcessorService

    for worker in (OutreachWorkerService, DelayedMessageWorkerService, MassPPVWorkerService,
                   WallWorkerService, WebhookEventProcessorService):
        source = inspect.getsource(worker)
        assert "claim_due_items" in source
        assert "renew_claim" in source
        for legacy_transition in ("mark_outreach_processing", "mark_delayed_message_processing",
                                  "mark_mass_ppv_processing", "mark_wall_post_processing",
                                  "mark_webhook_event_processing"):
            assert legacy_transition not in source


def test_migration_adds_only_lease_columns_and_indexes_to_scoped_queues():
    from pathlib import Path

    sql = Path("migrations/forward/20260719_002_atomic_queue_claims.sql").read_text(encoding="utf-8")
    for table in ("outreach_queue", "delayed_message_queue", "mass_ppv_queue", "wall_post_queue", "webhook_events"):
        assert f"ALTER TABLE public.{table}" in sql
        assert f"idx_{table}_active_lease" in sql
    for column in ("worker_instance_id TEXT", "claimed_at TIMESTAMPTZ", "lease_expires_at TIMESTAMPTZ"):
        assert sql.count(column) == 5

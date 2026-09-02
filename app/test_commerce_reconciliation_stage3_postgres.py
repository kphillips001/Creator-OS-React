"""Continuous Commerce Reconciliation worker certification on isolated PostgreSQL."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.repositories.webhook_event_repository import claim_due_items, fail_claim
from app.services.webhook_event_processor_service import WebhookEventProcessorService
from app.services.commerce_signal_service import CommerceSignalService
from app.workers.commerce_reconciliation import CommerceReconciliationWorker
from app.test_private_chat_settlement_postgres import connection_factory, fixture


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required"
)


def _event(*, event_type="follow_new", status="received", retry_count=0):
    external = str(uuid4())
    with connection_factory() as connection:
        row = connection.execute("""INSERT INTO webhook_events(
            internal_event_id,external_event_id,event_type,fanvue_account_id,
            fanvue_user_id,status,payload,headers,received_at,retry_count,next_retry_at)
            VALUES (%s,%s,%s,'synthetic-account','synthetic-user',%s,'{}','{}',NOW(),%s,NOW())
            RETURNING id""", (uuid4(), external, event_type, status, retry_count)).fetchone()
    return row["id"], external


def test_two_webhook_workers_claim_disjoint_rows_and_stale_claim_recovers():
    with connection_factory() as connection:
        connection.execute("UPDATE webhook_events SET status='quarantined' WHERE status IN ('received','failed','processing')")
    ids = [_event()[0] for _ in range(4)]
    first = claim_due_items(worker_instance_id="stage3-a", limit=2, lease_seconds=60)
    second = claim_due_items(worker_instance_id="stage3-b", limit=2, lease_seconds=60)
    left, right = ({row["id"] for row in first}, {row["id"] for row in second})
    assert len(left) == len(right) == 2 and left.isdisjoint(right)
    with connection_factory() as connection:
        connection.execute("UPDATE webhook_events SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE id=%s", (ids[0],))
    reclaimed = claim_due_items(worker_instance_id="stage3-restart", limit=4)
    assert ids[0] in {row["id"] for row in reclaimed}


def test_poison_event_quarantines_finitely_and_does_not_block_healthy_event():
    with connection_factory() as connection:
        connection.execute("UPDATE webhook_events SET status='quarantined' WHERE status IN ('received','failed','processing')")
    poison, _ = _event(event_type="malformed", retry_count=7)
    healthy, _ = _event(event_type="follow_new")
    claimed = claim_due_items(worker_instance_id="stage3-poison", limit=1)
    assert claimed[0]["id"] == poison
    fail_claim(poison, worker_instance_id="stage3-poison", error_message="synthetic poison")
    next_claim = claim_due_items(worker_instance_id="stage3-healthy", limit=1)
    assert next_claim[0]["id"] == healthy
    with connection_factory() as connection:
        row = connection.execute("SELECT status,retry_count,next_retry_at,last_error FROM webhook_events WHERE id=%s", (poison,)).fetchone()
    assert row["status"] == "quarantined" and row["retry_count"] == 8
    assert row["next_retry_at"] is None and row["last_error"] == "synthetic poison"


@pytest.mark.parametrize("outcome,expected", (
    ("SUCCEEDED", "processed"), ("IGNORED", "ignored"),
    ("RETRYABLE", "failed"), ("TERMINAL_FAILED", "quarantined"),
    ("QUARANTINED", "quarantined"),
))
def test_routed_outcome_controls_persisted_webhook_status(outcome, expected):
    with connection_factory() as connection:
        connection.execute("UPDATE webhook_events SET status='quarantined' WHERE status IN ('received','failed','processing')")
    item_id, _ = _event()
    class Router:
        def route_event(self, _event):
            return {"outcome": outcome, "reason": "synthetic", "result": {"blocked": True}}
    WebhookEventProcessorService(router=Router(), worker_instance_id=f"stage3-{outcome}").process_pending_events(limit=1)
    with connection_factory() as connection:
        row = connection.execute("SELECT status FROM webhook_events WHERE id=%s", (item_id,)).fetchone()
    assert row["status"] == expected


def test_worker_empty_queue_heartbeats_and_stops_cleanly(monkeypatch):
    lifecycle, metadata = [], []
    heartbeat = SimpleNamespace(
        register_startup=lambda: lifecycle.append("startup"),
        record_poll=lambda: lifecycle.append("poll"),
        record_success=lambda: lifecycle.append("success"),
        heartbeat=lambda **values: metadata.append(values),
            record_failure=lambda error, **_values: lifecycle.append(f"failure:{type(error).__name__}"),
        record_stopping=lambda: lifecycle.append("stopping"),
        record_shutdown=lambda: lifecycle.append("shutdown"),
    )
    stop = __import__("threading").Event()
    worker = CommerceReconciliationWorker(
        processor=SimpleNamespace(process_pending_events=lambda: []),
        reconciliation_service=SimpleNamespace(retry_pending=lambda limit: []),
        intent_service=SimpleNamespace(expire_due=lambda: []), heartbeat=heartbeat,
        interval_seconds=5,
    )
    monkeypatch.setattr("app.workers.commerce_reconciliation.recover_stale_claims", lambda limit: [])
    original = worker.run_once
    worker.run_once = lambda: (stop.set() or original())
    worker.run(stop)
    assert lifecycle == ["startup", "poll", "success", "stopping", "shutdown"]
    assert metadata[0]["idle"] is True
    assert metadata[0]["metadata"]["webhook_result_count"] == 0


def test_transient_database_failure_backs_off_and_recovers(monkeypatch):
    lifecycle, waits, attempts = [], [], []
    class Stop:
        stopped = False
        def is_set(self): return self.stopped
        def set(self): self.stopped = True
        def wait(self, seconds): waits.append(seconds)
    stop = Stop()
    class Processor:
        def process_pending_events(self):
            attempts.append("poll")
            if len(attempts) == 1:
                raise ConnectionError("synthetic database outage")
            stop.set()
            return []
    heartbeat = SimpleNamespace(
        register_startup=lambda: lifecycle.append("startup"),
        record_poll=lambda: lifecycle.append("poll"),
        record_success=lambda: lifecycle.append("success"),
        heartbeat=lambda **_values: lifecycle.append("heartbeat"),
        record_failure=lambda error, **_values: lifecycle.append(f"failure:{type(error).__name__}"),
        record_stopping=lambda: lifecycle.append("stopping"),
        record_shutdown=lambda: lifecycle.append("shutdown"),
    )
    worker = CommerceReconciliationWorker(processor=Processor(),
        reconciliation_service=SimpleNamespace(retry_pending=lambda limit: []),
        intent_service=SimpleNamespace(expire_due=lambda: []), heartbeat=heartbeat,
        interval_seconds=5)
    monkeypatch.setattr("app.workers.commerce_reconciliation.recover_stale_claims", lambda limit: [])
    worker.run(stop)
    assert attempts == ["poll", "poll"] and waits == [5, 5]
    assert "failure:ConnectionError" in lifecycle
    assert lifecycle[-4:] == ["success", "heartbeat", "stopping", "shutdown"]


def test_live_new_purchaser_full_chain_converges_once(monkeypatch):
    values = fixture(session=True, offering_type="PHOTOSET")
    creator_uuid, transaction = uuid4(), f"stage3-live-{uuid4()}"
    with connection_factory() as connection:
        connection.execute("UPDATE fanvue_accounts SET fanvue_creator_uuid=%s WHERE id=%s",
                           (creator_uuid, values["account"]))
        connection.execute("DELETE FROM fanvue_users WHERE id=%s", (values["user"],))
    purchased_at = datetime.now(timezone.utc)
    class Provider:
        def get_earnings_by_transaction(self, requested):
            assert requested == transaction
            return {"data": [{"transactionOrderId": transaction, "gross": 1497,
                "net": 1200, "currency": "USD", "date": purchased_at.isoformat(),
                "source": "media_link", "status": "paid",
                "mediaLinkUuid": "canonical"}]}
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    service = CommerceSignalService(client_factory=lambda _account: Provider())
    payload = {"eventId": str(uuid4()), "recipientUuid": str(creator_uuid),
        "sender": {"uuid": str(values["buyer_uuid"])}, "price": 1497,
        "purchaseType": "media", "transactionOrderId": transaction,
        "transactionOrderStatus": "paid", "mediaLinkUuid": "canonical"}
    event = {"event_type": "purchase_new", "external_event_id": payload["eventId"],
             "fanvue_account_id": str(values["account"]), "payload": payload}
    first = service.process_webhook(event)
    second = service.process_webhook(event)
    assert first["success"] is True and first["state"] == "VERIFIED"
    assert second == {"success": True, "duplicate": True, "state": "VERIFIED"}
    with connection_factory() as connection:
        counts = {
            "users": connection.execute("SELECT count(*) n FROM fanvue_users WHERE fanvue_account_id=%s AND fanvue_user_uuid=%s", (values["account"], values["buyer_uuid"])).fetchone()["n"],
            "mappings": connection.execute("SELECT count(*) n FROM telegram_identity_map WHERE telegram_user_id=%s", (values["telegram"],)).fetchone()["n"],
            "transactions": connection.execute("SELECT count(*) n FROM customer_commerce_transactions WHERE transaction_order_id=%s", (transaction,)).fetchone()["n"],
            "reconciliations": connection.execute("SELECT count(*) n FROM commerce_signal_reconciliations WHERE canonical_transaction_order_id=%s", (transaction,)).fetchone()["n"],
            "ownership": connection.execute("SELECT count(*) n FROM provider_purchase_asset_ownership WHERE provider_transaction_id=%s", (transaction,)).fetchone()["n"],
            "sessions": connection.execute("SELECT count(*) n FROM sales_sessions WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s", (values["account"], values["buyer_uuid"])).fetchone()["n"],
        }
        intent = connection.execute("SELECT status,purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()
        provisional = connection.execute("SELECT state,current_position FROM telegram_provisional_sales_sessions WHERE provisional_session_id=%s", (values["provisional_id"],)).fetchone()
    assert counts == {"users": 1, "mappings": 1, "transactions": 1,
                      "reconciliations": 1, "ownership": 1, "sessions": 1}
    assert intent == {"status": "PURCHASED", "purchase_acknowledged_at": None}
    assert provisional == {"state": "GRADUATED", "current_position": 2}


@pytest.mark.skipif(os.name != "nt", reason="Windows signal certification")
def test_production_module_entrypoint_starts_and_handles_ctrl_break_cleanly():
    env = os.environ.copy()
    env["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    env["COMMERCE_RECONCILIATION_INTERVAL_SECONDS"] = "5"
    env.pop("CREATOR_OS_LAUNCH_COMMERCE_RECONCILIATION", None)
    process = subprocess.Popen(
        [sys.executable, "-m", "app.workers.commerce_reconciliation"],
        cwd=os.getcwd(), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    try:
        deadline = time.time() + 15
        row = None
        while time.time() < deadline and process.poll() is None:
            with connection_factory() as connection:
                row = connection.execute("""SELECT worker_instance_id,status FROM worker_heartbeats
                    WHERE worker_name='Commerce Reconciliation' AND process_id=%s
                    ORDER BY started_at DESC LIMIT 1""", (process.pid,)).fetchone()
            if row is not None:
                break
            time.sleep(.2)
        assert process.poll() is None and row is not None
        process.send_signal(signal.CTRL_BREAK_EVENT)
        assert process.wait(timeout=15) == 0
        with connection_factory() as connection:
            stopped = connection.execute("SELECT status FROM worker_heartbeats WHERE worker_instance_id=%s", (row["worker_instance_id"],)).fetchone()
        assert stopped["status"] == "STOPPED"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

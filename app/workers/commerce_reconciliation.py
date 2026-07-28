"""Launcher-managed durable Commerce reconciliation and expiration worker."""
from __future__ import annotations

import logging
import os
import signal
import threading
from datetime import datetime, timezone

from app.repositories.webhook_event_repository import recover_stale_claims
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.webhook_event_processor_service import (
    WebhookEventProcessorService,
)
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


logger = logging.getLogger("commerce-reconciliation-worker")


class CommerceReconciliationWorker:
    def __init__(
        self, *, processor=None, intent_service=None, heartbeat=None,
        interval_seconds: int = 30,
    ):
        self.processor = processor or WebhookEventProcessorService()
        self.intents = intent_service or PurchaseIntentService()
        self.heartbeat = heartbeat or WorkerHeartbeatService(
            worker_name="Commerce Reconciliation",
            worker_type="commerce_reconciliation",
            poll_interval_seconds=interval_seconds,
        )
        self.interval_seconds = max(5, int(interval_seconds))
        self.last_success = None
        self.last_failure = None
        self.retry_count = 0

    def run_once(self):
        recovered = recover_stale_claims(limit=100)
        results = self.processor.process_pending_events()
        expired = self.intents.expire_due()
        self.last_success = datetime.now(timezone.utc)
        self.last_failure = None
        next_reconciliation = datetime.fromtimestamp(
            self.last_success.timestamp() + self.interval_seconds,
            tz=timezone.utc,
        )
        diagnostics = {
            "next_reconciliation": next_reconciliation.isoformat(),
            "pending_count": sum(
                isinstance(item, dict)
                and isinstance(item.get("result"), dict)
                and item["result"].get("state") == "PENDING"
                for item in results
            ),
            "retry_count": self.retry_count,
            "last_success": self.last_success.isoformat(),
            "last_failure": None,
            "recovered_count": len(recovered),
            "expired_intent_count": len(expired),
        }
        logger.info("event=commerce_reconciliation_completed diagnostics=%s",
                    diagnostics)
        return diagnostics

    def run(self, stop_event=None):
        stop_event = stop_event or threading.Event()
        record_heartbeat_safely(logger, "startup", self.heartbeat.register_startup)
        try:
            while not stop_event.is_set():
                try:
                    self.run_once()
                    record_heartbeat_safely(
                        logger, "success", self.heartbeat.record_success
                    )
                except Exception as error:
                    self.retry_count += 1
                    self.last_failure = datetime.now(timezone.utc)
                    logger.exception(
                        "event=commerce_reconciliation_failed error_type=%s "
                        "retry_count=%s",
                        type(error).__name__, self.retry_count,
                    )
                    record_heartbeat_safely(
                        logger, "failure",
                        lambda: self.heartbeat.record_failure(error),
                    )
                stop_event.wait(self.interval_seconds)
        finally:
            record_heartbeat_safely(
                logger, "stopping", self.heartbeat.record_stopping
            )
            record_heartbeat_safely(
                logger, "shutdown", self.heartbeat.record_shutdown
            )


def _install_shutdown_handlers(stop_event):
    def request_shutdown(_signum, _frame):
        stop_event.set()

    for signal_name in ("SIGINT", "SIGTERM"):
        shutdown_signal = getattr(signal, signal_name, None)
        if shutdown_signal is not None:
            signal.signal(shutdown_signal, request_shutdown)


def main():
    logging.basicConfig(level=logging.INFO)
    stop_event = threading.Event()
    _install_shutdown_handlers(stop_event)
    CommerceReconciliationWorker(
        interval_seconds=int(
            os.getenv("COMMERCE_RECONCILIATION_INTERVAL_SECONDS", "30")
        )
    ).run(stop_event)


if __name__ == "__main__":
    main()

"""Standalone supervised deterministic Content Intelligence merge worker."""

import logging
import time

from app.services.content_intelligence_merge_worker_service import ContentIntelligenceMergeWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run(*, worker=None, heartbeat=None, max_cycles: int | None = None,
        poll_seconds: int = 5) -> None:
    logger = logging.getLogger("content-intelligence-merge-worker")
    heartbeat = heartbeat or WorkerHeartbeatService(
        worker_name="Content Intelligence Merge", worker_type="analysis_worker",
        poll_interval_seconds=poll_seconds,
    )
    worker = worker or ContentIntelligenceMergeWorkerService(
        worker_instance_id=heartbeat.worker_instance_id
    )
    record_heartbeat_safely(logger, "startup", heartbeat.register_startup)
    cycles = 0
    try:
        while True:
            cycles += 1
            record_heartbeat_safely(logger, "poll", heartbeat.record_poll)
            try:
                result = worker.process_one()
                record_heartbeat_safely(logger, "success", lambda: heartbeat.record_success(idle=not result["processed"]))
            except Exception as error:
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
                logger.exception("Content Intelligence merge cycle failed")
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(poll_seconds)
    finally:
        record_heartbeat_safely(logger, "stopping", heartbeat.record_stopping)
        record_heartbeat_safely(logger, "shutdown", heartbeat.record_shutdown)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__":
    main()

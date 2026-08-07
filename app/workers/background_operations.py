"""Supervised application-wide Background Operations worker."""
import logging
import time

from app.services.background_operation_worker_service import BackgroundOperationWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run(*, worker=None, heartbeat=None, max_cycles=None, poll_seconds=1):
    logger = logging.getLogger("background-operations-worker")
    heartbeat = heartbeat or WorkerHeartbeatService(
        worker_name="Background Operations", worker_type="queue_worker",
        poll_interval_seconds=poll_seconds)
    worker = worker or BackgroundOperationWorkerService(
        worker_instance_id=heartbeat.worker_instance_id)
    record_heartbeat_safely(logger, "startup", heartbeat.register_startup)
    cycles = 0
    try:
        while True:
            cycles += 1
            record_heartbeat_safely(logger, "poll", heartbeat.record_poll)
            try:
                result = worker.process_one()
                record_heartbeat_safely(
                    logger, "success", lambda: heartbeat.record_success(idle=not result["processed"]))
            except Exception as error:
                logger.exception("Background Operations cycle failed")
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(poll_seconds)
    finally:
        record_heartbeat_safely(logger, "stopping", heartbeat.record_stopping)
        record_heartbeat_safely(logger, "shutdown", heartbeat.record_shutdown)


def main():
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__":
    main()

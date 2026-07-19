import logging
import time

from app.services.outreach_worker_service import OutreachWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run(*, worker=None, heartbeat=None, max_cycles: int | None = None) -> None:
    logger = logging.getLogger("outreach-queue-worker")
    heartbeat = heartbeat or WorkerHeartbeatService(
        worker_name="Outreach", worker_type="queue_worker", poll_interval_seconds=300,
    )
    worker = worker or OutreachWorkerService(worker_instance_id=heartbeat.worker_instance_id)
    record_heartbeat_safely(logger, "startup", heartbeat.register_startup)
    cycles = 0
    try:
        while True:
            cycles += 1
            record_heartbeat_safely(logger, "poll", heartbeat.record_poll)
            try:
                result = worker.process_outreach_queue(limit=25)
                count = int(result.get("processed_count") or 0) + int(result.get("failed_count") or 0)
                record_heartbeat_safely(logger, "success", lambda: heartbeat.record_success(idle=count == 0))
            except Exception as error:
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
                logger.exception("Outreach queue cycle failed")
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(300)
    finally:
        record_heartbeat_safely(logger, "stopping", heartbeat.record_stopping)
        record_heartbeat_safely(logger, "shutdown", heartbeat.record_shutdown)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__":
    main()

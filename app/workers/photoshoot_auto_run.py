"""Supervised durable Photoshoot Auto Generation worker."""

import logging
import time

from app.services.photoshoot_auto_run_worker_service import PhotoshootAutoRunWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run(*, worker=None, heartbeat=None, max_cycles=None, poll_seconds=2):
    logger = logging.getLogger("photoshoot-auto-run-worker")
    heartbeat = heartbeat or WorkerHeartbeatService(
        worker_name="Photoshoot Auto Run", worker_type="queue_worker", poll_interval_seconds=poll_seconds)
    worker = worker or PhotoshootAutoRunWorkerService(worker_instance_id=heartbeat.worker_instance_id)
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
                logger.exception("Photoshoot auto-run cycle failed")
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
            if max_cycles is not None and cycles >= max_cycles: break
            time.sleep(poll_seconds)
    finally:
        record_heartbeat_safely(logger, "stopping", heartbeat.record_stopping)
        record_heartbeat_safely(logger, "shutdown", heartbeat.record_shutdown)


def main():
    logging.basicConfig(level=logging.INFO)
    run()


if __name__ == "__main__": main()

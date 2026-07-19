import logging
import time

from app.services.wall_worker_service import WallWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


class WallWorkerLoopService:
    def __init__(self, poll_interval_seconds: int = 60, heartbeat_service=None, worker_service=None):
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_service = worker_service or WallWorkerService()
        self.logger = logging.getLogger(__name__)
        self.heartbeat = heartbeat_service or WorkerHeartbeatService(
            worker_name="Wall Worker", worker_type="queue_worker", poll_interval_seconds=poll_interval_seconds,
        )
        if getattr(self.heartbeat, "worker_instance_id", None):
            self.worker_service.worker_instance_id = self.heartbeat.worker_instance_id

    def run_once(self, limit: int = 10) -> dict:
        return self.worker_service.process_wall_queue(limit=limit)

    def run_forever(self, limit: int = 10, *, max_cycles: int | None = None):
        print("\n=== WALL WORKER LOOP STARTED ===\n")
        record_heartbeat_safely(self.logger, "startup", self.heartbeat.register_startup)
        failed = False
        cycle = 0
        try:
            while True:
                cycle += 1
                record_heartbeat_safely(self.logger, "poll", self.heartbeat.record_poll)
                try:
                    result = self.run_once(limit=limit)
                except Exception as error:
                    failed = True
                    record_heartbeat_safely(self.logger, "failure", lambda: self.heartbeat.record_failure(error))
                    raise
                record_heartbeat_safely(self.logger, "success", lambda: self.heartbeat.record_success(idle=int(result.get("processed_count") or 0) == 0))
                print("[WALL WORKER LOOP RESULT]", result)
                if max_cycles is not None and cycle >= max_cycles:
                    break
                time.sleep(self.poll_interval_seconds)
        finally:
            if not failed:
                record_heartbeat_safely(self.logger, "stopping", self.heartbeat.record_stopping)
                record_heartbeat_safely(self.logger, "shutdown", self.heartbeat.record_shutdown)

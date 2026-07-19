import logging
import time
import traceback

from app.services.delayed_message_worker_service import DelayedMessageWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


class DelayedMessageWorkerLoopService:
    def __init__(self, poll_interval_seconds: int = 15, heartbeat_service=None, worker_service=None):
        self.logger = logging.getLogger(__name__)
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_service = worker_service or DelayedMessageWorkerService()
        self.heartbeat = heartbeat_service or WorkerHeartbeatService(
            worker_name="Delayed Messages", worker_type="queue_worker",
            poll_interval_seconds=poll_interval_seconds,
        )
        if getattr(self.heartbeat, "worker_instance_id", None):
            self.worker_service.worker_instance_id = self.heartbeat.worker_instance_id

    def start_loop(self, *, max_cycles: int | None = None):
        self.logger.info("[DELAYED WORKER LOOP] Starting delayed worker loop...")
        record_heartbeat_safely(self.logger, "startup", self.heartbeat.register_startup)
        cycle = 0
        try:
            while True:
                cycle += 1
                try:
                    record_heartbeat_safely(self.logger, "poll", self.heartbeat.record_poll)
                    results = self.worker_service.process_due_messages()
                    record_heartbeat_safely(self.logger, "success", lambda: self.heartbeat.record_success(idle=not bool(results)))
                    if results:
                        self.logger.info("[DELAYED WORKER LOOP] processed=%s", len(results))
                        for result in results: self.logger.info("[DELAYED RESULT] %s", result)
                    else:
                        self.logger.info("[DELAYED WORKER LOOP] No due delayed messages")
                except Exception as error:
                    record_heartbeat_safely(self.logger, "failure", lambda: self.heartbeat.record_failure(error))
                    self.logger.error("[DELAYED WORKER LOOP ERROR] %s", error)
                    traceback.print_exc()
                if max_cycles is not None and cycle >= max_cycles:
                    break
                time.sleep(self.poll_interval_seconds)
        finally:
            record_heartbeat_safely(self.logger, "stopping", self.heartbeat.record_stopping)
            record_heartbeat_safely(self.logger, "shutdown", self.heartbeat.record_shutdown)

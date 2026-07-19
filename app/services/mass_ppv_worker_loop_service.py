import logging
import time

from app.services.mass_ppv_worker_service import MassPPVWorkerService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


class MassPPVWorkerLoopService:
    def __init__(self, *, worker_service=None, heartbeat_service=None):
        self.worker_service = worker_service or MassPPVWorkerService()
        self.logger = logging.getLogger(__name__)
        self.heartbeat = heartbeat_service or WorkerHeartbeatService(
            worker_name="Mass PPV", worker_type="queue_worker", poll_interval_seconds=30,
        )
        if getattr(self.heartbeat, "worker_instance_id", None):
            self.worker_service.worker_instance_id = self.heartbeat.worker_instance_id

    def run_once(self, limit: int = 25):
        print("\n[MASS PPV WORKER LOOP] run_once starting")
        results = self.worker_service.process_all_available_queue(pending_limit=limit, retry_limit=5)
        print("[MASS PPV WORKER LOOP] run_once complete processed=%s" % len(results))
        return {"success": True, "mode": "once", "processed_count": len(results), "results": results}

    def run_loop(self, limit: int = 25, sleep_seconds: int = 30, max_cycles: int | None = None):
        print("\n[MASS PPV WORKER LOOP START]")
        cycle = 0; all_results = []
        record_heartbeat_safely(self.logger, "startup", self.heartbeat.register_startup)
        failed = False
        try:
            while True:
                cycle += 1
                print(f"\n[MASS PPV WORKER LOOP CYCLE] cycle={cycle}")
                record_heartbeat_safely(self.logger, "poll", self.heartbeat.record_poll)
                try:
                    result = self.run_once(limit=limit)
                except Exception as error:
                    failed = True
                    record_heartbeat_safely(self.logger, "failure", lambda: self.heartbeat.record_failure(error))
                    raise
                all_results.append(result)
                cycle_result = result.get("results") or {}
                work_count = (int(cycle_result.get("pending_processed") or 0) + int(cycle_result.get("retry_processed") or 0)) if isinstance(cycle_result, dict) else int(result.get("processed_count") or 0)
                record_heartbeat_safely(self.logger, "success", lambda: self.heartbeat.record_success(idle=work_count == 0))
                if max_cycles is not None and cycle >= max_cycles:
                    print(f"\n[MASS PPV WORKER LOOP STOP] max_cycles={max_cycles}")
                    break
                print(f"[MASS PPV WORKER LOOP SLEEP] seconds={sleep_seconds}")
                time.sleep(sleep_seconds)
        finally:
            if not failed:
                record_heartbeat_safely(self.logger, "stopping", self.heartbeat.record_stopping)
                record_heartbeat_safely(self.logger, "shutdown", self.heartbeat.record_shutdown)
        return {"success": True, "mode": "loop", "cycles": cycle, "results": all_results}

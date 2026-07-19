import logging
import time

from app.services.outreach_runner import OutreachRunner
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run_outreach_worker(*, runner=None, heartbeat_service=None, max_cycles=None):
    runner = runner or OutreachRunner(); logger = logging.getLogger(__name__)
    heartbeat = heartbeat_service or WorkerHeartbeatService(
        worker_name="Outreach", worker_type="scheduled_worker", account_id=2, poll_interval_seconds=300,
    )
    print("[OUTREACH WORKER] Started.")
    record_heartbeat_safely(logger, "startup", heartbeat.register_startup)
    cycle = 0
    try:
        while True:
            cycle += 1
            record_heartbeat_safely(logger, "poll", heartbeat.record_poll)
            try:
                print("\n[OUTREACH WORKER] Running outreach cycle...\n")
                results = runner.run_outreach_cycle(fanvue_account_id=2, limit=10, dry_run=False)
                print(f"[OUTREACH WORKER] Done. Candidates={results['candidate_count']} | Eligible={results['eligible_count']} | Processed={results['processed_count']}")
                record_heartbeat_safely(logger, "success", lambda: heartbeat.record_success(idle=not bool(results.get("processed_count"))))
            except Exception as error:
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
                print(f"[OUTREACH WORKER] Error: {error}")
            if max_cycles is not None and cycle >= max_cycles: break
            print("[OUTREACH WORKER] Sleeping for 300 seconds...\n"); time.sleep(300)
    finally:
        record_heartbeat_safely(logger, "stopping", heartbeat.record_stopping)
        record_heartbeat_safely(logger, "shutdown", heartbeat.record_shutdown)


if __name__ == "__main__": run_outreach_worker()

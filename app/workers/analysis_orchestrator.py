"""Durable polling loop for Business Asset analysis workflow advancement."""

import logging
import time

from app.services.business_asset_analysis_orchestrator import BusinessAssetAnalysisOrchestrator
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService


def run(*, orchestrator=None, heartbeat=None, max_cycles: int | None = None,
        poll_seconds: int = 5) -> None:
    logger = logging.getLogger("analysis-orchestrator")
    heartbeat = heartbeat or WorkerHeartbeatService(
        worker_name="Analysis Orchestrator", worker_type="workflow_orchestrator",
        poll_interval_seconds=poll_seconds,
    )
    orchestrator = orchestrator or BusinessAssetAnalysisOrchestrator()
    record_heartbeat_safely(logger, "startup", heartbeat.register_startup)
    cycles = 0
    try:
        while True:
            cycles += 1
            record_heartbeat_safely(logger, "poll", heartbeat.record_poll)
            try:
                decision = orchestrator.orchestrate_next()
                record_heartbeat_safely(logger, "success", lambda: heartbeat.record_success(idle=decision is None))
            except Exception as error:
                record_heartbeat_safely(logger, "failure", lambda: heartbeat.record_failure(error))
                logger.exception("Analysis orchestration cycle failed")
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

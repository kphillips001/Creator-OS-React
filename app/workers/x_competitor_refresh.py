from __future__ import annotations

import logging, os, time
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.x_competitor_refresh_scheduler_service import XCompetitorRefreshSchedulerService

logger=logging.getLogger(__name__)

def main():
    poll=max(300,int(os.getenv("X_COMPETITOR_REFRESH_POLL_SECONDS","3600")))
    batch=max(1,int(os.getenv("X_COMPETITOR_REFRESH_BATCH_SIZE","10")))
    heartbeat=WorkerHeartbeatService(worker_name="X Competitor Refresh",worker_type="scheduler",poll_interval_seconds=poll)
    record_heartbeat_safely(logger,"startup",heartbeat.register_startup)
    try:
        while True:
            try:
                result=XCompetitorRefreshSchedulerService().run_once(limit=batch)
                record_heartbeat_safely(logger,"idle",lambda:heartbeat.heartbeat(idle=True,metadata={"last_considered":result["considered"]}))
            except Exception as error:
                logger.exception("X competitor rolling refresh pass failed")
                record_heartbeat_safely(logger,"error",lambda:heartbeat.record_failure(error))
            time.sleep(poll)
    finally:record_heartbeat_safely(logger,"stopped",heartbeat.record_shutdown)

if __name__=="__main__":main()

from __future__ import annotations

import logging, os, time
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.x_competitor_refresh_policy import XCompetitorRefreshPolicy
from app.services.x_competitor_refresh_scheduler_service import XCompetitorRefreshSchedulerService

logger=logging.getLogger(__name__)

def main():
    cadence=int(XCompetitorRefreshPolicy.INTERVAL.total_seconds())
    batch=max(1,int(os.getenv("X_COMPETITOR_REFRESH_BATCH_SIZE","10")))
    heartbeat=WorkerHeartbeatService(worker_name="X Competitor Refresh",worker_type="scheduler",poll_interval_seconds=cadence)
    record_heartbeat_safely(logger,"startup",heartbeat.register_startup)
    try:
        while True:
            try:
                result=XCompetitorRefreshSchedulerService().run_weekly_cycle(limit=batch,between_batches=time.sleep)
                record_heartbeat_safely(logger,"idle",lambda:heartbeat.heartbeat(idle=True,metadata={
                    "last_considered":result["considered"],"last_batches":result["batches"],
                    "cadence_seconds":cadence}))
            except Exception as error:
                logger.exception("X competitor weekly refresh cycle failed")
                record_heartbeat_safely(logger,"error",lambda:heartbeat.record_failure(error))
            time.sleep(cadence)
    finally:record_heartbeat_safely(logger,"stopped",heartbeat.record_shutdown)

if __name__=="__main__":main()

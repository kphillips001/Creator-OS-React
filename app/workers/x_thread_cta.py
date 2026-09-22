"""Supervised durable X CTA delivery worker."""
import logging,time
from app.services.x_thread_cta_queue_service import XThreadCtaQueueService
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
def run(*,service=None,heartbeat=None,max_cycles=None,poll_seconds=5):
    logger=logging.getLogger("x-thread-cta-worker"); heartbeat=heartbeat or WorkerHeartbeatService(worker_name="X Thread CTA",worker_type="queue_worker",poll_interval_seconds=poll_seconds); service=service or XThreadCtaQueueService(); record_heartbeat_safely(logger,"startup",heartbeat.register_startup); cycles=0
    try:
        while True:
            cycles+=1; record_heartbeat_safely(logger,"poll",heartbeat.record_poll)
            try:
                result=service.process_one(heartbeat.worker_instance_id); record_heartbeat_safely(logger,"success",lambda: heartbeat.record_success(idle=result is None))
            except Exception as error:
                logger.exception("X Thread CTA delivery entered SEND_UNCERTAIN"); record_heartbeat_safely(logger,"failure",lambda: heartbeat.record_failure(error))
            if max_cycles is not None and cycles>=max_cycles: break
            time.sleep(poll_seconds)
    finally: record_heartbeat_safely(logger,"stopping",heartbeat.record_stopping); record_heartbeat_safely(logger,"shutdown",heartbeat.record_shutdown)
if __name__=="__main__": logging.basicConfig(level=logging.INFO); run()

"""Lease-based dispatcher for durable Background Operations."""
from __future__ import annotations

from app.services.background_operation_service import BackgroundOperationService
from app.services.content_studio_background_executor import ContentStudioBackgroundExecutor
from app.services.content_studio_autonomous_background_executor import ContentStudioAutonomousBackgroundExecutor
from app.services.explicit_inspiration_background_executor import ExplicitInspirationBackgroundExecutor
from app.services.photoshoot_background_executor import PhotoshootBackgroundExecutor
from app.services.photoshoot_session_strategy_background_executor import PhotoshootSessionStrategyBackgroundExecutor
from app.services.video_studio_background_executor import VideoStudioBackgroundExecutor
from app.services.regeneration_background_executor import RegenerationBackgroundExecutor


class BackgroundOperationWorkerService:
    def __init__(self, *, worker_instance_id: str, operations=None, executors=None) -> None:
        self.worker_id = worker_instance_id
        self.operations = operations or BackgroundOperationService()
        generation = ContentStudioBackgroundExecutor()
        autonomous = ContentStudioAutonomousBackgroundExecutor()
        photoshoot = PhotoshootBackgroundExecutor()
        video = VideoStudioBackgroundExecutor()
        explicit_inspiration = ExplicitInspirationBackgroundExecutor()
        session_strategy = PhotoshootSessionStrategyBackgroundExecutor()
        regeneration = RegenerationBackgroundExecutor()
        self.executors = dict(executors or {
            generation.executor_key: generation,
            autonomous.executor_key: autonomous,
            photoshoot.executor_key: photoshoot,
            video.executor_key: video,
            explicit_inspiration.executor_key: explicit_inspiration,
            session_strategy.executor_key: session_strategy,
            regeneration.executor_key: regeneration,
        })

    def process_one(self) -> dict:
        operation = self.operations.repository.claim_next(self.worker_id, lease_seconds=120)
        if operation is None:
            return {"processed": False, "status": "IDLE"}
        if operation.status == "CANCEL_REQUESTED":
            self.operations.cancel(operation.operation_id, "Cancelled before execution")
            return {"processed": True, "status": "CANCELLED", "operation_id": str(operation.operation_id)}
        executor = self.executors.get(operation.executor_key)
        if executor is None:
            self.operations.fail(operation.operation_id,
                                 f"No executor is registered for {operation.executor_key}.",
                                 code="EXECUTOR_NOT_FOUND")
            return {"processed": True, "status": "FAILED", "operation_id": str(operation.operation_id)}
        try:
            executor.execute(operation, self.operations, worker_id=self.worker_id)
        except Exception as error:
            self.operations.fail(operation.operation_id, error)
        current = self.operations.repository._one_unscoped(operation.operation_id)
        return {"processed": True, "status": current.status,
                "operation_id": str(operation.operation_id)}

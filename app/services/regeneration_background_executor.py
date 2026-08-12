"""Background Operations adapter for durable regeneration replay."""
from app.services.regeneration_service import RegenerationService


class RegenerationBackgroundExecutor:
    executor_key = "regeneration"

    def __init__(self, service=None):
        self.service = service or RegenerationService()

    def execute(self, operation, operations, *, worker_id: str):
        try:
            self.service.execute(operation, operations, worker_id=worker_id)
        except Exception:
            run = self.service.repository.get_run(operation.operation_id)
            if run is not None and run.status not in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}:
                self.service.repository.update_run_status(operation.operation_id, "FAILED")
            raise

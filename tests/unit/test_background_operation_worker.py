from types import SimpleNamespace
from uuid import uuid4

from app.services.background_operation_worker_service import BackgroundOperationWorkerService


class Repository:
    def __init__(self, operation): self.operation = operation; self.claims = 0
    def claim_next(self, worker_id, *, lease_seconds):
        self.claims += 1
        value, self.operation = self.operation, None
        return value
    def _one_unscoped(self, operation_id): return SimpleNamespace(status="SUCCEEDED")


class Operations:
    def __init__(self, operation): self.repository = Repository(operation); self.failures = []
    def fail(self, operation_id, error, **kwargs): self.failures.append((operation_id, str(error), kwargs))
    def cancel(self, operation_id, message): pass


class Executor:
    def __init__(self): self.calls = []
    def execute(self, operation, operations, *, worker_id): self.calls.append((operation, worker_id))


def operation(executor_key="content_studio_generation"):
    return SimpleNamespace(operation_id=uuid4(), executor_key=executor_key, status="RUNNING")


def test_worker_claims_and_dispatches_operation_once():
    item, executor = operation(), Executor()
    operations = Operations(item)
    worker = BackgroundOperationWorkerService(
        worker_instance_id="worker-1", operations=operations,
        executors={"content_studio_generation": executor})
    assert worker.process_one()["processed"] is True
    assert worker.process_one() == {"processed": False, "status": "IDLE"}
    assert len(executor.calls) == 1


def test_unknown_executor_fails_without_dispatch():
    item = operation("unknown")
    operations = Operations(item)
    result = BackgroundOperationWorkerService(
        worker_instance_id="worker-1", operations=operations, executors={}).process_one()
    assert result["status"] == "FAILED"
    assert operations.failures[0][2]["code"] == "EXECUTOR_NOT_FOUND"

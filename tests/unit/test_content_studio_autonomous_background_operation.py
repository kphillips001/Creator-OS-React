import asyncio
import inspect
from types import SimpleNamespace
from uuid import uuid4

from app.api import content_studio
from app.services.content_studio_autonomous_background_executor import (
    ContentStudioAutonomousBackgroundExecutor,
)
from app.services.background_operation_worker_service import BackgroundOperationWorkerService


class Operations:
    def __init__(self):
        self.progress_values = []
        self.succeeded = []
        self.failed = []
        self.repository = SimpleNamespace(renew_lease=lambda *args, **kwargs: True)
    def progress(self, operation_id, **values): self.progress_values.append(values)
    def succeed(self, operation_id, **values): self.succeeded.append(values)
    def fail(self, operation_id, error, **values): self.failed.append((str(error), values))


def operation(**overrides):
    values = dict(
        operation_id=uuid4(), operation_type="content_studio_autonomous_inspiration",
        executor_key="content_studio_autonomous_inspiration", account_id=3,
        attempt_count=1, result_reference=None, progress_total=6,
        metadata={"request": {"provider": "seedream_5_0_pro"}, "imageCount": 6},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_inspire_endpoint_creates_durable_idempotent_operation(monkeypatch):
    captured = {}
    durable = SimpleNamespace(operation_id=uuid4())
    class Service:
        def create(self, **values): captured.update(values); return durable, True
    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})
    response = asyncio.run(content_studio.submit_autonomous_inspiration(
        content_studio.AutonomousInspirationRequest(provider="seedream_5_0_pro")))
    assert response.status_code == 202
    assert captured["operation_type"] == "content_studio_autonomous_inspiration"
    assert captured["executor_key"] == "content_studio_autonomous_inspiration"
    assert captured["idempotency_key"] == "content-studio-autonomous-inspiration:2:3"
    assert captured["metadata"]["request"] == {"provider": "seedream_5_0_pro"}
    assert "BackgroundTasks" not in inspect.signature(
        content_studio.submit_autonomous_inspiration).parameters


def test_autonomous_executor_persists_stages_job_and_terminal_result(monkeypatch):
    def execute(run_id, request, **kwargs):
        callback = kwargs["state_callback"]
        callback({"status": "planning", "message": "Building creative direction",
                  "inspirationDirections": ["one", "two"]})
        callback({"status": "queued", "message": "Waiting for provider", "jobId": "job-1"})
        callback({"status": "running", "message": "Processing image 1 of 6",
                  "completedCount": 1, "processedCount": 1, "progress": 16.7,
                  "outputReferences": ["one.png"]})
        return {"status": "succeeded", "message": "Complete", "completedCount": 6,
                "failedCount": 0, "processedCount": 6, "progress": 100,
                "outputReferences": [f"{index}.png" for index in range(6)]}
    monkeypatch.setattr(content_studio, "_execute_autonomous_inspiration", execute)
    operations = Operations()
    ContentStudioAutonomousBackgroundExecutor().execute(
        operation(), operations, worker_id="worker-1")
    assert [value["stage"] for value in operations.progress_values] == [
        "PLANNING", "PROVIDER_QUEUED", "GENERATING"]
    assert operations.progress_values[1]["result_reference"] == "job-1"
    assert operations.succeeded and not operations.failed


def test_provider_submitted_stale_operation_never_calls_autonomous_pipeline(monkeypatch):
    monkeypatch.setattr(
        "app.services.generation_engine_service.GenerationEngineService.get_job",
        lambda self, job_id: SimpleNamespace(status="running", result=None))
    called = []
    monkeypatch.setattr(content_studio, "_execute_autonomous_inspiration",
                        lambda *args, **kwargs: called.append(True))
    operations = Operations()
    ContentStudioAutonomousBackgroundExecutor().execute(
        operation(attempt_count=2, result_reference="job-accepted"),
        operations, worker_id="worker-2")
    assert not called
    assert operations.failed[0][1]["code"] == "PROVIDER_STATE_UNCERTAIN"


def test_worker_registry_dispatches_autonomous_executor():
    worker = BackgroundOperationWorkerService(
        worker_instance_id="worker-1", operations=SimpleNamespace())
    assert isinstance(
        worker.executors["content_studio_autonomous_inspiration"],
        ContentStudioAutonomousBackgroundExecutor,
    )

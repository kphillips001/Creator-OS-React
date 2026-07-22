from datetime import datetime, timezone

from app.models.asset_intelligence import (
    AssetIntelligenceProviderResult, AssetIntelligenceStatus,
)
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode, AssetIntelligenceProviderResponse, ProviderExecutionStatus,
)
from app.repositories.vision_analysis_job_repository import VisionAnalysisJob
from app.services.asset_intelligence_provider_adapters import GptVisionAssetIntelligenceAdapter
from app.services.vision_analysis_worker_service import VisionAnalysisWorkerService


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


class Jobs:
    def __init__(self, job): self.job, self.released = job, []
    def claim_next(self, worker): job, self.job = self.job, None; return job
    def release_claim(self, asset_id, worker): self.released.append((asset_id, worker)); return True


class Intelligence:
    def __init__(self, existing=()): self.results = list(existing)
    def list_provider_results(self, asset_id): return tuple(self.results)
    def save_provider_result(self, result): self.results.append(result); return result


class Decision:
    def __init__(self, state, changed=True): self.current_state, self.changed = state, changed


class Workflow:
    def __init__(self): self.started, self.completed, self.retried = [], [], []
    def report_started(self, asset_id, provider): self.started.append((asset_id, provider))
    def report_completion(self, asset_id, provider, *, success, **errors):
        self.completed.append((asset_id, provider, success, errors))
        return Decision(AssetIntelligenceStatus.GROK_PENDING if success else AssetIntelligenceStatus.VISION_FAILED)
    def retry(self, asset_id): self.retried.append(asset_id); return Decision(AssetIntelligenceStatus.VISION_PENDING)


class Adapter:
    provider_name = "gpt-vision"
    provider_version = "existing-model"
    def __init__(self, response): self.response, self.calls = response, []
    def analyze(self, request): self.calls.append(request); return self.response


def job(attempt=1):
    return VisionAnalysisJob(42, 7, "C:/media/shot.jpg", "shot.jpg", "image", attempt)


def response(status=ProviderExecutionStatus.SUCCEEDED):
    return AssetIntelligenceProviderResponse(
        run_id="run", asset_id=42, provider_name="gpt-vision",
        provider_version="existing-model", status=status,
        raw_response={"short_safe_summary": "Studio portrait", "confidence": .94},
        normalized_fields={"short_description": "Studio portrait", "tags": ("portrait",)},
        field_confidence={"short_description": .94, "tags": .9},
        error_code=None if status == ProviderExecutionStatus.SUCCEEDED else AssetIntelligenceErrorCode.PROVIDER_UNAVAILABLE,
        error_message=None if status == ProviderExecutionStatus.SUCCEEDED else "vision unavailable",
        started_at=NOW, completed_at=NOW, duration_ms=21,
    )


def build(status=ProviderExecutionStatus.SUCCEEDED, existing=()):
    jobs, intelligence, workflow, adapter = Jobs(job()), Intelligence(existing), Workflow(), Adapter(response(status))
    worker = VisionAnalysisWorkerService(
        worker_instance_id="vision-1", jobs=jobs, intelligence=intelligence,
        workflow=workflow, adapter=adapter,
    )
    return worker, jobs, intelligence, workflow, adapter


def test_vision_worker_persists_provider_result_and_reports_completion_only():
    worker, jobs, intelligence, workflow, adapter = build()
    result = worker.process_one()
    assert result["status"] == "GROK_PENDING"
    assert workflow.started == [(42, "VISION")]
    assert workflow.completed[0][1:3] == ("VISION", True)
    assert jobs.released == [(42, "vision-1")]
    stored = intelligence.results[0]
    assert stored.raw_response["confidence"] == .94
    assert stored.normalized_fields["short_description"] == "Studio portrait"
    assert stored.field_confidence["tags"] == .9
    assert stored.provider == "gpt-vision" and stored.provider_version == "existing-model"
    assert stored.metadata["started_at"] == NOW
    assert stored.metadata["completed_at"] == NOW and stored.metadata["duration_ms"] == 21
    assert len(adapter.calls) == 1


def test_vision_failure_is_persisted_and_reported_for_orchestrator_transition():
    worker, _, intelligence, workflow, _ = build(ProviderExecutionStatus.FAILED)
    assert worker.process_one()["status"] == "VISION_FAILED"
    assert intelligence.results[0].status == AssetIntelligenceStatus.FAILED
    assert workflow.completed[0][2] is False
    assert workflow.completed[0][3]["error_code"] == "PROVIDER_UNAVAILABLE"
    assert worker.retry_failed(42) is True and workflow.retried == [42]


def test_unexpected_vision_exception_is_persisted_as_failed_and_releases_claim():
    worker, jobs, _, workflow, _ = build()
    worker._current_asset_id = 42

    assert worker.fail_current(RuntimeError("unexpected vision crash")) == 42

    assert workflow.completed[-1] == (
        42, "VISION", False,
        {"error_code": "RuntimeError", "error_message": "unexpected vision crash"},
    )
    assert jobs.released == [(42, "vision-1")]
    assert worker._current_asset_id is None


def test_restart_reuses_successful_result_without_duplicate_vision_call():
    existing = AssetIntelligenceProviderResult(
        asset_id=42, creator_profile_id=7, provider="gpt-vision",
        raw_response={"saved": True}, status=AssetIntelligenceStatus.READY,
    )
    worker, _, intelligence, _, adapter = build(existing=(existing,))
    result = worker.process_one()
    assert result["reused"] is True and result["status"] == "GROK_PENDING"
    assert adapter.calls == [] and len(intelligence.results) == 1


def test_default_worker_reuses_existing_gpt_vision_adapter():
    worker = VisionAnalysisWorkerService(
        worker_instance_id="vision-1", jobs=Jobs(None), intelligence=Intelligence(),
        workflow=Workflow(),
    )
    assert isinstance(worker.adapter, GptVisionAssetIntelligenceAdapter)


def test_vision_claim_is_atomic_leased_and_restart_recoverable():
    import inspect
    from app.repositories.vision_analysis_job_repository import VisionAnalysisJobRepository
    source = inspect.getsource(VisionAnalysisJobRepository.claim_next)
    assert "VISION_PENDING" in source and "VISION_RUNNING" in source
    assert "FOR UPDATE OF p SKIP LOCKED" in source and "LIMIT 1" in source
    assert "vision_lease_expires_at <= now()" in source
    assert "vision_lease_expires_at IS NULL" in source


def test_worker_contains_no_next_provider_selection():
    import inspect
    source = inspect.getsource(VisionAnalysisWorkerService)
    assert "report_completion" in source
    assert "GROK_PENDING" not in source and "CONTENT_INTELLIGENCE" not in source

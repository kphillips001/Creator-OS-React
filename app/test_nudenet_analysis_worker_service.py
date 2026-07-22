from datetime import datetime, timezone

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode, AssetIntelligenceProviderResponse, ProviderExecutionStatus,
)
from app.repositories.nudenet_analysis_job_repository import NudeNetAnalysisJob
from app.services.nudenet_analysis_worker_service import NudeNetAnalysisWorkerService


NOW = datetime(2026, 7, 20, tzinfo=timezone.utc)


class Jobs:
    def __init__(self, job):
        self.job = job
        self.claims = 0
        self.released = []

    def claim_next(self, worker):
        self.claims += 1
        job, self.job = self.job, None
        return job

    def release_claim(self, asset_id, worker):
        self.released.append((asset_id, worker)); return True


class Decision:
    def __init__(self, state, changed=True): self.current_state, self.changed = state, changed


class Workflow:
    def __init__(self):
        self.started, self.completed, self.retried = [], [], []
    def report_started(self, asset_id, provider): self.started.append((asset_id, provider))
    def report_completion(self, asset_id, provider, *, success, **error):
        self.completed.append((asset_id, provider, success, error))
        return Decision(AssetIntelligenceStatus.VISION_PENDING if success else AssetIntelligenceStatus.NUDENET_FAILED)
    def retry(self, asset_id): self.retried.append(asset_id); return Decision(AssetIntelligenceStatus.NUDENET_PENDING)


class Intelligence:
    def __init__(self, existing=()):
        self.results = list(existing)

    def list_provider_results(self, asset_id): return tuple(self.results)
    def save_provider_result(self, result): self.results.append(result); return result


class Adapter:
    provider_name = "nudenet"
    provider_version = "existing"

    def __init__(self, response): self.response, self.calls = response, []
    def analyze(self, request): self.calls.append(request); return self.response


def job(attempt=1):
    return NudeNetAnalysisJob(42, 7, "C:/media/shot.jpg", "shot.jpg", "image", attempt)


def response(status=ProviderExecutionStatus.SUCCEEDED):
    return AssetIntelligenceProviderResponse(
        run_id="run", asset_id=42, provider_name="nudenet", provider_version="existing",
        status=status, raw_response=[{"class": "FEMALE_BREAST_EXPOSED", "score": .97}],
        normalized_fields={"safety_classification": "NUDITY", "keywords": ("FEMALE_BREAST_EXPOSED",)},
        field_confidence={"safety_classification": .97},
        error_code=None if status == ProviderExecutionStatus.SUCCEEDED else AssetIntelligenceErrorCode.PROVIDER_UNAVAILABLE,
        error_message=None if status == ProviderExecutionStatus.SUCCEEDED else "unavailable",
        started_at=NOW, completed_at=NOW, duration_ms=12,
    )


def test_pending_job_runs_once_and_persists_raw_normalized_confidence_and_timestamps():
    jobs, intelligence, adapter = Jobs(job()), Intelligence(), Adapter(response())
    workflow = Workflow()
    worker = NudeNetAnalysisWorkerService(worker_instance_id="worker-1", jobs=jobs,
                                           intelligence=intelligence, adapter=adapter, workflow=workflow)
    result = worker.process_one()
    assert result["status"] == "VISION_PENDING"
    assert len(adapter.calls) == 1 and jobs.released == [(42, "worker-1")]
    assert workflow.completed[0][1:3] == ("NUDENET", True)
    stored = intelligence.results[0]
    assert stored.raw_response[0]["score"] == .97
    assert stored.normalized_fields["safety_classification"] == "NUDITY"
    assert stored.field_confidence["safety_classification"] == .97
    assert stored.metadata["started_at"] == NOW and stored.metadata["duration_ms"] == 12
    assert worker.process_one()["status"] == "IDLE"
    assert len(adapter.calls) == 1


def test_existing_success_is_reused_after_restart_without_duplicate_provider_execution():
    first_jobs, intelligence, first_adapter = Jobs(job()), Intelligence(), Adapter(response())
    first_workflow = Workflow()
    NudeNetAnalysisWorkerService(worker_instance_id="old", jobs=first_jobs,
                                 intelligence=intelligence, adapter=first_adapter,
                                 workflow=first_workflow).process_one()
    resumed_jobs, resumed_adapter = Jobs(job(2)), Adapter(response())
    result = NudeNetAnalysisWorkerService(worker_instance_id="new", jobs=resumed_jobs,
                                           intelligence=intelligence, adapter=resumed_adapter,
                                           workflow=Workflow()).process_one()
    assert result["reused"] is True
    assert resumed_adapter.calls == []
    assert len(intelligence.results) == 1


def test_failure_is_persisted_failed_and_can_be_requeued():
    jobs, intelligence, adapter = Jobs(job()), Intelligence(), Adapter(response(ProviderExecutionStatus.FAILED))
    workflow = Workflow()
    worker = NudeNetAnalysisWorkerService(worker_instance_id="worker-1", jobs=jobs,
                                           intelligence=intelligence, adapter=adapter, workflow=workflow)
    assert worker.process_one()["status"] == "NUDENET_FAILED"
    assert workflow.completed[0][2] is False
    assert workflow.completed[0][3] == {"error_code": "PROVIDER_UNAVAILABLE", "error_message": "unavailable"}
    assert intelligence.results[0].status == AssetIntelligenceStatus.FAILED
    assert worker.retry_failed(42) is True and workflow.retried == [42]


def test_job_repository_uses_atomic_skip_locked_claim_and_expired_lease_recovery():
    import inspect
    from app.repositories.nudenet_analysis_job_repository import NudeNetAnalysisJobRepository
    source = inspect.getsource(NudeNetAnalysisJobRepository.claim_next)
    assert "SKIP LOCKED" in source
    assert "nudenet_lease_expires_at <= now()" in source
    assert "LIMIT 1" in source


def test_worker_reports_outcome_but_contains_no_next_provider_selection():
    import inspect
    source = inspect.getsource(NudeNetAnalysisWorkerService)
    assert "report_completion" in source
    assert "VISION" not in source
    assert "GROK" not in source

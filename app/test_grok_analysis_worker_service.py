from datetime import datetime, timezone
import inspect

from app.models.asset_intelligence import AssetIntelligenceProviderResult, AssetIntelligenceStatus
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode, AssetIntelligenceProviderResponse, ProviderExecutionStatus,
)
from app.repositories.grok_analysis_job_repository import GrokAnalysisJob
from app.services.asset_intelligence_provider_adapters import GrokVisionAssetIntelligenceAdapter
from app.services.grok_analysis_worker_service import GrokAnalysisWorkerService


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
        state = AssetIntelligenceStatus.CONTENT_INTELLIGENCE_PENDING if success else AssetIntelligenceStatus.GROK_FAILED
        return Decision(state)
    def retry(self, asset_id): self.retried.append(asset_id); return Decision(AssetIntelligenceStatus.GROK_PENDING)


class Adapter:
    provider_name = "grok-vision"
    provider_version = "existing-grok-model"
    def __init__(self, response): self.response, self.calls = response, []
    def analyze(self, request): self.calls.append(request); return self.response


def job(attempt=1): return GrokAnalysisJob(42, 7, "C:/media/shot.jpg", "shot.jpg", "image", attempt)


def response(status=ProviderExecutionStatus.SUCCEEDED):
    semantic = {
        "short_description": "A confident editorial moment",
        "content_summary": "A confident editorial moment",
        "themes": ("self-expression", "modern luxury"), "mood": "confident",
        "atmosphere": "aspirational", "emotional_tone": "empowered",
        "visual_style": "editorial lifestyle", "suggested_collections": ("Modern Muse",),
        "search_phrases": ("confident luxury portrait",),
        "keywords": ("confident luxury portrait",), "lifestyle_context": "fashion-forward city life",
    }
    return AssetIntelligenceProviderResponse(
        run_id="run", asset_id=42, provider_name="grok-vision",
        provider_version="existing-grok-model", status=status,
        raw_response={"descriptive_summary": "A confident editorial moment", "mood": "confident"},
        normalized_fields=semantic,
        field_confidence={key: .86 for key in semantic},
        error_code=None if status == ProviderExecutionStatus.SUCCEEDED else AssetIntelligenceErrorCode.PROVIDER_UNAVAILABLE,
        error_message=None if status == ProviderExecutionStatus.SUCCEEDED else "grok unavailable",
        started_at=NOW, completed_at=NOW, duration_ms=34,
    )


def build(status=ProviderExecutionStatus.SUCCEEDED, existing=()):
    jobs, intelligence, workflow, adapter = Jobs(job()), Intelligence(existing), Workflow(), Adapter(response(status))
    worker = GrokAnalysisWorkerService(worker_instance_id="grok-1", jobs=jobs,
        intelligence=intelligence, workflow=workflow, adapter=adapter)
    return worker, jobs, intelligence, workflow, adapter


def test_grok_worker_stores_semantic_result_and_reports_completion_only():
    worker, jobs, intelligence, workflow, adapter = build()
    result = worker.process_one()
    assert result["status"] == "CONTENT_INTELLIGENCE_PENDING"
    assert workflow.started == [(42, "GROK")]
    assert workflow.completed[0][1:3] == ("GROK", True)
    stored = intelligence.results[0]
    assert stored.raw_response["mood"] == "confident"
    assert stored.normalized_fields["themes"] == ("self-expression", "modern luxury")
    assert stored.normalized_fields["atmosphere"] == "aspirational"
    assert stored.normalized_fields["search_phrases"] == ("confident luxury portrait",)
    assert stored.field_confidence["mood"] == .86
    assert stored.provider == "grok-vision" and stored.provider_version == "existing-grok-model"
    assert stored.metadata["started_at"] == NOW and stored.metadata["duration_ms"] == 34
    assert jobs.released == [(42, "grok-1")] and len(adapter.calls) == 1


def test_grok_failure_is_persisted_reported_and_retryable():
    worker, _, intelligence, workflow, _ = build(ProviderExecutionStatus.FAILED)
    assert worker.process_one()["status"] == "GROK_FAILED"
    assert intelligence.results[0].status == AssetIntelligenceStatus.FAILED
    assert workflow.completed[0][3]["error_code"] == "PROVIDER_UNAVAILABLE"
    assert worker.retry_failed(42) is True and workflow.retried == [42]


def test_restart_reuses_success_without_duplicate_provider_execution():
    existing = AssetIntelligenceProviderResult(asset_id=42, creator_profile_id=7,
        provider="grok-vision", raw_response={"saved": True}, status=AssetIntelligenceStatus.READY)
    worker, _, intelligence, _, adapter = build(existing=(existing,))
    result = worker.process_one()
    assert result["reused"] is True and result["status"] == "CONTENT_INTELLIGENCE_PENDING"
    assert adapter.calls == [] and len(intelligence.results) == 1


def test_default_worker_reuses_existing_grok_adapter():
    worker = GrokAnalysisWorkerService(worker_instance_id="grok-1", jobs=Jobs(None),
        intelligence=Intelligence(), workflow=Workflow())
    assert isinstance(worker.adapter, GrokVisionAssetIntelligenceAdapter)


def test_grok_claim_is_atomic_leased_and_restart_recoverable():
    from app.repositories.grok_analysis_job_repository import GrokAnalysisJobRepository
    source = inspect.getsource(GrokAnalysisJobRepository.claim_next)
    assert "GROK_PENDING" in source and "GROK_RUNNING" in source
    assert "FOR UPDATE OF p SKIP LOCKED" in source and "LIMIT 1" in source
    assert "grok_lease_expires_at IS NULL" in source
    assert "grok_lease_expires_at <= now()" in source


def test_existing_grok_prompt_is_semantic_and_avoids_vision_duplication():
    source = inspect.getsource(GrokVisionAssetIntelligenceAdapter._default_runner)
    for field in ("themes", "mood", "atmosphere", "emotional_tone", "visual_style",
                  "suggested_collections", "search_phrases", "lifestyle_context"):
        assert field in source
    assert "do not repeat" in source


def test_worker_contains_no_next_stage_selection():
    source = inspect.getsource(GrokAnalysisWorkerService)
    assert "report_completion" in source
    assert "CONTENT_INTELLIGENCE_PENDING" not in source

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode,
    AssetIntelligenceProviderPolicy,
    AssetIntelligenceProviderResponse,
    AssetIntelligenceRunStatus,
    ProviderExecutionStatus,
)
from app.services.asset_intelligence_orchestrator import AssetIntelligenceOrchestrator
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.test_asset_intelligence_foundation import FakeRepository


class FakeRunRepository:
    def __init__(self):
        self.runs = {}
        self.executions = {}

    def create_run(self, run):
        for key, old in tuple(self.runs.items()):
            if old.asset_id == run.asset_id and old.is_current:
                self.runs[key] = replace(old, is_current=False)
        self.runs[run.run_id] = run
        return run

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def get_current_run(self, asset_id):
        return next((r for r in self.runs.values() if r.asset_id == asset_id and r.is_current), None)

    def list_runs(self, asset_id):
        return tuple(r for r in self.runs.values() if r.asset_id == asset_id)

    def update_run(self, run):
        self.runs[run.run_id] = run
        return run

    def next_attempt_number(self, run_id, provider_name):
        return 1 + max((e.attempt_number for e in self.executions.values()
                        if e.run_id == run_id and e.provider_name == provider_name), default=0)

    def create_execution(self, execution):
        existing = next((e for e in self.executions.values() if
                         (e.run_id, e.provider_name, e.attempt_number) ==
                         (execution.run_id, execution.provider_name, execution.attempt_number)), None)
        if existing:
            return existing
        self.executions[execution.execution_id] = execution
        return execution

    def complete_execution(self, execution):
        current = self.executions[execution.execution_id]
        if current.status.settled:
            return current
        self.executions[execution.execution_id] = execution
        return execution

    def list_executions(self, run_id):
        return tuple(e for e in self.executions.values() if e.run_id == run_id)

    def latest_executions(self, run_id):
        latest = {}
        for execution in self.list_executions(run_id):
            if execution.provider_name not in latest or execution.attempt_number > latest[execution.provider_name].attempt_number:
                latest[execution.provider_name] = execution
        return tuple(latest.values())


class RunAwareIntelligenceRepository(FakeRepository):
    def list_provider_results(self, asset_id, run_id=None):
        return tuple(result for result in self.results.values()
                     if result.asset_id == asset_id and (run_id is None or result.run_id == run_id))


class NeverCalledAdapter:
    provider_name = "required"
    provider_version = "fake-1"
    supported_media_types = frozenset({"image"})

    def __init__(self):
        self.calls = 0

    def is_ready(self):
        return True

    def analyze(self, request):
        self.calls += 1
        raise AssertionError("Phase 1.2 must not execute providers")

    def normalize(self, raw_response):
        return raw_response


@pytest.fixture
def harness(tmp_path):
    media = tmp_path / "image.png"
    media.write_bytes(b"image")
    run_repository = FakeRunRepository()
    intelligence_repository = RunAwareIntelligenceRepository()
    intelligence = AssetIntelligenceService(repository=intelligence_repository)
    adapter = NeverCalledAdapter()
    orchestrator = AssetIntelligenceOrchestrator(
        run_repository=run_repository, intelligence_service=intelligence,
        adapters={"required": adapter, "optional": adapter},
    )
    return orchestrator, run_repository, intelligence_repository, adapter, str(media)


def start(harness, policy=None):
    orchestrator, _, _, _, media = harness
    return orchestrator.start_analysis(
        asset_id=10, creator_profile_id=2, media_type="image",
        managed_media_path=media, original_filename="image.png",
        policy=policy or AssetIntelligenceProviderPolicy(required_providers=("required",)),
    )


def response(run, provider, status, fields=None, error=None):
    now = datetime.now(timezone.utc)
    return AssetIntelligenceProviderResponse(
        run_id=run.run_id, asset_id=run.asset_id, provider_name=provider,
        provider_version="fake-1", status=status, raw_response={"raw": provider},
        normalized_fields=fields or {}, field_confidence={key: .9 for key in (fields or {})},
        error_code=error, started_at=now, completed_at=now, duration_ms=1,
    )


def execution(repository, run, provider):
    return next(e for e in repository.latest_executions(run.run_id) if e.provider_name == provider)


def test_start_creates_pending_run_and_provider_records_without_api_call(harness):
    run = start(harness, AssetIntelligenceProviderPolicy(
        required_providers=("required",), optional_providers=("optional",)))
    _, repository, profiles, adapter, _ = harness
    assert run.status == AssetIntelligenceRunStatus.PENDING
    assert len(repository.list_executions(run.run_id)) == 2
    assert profiles.profiles[10].analysis_status == AssetIntelligenceStatus.PENDING
    assert adapter.calls == 0


def test_new_run_preserves_history_and_is_the_only_current_run(harness):
    first = start(harness)
    second = start(harness)
    repository = harness[1]
    assert len(repository.list_runs(10)) == 2
    assert repository.runs[first.run_id].is_current is False
    assert repository.get_current_run(10).run_id == second.run_id


def test_ready_when_all_required_and_optional_succeed(harness):
    run = start(harness, AssetIntelligenceProviderPolicy(
        required_providers=("required",), optional_providers=("optional",)))
    orchestrator, repository, profiles, _, _ = harness
    orchestrator.accept_provider_result(execution(repository, run, "required").execution_id,
        response(run, "required", ProviderExecutionStatus.SUCCEEDED, {"title": "Ready"}))
    settled = orchestrator.accept_provider_result(execution(repository, run, "optional").execution_id,
        response(run, "optional", ProviderExecutionStatus.SUCCEEDED, {"tags": ["tag"]}))
    assert settled.status == AssetIntelligenceRunStatus.READY
    assert profiles.profiles[10].analysis_status == AssetIntelligenceStatus.READY


@pytest.mark.parametrize("optional_status", [ProviderExecutionStatus.FAILED, ProviderExecutionStatus.TIMED_OUT])
def test_optional_failure_or_timeout_produces_partial(harness, optional_status):
    run = start(harness, AssetIntelligenceProviderPolicy(
        required_providers=("required",), optional_providers=("optional",)))
    orchestrator, repository, profiles, _, _ = harness
    orchestrator.accept_provider_result(execution(repository, run, "required").execution_id,
        response(run, "required", ProviderExecutionStatus.SUCCEEDED, {"title": "Usable"}))
    settled = orchestrator.accept_provider_result(execution(repository, run, "optional").execution_id,
        response(run, "optional", optional_status, error=AssetIntelligenceErrorCode.PROVIDER_TIMEOUT))
    assert settled.status == AssetIntelligenceRunStatus.PARTIAL
    assert profiles.profiles[10].analysis_status == AssetIntelligenceStatus.PARTIAL


def test_failed_when_no_required_provider_produces_usable_profile(harness):
    run = start(harness)
    orchestrator, repository, profiles, _, _ = harness
    settled = orchestrator.accept_provider_result(execution(repository, run, "required").execution_id,
        response(run, "required", ProviderExecutionStatus.FAILED,
                 error=AssetIntelligenceErrorCode.INVALID_RESPONSE))
    assert settled.status == AssetIntelligenceRunStatus.FAILED
    assert profiles.profiles[10].analysis_status == AssetIntelligenceStatus.FAILED


def test_one_required_success_and_one_required_failure_is_partial(harness):
    policy = AssetIntelligenceProviderPolicy(required_providers=("required", "required-two"))
    harness[0].adapters["required-two"] = harness[3]
    run = start(harness, policy)
    orchestrator, repository, profiles, _, _ = harness
    orchestrator.accept_provider_result(execution(repository, run, "required").execution_id,
        response(run, "required", ProviderExecutionStatus.SUCCEEDED, {"title": "Usable"}))
    settled = orchestrator.accept_provider_result(execution(repository, run, "required-two").execution_id,
        response(run, "required-two", ProviderExecutionStatus.FAILED,
                 error=AssetIntelligenceErrorCode.PROVIDER_UNAVAILABLE))
    assert settled.status == AssetIntelligenceRunStatus.PARTIAL
    assert profiles.profiles[10].analysis_status == AssetIntelligenceStatus.PARTIAL


def test_duplicate_completion_is_idempotent_and_stale_failure_cannot_replace_success(harness):
    run = start(harness)
    orchestrator, repository, _, _, _ = harness
    item = execution(repository, run, "required")
    first = orchestrator.accept_provider_result(item.execution_id,
        response(run, "required", ProviderExecutionStatus.SUCCEEDED, {"title": "Winner"}))
    second = orchestrator.accept_provider_result(item.execution_id,
        response(run, "required", ProviderExecutionStatus.FAILED,
                 error=AssetIntelligenceErrorCode.INTERNAL_ERROR))
    assert first.status == second.status == AssetIntelligenceRunStatus.READY
    assert repository.executions[item.execution_id].status == ProviderExecutionStatus.SUCCEEDED


def test_retry_attempt_numbers_and_success_is_not_retried(harness):
    run = start(harness)
    orchestrator, repository, _, _, _ = harness
    first = execution(repository, run, "required")
    repository.complete_execution(replace(first, status=ProviderExecutionStatus.TIMED_OUT))
    second = orchestrator.retry_provider(run.run_id, "required")
    assert second.attempt_number == 2
    repository.complete_execution(replace(second, status=ProviderExecutionStatus.SUCCEEDED))
    assert orchestrator.retry_provider(run.run_id, "required") is repository.executions[second.execution_id]


def test_policy_rejects_required_optional_overlap():
    with pytest.raises(ValueError, match="both required and optional"):
        AssetIntelligenceProviderPolicy(required_providers=("same",), optional_providers=("same",))


def test_migration_declares_asset_cascades_and_execution_idempotency():
    sql = open(
        "migrations/forward/20260715_002_asset_intelligence_provider_execution.sql",
        encoding="utf-8",
    ).read().upper()
    assert sql.count("REFERENCES PUBLIC.CONTENT_ITEMS(ID) ON DELETE CASCADE") == 2
    assert "REFERENCES PUBLIC.ASSET_INTELLIGENCE_RUNS(RUN_ID) ON DELETE CASCADE" in sql
    assert "UNIQUE (RUN_ID, PROVIDER_NAME, ATTEMPT_NUMBER)" in sql
    assert "UNIQUE (RESULT_ID)" in sql

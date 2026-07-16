"""Provider-neutral orchestration with synchronous Phase 2A execution."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from collections.abc import Callable

from app.models.asset_intelligence import (
    ASSET_INTELLIGENCE_SCHEMA_VERSION,
    AssetIntelligenceProviderResult,
    AssetIntelligenceStatus,
)
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode,
    AssetIntelligenceProviderAdapter,
    AssetIntelligenceProviderExecution,
    AssetIntelligenceProviderPolicy,
    AssetIntelligenceProviderRequest,
    AssetIntelligenceProviderResponse,
    AssetIntelligenceRun,
    AssetIntelligenceRunStatus,
    ProviderExecutionStatus,
)
from app.repositories.asset_intelligence_run_repository import AssetIntelligenceRunRepository
from app.services.asset_intelligence_service import AssetIntelligenceService


class AssetIntelligenceOrchestrator:
    def __init__(self, *, run_repository: AssetIntelligenceRunRepository,
                 intelligence_service: AssetIntelligenceService,
                 adapters: Mapping[str, AssetIntelligenceProviderAdapter] | None = None) -> None:
        self.runs = run_repository
        self.intelligence = intelligence_service
        self.adapters = dict(adapters or {})

    def start_analysis(self, *, asset_id: int, creator_profile_id: int,
                       media_type: str, managed_media_path: str,
                       original_filename: str, policy: AssetIntelligenceProviderPolicy,
                       schema_version: str = ASSET_INTELLIGENCE_SCHEMA_VERSION) -> AssetIntelligenceRun:
        profile = self.intelligence.initialize_pending(
            asset_id=asset_id, creator_profile_id=creator_profile_id
        )
        if profile.creator_profile_id != creator_profile_id:
            raise ValueError("Asset Intelligence creator ownership mismatch.")
        if not managed_media_path or not Path(managed_media_path).is_file():
            raise FileNotFoundError(managed_media_path)
        run = self.runs.create_run(AssetIntelligenceRun(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            schema_version=schema_version, required_providers=policy.required_providers,
            optional_providers=policy.optional_providers,
        ))
        for name in policy.all_providers:
            adapter = self.adapters.get(name)
            self.runs.create_execution(AssetIntelligenceProviderExecution(
                run_id=run.run_id, asset_id=asset_id, creator_profile_id=creator_profile_id,
                provider_name=name, provider_version=adapter.provider_version if adapter else None,
                attempt_number=1, is_required=name in policy.required_providers,
            ))
        # This phase records intent only. It never invokes adapter.analyze().
        return run

    def build_request(self, run_id: str, provider_name: str, *, media_type: str,
                      managed_media_path: str, original_filename: str,
                      provider_configuration: Mapping | None = None) -> AssetIntelligenceProviderRequest:
        run = self._run(run_id)
        return AssetIntelligenceProviderRequest(
            run_id=run.run_id, asset_id=run.asset_id,
            creator_profile_id=run.creator_profile_id, media_type=media_type,
            managed_media_path=managed_media_path, original_filename=original_filename,
            schema_version=run.schema_version,
            provider_configuration=dict(provider_configuration or {}),
        )

    def execute_analysis(self, *, asset_id: int, creator_profile_id: int,
                         media_type: str, managed_media_path: str,
                         original_filename: str, policy: AssetIntelligenceProviderPolicy,
                         progress: Callable[[str], None] | None = None) -> AssetIntelligenceRun:
        """Synchronously execute configured adapters for the Phase 2A workflow."""
        run = self.start_analysis(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            media_type=media_type, managed_media_path=managed_media_path,
            original_filename=original_filename, policy=policy,
        )
        for provider_name in policy.all_providers:
            adapter = self.adapters.get(provider_name)
            request = self.build_request(
                run.run_id, provider_name, media_type=media_type,
                managed_media_path=managed_media_path,
                original_filename=original_filename,
            )
            if adapter is None or not adapter.is_ready():
                now = datetime.now(timezone.utc)
                response = AssetIntelligenceProviderResponse(
                    run_id=run.run_id, asset_id=asset_id,
                    provider_name=provider_name,
                    provider_version=adapter.provider_version if adapter else "unconfigured",
                    status=ProviderExecutionStatus.FAILED,
                    error_code=AssetIntelligenceErrorCode.CONFIGURATION_ERROR,
                    error_message=f"Provider is not ready: {provider_name}",
                    started_at=now, completed_at=now, duration_ms=0,
                )
            else:
                response = adapter.analyze(request)
            execution = next(
                item for item in self.runs.latest_executions(run.run_id)
                if item.provider_name == provider_name
            )
            run = self.accept_provider_result(execution.execution_id, response)
            if progress is not None:
                progress(provider_name)
        return self._run(run.run_id)

    def retry_provider(self, run_id: str, provider_name: str) -> AssetIntelligenceProviderExecution:
        run = self._run(run_id)
        prior = [e for e in self.runs.list_executions(run_id) if e.provider_name == provider_name]
        if not prior:
            raise LookupError(f"Provider is not part of run: {provider_name}")
        latest = max(prior, key=lambda item: item.attempt_number)
        if latest.status == ProviderExecutionStatus.SUCCEEDED:
            return latest
        return self.runs.create_execution(replace(
            latest, execution_id=AssetIntelligenceProviderExecution.__dataclass_fields__["execution_id"].default_factory(),
            attempt_number=self.runs.next_attempt_number(run_id, provider_name),
            status=ProviderExecutionStatus.PENDING, result_id=None, started_at=None,
            completed_at=None, duration_ms=None, error_code=None, error_message=None,
            created_at=None, updated_at=None,
        ))

    def accept_provider_result(self, execution_id: str,
                               response: AssetIntelligenceProviderResponse) -> AssetIntelligenceRun:
        run = self._run(response.run_id)
        if run.status == AssetIntelligenceRunStatus.PENDING:
            self.runs.update_run(replace(
                run, status=AssetIntelligenceRunStatus.RUNNING,
                started_at=response.started_at or datetime.now(timezone.utc),
            ))
            self.intelligence.begin_analysis(run.asset_id)
        execution = next((e for e in self.runs.list_executions(response.run_id)
                          if e.execution_id == execution_id), None)
        if execution is None or execution.asset_id != response.asset_id:
            raise ValueError("Provider response does not match its execution.")
        result_id = f"{execution.execution_id}:result"
        settled = self.runs.complete_execution(replace(
            execution, status=response.status, result_id=result_id,
            started_at=response.started_at, completed_at=response.completed_at,
            duration_ms=response.duration_ms, error_code=response.error_code,
            error_message=response.error_message,
        ))
        if settled.status == ProviderExecutionStatus.SUCCEEDED:
            self.intelligence.record_provider_result(AssetIntelligenceProviderResult(
                result_id=result_id, run_id=response.run_id, execution_id=execution_id,
                asset_id=response.asset_id, creator_profile_id=execution.creator_profile_id,
                provider=response.provider_name, provider_version=response.provider_version,
                status=AssetIntelligenceStatus.READY, raw_response=response.raw_response,
                normalized_fields=response.normalized_fields,
                field_confidence=response.field_confidence, analyzed_at=response.completed_at,
                metadata=response.provider_metadata,
            ))
        return self._settle(response.run_id)

    def _settle(self, run_id: str) -> AssetIntelligenceRun:
        run = self._run(run_id)
        latest = self.runs.latest_executions(run_id)
        if not latest or any(not item.status.settled for item in latest):
            return run
        required = [item for item in latest if item.is_required]
        required_successes = [item for item in required if item.status == ProviderExecutionStatus.SUCCEEDED]
        all_required = len(required_successes) == len(required)
        any_failure = any(item.status != ProviderExecutionStatus.SUCCEEDED for item in latest)
        if required_successes:
            profile = self.intelligence.merger.merge(
                self.intelligence.get_profile(run.asset_id),
                self.intelligence.repository.list_provider_results(run.asset_id, run_id=run_id),
            )
            usable = profile.analysis_status in {AssetIntelligenceStatus.READY, AssetIntelligenceStatus.PARTIAL}
            if usable:
                status = AssetIntelligenceRunStatus.READY if all_required and not any_failure else AssetIntelligenceRunStatus.PARTIAL
                profile = replace(profile, analysis_status=AssetIntelligenceStatus(status.value))
                self.intelligence.repository.upsert_profile(profile)
            else:
                status = AssetIntelligenceRunStatus.FAILED
        else:
            status = AssetIntelligenceRunStatus.FAILED
            self.intelligence.mark_failed(run.asset_id, error_code="NO_USABLE_PROFILE", error_message="No required provider produced usable normalized data.")
        now = datetime.now(timezone.utc)
        return self.runs.update_run(replace(run, status=status, completed_at=now,
            error_summary={item.provider_name: item.error_code.value if item.error_code else item.status.value
                           for item in latest if item.status != ProviderExecutionStatus.SUCCEEDED}))

    def _run(self, run_id: str) -> AssetIntelligenceRun:
        run = self.runs.get_run(run_id)
        if run is None:
            raise LookupError(f"Analysis run not found: {run_id}")
        return run

"""One-provider Business Asset analysis worker for NudeNet."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from app.models.asset_intelligence import AssetIntelligenceProviderResult, AssetIntelligenceStatus
from app.models.asset_intelligence_execution import AssetIntelligenceProviderRequest, ProviderExecutionStatus
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.nudenet_analysis_job_repository import NudeNetAnalysisJobRepository
from app.services.asset_intelligence_provider_adapters import NudeNetAssetIntelligenceAdapter
from app.services.business_asset_analysis_orchestrator import BusinessAssetAnalysisOrchestrator


class NudeNetAnalysisWorkerService:
    def __init__(self, *, worker_instance_id: str, jobs=None, intelligence=None, adapter=None,
                 workflow=None) -> None:
        self.worker_instance_id = worker_instance_id
        self.jobs = jobs or NudeNetAnalysisJobRepository()
        self.intelligence = intelligence or AssetIntelligenceRepository()
        self.adapter = adapter or NudeNetAssetIntelligenceAdapter()
        self.workflow = workflow or BusinessAssetAnalysisOrchestrator()
        self._current_asset_id: int | None = None

    def process_one(self) -> dict:
        job = self.jobs.claim_next(self.worker_instance_id)
        if job is None:
            return {"processed": False, "status": "IDLE"}
        self._current_asset_id = job.asset_id
        self.workflow.report_started(job.asset_id, "NUDENET")

        previous = next(
            (item for item in self.intelligence.list_provider_results(job.asset_id)
             if item.provider == self.adapter.provider_name
             and item.status == AssetIntelligenceStatus.READY),
            None,
        )
        if previous is not None:
            decision = self.workflow.report_completion(job.asset_id, "NUDENET", success=True)
            self._release_claim(job.asset_id)
            return {"processed": True, "asset_id": job.asset_id, "status": decision.current_state.value, "reused": True}

        run_id = str(uuid5(NAMESPACE_URL, f"creator-os:nudenet-run:{job.asset_id}"))
        response = self.adapter.analyze(AssetIntelligenceProviderRequest(
            run_id=run_id, asset_id=job.asset_id, creator_profile_id=job.creator_profile_id,
            media_type=job.media_type, managed_media_path=job.file_path,
            original_filename=job.file_name, schema_version="nudenet_stage_v1",
        ))
        analyzed_at = response.completed_at or datetime.now(timezone.utc)
        result = self.intelligence.save_provider_result(AssetIntelligenceProviderResult(
            result_id=str(uuid5(NAMESPACE_URL, f"creator-os:nudenet-result:{job.asset_id}:{job.attempt_number}")),
            asset_id=job.asset_id, creator_profile_id=job.creator_profile_id,
            provider=response.provider_name, provider_version=response.provider_version,
            raw_response=response.raw_response, normalized_fields=response.normalized_fields,
            field_confidence=response.field_confidence,
            status=(AssetIntelligenceStatus.READY if response.status == ProviderExecutionStatus.SUCCEEDED
                    else AssetIntelligenceStatus.FAILED),
            analyzed_at=analyzed_at, error_code=response.error_code.value if response.error_code else None,
            error_message=response.error_message,
            metadata={"stage": "NUDENET", "attempt": job.attempt_number,
                      "started_at": response.started_at, "completed_at": response.completed_at,
                      "duration_ms": response.duration_ms},
        ))
        if response.status == ProviderExecutionStatus.SUCCEEDED:
            decision = self.workflow.report_completion(job.asset_id, "NUDENET", success=True)
            self._release_claim(job.asset_id)
            return {"processed": True, "asset_id": job.asset_id, "status": decision.current_state.value,
                    "result_id": result.result_id}
        code = response.error_code.value if response.error_code else "PROVIDER_UNAVAILABLE"
        decision = self.workflow.report_completion(
            job.asset_id, "NUDENET", success=False, error_code=code,
            error_message=response.error_message or "NudeNet failed.",
        )
        self._release_claim(job.asset_id)
        return {"processed": True, "asset_id": job.asset_id, "status": decision.current_state.value,
                "result_id": result.result_id, "error": response.error_message}

    def retry_failed(self, asset_id: int) -> bool:
        return self.workflow.retry(asset_id).changed

    def fail_current(self, error: Exception) -> int | None:
        asset_id = self._current_asset_id
        if asset_id is None:
            return None
        try:
            self.workflow.report_completion(
                asset_id, "NUDENET", success=False,
                error_code=type(error).__name__, error_message=str(error),
            )
        finally:
            self._release_claim(asset_id)
        return asset_id

    def _release_claim(self, asset_id: int) -> None:
        self.jobs.release_claim(asset_id, self.worker_instance_id)
        self._current_asset_id = None

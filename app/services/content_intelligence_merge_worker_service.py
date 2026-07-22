"""Run deterministic Content Intelligence merges assigned by the orchestrator."""

from __future__ import annotations

from app.repositories.content_intelligence_merge_job_repository import ContentIntelligenceMergeJobRepository
from app.services.business_asset_analysis_orchestrator import BusinessAssetAnalysisOrchestrator
from app.services.content_intelligence_merge_service import (
    ContentIntelligenceMergeService, MissingRequiredProviderResults,
)


class ContentIntelligenceMergeWorkerService:
    def __init__(self, *, worker_instance_id: str, jobs=None, merger=None, workflow=None) -> None:
        self.worker_instance_id = worker_instance_id
        self.jobs = jobs or ContentIntelligenceMergeJobRepository()
        self.merger = merger or ContentIntelligenceMergeService()
        self.workflow = workflow or BusinessAssetAnalysisOrchestrator()

    def process_one(self) -> dict:
        job = self.jobs.claim_next(self.worker_instance_id)
        if job is None:
            return {"processed": False, "status": "IDLE"}
        self.workflow.report_started(job.asset_id, "CONTENT_INTELLIGENCE")
        try:
            existing = self.merger.profiles.get_by_asset_id(job.asset_id)
            reused = self.merger.is_completed_merge(existing)
            profile = existing if reused else self.merger.merge(
                job.asset_id, attempt_number=job.attempt_number
            )
            if profile is None or not profile.ready:
                raise RuntimeError("Content Intelligence merge did not produce a complete profile.")
            if not self.jobs.mark_business_ready(job.asset_id):
                raise LookupError(f"Business Asset registration not found: {job.asset_id}")
            decision = self.workflow.report_completion(
                job.asset_id, "CONTENT_INTELLIGENCE", success=True
            )
            return {"processed": True, "asset_id": job.asset_id,
                    "status": decision.current_state.value, "reused": reused}
        except MissingRequiredProviderResults as error:
            decision = self.workflow.report_completion(
                job.asset_id, "CONTENT_INTELLIGENCE", success=False,
                error_code="MISSING_REQUIRED_PROVIDER_RESULT", error_message=str(error),
            )
            return {"processed": True, "asset_id": job.asset_id,
                    "status": decision.current_state.value, "error": str(error)}
        except Exception as error:
            self.merger.record_failure(
                job.asset_id, error, attempt_number=job.attempt_number
            )
            decision = self.workflow.report_completion(
                job.asset_id, "CONTENT_INTELLIGENCE", success=False,
                error_code=type(error).__name__, error_message=str(error),
            )
            return {"processed": True, "asset_id": job.asset_id,
                    "status": decision.current_state.value, "error": str(error)}
        finally:
            self.jobs.release_claim(job.asset_id, self.worker_instance_id)

    def retry_failed(self, asset_id: int) -> bool:
        return self.workflow.retry(asset_id).changed

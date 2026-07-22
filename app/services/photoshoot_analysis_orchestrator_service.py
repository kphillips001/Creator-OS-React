"""Photoshoot-specific orchestration reusing canonical member Image analysis."""

from __future__ import annotations

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.commerce_registration_repository import CommerceRegistrationRepository
from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository
from app.repositories.photoshoot_analysis_workflow_repository import PhotoshootAnalysisWorkflowRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.services.business_asset_analysis_orchestrator import BusinessAssetAnalysisOrchestrator
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


class PhotoshootAnalysisOrchestratorService:
    REQUIRED_STAGES = {"NUDENET", "VISION", "GROK"}
    TERMINAL_MEMBER_FAILURES = {
        AssetIntelligenceStatus.NUDENET_FAILED, AssetIntelligenceStatus.VISION_FAILED,
        AssetIntelligenceStatus.GROK_FAILED, AssetIntelligenceStatus.CONTENT_INTELLIGENCE_FAILED,
        AssetIntelligenceStatus.FAILED,
    }

    def __init__(self, *, worker_instance_id: str, workflows=None, photoshoots=None,
                 intelligence=None, intelligence_service=None, content=None, business=None,
                 deliverables=None):
        self.worker_id = worker_instance_id
        self.workflows = workflows or PhotoshootAnalysisWorkflowRepository()
        self.photoshoots = photoshoots or PhotoshootCommerceRepository()
        self.intelligence = intelligence or AssetIntelligenceRepository()
        self.intelligence_service = intelligence_service or AssetIntelligenceService(self.intelligence)
        self.content = content or ContentIntelligenceProfileRepository()
        self.business = business or CommerceRegistrationRepository()
        self.deliverables = deliverables or PhotoshootCommerceDeliverableService(
            repository=self.photoshoots, intelligence=self.content)

    def process_one(self):
        job = self.workflows.claim_next(self.worker_id)
        if job is None:
            return {"processed": False, "status": "IDLE"}
        row = self.photoshoots.get(job.deliverable_id)
        if row is None or row["registration_state"] != "REGISTERED" or row["is_archived"]:
            error = RuntimeError("Photoshoot is not active registered inventory.")
            self.workflows.transition(job.deliverable_id, self.worker_id, "MEMBER_ANALYSIS_FAILED", error=error)
            return self._result(job, "MEMBER_ANALYSIS_FAILED", error)
        try:
            if job.current_stage == "MEMBER_ANALYSIS_RUNNING":
                return self._members(job, row)
            if job.current_stage == "PHOTOSHOOT_INTELLIGENCE_RUNNING":
                return self._aggregate(job, row)
            return self._name(job, row)
        except Exception as error:
            failed = ("MEMBER_ANALYSIS_FAILED" if job.current_stage == "MEMBER_ANALYSIS_RUNNING"
                      else "PHOTOSHOOT_INTELLIGENCE_FAILED" if job.current_stage == "PHOTOSHOOT_INTELLIGENCE_RUNNING"
                      else "NAMING_FAILED")
            self.photoshoots.set_analysis_failure(job.deliverable_id, str(error))
            self.workflows.transition(job.deliverable_id, self.worker_id, failed, error=error)
            return self._result(job, failed, error)

    def _members(self, job, row):
        for member in self.photoshoots.members(row["photoshoot_session_id"]):
            asset_id = int(member["asset_id"])
            if self.business.get_by_asset_id(asset_id) is None:
                raise RuntimeError(f"Member Asset {asset_id} has no Business Asset registration for canonical analysis.")
            profile = self.intelligence_service.initialize_pending(
                asset_id=asset_id, creator_profile_id=int(row["creator_profile_id"]))
            if profile.analysis_status in self.TERMINAL_MEMBER_FAILURES:
                error = RuntimeError(f"Member Asset {asset_id} failed canonical analysis: {profile.error_message or profile.analysis_status.value}")
                self.photoshoots.set_analysis_failure(job.deliverable_id, str(error))
                self.workflows.transition(job.deliverable_id, self.worker_id, "MEMBER_ANALYSIS_FAILED", error=error, member_id=asset_id)
                return self._result(job, "MEMBER_ANALYSIS_FAILED", error)
            if not self._canonical_ready(asset_id, profile):
                self.photoshoots.set_analysis_pending(job.deliverable_id)
                self.workflows.transition(job.deliverable_id, self.worker_id, "MEMBER_ANALYSIS_PENDING")
                return self._result(job, "MEMBER_ANALYSIS_PENDING")
        self.workflows.transition(job.deliverable_id, self.worker_id, "PHOTOSHOOT_INTELLIGENCE_PENDING")
        return self._result(job, "PHOTOSHOOT_INTELLIGENCE_PENDING")

    def _canonical_ready(self, asset_id, profile):
        if profile.analysis_status != AssetIntelligenceStatus.READY:
            return False
        successful = {str(result.metadata.get("stage") or "").upper() for result in self.intelligence.list_provider_results(asset_id)
                      if result.status == AssetIntelligenceStatus.READY}
        content = self.content.get_by_asset_id(asset_id)
        business = self.business.get_by_asset_id(asset_id)
        return self.REQUIRED_STAGES <= successful and bool(content and content.ready) and bool(business and business.content_intelligence_ready)

    def _aggregate(self, job, row):
        try:
            status, profile, error = self.deliverables.aggregate_members(
                tuple(int(member["asset_id"]) for member in self.photoshoots.members(row["photoshoot_session_id"])))
            if status != "READY":
                raise error or RuntimeError("Photoshoot Intelligence aggregation failed.")
            self.photoshoots.upsert_intelligence(row["photoshoot_session_id"], "READY", profile)
            self.workflows.transition(job.deliverable_id, self.worker_id, "NAMING_PENDING")
            return self._result(job, "NAMING_PENDING")
        except Exception as error:
            self.photoshoots.set_analysis_failure(job.deliverable_id, str(error))
            self.workflows.transition(job.deliverable_id, self.worker_id, "PHOTOSHOOT_INTELLIGENCE_FAILED", error=error)
            return self._result(job, "PHOTOSHOOT_INTELLIGENCE_FAILED", error)

    def _name(self, job, row):
        try:
            intelligence = self.photoshoots.get(job.deliverable_id).get("intelligence_profile") or {}
            self.deliverables.ensure_naming_or_raise(row, intelligence)
            self.photoshoots.set_ready(job.deliverable_id)
            self.workflows.transition(job.deliverable_id, self.worker_id, "READY")
            return self._result(job, "READY")
        except Exception as error:
            self.photoshoots.set_naming_failure(job.deliverable_id, str(error))
            self.workflows.transition(job.deliverable_id, self.worker_id, "NAMING_FAILED", error=error)
            return self._result(job, "NAMING_FAILED", error)

    def retry(self, deliverable_id: str):
        workflow = self.workflows.get(deliverable_id)
        if workflow is None:
            raise KeyError("Photoshoot analysis workflow not found.")
        member_id = workflow.get("failed_member_asset_id")
        if workflow["current_stage"] == "MEMBER_ANALYSIS_FAILED" and member_id:
            profile = self.intelligence.get_profile(int(member_id))
            if profile and profile.analysis_status in self.TERMINAL_MEMBER_FAILURES:
                BusinessAssetAnalysisOrchestrator().retry(int(member_id))
        self.photoshoots.set_analysis_pending(deliverable_id)
        return self.workflows.retry(deliverable_id)

    @staticmethod
    def _result(job, status, error=None):
        value = {"processed": True, "deliverable_id": job.deliverable_id, "status": status}
        if error: value["error"] = str(error)
        return value

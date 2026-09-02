"""Promote a staged generation into a pending Business Asset."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceDestinationStatus,
    CommerceRegistrationStatus,
)
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.generation_engine import utc_now
from app.models.generation_library import GeneratedImageRecord
from app.repositories.commerce_registration_repository import (
    CommerceRegistrationRepository,
)
from app.services.asset_registration_service import AssetRegistrationService
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.services.business_asset_analysis_orchestrator import (
    BusinessAssetAnalysisOrchestrator,
)
from app.services.generation_library_service import GenerationLibraryService
from app.models.asset_intelligence import AssetIntelligenceStatus


@dataclass(frozen=True)
class StagedAssetRegistrationResult:
    success: bool
    asset_id: int | None = None
    registration_id: str | None = None
    already_registered: bool = False
    analysis_status: str = "PENDING"
    business_lifecycle_state: str | None = None
    message: str = ""


class StagedAssetRegistrationService:
    """Own only staged-to-pending-Business-Asset promotion."""

    def __init__(
        self,
        *,
        asset_registration_service: AssetRegistrationService | None = None,
        commerce_registration_repository: CommerceRegistrationRepository | None = None,
        generation_library_service: GenerationLibraryService | None = None,
        asset_intelligence_service: AssetIntelligenceService | None = None,
        analysis_orchestrator: BusinessAssetAnalysisOrchestrator | None = None,
    ) -> None:
        self.generation_library = generation_library_service or GenerationLibraryService()
        self.asset_registration = asset_registration_service or AssetRegistrationService(
            generation_library_service=self.generation_library,
            analyze_on_registration=False,
        )
        self.business_assets = (
            commerce_registration_repository or CommerceRegistrationRepository()
        )
        self.intelligence = (
            asset_intelligence_service
            or getattr(self.asset_registration, "asset_intelligence", None)
            or AssetIntelligenceService()
        )
        self.analysis = analysis_orchestrator or BusinessAssetAnalysisOrchestrator()

    def register(
        self,
        record: GeneratedImageRecord,
        *,
        creator_profile_id: int,
        registration_purpose: str = "SINGLE_IMAGE",
        finalize_generation: bool = True,
    ) -> StagedAssetRegistrationResult:
        if int(record.creator_profile_id) != int(creator_profile_id):
            return StagedAssetRegistrationResult(
                success=False,
                message="Staged Asset belongs to another Creator Profile.",
            )
        purpose = str(registration_purpose or "SINGLE_IMAGE").strip().upper()
        allowed_statuses = {"staged_asset_library", "business_asset_registered"}
        if purpose == "PHOTOSHOOT_MEMBER":
            allowed_statuses.add("active")
        if record.status not in allowed_statuses:
            return StagedAssetRegistrationResult(
                success=False,
                message="Only staged Asset Library items can be registered.",
            )

        asset_result = self.asset_registration.register_generated_image(
            record,
            creator_profile_id=int(creator_profile_id),
            classification=("UNCLASSIFIED" if purpose == "PHOTOSHOOT_MEMBER" else "SINGLE_IMAGE"),
            finalize_generation=finalize_generation,
        )
        if not asset_result.success or asset_result.asset_id is None:
            return StagedAssetRegistrationResult(
                success=False,
                asset_id=asset_result.asset_id,
                already_registered=asset_result.already_registered,
                message=asset_result.message or "Asset registration failed.",
            )

        asset_id = int(asset_result.asset_id)
        existing = self.business_assets.get_by_asset_id(asset_id)
        if existing is not None:
            if int(existing.creator_profile_id or 0) != int(creator_profile_id):
                return StagedAssetRegistrationResult(
                    success=False,
                    asset_id=asset_id,
                    message="Business Asset belongs to another Creator Profile.",
                )
            business_asset = existing
            already_registered = True
        else:
            business_asset = self.business_assets.upsert_record(
                self._pending_business_asset(
                    record,
                    asset_id=asset_id,
                    creator_profile_id=int(creator_profile_id),
                    registration_purpose=purpose,
                )
            )
            already_registered = bool(asset_result.already_registered)

        analysis_status = self._ensure_analysis(
            asset_id, creator_profile_id=int(creator_profile_id),
        )
        if finalize_generation:
            self.generation_library.mark_business_registered(record.image_id, asset_id)
        return StagedAssetRegistrationResult(
            success=True,
            asset_id=asset_id,
            registration_id=str(business_asset.registration_id),
            already_registered=already_registered,
            analysis_status=analysis_status,
            business_lifecycle_state=business_asset.business_lifecycle_state.value,
            message=(
                "Asset is already registered. Intelligence analysis is complete."
                if already_registered and analysis_status == "READY"
                else "Asset is registered. Intelligence analysis is in progress."
            ),
        )

    def _ensure_analysis(self, asset_id: int, *, creator_profile_id: int) -> str:
        """Idempotently start or repair the canonical Business Asset analysis chain."""
        reader = getattr(self.intelligence, "get_profile", None)
        profile = reader(int(asset_id)) if callable(reader) else None
        profile = profile or self.intelligence.initialize_pending(
            asset_id=int(asset_id), creator_profile_id=int(creator_profile_id),
        )
        if profile.analysis_status == AssetIntelligenceStatus.READY:
            return profile.analysis_status.value
        provider_failures = set(BusinessAssetAnalysisOrchestrator.FAILED.values())
        if profile.analysis_status in provider_failures:
            decision = self.analysis.retry(int(asset_id))
        elif profile.analysis_status == AssetIntelligenceStatus.FAILED:
            self.analysis.repository.transition(
                int(asset_id), AssetIntelligenceStatus.FAILED,
                AssetIntelligenceStatus.PENDING,
            )
            decision = self.analysis.advance(int(asset_id))
        else:
            decision = self.analysis.advance(int(asset_id))
        return decision.current_state.value

    @staticmethod
    def _pending_business_asset(
        record: GeneratedImageRecord,
        *,
        asset_id: int,
        creator_profile_id: int,
        registration_purpose: str = "SINGLE_IMAGE",
    ) -> BusinessAssetRecord:
        now = utc_now()
        source_metadata: dict[str, Any] = {
            "generated_image_id": record.image_id,
            "generation_job_id": record.generation_job_id,
            "generation_request_id": record.generation_request_id,
            "generation_result_id": record.generation_result_id,
            "prompt_plan_id": record.prompt_plan_id,
            "prompt_text": record.prompt_text,
            "provider_id": record.provider_id,
            "creative_mode": record.creative_mode,
            "reference_asset_id": record.reference_asset_id,
            "photoshoot_session_id": record.photoshoot_session_id,
            "photoshoot_request_id": record.photoshoot_request_id,
            "provider_metadata": dict(record.provider_metadata or {}),
            "prompt_metadata": dict(record.prompt_metadata or {}),
            "generation_metadata": dict(record.generation_metadata or {}),
            "output_reference": record.output_reference,
        }
        return BusinessAssetRecord(
            registration_id=BusinessAssetRecord.deterministic_id(asset_id),
            asset_id=asset_id,
            creator_profile_id=creator_profile_id,
            approval_status="approved",
            content_intelligence_status="PENDING",
            content_intelligence_ready=False,
            commerce_registration_status=CommerceRegistrationStatus.PENDING,
            business_lifecycle_state=BusinessAssetLifecycleState.INTELLIGENCE_PENDING,
            commerce_destination_status=CommerceDestinationStatus.NOT_READY,
            commerce_intelligence_refs={"asset_intelligence_status": "PENDING"},
            publishing_readiness={"status": "NOT_EVALUATED", "execution": "not_run"},
            fulfillment_readiness={"status": "NOT_EVALUATED", "execution": "not_run"},
            relationship_provenance={
                "source": "staged_asset_registration",
                "registration_purpose": registration_purpose,
            },
            registration_provenance={
                "source": "Asset Library",
                "source_workflow": "staged_asset_library_registration",
                "registration_purpose": registration_purpose,
                "idempotency_key": f"staged-asset-registration:{record.image_id}",
                "approval_identity": {
                    "source_workflow": "staged_asset_library_registration",
                    "source_item_id": record.image_id,
                    "idempotency_key": f"staged-asset-registration:{record.image_id}",
                    "approved_at": now,
                },
                ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                    AssetProvenanceClassification.CREATOR_APPROVAL,
                    source="Asset Library",
                    source_workflow="staged_asset_library_registration",
                    metadata={"source_item_id": record.image_id},
                ),
                "generation": source_metadata,
            },
            missing_requirements=("asset_analysis_complete",),
            warnings=("analysis_pending",),
            registered_at=now,
            last_refreshed_at=now,
        )

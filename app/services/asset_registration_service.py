"""Minimal generated-image registration into the canonical Asset Library."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.models.generation_library import GeneratedImageRecord
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.generation_engine import utc_now
from app.repositories.asset_repository import AssetRepository
from app.repositories.content_repository import insert_content_item, update_content_item
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.services.asset_intelligence_analysis_service import AssetIntelligenceAnalysisService
from app.services.generation_library_service import GenerationLibraryService
from app.services.reference_asset_protection import is_protected_generation_metadata, is_protected_reference_asset


@dataclass(frozen=True)
class AssetRegistrationResult:
    success: bool
    asset_id: int | None = None
    already_registered: bool = False
    message: str = ""


class AssetRegistrationService:
    """Register generated media and synchronously build Phase 2A intelligence."""

    def __init__(
        self,
        *,
        asset_repository: AssetRepository | None = None,
        generation_library_service: GenerationLibraryService | None = None,
        asset_intelligence_service: AssetIntelligenceService | None = None,
        asset_analysis_service: AssetIntelligenceAnalysisService | None = None,
        content_item_inserter: Callable[[dict], int | None] = insert_content_item,
        content_item_updater: Callable[[int, dict], object] = update_content_item,
        analyze_on_registration: bool = True,
    ) -> None:
        self.assets = asset_repository or AssetRepository()
        self.generation_library = (
            generation_library_service or GenerationLibraryService()
        )
        self.insert_content_item = content_item_inserter
        self.asset_intelligence = (
            asset_intelligence_service or AssetIntelligenceService()
        )
        self.asset_analysis = asset_analysis_service
        self.update_content_item = content_item_updater
        self.analyze_on_registration = bool(analyze_on_registration)

    def register_generated_image(
        self,
        record: GeneratedImageRecord,
        *,
        creator_profile_id: int,
        progress: Callable[[str], None] | None = None,
    ) -> AssetRegistrationResult:
        if is_protected_generation_metadata(record.generation_metadata):
            return AssetRegistrationResult(success=False, message="Protected Reference assets cannot be registered.")
        existing_id = record.imported_asset_id
        if existing_id is None:
            existing = self.assets.get_by_generation_image_id(record.image_id)
            existing_id = existing.id if existing else None
        if existing_id is not None:
            get_by_id = getattr(self.assets, "get_by_id", None)
            existing_asset = get_by_id(int(existing_id)) if callable(get_by_id) else None
            if existing_asset is not None and is_protected_reference_asset(existing_asset):
                return AssetRegistrationResult(success=False, message="Protected Reference assets cannot be registered.")
            if (
                existing_asset is not None
                and int(existing_asset.creator_profile_id or 0) != int(creator_profile_id)
            ):
                return AssetRegistrationResult(success=False, message="Asset belongs to another Creator Profile.")
            profile = self.asset_intelligence.initialize_pending(
                asset_id=int(existing_id),
                creator_profile_id=int(creator_profile_id),
            )
            if self.analyze_on_registration and profile.analysis_status.value != "READY":
                completed = self._analyze(
                    asset_id=int(existing_id), creator_profile_id=int(creator_profile_id),
                    progress=progress,
                )
                if not completed:
                    return AssetRegistrationResult(
                        success=False, asset_id=int(existing_id), already_registered=True,
                        message="Asset registration is saved, but intelligence analysis failed.",
                    )
            self.generation_library.mark_registered(record.image_id, int(existing_id))
            return AssetRegistrationResult(
                success=True,
                asset_id=int(existing_id),
                already_registered=True,
                message="Asset is already registered.",
            )

        source_path = Path(record.output_reference).expanduser()
        if not source_path.exists() or not source_path.is_file():
            return AssetRegistrationResult(
                success=False,
                message="Generated image file was not found.",
            )

        asset_id = self.insert_content_item(
            {
                "file_path": str(source_path),
                "file_name": source_path.name,
                "classification": "UNCLASSIFIED",
                "confidence": None,
                "detected_themes": [],
                "suggested_tags": [],
                "nudity_labels": [],
                "is_explicit": False,
                "is_test": False,
                "requires_nudenet": False,
                "requires_blur": False,
                "requires_vision": False,
                "status": "analyzing" if self.analyze_on_registration else "approved",
                "ready_for_rotation": False,
                "content_type": "image",
                "creator_profile_id": int(creator_profile_id),
                "media_metadata": {
                    "media_type": "image",
                    "creator_approval": {
                        "source_workflow": "staged_asset_library_registration",
                        "source_item_id": record.image_id,
                        "idempotency_key": f"staged-asset-registration:{record.image_id}",
                        "approved_at": utc_now(),
                    },
                    ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                        AssetProvenanceClassification.CREATOR_APPROVAL,
                        source="AssetRegistrationService",
                        source_workflow="staged_asset_library_registration",
                        metadata={
                            "source_item_id": record.image_id,
                            "idempotency_key": f"staged-asset-registration:{record.image_id}",
                        },
                    ),
                    "asset_registration": {
                        "phase": 1,
                        "source": "generation_library",
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
                    },
                },
            }
        )
        if asset_id is None:
            return AssetRegistrationResult(
                success=False,
                message="Asset registration did not create a record.",
            )
        self.asset_intelligence.initialize_pending(
            asset_id=int(asset_id),
            creator_profile_id=int(creator_profile_id),
        )
        if progress:
            progress("Registering Asset")
        if self.analyze_on_registration and not self._analyze(
            asset_id=int(asset_id), creator_profile_id=int(creator_profile_id),
            progress=progress,
        ):
            return AssetRegistrationResult(
                success=False,
                asset_id=int(asset_id),
                message="Asset registration is saved, but intelligence analysis failed.",
            )
        self.generation_library.mark_registered(record.image_id, int(asset_id))
        if progress:
            progress("Completed")
        return AssetRegistrationResult(
            success=True,
            asset_id=int(asset_id),
            message="Image registered in the Asset Library.",
        )

    def _analyze(self, *, asset_id: int, creator_profile_id: int,
                 progress: Callable[[str], None] | None) -> bool:
        analysis = self.asset_analysis or AssetIntelligenceAnalysisService(
            asset_repository=self.assets,
        )
        try:
            analysis.analyze(
                asset_id=asset_id, creator_profile_id=creator_profile_id,
                progress=progress,
            )
        except Exception:
            self.update_content_item(asset_id, {"status": "analysis_failed"})
            return False
        self.update_content_item(asset_id, {"status": "approved"})
        return True

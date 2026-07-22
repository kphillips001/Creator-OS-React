"""Post-analysis bridge into the existing Chat Commerce registration boundary."""

from __future__ import annotations

from app.repositories.ready_asset_chat_registration_job_repository import (
    ReadyAssetChatRegistrationJobRepository,
)
from app.services.chat_commerce_registration_service import ChatCommerceRegistrationService
from app.repositories.asset_repository import AssetRepository
from app.repositories.commerce_registration_repository import CommerceRegistrationRepository
from app.services.runtime_media_resolver import RuntimeMediaResolver


class ReadyAssetChatRegistrationWorkerService:
    def __init__(self, *, worker_instance_id: str, jobs=None, chat_registration=None,
                 assets=None, registrations=None, runtime_media=None) -> None:
        self.worker_instance_id = worker_instance_id
        self.jobs = jobs or ReadyAssetChatRegistrationJobRepository()
        self.chat_registration = chat_registration or ChatCommerceRegistrationService()
        self.assets = assets or AssetRepository()
        self.registrations = registrations or CommerceRegistrationRepository()
        self.runtime_media = runtime_media or RuntimeMediaResolver()

    def process_one(self) -> dict:
        job = self.jobs.claim_next(self.worker_instance_id)
        if job is None:
            return {"processed": False, "status": "IDLE"}
        try:
            asset = self.assets.get_by_id(job.asset_id)
            business = self.registrations.get_by_asset_id(job.asset_id)
            missing: list[str] = []
            if asset is None:
                missing.append("canonical_asset_not_found")
            elif not self.runtime_media.resolve_original(asset, require_exists=True).exists:
                missing.append("runtime_media_missing")
            if business is None:
                missing.append("business_asset_not_found")
            elif asset is not None and int(getattr(asset, "creator_profile_id", 0) or 0) != int(business.creator_profile_id or 0):
                missing.append("creator_ownership_mismatch")
            result = self.chat_registration.register_fulfilled_asset(
                job.asset_id,
                idempotency_key=f"ready-asset-chat-registration:{job.asset_id}",
                additional_block_reasons=tuple(missing),
            )
            self.jobs.complete(job.asset_id, self.worker_instance_id, result)
            return {
                "processed": True,
                "asset_id": job.asset_id,
                "status": getattr(result.availability_state, "value", None),
                "chat_ready": bool(result.chat_ready),
                "missing_requirements": list(result.block_reasons),
            }
        except Exception as error:
            self.jobs.fail(job.asset_id, self.worker_instance_id, error)
            return {"processed": True, "asset_id": job.asset_id, "status": "FAILED", "error": str(error)}

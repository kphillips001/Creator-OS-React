"""Compatibility projection over canonical Ownership Intelligence."""

from __future__ import annotations

from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.ownership_intelligence_repository import (
    OwnershipIntelligenceRepository,
)
from app.services.ownership_intelligence_service import (
    OwnershipIntelligenceService,
)


class CommercialOwnershipCoverageRepository:
    """Preserve the Phase 3 shape without retaining a second ownership query."""

    def __init__(self, connection_factory=None) -> None:
        repository = (
            OwnershipIntelligenceRepository(connection_factory)
            if connection_factory is not None
            else OwnershipIntelligenceRepository()
        )
        self.intelligence = OwnershipIntelligenceService(repository)

    def get(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid, telegram_user_id: int | None,
        legacy_fanvue_user_id, core_user_id=None,
    ) -> dict:
        answer = self.intelligence.answer(OwnershipIdentity(
            creator_profile_id=int(creator_profile_id),
            fanvue_account_id=int(fanvue_account_id),
            external_fanvue_user_uuid=external_fanvue_user_uuid,
            telegram_user_id=telegram_user_id,
            legacy_fanvue_user_id=(
                str(legacy_fanvue_user_id)
                if legacy_fanvue_user_id is not None else None
            ),
            core_user_id=core_user_id,
        ))
        purchase_assets = {
            asset_id for item in answer.evidence
            if item.offering_id is not None and item.proves_ownership
            for asset_id in item.asset_ids
        }
        entitlement_assets = {
            asset_id for item in answer.evidence
            if item.product_id is not None and item.proves_ownership
            for asset_id in item.asset_ids
        }
        legacy_assets = {
            asset_id for item in answer.evidence
            if item.source.value == "LEGACY_CONTENT_USAGE"
            and item.proves_ownership for asset_id in item.asset_ids
        }
        return {
            "owned_offering_ids": answer.owned_offering_ids,
            "owned_asset_ids": answer.owned_asset_ids,
            "purchase_asset_ids": tuple(sorted(purchase_assets)),
            "entitlement_asset_ids": tuple(sorted(entitlement_assets)),
            "legacy_asset_ids": tuple(sorted(legacy_assets)),
            "evidence_sources": tuple(dict.fromkeys(
                item.source.value for item in answer.evidence
                if item.proves_ownership
            )),
            "incomplete": bool(answer.insufficiencies),
            "conflicts": answer.conflicts,
        }

"""Photoshoot-level Bundle ownership projected from canonical commerce evidence."""

from __future__ import annotations

from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.photoshoot_bundle_ownership_repository import (
    PhotoshootBundleOwnershipRepository,
)
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


class PhotoshootBundleOwnershipService:
    def __init__(self, *, repository=None, ownership=None) -> None:
        self.repository = repository or PhotoshootBundleOwnershipRepository()
        self.ownership = ownership or OwnershipIntelligenceService()

    def inspect(self, deliverable_id, *, identity: OwnershipIdentity) -> dict:
        row = self.repository.context(
            deliverable_id, creator_profile_id=identity.creator_profile_id,
        )
        if row is None:
            raise KeyError("Photoshoot not found.")
        if str(row.get("selling_mode") or "SESSION") != "BUNDLE":
            raise ValueError("Bundle ownership requires BUNDLE selling mode.")
        offering_id = row.get("offering_id")
        paid_ids = tuple(row.get("paid_asset_ids") or ())
        answer = self.ownership.answer(identity)
        purchased = bool(
            offering_id is not None
            and self.ownership.owns_offering(answer, offering_id)
        )
        paid_set = frozenset(paid_ids)
        owned_ids = tuple(
            asset_id for asset_id in paid_ids
            if asset_id in frozenset(answer.owned_asset_ids)
        )
        purchased_at = None
        if purchased:
            evidence = next((
                item for item in answer.evidence
                if item.proves_ownership and item.offering_id == offering_id
            ), None)
            purchased_at = (
                evidence.details.get("purchasedAt") if evidence else None
            )
        teaser_asset_id = row.get("teaser_asset_id")
        return {
            "deliverableId": str(row["deliverable_id"]),
            "photoshootSessionId": str(row["photoshoot_session_id"]),
            "sellingMode": "BUNDLE",
            "bundleOfferingId": str(offering_id) if offering_id else None,
            "priceMinor": row.get("price_minor"),
            "currency": row.get("currency") or "USD",
            "purchased": purchased,
            "purchasedAt": purchased_at,
            "ownedAssetIds": list(owned_ids),
            "paidAssetIds": list(paid_ids),
            "totalPaidAssetCount": len(paid_ids),
            "ownedPaidAssetCount": len(owned_ids),
            "complete": bool(purchased and paid_set == frozenset(owned_ids)),
            "promotionalTeaserAssetId": (
                int(teaser_asset_id) if teaser_asset_id is not None else None
            ),
            "promotionalTeaserExcluded": (
                teaser_asset_id is None or int(teaser_asset_id) not in paid_set
            ),
            "ownershipState": answer.state.value,
        }

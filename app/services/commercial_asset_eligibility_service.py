"""Authoritative application boundary for canonical Asset commerce isolation."""

from app.repositories.asset_repository import AssetRepository
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.services.reference_asset_protection import require_commercially_eligible_asset


class CommercialAssetEligibilityService:
    def __init__(self, *, asset_repository=None, offering_repository=None) -> None:
        self.assets = asset_repository or AssetRepository()
        self.offerings = offering_repository or CommercialOfferingRepository()

    def require_asset(
        self, asset_id: int, *, creator_profile_id: int, connection=None,
    ):
        kwargs = {"connection": connection} if connection is not None else {}
        asset = self.assets.get_by_id(int(asset_id), **kwargs)
        if asset is None or int(asset.creator_profile_id or 0) != int(creator_profile_id):
            raise ValueError(f"Canonical Asset is unavailable: {asset_id}.")
        require_commercially_eligible_asset(asset, asset_id=int(asset_id))
        return asset

    def require_offering(self, offering, *, creator_profile_id: int, connection=None) -> None:
        if offering is None:
            raise ValueError("Commercial Offering is unavailable.")
        members = tuple(getattr(offering, "assets", ()) or ())
        if not members:
            raise ValueError("Commercial Offering has no assets.")
        for member in members:
            self.require_asset(
                int(member.asset_id), creator_profile_id=creator_profile_id,
                connection=connection,
            )

    def require_offering_id(
        self, offering_id, *, creator_profile_id: int, connection=None,
    ):
        offering = self.offerings.get(
            offering_id, creator_profile_id=creator_profile_id,
        )
        self.require_offering(
            offering, creator_profile_id=creator_profile_id, connection=connection,
        )
        return offering

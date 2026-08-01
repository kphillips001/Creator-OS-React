"""Read-only, creator-scoped Asset Lineage inspection adapter."""

from types import MappingProxyType

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from app.api.asset_library import _creator_profile
from app.services.asset_lineage_service import AssetLineageService


router = APIRouter(prefix="/api/v1/asset-lineage", tags=["asset-lineage"])


def _service() -> AssetLineageService:
    return AssetLineageService()


@router.get("/assets/{asset_id}")
def inspect_asset_lineage(asset_id: int):
    """Return canonical lineage diagnostics without mutating lineage state."""
    service = _service()
    creator_profile_id = int(_creator_profile()["id"])
    asset = service.assets.get_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Canonical Asset not found.")
    if int(getattr(asset, "creator_profile_id", 0) or 0) != creator_profile_id:
        # Do not reveal whether a cross-creator Asset exists.
        raise HTTPException(status_code=404, detail="Canonical Asset not found.")
    try:
        diagnostics = service.diagnostics(asset_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return jsonable_encoder(
        diagnostics,
        custom_encoder={type(MappingProxyType({})): dict},
    )

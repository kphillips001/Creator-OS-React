"""Narrow Asset Library HTTP presentation adapter for React."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.content_studio import _current_account_id
from app.models.asset_library import AssetLibraryFilter
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.asset_library_service import AssetLibraryService
from app.services.reference_library_service import ReferenceLibraryService


router = APIRouter(prefix="/api/v1/assets", tags=["asset-library"])


def _creator_profile() -> dict:
    account_id = _current_account_id()
    profile = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not profile or not int(profile.get("id") or 0):
        raise HTTPException(status_code=400, detail="Creator Profile required before using Asset Library.")
    return profile


def _canonical_asset_id(creator_profile_id: int) -> int | None:
    reference = ReferenceLibraryService().get_active_reference(
        creator_profile_id=int(creator_profile_id),
    )
    if reference is None or not bool(dict(reference.metadata or {}).get("canonical")):
        return None
    return int(reference.asset_id)


def _item_payload(item, *, canonical_asset_id: int | None) -> dict:
    return {
        "assetId": item.asset_id,
        "fileName": item.file_name,
        "mediaType": item.media_type,
        "classification": item.classification,
        "status": item.status,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "tags": list(item.tags),
        "themes": list(item.themes),
        "isReference": bool(item.is_reference_image),
        "isCanonicalReference": item.asset_id == canonical_asset_id,
        "mediaAvailable": bool(item.original_path),
        "imageUrl": f"/api/v1/assets/{item.asset_id}/media" if item.original_path else None,
    }


@router.get("")
def list_assets(
    search: str | None = None,
    media_type: str | None = None,
    classification: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(18, ge=1, le=60),
):
    profile = _creator_profile()
    creator_profile_id = int(profile["id"])
    service = AssetLibraryService()
    result = service.search_assets(AssetLibraryFilter(
        search=str(search or "").strip() or None,
        media_type=str(media_type or "").strip() or None,
        classification=str(classification or "").strip() or None,
        creator_profile_id=creator_profile_id,
        eligible_only=True,
        limit=5000,
    ))
    total = result.total
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    canonical_id = _canonical_asset_id(creator_profile_id)
    items = result.items[start:start + page_size]
    classifications = sorted({
        str(item.classification) for item in result.items if item.classification
    })
    return {
        "assets": [_item_payload(item, canonical_asset_id=canonical_id) for item in items],
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "classifications": classifications,
    }


@router.get("/{asset_id}")
def asset_details(asset_id: int):
    profile = _creator_profile()
    creator_profile_id = int(profile["id"])
    details = AssetLibraryService().get_asset_details(asset_id)
    if details is None or details.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Asset not found.")
    canonical_id = _canonical_asset_id(creator_profile_id)
    payload = _item_payload(details.item, canonical_asset_id=canonical_id)
    registration = dict((details.media_metadata or {}).get("asset_registration") or {})
    payload.update({
        "registrationSource": registration.get("source"),
        "mediaAvailable": bool(details.storage and details.storage.original_exists),
    })
    return payload


@router.get("/{asset_id}/media", response_class=FileResponse)
def asset_media(asset_id: int):
    profile = _creator_profile()
    details = AssetLibraryService().get_asset_details(asset_id)
    if details is None or details.creator_profile_id != int(profile["id"]):
        raise HTTPException(status_code=404, detail="Asset not found.")
    path_value = details.storage.original_path if details.storage else None
    path = Path(path_value).expanduser() if path_value else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Asset media is unavailable.")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )

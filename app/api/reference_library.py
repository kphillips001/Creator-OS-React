"""React Reference Library read API backed by the canonical reference service."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.reference_library_service import ReferenceLibraryService


router = APIRouter(prefix="/api/v1/reference-library", tags=["reference-library"])


def _active_profile() -> dict:
    account_id = _current_account_id()
    profile = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not int(profile.get("id") or 0):
        raise HTTPException(status_code=404, detail="Creator Profile required.")
    return profile


@router.get("/active")
def active_reference():
    profile = _active_profile()
    reference = ReferenceLibraryService().get_active_canonical_reference(
        creator_profile_id=int(profile["id"]),
    )
    if reference is None:
        return {"creator_profile_exists": True, "creator": {"id": int(profile["id"]), "name": str(profile.get("name") or profile.get("display_name") or "Creator")}, "active_reference": None}
    asset = reference.asset
    metadata = dict(reference.metadata or {})
    return {
        "creator_profile_exists": True,
        "creator": {"id": int(profile["id"]), "name": str(profile.get("name") or profile.get("display_name") or "Creator")},
        "active_reference": {
            "asset_id": reference.asset_id,
            "file_name": asset.file_name,
            "media_type": asset.media_type,
            "classification": asset.classification,
            "status": asset.status,
            "is_active": reference.is_active,
            "is_favorite": reference.is_favorite,
            "is_canonical": bool(metadata.get("canonical")),
            "is_protected": bool(metadata.get("protected")),
            "added_at": reference.added_at,
            "last_used_at": reference.last_used_at,
            "creator_profile_id": reference.creator_profile_id,
            "image_url": f"/api/v1/reference-library/active/image?v={reference.last_used_at or reference.asset_id}",
        },
    }


@router.get("/active/image", response_class=FileResponse)
def active_reference_image():
    profile = _active_profile()
    reference = ReferenceLibraryService().get_active_canonical_reference(
        creator_profile_id=int(profile["id"]),
    )
    if reference is None:
        raise HTTPException(status_code=404, detail="Active Reference Image not found.")
    path = Path(reference.asset.original_path or "").expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Active Reference Image file not found.")
    return FileResponse(path)

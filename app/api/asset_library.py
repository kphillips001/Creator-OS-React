"""Narrow Asset Library HTTP presentation adapter for React."""

from __future__ import annotations

import mimetypes
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from app.api.content_studio import _current_account_id
from app.models.asset_library import AssetLibraryFilter
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.asset_repository import AssetRepository
from app.services.asset_library_service import AssetLibraryService
from app.services.generation_library_service import GenerationLibraryService
from app.services.grid_thumbnail_service import GridThumbnailService
from app.services.reference_library_service import ReferenceLibraryService
from app.services.runtime_media_resolver import RuntimeMediaResolver
from app.services.staged_asset_registration_service import (
    StagedAssetRegistrationService,
)
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.creative_intelligence_learning_service import CreativeIntelligenceLearningService


router = APIRouter(prefix="/api/v1/assets", tags=["asset-library"])
logger = logging.getLogger(__name__)


def _creator_profile() -> dict:
    account_id = _current_account_id()
    profile = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not profile or not int(profile.get("id") or 0):
        raise HTTPException(status_code=400, detail="Creator Profile required before using Asset Library.")
    return profile


def _asset_repository() -> AssetRepository:
    return AssetRepository()


def _canonical_asset_id(creator_profile_id: int) -> int | None:
    return ReferenceLibraryService().get_active_canonical_asset_id(
        creator_profile_id=int(creator_profile_id),
    )


def _item_payload(item, *, canonical_asset_id: int | None) -> dict:
    return {
        "libraryItemId": f"asset:{item.asset_id}",
        "itemKind": "registered_asset",
        "assetId": item.asset_id,
        "generationId": None,
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
        "imageUrl": f"/api/v1/assets/{item.asset_id}/thumbnail" if item.original_path else None,
    }


@router.post("/staged/{generation_id}/register")
def register_staged_asset(generation_id: str):
    try:
        profile = _creator_profile()
        creator_profile_id = int(profile["id"])
        library = GenerationLibraryService()
        try:
            record = library.get(str(generation_id))
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Staged Asset was not found."
            ) from exc
        if record.creator_profile_id != creator_profile_id:
            raise HTTPException(status_code=404, detail="Staged Asset was not found.")
        result = StagedAssetRegistrationService(
            generation_library_service=library,
        ).register(record, creator_profile_id=creator_profile_id)
        if not result.success:
            raise HTTPException(status_code=409, detail=result.message)
        return {
            "success": True,
            "assetId": result.asset_id,
            "registrationId": result.registration_id,
            "generationId": generation_id,
            "alreadyRegistered": result.already_registered,
            "analysisStatus": result.analysis_status,
            "businessLifecycleState": result.business_lifecycle_state,
            "message": result.message,
        }
    except HTTPException:
        # FastAPI serializes HTTPException.detail as application/json.
        raise
    except Exception:
        logger.exception("Unexpected staged Asset registration failure")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "registration_failed",
                "detail": "Unable to register Business Asset due to an internal server error.",
            },
        )


@router.post("/staged/{generation_id}/archive")
def archive_staged_asset(generation_id: str):
    creator_profile_id = int(_creator_profile()["id"])
    library = GenerationLibraryService()
    try:
        record = library.get(generation_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Staged Asset was not found.") from error
    if record.creator_profile_id != creator_profile_id or record.status != "staged_asset_library":
        raise HTTPException(status_code=404, detail="Staged Asset was not found.")
    result = library.delete((generation_id,))
    if not result.success:
        raise HTTPException(status_code=409, detail="; ".join(result.errors))
    return {"success": True, "message": "Asset archived.", "generationId": generation_id}


def _staged_payload(record) -> dict:
    path = Path(record.output_reference).expanduser()
    available = path.is_file()
    return {
        "libraryItemId": f"generation:{record.image_id}",
        "itemKind": "staged_generation",
        "assetId": None,
        "generationId": record.image_id,
        "fileName": path.name,
        "mediaType": "image",
        "classification": None,
        "status": record.status,
        "createdAt": record.created_at or record.generation_date,
        "tags": [],
        "themes": [],
        "isReference": False,
        "isCanonicalReference": False,
        "mediaAvailable": available,
        "imageUrl": f"/api/v1/generation-library/{record.image_id}/thumbnail" if available else None,
        "registrationSource": None,
        "prompt": record.prompt_text,
        "provider": record.provider_id,
    }


def _photoshoot_payload(row: dict) -> dict:
    return {
        "libraryItemId": f"photoshoot:{row['deliverable_id']}",
        "itemKind": "photoshoot",
        "assetId": None,
        "generationId": None,
        "deliverableId": str(row["deliverable_id"]),
        "fileName": row.get("display_title") or row["display_name"],
        "description": row.get("display_description"),
        "mediaType": "photoshoot",
        "classification": None,
        "status": row["registration_state"],
        "createdAt": row.get("updated_at") or row["completed_at"],
        "tags": [], "themes": [], "isReference": False, "isCanonicalReference": False,
        "mediaAvailable": bool(row.get("hero_asset_id")),
        "imageUrl": f"/api/v1/assets/{row['hero_asset_id']}/thumbnail" if row.get("hero_asset_id") else None,
        "shotCount": int(row["shot_count"]),
        "registrationSource": "Photoshoot Gallery",
    }


def _asset_sort_timestamp(item: dict) -> float:
    value = item.get("createdAt")
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _merge_all_media_candidates(
    staged: list[dict],
    registered: list[dict],
    photoshoots: list[dict],
) -> list[dict]:
    """Return the complete source union without cross-source truncation."""
    return [*staged, *registered, *photoshoots]


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
    filters = AssetLibraryFilter(
        search=str(search or "").strip() or None,
        media_type=str(media_type or "").strip() or None,
        classification=str(classification or "").strip() or None,
        creator_profile_id=creator_profile_id,
        is_reference_image=False,
        eligible_only=True,
        limit=page_size,
    )
    staged_by_id = {}
    search_value = str(search or "").strip().lower()
    for record in GenerationLibraryService().list_records():
        if record.creator_profile_id != creator_profile_id or record.status != "staged_asset_library":
            continue
        if media_type and media_type != "image":
            continue
        if classification:
            continue
        haystack = " ".join((record.image_id, record.prompt_text, record.provider_id, record.creative_mode or "")).lower()
        if search_value and search_value not in haystack:
            continue
        staged_by_id[record.image_id] = _staged_payload(record)
    photoshoot_repository = PhotoshootCommerceRepository()
    include_photoshoots = (not media_type or media_type == "photoshoot") and not classification
    photoshoot_total = photoshoot_repository.count_asset_library(
        creator_profile_id, search=search_value or None
    ) if include_photoshoots else 0
    requested_candidate_limit = page * page_size
    registered_candidates, registered_total, classifications = (
        service.asset_library_grid_summary(
            filters, candidate_limit=requested_candidate_limit
        )
    )
    total = len(staged_by_id) + registered_total + photoshoot_total
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    candidate_limit = current_page * page_size
    if candidate_limit != requested_candidate_limit:
        registered_candidates, _, classifications = service.asset_library_grid_summary(
            filters, candidate_limit=candidate_limit
        )
    photoshoots = photoshoot_repository.list_asset_library(
        creator_profile_id,
        search=search_value or None,
        limit=candidate_limit,
    ) if include_photoshoots else ()
    staged_candidates = list(staged_by_id.values())
    registered_merge_candidates = [{
        "libraryItemId": f"asset:{row['id']}",
        "itemKind": "registered_asset_candidate",
        "assetId": int(row["id"]),
        "createdAt": row.get("created_at"),
    } for row in registered_candidates]
    photoshoot_candidates = [_photoshoot_payload(row) for row in photoshoots]
    combined = _merge_all_media_candidates(
        staged_candidates,
        registered_merge_candidates,
        photoshoot_candidates,
    )
    combined.sort(key=_asset_sort_timestamp, reverse=True)
    items = combined[start:start + page_size]
    selected_asset_ids = tuple(
        int(item["assetId"])
        for item in items
        if item["itemKind"] == "registered_asset_candidate"
    )
    canonical_id = _canonical_asset_id(creator_profile_id)
    registered_payloads = {
        item.asset_id: _item_payload(item, canonical_asset_id=canonical_id)
        for item in service.build_items_by_ids(selected_asset_ids)
    }
    items = [
        registered_payloads[item["assetId"]]
        if item["itemKind"] == "registered_asset_candidate"
        else item
        for item in items
        if item["itemKind"] != "registered_asset_candidate"
        or item["assetId"] in registered_payloads
    ]
    return {
        "assets": items,
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "classifications": classifications,
    }


@router.post("/photoshoots/{deliverable_id}/register")
def register_photoshoot_asset(deliverable_id: str):
    creator_profile_id = int(_creator_profile()["id"])
    try:
        row = PhotoshootCommerceDeliverableService().register(deliverable_id, creator_profile_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Photoshoot Asset was not found.") from error
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "success": True,
        "deliverableId": str(row["deliverable_id"]),
        "registrationState": row["registration_state"],
        "alreadyRegistered": row["registration_state"] == "REGISTERED",
        "message": "Photoshoot registered for Commerce.",
    }


@router.post("/photoshoots/{deliverable_id}/archive")
def archive_photoshoot_asset(deliverable_id: str):
    creator_profile_id = int(_creator_profile()["id"])
    repository = PhotoshootCommerceRepository()
    existing = repository.get(deliverable_id)
    members = (
        repository.members(str(existing["photoshoot_session_id"]))
        if existing and int(existing.get("creator_profile_id") or 0) == creator_profile_id
        else ()
    )
    row = repository.archive_asset_library(deliverable_id, creator_profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Active Photoshoot Asset was not found.")
    assets = AssetRepository()
    learner = CreativeIntelligenceLearningService()
    for member in members:
        asset = assets.get_by_id(int(member["asset_id"]))
        if asset is None:
            continue
        learner.record_negative_safely(
            creator_profile_id=creator_profile_id,
            image_reference=asset.local_vault_path or asset.file_path,
            event_type="archived",
            source_workflow="photoshoot",
            source_image_id=f"asset:{asset.id}",
            source_asset_id=asset.id,
            operational_metadata={
                "photoshoot_session_id": str(existing["photoshoot_session_id"]),
                "archive_reason": "photoshoot_archive",
            },
        )
    return {"success": True, "message": "Photoshoot archived.", "deliverableId": deliverable_id}


@router.post("/{asset_id}/archive")
def archive_registered_asset(asset_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    repository = AssetRepository()
    asset = repository.get_by_id(asset_id)
    row = repository.archive_asset_library_item(asset_id, creator_profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Active Asset was not found.")
    if asset is not None and int(asset.creator_profile_id or 0) == creator_profile_id:
        CreativeIntelligenceLearningService().record_negative_safely(
            creator_profile_id=creator_profile_id,
            image_reference=asset.local_vault_path or asset.file_path,
            event_type="archived",
            source_workflow="asset_library",
            source_image_id=f"asset:{asset.id}",
            source_asset_id=asset.id,
            operational_metadata={"archive_reason": "asset_library_archive"},
        )
    return {"success": True, "message": "Asset archived.", "assetId": asset_id}


@router.get("/archived")
def list_archived_assets():
    creator_profile_id = int(_creator_profile()["id"])
    service = AssetLibraryService()
    canonical_id = _canonical_asset_id(creator_profile_id)
    items = []
    for asset in AssetRepository().list_asset_library_archived(creator_profile_id):
        item = service.build_item(asset)
        payload = _item_payload(item, canonical_asset_id=canonical_id)
        payload["archivedAt"] = (asset.media_metadata or {}).get("asset_library_archive", {}).get("archived_at")
        items.append(payload)
    photoshoots = PhotoshootCommerceRepository().list_archived_asset_library(creator_profile_id)
    for row in photoshoots:
        items.append({**_photoshoot_payload(row), "archivedAt": row.get("archived_at")})
    library = GenerationLibraryService()
    for record in library.archive_service.list_records(archive_type="junk"):
        generation = dict(record.generation_record or {})
        if int(generation.get("creator_profile_id") or 0) != creator_profile_id:
            continue
        if generation.get("status") != "staged_asset_library":
            continue
        items.append({
            "libraryItemId": f"generation:{record.image_id}", "itemKind": "staged_generation",
            "assetId": None, "generationId": record.image_id, "deliverableId": None,
            "fileName": Path(record.current_file_path).name, "mediaType": "image",
            "classification": None, "status": "archived", "createdAt": generation.get("created_at"),
            "archivedAt": record.created_at, "tags": [], "themes": [], "isReference": False,
            "isCanonicalReference": False, "mediaAvailable": Path(record.current_file_path).is_file(),
            "imageUrl": f"/api/v1/generation-library/removed/{record.image_id}/media",
            "prompt": record.prompt_text or "", "provider": record.provider_id,
        })
    items.sort(key=lambda item: str(item.get("archivedAt") or ""), reverse=True)
    return {"items": items}


@router.post("/archived/assets/{asset_id}/restore")
def restore_registered_asset(asset_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    row = AssetRepository().restore_asset_library_item(asset_id, creator_profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Archived Asset was not found.")
    return {"success": True, "message": "Asset restored.", "assetId": asset_id}


@router.post("/archived/photoshoots/{deliverable_id}/restore")
def restore_photoshoot_asset(deliverable_id: str):
    creator_profile_id = int(_creator_profile()["id"])
    row = PhotoshootCommerceRepository().restore_asset_library(deliverable_id, creator_profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Archived Photoshoot was not found.")
    return {"success": True, "message": "Photoshoot restored.", "deliverableId": deliverable_id}


@router.post("/archived/staged/{generation_id}/restore")
def restore_staged_asset(generation_id: str):
    creator_profile_id = int(_creator_profile()["id"])
    library = GenerationLibraryService()
    archived = next((record for record in library.archive_service.list_records(archive_type="junk")
                     if record.image_id == generation_id
                     and int((record.generation_record or {}).get("creator_profile_id") or 0) == creator_profile_id
                     and (record.generation_record or {}).get("status") == "staged_asset_library"), None)
    if archived is None:
        raise HTTPException(status_code=404, detail="Archived Asset was not found.")
    restored = library.restore((generation_id,))
    if not restored.success:
        raise HTTPException(status_code=409, detail="; ".join(restored.errors))
    library.move_to_asset_library(generation_id)
    return {"success": True, "message": "Asset restored.", "generationId": generation_id}


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


@router.get("/{asset_id}/thumbnail", response_class=FileResponse)
def asset_thumbnail(asset_id: int):
    profile = _creator_profile()
    projection = _asset_repository().get_media_projection(asset_id)
    if projection is None or int(projection.get("creator_profile_id") or 0) != int(profile["id"]):
        raise HTTPException(status_code=404, detail="Asset not found.")
    source = RuntimeMediaResolver().resolve_original_path(projection, require_exists=True)
    if source is None or not source.is_file():
        raise HTTPException(status_code=404, detail="Asset media is unavailable.")
    try:
        path = GridThumbnailService().get_or_create(source, identity=f"asset-{asset_id}")
        media_type = "image/webp"
    except Exception:
        logger.exception("Asset thumbnail generation failed for Asset %s", asset_id)
        path = source
        media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )

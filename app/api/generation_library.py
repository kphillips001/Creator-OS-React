"""Generation Library workflow endpoints for React migration clients."""

from __future__ import annotations

import mimetypes
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.generation_library_service import GenerationLibraryService
from app.services.staged_asset_registration_service import StagedAssetRegistrationService
from app.services.asset_library_return_service import AssetLibraryReturnService, AssetReturnConflict
from app.services.grid_thumbnail_service import GridThumbnailService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.reference_library_service import ReferenceLibraryService
from app.models.generation_library import GENERATION_LIBRARY_PAGE_SIZE, GenerationLibraryFilter
from app.services.assembled_photoshoot_intake_service import AssembledPhotoshootIntakeService
from app.services.engagement_teaser_intake_service import EngagementTeaserIntakeService


router = APIRouter(prefix="/api/v1/generation-library", tags=["generation-library"])
logger = logging.getLogger(__name__)


class EditStudioHandoffResponse(BaseModel):
    success: bool
    message: str
    image_id: str
    status: str
    review_state: str
    source_image_url: str
    context_refresh: bool
    redirect: str


class PhotoshootHandoffResponse(BaseModel):
    success: bool
    message: str
    image_id: str
    session_id: str
    status: str
    context_refresh: bool
    redirect: str


class AssetVersionResponse(BaseModel):
    generation_library_record_id: str
    version_number: int
    is_current: bool
    approval_timestamp: str | None
    provider_id: str
    prompt: str
    prompt_plan_id: str
    generation_metadata: dict
    original_file_path: str
    archived_file_path: str | None
    edit_source: str
    image_url: str


class AssetVersionHistoryResponse(BaseModel):
    generation_library_record_id: str
    current_version: int
    versions: list[AssetVersionResponse]


class AssetVersionRestoreResponse(BaseModel):
    success: bool
    message: str
    updated_current: dict
    version_history: AssetVersionHistoryResponse


class PermanentDeleteRequest(BaseModel):
    confirmed: bool = False


class PostingStageRequest(BaseModel):
    is_staged: bool


class ContentClassificationRequest(BaseModel):
    classification: Literal["SFW", "NSFW"]


class BulkContentClassificationRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=100)
    classification: Literal["SFW", "NSFW"]

    @field_validator("image_ids")
    @classmethod
    def validate_image_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("Image IDs must not be empty.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate image IDs are not allowed.")
        return normalized


class BulkArchiveRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("image_ids")
    @classmethod
    def validate_image_ids(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("Image IDs must not be empty.")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate image IDs are not allowed.")
        return normalized


class AssetLibraryMoveResponse(BaseModel):
    success: bool
    generation_id: str
    already_moved: bool
    status: str
    message: str
    asset_id: int | None = None
    analysis_status: str | None = None


class AssembledPhotoshootImportRequest(BaseModel):
    imageIds: list[str]
    heroImageId: str | None = None
    idempotencyKey: str | None = None


@router.post("/photoshoots/import", status_code=202)
def import_generation_library_photoshoot(request: AssembledPhotoshootImportRequest):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before creating a Photoshoot.")
    try:
        intake, operation, created = AssembledPhotoshootIntakeService().create(
            creator_profile_id=creator_profile_id,
            account_id=_current_account_id(),
            image_ids=request.imageIds,
            hero_image_id=request.heroImageId,
            idempotency_key=request.idempotencyKey,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "intakeId": str(intake["intake_id"]),
        "operationId": str(operation.operation_id),
        "operationStatus": operation.status,
        "created": bool(created),
        "deliverableId": str(intake["deliverable_id"]) if intake.get("deliverable_id") else None,
        "sourceKind": "GENERATION_LIBRARY_IMPORT",
    }


def _record_payload(record, eligibility=None) -> dict:
    payload = asdict(record)
    payload["image_url"] = f"/api/v1/generation-library/{record.image_id}/media?v={record.updated_at or record.generation_date}"
    payload["canRegenerate"] = bool(eligibility and eligibility.can_regenerate)
    payload["regenerationIneligibilityReason"] = (
        eligibility.reason if eligibility and not eligibility.can_regenerate else None
    )
    return payload


def _card_payload(record, eligibility=None) -> dict:
    version = record.updated_at or record.generation_date
    return {
        "image_id": record.image_id,
        "image_url": f"/api/v1/generation-library/{record.image_id}/thumbnail?v={version}",
        "media_url": f"/api/v1/generation-library/{record.image_id}/media?v={version}",
        "provider_id": record.provider_id,
        "creative_mode": record.creative_mode,
        "generation_date": record.generation_date,
        "status": record.status,
        "is_staged": record.is_staged,
        "staged_at": record.staged_at,
        "content_classification": record.content_classification,
        "classification_source": record.classification_source,
        "creator_profile_id": record.creator_profile_id,
        "canRegenerate": bool(eligibility and eligibility.can_regenerate),
        "regenerationIneligibilityReason": (
            eligibility.reason if eligibility and not eligibility.can_regenerate else None
        ),
    }


def _removed_record(library: GenerationLibraryService, image_id: str):
    try:
        record = library.archive_service.get_latest(image_id, archive_type="junk")
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Removed content not found.") from error
    creator_profile_id = _creator_profile_id()
    owner_id = int(dict(record.generation_record or {}).get("creator_profile_id") or 0)
    if creator_profile_id and owner_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Removed content not found.")
    return record


@router.get("")
def browse_generation_library(
    search: str | None = None,
    contentOrigin: Literal["SFW", "NSFW", "UNCLASSIFIED"] | None = None,
    provider: str | None = None,
    mode: str | None = None,
    sort: str = "newest",
    page: int = Query(1, ge=1),
):
    library = GenerationLibraryService()
    filters = GenerationLibraryFilter(
        search=search,
        content_origin=contentOrigin,
        provider_id=provider,
        creative_mode=mode,
        creator_profile_id=_creator_profile_id() or None,
        sort=sort,
    )
    page_size = GENERATION_LIBRARY_PAGE_SIZE
    browse_result = library.browse_page(filters, page=page, page_size=page_size)
    page_records, total, providers, modes = browse_result[:4]
    total_pages = browse_result[4] if len(browse_result) > 4 else max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    from app.services.regeneration_eligibility_service import RegenerationEligibilityService
    eligibility_service = RegenerationEligibilityService(generation_library=library)
    recipe_records = tuple(record for record in page_records if record.generation_recipe_id)
    eligibility = eligibility_service.inspect_many(
        recipe_records, creator_profile_id=_creator_profile_id() or None,
    )
    return {
        "records": [_card_payload(record, eligibility.get(record.image_id)) for record in page_records],
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "providers": list(providers),
        "modes": list(modes),
    }


@router.get("/{generated_image_id}")
def generation_library_details(generated_image_id: str):
    library = GenerationLibraryService()
    try:
        record = library.get_with_effective_classification(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    creator_profile_id = _creator_profile_id()
    if creator_profile_id and record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    return _record_payload(record)


@router.patch("/{generated_image_id}/content-classification")
def classify_generation_content(generated_image_id: str, request: ContentClassificationRequest):
    library = GenerationLibraryService()
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before classifying an image.")
    try:
        record = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    try:
        result = library.classify_content(
            generated_image_id, creator_profile_id=creator_profile_id,
            classification=request.classification,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"image_id": generated_image_id,
            "content_classification": result["content_classification"],
            "classification_source": result["classification_source"]}


@router.patch("/content-classification/bulk")
def bulk_classify_generation_content(request: BulkContentClassificationRequest):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before classifying images.")
    try:
        rows = GenerationLibraryService().bulk_classify_content(
            request.image_ids, creator_profile_id=creator_profile_id,
            classification=request.classification,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    count = len(rows)
    return {"image_ids": [row["image_id"] for row in rows],
            "content_classification": request.classification,
            "classification_source": "MANUAL", "classified_count": count}


@router.post("/archive/bulk")
def bulk_archive_generation_content(request: BulkArchiveRequest):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before archiving images.")
    try:
        result = GenerationLibraryService().bulk_archive_unclassified(
            request.image_ids, creator_profile_id=creator_profile_id,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {"image_ids": list(result.image_ids), "archived_count": len(result.image_ids),
            "message": result.message}


@router.put("/{generated_image_id}/posting-stage")
def update_generation_posting_stage(generated_image_id: str, request: PostingStageRequest):
    library = GenerationLibraryService()
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before staging an image.")
    try:
        record = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    try:
        updated = library.set_posting_stage(generated_image_id, staged=request.is_staged)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return _record_payload(updated)


@router.get("/{generated_image_id}/media", response_class=FileResponse)
def generation_library_media(generated_image_id: str):
    library = GenerationLibraryService()
    try:
        record = library.projected_get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if _creator_profile_id() and record.creator_profile_id != _creator_profile_id():
        raise HTTPException(status_code=404, detail="Generated image not found.")
    path = Path(record.output_reference).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Generated image media is unavailable.")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@router.get("/{generated_image_id}/thumbnail", response_class=FileResponse)
def generation_library_thumbnail(generated_image_id: str):
    library = GenerationLibraryService()
    try:
        record = library.projected_get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    creator_profile_id = _creator_profile_id()
    if creator_profile_id and record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    source = Path(record.output_reference).expanduser()
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Generated image media is unavailable.")
    try:
        path = GridThumbnailService().get_or_create(
            source,
            identity=f"generation-{generated_image_id}",
        )
        media_type = "image/webp"
    except Exception:
        logger.exception(
            "Generation Library thumbnail failed for %s", generated_image_id
        )
        path = source
        media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.get("/{generated_image_id}/preview", response_class=FileResponse)
def generation_library_preview(generated_image_id: str):
    library = GenerationLibraryService()
    try:
        record = library.projected_get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    creator_profile_id = _creator_profile_id()
    if creator_profile_id and record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    source = Path(record.output_reference).expanduser()
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Generated image media is unavailable.")
    try:
        path = GridThumbnailService().get_or_create_preview(source, identity=f"generation-{generated_image_id}")
    except Exception as error:
        logger.exception("Generation Library preview failed for %s", generated_image_id)
        raise HTTPException(status_code=422, detail="Generated image preview is unavailable.") from error
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})


@router.post("/{generated_image_id}/remove")
def remove_generation_content(generated_image_id: str):
    library = GenerationLibraryService()
    try:
        record = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if _creator_profile_id() and record.creator_profile_id != _creator_profile_id():
        raise HTTPException(status_code=404, detail="Generated image not found.")
    result = library.delete((generated_image_id,))
    if not result.success:
        raise HTTPException(status_code=409, detail="; ".join(result.errors))
    return {"success": True, "message": result.message, "image_id": generated_image_id}


@router.get("/removed/items")
def removed_generation_content():
    library = GenerationLibraryService()
    creator_profile_id = _creator_profile_id()
    items = []
    for record in library.archive_service.list_records(archive_type="junk"):
        generation = dict(record.generation_record or {})
        if creator_profile_id and int(generation.get("creator_profile_id") or 0) != creator_profile_id:
            continue
        items.append({
            "archiveId": record.archive_id,
            "generationLibraryId": record.image_id,
            "removedAt": record.created_at,
            "provider": record.provider_id,
            "prompt": record.prompt_text or "",
            "mediaUrl": f"/api/v1/generation-library/removed/{record.image_id}/media?v={record.updated_at or record.created_at}",
        })
    return {"items": items}


@router.get("/removed/{generated_image_id}/media", response_class=FileResponse)
def removed_generation_media(generated_image_id: str):
    library = GenerationLibraryService()
    record = _removed_record(library, generated_image_id)
    path = Path(record.current_file_path).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Removed media is unavailable.")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@router.post("/removed/{generated_image_id}/restore")
def restore_removed_generation(generated_image_id: str):
    library = GenerationLibraryService()
    _removed_record(library, generated_image_id)
    result = library.restore((generated_image_id,))
    if not result.success:
        raise HTTPException(status_code=409, detail="; ".join(result.errors))
    return {"success": True, "message": "Content restored to the Generation Library.", "image_id": generated_image_id}


@router.post("/removed/{generated_image_id}/permanent-delete")
def permanently_delete_removed_generation(generated_image_id: str, request: PermanentDeleteRequest):
    if not request.confirmed:
        raise HTTPException(status_code=400, detail="Permanent deletion requires confirmation.")
    library = GenerationLibraryService()
    _removed_record(library, generated_image_id)
    library.archive_service.permanent_delete_junk(generated_image_id)
    return {"success": True, "message": "Content permanently deleted.", "image_id": generated_image_id}


def _creator_profile_id() -> int:
    account_id = _current_account_id()
    profile = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    return int(profile.get("id") or 0)


@router.post("/{generated_image_id}/move-to-asset-library", response_model=AssetLibraryMoveResponse)
def move_generation_to_asset_library(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before using Asset Library.")
    library = GenerationLibraryService()
    try:
        record = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    try:
        if record.status == "business_asset_registered":
            moved, already_moved = record, True
        else:
            moved, already_moved = library.move_to_asset_library(record.image_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    try:
        result = StagedAssetRegistrationService(
            generation_library_service=library,
        ).register(moved, creator_profile_id=creator_profile_id)
    except Exception as error:
        logger.exception("Canonical Asset intelligence dispatch failed")
        raise HTTPException(
            status_code=409,
            detail="Asset registration was saved, but intelligence could not start. Retry Move to Asset Library.",
        ) from error
    if not result.success or result.asset_id is None:
        raise HTTPException(status_code=409, detail=result.message or "Asset registration failed.")
    return {
        "success": True,
        "generation_id": moved.image_id,
        "already_moved": bool(already_moved or result.already_registered),
        "status": "analyzing" if result.analysis_status != "READY" else "ready",
        "asset_id": result.asset_id,
        "analysis_status": result.analysis_status,
        "message": result.message,
    }


@router.post("/{generated_image_id}/add-to-teasers", response_model=AssetLibraryMoveResponse)
def add_generation_to_teasers(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before adding a Teaser.")
    try:
        result = EngagementTeaserIntakeService().add(
            generated_image_id, creator_profile_id=creator_profile_id,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        logger.exception("Engagement Teaser intake failed")
        raise HTTPException(
            status_code=409,
            detail="Teaser intake could not finish. Retry Add to Teasers.",
        ) from error
    return {
        "success": True,
        "generation_id": result.generation_id,
        "already_moved": result.already_registered,
        "status": "analyzing" if result.analysis_status != "READY" else "ready",
        "asset_id": result.asset_id,
        "analysis_status": result.analysis_status,
        "message": "Added to Teasers. Asset Intelligence is ready." if result.analysis_status == "READY" else "Added to Teasers. Asset Intelligence is analyzing.",
    }


@router.post("/{generated_image_id}/move-back-to-generation-library", response_model=AssetLibraryMoveResponse)
def move_generation_back_to_generation_library(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before using Generation Library.")
    library = GenerationLibraryService()
    try:
        record = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Staged generation not found.") from error
    if record.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Staged generation not found.")
    if record.status == "staged_asset_library":
        try:
            moved, already_moved = library.move_back_to_generation_library(record.image_id)
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "success": True, "generation_id": moved.image_id,
            "already_moved": already_moved, "status": moved.status,
            "message": "Image moved back to Generation Library.",
        }
    try:
        result = AssetLibraryReturnService(generation_library=library).return_single_image(
            record.image_id, creator_profile_id=creator_profile_id)
        moved = library.get(record.image_id)
    except AssetReturnConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        logger.exception("Asset Library return failed for %s", generated_image_id)
        raise HTTPException(status_code=409, detail="Unable to return image safely. No lifecycle changes were retained.") from error
    return {
        "success": True,
        "generation_id": moved.image_id,
        "already_moved": False,
        "status": moved.status,
        "asset_id": result.asset_id,
        "message": "Image returned to Generation Library. Asset Intelligence was removed.",
    }


@router.post("/{generated_image_id}/edit", response_model=EditStudioHandoffResponse)
def send_generation_to_edit_studio(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before editing.")

    library = GenerationLibraryService()
    try:
        selected = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if selected.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")

    if selected.status not in {"active", "pending_edit"}:
        raise HTTPException(status_code=400, detail="Generated image is not available for editing.")

    pending_records = sorted(
        (
            record
            for record in library.list_records()
            if record.creator_profile_id == creator_profile_id
            and record.status == "pending_edit"
            and record.image_id != selected.image_id
        ),
        key=lambda record: (record.updated_at or record.created_at or "", record.image_id),
        reverse=True,
    )
    for current in pending_records:
        candidates = (
            record
            for record in library.list_records()
            if record.status == "edit_candidate"
            and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == current.image_id
        )
        for candidate in candidates:
            discarded = library.discard_edit_candidate(candidate.image_id)
            if not discarded.success:
                raise HTTPException(status_code=400, detail="; ".join(discarded.errors) or discarded.message)
        restored = library.return_pending_edit_to_library(current.image_id)
        if not restored.success:
            raise HTTPException(status_code=400, detail="; ".join(restored.errors) or restored.message)

    try:
        pending = library.send_to_pending_edit(selected.image_id)
    except (KeyError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "success": True,
        "message": "Image opened in Edit Studio.",
        "image_id": pending.image_id,
        "status": pending.status,
        "review_state": pending.review_state,
        "source_image_url": (
            f"/api/v1/edit-studio/pending-source/image"
            f"?image_id={pending.image_id}&v={pending.updated_at or pending.generation_date}"
        ),
        "context_refresh": True,
        "redirect": "/content/edit",
    }


def _resolve_photoshoot_session(queue: PhotoshootQueueService, library: GenerationLibraryService, session) -> None:
    continuity = dict(session.creative_continuity or {})
    seed_id = str(continuity.get("seed_image_id") or "")
    seed_request = next((
        request for request in queue.requests_for_session(session.session_id)
        if bool(dict(request.metadata or {}).get("is_seed_image"))
    ), None)
    if seed_request is not None and seed_request.status != "returned_to_library":
        queue.return_seed_request_to_library(seed_request.request_id, notes="Replaced by a new Generation Library seed.")
    if seed_id:
        restored = library.return_photoshoot_seed_to_library(seed_id)
        if not restored.success:
            raise HTTPException(status_code=409, detail="; ".join(restored.errors) or restored.message)
    if session.status not in {"completed", "cancelled"}:
        queue.cancel_session(session.session_id)


@router.post("/{generated_image_id}/photoshoot", response_model=PhotoshootHandoffResponse)
def send_generation_to_photoshoot(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before starting a Photoshoot.")

    library = GenerationLibraryService()
    queue = PhotoshootQueueService()
    try:
        selected = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if selected.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    if selected.status not in {"active", "pending_photoshoot"}:
        raise HTTPException(status_code=400, detail="Generated image is not available for Photoshoot Studio.")

    matching_session = None
    for session in queue.list_sessions(creator_profile_id=creator_profile_id):
        if session.status in {"completed", "cancelled", "junked"}:
            continue
        seed_id = str(dict(session.creative_continuity or {}).get("seed_image_id") or "")
        if seed_id == selected.image_id:
            matching_session = session
        else:
            _resolve_photoshoot_session(queue, library, session)

    for pending_record in tuple(library.list_records()):
        if (pending_record.creator_profile_id == creator_profile_id
                and pending_record.status == "pending_photoshoot"
                and pending_record.image_id != selected.image_id):
            restored = library.return_photoshoot_seed_to_library(pending_record.image_id)
            if not restored.success:
                raise HTTPException(status_code=409, detail="; ".join(restored.errors) or restored.message)

    try:
        pending = library.send_to_pending_photoshoot(selected.image_id)
        frozen = dict((matching_session.creative_continuity or {}).get("canonical_identity_reference") or {}) if matching_session else {}
        if frozen:
            identity_reference = frozen
        else:
            canonical = ReferenceLibraryService().get_active_canonical_reference(
                creator_profile_id=creator_profile_id,
            )
            if canonical is None or not str(canonical.asset.original_path or "").strip():
                raise ValueError("An active canonical identity reference is required to start a Photoshoot.")
            identity_reference = {
                "asset_id": canonical.asset_id,
                "path": canonical.asset.original_path,
            }
        session, _created = queue.start_studio_session_from_generated_image(
            pending,
            canonical_identity_reference=identity_reference,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        logger.exception("Photoshoot handoff failed for %s", generated_image_id)
        raise HTTPException(status_code=409, detail="Generation Library handoff failed.") from error

    if matching_session is not None and session.session_id != matching_session.session_id:
        raise HTTPException(status_code=409, detail="Photoshoot session did not match the selected image.")
    return {
        "success": True,
        "message": "Image opened in Photoshoot Studio.",
        "image_id": pending.image_id,
        "session_id": session.session_id,
        "status": pending.status,
        "context_refresh": True,
        "redirect": "/content/photoshoot",
    }


@router.get("/{generated_image_id}/versions", response_model=AssetVersionHistoryResponse)
def generation_asset_versions(generated_image_id: str):
    creator_profile_id = _creator_profile_id()
    library = GenerationLibraryService()
    try:
        current = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if current.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    archived = library.archive_service.list_asset_versions(current.image_id)
    archived_max = max(
        (int(item.metadata.get("version_number") or 0) for item in archived),
        default=0,
    )
    current_metadata = dict(current.generation_metadata or {})
    current_version = max(1, int(current_metadata.get("asset_version") or 0), archived_max + 1)
    versions = [{
        "generation_library_record_id": current.image_id,
        "version_number": current_version,
        "is_current": True,
        "approval_timestamp": current_metadata.get("edit_approved_at"),
        "provider_id": current.provider_id,
        "prompt": current.prompt_text,
        "prompt_plan_id": current.prompt_plan_id,
        "generation_metadata": current_metadata,
        "original_file_path": current.output_reference,
        "archived_file_path": None,
        "edit_source": str(current_metadata.get("approved_from") or "current_generation"),
        "image_url": f"/api/generation-library/media/{current.image_id}?v={current_version}",
    }]
    versions.extend({
        "generation_library_record_id": item.image_id,
        "version_number": int(item.metadata.get("version_number") or 0),
        "is_current": False,
        "approval_timestamp": item.metadata.get("approval_timestamp"),
        "provider_id": item.provider_id,
        "prompt": str(item.prompt_text or ""),
        "prompt_plan_id": str(item.metadata.get("prompt_plan_id") or ""),
        "generation_metadata": dict(item.metadata.get("generation_metadata") or {}),
        "original_file_path": str(item.metadata.get("original_file_path") or item.original_output_reference),
        "archived_file_path": item.current_file_path,
        "edit_source": str(item.metadata.get("edit_source") or "edit_studio"),
        "image_url": f"/api/v1/generation-library/{current.image_id}/versions/{int(item.metadata.get('version_number') or 0)}/media",
    } for item in archived)
    return {
        "generation_library_record_id": current.image_id,
        "current_version": current_version,
        "versions": versions,
    }


@router.get("/{generated_image_id}/versions/{version_number}/media", response_class=FileResponse)
def generation_asset_version_media(generated_image_id: str, version_number: int):
    creator_profile_id = _creator_profile_id()
    library = GenerationLibraryService()
    try:
        current = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if current.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    archived = next((
        item
        for item in library.archive_service.list_asset_versions(current.image_id)
        if int(item.metadata.get("version_number") or 0) == int(version_number)
    ), None)
    if archived is None:
        raise HTTPException(status_code=404, detail="Archived asset version not found.")
    path = Path(archived.current_file_path).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Archived asset version media is unavailable.")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=31536000, immutable"},
    )


@router.post(
    "/{generated_image_id}/versions/{version_number}/restore",
    response_model=AssetVersionRestoreResponse,
)
def restore_generation_asset_version(generated_image_id: str, version_number: int):
    creator_profile_id = _creator_profile_id()
    library = GenerationLibraryService()
    try:
        current = library.get(generated_image_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Generated image not found.") from error
    if current.creator_profile_id != creator_profile_id:
        raise HTTPException(status_code=404, detail="Generated image not found.")
    try:
        restored = library.restore_asset_version(
            image_id=generated_image_id,
            version_number=version_number,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Archived asset version not found.") from error
    except FileNotFoundError as error:
        logger.exception("Version restore media is missing for %s version %s", generated_image_id, version_number)
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Exception as error:
        logger.exception("Version restore failed for %s version %s", generated_image_id, version_number)
        raise HTTPException(status_code=500, detail="Version restore failed. The current version remains unchanged.") from error

    history = generation_asset_versions(generated_image_id)
    updated_current = asdict(restored)
    updated_current["image_url"] = (
        f"/api/generation-library/media/{restored.image_id}"
        f"?v={int(restored.generation_metadata.get('asset_version') or 1)}"
    )
    return {
        "success": True,
        "message": f"Version {version_number} restored as a new current version.",
        "updated_current": updated_current,
        "version_history": history,
    }

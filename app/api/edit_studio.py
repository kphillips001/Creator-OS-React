"""Edit Studio HTTP API."""

from __future__ import annotations

import mimetypes
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.models.generation_engine import GenerationStatus
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.edit_studio_context_service import EditStudioContextService
from app.services.edit_studio_service import EditStudioService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.reference_library_service import ReferenceLibraryService


router = APIRouter(prefix="/api/v1/edit-studio", tags=["edit-studio"])


class EditStudioProviderResponse(BaseModel):
    value: str
    label: str


class PendingSourceResponse(BaseModel):
    image_id: str
    image_url: str
    provider_id: str
    prompt_text: str
    creative_mode: str | None
    generation_date: str
    status: str
    generation_job_id: str
    generation_request_id: str
    generation_result_id: str
    prompt_plan_id: str
    reference_asset_id: int | None
    imported_asset_id: int | None
    provider_metadata: dict
    prompt_metadata: dict
    generation_metadata: dict


class EditStudioContextResponse(BaseModel):
    creator_profile_exists: bool
    pending_source: PendingSourceResponse | None
    candidate: PendingSourceResponse | None = None
    providers: list[EditStudioProviderResponse]


class EditStudioReferenceResponse(BaseModel):
    asset_id: int
    label: str
    preview_url: str


class EditStudioReferenceInput(BaseModel):
    role: Literal[
        "Wardrobe", "Hair", "Pose", "Environment", "Lighting",
        "Makeup", "Accessories", "Style", "Other",
    ] = "Other"
    source: Literal["reference_library", "upload"]
    asset_id: int


class GenerateEditRequest(BaseModel):
    source_image_id: str
    original_source_image_id: str | None = None
    edit_mode: Literal["single_image", "multi_image"]
    provider_id: str
    prompt: str
    references: list[EditStudioReferenceInput] = Field(default_factory=list)


class EditStudioActionResponse(BaseModel):
    success: bool
    message: str


class GenerateEditResponse(EditStudioActionResponse):
    edit_request_id: str
    generation_job_id: str
    generation_status: str
    candidate_image_ids: list[str]


class EditGenerationStatusResponse(BaseModel):
    generation_job_id: str
    generation_status: str
    provider_id: str
    candidate: PendingSourceResponse | None = None
    error: str | None = None


class EditCandidateActionRequest(BaseModel):
    candidate_image_id: str


class EditAgainResponse(EditStudioActionResponse):
    working_source: PendingSourceResponse


class ApproveEditResponse(EditStudioActionResponse):
    updated_record: PendingSourceResponse


def _creator_profile() -> dict:
    account_id = _current_account_id()
    return get_active_creator_profile(str(account_id)) if account_id is not None else {}


def _record_payload(record, *, image_url: str) -> dict:
    payload = EditStudioContextService._pending_source_payload(record)
    payload["image_url"] = image_url
    return payload


def _candidate_for_pending(library: GenerationLibraryService, candidate_id: str, source_id: str):
    try:
        candidate = library.get(candidate_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Edit candidate not found.") from error
    metadata = dict(candidate.generation_metadata or {})
    if candidate.status != "edit_candidate" or metadata.get("edit_pending_source_image_id") != source_id:
        raise HTTPException(status_code=400, detail="Edit candidate does not belong to the pending source.")
    return candidate


def _execute_edit_generation(*, job_id: str, pending_source_image_id: str) -> None:
    engine = GenerationEngineService()
    library = GenerationLibraryService()
    executed = engine.dispatch_job(job_id)
    if executed.status != GenerationStatus.SUCCEEDED.value:
        return
    for record in library.sync_job(executed):
        library.mark_edit_candidate(
            record.image_id,
            pending_source_image_id=pending_source_image_id,
        )


@router.get("/context", response_model=EditStudioContextResponse)
def edit_studio_context(response: Response):
    response.headers["Cache-Control"] = "no-store"
    profile = _creator_profile()
    result = EditStudioContextService().read(creator_profile=profile)
    source = result.get("pending_source")
    candidate = None
    if source:
        record = GenerationLibraryService().latest_edit_candidate_for_source(source["image_id"])
        if record:
            candidate = _record_payload(record, image_url=f"/api/v1/edit-studio/candidates/{record.image_id}/image")
    return {**result, "candidate": candidate}


@router.get("/references", response_model=list[EditStudioReferenceResponse])
def edit_studio_references():
    creator_profile_id = int(_creator_profile().get("id") or 0)
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before editing.")
    return EditStudioContextService().creative_references(
        creator_profile_id=creator_profile_id,
    )


@router.get("/references/{asset_id}/image", response_class=FileResponse)
def edit_studio_reference_image(asset_id: int):
    reference = ReferenceLibraryService().get_reference(asset_id)
    creator_profile_id = int(_creator_profile().get("id") or 0)
    if reference is None or reference.creator_profile_id not in (None, creator_profile_id):
        raise HTTPException(status_code=404, detail="Reference image not found.")
    path = Path(reference.asset.preview_path or reference.asset.original_path or "").expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Reference image is unavailable.")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


@router.post("/references/upload", response_model=EditStudioReferenceResponse)
async def edit_studio_upload_reference(image: UploadFile = File(...)):
    creator_profile_id = int(_creator_profile().get("id") or 0)
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before editing.")
    suffix = Path(image.filename or "reference.png").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Reference image must be JPG, PNG, or WebP.")
    staged_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as staged:
            staged_path = Path(staged.name)
            while chunk := await image.read(1024 * 1024):
                staged.write(chunk)
        result = ReferenceLibraryService().add_reference(
            media_path=staged_path,
            original_filename=image.filename,
            creator_profile_id=creator_profile_id,
            favorite=False,
            make_active=False,
        )
        if not result.success or not result.asset_id:
            raise HTTPException(status_code=400, detail=result.message)
        return {
            "asset_id": result.asset_id,
            "label": image.filename or f"Reference {result.asset_id}",
            "preview_url": f"/api/v1/edit-studio/references/{result.asset_id}/image",
        }
    finally:
        if staged_path is not None:
            staged_path.unlink(missing_ok=True)


@router.post("/return-to-library", response_model=EditStudioActionResponse)
def edit_studio_return_to_library():
    creator_profile_id = int(_creator_profile().get("id") or 0)
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=creator_profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Pending Edit Studio source not found.")
    candidates = tuple(
        record
        for record in library.list_records()
        if record.status == "edit_candidate"
        and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == source.image_id
    )
    for candidate in candidates:
        discarded = library.discard_edit_candidate(candidate.image_id)
        if not discarded.success:
            raise HTTPException(status_code=400, detail="; ".join(discarded.errors) or discarded.message)
    result = library.return_pending_edit_to_library(source.image_id)
    if not result.success:
        raise HTTPException(status_code=400, detail="; ".join(result.errors) or result.message)
    return {"success": True, "message": result.message}


@router.post("/generate", response_model=GenerateEditResponse)
def edit_studio_generate(request: GenerateEditRequest, background_tasks: BackgroundTasks):
    profile = _creator_profile()
    creator_profile_id = int(profile.get("id") or 0)
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before editing.")
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=creator_profile_id)
    original_source_id = request.original_source_image_id or request.source_image_id
    if source is None or source.image_id != original_source_id:
        raise HTTPException(status_code=400, detail="Selected Edit Studio source is no longer pending.")
    try:
        working_source = library.get(request.source_image_id)
    except KeyError as error:
        raise HTTPException(status_code=400, detail="Selected editing source is unavailable.") from error
    if working_source.image_id != source.image_id:
        _candidate_for_pending(library, working_source.image_id, source.image_id)
    engine = GenerationEngineService()
    edit_service = EditStudioService()
    references = [reference.model_dump() for reference in request.references]
    reference_service = ReferenceLibraryService()
    for reference_input in references:
        reference = reference_service.get_reference(reference_input["asset_id"])
        if reference is None or reference.creator_profile_id not in (None, creator_profile_id):
            raise HTTPException(status_code=400, detail="Selected reference image is unavailable.")
    first_reference_asset_id = references[0]["asset_id"] if references else None
    try:
        edit_item, job = edit_service.create_edit_request(
            creator_profile=profile,
            source_image_ids=(working_source.image_id,),
            edit_mode=request.edit_mode,
            edit_prompt=request.prompt,
            provider_id=request.provider_id,
            generation_library=library,
            generation_engine=engine,
            reference_asset_id=first_reference_asset_id,
            references=references,
            batch_size=1,
        )
    except (KeyError, ValueError, RuntimeError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    background_tasks.add_task(
        _execute_edit_generation,
        job_id=job.job_id,
        pending_source_image_id=source.image_id,
    )
    return {
        "success": True,
        "message": "Edit generation started.",
        "edit_request_id": edit_item.edit_request_id,
        "generation_job_id": job.job_id,
        "generation_status": job.status,
        "candidate_image_ids": [],
    }


@router.get("/generation/{job_id}", response_model=EditGenerationStatusResponse)
def edit_studio_generation_status(job_id: str):
    profile_id = int(_creator_profile().get("id") or 0)
    engine = GenerationEngineService()
    library = GenerationLibraryService()
    try:
        job = engine.get_job(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Edit generation job not found.") from error
    if job.request.creator_profile_id != profile_id or job.request.metadata.get("source") != "edit_studio":
        raise HTTPException(status_code=404, detail="Edit generation job not found.")
    source_ids = tuple(job.request.metadata.get("source_image_ids") or ())
    pending_source_id = str(job.request.metadata.get("edit_pending_source_image_id") or "")
    if not pending_source_id:
        pending = library.pending_edit_record(creator_profile_id=profile_id)
        pending_source_id = pending.image_id if pending else (str(source_ids[0]) if source_ids else "")
    candidate = next((
        record
        for record in library.list_records()
        if record.status == "edit_candidate"
        and record.generation_job_id == job.job_id
        and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == pending_source_id
    ), None)
    return {
        "generation_job_id": job.job_id,
        "generation_status": job.status,
        "provider_id": job.request.provider_id,
        "candidate": _record_payload(candidate, image_url=f"/api/v1/edit-studio/candidates/{candidate.image_id}/image") if candidate else None,
        "error": job.failure.reason if job.failure else None,
    }


@router.get("/candidates/{candidate_id}/image", response_class=FileResponse)
def edit_studio_candidate_image(candidate_id: str):
    profile_id = int(_creator_profile().get("id") or 0)
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Pending Edit Studio source not found.")
    candidate = _candidate_for_pending(library, candidate_id, source.image_id)
    path = Path(candidate.output_reference).expanduser()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Edit candidate image is unavailable.")
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@router.post("/approve", response_model=ApproveEditResponse)
def edit_studio_approve(request: EditCandidateActionRequest):
    profile_id = int(_creator_profile().get("id") or 0)
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Pending Edit Studio source not found.")
    candidate = _candidate_for_pending(library, request.candidate_image_id, source.image_id)
    result = library.approve_edit_candidate(
        source_image_id=source.image_id,
        edited_image_id=candidate.image_id,
        metadata={"approved_from": "edit_studio"},
    )
    if not result.success:
        raise HTTPException(status_code=400, detail="; ".join(result.errors) or result.message)
    for record in library.list_records():
        if record.status == "edit_candidate" and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == source.image_id:
            library.discard_edit_candidate(record.image_id)
    updated = library.get(source.image_id)
    version = dict(updated.generation_metadata or {}).get("asset_version") or updated.updated_at
    return {
        "success": True,
        "message": result.message,
        "updated_record": _record_payload(
            updated,
            image_url=f"/api/generation-library/media/{updated.image_id}?v={version}",
        ),
    }


@router.post("/edit-again", response_model=EditAgainResponse)
def edit_studio_edit_again(request: EditCandidateActionRequest):
    profile_id = int(_creator_profile().get("id") or 0)
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Pending Edit Studio source not found.")
    candidate = _candidate_for_pending(library, request.candidate_image_id, source.image_id)
    return {
        "success": True,
        "message": "Edited candidate is ready for another edit.",
        "working_source": _record_payload(candidate, image_url=f"/api/v1/edit-studio/candidates/{candidate.image_id}/image"),
    }


@router.post("/discard", response_model=EditStudioActionResponse)
def edit_studio_discard(request: EditCandidateActionRequest):
    profile_id = int(_creator_profile().get("id") or 0)
    library = GenerationLibraryService()
    source = library.pending_edit_record(creator_profile_id=profile_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Pending Edit Studio source not found.")
    _candidate_for_pending(library, request.candidate_image_id, source.image_id)
    errors = []
    for record in library.list_records():
        if record.status == "edit_candidate" and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == source.image_id:
            result = library.discard_edit_candidate(record.image_id)
            errors.extend(result.errors)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    return {"success": True, "message": "Edited image discarded."}


@router.get("/pending-source/image", response_class=FileResponse)
def edit_studio_pending_source_image(image_id: str | None = None):
    profile = _creator_profile()
    current = GenerationLibraryService().pending_edit_record(
        creator_profile_id=int(profile.get("id") or 0),
    )
    if current is None or (image_id and current.image_id != image_id):
        raise HTTPException(status_code=404, detail="Pending Edit Studio source changed.")
    try:
        path = EditStudioContextService().pending_source_path(
            creator_profile=profile,
        )
    except (KeyError, FileNotFoundError) as error:
        return JSONResponse(status_code=404, content={"error": str(error)})
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        filename=path.name,
        headers={"Cache-Control": "private, no-cache, must-revalidate"},
    )

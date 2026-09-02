"""Trusted backend API for recipe-based regeneration operations."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.background_operations import _context
from app.services.background_operation_service import BackgroundOperationService
from app.services.regeneration_eligibility_service import RegenerationEligibilityService
from app.services.regeneration_service import RegenerationIneligible, RegenerationService
from app.repositories.regeneration_repository import RegenerationRepository
from app.services.grid_thumbnail_service import GridThumbnailService


router = APIRouter(prefix="/api/v1/regeneration", tags=["regeneration"])


class RegenerationStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_generated_image_id: str
    count: Annotated[int, Field(strict=True, ge=1, le=5)]


class RegenerationPromoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_ids: Annotated[list[str], Field(min_length=1, max_length=5)]


def _eligibility_payload(value):
    return {
        "canRegenerate": value.can_regenerate,
        "reasonCode": value.reason_code,
        "reason": value.reason,
        "sourceGeneratedImageId": value.source_generated_image_id,
        "sourceRecipeId": str(value.source_recipe_id) if value.source_recipe_id else None,
    }


def _result_payload(item):
    return {
        "resultId": str(item.regeneration_result_id),
        "variationIndex": item.variation_index,
        "status": item.status,
        "generatedImageId": item.generated_image_id,
        "generationRecipeId": str(item.generation_recipe_id) if item.generation_recipe_id else None,
        "disposition": item.disposition,
        "mediaUrl": (
            f"/api/v1/regeneration/{item.operation_id}/results/{item.regeneration_result_id}/preview"
            if item.status == "SUCCEEDED" and item.media_path else None
        ),
        "errorCode": item.error_code,
        "errorMessage": item.error_message,
        "createdAt": item.created_at.isoformat() if item.created_at else None,
        "completedAt": item.completed_at.isoformat() if item.completed_at else None,
    }


@router.get("/eligibility/{source_generated_image_id}")
def regeneration_eligibility(source_generated_image_id: str):
    creator_id, _ = _context()
    value = RegenerationEligibilityService().inspect(
        source_generated_image_id, creator_profile_id=creator_id,
    )
    return {"success": True, "eligibility": _eligibility_payload(value)}


@router.get("/source/{source_generated_image_id}")
def regeneration_source(source_generated_image_id: str):
    creator_id, _ = _context()
    service = RegenerationEligibilityService()
    value = service.inspect(source_generated_image_id, creator_profile_id=creator_id)
    payload = {"success": True, "eligibility": _eligibility_payload(value), "source": None}
    try:
        record = service.library.get(source_generated_image_id)
    except KeyError:
        return payload
    if creator_id and int(record.creator_profile_id) != int(creator_id):
        return payload
    recipe = service.recipes.get(record.generation_recipe_id) if record.generation_recipe_id else None
    payload["source"] = {
        "generatedImageId": record.image_id,
        "mediaUrl": f"/api/v1/generation-library/{record.image_id}/preview",
        "providerDisplayName": str(record.provider_id or "").replace("_", " ").title(),
        "modelDisplayName": recipe.provider_model if recipe else None,
        "sourceWorkflow": recipe.source_workflow if recipe else None,
        "creativeMode": record.creative_mode,
    }
    return payload


@router.post("")
def start_regeneration(request: RegenerationStartRequest):
    creator_id, account_id = _context()
    try:
        operation, created = RegenerationService().start(
            source_generated_image_id=request.source_generated_image_id,
            count=request.count, creator_profile_id=creator_id, account_id=account_id,
        )
    except RegenerationIneligible as error:
        return JSONResponse(status_code=409, content={
            "success": False, "error": str(error),
            "eligibility": _eligibility_payload(error.eligibility),
        })
    except ValueError as error:
        return JSONResponse(status_code=400, content={"success": False, "error": str(error)})
    return JSONResponse(status_code=202, content={
        "success": True, "operationId": str(operation.operation_id), "reused": not created,
    })


@router.get("/workspace/current")
def current_regeneration_workspace():
    creator_id, _ = _context()
    run = RegenerationRepository().discover_workspace(creator_profile_id=creator_id)
    return {"success": True, "workspace": ({
        "operationId": str(run.operation_id),
        "sourceGeneratedImageId": run.source_generated_image_id,
    } if run else None)}


@router.post("/{operation_id}/dismiss")
def dismiss_regeneration_workspace(operation_id: str):
    creator_id, account_id = _context()
    operation = BackgroundOperationService().get(
        operation_id, creator_profile_id=creator_id, account_id=account_id)
    run = RegenerationRepository().get_run(operation_id, creator_profile_id=creator_id)
    if operation is None or run is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Regeneration operation not found."})
    if operation.status in {"QUEUED", "RUNNING", "WAITING_EXTERNAL", "CANCEL_REQUESTED"}:
        return JSONResponse(status_code=409, content={"success": False, "error": "Active regeneration cannot be reset."})
    RegenerationRepository().dismiss_workspace(operation_id, creator_profile_id=creator_id)
    return {"success": True}


@router.get("/{operation_id}")
def get_regeneration(operation_id: str):
    creator_id, account_id = _context()
    operations = BackgroundOperationService()
    operation = operations.get(operation_id, creator_profile_id=creator_id, account_id=account_id)
    service = RegenerationService()
    run = service.repository.get_run(operation_id, creator_profile_id=creator_id)
    if operation is None or run is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Regeneration operation not found."})
    if run.workspace_dismissed_at is not None:
        return JSONResponse(status_code=410, content={
            "success": False, "code": "WORKSPACE_DISMISSED",
            "error": "This Regeneration Studio workspace has been finalized.",
        })
    return {
        "success": True,
        "operation": operations.payload(operation),
        "run": {
            "operationId": str(run.operation_id),
            "sourceGeneratedImageId": run.source_generated_image_id,
            "sourceRecipeId": str(run.source_recipe_id),
            "requestedCount": run.requested_count,
            "status": run.status,
        },
        "results": [_result_payload(item) for item in service.repository.results(operation_id)],
    }


@router.get("/{operation_id}/results")
def get_regeneration_results(operation_id: str):
    response = get_regeneration(operation_id)
    if isinstance(response, JSONResponse):
        return response
    return {"success": True, "results": response["results"]}


@router.post("/{operation_id}/promote")
def promote_regeneration_results(operation_id: str, request: RegenerationPromoteRequest):
    creator_id, account_id = _context()
    try:
        records, archived, _ = RegenerationService().finalize_selection(
            operation_id, request.result_ids,
            creator_profile_id=creator_id, account_id=account_id,
        )
    except KeyError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"success": False, "error": str(error)})
    return {
        "success": True,
        "message": f"{len(records)} image{'s' if len(records) != 1 else ''} added to Generation Library",
        "promotedResultIds": request.result_ids,
        "generatedImageIds": [record.image_id for record in records],
        "archivedResultIds": [str(item.regeneration_result_id) for item in archived],
        "workspaceDismissed": True,
    }


@router.post("/{operation_id}/archive")
def archive_regeneration_results(operation_id: str, request: RegenerationPromoteRequest):
    creator_id, account_id = _context()
    try:
        rows = RegenerationService().archive(operation_id, request.result_ids,
            creator_profile_id=creator_id, account_id=account_id)
    except KeyError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"success": False, "error": str(error)})
    return {"success": True, "message": f"{len(rows)} regenerated image{'s' if len(rows)!=1 else ''} archived", "archivedResultIds": request.result_ids}


@router.post("/{operation_id}/results/{result_id}/restore")
def restore_regeneration_result(operation_id: str, result_id: str):
    creator_id, account_id = _context()
    service = RegenerationService()
    try:
        item = service.restore(operation_id, result_id,
            creator_profile_id=creator_id, account_id=account_id)
    except KeyError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})
    except ValueError as error:
        return JSONResponse(status_code=409, content={"success": False, "error": str(error)})
    run = service.repository.get_run(operation_id, creator_profile_id=creator_id)
    return {"success": True, "result": _result_payload(item), "redirect": f"/studio/regeneration?source={run.source_generated_image_id}&operation={operation_id}"}


@router.get("/archive/items")
def archived_regeneration_items(search: str | None = None, page: int = 1):
    creator_id, _ = _context(); page_size=20
    rows,total=RegenerationRepository().archived(creator_profile_id=creator_id,search=search,page=page,page_size=page_size)
    return {"success":True,"items":[{
        "resultId":str(row["regeneration_result_id"]),"operationId":str(row["operation_id"]),
        "variationIndex":row["variation_index"],"generatedImageId":row["generated_image_id"],
        "sourceGeneratedImageId":row["source_generated_image_id"],"providerDisplayName":str(row.get("provider_id") or "").replace("_"," ").title(),
        "modelDisplayName":row.get("provider_model"),"sourceWorkflow":row.get("source_workflow"),
        "generatedAt":row["completed_at"].isoformat() if row.get("completed_at") else None,
        "archivedAt":row["updated_at"].isoformat() if row.get("updated_at") else None,
        "mediaUrl":f"/api/v1/regeneration/{row['operation_id']}/results/{row['regeneration_result_id']}/preview",
    } for row in rows],"total":total,"page":page,"pageSize":page_size,"totalPages":max(1,(total+page_size-1)//page_size)}


@router.get("/{operation_id}/results/{result_id}/media")
def get_regeneration_result_media(operation_id: str, result_id: str):
    creator_id, _ = _context()
    service = RegenerationService()
    run = service.repository.get_run(operation_id, creator_profile_id=creator_id)
    item = next((value for value in service.repository.results(operation_id)
                 if str(value.regeneration_result_id) == result_id), None) if run else None
    if item is None or item.status != "SUCCEEDED" or not item.media_path:
        return JSONResponse(status_code=404, content={"success": False, "error": "Regenerated media not found."})
    path = Path(item.media_path)
    if not path.is_file():
        return JSONResponse(status_code=404, content={"success": False, "error": "Regenerated media is unavailable."})
    return FileResponse(path)


@router.get("/{operation_id}/results/{result_id}/preview")
def get_regeneration_result_preview(operation_id: str, result_id: str):
    creator_id, _ = _context()
    service = RegenerationService()
    run = service.repository.get_run(operation_id, creator_profile_id=creator_id)
    item = next((value for value in service.repository.results(operation_id)
                 if str(value.regeneration_result_id) == result_id), None) if run else None
    if item is None or item.status != "SUCCEEDED" or not item.media_path:
        return JSONResponse(status_code=404, content={"success": False, "error": "Regenerated media not found."})
    source = Path(item.media_path)
    if not source.is_file():
        return JSONResponse(status_code=404, content={"success": False, "error": "Regenerated media is unavailable."})
    path = GridThumbnailService().get_or_create_preview(
        source, identity=f"regeneration-{operation_id}-{result_id}")
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})

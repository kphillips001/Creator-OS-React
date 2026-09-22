"""Posted Content read surface and bounded library-disposition action."""

from __future__ import annotations

import mimetypes
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.posted_content_service import PostedContentService


router = APIRouter(prefix="/api/v1/posted-content", tags=["posted-content"])


class PostedContentResponse(BaseModel):
    content_id: str
    platform: str
    posted_at: str
    caption: str
    creator: str
    creator_profile_id: int | None
    generation_library_id: str
    provider: str
    prompt: str
    file_location: str
    media_url: str
    media_type: str
    move_eligible: bool


class PostedContentListResponse(BaseModel):
    items: list[PostedContentResponse]
    total: int


@router.get("", response_model=PostedContentListResponse)
def list_posted_content():
    items = PostedContentService().list_items()
    return {"items": [asdict(item) for item in items], "total": len(items)}


@router.get("/{content_id}/media", response_class=FileResponse)
def posted_content_media(content_id: str):
    try:
        item = PostedContentService().get(content_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Posted content not found.") from error
    path = Path(item.file_location)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Posted media is unavailable.")
    return FileResponse(
        path,
        media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/{content_id}/move-to-generation-library")
def move_posted_content_to_generation_library(content_id: str):
    try:
        item, already_moved = PostedContentService().move_to_generation_library(content_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Posted content not found.") from error
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return {
        "success": True,
        "already_moved": already_moved,
        "generation_library_id": item.generation_library_id,
        "message": "Image is already in Generation Library." if already_moved
        else "Image moved to Generation Library. Publication history was preserved.",
    }

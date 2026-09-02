"""Generation Library publishing HTTP endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.generation_library_publishing_service import (
    GenerationLibraryPublishingService,
)
from app.api.android_device import android_device_service
from app.services.instagram_handoff_service import InstagramHandoffService


router = APIRouter(prefix="/api/v1/generation-library", tags=["generation-library"])
instagram_handoff_service = InstagramHandoffService(android_device=android_device_service)


class CaptionGenerationRequest(BaseModel):
    destination: str
    ideaSeed: int = Field(default=0, ge=0)


class XPublishTarget(BaseModel):
    accountName: str
    caption: str
    captionResultId: str | None = None
    selectedGeneratedCaption: str = ""


class PublishRequest(BaseModel):
    destination: str
    caption: str
    captionResultId: str | None = None
    selectedGeneratedCaption: str = ""
    ctaEnabled: bool = False
    ctaLabel: str = ""
    ctaUrl: str = ""
    selectedCtas: list[str] | None = None
    xTargets: list[XPublishTarget] | None = None
    xAutoRepliesEnabled: bool = True


class InstagramHandoffRequest(BaseModel):
    caption: str = Field(min_length=1)


def _creator_profile() -> dict:
    account_id = _current_account_id()
    profile = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not profile or not int(profile.get("id") or 0):
        raise ValueError("Creator Profile required before publishing.")
    return profile


def _error_response(error: Exception) -> JSONResponse:
    status = 404 if isinstance(error, KeyError) else 400
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "error": str(error),
            "exceptionType": error.__class__.__name__,
        },
    )


@router.get("/{generated_image_id}/publish")
def publish_context(generated_image_id: str):
    try:
        return {"success": True, **GenerationLibraryPublishingService().context(generated_image_id)}
    except (KeyError, ValueError) as error:
        return _error_response(error)


@router.post("/{generated_image_id}/publish/captions")
def generate_captions(generated_image_id: str, request: CaptionGenerationRequest):
    try:
        result = GenerationLibraryPublishingService().generate_captions(
            generated_image_id=generated_image_id,
            destination=request.destination,
            creator_profile=_creator_profile(),
            idea_seed=request.ideaSeed,
        )
        return {"success": True, **result}
    except (KeyError, ValueError, RuntimeError) as error:
        return _error_response(error)
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(error),
                "exceptionType": error.__class__.__name__,
            },
        )


@router.post("/{generated_image_id}/publish")
def publish(generated_image_id: str, request: PublishRequest):
    try:
        result = GenerationLibraryPublishingService().publish(
            generated_image_id=generated_image_id,
            destination=request.destination,
            caption=request.caption,
            caption_result_id=request.captionResultId,
            selected_generated_caption=request.selectedGeneratedCaption,
            cta_enabled=request.ctaEnabled,
            cta_label=request.ctaLabel,
            cta_url=request.ctaUrl,
            selected_ctas=(tuple(request.selectedCtas) if request.selectedCtas is not None else None),
            x_targets=(
                tuple(target.model_dump() for target in request.xTargets)
                if request.xTargets is not None
                else None
            ),
            x_auto_replies_enabled=request.xAutoRepliesEnabled,
        )
        return {"success": True, **result}
    except (KeyError, ValueError, RuntimeError) as error:
        return _error_response(error)
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(error),
                "exceptionType": error.__class__.__name__,
            },
        )


@router.post("/{generated_image_id}/publish/instagram/handoff")
async def handoff_to_instagram(generated_image_id: str, request: InstagramHandoffRequest):
    try:
        result = await asyncio.to_thread(
            instagram_handoff_service.handoff,
            generated_image_id=generated_image_id,
            caption=request.caption,
        )
        return {"success": True, **result}
    except (KeyError, ValueError, RuntimeError) as error:
        return _error_response(error)
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(error),
                "exceptionType": error.__class__.__name__,
            },
        )

"""Content Studio HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.dashboard.config import load_dashboard_config
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.fanvue_account_repository import get_all_accounts
from app.services.reference_library_service import ReferenceLibraryService


router = APIRouter(prefix="/api/v1/content-studio", tags=["content-studio"])
logger = logging.getLogger("uvicorn.error")

PLANNER_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PLANNER_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}
PLANNER_IMAGE_MAX_BYTES = 200 * 1024 * 1024
GENERATION_PROMPT_SOURCES = {
    "Original Tags", "Enhanced Tags", "Surprise Me Tags",
    "Enhanced Explicit Tags", "Prompt Workshop", "Manual Prompt",
}
_generation_runs: dict[str, dict] = {}
_generation_runs_lock = threading.Lock()


class LuckyTagsRequest(BaseModel):
    promptCount: int
    explicit: bool = False


class TransformTagsRequest(BaseModel):
    tags: str
    explicit: bool = False


class PromptWorkshopRequest(BaseModel):
    lane: str = "premium"
    requestText: str
    promptCount: int


class PromptWorkshopUseRequest(BaseModel):
    promptNumber: int


class PromptPreviewRequest(BaseModel):
    creativeMode: str
    creativeTags: str
    promptCount: int


class GenerationSubmissionRequest(BaseModel):
    provider: str
    promptSource: str
    promptSourceLabel: str
    promptBatch: list[str] = Field(default_factory=list)
    creativeMode: str
    promptCount: int
    creatorContext: dict


def _current_account_id() -> int | None:
    accounts = tuple(dict(account) for account in get_all_accounts())
    if not accounts:
        return None

    selected_id = None
    state_path = Path("data/config/dashboard_selected_account.json")
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        selected_id = state.get("last_selected_account_id")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass

    selected = next((account for account in accounts if account.get("id") == selected_id), None)
    if selected is None:
        behavior_config, _ = load_dashboard_config()
        default_persona = str(behavior_config.get("default_persona") or "ava").lower()
        selected = next(
            (
                account
                for account in accounts
                if default_persona in str(account.get("display_name") or "").lower()
            ),
            None,
        )

    return int((selected or accounts[0])["id"])


def _read_content_studio_context() -> dict[str, bool | int | str | None]:
    account_id = _current_account_id()
    creator_profile = (
        get_active_creator_profile(str(account_id)) if account_id is not None else {}
    )
    creator_profile_id = int(creator_profile.get("id") or 0)
    active_reference = (
        ReferenceLibraryService().get_active_reference_context(
            creator_profile_id=creator_profile_id,
        )
        if creator_profile_id
        else None
    )
    return {
        "success": True,
        "error": None,
        "creatorProfileExists": bool(creator_profile_id),
        "activeReferenceExists": active_reference is not None,
        "activeReferenceAssetId": (
            active_reference["asset_id"] if active_reference is not None else None
        ),
        "activeReferenceLastUsedAt": (
            active_reference["last_used_at"] if active_reference is not None else None
        ),
    }


def _read_content_studio_configuration() -> dict:
    from app.services.content_studio_configuration_service import (
        ContentStudioConfigurationService,
    )
    from app.services.creative_director_service import CreativeDirectorService
    from app.services.generation_engine_service import GenerationEngineService

    account_id = _current_account_id()
    creator_profile = (
        get_active_creator_profile(str(account_id)) if account_id is not None else {}
    )
    creator_profile_id = int(creator_profile.get("id") or 0)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before using Content Studio.")

    reference_service = ReferenceLibraryService()
    creative_director = CreativeDirectorService(
        reference_library_service=reference_service,
    )
    generation_engine = GenerationEngineService(
        reference_library_service=reference_service,
    )
    configuration = ContentStudioConfigurationService(
        creative_director=creative_director,
        generation_engine=generation_engine,
    ).load(creator_profile_id)
    return {
        "success": True,
        "error": None,
        "modes": [
            {"value": value, "label": label}
            for value, label in configuration.modes
        ],
        "promptCount": {
            "minimum": configuration.prompt_count_minimum,
            "maximum": configuration.prompt_count_maximum,
            "default": configuration.default_prompt_count,
        },
        "providers": [
            {"value": value, "label": label}
            for value, label in configuration.providers
        ],
        "defaults": {
            "mode": configuration.default_mode,
            "provider": configuration.default_provider,
        },
    }


def _creative_director_context(*, require_reference: bool = True):
    from app.services.creative_director_service import CreativeDirectorService

    account_id = _current_account_id()
    creator_profile = (
        get_active_creator_profile(str(account_id)) if account_id is not None else {}
    )
    creator_profile_id = int(creator_profile.get("id") or 0)
    if not creator_profile_id:
        raise ValueError("Creator Profile required before using Content Studio.")
    reference_service = ReferenceLibraryService()
    if require_reference and reference_service.get_active_canonical_asset_id(creator_profile_id=creator_profile_id) is None:
        raise ValueError("Select an active Reference Image before creating premium work.")
    return creator_profile, CreativeDirectorService(
        reference_library_service=reference_service,
    )


def _prompt_workshop_batch_content(batch) -> dict:
    return {
        "batchId": batch.batch_id,
        "requestText": batch.request_text,
        "lane": batch.lane,
        "prompts": list(batch.prompts),
        "usedPromptNumbers": list(batch.used_prompt_numbers),
        "createdAt": batch.created_at,
    }


def _create_lucky_tags(request: LuckyTagsRequest) -> dict:
    from app.services.content_studio_configuration_service import (
        PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
    )

    creator_profile, creative_director = _creative_director_context()
    if not (
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM
        <= request.promptCount
        <= PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM
    ):
        raise ValueError(
            "Prompt Count must be between "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM} and "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM}."
        )
    tags = creative_director.premium_lucky_tags(
        creator_profile=creator_profile,
        prompt_count=request.promptCount,
        explicit=request.explicit,
    )
    return {"success": True, "error": None, "tags": tags}


def _enhance_tags(request: TransformTagsRequest) -> dict:
    creator_profile, creative_director = _creative_director_context()
    tags = request.tags.strip()
    if not tags:
        raise ValueError("Tags are required.")
    enhanced_tags = creative_director.enhance_premium_tags(
        simple_tags=tags,
        creator_profile=creator_profile,
        explicit=request.explicit,
    )
    return {"success": True, "error": None, "tags": enhanced_tags}


def _surprise_tags(request: TransformTagsRequest) -> dict:
    creator_profile, creative_director = _creative_director_context()
    tags = request.tags.strip()
    if not tags:
        raise ValueError("Tags are required.")
    surprise_tags = creative_director.surprise_premium_tags(
        simple_tags=tags,
        creator_profile=creator_profile,
    )
    return {"success": True, "error": None, "tags": surprise_tags}


def _generate_prompt_workshop_batch(request: PromptWorkshopRequest) -> dict:
    from app.services.content_studio_configuration_service import (
        PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
    )

    creator_profile, creative_director = _creative_director_context()
    lane = request.lane.strip().lower()
    if lane not in {"premium", "explicit"}:
        raise ValueError("Prompt Mode must be Premium or Explicit.")
    brief = request.requestText.strip()
    if not brief:
        raise ValueError("Prompt assistant request is required.")
    if not (
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM
        <= request.promptCount
        <= PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM
    ):
        raise ValueError(
            "Prompt Count must be between "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM} and "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM}."
        )
    batch = creative_director.ask_prompt_assistant(
        creator_profile=creator_profile,
        request_text=brief,
        lane=lane,
        prompt_count=request.promptCount,
    )
    return {"success": True, "error": None, "batch": _prompt_workshop_batch_content(batch)}


def _read_prompt_workshop_archive() -> dict:
    creator_profile, creative_director = _creative_director_context(require_reference=False)
    history = creative_director.prompt_assistant_history(
        creator_profile_id=int(creator_profile["id"]),
        limit=10,
    )
    return {
        "success": True,
        "error": None,
        "batches": [_prompt_workshop_batch_content(batch) for batch in history],
    }


def _mark_prompt_workshop_used(batch_id: str, request: PromptWorkshopUseRequest) -> dict:
    creator_profile, creative_director = _creative_director_context(require_reference=False)
    history = creative_director.prompt_assistant_history(
        creator_profile_id=int(creator_profile["id"]),
        limit=10_000,
    )
    batch = next((item for item in history if item.batch_id == batch_id), None)
    if batch is None:
        raise ValueError("Prompt Workshop batch not found.")
    if not 1 <= request.promptNumber <= len(batch.prompts):
        raise ValueError("Selected prompt is outside the archived batch.")
    creative_director.mark_prompt_assistant_used(batch.batch_id, request.promptNumber)
    return {"success": True, "error": None}


def _create_prompt_preview(request: PromptPreviewRequest) -> dict:
    from app.services.content_studio_configuration_service import (
        PREMIUM_CREATIVE_MODE_LABELS,
        PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
    )

    creator_profile, creative_director = _creative_director_context()
    creative_mode = request.creativeMode.strip()
    if creative_mode not in PREMIUM_CREATIVE_MODE_LABELS:
        raise ValueError("Select a Premium creative mode.")
    creative_tags = request.creativeTags.strip()
    if not creative_tags:
        raise ValueError("Creative Tags are required.")
    if not (
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM
        <= request.promptCount
        <= PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM
    ):
        raise ValueError(
            "Prompt Count must be between "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM} and "
            f"{PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM}."
        )
    plan = creative_director.create_prompt_plan(
        creator_profile=creator_profile,
        creative_tags=creative_tags,
        creative_mode=creative_mode,
        prompt_count=request.promptCount,
    )
    metadata = dict(plan.prompt_metadata or {})
    prompts = [
        str(prompt).strip()
        for prompt in metadata.get("prompt_variations") or ()
        if str(prompt).strip()
    ][: request.promptCount]
    if not prompts:
        prompts = [str(plan.prompt_text or "").strip()]
    return {
        "success": True,
        "error": None,
        "preview": {
            "planId": plan.plan_id,
            "creativeMode": plan.creative_mode,
            "creativeRationale": plan.creative_rationale,
            "promptMetadata": metadata,
            "prompts": prompts,
            "signature": {
                "creativeMode": creative_mode,
                "promptCount": request.promptCount,
                "creativeTags": creative_tags,
            },
        },
    }


def _ask_prompt_planner(
    *,
    question: str,
    image_bytes: bytes | None = None,
    image_mime_type: str | None = None,
    image_name: str | None = None,
) -> dict:
    prompt = str(question or "").strip()
    if not prompt:
        raise ValueError("Enter a question before asking.")
    if image_bytes is not None:
        suffix = Path(image_name or "").suffix.lower()
        if image_mime_type not in PLANNER_IMAGE_TYPES or suffix not in PLANNER_IMAGE_SUFFIXES:
            raise ValueError("Image must be a PNG, JPG, JPEG, or WEBP file.")
        if not image_bytes:
            raise ValueError("The selected image is empty.")
        if len(image_bytes) > PLANNER_IMAGE_MAX_BYTES:
            raise ValueError("The selected image exceeds the 200 MB upload limit.")
    _, creative_director = _creative_director_context(require_reference=False)
    answer = creative_director.ask_anything(
        question=prompt,
        image_bytes=image_bytes,
        image_mime_type=image_mime_type,
        image_name=image_name,
    )
    return {"success": True, "error": None, "answer": answer}


def _generation_run_content(run_id: str) -> dict:
    with _generation_runs_lock:
        state = dict(_generation_runs.get(run_id) or {})
    if not state:
        raise ValueError("Content Studio generation was not found.")
    outputs = tuple(state.pop("outputReferences", ()))
    state["images"] = [
        {"index": index, "url": f"/api/v1/content-studio/generations/{run_id}/images/{index}"}
        for index, _ in enumerate(outputs)
    ]
    return {"success": True, "error": None, "generation": state}


def _update_generation_run(run_id: str, **values) -> None:
    with _generation_runs_lock:
        if run_id in _generation_runs:
            _generation_runs[run_id].update(values)


def _execute_content_studio_generation(run_id: str, request: GenerationSubmissionRequest) -> None:
    from app.models.generation_engine import GenerationStatus
    from app.services.content_studio_configuration_service import (
        ContentStudioConfigurationService,
        PREMIUM_CREATIVE_MODE_LABELS,
        PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM,
        PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM,
    )
    from app.services.creative_director_service import CreativeDirectorService
    from app.services.generation_engine_service import GenerationEngineService
    from app.services.generation_library_service import GenerationLibraryService
    from app.services.content_studio_generation_service import (
        ContentStudioGenerationService,
        generation_completion_message,
    )

    try:
        creator_profile, creative_director = _creative_director_context()
        if request.creativeMode not in PREMIUM_CREATIVE_MODE_LABELS:
            raise ValueError("Select a Premium creative mode.")
        if request.promptSourceLabel not in GENERATION_PROMPT_SOURCES:
            raise ValueError("Select a valid prompt source.")
        source = request.promptSource.strip()
        if not source:
            raise ValueError("Creative Tags are required.")
        if not PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM <= request.promptCount <= PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM:
            raise ValueError(
                f"Prompt Count must be between {PREMIUM_STUDIO_PROMPT_COUNT_MINIMUM} "
                f"and {PREMIUM_STUDIO_PROMPT_COUNT_MAXIMUM}."
            )
        reference_service = creative_director.reference_library
        generation_engine = GenerationEngineService(reference_library_service=reference_service)
        configuration = ContentStudioConfigurationService(
            creative_director=creative_director,
            generation_engine=generation_engine,
        ).load(int(creator_profile["id"]))
        available_providers = {provider_id for provider_id, _ in configuration.providers}
        if request.provider not in available_providers:
            raise ValueError("Select an available Content Studio provider.")
        provider_label = dict(configuration.providers).get(request.provider, request.provider)
        _update_generation_run(run_id, status="planning", message="Creating prompt plan", provider=provider_label)
        prompts = tuple(str(prompt).strip() for prompt in request.promptBatch if str(prompt).strip())
        generation_service = ContentStudioGenerationService(
            creative_director=creative_director,
            generation_engine=generation_engine,
            generation_library=GenerationLibraryService(),
            reference_service=reference_service,
        )
        plan, job = generation_service.queue(
            creator_profile=creator_profile,
            creative_tags=source,
            creative_mode=request.creativeMode,
            prompt_count=request.promptCount,
            provider_id=request.provider,
            prompt_batch=prompts,
        )
        _update_generation_run(run_id, status="queued", jobId=job.job_id, message="Queued Image 1")

        def progress_callback(**event) -> None:
            outputs = tuple(str(value) for value in event.get("output_references") or () if str(value))
            with _generation_runs_lock:
                previous_outputs = tuple((_generation_runs.get(run_id) or {}).get("outputReferences") or ())
            outputs = tuple(dict.fromkeys((*previous_outputs, *outputs)))
            completed = max(int(event.get("completed_count") or event.get("current") or 0), len(outputs))
            failed = int(event.get("failed_count") or 0)
            processed = int(event.get("processed_count") or completed + failed)
            _update_generation_run(
                run_id,
                status="running",
                message=str(event.get("message") or "Generation running"),
                completedCount=completed,
                failedCount=failed,
                processedCount=processed,
                progress=min(100.0, processed / max(1, request.promptCount) * 100),
                outputReferences=outputs,
            )

        executed, records = generation_service.execute(job, progress_callback=progress_callback)
        outputs = tuple(record.output_reference for record in records)
        if not outputs and executed.result:
            outputs = tuple(executed.result.output_references)
        metadata = dict(executed.result.image_metadata or {}) if executed.result else {}
        completed = int(metadata.get("completed_count") or len(outputs))
        failed = int(metadata.get("failed_count") or (request.promptCount if not completed else 0))
        level, message = generation_completion_message(
            total_requested=request.promptCount,
            success_count=completed,
            failed_count=failed,
        )
        final_status = "succeeded" if level == "success" else "partial" if level == "warning" else "failed"
        if executed.status != GenerationStatus.SUCCEEDED.value and executed.failure:
            message = executed.failure.reason
            final_status = "failed"
        _update_generation_run(
            run_id,
            status=final_status,
            message=message,
            completedCount=completed,
            failedCount=failed,
            processedCount=completed + failed,
            progress=100.0,
            outputReferences=outputs,
            promptPlanId=plan.plan_id,
        )
    except ValueError as error:
        _update_generation_run(run_id, status="failed", message=str(error), failedCount=request.promptCount, processedCount=request.promptCount, progress=100.0)
    except Exception:
        logger.exception("Content Studio generation failed")
        _update_generation_run(run_id, status="failed", message="Generation failed. Please try again.", failedCount=request.promptCount, processedCount=request.promptCount, progress=100.0)


async def _run_tag_action(action) -> JSONResponse:
    try:
        content = await asyncio.wait_for(asyncio.to_thread(action), timeout=60)
        return JSONResponse(status_code=200, content=content)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error), "tags": ""},
        )
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Creative tag action timed out", "tags": ""},
        )
    except Exception as error:
        logger.exception("Content Studio creative tag action failed")
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": str(error) or "Creative tag action failed",
                "tags": "",
            },
        )


@router.get("/context")
async def get_content_studio_context() -> JSONResponse:
    logger.info("Content Studio context request received")
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(_read_content_studio_context),
            timeout=10,
        )
        logger.info("Content Studio context response status=200")
        return JSONResponse(status_code=200, content=content)
    except asyncio.TimeoutError:
        logger.exception("Content Studio context request timed out")
        content = {
            "success": False,
            "error": "Content Studio context read timed out",
            "creatorProfileExists": False,
            "activeReferenceExists": False,
            "activeReferenceAssetId": None,
            "activeReferenceLastUsedAt": None,
        }
        logger.error("Content Studio context response status=503")
        return JSONResponse(status_code=503, content=content)
    except Exception as error:
        logger.exception("Content Studio context request failed")
        content = {
            "success": False,
            "error": str(error) or "Content Studio context read failed",
            "creatorProfileExists": False,
            "activeReferenceExists": False,
            "activeReferenceAssetId": None,
            "activeReferenceLastUsedAt": None,
        }
        logger.error("Content Studio context response status=503")
        return JSONResponse(status_code=503, content=content)


@router.get("/configuration")
async def get_content_studio_configuration() -> JSONResponse:
    logger.info("Content Studio configuration request received")
    try:
        content = await asyncio.wait_for(
            asyncio.to_thread(_read_content_studio_configuration),
            timeout=10,
        )
        logger.info("Content Studio configuration response status=200")
        return JSONResponse(status_code=200, content=content)
    except asyncio.TimeoutError:
        logger.exception("Content Studio configuration request timed out")
        content = {
            "success": False,
            "error": "Content Studio configuration read timed out",
        }
        logger.error("Content Studio configuration response status=503")
        return JSONResponse(status_code=503, content=content)
    except Exception as error:
        logger.exception("Content Studio configuration request failed")
        content = {
            "success": False,
            "error": str(error) or "Content Studio configuration read failed",
        }
        logger.error("Content Studio configuration response status=503")
        return JSONResponse(status_code=503, content=content)


@router.post("/creative-tags/lucky")
async def create_content_studio_lucky_tags(request: LuckyTagsRequest) -> JSONResponse:
    return await _run_tag_action(lambda: _create_lucky_tags(request))


@router.post("/creative-tags/enhance")
async def enhance_content_studio_tags(request: TransformTagsRequest) -> JSONResponse:
    return await _run_tag_action(lambda: _enhance_tags(request))


@router.post("/creative-tags/surprise")
async def surprise_content_studio_tags(request: TransformTagsRequest) -> JSONResponse:
    return await _run_tag_action(lambda: _surprise_tags(request))


@router.post("/prompt-workshop/generate")
async def generate_content_studio_prompt_workshop(request: PromptWorkshopRequest) -> JSONResponse:
    return await _run_tag_action(lambda: _generate_prompt_workshop_batch(request))


@router.get("/prompt-workshop/archive")
async def get_content_studio_prompt_workshop_archive() -> JSONResponse:
    return await _run_tag_action(_read_prompt_workshop_archive)


@router.post("/prompt-workshop/archive/{batch_id}/use")
async def mark_content_studio_prompt_workshop_used(
    batch_id: str,
    request: PromptWorkshopUseRequest,
) -> JSONResponse:
    return await _run_tag_action(lambda: _mark_prompt_workshop_used(batch_id, request))


@router.post("/prompt-preview")
async def create_content_studio_prompt_preview(request: PromptPreviewRequest) -> JSONResponse:
    return await _run_tag_action(lambda: _create_prompt_preview(request))


@router.post("/prompt-planner/ask")
async def ask_content_studio_prompt_planner(
    question: str = Form(...),
    image: UploadFile | None = File(default=None),
) -> JSONResponse:
    try:
        image_bytes = await image.read() if image is not None else None
        content = await asyncio.wait_for(
            asyncio.to_thread(
                _ask_prompt_planner,
                question=question,
                image_bytes=image_bytes,
                image_mime_type=image.content_type if image is not None else None,
                image_name=image.filename if image is not None else None,
            ),
            timeout=60,
        )
        return JSONResponse(status_code=200, content=content)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"success": False, "error": str(error), "answer": ""})
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Canonical Prompt Planner request timed out.", "answer": ""},
        )
    except Exception:
        logger.exception("Canonical Prompt Planner request failed")
        return JSONResponse(
            status_code=503,
            content={"success": False, "error": "Canonical Prompt Planner request failed. Please try again.", "answer": ""},
        )


@router.post("/generations")
async def submit_content_studio_generation(
    request: GenerationSubmissionRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    run_id = f"content_studio_generation_{uuid4().hex}"
    with _generation_runs_lock:
        _generation_runs[run_id] = {
            "runId": run_id,
            "jobId": None,
            "promptPlanId": None,
            "status": "queued",
            "message": "Queued Image 1",
            "provider": request.provider,
            "completedCount": 0,
            "failedCount": 0,
            "processedCount": 0,
            "totalCount": request.promptCount,
            "progress": 0.0,
            "outputReferences": (),
        }
    background_tasks.add_task(_execute_content_studio_generation, run_id, request)
    return JSONResponse(
        status_code=202,
        content={"success": True, "error": None, "runId": run_id},
    )


@router.get("/generations/{run_id}")
async def get_content_studio_generation(run_id: str) -> JSONResponse:
    try:
        return JSONResponse(status_code=200, content=_generation_run_content(run_id))
    except ValueError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})


@router.get("/generations/{run_id}/images/{image_index}")
async def get_content_studio_generation_image(run_id: str, image_index: int) -> Response:
    with _generation_runs_lock:
        outputs = tuple((_generation_runs.get(run_id) or {}).get("outputReferences") or ())
    if image_index < 0 or image_index >= len(outputs):
        return JSONResponse(status_code=404, content={"success": False, "error": "Generated image not found."})
    reference = str(outputs[image_index])
    if reference.lower().startswith(("http://", "https://")):
        return RedirectResponse(reference)
    path = Path(reference).resolve()
    if not path.is_file():
        return JSONResponse(status_code=404, content={"success": False, "error": "Generated image is unavailable."})
    return FileResponse(path)

"""Photoshoot Studio read-only HTTP context."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.photoshoot_context_service import PhotoshootContextService
from app.services.generation_library_service import GenerationLibraryService
from app.services.photoshoot_queue_service import PhotoshootQueueService
from app.services.photoshoot_manual_service import PhotoshootManualService
from app.services.photoshoot_creative_director_service import PhotoshootCreativeDirectorWorkflowService
from app.services.photoshoot_auto_run_service import PhotoshootAutoRunService
from app.services.photoshoot_curation_service import PhotoshootCurationService


router = APIRouter(prefix="/api/v1/photoshoot", tags=["photoshoot"])


class PhotoshootProviderResponse(BaseModel):
    value: str
    label: str


class PhotoshootGenerationResponse(BaseModel):
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


class ContinuitySettingsResponse(BaseModel):
    location: bool
    wardrobe: bool
    lighting: bool
    hairstyle: bool
    makeup: bool
    camera_style: bool


class ActivePhotoshootSessionResponse(BaseModel):
    session_id: str
    creator_profile_id: int
    title: str
    reference_asset_id: int | None
    creative_mode: str
    status: str
    provider_id: str
    creator_notes: str | None
    creative_continuity: dict
    request_ids: list[str]
    current_request_id: str | None
    created_at: str
    updated_at: str | None
    metadata: dict
    continuity_locks: ContinuitySettingsResponse


class TimelineSummaryItemResponse(BaseModel):
    request_id: str
    sequence_index: int
    shot_number: int
    label: str
    is_seed: bool
    image: PhotoshootGenerationResponse


class PhotoshootContextResponse(BaseModel):
    creator_profile_exists: bool
    pending_photoshoot: PhotoshootGenerationResponse | None
    active_session: ActivePhotoshootSessionResponse | None
    provider_list: list[PhotoshootProviderResponse]
    creative_mode: str | None
    continuity_settings: ContinuitySettingsResponse | None
    timeline_summary: list[TimelineSummaryItemResponse]


class PhotoshootReturnResponse(BaseModel):
    success: bool
    message: str
    image_id: str
    redirect: str


class ManualGenerateRequest(BaseModel):
    session_id: str
    provider_id: str
    creative_mode: str
    prompt: str
    continuity_settings: ContinuitySettingsResponse
    session_direction: str = ""
    creative_hint: str = ""


class CandidateActionRequest(BaseModel):
    session_id: str
    request_id: str


class ManualGenerateResponse(BaseModel):
    success: bool
    session_id: str
    request_id: str
    generation_job_id: str
    status: str


class CreativeDirectorSessionRequest(BaseModel):
    session_id: str


class AutoRunStartRequest(CreativeDirectorSessionRequest):
    auto_approve_enabled: bool = True


class PhotoshootCurationRequest(CreativeDirectorSessionRequest):
    selected_image_ids: list[str] = Field(default_factory=list)
    photoshoot_decision: str


class CreativeDirectorInputRequest(CreativeDirectorSessionRequest):
    creative_mode: str
    creator_guidance: str = ""
    continuity_locks: ContinuitySettingsResponse


class InspirationRequest(CreativeDirectorInputRequest):
    provider_context: str = ""


class InspirationSelectionRequest(CreativeDirectorSessionRequest):
    idea: str


class CreatorGuidanceRequest(CreativeDirectorSessionRequest):
    creator_guidance: str = ""


class PlanningModeRequest(CreativeDirectorSessionRequest):
    planning_mode: str = "frame_by_frame"
    plan_frame_count: int = 8


class SessionPlanRequest(CreativeDirectorInputRequest):
    plan_frame_count: int = 8


def _creator_profile_id_required() -> int:
    creator_profile_id = int(_creator_profile().get("id") or 0)
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before using Photoshoot Studio.")
    return creator_profile_id


def _manual_error(error: Exception):
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail="Photoshoot Session not found.") from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(status_code=409, detail="Photoshoot action failed. Please try again.") from error


def _execute_manual_generation(session_id: str, job) -> None:
    PhotoshootManualService().execute(session_id=session_id, job=job)


def _creative_director_error(error: Exception):
    if isinstance(error, KeyError):
        raise HTTPException(status_code=404, detail="Photoshoot Session not found.") from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=409, detail=str(error)) from error
    raise HTTPException(status_code=502, detail="Creative Director request failed. Please try again.") from error


def _creator_profile() -> dict:
    account_id = _current_account_id()
    return get_active_creator_profile(str(account_id)) if account_id is not None else {}


@router.get("/context", response_model=PhotoshootContextResponse)
def photoshoot_context():
    return PhotoshootContextService().read(creator_profile=_creator_profile())


@router.get("/creative-director/context")
def creative_director_context(session_id: str | None = None):
    try:
        return PhotoshootCreativeDirectorWorkflowService().context(
            creator_profile_id=_creator_profile_id_required(), session_id=session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/inspiration")
def creative_director_inspiration(request: InspirationRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().inspiration(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            creative_mode=request.creative_mode,
            creator_guidance=request.creator_guidance, provider_context=request.provider_context,
            continuity_locks=request.continuity_locks.model_dump(),
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/selection")
def creative_director_selection(request: InspirationSelectionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().select_inspiration(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id, idea=request.idea,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/guidance")
def creative_director_guidance(request: CreatorGuidanceRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().save_guidance(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            creator_guidance=request.creator_guidance,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/recommendation")
def creative_director_recommendation(request: CreativeDirectorInputRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().recommendation(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            creative_mode=request.creative_mode,
            creator_guidance=request.creator_guidance,
            continuity_locks=request.continuity_locks.model_dump(),
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/approve")
def creative_director_approve(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().approve(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/choose-another")
def creative_director_choose_another(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().choose_another(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/planning-mode")
def creative_director_planning_mode(request: PlanningModeRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().set_planning_mode(
            creator_profile_id=_creator_profile_id_required(),
            session_id=request.session_id,
            planning_mode=request.planning_mode,
            plan_frame_count=request.plan_frame_count,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/session-plan")
def creative_director_session_plan(request: SessionPlanRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().generate_session_plan(
            creator_profile_id=_creator_profile_id_required(),
            session_id=request.session_id,
            creative_mode=request.creative_mode,
            creator_guidance=request.creator_guidance,
            continuity_locks=request.continuity_locks.model_dump(),
            plan_frame_count=request.plan_frame_count,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/session-plan/approve")
def creative_director_approve_session_plan(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().approve_session_plan(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.get("/auto-run/runtime")
def photoshoot_auto_run_runtime(session_id: str):
    try:
        return PhotoshootAutoRunService().runtime(
            creator_profile_id=_creator_profile_id_required(), session_id=session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/auto-run/start")
def photoshoot_auto_run_start(request: AutoRunStartRequest):
    try:
        return PhotoshootAutoRunService().start(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            auto_approve_enabled=request.auto_approve_enabled)
    except Exception as error:
        _manual_error(error)


@router.post("/auto-run/pause")
def photoshoot_auto_run_pause(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootAutoRunService().pause(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/auto-run/resume")
def photoshoot_auto_run_resume(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootAutoRunService().resume(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/auto-run/stop")
def photoshoot_auto_run_stop(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootAutoRunService().stop(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/auto-run/retry")
def photoshoot_auto_run_retry(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootAutoRunService().retry(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/creative-director/session-plan/develop")
def creative_director_develop_planned_shot(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().develop_planned_shot(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/creative-director/session-plan/advance")
def creative_director_advance_session_plan(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCreativeDirectorWorkflowService().advance_session_plan(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
        )
    except Exception as error:
        _creative_director_error(error)


@router.post("/generate", response_model=ManualGenerateResponse, status_code=202)
def generate_manual_photoshoot(request: ManualGenerateRequest, background_tasks: BackgroundTasks):
    service = PhotoshootManualService()
    try:
        shot, job = service.create_manual_request(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            provider_id=request.provider_id, creative_mode=request.creative_mode, prompt=request.prompt,
            continuity_locks=request.continuity_settings.model_dump(), session_direction=request.session_direction,
            creative_hint=request.creative_hint,
        )
    except Exception as error:
        _manual_error(error)
    background_tasks.add_task(_execute_manual_generation, request.session_id, job)
    return {"success": True, "session_id": request.session_id, "request_id": shot.request_id,
            "generation_job_id": job.job_id, "status": "generating"}


@router.get("/status")
def manual_photoshoot_status(session_id: str):
    try:
        state = PhotoshootManualService().status(
            creator_profile_id=_creator_profile_id_required(), session_id=session_id,
        )
    except Exception as error:
        _manual_error(error)
    request = state["request"]
    candidate = state["candidate"]
    return {
        "success": True,
        "session_id": session_id,
        "request": None if request is None else {
            "request_id": request.request_id, "status": request.status, "prompt": request.prompt_text,
            "provider_id": state["session"].provider_id, "generation_job_id": request.generation_job_id,
            "failure": state["failure"] or None,
        },
        "candidate": None if candidate is None else PhotoshootContextService._generation_payload(candidate),
    }


@router.post("/candidate/approve")
def approve_manual_candidate(request: CandidateActionRequest):
    try:
        service = PhotoshootManualService()
        approved = service.approve(
            creator_profile_id=_creator_profile_id_required(),
            session_id=request.session_id,
            request_id=request.request_id,
        )
        session = service.queue.get_session(request.session_id)
    except Exception as error:
        _manual_error(error)
    return {
        "success": True,
        "message": "Shot approved.",
        "request": {
            "request_id": approved.request_id,
            "status": approved.status,
            "imported_asset_ids": list(approved.imported_asset_ids),
        },
        "session": PhotoshootContextService._session_payload(session),
    }


@router.post("/candidate/regenerate", response_model=ManualGenerateResponse, status_code=202)
def regenerate_manual_candidate(request: CandidateActionRequest, background_tasks: BackgroundTasks):
    service = PhotoshootManualService()
    try:
        shot, job = service.regenerate(creator_profile_id=_creator_profile_id_required(), session_id=request.session_id, request_id=request.request_id)
    except Exception as error:
        _manual_error(error)
    background_tasks.add_task(_execute_manual_generation, request.session_id, job)
    return {"success": True, "session_id": request.session_id, "request_id": shot.request_id,
            "generation_job_id": job.job_id, "status": "generating"}


@router.post("/candidate/edit-prompt")
def edit_manual_candidate_prompt(request: CandidateActionRequest):
    try:
        prompt = PhotoshootManualService().edit_prompt(creator_profile_id=_creator_profile_id_required(), session_id=request.session_id, request_id=request.request_id)
    except Exception as error:
        _manual_error(error)
    return {"success": True, "message": "Candidate returned for prompt editing.", "prompt": prompt}


@router.post("/candidate/reject")
def reject_manual_candidate(request: CandidateActionRequest):
    try:
        PhotoshootManualService().reject(creator_profile_id=_creator_profile_id_required(), session_id=request.session_id, request_id=request.request_id)
    except Exception as error:
        _manual_error(error)
    return {"success": True, "message": "Candidate rejected."}


@router.post("/finish")
def finish_photoshoot(request: CreativeDirectorSessionRequest):
    try:
        return PhotoshootCurationService().review(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id)
    except Exception as error:
        _manual_error(error)


@router.get("/curation")
def photoshoot_curation_review(session_id: str):
    try:
        return PhotoshootCurationService().review(
            creator_profile_id=_creator_profile_id_required(), session_id=session_id)
    except Exception as error:
        _manual_error(error)


@router.post("/curation/confirm")
def photoshoot_curation_confirm(request: PhotoshootCurationRequest):
    try:
        return PhotoshootCurationService().confirm(
            creator_profile_id=_creator_profile_id_required(), session_id=request.session_id,
            selected_image_ids=request.selected_image_ids,
            photoshoot_decision=request.photoshoot_decision)
    except Exception as error:
        _manual_error(error)


@router.post("/stop-and-return-seed", response_model=PhotoshootReturnResponse)
def stop_photoshoot_and_return_seed():
    try:
        session, seed_id = PhotoshootManualService().stop_and_return_seed(
            creator_profile_id=_creator_profile_id_required(),
        )
    except Exception as error:
        _manual_error(error)
    return {
        "success": True,
        "message": "Photoshoot stopped. Seed returned to Generation Library.",
        "image_id": seed_id,
        "redirect": "/library/generations",
    }


@router.post("/return-to-library", response_model=PhotoshootReturnResponse)
def return_photoshoot_to_library():
    profile = _creator_profile()
    creator_profile_id = int(profile.get("id") or 0)
    if not creator_profile_id:
        raise HTTPException(status_code=400, detail="Creator Profile required before returning a Photoshoot.")
    queue = PhotoshootQueueService()
    session = queue.current_session(creator_profile_id=creator_profile_id)
    if session is None:
        raise HTTPException(status_code=404, detail="No pending Photoshoot was found.")
    seed_id = str(dict(session.creative_continuity or {}).get("seed_image_id") or "")
    if not seed_id:
        raise HTTPException(status_code=404, detail="No pending Photoshoot was found.")
    seed_request = next((
        request for request in queue.requests_for_session(session.session_id)
        if bool(dict(request.metadata or {}).get("is_seed_image"))
    ), None)
    if seed_request is not None and seed_request.status != "returned_to_library":
        queue.return_seed_request_to_library(seed_request.request_id, notes="Returned from Photoshoot Studio.")
    result = GenerationLibraryService().return_photoshoot_seed_to_library(seed_id)
    if not result.success:
        raise HTTPException(status_code=409, detail="; ".join(result.errors) or result.message)
    if queue.get_session(session.session_id).status != "cancelled":
        queue.cancel_session(session.session_id)
    return {"success": True, "message": result.message, "image_id": seed_id, "redirect": "/library/generations"}

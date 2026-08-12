"""Content Studio HTTP API."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from time import perf_counter
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from app.dashboard.config import load_dashboard_config
from app.config import settings
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.fanvue_account_repository import get_all_accounts
from app.services.creator_aware_canonical_prompt_planner import (
    CreatorAwareCanonicalPromptPlanner,
)
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


def _has_supported_image_signature(data: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/jpeg":
        return data.startswith(b"\xff\xd8\xff")
    if mime_type == "image/webp":
        return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


class TransformTagsRequest(BaseModel):
    tags: str
    explicit: bool = False
    origin: str | None = None
    plannerQuestion: str | None = None
    plannerItemId: str | None = None
    plannerItemTitle: str | None = None
    diagnosticTraceId: str | None = None


class PromptWorkshopRequest(BaseModel):
    lane: str = "premium"
    requestText: str
    promptCount: int


class PromptWorkshopUseRequest(BaseModel):
    promptNumber: int


class ExplicitGenerationInput(BaseModel):
    sourceText: str
    originalSource: str
    sourceType: str
    origin: str
    conceptTier: str | None = None
    requiredSemanticAttributes: dict = Field(default_factory=dict)
    requestedImageCount: int = 1
    collectionId: str | None = None
    lineage: dict = Field(default_factory=dict)

    def planning_metadata(self) -> dict:
        return {
            "source_text": self.sourceText.strip(),
            "original_source": self.originalSource.strip(),
            "source_type": self.sourceType.strip(),
            "origin": self.origin.strip(),
            "concept_tier": self.conceptTier,
            "required_semantic_attributes": dict(self.requiredSemanticAttributes),
            "requested_image_count": max(1, int(self.requestedImageCount or 1)),
            "collection_id": self.collectionId,
            "lineage": dict(self.lineage),
        }


class PromptPreviewRequest(BaseModel):
    creativeMode: str
    creativeTags: str
    promptCount: int
    lane: str = "social"
    explicitInput: ExplicitGenerationInput | None = None
    origin: str | None = None
    diagnosticTraceId: str | None = None


class GenerationSubmissionRequest(BaseModel):
    provider: str
    promptSource: str
    promptSourceLabel: str
    promptBatch: list[str] = Field(default_factory=list)
    creativeMode: str
    promptCount: int
    creatorContext: dict
    origin: str | None = None
    plannerLineage: dict | None = None
    lane: str = "social"
    explicitInput: ExplicitGenerationInput | None = None
    diagnosticTraceId: str | None = None


class AutonomousInspirationRequest(BaseModel):
    provider: str


class ExplicitBatchStartRequest(BaseModel):
    batchId: str
    provider: str
    concepts: list[dict] = Field(default_factory=list)


class ExplicitBatchProgressRequest(BaseModel):
    current: int
    total: int
    stage: str
    message: str
    metadata: dict = Field(default_factory=dict)
    terminalStatus: str | None = None


class ExplicitInspirationHandoffRequest(BaseModel):
    generationOperationId: str


def _analyze_recreate_image(
    *, image_bytes: bytes, image_mime_type: str, image_name: str,
) -> dict:
    creator_profile, creative_director = _creative_director_context(
        require_reference=True
    )
    analysis = creative_director.analyze_inspiration_scene(
        image_bytes=image_bytes, image_mime_type=image_mime_type,
        image_name=image_name,
    )
    return {
        "success": True, "error": None,
        "creatorProfileId": int(creator_profile["id"]),
        "analysis": analysis.as_dict(),
    }


class ExplicitInspirationRequest(BaseModel):
    tierMode: Literal["softcore", "hardcore", "both"] = "both"
    count: int | None = Field(default=None, ge=1, le=12)
    countPerTier: int | None = Field(default=5, ge=1, le=12)
    # Backward-compatible alias used by older clients.
    conceptCount: int | None = None


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


def _enhance_with_canonical_planner(*, account_id: int | str, concept: str) -> str:
    """Use the canonical planner's single enhancement path for social concepts."""
    from app.services.canonical_planner_enhancement_service import (
        CanonicalPlannerEnhancementService,
    )

    return CanonicalPlannerEnhancementService().enhance(
        fanvue_account_id=account_id,
        selected_item=concept,
    )


def _enhance_tags(request: TransformTagsRequest) -> dict:
    creator_profile, creative_director = _creative_director_context()
    tags = request.tags.strip()
    if not tags:
        raise ValueError("Tags are required.")
    if request.origin == "canonical_planner":
        if request.explicit:
            raise ValueError("Canonical Planner enhancement must use the premium lane.")
        account_id = creator_profile.get("fanvue_account_id") or _current_account_id()
        if account_id is None:
            raise ValueError("Creator account required before enhancing planner ideas.")
        enhanced_tags = _enhance_with_canonical_planner(
            account_id=account_id, concept=tags,
        )
    elif request.origin == "manual_creative_concept":
        if request.explicit:
            raise ValueError("Manual Creative Concept enhancement must use the premium lane.")
        account_id = creator_profile.get("fanvue_account_id") or _current_account_id()
        if account_id is None:
            raise ValueError("Creator account required before enhancing a Creative Concept.")
        from app.services.generation_request_diagnostic_service import (
            GenerationRequestDiagnosticService,
        )
        diagnostic = GenerationRequestDiagnosticService()
        diagnostic.record(
            trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
            stage="1_workflow_origin", value=request.origin,
        )
        diagnostic.record(
            trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
            stage="2_initial_creative_input", value=tags,
        )
        diagnostic.record(
            trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
            stage="3_ava_creator_context_supplied",
            value={"promptConstructionPath": "canonical_planner_enhancement"},
        )
        enhanced_tags = _enhance_with_canonical_planner(
            account_id=account_id, concept=tags,
        )
        diagnostic.record(
            trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
            stage="4_enhanced_creative_intent", value=enhanced_tags,
        )
    elif request.origin == "recreate_with_ava":
        if request.explicit:
            raise ValueError("Manual Creative Concept enhancement must use the premium lane.")
        from app.services.manual_creative_concept_enhancement_service import (
            ManualCreativeConceptEnhancementService,
        )
        account_id = creator_profile.get("fanvue_account_id") or _current_account_id()
        if account_id is None:
            raise ValueError("Creator account required before enhancing a Creative Concept.")
        enhanced_tags = ManualCreativeConceptEnhancementService().enhance(
            fanvue_account_id=account_id,
            creative_concept=tags,
            include_canonical_ava=False,
        )
    else:
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
    lane = request.lane.strip().lower()
    if lane not in {"social", "explicit"}:
        raise ValueError("Content Studio lane must be social or explicit.")
    if lane == "social" and creative_mode not in PREMIUM_CREATIVE_MODE_LABELS:
        raise ValueError("Select a Premium creative mode.")
    if lane == "explicit":
        creative_mode = "explicit"
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
        metadata={
            "explicit_input": request.explicitInput.planning_metadata()
        } if request.explicitInput else None,
    )
    metadata = dict(plan.prompt_metadata or {})
    prompts = [
        str(prompt).strip()
        for prompt in metadata.get("prompt_variations") or ()
        if str(prompt).strip()
    ][: request.promptCount]
    if not prompts:
        prompts = [str(plan.prompt_text or "").strip()]
    from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
    diagnostic = GenerationRequestDiagnosticService()
    diagnostic.record(
        trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
        stage="5_prompt_plan_input",
        value={"creativeTags": creative_tags, "creativeMode": creative_mode,
               "promptCount": request.promptCount, "lane": lane},
    )
    diagnostic.record(
        trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
        stage="6_prompt_plan_output_and_variations",
        value={"planId": plan.plan_id, "promptText": plan.prompt_text,
               "promptMetadata": metadata, "variations": prompts},
    )
    diagnostic.record(trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
                      stage="7_prompt_before_render_locks", value=prompts)
    if lane == "explicit" or creative_mode in {
        "premium_teaser", "spicy", "story_sequence"
    }:
        from app.services.seedream_premium_render_locks import (
            enforce_premium_render_body_lock,
        )

        prompts = [enforce_premium_render_body_lock(prompt) for prompt in prompts]
        metadata["provider_prompt_preview"] = True
        metadata["provider_target"] = (
            "provider_selected" if lane == "explicit" else "seedream_5_0_pro"
        )
    diagnostic.record(trace_id=request.diagnosticTraceId, workflow_origin=request.origin,
                      stage="8_prompt_after_render_locks", value=prompts)
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
    creator_profile, creative_director = _creative_director_context(
        require_reference=False
    )
    account_id = creator_profile.get("fanvue_account_id") or _current_account_id()
    if account_id is None:
        raise ValueError("Creator account required before using Content Studio.")
    creator_aware_question = CreatorAwareCanonicalPromptPlanner().build_question(
        fanvue_account_id=account_id,
        question=prompt,
    )
    answer = creative_director.ask_anything(
        question=creator_aware_question,
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


def _background_generation_run_content(run_id: str) -> dict | None:
    """Compatibility shape for the existing Content Studio result UI."""
    from app.services.background_operation_service import BackgroundOperationService

    account_id = _current_account_id()
    if account_id is None:
        return None
    creator = get_active_creator_profile(str(account_id))
    if not creator:
        return None
    try:
        service = BackgroundOperationService()
        operation = service.get(run_id, creator_profile_id=int(creator["id"]), account_id=account_id)
    except Exception:
        return None
    if operation is None or operation.operation_type not in {
        "content_studio_generation", "content_studio_autonomous_inspiration",
    }:
        return None
    metadata = dict(operation.metadata or {})
    outputs = tuple(str(item) for item in metadata.get("outputReferences") or ())
    status = {
        "QUEUED": "queued", "RUNNING": "running", "WAITING_EXTERNAL": "running",
        "SUCCEEDED": "succeeded", "PARTIAL": "partial", "FAILED": "failed",
        "CANCEL_REQUESTED": "running", "CANCELLED": "failed",
    }.get(operation.status, operation.status.lower())
    generation = {
        "runId": str(operation.operation_id),
        "jobId": operation.result_reference or metadata.get("jobId"),
        "promptPlanId": metadata.get("promptPlanId"),
        "status": status,
        "message": operation.error_message or operation.stage_message or "Generation queued",
        "provider": metadata.get("provider") or dict(metadata.get("request") or {}).get("provider"),
        "completedCount": int(metadata.get("completedCount") or len(outputs)),
        "failedCount": int(metadata.get("failedCount") or 0),
        "processedCount": int(operation.progress_current),
        "totalCount": int(operation.progress_total),
        "progress": float(operation.progress_percent),
        "images": [
            {"index": index, "url": f"/api/v1/content-studio/generations/{run_id}/images/{index}"}
            for index, _ in enumerate(outputs)
        ],
    }
    return {"success": True, "error": None, "generation": generation}


def _update_generation_run(run_id: str, **values) -> None:
    with _generation_runs_lock:
        if run_id in _generation_runs:
            _generation_runs[run_id].update(values)


def _execute_content_studio_generation(run_id: str, request: GenerationSubmissionRequest,
                                       *, state_callback=None, account_id: int | None = None) -> dict:
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

    def update(**values):
        _update_generation_run(run_id, **values)
        if state_callback is not None:
            state_callback(dict(values))

    try:
        if account_id is None:
            creator_profile, creative_director = _creative_director_context()
        else:
            from app.repositories.creator_profile_repository import get_active_creator_profile
            from app.services.reference_library_service import ReferenceLibraryService
            creator_profile = get_active_creator_profile(str(account_id))
            if not creator_profile:
                raise ValueError("Creator Profile required before using Content Studio.")
            creative_director = CreativeDirectorService(
                reference_library_service=ReferenceLibraryService())
        lane = request.lane.strip().lower()
        if lane not in {"social", "explicit"}:
            raise ValueError("Content Studio lane must be social or explicit.")
        if lane == "social" and request.creativeMode not in PREMIUM_CREATIVE_MODE_LABELS:
            raise ValueError("Select a Premium creative mode.")
        creative_mode = "explicit" if lane == "explicit" else request.creativeMode
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
        update(status="planning", message="Creating prompt plan", provider=provider_label)
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
            creative_mode=creative_mode,
            prompt_count=request.promptCount,
            provider_id=request.provider,
            prompt_batch=prompts,
            origin=request.origin,
            planner_lineage=request.plannerLineage,
            explicit_input=(
                request.explicitInput.planning_metadata()
                if request.explicitInput else None
            ),
            **({"diagnostic_trace_id": request.diagnosticTraceId}
               if request.diagnosticTraceId else {}),
        )
        update(status="queued", jobId=job.job_id, message="Queued Image 1")

        known_outputs: tuple[str, ...] = ()

        def progress_callback(**event) -> None:
            nonlocal known_outputs
            outputs = tuple(str(value) for value in event.get("output_references") or () if str(value))
            with _generation_runs_lock:
                previous_outputs = tuple((_generation_runs.get(run_id) or {}).get("outputReferences") or ())
            outputs = tuple(dict.fromkeys((*known_outputs, *previous_outputs, *outputs)))
            known_outputs = outputs
            completed = max(int(event.get("completed_count") or event.get("current") or 0), len(outputs))
            failed = int(event.get("failed_count") or 0)
            processed = int(event.get("processed_count") or completed + failed)
            update(
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
        final = dict(
            status=final_status,
            message=message,
            completedCount=completed,
            failedCount=failed,
            processedCount=completed + failed,
            progress=100.0,
            outputReferences=outputs,
            promptPlanId=plan.plan_id,
        )
        update(**final)
        return final
    except ValueError as error:
        final = {"status": "failed", "message": str(error), "failedCount": request.promptCount,
                 "processedCount": request.promptCount, "progress": 100.0}
        update(**final); return final
    except Exception as error:
        logger.exception("Content Studio generation failed")
        final = {"status": "failed", "message": "Generation failed. Please try again.",
                 "failedCount": request.promptCount, "processedCount": request.promptCount,
                 "progress": 100.0, "error": str(error)}
        update(**final); return final


def _execute_autonomous_inspiration(
    run_id: str,
    request: AutonomousInspirationRequest,
    *, state_callback=None, account_id: int | None = None,
    directions_override: tuple[str, ...] = (),
) -> dict:
    from app.services.autonomous_inspiration_engine import (
        AutonomousInspirationEngine,
    )

    def update(**values):
        _update_generation_run(run_id, **values)
        if state_callback is not None:
            state_callback(dict(values))

    try:
        account_id = account_id if account_id is not None else _current_account_id()
        if account_id is None:
            raise ValueError(
                "Creator account required before using autonomous inspiration."
            )
        update(status="planning", message="Building creative direction")
        directions = directions_override or AutonomousInspirationEngine().create_directions(
            fanvue_account_id=account_id, diagnostic_trace_id=run_id)
        update(status="planning", message="Creating prompt plan",
               inspirationDirections=list(directions))
        generation_request = GenerationSubmissionRequest(
            provider=request.provider,
            promptSource="\n".join(directions),
            promptSourceLabel="Original Tags",
            promptBatch=[],
            creativeMode="premium_teaser",
            promptCount=AutonomousInspirationEngine.IMAGE_COUNT,
            creatorContext={},
            origin="autonomous_inspiration",
            diagnosticTraceId=run_id,
        )
        return _execute_content_studio_generation(
            run_id, generation_request, state_callback=state_callback,
            account_id=account_id)
    except ValueError as error:
        final = dict(
            status="failed",
            message=str(error),
            failedCount=AutonomousInspirationEngine.IMAGE_COUNT,
            processedCount=AutonomousInspirationEngine.IMAGE_COUNT,
            progress=100.0,
        )
        update(**final)
        return final
    except Exception as error:
        logger.exception("Autonomous inspiration failed")
        final = dict(
            status="failed",
            message="Autonomous inspiration failed. Please try again.",
            failedCount=AutonomousInspirationEngine.IMAGE_COUNT,
            processedCount=AutonomousInspirationEngine.IMAGE_COUNT,
            progress=100.0,
            error=str(error),
        )
        update(**final)
        return final


async def _run_tag_action(
    action,
    *,
    action_type: str = "creative_tag_action",
    correlation_id: str | None = None,
) -> JSONResponse:
    request_id = correlation_id or uuid4().hex
    timeout_seconds = settings.CREATIVE_TAG_API_DEADLINE_SECONDS
    started = perf_counter()
    try:
        # The synchronous Grok transport has a shorter timeout than this API
        # deadline. Cancelling to_thread cannot stop an already-running thread,
        # so the downstream timeout must always fire first.
        content = await asyncio.wait_for(
            asyncio.to_thread(action),
            timeout=timeout_seconds,
        )
        return JSONResponse(status_code=200, content=content)
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error), "tags": ""},
        )
    except asyncio.TimeoutError:
        elapsed_seconds = perf_counter() - started
        logger.warning(
            "Content Studio creative tag action timed out "
            "action_type=%s timeout_seconds=%s elapsed_seconds=%.3f request_id=%s",
            action_type,
            timeout_seconds,
            elapsed_seconds,
            request_id,
            exc_info=True,
        )
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


@router.post("/creative-tags/enhance")
async def enhance_content_studio_tags(request: TransformTagsRequest) -> JSONResponse:
    return await _run_tag_action(
        lambda: _enhance_tags(request),
        action_type="creative_tags.enhance",
    )


@router.post("/creative-tags/surprise")
async def surprise_content_studio_tags(request: TransformTagsRequest) -> JSONResponse:
    return await _run_tag_action(
        lambda: _surprise_tags(request),
        action_type="creative_tags.surprise",
    )


@router.post("/prompt-workshop/generate")
async def generate_content_studio_prompt_workshop(request: PromptWorkshopRequest) -> JSONResponse:
    return await _run_tag_action(
        lambda: _generate_prompt_workshop_batch(request),
        action_type="prompt_workshop.generate",
    )


@router.get("/prompt-workshop/archive")
async def get_content_studio_prompt_workshop_archive() -> JSONResponse:
    return await _run_tag_action(
        _read_prompt_workshop_archive,
        action_type="prompt_workshop.archive.read",
    )


@router.post("/prompt-workshop/archive/{batch_id}/use")
async def mark_content_studio_prompt_workshop_used(
    batch_id: str,
    request: PromptWorkshopUseRequest,
) -> JSONResponse:
    return await _run_tag_action(
        lambda: _mark_prompt_workshop_used(batch_id, request),
        action_type="prompt_workshop.archive.use",
    )


@router.post("/prompt-preview")
async def create_content_studio_prompt_preview(request: PromptPreviewRequest) -> JSONResponse:
    return await _run_tag_action(
        lambda: _create_prompt_preview(request),
        action_type="prompt_preview.create",
    )


@router.post("/explicit/inspire")
def inspire_explicit_content(request: ExplicitInspirationRequest):
    from app.services.background_operation_service import BackgroundOperationService
    from app.services.explicit_inspiration_service import ExplicitInspirationService

    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not creator:
        return JSONResponse(status_code=400, content={"success": False, "error": "Active Creator Profile required."})
    uses_new_contract = request.count is not None or "tierMode" in request.model_fields_set
    legacy_count = None if uses_new_contract else (
        request.conceptCount if request.conceptCount is not None else request.countPerTier
    )
    mode = request.tierMode if uses_new_contract else "both"
    count = int(request.count if request.count is not None else (legacy_count or 5) * 2)
    if count < 1 or count > (ExplicitInspirationService.MAX_CONCEPT_COUNT if uses_new_contract else 24):
        return JSONResponse(status_code=400, content={"success": False, "error": "Explicit inspiration count is invalid."})
    softcore_count = count if mode == "softcore" else (count + 1) // 2 if mode == "both" else 0
    hardcore_count = count if mode == "hardcore" else count // 2 if mode == "both" else 0
    label = (f"Generating {count} ideas — {softcore_count} Softcore + {hardcore_count} Hardcore…"
             if mode == "both" else f"Generating {count} {mode.title()} {'idea' if count == 1 else 'ideas'}…")
    service = BackgroundOperationService()
    operation, created = service.create(
        operation_type="content_studio_explicit_inspiration", originating_workspace="content_studio",
        creator_profile_id=int(creator["id"]), account_id=int(account_id),
        subject_type="creator_profile", subject_id=str(creator["id"]),
        idempotency_key=f"content-studio-explicit-inspiration:{creator['id']}",
        executor_key="content_studio_explicit_inspiration", progress_total=int(hardcore_count > 0) + int(softcore_count > 0),
        current_stage="QUEUED", stage_message=label, result_location="/studio/content",
        cancellation_supported=True,
        metadata={"phase": "QUEUED", "tierMode": mode, "requestedCount": count,
                  "softcoreCount": softcore_count, "hardcoreCount": hardcore_count,
                  "requestLabel": label, "conceptGenerationStatus": "QUEUED",
                  "hardcore": [], "softcore": [], "concepts": [], "tierErrors": {}},
    )
    return {"success": True, "error": None, "operationId": str(operation.operation_id),
            "reused": not created, "operation": service.payload(operation)}


@router.post("/explicit/inspire/{operation_id}/handoff")
def handoff_explicit_inspiration(operation_id: str, request: ExplicitInspirationHandoffRequest):
    from app.services.background_operation_service import BackgroundOperationService
    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    service = BackgroundOperationService()
    operation = service.get(operation_id, creator_profile_id=int(creator.get("id") or 0), account_id=account_id)
    if operation is None or operation.operation_type != "content_studio_explicit_inspiration":
        return JSONResponse(status_code=404, content={"success": False, "error": "Explicit inspiration operation not found."})
    if str(operation.current_stage or "") != "WAITING_SELECTION":
        return JSONResponse(status_code=409, content={"success": False, "error": "Explicit concepts are not ready for handoff."})
    updated = service.succeed(
        operation_id, result_reference=request.generationOperationId,
        message="Explicit concepts handed off to generation.",
        metadata={"phase": "HANDED_OFF", "generationOperationId": request.generationOperationId},
    )
    return {"success": True, "operation": service.payload(updated)}


@router.post("/explicit/inspire/{operation_id}/discard")
def discard_explicit_inspiration(operation_id: str):
    from app.services.background_operation_service import BackgroundOperationService
    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    service = BackgroundOperationService()
    operation = service.get(operation_id, creator_profile_id=int(creator.get("id") or 0), account_id=account_id)
    if operation is None or operation.operation_type != "content_studio_explicit_inspiration":
        return JSONResponse(status_code=404, content={"success": False, "error": "Explicit inspiration operation not found."})
    if str(operation.current_stage or "") != "WAITING_SELECTION":
        return JSONResponse(status_code=409, content={"success": False, "error": "Only concepts waiting for selection can be discarded."})
    updated = service.cancel(operation_id, "Explicit inspiration discarded by operator.")
    return {"success": True, "operation": service.payload(updated)}


@router.post("/explicit/batches")
def start_explicit_batch(request: ExplicitBatchStartRequest):
    from app.services.background_operation_service import BackgroundOperationService
    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not creator:
        return JSONResponse(status_code=400, content={"success": False, "error": "Active Creator Profile required."})
    total = len(request.concepts)
    if total < 1:
        return JSONResponse(status_code=400, content={"success": False, "error": "Select at least one explicit concept."})
    service = BackgroundOperationService()
    operation, created = service.create(
        operation_type="content_studio_explicit_batch", originating_workspace="content_studio",
        creator_profile_id=int(creator["id"]), account_id=int(account_id),
        subject_type="creator_profile", subject_id=str(creator["id"]),
        idempotency_key=f"content-studio-explicit-batch:{request.batchId}",
        executor_key="content_studio_explicit_batch_client", progress_total=total,
        current_stage="PREPARING", stage_message=f"Preparing idea 1 of {total}...",
        result_location="/studio/content", cancellation_supported=False,
        metadata={"batchId": request.batchId, "provider": request.provider,
                  "concepts": request.concepts, "items": [], "completedIdeas": 0,
                  "failedIdeas": 0, "currentIdeaIndex": 1, "phase": "preparing"},
    )
    if created:
        operation = service.repository.transition(
            operation.operation_id, "RUNNING", stage="PREPARING",
            message=f"Preparing idea 1 of {total}...",
        )
    return {"success": True, "operationId": str(operation.operation_id), "reused": not created}


@router.post("/explicit/batches/{operation_id}/progress")
def update_explicit_batch(operation_id: str, request: ExplicitBatchProgressRequest):
    from app.services.background_operation_service import BackgroundOperationService
    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    service = BackgroundOperationService()
    operation = service.get(operation_id, creator_profile_id=int(creator.get("id") or 0), account_id=account_id)
    if operation is None or operation.operation_type != "content_studio_explicit_batch":
        return JSONResponse(status_code=404, content={"success": False, "error": "Explicit batch not found."})
    terminal = str(request.terminalStatus or "").upper()
    if terminal in {"SUCCEEDED", "PARTIAL"}:
        updated = service.succeed(operation_id, partial=terminal == "PARTIAL",
                                  message=request.message, metadata=request.metadata)
    elif terminal == "FAILED":
        updated = service.fail(operation_id, request.message, metadata=request.metadata)
    else:
        updated = service.progress(
            operation_id, current=request.current, total=request.total,
            percent=request.current / max(1, request.total) * 100,
            stage=request.stage, message=request.message, metadata=request.metadata,
        )
    return {"success": True, "operation": service.payload(updated)}


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


@router.post("/recreate/analyze")
async def analyze_recreate_inspiration(image: UploadFile = File(...)) -> JSONResponse:
    suffix = Path(image.filename or "").suffix.lower()
    if image.content_type not in PLANNER_IMAGE_TYPES or suffix not in PLANNER_IMAGE_SUFFIXES:
        return JSONResponse(status_code=400, content={"success": False, "error": "Use one PNG, JPG, JPEG, or WEBP image."})
    image_bytes = await image.read(PLANNER_IMAGE_MAX_BYTES + 1)
    if not image_bytes:
        return JSONResponse(status_code=400, content={"success": False, "error": "An inspiration image is required."})
    if len(image_bytes) > PLANNER_IMAGE_MAX_BYTES:
        return JSONResponse(status_code=400, content={"success": False, "error": "The inspiration image is too large."})
    if not _has_supported_image_signature(image_bytes, image.content_type or ""):
        return JSONResponse(status_code=400, content={"success": False, "error": "The uploaded file is not a valid supported image."})
    try:
        content = await asyncio.wait_for(asyncio.to_thread(
            _analyze_recreate_image,
            image_bytes=image_bytes,
            image_mime_type=image.content_type,
            image_name=image.filename or "inspiration",
        ), timeout=60)
        return JSONResponse(status_code=200, content=content)
    except ValueError as error:
        return JSONResponse(status_code=400, content={"success": False, "error": str(error)})
    except asyncio.TimeoutError:
        return JSONResponse(status_code=503, content={"success": False, "error": "Inspiration analysis timed out. Please retry."})
    except Exception:
        logger.exception("Recreate With Ava analysis failed")
        return JSONResponse(status_code=503, content={"success": False, "error": "Inspiration analysis failed. Please retry."})


@router.post("/generations")
async def submit_content_studio_generation(
    request: GenerationSubmissionRequest,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    # Planner batches and Recreate's composite orchestration remain intentionally
    # on their existing execution path during Phase 1.
    if request.origin not in {"canonical_planner", "recreate_with_ava"}:
        from app.services.background_operation_service import BackgroundOperationService

        account_id = _current_account_id()
        creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
        if not creator:
            return JSONResponse(status_code=400, content={"success": False,
                                "error": "Active Creator Profile required."})
        operation, created = BackgroundOperationService().create(
            operation_type="content_studio_generation",
            originating_workspace="content_studio",
            creator_profile_id=int(creator["id"]),
            account_id=int(account_id),
            subject_type="creator_profile",
            subject_id=str(creator["id"]),
            idempotency_key=f"content-studio-generation:{creator['id']}",
            executor_key="content_studio_generation",
            progress_total=request.promptCount,
            current_stage="QUEUED",
            stage_message="Generation queued",
            result_location="/studio/content",
            cancellation_supported=False,
            metadata={"request": request.model_dump(), "provider": request.provider,
                      "completedCount": 0, "failedCount": 0, "outputReferences": []},
        )
        return JSONResponse(status_code=202, content={
            "success": True, "error": None, "runId": str(operation.operation_id),
            "operationId": str(operation.operation_id), "reused": not created,
        })
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


@router.post("/inspire")
async def submit_autonomous_inspiration(
    request: AutonomousInspirationRequest,
) -> JSONResponse:
    from app.services.autonomous_inspiration_engine import AutonomousInspirationEngine
    from app.services.background_operation_service import BackgroundOperationService

    account_id = _current_account_id()
    creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
    if not creator:
        return JSONResponse(status_code=400, content={"success": False,
                            "error": "Active Creator Profile required."})
    operation, created = BackgroundOperationService().create(
        operation_type="content_studio_autonomous_inspiration",
        originating_workspace="content_studio",
        creator_profile_id=int(creator["id"]), account_id=int(account_id),
        subject_type="creator_profile", subject_id=str(creator["id"]),
        idempotency_key=f"content-studio-autonomous-inspiration:{creator['id']}:{account_id}",
        executor_key="content_studio_autonomous_inspiration",
        progress_total=AutonomousInspirationEngine.IMAGE_COUNT,
        current_stage="PREPARING_INSPIRATION",
        stage_message="Preparing inspiration",
        result_location="/studio/content", cancellation_supported=False,
        metadata={
            "request": request.model_dump(),
            "provider": request.provider,
            "imageCount": AutonomousInspirationEngine.IMAGE_COUNT,
            "contentMode": "social",
            "creativeMode": "premium_teaser",
            "completedCount": 0, "failedCount": 0, "outputReferences": [],
        },
    )
    return JSONResponse(
        status_code=202,
        content={"success": True, "error": None,
                 "runId": str(operation.operation_id),
                 "operationId": str(operation.operation_id), "reused": not created},
    )


@router.get("/generations/{run_id}")
async def get_content_studio_generation(run_id: str) -> JSONResponse:
    try:
        background = _background_generation_run_content(run_id)
        if background is not None:
            return JSONResponse(status_code=200, content=background)
        return JSONResponse(status_code=200, content=_generation_run_content(run_id))
    except ValueError as error:
        return JSONResponse(status_code=404, content={"success": False, "error": str(error)})


@router.get("/generations/{run_id}/images/{image_index}")
async def get_content_studio_generation_image(run_id: str, image_index: int) -> Response:
    outputs: tuple[str, ...] = ()
    background = _background_generation_run_content(run_id)
    if background is not None:
        from app.services.background_operation_service import BackgroundOperationService
        account_id = _current_account_id()
        creator = get_active_creator_profile(str(account_id)) if account_id is not None else {}
        operation = BackgroundOperationService().get(
            run_id, creator_profile_id=int(creator["id"]), account_id=account_id)
        outputs = tuple(str(item) for item in dict(operation.metadata).get("outputReferences") or ())
    else:
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

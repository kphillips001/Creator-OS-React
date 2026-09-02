"""Creator OS Photoshoot Queue service."""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import tempfile
import time
from contextlib import contextmanager
from threading import RLock
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.creative_director import PromptPlan, new_id
from app.models.generation_engine import GenerationMediaType, GenerationType, utc_now
from app.models.render_policy import photoshoot_render_policy
from app.models.photoshoot_queue import (
    CanonicalPhotoshootSeedSummary,
    PHOTOSHOOT_ASSET_METADATA_KEY,
    PhotoshootProgress,
    PhotoshootRequest,
    PhotoshootResult,
    PhotoshootSession,
    normalize_target_shot_count,
)
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class PhotoshootPreparationRequired(RuntimeError):
    def __init__(self, message: str, *, request_id: str, generation_job_id: str):
        super().__init__(message)
        self.request_id = request_id
        self.generation_job_id = generation_job_id


class PhotoshootQueueService:
    """Owns creative sequencing and review-gated photoshoot progress."""

    DEFAULT_STORAGE_DIR = Path("data") / "photoshoot_queue"
    _extension_lock = RLock()

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        generation_ingestion_service: GenerationResultIngestionService | None = None,
        asset_repository=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR).resolve()
        self.generation_ingestion = generation_ingestion_service or GenerationResultIngestionService()
        self.asset_repository = asset_repository

    @property
    def sessions_path(self) -> Path:
        return self.storage_dir / "photoshoot_sessions.json"

    @property
    def requests_path(self) -> Path:
        return self.storage_dir / "photoshoot_requests.json"

    @property
    def assets(self):
        if self.asset_repository is not None:
            return self.asset_repository
        return self.generation_ingestion.assets

    def create_session(
        self,
        *,
        creator_profile_id: int,
        prompt_plans: Iterable[PromptPlan],
        title: str = "Photoshoot Session",
        provider_id: str = "seedream_5_0_pro",
        reference_asset_id: int | None = None,
        creator_notes: str | None = None,
        creative_continuity: Mapping[str, Any] | None = None,
        target_shot_count: int = 5,
    ) -> PhotoshootSession:
        plans = tuple(prompt_plans)
        if not plans:
            raise ValueError("At least one Prompt Plan is required.")
        session_id = new_id("photoshoot_session")
        requests = tuple(
            PhotoshootRequest(
                request_id=new_id("photoshoot_request"),
                session_id=session_id,
                prompt_plan_id=plan.plan_id,
                prompt_text=plan.prompt_text,
                sequence_index=index,
                creative_mode=plan.creative_mode,
                reference_asset_id=plan.reference_asset_id if reference_asset_id is None else reference_asset_id,
                metadata={
                    "creative_tags": tuple(plan.creative_tags),
                    "prompt_metadata": dict(plan.prompt_metadata or {}),
                },
            )
            for index, plan in enumerate(plans, start=1)
        )
        session = PhotoshootSession(
            session_id=session_id,
            creator_profile_id=int(creator_profile_id),
            title=title,
            reference_asset_id=reference_asset_id if reference_asset_id is not None else plans[0].reference_asset_id,
            creative_mode=plans[0].creative_mode,
            target_shot_count=normalize_target_shot_count(target_shot_count),
            provider_id=provider_id,
            creator_notes=creator_notes,
            creative_continuity={
                "prompt_count": len(plans),
                "target_shot_count": normalize_target_shot_count(target_shot_count),
                "generation_mode_behavior": "photoshoot_queue",
                "wavespeed_generation_mode_key": "photoshoot_set",
                "continuity": (
                    "Wavespeed Photoshoot Queue Mode: preserve the same selected-shot or requested location, "
                    "wardrobe, lighting, mood, story, environment, camera style, and creative concept across "
                    "ordered prompts. Vary only pose, camera angle, framing, crop, expression, hand placement, "
                    "posture, distance from camera, eye contact, and body orientation."
                ),
                "normal_generation_boundary": (
                    "Do not use normal generation scene-hopping here. Photoshoot Queue is the continuity workflow."
                ),
                **dict(creative_continuity or {}),
            },
            request_ids=tuple(request.request_id for request in requests),
        )
        self._mutate_json(self.sessions_path, lambda items: [asdict(session), *items])
        self._mutate_json(
            self.requests_path,
            lambda items: [*items, *(asdict(request) for request in requests)],
        )
        return session

    def queue_next_prompt(
        self,
        *,
        session_id: str,
        generation_engine: GenerationEngineService,
    ):
        session = self.get_session(session_id)
        if session.status == "paused":
            raise ValueError("Photoshoot Session is paused.")
        if session.status in {"cancelled", "completed"}:
            raise ValueError(f"Photoshoot Session is {session.status}.")
        active = self.current_request(session_id)
        if active and active.status in {"generating", "awaiting_review"}:
            return None
        next_request = self.next_queued_request(session_id)
        if next_request is None:
            completed = replace(session, status="completed", current_request_id=None, updated_at=utc_now())
            self._replace_session(completed)
            return None
        plan = self._prompt_plan_from_request(next_request, session.creator_profile_id)
        frozen_identity = dict((session.creative_continuity or {}).get("canonical_identity_reference") or {})
        frozen_identity_path = str(frozen_identity.get("path") or "").strip()
        seed_image_id = str(dict(session.creative_continuity or {}).get("seed_image_id") or "").strip()
        seed_output_reference = str(dict(session.creative_continuity or {}).get("seed_output_reference") or "").strip()
        previous_image_id = str(dict(next_request.metadata or {}).get("active_reference_image_id") or seed_image_id).strip()
        previous_output_reference = str(
            dict(next_request.metadata or {}).get("active_reference_output_reference") or seed_output_reference
        ).strip()
        if (session.creative_continuity or {}).get("canonical_identity_reference_frozen") and not frozen_identity_path:
            raise ValueError("The frozen canonical identity reference is unavailable for this Photoshoot.")
        job = generation_engine.queue_prompt_plan(
            creator_profile={"id": session.creator_profile_id},
            prompt_plan=plan,
            provider_id=session.provider_id,
            generation_type=GenerationType.IMAGE_TO_IMAGE.value,
            media_type=GenerationMediaType.IMAGE.value,
            image_count=1,
            metadata={
                "source": "photoshoot_queue",
                "workflow_type": "photoshoot",
                "render_policy": photoshoot_render_policy(session.creative_mode).value,
                "generation_mode_behavior": "photoshoot_queue",
                "wavespeed_generation_mode_key": "photoshoot_set",
                "wavespeed_mode_decision": (
                    "Photoshoot Queue uses Wavespeed Photoshoot Set Mode: same environment, same wardrobe, "
                    "same lighting, same mood, ordered progression. It must not use normal generation "
                    "scene-hopping."
                ),
                "photoshoot_session_id": session.session_id,
                "photoshoot_request_id": next_request.request_id,
                "photoshoot_sequence_index": next_request.sequence_index,
                "active_reference_image_id": (
                    previous_image_id
                ),
                "creative_continuity": dict(session.creative_continuity or {}),
                **({
                    "canonical_identity_reference_asset_id": int(frozen_identity.get("asset_id") or 0),
                    "canonical_identity_reference_path": frozen_identity_path,
                    "canonical_reference_image_url": frozen_identity_path,
                    "require_frozen_photoshoot_identity": True,
                } if frozen_identity_path else {}),
                **(
                    {
                        "reference_image_url": previous_output_reference,
                        "photoshoot_continuity_reference_image_url": previous_output_reference,
                        "previous_approved_continuity_reference_image_id": previous_image_id,
                        "previous_approved_continuity_reference_image_url": previous_output_reference,
                        **({
                            "original_photoshoot_seed_image_id": seed_image_id,
                            "original_photoshoot_seed_reference_image_url": seed_output_reference,
                        } if seed_output_reference else {}),
                    }
                    if previous_output_reference
                    else {}
                ),
            },
        )
        updated_request = replace(
            next_request,
            status="generating",
            generation_job_id=job.job_id,
            metadata={
                key: value for key, value in dict(next_request.metadata or {}).items()
                if key != "last_generation_failure"
            },
            updated_at=utc_now(),
        )
        updated_session = replace(
            session,
            status="running",
            current_request_id=next_request.request_id,
            creative_continuity={
                **dict(session.creative_continuity or {}),
                "workflow_stage": "generating",
            },
            updated_at=utc_now(),
        )
        try:
            self._replace_request(updated_request)
            self._replace_session(updated_session)
        except Exception as error:
            try:
                self.mark_preparation_required(
                    next_request.request_id, generation_job_id=job.job_id, reason=str(error),
                )
            except Exception:
                logging.getLogger("creator_os.photoshoot.queue").exception(
                    "preparation_recovery_marker_failed request_id=%s job_id=%s",
                    next_request.request_id, job.job_id,
                )
            raise PhotoshootPreparationRequired(
                str(error), request_id=next_request.request_id, generation_job_id=job.job_id,
            ) from error
        return job

    def mark_generation_complete(
        self,
        *,
        generation_job_id: str,
        imported_asset_ids: Iterable[int] = (),
        generated_image_ids: Iterable[str] = (),
    ) -> PhotoshootRequest | None:
        request = self.request_for_generation_job(generation_job_id)
        if request is None:
            return None
        asset_ids = tuple(int(asset_id) for asset_id in imported_asset_ids if asset_id is not None)
        generated_ids = tuple(str(image_id) for image_id in generated_image_ids if str(image_id))
        completed_metadata = dict(request.metadata or {})
        completed_metadata.pop("last_generation_failure", None)
        completed_metadata.pop("finalization_required", None)
        completed_metadata.pop("finalization_error", None)
        updated = replace(
            request,
            status="awaiting_review",
            imported_asset_ids=asset_ids,
            metadata={**completed_metadata, "generated_image_ids": generated_ids},
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        self._associate_assets(updated)
        session = self.get_session(updated.session_id)
        continuity = dict(session.creative_continuity or {})
        self._replace_session(
            replace(
                session,
                current_request_id=updated.request_id,
                creative_continuity={
                    **continuity,
                    "workflow_stage": "awaiting_review",
                },
                updated_at=utc_now(),
            )
        )
        return updated

    def mark_generation_failed(self, generation_job_id: str, *, reason: str | None = None) -> PhotoshootRequest | None:
        request = self.request_for_generation_job(generation_job_id)
        if request is None:
            return None
        updated = replace(
            request,
            status="queued",
            metadata={
                **dict(request.metadata or {}),
                "last_generation_failure": str(reason or "").strip(),
            },
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        continuity = dict(session.creative_continuity or {})
        self._replace_session(
            replace(
                session,
                current_request_id=None,
                creative_continuity={
                    **continuity,
                    "direction_approved": False,
                    "workflow_stage": "recommendation_ready",
                },
                updated_at=utc_now(),
            )
        )
        return updated

    def queue_generated_image(
        self,
        record: GeneratedImageRecord,
        *,
        title: str = "Generation Library Photoshoot",
    ) -> tuple[PhotoshootRequest, bool]:
        for request in self.list_requests():
            generated_ids = tuple((request.metadata or {}).get("generated_image_ids") or ())
            if record.image_id in generated_ids:
                return request, False

        plan = PromptPlan(
            plan_id=record.prompt_plan_id,
            session_id=record.generation_job_id,
            creator_profile_id=record.creator_profile_id,
            prompt_text=record.prompt_text,
            creative_mode=record.creative_mode or "social_safe",
            creative_tags=tuple(record.prompt_metadata.get("creative_tags") or ()),
            reference_asset_id=record.reference_asset_id,
            reference_asset_path=None,
            creative_rationale="Generated image queued from Generation Library for Photoshoot review.",
            prompt_metadata={
                "provider_neutral": True,
                "source": "generation_library",
                "generated_image_id": record.image_id,
                **dict(record.prompt_metadata or {}),
            },
        )
        session = self.create_session(
            creator_profile_id=record.creator_profile_id,
            prompt_plans=(plan,),
            title=title,
            provider_id=record.provider_id,
            reference_asset_id=record.reference_asset_id,
            creator_notes="Queued from Generation Library.",
            creative_continuity={
                "source": "generation_library",
                "generated_image_id": record.image_id,
                "output_reference": record.output_reference,
                "generation_job_id": record.generation_job_id,
                "generation_request_id": record.generation_request_id,
                "generation_result_id": record.generation_result_id,
            },
        )
        request = self.requests_for_session(session.session_id)[0]
        updated = replace(
            request,
            status="awaiting_review",
            metadata={
                **dict(request.metadata or {}),
                "source": "generation_library",
                "generated_image_ids": (record.image_id,),
                "output_reference": record.output_reference,
                "generation_job_id": record.generation_job_id,
                "generation_request_id": record.generation_request_id,
                "generation_result_id": record.generation_result_id,
            },
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        self._replace_session(
            replace(
                session,
                status="running",
                current_request_id=updated.request_id,
                updated_at=utc_now(),
            )
        )
        return updated, True

    def start_studio_session_from_generated_image(
        self,
        record: GeneratedImageRecord,
        *,
        title: str = "Photoshoot Studio",
        canonical_identity_reference: Mapping[str, Any] | None = None,
    ) -> tuple[PhotoshootSession, bool]:
        """Open a persisted Photoshoot Studio session with a generated image as seed."""
        identity_reference = dict(canonical_identity_reference or {})
        identity_path = str(identity_reference.get("path") or identity_reference.get("url") or "").strip()
        identity_asset_id = int(identity_reference.get("asset_id") or 0)
        if identity_reference and (not identity_asset_id or not identity_path):
            raise ValueError("Canonical Photoshoot identity reference is incomplete.")
        for session in self.list_sessions(creator_profile_id=record.creator_profile_id):
            if session.status in {"completed", "cancelled", "junked"}:
                continue
            continuity = dict(session.creative_continuity or {})
            if continuity.get("seed_image_id") == record.image_id:
                if not continuity.get("canonical_identity_reference_frozen") and identity_reference:
                    updated = replace(
                        session,
                        creative_continuity={
                            **continuity,
                            "canonical_identity_reference": {
                                "asset_id": identity_asset_id,
                                "path": identity_path,
                                "frozen_at": str(identity_reference.get("frozen_at") or utc_now()),
                            },
                            "canonical_identity_reference_frozen": True,
                        },
                        updated_at=utc_now(),
                    )
                    self._replace_session(updated)
                    return updated, False
                return session, False

        plan = PromptPlan(
            plan_id=record.prompt_plan_id,
            session_id=record.generation_job_id,
            creator_profile_id=record.creator_profile_id,
            prompt_text=record.prompt_text,
            creative_mode=record.creative_mode or "social_safe",
            creative_tags=tuple(record.prompt_metadata.get("creative_tags") or ()),
            reference_asset_id=record.reference_asset_id,
            reference_asset_path=None,
            creative_rationale="Seed image selected for Photoshoot Studio.",
            prompt_metadata={
                "provider_neutral": True,
                "source": "generation_library",
                "generated_image_id": record.image_id,
                "photoshoot_studio_seed": True,
                **dict(record.prompt_metadata or {}),
            },
        )
        seed_summary = CanonicalPhotoshootSeedSummary.from_provider_prompt(
            record.prompt_text,
            creative_tags=tuple(record.prompt_metadata.get("creative_tags") or ()),
        )
        session = self.create_session(
            creator_profile_id=record.creator_profile_id,
            prompt_plans=(plan,),
            title=title,
            provider_id=record.provider_id,
            reference_asset_id=record.reference_asset_id,
            creator_notes="Opened from Generation Library Shoot action.",
            creative_continuity={
                "source": "photoshoot_studio",
                "seed_image_id": record.image_id,
                "seed_output_reference": record.output_reference,
                "seed_prompt_text": record.prompt_text,
                "canonical_seed_summary": seed_summary.to_dict(),
                "seed_generation_job_id": record.generation_job_id,
                "seed_generation_request_id": record.generation_request_id,
                "seed_generation_result_id": record.generation_result_id,
                **({
                    "canonical_identity_reference": {
                        "asset_id": identity_asset_id,
                        "path": identity_path,
                        "frozen_at": str(identity_reference.get("frozen_at") or utc_now()),
                    },
                    "canonical_identity_reference_frozen": True,
                } if identity_reference else {}),
                "continuity_rule": (
                    "Use the seed image as the canonical continuity reference. Preserve outfit, hair, makeup, "
                    "accessories, location, lighting, time of day, mood, and photography style. Vary only pose, "
                    "expression, camera angle, framing, distance, body orientation, hand placement, eye contact, "
                    "and subtle movement unless the creator explicitly asks otherwise."
                ),
                "session_defaults": {
                    "location": "Preserve the current image location unless overridden.",
                    "wardrobe": "Preserve the current outfit unless overridden.",
                    "lighting": "Preserve the current lighting unless overridden.",
                    "camera_style": "Preserve the current camera style unless overridden.",
                    "identity_continuity": "Preserve the same identity, face, body, and proportions.",
                    "hairstyle": "Preserve the current hairstyle unless overridden.",
                    "makeup": "Preserve the current makeup unless overridden.",
                    "visual_tone": "Preserve the current visual tone unless overridden.",
                },
                "approved_directions": (),
                "approved_prompts": (),
                "progression_stage": 0,
                "workflow_stage": "ready_for_direction",
            },
        )
        request = self.requests_for_session(session.session_id)[0]
        seed_request = replace(
            request,
            status="approved",
            review_status="approved",
            metadata={
                **dict(request.metadata or {}),
                "source": "photoshoot_studio_seed",
                "generated_image_ids": (record.image_id,),
                "output_reference": record.output_reference,
                "generation_job_id": record.generation_job_id,
                "generation_request_id": record.generation_request_id,
                "generation_result_id": record.generation_result_id,
                "is_seed_image": True,
            },
            updated_at=utc_now(),
        )
        self._replace_request(seed_request)
        updated_session = replace(
            session,
            status="running",
            current_request_id=None,
            updated_at=utc_now(),
        )
        self._replace_session(updated_session)
        return updated_session, True

    def record_creative_direction(
        self,
        *,
        session_id: str,
        recommendation: Mapping[str, Any],
        final_prompt: str | None = None,
    ) -> PhotoshootSession:
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        approved_directions = list(continuity.get("approved_directions") or ())
        entry = {
            "title": str(recommendation.get("title") or "").strip(),
            "creative_direction": str(recommendation.get("creative_direction") or "").strip(),
            "reasoning": str(recommendation.get("reasoning") or "").strip(),
            "continuity_notes": str(recommendation.get("continuity_notes") or "").strip(),
            "camera_framing": str(recommendation.get("camera_framing") or "").strip(),
            "lighting": str(recommendation.get("lighting") or "").strip(),
            "emotion": str(recommendation.get("emotion") or "").strip(),
            "pose_composition": str(recommendation.get("pose_composition") or "").strip(),
            "creative_mode": str(recommendation.get("creative_mode") or session.creative_mode).strip(),
            "session_direction": str(recommendation.get("session_direction") or "").strip(),
            "continuity_locks": dict(recommendation.get("continuity_locks") or {}),
            "created_at": utc_now(),
        }
        if entry not in approved_directions:
            approved_directions.append(entry)
        approved_prompts = list(continuity.get("approved_prompts") or ())
        if str(final_prompt or "").strip() and str(final_prompt).strip() not in approved_prompts:
            approved_prompts.append(str(final_prompt).strip())
        updated = replace(
            session,
            creative_continuity={
                **continuity,
                "approved_directions": tuple(approved_directions),
                "approved_prompts": tuple(approved_prompts),
                "current_direction": entry,
                "current_prompt": str(final_prompt or "").strip(),
                "direction_approved": bool(str(final_prompt or "").strip()),
                "workflow_stage": "direction_approved",
                "progression_stage": int(continuity.get("progression_stage") or 0) + 1,
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def record_pending_recommendation(
        self,
        *,
        session_id: str,
        recommendation: Mapping[str, Any],
    ) -> PhotoshootSession:
        """Persist a Creative Director recommendation that is awaiting creator approval."""
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        entry = {
            "title": str(recommendation.get("title") or "").strip(),
            "creative_direction": str(recommendation.get("creative_direction") or "").strip(),
            "reasoning": str(recommendation.get("reasoning") or "").strip(),
            "continuity_notes": str(recommendation.get("continuity_notes") or "").strip(),
            "camera_framing": str(recommendation.get("camera_framing") or "").strip(),
            "lighting": str(recommendation.get("lighting") or "").strip(),
            "emotion": str(recommendation.get("emotion") or "").strip(),
            "pose_composition": str(recommendation.get("pose_composition") or "").strip(),
            "creative_mode": str(recommendation.get("creative_mode") or session.creative_mode).strip(),
            "session_direction": str(recommendation.get("session_direction") or "").strip(),
            "continuity_locks": dict(recommendation.get("continuity_locks") or {}),
            "created_at": str(recommendation.get("created_at") or utc_now()),
        }
        updated = replace(
            session,
            creative_continuity={
                **continuity,
                "current_direction": entry,
                "current_prompt": "",
                "direction_approved": False,
                "workflow_stage": "recommendation_ready",
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def clear_workspace_state(
        self,
        session_id: str,
        *,
        workflow_stage: str = "ready_for_direction",
    ) -> PhotoshootSession:
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        updated = replace(
            session,
            creative_continuity={
                **continuity,
                "current_direction": {},
                "current_prompt": "",
                "direction_approved": False,
                "workflow_stage": str(workflow_stage or "ready_for_direction"),
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def add_studio_shot_request(
        self,
        *,
        session_id: str,
        prompt_text: str,
        shot_direction: str,
        provider_id: str | None = None,
        active_reference_image_id: str | None = None,
        active_reference_output_reference: str | None = None,
        creative_direction: Mapping[str, Any] | None = None,
    ) -> PhotoshootRequest:
        """Append a single creator-directed shot to a Photoshoot Studio session."""
        session = self.get_session(session_id)
        if session.status in {"completed", "cancelled"}:
            raise ValueError(f"Photoshoot Session is {session.status}.")
        prompt = str(prompt_text or "").strip()
        if not prompt:
            raise ValueError("Prompt is required before generating a Photoshoot shot.")
        requests = list(self.requests_for_session(session_id))
        for existing in reversed(requests):
            if existing.status in {"queued", "generating", "awaiting_review"}:
                return existing
        continuity = dict(session.creative_continuity or {})
        replacement_index = int(continuity.get("replacement_sequence_index") or 0)
        next_index = replacement_index or max((request.sequence_index for request in requests), default=0) + 1
        request = PhotoshootRequest(
            request_id=new_id("photoshoot_request"),
            session_id=session_id,
            prompt_plan_id=new_id("prompt_plan"),
            prompt_text=prompt,
            sequence_index=next_index,
            creative_mode=session.creative_mode,
            reference_asset_id=session.reference_asset_id,
            metadata={
                "creative_tags": (),
                "prompt_metadata": {
                    "provider_neutral": True,
                    "source": "photoshoot_studio",
                    "shot_direction": str(shot_direction or "").strip(),
                    "seed_image_id": dict(session.creative_continuity or {}).get("seed_image_id"),
                    "active_reference_image_id": str(active_reference_image_id or "").strip(),
                    "active_reference_output_reference": str(active_reference_output_reference or "").strip(),
                    "continuity_rule": dict(session.creative_continuity or {}).get("continuity_rule"),
                    "creative_direction": dict(creative_direction or {}),
                },
                "shot_direction": str(shot_direction or "").strip(),
                "active_reference_image_id": str(active_reference_image_id or "").strip(),
                "active_reference_output_reference": str(active_reference_output_reference or "").strip(),
                "creative_direction": dict(creative_direction or {}),
                "replaces_request_id": str(continuity.get("replacement_request_id") or ""),
                "inspiration_ideas": tuple(continuity.get("inspiration_ideas") or ()),
                "selected_inspiration": str(continuity.get("selected_inspiration") or ""),
                "inspiration_planning_shot": int(continuity.get("inspiration_planning_shot") or 0),
                "inspiration_idea_set_id": str(continuity.get("active_freeflow_idea_set_id") or "")
                if session.target_shot_count == 0 and str(continuity.get("planning_mode") or "frame_by_frame") == "frame_by_frame"
                else "",
            },
        )
        self._mutate_json(self.requests_path, lambda items: [*items, asdict(request)])
        self._replace_session(
            replace(
                session,
                status="running",
                provider_id=provider_id or session.provider_id,
                request_ids=tuple((*session.request_ids, request.request_id)),
                current_request_id=None,
                creative_continuity={
                    **dict(session.creative_continuity or {}),
                    "workflow_stage": "generating",
                },
                updated_at=utc_now(),
            )
        )
        return request

    def replace_approved_shot(self, request_id: str) -> tuple[PhotoshootRequest, tuple[PhotoshootRequest, ...], PhotoshootSession]:
        """Return an approved timeline position to planning and invalidate dependent shots."""
        target = self.get_request(request_id)
        if target.status not in {"approved", "continuity_invalidated", "replacement_pending"}:
            raise ValueError("Only an approved or invalidated Photoshoot shot can be replaced.")
        if bool(dict(target.metadata or {}).get("is_seed_image")):
            raise ValueError("The Photoshoot seed cannot be replaced.")
        session = self.get_session(target.session_id)
        if session.status in {"completed", "cancelled", "archived"}:
            raise ValueError(f"Photoshoot Session is {session.status}.")
        requests = list(self.requests_for_session(target.session_id))
        active = next((item for item in requests if item.status in {"queued", "generating", "awaiting_review"}), None)
        if active is not None:
            raise ValueError("Finish the active Photoshoot shot before replacing an approved shot.")

        invalidated = []
        for item in requests:
            if item.sequence_index < target.sequence_index or item.request_id == target.request_id:
                continue
            if item.status in {"approved", "continuity_invalidated", "replacement_pending"}:
                updated = replace(item, status="continuity_invalidated", review_status="continuity_invalidated",
                                  review_notes=f"Continuity changed before Shot {item.sequence_index}; regeneration required.", updated_at=utc_now())
                self._replace_request(updated)
                invalidated.append(updated)
        replacement = replace(target, status="replacement_pending", review_status="replacement_pending",
                              review_notes="Selected by operator for replacement.", updated_at=utc_now())
        self._replace_request(replacement)

        previous = max(
            (item for item in requests if item.sequence_index < target.sequence_index and item.status == "approved"),
            key=lambda item: item.sequence_index,
            default=None,
        )
        continuity = dict(session.creative_continuity or {})
        previous_ids = tuple(dict(previous.metadata or {}).get("generated_image_ids") or ()) if previous else ()
        approved_before = tuple(
            item for item in requests if item.sequence_index < target.sequence_index and item.status == "approved"
        )
        updated_session = replace(
            session,
            current_request_id=None,
            creative_continuity={
                **continuity,
                "current_shot_image_id": previous_ids[-1] if previous_ids else continuity.get("seed_image_id"),
                "replacement_request_id": target.request_id,
                "replacement_sequence_index": target.sequence_index,
                "inspiration_ideas": (),
                "selected_inspiration": "",
                "inspiration_planning_shot": 0,
                "current_direction": {},
                "current_prompt": "",
                "creator_guidance": "",
                "grok_guidance": "",
                "session_direction": "",
                "creative_hint": "",
                "direction_approved": False,
                "workflow_stage": "ready_for_next_shot",
                "progression_stage": max(0, len(approved_before) - 1),
                "approved_directions": tuple(
                    dict((item.metadata or {}).get("creative_direction") or {})
                    for item in approved_before if dict((item.metadata or {}).get("creative_direction") or {})
                ),
                "approved_prompts": tuple(item.prompt_text for item in approved_before if item.prompt_text),
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated_session)
        return replacement, tuple(invalidated), updated_session

    def update_request_continuity_reference(
        self,
        request_id: str,
        *,
        image_id: str | None,
        output_reference: str | None,
    ) -> PhotoshootRequest:
        request = self.get_request(request_id)
        metadata = dict(request.metadata or {})
        prompt_metadata = dict(metadata.get("prompt_metadata") or {})
        image_value = str(image_id or "").strip()
        reference_value = str(output_reference or "").strip()
        updated = replace(
            request,
            metadata={
                **metadata,
                "active_reference_image_id": image_value,
                "active_reference_output_reference": reference_value,
                "prompt_metadata": {
                    **prompt_metadata,
                    "active_reference_image_id": image_value,
                    "active_reference_output_reference": reference_value,
                },
            },
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        return updated

    def mark_finalization_required(
        self, generation_job_id: str, *, generated_image_ids: Iterable[str], reason: str,
    ) -> PhotoshootRequest | None:
        """Preserve a successful render whose local review transition needs retrying."""
        request = self.request_for_generation_job(generation_job_id)
        if request is None:
            return None
        generated_ids = tuple(str(image_id) for image_id in generated_image_ids if str(image_id))
        updated = replace(
            request,
            status="finalization_required",
            metadata={
                **dict(request.metadata or {}),
                "generated_image_ids": generated_ids,
                "finalization_required": True,
                "finalization_error": str(reason or "Local Photoshoot finalization failed.").strip(),
            },
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(
            session,
            current_request_id=updated.request_id,
            creative_continuity={
                **dict(session.creative_continuity or {}),
                "workflow_stage": "finalization_required",
            },
            updated_at=utc_now(),
        ))
        return updated

    def mark_preparation_required(
        self, request_id: str, *, generation_job_id: str, reason: str,
    ) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            status="preparation_recovery_required",
            generation_job_id=generation_job_id,
            metadata={
                **dict(request.metadata or {}),
                "preparation_recovery_required": True,
                "preparation_error": str(reason or "Local generation preparation failed.").strip(),
            },
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(
            session,
            current_request_id=updated.request_id,
            creative_continuity={
                **dict(session.creative_continuity or {}),
                "workflow_stage": "preparation_recovery_required",
            },
            updated_at=utc_now(),
        ))
        return updated

    def resume_prepared_request(self, request_id: str) -> PhotoshootRequest:
        request = self.get_request(request_id)
        if request.status != "preparation_recovery_required" or not request.generation_job_id:
            raise ValueError("This Photoshoot request does not require preparation recovery.")
        metadata = dict(request.metadata or {})
        metadata.pop("preparation_recovery_required", None)
        metadata.pop("preparation_error", None)
        updated = replace(request, status="generating", metadata=metadata, updated_at=utc_now())
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(
            session, current_request_id=updated.request_id,
            creative_continuity={**dict(session.creative_continuity or {}), "workflow_stage": "generating"},
            updated_at=utc_now(),
        ))
        return updated

    def record_continuity_assessment(self, request_id: str, assessment: Mapping[str, Any]) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            metadata={**dict(request.metadata or {}), "continuity_assessment": dict(assessment or {})},
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        return updated

    def finish_session(self, session_id: str) -> PhotoshootSession:
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        updated = replace(
            session,
            status="completed",
            current_request_id=None,
            creative_continuity={
                **continuity,
                "completed_at": utc_now(),
                "gallery_ready": True,
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def archive_curated_session(self, session_id: str, *, curation: Mapping[str, Any]) -> PhotoshootSession:
        """Archive a reviewed session while preserving its complete creative history."""
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        updated = replace(
            session, status="archived", current_request_id=None,
            creative_continuity={
                **continuity, "completed_at": continuity.get("completed_at") or utc_now(),
                "gallery_ready": bool(curation.get("photoshoot_created")),
                "curation": dict(curation), "workflow_stage": "curation_complete",
            }, updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def reconcile_curation(self, session_id: str, *, curation: Mapping[str, Any]) -> PhotoshootSession:
        """Persist an idempotently normalized legacy curation decision."""
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        if dict(continuity.get("curation") or {}) == dict(curation):
            return session
        updated = replace(
            session,
            creative_continuity={**continuity, "curation": dict(curation)},
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def record_fanvue_upload_result(
        self,
        session_id: str,
        upload_result: Mapping[str, Any],
    ) -> PhotoshootSession:
        session = self.get_session(session_id)
        metadata = dict(session.metadata or {})
        previous = dict(metadata.get("fanvue_photoshoot_upload") or {})
        uploaded_media_ids = list(upload_result.get("uploaded_media_ids") or ())
        uploaded_by_image_id = dict(upload_result.get("uploaded_media_by_image_id") or {})
        upload_metadata = {
            **previous,
            "uploaded_to_fanvue": bool(upload_result.get("uploaded_to_fanvue")),
            "uploaded_folder": upload_result.get("uploaded_folder"),
            "uploaded_timestamp": upload_result.get("uploaded_timestamp"),
            "last_attempted_at": upload_result.get("last_attempted_at") or utc_now(),
            "uploaded_media_ids": uploaded_media_ids,
            "uploaded_media_by_image_id": uploaded_by_image_id,
            "uploaded_count": int(upload_result.get("uploaded_count") or len(uploaded_by_image_id)),
            "total_count": int(upload_result.get("total_count") or 0),
            "failures": list(upload_result.get("failures") or ()),
        }
        updated = replace(
            session,
            metadata={
                **metadata,
                "fanvue_photoshoot_upload": upload_metadata,
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def sync_ingested_assets_for_session(self, session_id: str) -> tuple[int, ...]:
        asset_ids: list[int] = []
        for request in self.requests_for_session(session_id):
            if not request.generation_job_id:
                continue
            status = self.generation_ingestion.ingestion_status_for_job(request.generation_job_id)
            imported = tuple(int(asset_id) for asset_id in status.get("imported_asset_ids", ()) if asset_id is not None)
            if imported and tuple(request.imported_asset_ids) != imported:
                self._replace_request(replace(request, imported_asset_ids=imported, updated_at=utc_now()))
                self._associate_assets(replace(request, imported_asset_ids=imported))
            asset_ids.extend(imported)
        return tuple(dict.fromkeys(asset_ids))

    def approve_request(
        self,
        request_id: str,
        *,
        notes: str | None = None,
        imported_asset_ids: Iterable[int] = (),
    ) -> PhotoshootRequest:
        request = self.get_request(request_id)
        approved_asset_ids = tuple(
            dict.fromkeys(
                tuple(int(asset_id) for asset_id in request.imported_asset_ids if asset_id is not None)
                + tuple(int(asset_id) for asset_id in imported_asset_ids if asset_id is not None)
            )
        )
        updated = replace(
            request,
            status="approved",
            review_status="approved",
            review_notes=notes,
            imported_asset_ids=approved_asset_ids,
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        self._associate_assets(updated)
        session = self.get_session(updated.session_id)
        continuity = dict(session.creative_continuity or {})
        approved_prompts = list(continuity.get("approved_prompts") or ())
        if updated.prompt_text and updated.prompt_text not in approved_prompts:
            approved_prompts.append(updated.prompt_text)
        approved_directions = list(continuity.get("approved_directions") or ())
        creative_direction = dict((updated.metadata or {}).get("creative_direction") or {})
        if creative_direction and creative_direction not in approved_directions:
            approved_directions.append(creative_direction)
        generated_image_ids = tuple((updated.metadata or {}).get("generated_image_ids") or ())
        approved_count = len(tuple(
            request for request in self.requests_for_session(updated.session_id)
            if request.status == "approved"
        ))
        self._replace_session(
            replace(
                session,
                current_request_id=None,
                creative_continuity={
                    **continuity,
                    "approved_prompts": tuple(approved_prompts),
                    "approved_directions": tuple(approved_directions),
                    "current_direction": {},
                    "current_prompt": "",
                    "creative_hint": "",
                    "creator_guidance": "",
                    "grok_guidance": "",
                    "session_direction": "",
                    "inspiration_ideas": (),
                    "inspiration_planning_shot": 0,
                    "selected_inspiration": "",
                    "direction_approved": False,
                    "workflow_stage": "ready_for_next_shot",
                    "current_shot_image_id": generated_image_ids[-1] if generated_image_ids else continuity.get("current_shot_image_id"),
                    "selected_timeline_index": max(0, approved_count - 1),
                    "progression_stage": max(
                        int(continuity.get("progression_stage") or 0),
                        len(tuple(request for request in self.requests_for_session(updated.session_id) if request.status == "approved")),
                    ),
                    "replacement_request_id": "",
                    "replacement_sequence_index": 0,
                },
                updated_at=utc_now(),
            )
        )
        return updated

    def reject_request(self, request_id: str, *, notes: str | None = None) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            status="rejected",
            review_status="rejected",
            review_notes=notes,
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(
            session,
            current_request_id=None,
            creative_continuity={
                **dict(session.creative_continuity or {}),
                "direction_approved": False,
                "workflow_stage": "ready_for_next_shot",
            },
            updated_at=utc_now(),
        ))
        return updated

    def return_seed_request_to_library(self, request_id: str, *, notes: str | None = None) -> PhotoshootRequest:
        request = self.get_request(request_id)
        if not bool((request.metadata or {}).get("is_seed_image")):
            raise ValueError("Only the Photoshoot seed image can be returned to Generation Library.")
        updated = replace(
            request,
            status="returned_to_library",
            review_status="returned_to_library",
            review_notes=notes,
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        continuity = dict(session.creative_continuity or {})
        returned_ids = tuple((updated.metadata or {}).get("generated_image_ids") or ())
        remaining_approved_ids = tuple(
            image_id
            for request_item in self.requests_for_session(updated.session_id)
            if request_item.request_id != updated.request_id and request_item.status == "approved"
            for image_id in tuple((request_item.metadata or {}).get("generated_image_ids") or ())
        )
        cleaned_continuity = {
            key: value
            for key, value in continuity.items()
            if key
            not in {
                "seed_image_id",
                "seed_output_reference",
                "seed_prompt_text",
                "seed_generation_job_id",
                "seed_generation_request_id",
                "seed_generation_result_id",
            }
        }
        cleaned_continuity.update(
            {
                "current_shot_image_id": remaining_approved_ids[-1] if remaining_approved_ids else None,
                "photoshoot_returned_seed_image_ids": tuple(
                    dict.fromkeys(
                        tuple(continuity.get("photoshoot_returned_seed_image_ids") or ())
                        + returned_ids
                    )
                ),
                "workflow_stage": "ready_for_next_shot" if remaining_approved_ids else "seed_returned",
            }
        )
        self._replace_session(
            replace(
                session,
                status="running" if remaining_approved_ids else "cancelled",
                current_request_id=None,
                creative_continuity=cleaned_continuity,
                updated_at=utc_now(),
            )
        )
        return updated

    def junk_request(self, request_id: str, *, notes: str | None = None) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            status="junked",
            review_status="junked",
            review_notes=notes,
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        continuity = dict(session.creative_continuity or {})
        generated_image_ids = tuple((updated.metadata or {}).get("generated_image_ids") or ())
        current_shot_id = continuity.get("current_shot_image_id")
        if current_shot_id in generated_image_ids:
            approved_ids = tuple(
                image_id
                for request_item in self.requests_for_session(updated.session_id)
                if request_item.request_id != updated.request_id and request_item.status == "approved"
                for image_id in tuple((request_item.metadata or {}).get("generated_image_ids") or ())
            )
            current_shot_id = approved_ids[-1] if approved_ids else continuity.get("seed_image_id")
        self._replace_session(
            replace(
                session,
                current_request_id=None,
                creative_continuity={
                    **continuity,
                    "current_shot_image_id": current_shot_id,
                    "photoshoot_junked_image_ids": tuple(
                        dict.fromkeys(
                            tuple(continuity.get("photoshoot_junked_image_ids") or ())
                            + generated_image_ids
                        )
                    ),
                },
                updated_at=utc_now(),
            )
        )
        return updated

    def regenerate_request(self, request_id: str, *, notes: str | None = None) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            status="queued",
            review_status="regenerate",
            review_notes=notes,
            generation_job_id=None,
            imported_asset_ids=(),
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(session, current_request_id=None, updated_at=utc_now()))
        return updated

    def pause_session(self, session_id: str) -> PhotoshootSession:
        session = self.get_session(session_id)
        updated = replace(session, status="paused", updated_at=utc_now())
        self._replace_session(updated)
        return updated

    def resume_session(self, session_id: str) -> PhotoshootSession:
        session = self.get_session(session_id)
        updated = replace(session, status="queued", updated_at=utc_now())
        self._replace_session(updated)
        return updated

    def cancel_session(self, session_id: str) -> PhotoshootSession:
        session = self.get_session(session_id)
        updated = replace(session, status="cancelled", updated_at=utc_now())
        self._replace_session(updated)
        return updated

    def cancel_session_for_seed_return(self, session_id: str, *, seed_image_id: str) -> PhotoshootSession:
        """Cancel one active session and clear its transient workspace without deleting media."""
        session = self.get_session(session_id)
        if session.status == "completed":
            raise ValueError("Completed Photoshoots cannot be stopped.")
        for request in self.requests_for_session(session_id):
            if request.status in {"queued", "generating", "awaiting_review"}:
                self._replace_request(replace(
                    request, status="cancelled", review_status="cancelled",
                    review_notes="Photoshoot stopped and seed returned.", updated_at=utc_now(),
                ))
        continuity = dict(session.creative_continuity or {})
        for key in (
            "inspiration_ideas", "selected_inspiration", "inspiration_edits", "current_direction",
            "current_prompt", "creator_guidance", "grok_guidance", "creative_hint",
            "direction_approved",
        ):
            continuity.pop(key, None)
        continuity.update({
            "seed_image_id": str(seed_image_id),
            "current_shot_image_id": None,
            "workflow_stage": "seed_returned",
            "seed_returned_to_library": True,
        })
        updated = replace(
            session, status="cancelled", current_request_id=None,
            creative_continuity=continuity, updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def junk_completed_session(self, session_id: str, *, notes: str | None = None) -> PhotoshootSession:
        session = self.get_session(session_id)
        metadata = dict(session.metadata or {})
        updated = replace(
            session,
            status="junked",
            current_request_id=None,
            metadata={
                **metadata,
                "junked_at": utc_now(),
                "junk_notes": notes,
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def progress(self, session_id: str) -> PhotoshootProgress:
        requests = self.requests_for_session(session_id)
        total = len(requests)
        approved = tuple(request for request in requests if request.status == "approved")
        rejected = tuple(request for request in requests if request.status == "rejected")
        awaiting = tuple(request for request in requests if request.status == "awaiting_review")
        active = tuple(request for request in requests if request.status == "generating")
        queued = tuple(request for request in requests if request.status == "queued")
        imported_assets = tuple(
            asset_id
            for request in requests
            for asset_id in request.imported_asset_ids
        )
        reviewed = len(approved) + len(rejected)
        return PhotoshootProgress(
            total_prompts=total,
            queued_prompts=len(queued),
            active_prompts=len(active),
            awaiting_review=len(awaiting),
            approved_images=sum(
                len(request.imported_asset_ids)
                or len(tuple((request.metadata or {}).get("generated_image_ids") or ()))
                for request in approved
            ),
            rejected_images=sum(
                len(request.imported_asset_ids)
                or len(tuple((request.metadata or {}).get("generated_image_ids") or ()))
                for request in rejected
            ),
            imported_assets=len(tuple(dict.fromkeys(imported_assets))),
            percent_complete=(reviewed / total * 100) if total else 0.0,
        )

    def result(self, session_id: str) -> PhotoshootResult:
        requests = self.requests_for_session(session_id)
        return PhotoshootResult(
            session_id=session_id,
            approved_asset_ids=tuple(
                asset_id
                for request in requests
                if request.status == "approved"
                for asset_id in request.imported_asset_ids
            ),
            rejected_asset_ids=tuple(
                asset_id
                for request in requests
                if request.status == "rejected"
                for asset_id in request.imported_asset_ids
            ),
            regenerated_request_ids=tuple(
                request.request_id
                for request in requests
                if request.review_status == "regenerate"
            ),
            metadata={
                "approved_generated_image_ids": tuple(
                    image_id
                    for request in requests
                    if request.status == "approved"
                    for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ())
                ),
                "rejected_generated_image_ids": tuple(
                    image_id
                    for request in requests
                    if request.status == "rejected"
                    for image_id in tuple((request.metadata or {}).get("generated_image_ids") or ())
                ),
            },
        )

    def current_session(self, *, creator_profile_id: int | None = None) -> PhotoshootSession | None:
        active_sessions = tuple(
            session
            for session in self.list_sessions(creator_profile_id=creator_profile_id)
            if session.status not in {"completed", "archived", "cancelled", "junked"}
        )
        if not active_sessions:
            return None
        return sorted(
            active_sessions,
            key=lambda session: session.updated_at or session.created_at or "",
            reverse=True,
        )[0]

    def update_session_settings(
        self,
        session_id: str,
        *,
        provider_id: str | None = None,
        creative_mode: str | None = None,
        continuity_locks: Mapping[str, bool] | None = None,
        selected_timeline_index: int | None = None,
        workflow_stage: str | None = None,
        session_direction: str | None = None,
        creative_hint: str | None = None,
        creator_guidance: str | None = None,
        grok_guidance: str | None = None,
        inspiration_ideas: tuple[str, ...] | list[str] | None = None,
        inspiration_planning_shot: int | None = None,
        selected_inspiration: str | None = None,
        inspiration_edits: Mapping[str, str] | None = None,
        planning_mode: str | None = None,
        plan_frame_count: int | None = None,
        target_shot_count: int | None = None,
        session_plan: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
        session_plan_index: int | None = None,
        session_plan_approved: bool | None = None,
    ) -> PhotoshootSession:
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        if continuity_locks is not None:
            continuity["continuity_locks"] = {
                key: bool(value)
                for key, value in dict(continuity_locks or {}).items()
            }
        if selected_timeline_index is not None:
            continuity["selected_timeline_index"] = int(selected_timeline_index)
        if workflow_stage:
            continuity["workflow_stage"] = str(workflow_stage)
        if session_direction is not None:
            continuity["session_direction"] = str(session_direction)
        if creative_hint is not None:
            continuity["creative_hint"] = str(creative_hint)
        if creator_guidance is not None:
            continuity["creator_guidance"] = str(creator_guidance)
        if grok_guidance is not None:
            continuity["grok_guidance"] = str(grok_guidance)
        if inspiration_ideas is not None:
            continuity["inspiration_ideas"] = tuple(str(item) for item in inspiration_ideas)
        if inspiration_planning_shot is not None:
            continuity["inspiration_planning_shot"] = max(0, int(inspiration_planning_shot))
        if selected_inspiration is not None:
            continuity["selected_inspiration"] = str(selected_inspiration)
        if inspiration_edits is not None:
            continuity["inspiration_edits"] = {
                str(key): str(value).strip() for key, value in dict(inspiration_edits).items()
                if str(key).strip() and str(value).strip()
            }
        if planning_mode is not None:
            mode = str(planning_mode or "frame_by_frame").strip().lower()
            continuity["planning_mode"] = mode if mode in {"frame_by_frame", "full_plan"} else "frame_by_frame"
        if plan_frame_count is not None:
            continuity["plan_frame_count"] = max(4, min(12, int(plan_frame_count)))
        normalized_target = session.target_shot_count
        if target_shot_count is not None:
            normalized_target = normalize_target_shot_count(target_shot_count)
            continuity["target_shot_count"] = normalized_target
        if session_plan is not None:
            continuity["session_plan"] = tuple(dict(item or {}) for item in session_plan)
        if session_plan_index is not None:
            continuity["session_plan_index"] = max(0, int(session_plan_index))
        if session_plan_approved is not None:
            continuity["session_plan_approved"] = bool(session_plan_approved)
        updated = replace(
            session,
            provider_id=str(provider_id or session.provider_id),
            creative_mode=str(creative_mode or session.creative_mode),
            target_shot_count=normalized_target,
            creative_continuity=continuity,
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def extend_target_one_shot(self, session_id: str, *, expected_target_shot_count: int) -> tuple[PhotoshootSession, bool]:
        """Atomically grant one additional planned shot to an eligible active session.

        The expected-target compare-and-set makes an HTTP retry idempotent: once
        target 5 has become 6, another request expecting 5 observes 6 and does
        not extend it again.
        """
        with self._extension_lock:
            session = self.get_session(session_id)
            expected = normalize_target_shot_count(expected_target_shot_count)
            if session.target_shot_count == 0:
                raise ValueError("Creative Freeflow Photoshoots are already open-ended.")
            if session.status in {"completed", "cancelled"}:
                raise ValueError("Only an active Photoshoot can be extended.")
            if session.target_shot_count != expected:
                if session.target_shot_count == expected + 1:
                    return session, False
                raise ValueError("The Photoshoot target changed. Refresh before extending again.")
            if session.target_shot_count >= 100:
                raise ValueError("The maximum supported Photoshoot length is 100 shots.")
            requests = tuple(self.requests_for_session(session_id))
            if any(request.status in {"queued", "generating", "awaiting_review"} for request in requests):
                raise ValueError("Finish the current shot before extending this Photoshoot.")
            from app.services.photoshoot_context_service import PhotoshootContextService
            approved = PhotoshootContextService.approved_display_count(requests)
            if approved < session.target_shot_count:
                raise ValueError("The current Photoshoot target has not been reached.")
            continuity = dict(session.creative_continuity or {})
            new_target = session.target_shot_count + 1
            continuity.update({
                "target_shot_count": new_target,
                # A completed full plan has no authored beat beyond its endpoint.
                # Preserve that plan as history, then return to the canonical
                # frame-by-frame Ask AI / Direct Shot workflow for the extension.
                "planning_mode": "frame_by_frame",
                "workflow_stage": "ready_for_next_shot",
                "last_extension_from": session.target_shot_count,
                "last_extension_to": new_target,
                "last_extension_at": utc_now(),
            })
            updated = replace(
                session, target_shot_count=new_target,
                creative_continuity=continuity, updated_at=utc_now(),
            )
            self._replace_session(updated)
            return updated, True

    def record_freeflow_idea_set(
        self, session_id: str, *, idea_set_id: str, ideas: Iterable[str],
        recommended_idea: str, planning_shot: int,
    ) -> PhotoshootSession:
        """Append one immutable AI idea batch to the owning Photoshoot session."""
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        sets = [dict(item) for item in tuple(continuity.get("freeflow_idea_sets") or ()) if isinstance(item, Mapping)]
        if not any(str(item.get("idea_set_id") or "") == str(idea_set_id) for item in sets):
            sets.append({
                "idea_set_id": str(idea_set_id),
                "session_id": session_id,
                "planning_shot": max(1, int(planning_shot)),
                "approved_shot_count": max(0, int(planning_shot) - 1),
                "ideas": tuple(str(item) for item in ideas),
                "recommended_idea": str(recommended_idea or ""),
                "created_at": utc_now(),
            })
        updated = replace(session, creative_continuity={
            **continuity,
            "freeflow_idea_sets": tuple(sets),
            "active_freeflow_idea_set_id": str(idea_set_id),
        }, updated_at=utc_now())
        self._replace_session(updated)
        return updated

    def activate_freeflow_idea_set(self, session_id: str, *, idea_set_id: str, planning_shot: int) -> PhotoshootSession:
        """Reactivate persisted idea text at the current Freeflow review position."""
        session = self.get_session(session_id)
        continuity = dict(session.creative_continuity or {})
        sets = [dict(item) for item in tuple(continuity.get("freeflow_idea_sets") or ()) if isinstance(item, Mapping)]
        selected_set = next((item for item in sets if str(item.get("idea_set_id") or "") == str(idea_set_id)), None)
        if selected_set is None:
            raise KeyError("Creative Freeflow idea set not found.")
        ideas = tuple(str(item) for item in tuple(selected_set.get("ideas") or ()) if str(item).strip())
        updated = replace(session, creative_continuity={
            **continuity,
            "inspiration_ideas": ideas,
            "inspiration_planning_shot": max(1, int(planning_shot)),
            "selected_inspiration": "",
            "inspiration_edits": {},
            "active_freeflow_idea_set_id": str(idea_set_id),
            "creative_hint": "",
            "current_direction": {},
            "current_prompt": "",
            "direction_approved": False,
            "workflow_stage": "inspiration_ready",
        }, updated_at=utc_now())
        self._replace_session(updated)
        return updated

    def record_photoshoot_summary(self, *, session_id: str, summary: Mapping[str, Any]) -> PhotoshootSession:
        session = self.get_session(session_id)
        updated = replace(
            session,
            creative_continuity={
                **dict(session.creative_continuity or {}),
                "photoshoot_summary": dict(summary or {}),
                "photoshoot_summary_updated_at": utc_now(),
            },
            updated_at=utc_now(),
        )
        self._replace_session(updated)
        return updated

    def list_sessions(self, *, creator_profile_id: int | None = None) -> tuple[PhotoshootSession, ...]:
        sessions = tuple(self._session_from_dict(item) for item in self._read_json(self.sessions_path, []))
        if creator_profile_id is None:
            return sessions
        return tuple(session for session in sessions if session.creator_profile_id == int(creator_profile_id))

    def list_requests(self) -> tuple[PhotoshootRequest, ...]:
        return tuple(self._request_from_dict(item) for item in self._read_json(self.requests_path, []))

    def requests_for_session(self, session_id: str) -> tuple[PhotoshootRequest, ...]:
        return tuple(
            sorted(
                (request for request in self.list_requests() if request.session_id == session_id),
                key=lambda request: request.sequence_index,
            )
        )

    def next_queued_request(self, session_id: str) -> PhotoshootRequest | None:
        for request in self.requests_for_session(session_id):
            if request.status == "queued":
                return request
        return None

    def current_request(self, session_id: str) -> PhotoshootRequest | None:
        session = self.get_session(session_id)
        if not session.current_request_id:
            return None
        try:
            return self.get_request(session.current_request_id)
        except KeyError:
            return None

    def request_for_generation_job(self, generation_job_id: str) -> PhotoshootRequest | None:
        for request in self.list_requests():
            if request.generation_job_id == generation_job_id:
                return request
        return None

    def get_session(self, session_id: str) -> PhotoshootSession:
        for session in self.list_sessions():
            if session.session_id == session_id:
                return session
        raise KeyError(f"Photoshoot Session not found: {session_id}")

    def get_request(self, request_id: str) -> PhotoshootRequest:
        for request in self.list_requests():
            if request.request_id == request_id:
                return request
        raise KeyError(f"Photoshoot Request not found: {request_id}")

    def _associate_assets(self, request: PhotoshootRequest) -> None:
        if not request.imported_asset_ids:
            return
        update = getattr(self.assets, "update_media_metadata", None)
        if not callable(update):
            return
        for asset_id in request.imported_asset_ids:
            asset = self.assets.get_by_id(asset_id)
            media_metadata = dict(getattr(asset, "media_metadata", None) or {})
            media_metadata[PHOTOSHOOT_ASSET_METADATA_KEY] = {
                "session_id": request.session_id,
                "request_id": request.request_id,
                "sequence_index": request.sequence_index,
                "prompt_plan_id": request.prompt_plan_id,
            }
            update(asset_id, media_metadata)

    @staticmethod
    def _prompt_plan_from_request(request: PhotoshootRequest, creator_profile_id: int) -> PromptPlan:
        return PromptPlan(
            plan_id=request.prompt_plan_id,
            session_id=request.session_id,
            creator_profile_id=int(creator_profile_id),
            prompt_text=request.prompt_text,
            creative_mode=request.creative_mode,
            creative_tags=tuple(request.metadata.get("creative_tags") or ()),
            reference_asset_id=request.reference_asset_id,
            reference_asset_path=None,
            creative_rationale="Prompt Plan queued by Photoshoot Queue for ordered session generation.",
            prompt_metadata={
                "provider_neutral": True,
                "generation_mode_behavior": "photoshoot_queue",
                "wavespeed_generation_mode_key": "photoshoot_set",
                "photoshoot_continuity": (
                    "Maintain one continuous photoshoot: same location, same wardrobe, same lighting, same story, "
                    "same environment, same mood; vary only pose, camera, framing, crop, expression, hand placement, "
                    "posture, distance, eye contact, and body orientation."
                ),
                "photoshoot_session_id": request.session_id,
                "photoshoot_request_id": request.request_id,
                **dict(request.metadata.get("prompt_metadata") or {}),
            },
        )

    def _replace_session(self, updated: PhotoshootSession) -> None:
        self._mutate_json(
            self.sessions_path,
            lambda items: [
                asdict(updated) if str(item.get("session_id")) == updated.session_id else item
                for item in items
            ],
        )

    def _replace_request(self, updated: PhotoshootRequest) -> None:
        self._mutate_json(
            self.requests_path,
            lambda items: [
                asdict(updated) if str(item.get("request_id")) == updated.request_id else item
                for item in items
            ],
        )

    def _write_sessions(self, sessions: list[PhotoshootSession]) -> None:
        self._write_json(self.sessions_path, [asdict(session) for session in sessions])

    def _write_requests(self, requests: list[PhotoshootRequest]) -> None:
        self._write_json(self.requests_path, [asdict(request) for request in requests])

    @staticmethod
    def _session_from_dict(data: Mapping[str, Any]) -> PhotoshootSession:
        return PhotoshootSession(
            session_id=str(data.get("session_id")),
            creator_profile_id=int(data.get("creator_profile_id")),
            title=str(data.get("title") or "Photoshoot Session"),
            reference_asset_id=data.get("reference_asset_id"),
            creative_mode=str(data.get("creative_mode") or "social_safe"),
            target_shot_count=normalize_target_shot_count(data.get("target_shot_count")),
            status=str(data.get("status") or "queued"),
            provider_id=str(data.get("provider_id") or "future_provider"),
            creator_notes=data.get("creator_notes"),
            creative_continuity=data.get("creative_continuity") or {},
            request_ids=tuple(data.get("request_ids") or ()),
            current_request_id=data.get("current_request_id"),
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _request_from_dict(data: Mapping[str, Any]) -> PhotoshootRequest:
        return PhotoshootRequest(
            request_id=str(data.get("request_id")),
            session_id=str(data.get("session_id")),
            prompt_plan_id=str(data.get("prompt_plan_id")),
            prompt_text=str(data.get("prompt_text") or ""),
            sequence_index=int(data.get("sequence_index") or 0),
            creative_mode=str(data.get("creative_mode") or "social_safe"),
            reference_asset_id=data.get("reference_asset_id"),
            status=str(data.get("status") or "queued"),
            generation_job_id=data.get("generation_job_id"),
            imported_asset_ids=tuple(data.get("imported_asset_ids") or ()),
            review_status=data.get("review_status"),
            review_notes=data.get("review_notes"),
            metadata=data.get("metadata") or {},
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at"),
        )

    @classmethod
    def _read_json(cls, path: Path, default):
        path = path.resolve()
        with cls._file_lock(path, operation="read"):
            return cls._read_json_unlocked(path, default)

    @classmethod
    def _read_json_unlocked(cls, path: Path, default):
        try:
            if not path.exists():
                return cls._read_recovery_json(path, default)
            canonical_mtime = path.stat().st_mtime_ns
            recovered = cls._read_recovery_json(path, None, newer_than=canonical_mtime)
            if recovered is not None:
                return recovered
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return cls._read_recovery_json(path, default)

    @staticmethod
    def _read_recovery_json(path: Path, default, *, newer_than: int | None = None):
        candidates = sorted(
            path.parent.glob(f".{path.name}.*.recovery"),
            key=lambda item: item.stat().st_mtime_ns,
            reverse=True,
        )
        for candidate in candidates:
            try:
                if newer_than is not None and candidate.stat().st_mtime_ns <= newer_than:
                    continue
                with open(candidate, "r", encoding="utf-8") as file:
                    return json.load(file)
            except (OSError, json.JSONDecodeError):
                continue
        return default

    @classmethod
    def _mutate_json(cls, path: Path, mutation) -> None:
        path = path.resolve()
        with cls._file_lock(path, operation="mutate"):
            current = cls._read_json_unlocked(path, [])
            cls._write_json_unlocked(path, mutation(current))

    @classmethod
    def _write_json(cls, path: Path, data) -> None:
        path = path.resolve()
        with cls._file_lock(path, operation="write"):
            cls._write_json_unlocked(path, data)

    @staticmethod
    @contextmanager
    def _file_lock(path: Path, *, operation: str = "unknown"):
        """Serialize a complete queue-file mutation across Creator_OS processes."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = path.with_name(f".{path.name}.lock")
        started = time.monotonic()
        role = " ".join(sys.argv[:3])
        with open(lock_path, "a+b") as lock_file:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
                acquired = time.monotonic()
                logging.getLogger("creator_os.photoshoot.queue").debug(
                    "queue_lock_acquired pid=%s role=%s operation=%s target=%s lock=%s wait_ms=%.2f",
                    os.getpid(), role, operation, path, lock_path, (acquired - started) * 1000,
                )
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
                    logging.getLogger("creator_os.photoshoot.queue").debug(
                        "queue_lock_released pid=%s role=%s operation=%s target=%s lock=%s held_ms=%.2f",
                        os.getpid(), role, operation, path, lock_path,
                        (time.monotonic() - acquired) * 1000,
                    )
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                acquired = time.monotonic()
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @classmethod
    def _write_json_unlocked(cls, path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        started_at = time.monotonic()
        temporary_path: Path | None = None
        replaced = False
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(data, file, indent=2, default=str)
                file.flush()
                os.fsync(file.fileno())
            delays = (0.05, 0.1, 0.2, 0.4, 0.75)
            for attempt in range(len(delays) + 1):
                try:
                    os.replace(temporary_path, path)
                    replaced = True
                    break
                except OSError as error:
                    winerror = getattr(error, "winerror", None)
                    writable = os.access(path.parent, os.W_OK) and (not path.exists() or os.access(path, os.W_OK))
                    transient = winerror in {32, 33} or (winerror == 5 and writable)
                    if not transient or attempt >= len(delays):
                        stat = path.stat() if path.exists() else None
                        logging.getLogger("creator_os.photoshoot.queue").error(
                            "queue_replace_exhausted pid=%s role=%s destination=%s temporary=%s "
                            "lock=%s attempt=%s winerror=%s elapsed_ms=%.2f canonical_size=%s "
                            "canonical_mtime_ns=%s writable=%s",
                            os.getpid(), " ".join(sys.argv[:3]), path, temporary_path,
                            path.with_name(f".{path.name}.lock"), attempt + 1, winerror,
                            (time.monotonic() - started_at) * 1000,
                            getattr(stat, "st_size", None), getattr(stat, "st_mtime_ns", None), writable,
                        )
                        raise
                    logging.getLogger("creator_os.photoshoot.queue").warning(
                        "queue_replace_retry pid=%s role=%s destination=%s temporary=%s lock=%s "
                        "attempt=%s winerror=%s elapsed_ms=%.2f",
                        os.getpid(), " ".join(sys.argv[:3]), path, temporary_path,
                        path.with_name(f".{path.name}.lock"), attempt + 1, winerror,
                        (time.monotonic() - started_at) * 1000,
                    )
                    time.sleep(delays[attempt] + random.uniform(0, min(0.025, delays[attempt] / 4)))
        finally:
            if temporary_path is not None and temporary_path.exists():
                if replaced:
                    temporary_path.unlink()
                else:
                    recovery_path = path.with_name(
                        f".{path.name}.{time.time_ns()}.recovery"
                    )
                    try:
                        os.replace(temporary_path, recovery_path)
                        logging.getLogger("creator_os.photoshoot.queue").error(
                            "queue_recovery_preserved pid=%s destination=%s recovery=%s",
                            os.getpid(), path, recovery_path,
                        )
                    except OSError:
                        logging.getLogger("creator_os.photoshoot.queue").exception(
                            "queue_recovery_preserve_failed path=%s temporary_path=%s",
                            path, temporary_path,
                        )

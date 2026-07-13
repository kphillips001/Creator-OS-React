"""Creator OS Photoshoot Queue service."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.creative_director import PromptPlan, new_id
from app.models.generation_engine import GenerationMediaType, GenerationType, utc_now
from app.models.photoshoot_queue import (
    PHOTOSHOOT_ASSET_METADATA_KEY,
    PhotoshootProgress,
    PhotoshootRequest,
    PhotoshootResult,
    PhotoshootSession,
)
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class PhotoshootQueueService:
    """Owns creative sequencing and review-gated photoshoot progress."""

    DEFAULT_STORAGE_DIR = Path("data") / "photoshoot_queue"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        generation_ingestion_service: GenerationResultIngestionService | None = None,
        asset_repository=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
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
        provider_id: str = "future_provider",
        reference_asset_id: int | None = None,
        creator_notes: str | None = None,
        creative_continuity: Mapping[str, Any] | None = None,
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
            provider_id=provider_id,
            creator_notes=creator_notes,
            creative_continuity={
                "prompt_count": len(plans),
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
        sessions = list(self.list_sessions())
        sessions.insert(0, session)
        existing_requests = list(self.list_requests())
        existing_requests.extend(requests)
        self._write_sessions(sessions)
        self._write_requests(existing_requests)
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
                "creative_continuity": dict(session.creative_continuity or {}),
                **(
                    {
                        "reference_image_url": dict(next_request.metadata or {}).get("active_reference_output_reference")
                        or dict(session.creative_continuity or {}).get("seed_output_reference")
                    }
                    if (
                        dict(next_request.metadata or {}).get("active_reference_output_reference")
                        or dict(session.creative_continuity or {}).get("seed_output_reference")
                    )
                    else {}
                ),
            },
        )
        updated_request = replace(
            next_request,
            status="generating",
            generation_job_id=job.job_id,
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
        self._replace_request(updated_request)
        self._replace_session(updated_session)
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
        updated = replace(
            request,
            status="awaiting_review",
            imported_asset_ids=asset_ids,
            metadata={**dict(request.metadata or {}), "generated_image_ids": generated_ids},
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
    ) -> tuple[PhotoshootSession, bool]:
        """Open a persisted Photoshoot Studio session with a generated image as seed."""
        for session in self.list_sessions(creator_profile_id=record.creator_profile_id):
            if session.status in {"completed", "cancelled"}:
                continue
            continuity = dict(session.creative_continuity or {})
            if continuity.get("seed_image_id") == record.image_id:
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
                "seed_generation_job_id": record.generation_job_id,
                "seed_generation_request_id": record.generation_request_id,
                "seed_generation_result_id": record.generation_result_id,
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
        next_index = max((request.sequence_index for request in requests), default=0) + 1
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
            },
        )
        all_requests = list(self.list_requests())
        all_requests.append(request)
        self._write_requests(all_requests)
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
                    "direction_approved": False,
                    "workflow_stage": "ready_for_next_shot",
                    "current_shot_image_id": generated_image_ids[-1] if generated_image_ids else continuity.get("current_shot_image_id"),
                    "progression_stage": max(
                        int(continuity.get("progression_stage") or 0),
                        len(tuple(request for request in self.requests_for_session(updated.session_id) if request.status == "approved")),
                    ),
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
        self._replace_session(replace(session, current_request_id=None, updated_at=utc_now()))
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
            if session.status not in {"completed", "cancelled", "junked"}
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
        updated = replace(
            session,
            provider_id=str(provider_id or session.provider_id),
            creative_mode=str(creative_mode or session.creative_mode),
            creative_continuity=continuity,
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
        sessions = [updated if session.session_id == updated.session_id else session for session in self.list_sessions()]
        self._write_sessions(sessions)

    def _replace_request(self, updated: PhotoshootRequest) -> None:
        requests = [updated if request.request_id == updated.request_id else request for request in self.list_requests()]
        self._write_requests(requests)

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

    @staticmethod
    def _read_json(path: Path, default):
        try:
            if not path.exists():
                return default
            with open(path, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError):
            return default

    @staticmethod
    def _write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, default=str)

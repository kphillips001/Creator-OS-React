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

    def approve_request(self, request_id: str, *, notes: str | None = None) -> PhotoshootRequest:
        request = self.get_request(request_id)
        updated = replace(
            request,
            status="approved",
            review_status="approved",
            review_notes=notes,
            updated_at=utc_now(),
        )
        self._replace_request(updated)
        session = self.get_session(updated.session_id)
        self._replace_session(replace(session, current_request_id=None, updated_at=utc_now()))
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
        for session in self.list_sessions(creator_profile_id=creator_profile_id):
            if session.status not in {"completed", "cancelled"}:
                return session
        return None

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

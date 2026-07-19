"""Edit Studio workflow service."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.creative_director import PromptPlan, new_id
from app.models.edit_studio import EDIT_MODE_OPTIONS, EditHistoryEntry, EditRequest, EditSession
from app.models.generation_engine import GenerationMediaType, GenerationType, utc_now
from app.models.generation_library import GeneratedImageRecord
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService


class EditStudioService:
    """Owns edit workflow state and submits execution to Generation Engine."""

    DEFAULT_STORAGE_DIR = Path("data") / "edit_studio"

    def __init__(self, *, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)

    @property
    def sessions_path(self) -> Path:
        return self.storage_dir / "edit_sessions.json"

    @property
    def edit_items_path(self) -> Path:
        return self.storage_dir / "edit_items.json"

    def create_session(
        self,
        *,
        creator_profile_id: int,
        source_image_ids: Iterable[str],
        edit_mode: str,
        title: str = "Edit Session",
        metadata: Mapping[str, Any] | None = None,
    ) -> EditSession:
        source_ids = tuple(str(image_id) for image_id in source_image_ids if str(image_id))
        if not source_ids:
            raise ValueError("At least one source image is required.")
        mode = self.normalize_mode(edit_mode)
        session = EditSession(
            session_id=new_id("edit_session"),
            creator_profile_id=int(creator_profile_id),
            source_image_ids=source_ids,
            edit_mode=mode,
            title=title,
            metadata=dict(metadata or {}),
        )
        sessions = list(self.list_sessions())
        sessions.insert(0, session)
        self._write_sessions(sessions)
        return session

    def create_edit_request(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        source_image_ids: Iterable[str],
        edit_mode: str,
        edit_prompt: str,
        provider_id: str,
        generation_library: GenerationLibraryService,
        generation_engine: GenerationEngineService,
        reference_image_id: str | None = None,
        reference_asset_id: int | None = None,
        batch_size: int = 1,
        references: Iterable[Mapping[str, Any]] | None = None,
    ) -> tuple[EditRequest, Any]:
        creator_profile_id = int((creator_profile or {}).get("id") or 0)
        if not creator_profile_id:
            raise ValueError("Creator Profile required before editing.")
        source_ids = tuple(str(image_id) for image_id in source_image_ids if str(image_id))
        if not source_ids:
            raise ValueError("Select at least one generated image before editing.")
        prompt = str(edit_prompt or "").strip()
        if not prompt:
            raise ValueError("Edit prompt is required.")
        mode = self.normalize_mode(edit_mode)
        reference_inputs = tuple(dict(reference) for reference in (references or ()))
        source_records = tuple(generation_library.get(image_id) for image_id in source_ids)
        reference_record = generation_library.get(reference_image_id) if reference_image_id else None
        session = self.create_session(
            creator_profile_id=creator_profile_id,
            source_image_ids=source_ids,
            edit_mode=mode,
            title=self._title_for_mode(mode),
            metadata={
                "owner": "Edit Studio",
                "reference_image_id": reference_image_id,
                "reference_asset_id": reference_asset_id,
                "references": reference_inputs,
            },
        )
        edit_item = EditRequest(
            edit_request_id=new_id("edit_request"),
            session_id=session.session_id,
            creator_profile_id=creator_profile_id,
            source_image_ids=source_ids,
            edit_mode=mode,
            edit_prompt=prompt,
            provider_id=str(provider_id or "future_provider"),
            reference_image_id=reference_image_id,
            reference_asset_id=reference_asset_id,
            batch_size=max(1, int(batch_size or 1)),
            metadata={
                "source_output_references": tuple(record.output_reference for record in source_records),
                "reference_output_reference": reference_record.output_reference if reference_record else None,
                "references": reference_inputs,
            },
        )
        plan = self._prompt_plan_for_edit(
            edit_item,
            source_records=source_records,
            reference_record=reference_record,
        )
        job = generation_engine.queue_prompt_plan(
            creator_profile=creator_profile or {"id": creator_profile_id},
            prompt_plan=plan,
            provider_id=edit_item.provider_id,
            generation_type=GenerationType.IMAGE_TO_IMAGE.value,
            media_type=GenerationMediaType.IMAGE.value,
            image_count=edit_item.batch_size,
            metadata={
                "source": "edit_studio",
                "workflow_type": "edit",
                "edit_session_id": edit_item.session_id,
                "edit_request_id": edit_item.edit_request_id,
                "edit_mode": edit_item.edit_mode,
                "source_image_ids": edit_item.source_image_ids,
                "reference_image_id": edit_item.reference_image_id,
                "reference_asset_id": edit_item.reference_asset_id,
                "references": reference_inputs,
                "reference_image_url": source_records[0].output_reference,
                "edit_source_output_reference": source_records[0].output_reference,
                "edit_reference_output_reference": reference_record.output_reference if reference_record else None,
                "generation_library_return": True,
            },
        )
        updated = replace(
            edit_item,
            generation_job_id=job.job_id,
            status="submitted",
            updated_at=utc_now(),
        )
        self._write_edit_items([updated, *self.list_edit_requests()])
        return updated, job

    def batch_edit(
        self,
        *,
        creator_profile: Mapping[str, Any] | None,
        source_image_ids: Iterable[str],
        edit_prompt: str,
        provider_id: str,
        generation_library: GenerationLibraryService,
        generation_engine: GenerationEngineService,
    ) -> tuple[EditRequest, Any]:
        ids = tuple(source_image_ids)
        return self.create_edit_request(
            creator_profile=creator_profile,
            source_image_ids=ids,
            edit_mode="multi_image",
            edit_prompt=edit_prompt,
            provider_id=provider_id,
            generation_library=generation_library,
            generation_engine=generation_engine,
            batch_size=max(1, len(ids)),
        )

    def sync_generation_library(
        self,
        *,
        generation_engine: GenerationEngineService,
        generation_library: GenerationLibraryService,
    ):
        return generation_library.sync_jobs(
            job
            for job in generation_engine.list_jobs()
            if job.request.metadata.get("source") == "edit_studio"
        )

    def history(self, *, creator_profile_id: int | None = None, limit: int = 25) -> tuple[EditHistoryEntry, ...]:
        sessions = self.list_sessions()
        edit_items = self.list_edit_requests()
        if creator_profile_id is not None:
            sessions = tuple(session for session in sessions if session.creator_profile_id == int(creator_profile_id))
        entries = []
        for session in sessions[: max(1, int(limit or 25))]:
            latest = next((item for item in edit_items if item.session_id == session.session_id), None)
            entries.append(EditHistoryEntry(session=session, edit_request=latest))
        return tuple(entries)

    def list_sessions(self) -> tuple[EditSession, ...]:
        return tuple(self._session_from_dict(item) for item in self._read_json(self.sessions_path, []))

    def list_edit_requests(self) -> tuple[EditRequest, ...]:
        return tuple(self._edit_request_from_dict(item) for item in self._read_json(self.edit_items_path, []))

    @staticmethod
    def normalize_mode(edit_mode: str) -> str:
        mode = str(edit_mode or "single_image").strip().lower()
        return mode if mode in EDIT_MODE_OPTIONS else "single_image"

    @staticmethod
    def _title_for_mode(mode: str) -> str:
        return {
            "single_image": "Single Image Edit",
            "multi_image": "Multi Image Edit",
            "face_replacement": "Face Replacement Edit",
            "style_transfer": "Style Transfer Edit",
            "variation": "Variation Edit",
        }.get(mode, "Edit Session")

    @staticmethod
    def _prompt_plan_for_edit(
        edit_item: EditRequest,
        *,
        source_records: tuple[GeneratedImageRecord, ...],
        reference_record: GeneratedImageRecord | None,
    ) -> PromptPlan:
        source_text = ", ".join(record.image_id for record in source_records)
        reference_text = (
            f" Use generated reference image {reference_record.image_id} as the secondary visual reference."
            if reference_record
            else ""
        )
        asset_text = (
            f" Use Reference Asset #{edit_item.reference_asset_id} for identity/reference continuity."
            if edit_item.reference_asset_id
            else ""
        )
        return PromptPlan(
            plan_id=new_id("prompt_plan"),
            session_id=edit_item.session_id,
            creator_profile_id=edit_item.creator_profile_id,
            prompt_text=(
                f"Edit Studio {edit_item.edit_mode} request. "
                f"Source generated image(s): {source_text}. "
                f"Edit prompt: {edit_item.edit_prompt}."
                f"{reference_text}{asset_text} "
                "Preserve the creator identity and only change details requested by the edit prompt."
            ),
            creative_mode=f"edit_{edit_item.edit_mode}",
            creative_tags=(edit_item.edit_mode, "edit_studio"),
            reference_asset_id=edit_item.reference_asset_id or source_records[0].reference_asset_id,
            reference_asset_path=None,
            creative_rationale="Edit request converted to a provider-neutral Prompt Plan for Generation Engine.",
            prompt_metadata={
                "owner": "Edit Studio",
                "provider_neutral": True,
                "edit_request_id": edit_item.edit_request_id,
                "edit_mode": edit_item.edit_mode,
                "source_image_ids": edit_item.source_image_ids,
                "reference_image_id": edit_item.reference_image_id,
                "batch_size": edit_item.batch_size,
                "references": tuple(dict(edit_item.metadata or {}).get("references") or ()),
            },
        )

    @staticmethod
    def _session_from_dict(data: Mapping[str, Any]) -> EditSession:
        return EditSession(
            session_id=str(data.get("session_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            source_image_ids=tuple(data.get("source_image_ids") or ()),
            edit_mode=str(data.get("edit_mode") or "single_image"),
            title=str(data.get("title") or "Edit Session"),
            status=str(data.get("status") or "active"),
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _edit_request_from_dict(data: Mapping[str, Any]) -> EditRequest:
        return EditRequest(
            edit_request_id=str(data.get("edit_request_id") or ""),
            session_id=str(data.get("session_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            source_image_ids=tuple(data.get("source_image_ids") or ()),
            edit_mode=str(data.get("edit_mode") or "single_image"),
            edit_prompt=str(data.get("edit_prompt") or ""),
            provider_id=str(data.get("provider_id") or "future_provider"),
            reference_image_id=data.get("reference_image_id"),
            reference_asset_id=data.get("reference_asset_id"),
            batch_size=max(1, int(data.get("batch_size") or 1)),
            status=str(data.get("status") or "queued"),
            generation_job_id=data.get("generation_job_id"),
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata") or {},
        )

    def _write_sessions(self, sessions: list[EditSession]) -> None:
        self._write_json(self.sessions_path, [asdict(session) for session in sessions])

    def _write_edit_items(self, edit_items: list[EditRequest]) -> None:
        self._write_json(self.edit_items_path, [asdict(item) for item in edit_items])

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

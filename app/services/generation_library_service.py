"""Generation Library service."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationJob, GenerationMediaType, GenerationStatus, GenerationType, utc_now
from app.models.generation_library import (
    GeneratedImageRecord,
    GenerationLibraryActionResult,
    GenerationLibraryFilter,
    GenerationLibraryResult,
)
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class GenerationLibraryService:
    """Owns generated-image review state before Creator OS asset import."""

    DEFAULT_STORAGE_DIR = Path("data") / "generation_library"

    def __init__(self, *, storage_dir: str | Path | None = None):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)

    @property
    def records_path(self) -> Path:
        return self.storage_dir / "generated_images.json"

    def sync_job(self, job: GenerationJob) -> tuple[GeneratedImageRecord, ...]:
        if job.status != GenerationStatus.SUCCEEDED.value or job.result is None:
            return ()
        records = list(self.list_records())
        existing_keys = {
            (record.generation_job_id, record.output_reference)
            for record in records
        }
        created = []
        for output_reference in job.result.output_references:
            key = (job.job_id, output_reference)
            if key in existing_keys:
                continue
            record = self._record_from_job(job, output_reference)
            records.append(record)
            created.append(record)
        if created:
            self._write_records(records)
        return tuple(created)

    def sync_jobs(self, jobs: Iterable[GenerationJob]) -> tuple[GeneratedImageRecord, ...]:
        created = []
        for job in jobs:
            created.extend(self.sync_job(job))
        return tuple(created)

    def browse(
        self,
        filters: GenerationLibraryFilter | None = None,
    ) -> GenerationLibraryResult:
        filters = filters or GenerationLibraryFilter()
        search = str(filters.search or "").strip().lower()
        records = []
        for record in self.list_records():
            if filters.creator_profile_id is not None and record.creator_profile_id != int(filters.creator_profile_id):
                continue
            if filters.provider_id and record.provider_id != filters.provider_id:
                continue
            if filters.status and record.status != filters.status:
                continue
            if filters.creative_mode and record.creative_mode != filters.creative_mode:
                continue
            if filters.photoshoot_session_id and record.photoshoot_session_id != filters.photoshoot_session_id:
                continue
            if filters.reference_asset_id is not None and record.reference_asset_id != int(filters.reference_asset_id):
                continue
            if filters.selected_only and not record.selected:
                continue
            haystack = " ".join(
                (
                    record.image_id,
                    record.generation_job_id,
                    record.provider_id,
                    record.prompt_plan_id,
                    record.prompt_text,
                    record.creative_mode or "",
                    record.photoshoot_session_id or "",
                    str(record.reference_asset_id or ""),
                )
            ).lower()
            if search and search not in haystack:
                continue
            records.append(record)
        reverse = filters.sort != "oldest"
        if filters.sort in {"provider", "status"}:
            records.sort(key=lambda record: getattr(record, filters.sort if filters.sort != "provider" else "provider_id"))
        else:
            records.sort(key=lambda record: record.generation_date or record.created_at, reverse=reverse)
        return GenerationLibraryResult(records=tuple(records), filters=filters, total=len(records))

    def select(self, image_ids: Iterable[str], *, selected: bool = True) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        updated = []
        for record in self.list_records():
            if record.image_id in ids:
                updated.append(replace(record, selected=selected, updated_at=utc_now()))
            else:
                updated.append(record)
        self._write_records(updated)
        return GenerationLibraryActionResult(True, "Selection updated.", ids)

    def bulk_select(self, filters: GenerationLibraryFilter) -> GenerationLibraryActionResult:
        result = self.browse(filters)
        return self.select(tuple(record.image_id for record in result.records), selected=True)

    def move_to_junk(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        return self._set_status(image_ids, status="junk", message="Generated image(s) moved to Junk.")

    def archive(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        return self._set_status(image_ids, status="archived", message="Generated image(s) archived.")

    def restore(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        return self._set_status(image_ids, status="active", message="Generated image(s) restored.")

    def delete(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        records = [record for record in self.list_records() if record.image_id not in ids]
        self._write_records(records)
        return GenerationLibraryActionResult(True, "Generated image record(s) deleted.", ids)

    def regenerate(
        self,
        image_ids: Iterable[str],
        *,
        generation_engine: GenerationEngineService,
    ) -> GenerationLibraryActionResult:
        jobs = []
        errors = []
        records_by_id = {record.image_id: record for record in self.list_records()}
        for image_id in tuple(str(value) for value in image_ids):
            record = records_by_id.get(image_id)
            if record is None:
                errors.append(f"Generated image not found: {image_id}")
                continue
            plan = PromptPlan(
                plan_id=record.prompt_plan_id,
                session_id=record.photoshoot_session_id or record.generation_job_id,
                creator_profile_id=record.creator_profile_id,
                prompt_text=record.prompt_text,
                creative_mode=record.creative_mode or "social_safe",
                creative_tags=tuple(record.prompt_metadata.get("creative_tags") or ()),
                reference_asset_id=record.reference_asset_id,
                reference_asset_path=None,
                creative_rationale="Regeneration requested from Generation Library.",
                prompt_metadata={
                    "provider_neutral": True,
                    "generation_library_source_image_id": record.image_id,
                    **dict(record.prompt_metadata or {}),
                },
            )
            job = generation_engine.queue_prompt_plan(
                creator_profile={"id": record.creator_profile_id},
                prompt_plan=plan,
                provider_id=record.provider_id,
                generation_type=GenerationType.IMAGE_TO_IMAGE.value,
                media_type=GenerationMediaType.IMAGE.value,
                image_count=1,
                metadata={
                    "source": "generation_library_regenerate",
                    "generation_library_source_image_id": record.image_id,
                },
            )
            jobs.append(job.job_id)
            self._replace_record(replace(record, review_state="regenerate_requested", updated_at=utc_now()))
        return GenerationLibraryActionResult(
            success=not errors,
            message="Regeneration request queued." if jobs else "No regeneration request queued.",
            image_ids=tuple(jobs),
            errors=tuple(errors),
        )

    def add_to_creator_os(
        self,
        image_ids: Iterable[str],
        *,
        generation_engine: GenerationEngineService,
        ingestion_service: GenerationResultIngestionService,
    ) -> GenerationLibraryActionResult:
        imported_asset_ids = []
        errors = []
        records_by_id = {record.image_id: record for record in self.list_records()}
        selected_ids = tuple(str(value) for value in image_ids)
        for image_id in selected_ids:
            record = records_by_id.get(image_id)
            if record is None:
                errors.append(f"Generated image not found: {image_id}")
                continue
            if record.imported_asset_id is not None:
                imported_asset_ids.append(record.imported_asset_id)
                continue
            try:
                job = generation_engine.get_job(record.generation_job_id)
                if job.result is None:
                    raise RuntimeError("Generation Job has no result.")
                partial_job = replace(
                    job,
                    result=replace(job.result, output_references=(record.output_reference,)),
                )
                ingestion = ingestion_service.ingest_job(partial_job)
                if not ingestion.success or not ingestion.imported_asset_ids:
                    raise RuntimeError("; ".join(ingestion.errors) or "Generation output was not imported.")
                asset_id = int(ingestion.imported_asset_ids[0])
                imported_asset_ids.append(asset_id)
                self._replace_record(
                    replace(
                        record,
                        status="added_to_creator_os",
                        review_state="added_to_creator_os",
                        imported_asset_id=asset_id,
                        updated_at=utc_now(),
                    )
                )
            except Exception as exc:
                errors.append(str(exc))
        return GenerationLibraryActionResult(
            success=not errors,
            message="Generated image(s) added to Creator OS." if not errors else "Some generated images could not be added.",
            image_ids=selected_ids,
            imported_asset_ids=tuple(imported_asset_ids),
            errors=tuple(errors),
        )

    def get(self, image_id: str) -> GeneratedImageRecord:
        for record in self.list_records():
            if record.image_id == image_id:
                return record
        raise KeyError(f"Generated image not found: {image_id}")

    def list_records(self) -> tuple[GeneratedImageRecord, ...]:
        return tuple(self._record_from_dict(item) for item in self._read_json(self.records_path, []))

    def _set_status(
        self,
        image_ids: Iterable[str],
        *,
        status: str,
        message: str,
    ) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        updated = []
        for record in self.list_records():
            if record.image_id in ids:
                updated.append(replace(record, status=status, review_state=status, selected=False, updated_at=utc_now()))
            else:
                updated.append(record)
        self._write_records(updated)
        return GenerationLibraryActionResult(True, message, ids)

    def _replace_record(self, updated: GeneratedImageRecord) -> None:
        records = [updated if record.image_id == updated.image_id else record for record in self.list_records()]
        self._write_records(records)

    @staticmethod
    def _record_from_job(job: GenerationJob, output_reference: str) -> GeneratedImageRecord:
        result = job.result
        request_metadata = dict(job.request.metadata or {})
        image_id = "generated_image_" + hashlib.sha256(
            f"{job.job_id}:{output_reference}".encode("utf-8")
        ).hexdigest()[:24]
        return GeneratedImageRecord(
            image_id=image_id,
            generation_job_id=job.job_id,
            generation_request_id=job.request.request_id,
            generation_result_id=result.result_id,
            output_reference=output_reference,
            creator_profile_id=job.request.creator_profile_id,
            provider_id=job.request.provider_id,
            prompt_plan_id=job.request.prompt_plan_id,
            prompt_text=job.request.prompt_text,
            creative_mode=request_metadata.get("creative_mode"),
            reference_asset_id=job.request.reference_asset_id,
            photoshoot_session_id=request_metadata.get("photoshoot_session_id"),
            photoshoot_request_id=request_metadata.get("photoshoot_request_id"),
            generation_date=result.created_at or job.completed_at or job.updated_at,
            provider_metadata=dict(result.generation_metadata or {}),
            prompt_metadata={
                "creative_tags": tuple(request_metadata.get("creative_tags") or ()),
                "prompt_metadata": dict(request_metadata.get("prompt_metadata") or {}),
            },
            generation_metadata={
                "source": request_metadata.get("source"),
                "workflow_type": request_metadata.get("workflow_type") or request_metadata.get("source"),
                "generation_timestamp": result.created_at or job.completed_at or job.updated_at,
                "reference_metadata": dict(request_metadata.get("reference_metadata") or {}),
                "reference_file_name": request_metadata.get("reference_file_name"),
                "reference_preview_path": request_metadata.get("reference_preview_path"),
                "creative_tags": tuple(request_metadata.get("creative_tags") or ()),
                "creative_mode": request_metadata.get("creative_mode"),
                "output_reference": output_reference,
                "request_metadata": request_metadata,
                "execution_metadata": dict(result.execution_metadata or {}),
                "image_metadata": dict(result.image_metadata or {}),
            },
        )

    @staticmethod
    def _record_from_dict(data: Mapping[str, Any]) -> GeneratedImageRecord:
        return GeneratedImageRecord(
            image_id=str(data.get("image_id")),
            generation_job_id=str(data.get("generation_job_id")),
            generation_request_id=str(data.get("generation_request_id")),
            generation_result_id=str(data.get("generation_result_id")),
            output_reference=str(data.get("output_reference") or ""),
            creator_profile_id=int(data.get("creator_profile_id")),
            provider_id=str(data.get("provider_id") or ""),
            prompt_plan_id=str(data.get("prompt_plan_id") or ""),
            prompt_text=str(data.get("prompt_text") or ""),
            creative_mode=data.get("creative_mode"),
            reference_asset_id=data.get("reference_asset_id"),
            photoshoot_session_id=data.get("photoshoot_session_id"),
            photoshoot_request_id=data.get("photoshoot_request_id"),
            generation_date=data.get("generation_date") or "",
            status=str(data.get("status") or "active"),
            review_state=str(data.get("review_state") or "unreviewed"),
            selected=bool(data.get("selected", False)),
            imported_asset_id=data.get("imported_asset_id"),
            provider_metadata=data.get("provider_metadata") or {},
            prompt_metadata=data.get("prompt_metadata") or {},
            generation_metadata=data.get("generation_metadata") or {},
            created_at=data.get("created_at") or "",
            updated_at=data.get("updated_at"),
        )

    def _write_records(self, records: list[GeneratedImageRecord]) -> None:
        self._write_json(self.records_path, [asdict(record) for record in records])

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

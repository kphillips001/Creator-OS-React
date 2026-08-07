"""Ingest completed generation results into Creator OS Assets."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

from app.models.creator_intent import CreatorIntent
from app.models.generation_engine import GenerationJob, GenerationResult, GenerationStatus, new_generation_id, utc_now
from app.models.generation_ingestion import (
    GENERATION_ASSET_METADATA_KEY,
    GenerationAssetIngestionRecord,
    GenerationResultIngestionResult,
)
from app.services.ai_import_workflow_service import AIImportWorkflowService


class GenerationResultIngestionService:
    """Downloads provider outputs and imports them through Creator OS asset ingestion."""

    IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    VIDEO_SUFFIXES = {".m4v", ".mov", ".mp4", ".webm"}
    DEFAULT_STORAGE_DIR = Path("data") / "generation_engine"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        download_dir: str | Path | None = None,
        import_workflow_service: AIImportWorkflowService | None = None,
        asset_repository=None,
        http_client=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.download_dir = Path(download_dir or self.storage_dir / "downloads")
        self.import_workflow = import_workflow_service or AIImportWorkflowService()
        self.asset_repository = asset_repository
        self.http_client = http_client or requests

    @property
    def records_path(self) -> Path:
        return self.storage_dir / "generation_ingestions.json"

    @property
    def assets(self):
        if self.asset_repository is not None:
            return self.asset_repository
        return self.import_workflow.assets

    def ingest_job(self, job: GenerationJob) -> GenerationResultIngestionResult:
        if job.status != GenerationStatus.SUCCEEDED.value or job.result is None:
            record = self._failure_record(
                job=job,
                result=job.result,
                output_reference="",
                message="Generation Job is not successful.",
            )
            self._upsert_record(record)
            return GenerationResultIngestionResult(
                success=False,
                generation_job_id=job.job_id,
                records=(record,),
                errors=(record.message or "Generation Job is not successful.",),
            )

        imported_asset_ids: list[int] = []
        records: list[GenerationAssetIngestionRecord] = []
        errors: list[str] = []
        for output_reference in job.result.output_references:
            existing = self._successful_record_for_output(job.job_id, output_reference)
            if existing:
                records.append(existing)
                if existing.asset_id is not None:
                    imported_asset_ids.append(existing.asset_id)
                continue

            try:
                local_file = self._materialize_output_reference(
                    output_reference,
                    job=job,
                )
                is_video = Path(local_file).suffix.lower() in self.VIDEO_SUFFIXES
                upload_intent = "teaser_video" if is_video else "teaser_image"
                import_result = self.import_workflow.import_asset(
                    media_path=local_file,
                    upload_intent=upload_intent,
                    creator_profile_id=job.request.creator_profile_id,
                    creator_intent=CreatorIntent.create(
                        "single_asset",
                        legacy_upload_intent=upload_intent,
                        metadata={
                            "source": "content_studio",
                            "generation_job_id": job.job_id,
                            "generation_request_id": job.request.request_id,
                            "prompt_plan_id": job.request.prompt_plan_id,
                        },
                    ),
                    original_filename=Path(local_file).name,
                    create_product_draft=False,
                    provider_upload_enabled=False,
                    is_test=False,
                    import_session_id=f"generation:{job.job_id}",
                )
                asset_id = getattr(import_result, "content_id", None)
                if not getattr(import_result, "success", False) or asset_id is None:
                    raise RuntimeError(self._import_error(import_result))
                metadata = self._generation_asset_metadata(
                    job=job,
                    result=job.result,
                    output_reference=output_reference,
                )
                self._merge_asset_generation_metadata(asset_id, metadata)
                record = GenerationAssetIngestionRecord(
                    ingestion_id=new_generation_id("generation_ingestion"),
                    generation_job_id=job.job_id,
                    generation_request_id=job.request.request_id,
                    generation_result_id=job.result.result_id,
                    output_reference=output_reference,
                    status="imported",
                    asset_id=int(asset_id),
                    local_file_path=str(local_file),
                    message="Generation result imported as Creator OS Asset.",
                    metadata=metadata,
                )
                self._upsert_record(record)
                records.append(record)
                imported_asset_ids.append(int(asset_id))
            except Exception as exc:
                record = self._failure_record(
                    job=job,
                    result=job.result,
                    output_reference=output_reference,
                    message=str(exc),
                )
                self._upsert_record(record)
                records.append(record)
                errors.append(str(exc))

        return GenerationResultIngestionResult(
            success=not errors,
            generation_job_id=job.job_id,
            imported_asset_ids=tuple(imported_asset_ids),
            records=tuple(records),
            errors=tuple(errors),
        )

    def records_for_job(self, generation_job_id: str) -> tuple[GenerationAssetIngestionRecord, ...]:
        return tuple(
            record
            for record in self.list_records()
            if record.generation_job_id == generation_job_id
        )

    def ingestion_status_for_job(self, generation_job_id: str) -> Mapping[str, Any]:
        records = self.records_for_job(generation_job_id)
        imported = tuple(record for record in records if record.status == "imported")
        failed = tuple(record for record in records if record.status == "failed")
        return {
            "generation_job_id": generation_job_id,
            "status": "failed" if failed and not imported else ("imported" if imported else "pending"),
            "generated_result_count": len(records),
            "imported_asset_ids": tuple(record.asset_id for record in imported if record.asset_id is not None),
            "failed_messages": tuple(record.message for record in failed if record.message),
        }

    def list_records(self) -> tuple[GenerationAssetIngestionRecord, ...]:
        return tuple(self._record_from_dict(item) for item in self._read_json(self.records_path, []))

    def _materialize_output_reference(self, output_reference: str, *, job: GenerationJob) -> Path:
        reference = str(output_reference or "").strip()
        if not reference:
            raise ValueError("Generation output reference is empty.")
        parsed = urlparse(reference)
        if parsed.scheme in {"http", "https"}:
            suffix = Path(parsed.path).suffix.lower() or ".png"
            if suffix not in self.IMAGE_SUFFIXES and suffix not in self.VIDEO_SUFFIXES:
                suffix = ".png"
            destination = self.download_dir / job.job_id / f"{self._reference_hash(reference)}{suffix}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            response = self.http_client.get(reference, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status()
            destination.write_bytes(response.content)
            return destination

        source = Path(reference).expanduser()
        if not source.exists():
            raise FileNotFoundError(f"Generation output was not found: {reference}")
        suffix = source.suffix.lower() or ".png"
        destination = self.download_dir / job.job_id / f"{self._reference_hash(str(source.resolve()))}{suffix}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        return destination

    def _merge_asset_generation_metadata(self, asset_id: int, generation_metadata: Mapping[str, Any]) -> None:
        asset = self.assets.get_by_id(asset_id)
        current = dict(getattr(asset, "media_metadata", None) or {})
        current[GENERATION_ASSET_METADATA_KEY] = dict(generation_metadata)
        update = getattr(self.assets, "update_media_metadata", None)
        if not callable(update):
            raise RuntimeError("Asset repository does not support media metadata updates.")
        update(asset_id, current)

    @staticmethod
    def _generation_asset_metadata(
        *,
        job: GenerationJob,
        result: GenerationResult,
        output_reference: str,
    ) -> dict[str, Any]:
        request_metadata = dict(job.request.metadata or {})
        return {
            "source": "content_studio",
            "generation_provider": job.request.provider_id,
            "generation_job_id": job.job_id,
            "generation_request_id": job.request.request_id,
            "generation_result_id": result.result_id,
            "prompt_plan_id": job.request.prompt_plan_id,
            "prompt_text": job.request.prompt_text,
            "creative_mode": request_metadata.get("creative_mode"),
            "creative_tags": tuple(request_metadata.get("creative_tags") or ()),
            "reference_asset_id": job.request.reference_asset_id,
            "creator_profile_id": job.request.creator_profile_id,
            "provider_response_id": result.generation_metadata.get("provider_request_id"),
            "generation_parameters": {
                "generation_type": job.request.generation_type,
                "media_type": job.request.media_type,
                "image_count": job.request.image_count,
                "request_metadata": request_metadata,
                "provider_generation_metadata": dict(result.generation_metadata or {}),
                "provider_execution_metadata": dict(result.execution_metadata or {}),
                "image_metadata": dict(result.image_metadata or {}),
            },
            "output_reference": output_reference,
            "ingested_at": utc_now(),
        }

    def _successful_record_for_output(
        self,
        generation_job_id: str,
        output_reference: str,
    ) -> GenerationAssetIngestionRecord | None:
        for record in self.records_for_job(generation_job_id):
            if record.output_reference == output_reference and record.status == "imported":
                return record
        return None

    def _failure_record(
        self,
        *,
        job: GenerationJob,
        result: GenerationResult | None,
        output_reference: str,
        message: str,
    ) -> GenerationAssetIngestionRecord:
        return GenerationAssetIngestionRecord(
            ingestion_id=new_generation_id("generation_ingestion"),
            generation_job_id=job.job_id,
            generation_request_id=job.request.request_id,
            generation_result_id=result.result_id if result else "",
            output_reference=output_reference,
            status="failed",
            message=message,
        )

    @staticmethod
    def _import_error(import_result: Any) -> str:
        legacy = getattr(import_result, "legacy_result", {}) or {}
        return str(legacy.get("error") or legacy.get("message") or "AI Import Workflow did not return an asset.")

    def _upsert_record(self, record: GenerationAssetIngestionRecord) -> None:
        records = list(self.list_records())
        for index, existing in enumerate(records):
            if (
                existing.generation_job_id == record.generation_job_id
                and existing.output_reference == record.output_reference
                and existing.status == record.status
            ):
                records[index] = replace(record, ingestion_id=existing.ingestion_id, updated_at=utc_now())
                break
        else:
            records.append(record)
        self._write_json(self.records_path, [asdict(item) for item in records])

    @staticmethod
    def _reference_hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @classmethod
    def _record_from_dict(cls, data: Mapping[str, Any]) -> GenerationAssetIngestionRecord:
        return GenerationAssetIngestionRecord(
            ingestion_id=str(data.get("ingestion_id")),
            generation_job_id=str(data.get("generation_job_id")),
            generation_request_id=str(data.get("generation_request_id")),
            generation_result_id=str(data.get("generation_result_id")),
            output_reference=str(data.get("output_reference") or ""),
            status=str(data.get("status") or "pending"),
            asset_id=data.get("asset_id"),
            local_file_path=data.get("local_file_path"),
            message=data.get("message"),
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

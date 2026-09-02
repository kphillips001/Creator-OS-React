"""Generation Library service."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import threading
import time
from uuid import uuid4
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationJob, GenerationMediaType, GenerationStatus, GenerationType, utc_now
from app.models.generation_library import (
    GENERATION_LIBRARY_PAGE_SIZE,
    GeneratedImageRecord,
    GenerationLibraryActionResult,
    GenerationLibraryFilter,
    GenerationLibraryResult,
)
from app.services.content_archive_service import ContentArchiveService
from app.services.creator_approval_service import CreatorApprovalService
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService
from app.services.reference_asset_protection import is_protected_generation_metadata, is_protected_reference_asset
from app.repositories.asset_repository import AssetRepository
from app.services.creative_intelligence_learning_service import CreativeIntelligenceLearningService


class GenerationLibraryService:
    """Owns generated-image review state before Creator OS asset import."""

    DEFAULT_STORAGE_DIR = Path("data") / "generation_library"
    _version_restore_lock = threading.RLock()
    _performance_logger = logging.getLogger("creator-os-performance")

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        archive_service: ContentArchiveService | None = None,
        creator_approval_service: CreatorApprovalService | None = None,
        asset_repository: AssetRepository | None = None,
        creative_intelligence: CreativeIntelligenceLearningService | None = None,
        recipe_capture_service=None,
        projection_repository=None,
        canonical_repository=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self._uses_default_storage = storage_dir is None
        self._projection_repository = projection_repository
        self._canonical_repository = canonical_repository
        self._canonical_bootstrapped = False
        self.archive_service = archive_service or ContentArchiveService()
        self.creator_approval = creator_approval_service or CreatorApprovalService(
            storage_dir=self.storage_dir / "creator_approvals"
        )
        self.assets = asset_repository or AssetRepository()
        self.creative_intelligence = creative_intelligence or CreativeIntelligenceLearningService()
        self.recipe_capture = recipe_capture_service

    def _projection(self):
        if not self._uses_default_storage and self._projection_repository is None:
            return None
        if self._projection_repository is None:
            from app.repositories.generation_library_projection_repository import GenerationLibraryProjectionRepository
            self._projection_repository = GenerationLibraryProjectionRepository()
        return self._projection_repository

    def _canonical(self):
        if not self._uses_default_storage and self._canonical_repository is None:
            return None
        if self._canonical_repository is None:
            from app.repositories.generation_library_record_repository import GenerationLibraryRecordRepository
            self._canonical_repository = GenerationLibraryRecordRepository()
        return self._canonical_repository

    def _ensure_canonical(self) -> None:
        canonical = self._canonical()
        if canonical is None or self._canonical_bootstrapped:
            return
        count = canonical.count()
        legacy_version = self._legacy_source_version()
        if count == 0:
            legacy = tuple(self._record_from_dict(item) for item in self._read_json(self.records_path, []))
            canonical.replace_all(legacy, legacy_version=legacy_version, bootstrap=True)
        self._canonical_bootstrapped = True

    def _legacy_source_version(self) -> str:
        try:
            stat = self.records_path.stat()
            return f"{stat.st_mtime_ns}:{stat.st_size}"
        except OSError:
            return "missing:0"

    def _source_version(self) -> str:
        canonical = self._canonical()
        if canonical is not None:
            self._ensure_canonical()
            return f"db:{canonical.state()[0]}"
        return self._legacy_source_version()

    def ensure_read_projection(self) -> None:
        projection = self._projection()
        if projection is not None and projection.source_version() != self._source_version():
            projection.synchronize(self.list_records(), source_version=self._source_version())

    def browse_page(self, filters: GenerationLibraryFilter | None = None, *, page: int = 1,
                    page_size: int = GENERATION_LIBRARY_PAGE_SIZE):
        """Use the indexed production projection; retain file behavior for isolated stores."""
        filters = filters or GenerationLibraryFilter()
        projection = self._projection()
        if projection is not None:
            self.ensure_read_projection()
            return projection.browse_page(filters, page=page, page_size=page_size)
        result = self.browse(filters)
        total_pages = max(1, (result.total + page_size - 1) // page_size)
        current_page = min(max(1, page), total_pages)
        start = (current_page - 1) * page_size
        active = self.browse(GenerationLibraryFilter(creator_profile_id=filters.creator_profile_id))
        return (result.records[start:start + page_size], result.total,
                tuple(sorted({item.provider_id for item in active.records})),
                tuple(sorted({item.creative_mode for item in active.records if item.creative_mode})))

    def staged_records(self, *, creator_profile_id: int, search: str | None = None):
        projection = self._projection()
        if projection is not None:
            self.ensure_read_projection()
            return projection.staged(creator_profile_id=creator_profile_id, search=search)
        return tuple(record for record in self.list_records()
                     if record.creator_profile_id == int(creator_profile_id)
                     and record.status == "staged_asset_library")

    def staged_count(self, creator_profile_id: int) -> int:
        projection = self._projection()
        if projection is not None:
            self.ensure_read_projection()
            return projection.staged_count(creator_profile_id)
        return len(self.staged_records(creator_profile_id=creator_profile_id))

    def projected_get(self, image_id: str) -> GeneratedImageRecord:
        projection = self._projection()
        if projection is None:
            return self.get(image_id)
        self.ensure_read_projection()
        record = projection.get(image_id)
        if record is None:
            raise KeyError(f"Generated image not found: {image_id}")
        return record

    def get_with_effective_classification(self, image_id: str) -> GeneratedImageRecord:
        canonical = self.get(image_id)
        projected = self.projected_get(image_id)
        return replace(canonical, content_classification=projected.content_classification,
                       classification_source=projected.classification_source)

    def classify_content(self, image_id: str, *, creator_profile_id: int, classification: str) -> dict:
        from app.repositories.generation_library_classification_repository import GenerationLibraryClassificationRepository
        result = GenerationLibraryClassificationRepository().classify_unclassified(
            image_id=image_id, creator_profile_id=creator_profile_id, classification=classification,
        )
        if result is None:
            raise ValueError("Only an Unclassified Generation Library image can be manually classified.")
        return result

    def bulk_classify_content(self, image_ids: Iterable[str], *, creator_profile_id: int,
                              classification: str) -> tuple[dict, ...]:
        from app.repositories.generation_library_classification_repository import GenerationLibraryClassificationRepository
        return GenerationLibraryClassificationRepository().bulk_classify_unclassified(
            image_ids=tuple(image_ids), creator_profile_id=creator_profile_id,
            classification=classification,
        )

    def bulk_archive_unclassified(self, image_ids: Iterable[str], *, creator_profile_id: int) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id).strip() for image_id in image_ids)
        if not ids:
            raise ValueError("At least one image is required.")
        if len(ids) > 100:
            raise ValueError("Bulk Archive supports at most 100 images.")
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate image IDs are not allowed.")
        projection = self._projection()
        if projection is None:
            raise RuntimeError("Bulk Archive requires the canonical Generation Library repository.")
        self.ensure_read_projection()
        eligible = projection.eligible_unclassified_ids(ids, creator_profile_id=creator_profile_id)
        if eligible != set(ids):
            raise ValueError(
                "Every selected image must belong to the active creator and still be an eligible Unclassified image."
            )
        result = self.delete(ids)
        if not result.success or set(result.image_ids) != set(ids):
            raise RuntimeError("Bulk Archive could not archive the complete selection.")
        return result

    @property
    def records_path(self) -> Path:
        return self.storage_dir / "generated_images.json"

    @property
    def reviewed_edit_outputs_path(self) -> Path:
        return self.storage_dir / "reviewed_edit_outputs.json"

    @property
    def video_queue_path(self) -> Path:
        return self.storage_dir / "video_queue.json"

    @property
    def photoshoot_root(self) -> Path:
        return self.archive_service.content_paths()["generation_active"].parent / "Photoshoot"

    def sync_job(self, job: GenerationJob) -> tuple[GeneratedImageRecord, ...]:
        if job.status != GenerationStatus.SUCCEEDED.value or job.result is None:
            return ()
        request_metadata = dict(job.request.metadata or {})
        if str(
            request_metadata.get("workflow_type")
            or request_metadata.get("source")
            or ""
        ).upper() == "REGENERATION_STUDIO":
            # Regenerated variations remain in their durable review workspace
            # until a later explicit promotion action. Global succeeded-job
            # synchronization must never make them visible prematurely.
            return ()
        prospective = tuple(
            self._record_from_job(job, output_reference, output_index=index)
            for index, output_reference in enumerate(job.result.output_references)
        )
        projection = self._projection()
        if projection is not None and hasattr(projection, "existing_identities"):
            self.ensure_read_projection()
            existing_image_ids, existing_keys = projection.existing_identities(
                generation_job_id=job.job_id,
                output_references=job.result.output_references,
                image_ids=(item.image_id for item in prospective),
            )
        else:
            records = self.list_records()
            existing_image_ids = {record.image_id for record in records}
            existing_keys = {(record.generation_job_id, reference) for record in records for reference in self._record_output_references(record)}
        archived_output_references = self._archived_output_references()
        archived_image_ids = self._archived_image_ids()
        created = []
        for output_index, output_reference in enumerate(job.result.output_references):
            key = (job.job_id, output_reference)
            record = prospective[output_index]
            if (
                key in existing_keys
                or output_reference in archived_output_references
                or record.image_id in existing_image_ids
                or record.image_id in archived_image_ids
            ):
                continue
            record = self.archive_service.materialize_generation(record)
            if record.generation_recipe_id:
                if self.recipe_capture is None:
                    from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService
                    self.recipe_capture = GenerationRecipeCaptureService()
                self.recipe_capture.associate_output(
                    record.generation_recipe_id,
                    result_id=job.result.result_id,
                    image_id=record.image_id,
                    output_index=0,
                    output_reference=record.output_reference,
                )
            existing_image_ids.add(record.image_id)
            created.append(record)
        if created:
            self._append_records(created)
        return tuple(created)

    def sync_jobs(self, jobs: Iterable[GenerationJob]) -> tuple[GeneratedImageRecord, ...]:
        created = []
        for job in jobs:
            created.extend(self.sync_job(job))
        return tuple(created)

    def promote_regeneration_result(self, *, job: GenerationJob, media_path: str,
                                    generated_image_id: str, generation_recipe_id: str) -> tuple[GeneratedImageRecord, bool]:
        """Copy one reviewed regeneration output into the normal Generation Library."""
        try:
            existing = self.get(generated_image_id)
        except KeyError:
            existing = None
        if existing:
            if str(existing.generation_recipe_id or "") != str(generation_recipe_id):
                raise ValueError("Existing Generation Library record has conflicting recipe lineage.")
            return existing, False
        source = Path(media_path).expanduser()
        if not source.is_file():
            raise ValueError("Regenerated media is unavailable.")
        if job.result is None:
            raise ValueError("Regenerated Generation Engine result is unavailable.")
        request_metadata = {
            **dict(job.request.metadata or {}),
            "source": "REGENERATION_STUDIO",
            "workflow_type": "REGENERATION_STUDIO",
            "workflow_origin": "regeneration",
        }
        promoted_job = replace(
            job,
            request=replace(job.request, metadata=request_metadata),
            result=replace(job.result, output_references=(str(source),), generation_metadata={
                **dict(job.result.generation_metadata or {}),
                "generation_recipe_ids": (str(generation_recipe_id),),
                "output_generation_recipe_ids": (str(generation_recipe_id),),
            }),
        )
        record = replace(
            self._record_from_job(promoted_job, str(source)),
            image_id=str(generated_image_id),
            generation_recipe_id=str(generation_recipe_id),
        )
        record = self.archive_service.copy_generation(record)
        record = replace(record, generation_metadata={
            **dict(record.generation_metadata or {}),
            "regeneration_disposition": "PROMOTED",
        })
        self._append_records((record,))
        return record, True

    def browse(
        self,
        filters: GenerationLibraryFilter | None = None,
    ) -> GenerationLibraryResult:
        filters = filters or GenerationLibraryFilter()
        search = str(filters.search or "").strip().lower()
        records = []
        for record in self.list_records():
            target_status = filters.status if filters.status is not None else "active"
            if target_status == "active":
                record = self._active_record_with_valid_file(record)
                if record is None:
                    continue
            if filters.creator_profile_id is not None and record.creator_profile_id != int(filters.creator_profile_id):
                continue
            if filters.provider_id and record.provider_id != filters.provider_id:
                continue
            if target_status and record.status != target_status:
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
        staged = sorted(
            (record for record in records if record.is_staged),
            key=lambda record: (record.staged_at or "", record.image_id),
            reverse=True,
        )
        records = staged + [record for record in records if not record.is_staged]
        return GenerationLibraryResult(records=tuple(records), filters=filters, total=len(records))

    def set_posting_stage(self, image_id: str, *, staged: bool) -> GeneratedImageRecord:
        """Idempotently update lightweight posting-stage metadata."""
        record = self.get(str(image_id))
        if record.status != "active":
            raise ValueError("Only active Generation Library images can be staged for posting.")
        if record.is_staged == bool(staged):
            return record
        updated = replace(
            record,
            is_staged=bool(staged),
            staged_at=utc_now() if staged else None,
            updated_at=utc_now(),
        )
        self._upsert_records((updated,))
        return updated

    def resolve_publishable_image_reference(self, image_id: str) -> str | None:
        """Return a currently publishable image reference for an active library item."""
        try:
            record = self.get(image_id)
        except KeyError:
            return None
        active_record = self._active_record_with_valid_file(record)
        if active_record is None:
            return None
        return active_record.output_reference

    def select(self, image_ids: Iterable[str], *, selected: bool = True) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        changed = []
        for image_id in ids:
            try: record = self.get(image_id)
            except KeyError: continue
            changed.append(replace(record, selected=selected, updated_at=utc_now()))
        self._upsert_records(changed)
        return GenerationLibraryActionResult(True, "Selection updated.", ids)

    def mark_registered(self, image_id: str, asset_id: int) -> GeneratedImageRecord:
        """Keep generated history intact while linking its canonical Asset."""
        record = self.get(str(image_id))
        updated = replace(
            record,
            imported_asset_id=int(asset_id),
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "asset_registration_phase": 1,
                "registered_asset_id": int(asset_id),
            },
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        return updated

    def mark_business_registered(self, image_id: str, asset_id: int) -> GeneratedImageRecord:
        """Persist successful promotion and remove the item from staged views."""
        record = self.get(str(image_id))
        updated = replace(
            record,
            status="business_asset_registered",
            review_state="business_asset_registered",
            selected=False,
            imported_asset_id=int(asset_id),
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "asset_registration_phase": 4,
                "registered_asset_id": int(asset_id),
                "business_asset_analysis_status": "PENDING",
            },
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        return updated

    def move_to_asset_library(self, image_id: str) -> tuple[GeneratedImageRecord, bool]:
        """Stage an existing generation without creating a canonical Asset."""
        record = self.get(str(image_id))
        if is_protected_generation_metadata(record.generation_metadata):
            raise ValueError("Protected Reference assets cannot be moved to Asset Library.")
        if record.imported_asset_id is not None:
            asset = self.assets.get_by_id(int(record.imported_asset_id))
            if asset is not None and is_protected_reference_asset(asset):
                raise ValueError("Protected Reference assets cannot be moved to Asset Library.")
        if record.status == "staged_asset_library":
            return record, True
        if record.status != "active":
            raise ValueError("Generated image is not available to move to Asset Library.")
        staged_at = utc_now()
        updated = replace(
            record,
            status="staged_asset_library",
            review_state="staged_asset_library",
            selected=False,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "asset_library_item_kind": "staged_generation",
                "asset_library_staged_at": staged_at,
            },
            updated_at=staged_at,
        )
        self._replace_record(updated)
        self._learn_positive(updated, "generation_library_retained", "generation_library")
        return updated, False

    def stage_photoshoot_image_in_asset_library(self, image_id: str) -> tuple[GeneratedImageRecord, bool]:
        """Create an Asset Library projection for existing canonical Photoshoot media."""
        record = self.get(str(image_id))
        metadata = dict(record.generation_metadata or {})
        if record.status == "staged_asset_library" and metadata.get("curated_from_photoshoot"):
            return record, True
        if record.status not in {"photoshoot_session", "photoshoot_completed", "staged_asset_library"}:
            raise ValueError("Photoshoot image is not available for Asset Library curation.")
        staged_at = utc_now()
        updated = replace(
            record, status="staged_asset_library", review_state="staged_asset_library", selected=False,
            generation_metadata={
                **metadata, "asset_library_item_kind": "staged_generation",
                "asset_library_staged_at": metadata.get("asset_library_staged_at") or staged_at,
                "curated_from_photoshoot": True,
                "canonical_asset_id": record.imported_asset_id,
            }, updated_at=staged_at,
        )
        self._replace_record(updated)
        return updated, False

    def move_back_to_generation_library(
        self, image_id: str, *, registration_reversed: bool = False,
    ) -> tuple[GeneratedImageRecord, bool]:
        """Return a staged generation to the active library without duplicating it."""
        record = self.get(str(image_id))
        if is_protected_generation_metadata(record.generation_metadata):
            raise ValueError("Protected Reference assets cannot be moved back.")
        if record.imported_asset_id is not None:
            asset = self.assets.get_by_id(int(record.imported_asset_id))
            if asset is not None and is_protected_reference_asset(asset):
                raise ValueError("Protected Reference assets cannot be moved back.")
        if record.status == "active":
            return record, True
        if record.status == "business_asset_registered" and not registration_reversed:
            raise ValueError("Registered Assets must be reversed through the Asset Library return workflow.")
        if record.status not in {"staged_asset_library", "business_asset_registered"}:
            raise ValueError("Only staged Asset Library items can move back to Generation Library.")
        metadata = {
            key: value for key, value in dict(record.generation_metadata or {}).items()
            if key not in {
                "asset_library_item_kind", "asset_library_staged_at",
                "asset_registration_phase", "registered_asset_id",
                "business_asset_analysis_status",
            }
        }
        updated = replace(
            record,
            status="active",
            review_state="unreviewed",
            imported_asset_id=None if registration_reversed else record.imported_asset_id,
            generation_metadata=metadata,
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        return updated, False

    def bulk_select(self, filters: GenerationLibraryFilter) -> GenerationLibraryActionResult:
        result = self.browse(filters)
        return self.select(tuple(record.image_id for record in result.records), selected=True)

    def move_to_junk(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        return self.delete(image_ids)

    def archive(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        records_by_id = {record.image_id: record for record in self.list_records()}
        already_completed = [records_by_id[image_id] for image_id in ids
                             if image_id in records_by_id and records_by_id[image_id].status == "photoshoot_completed"]
        if len(already_completed) == len(ids):
            gallery_dir = Path(already_completed[0].output_reference).parent
            self._write_photoshoot_session_manifest(
                gallery_dir, session_id=session_id, records=self.list_records()
            )
            return GenerationLibraryActionResult(
                success=True,
                message="Photoshoot Gallery was already finalized and has been reconciled.",
                image_ids=ids,
            )
        archived = []
        errors = []
        for image_id in ids:
            record = records_by_id.get(image_id)
            if not record:
                errors.append(f"Generated image not found: {image_id}")
                continue
            try:
                self.archive_service.archive_record(
                    record,
                    archive_type="archived",
                    destination=self.archive_service.content_paths()["archive_junk"],
                    metadata={"archive_reason": "manual_archive"},
                )
                archived.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        if archived:
            self._remove_records(archived)
            for image_id in archived:
                self._learn_negative(records_by_id[image_id], "archived", "generation_library")
        return GenerationLibraryActionResult(
            success=not errors,
            message="Generated image(s) archived." if not errors else "Some generated images could not be archived.",
            image_ids=tuple(archived),
            errors=tuple(errors),
        )

    def restore(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        restored = []
        errors = []
        records = list(self.list_records())
        existing_by_id = {record.image_id: record for record in records}
        changed = []
        for image_id in ids:
            if image_id in existing_by_id:
                changed.append(replace(existing_by_id[image_id], status="active", review_state="restored", selected=False, updated_at=utc_now()))
                restored.append(image_id)
                continue
            try:
                changed.append(self.archive_service.restore_junk(image_id))
                restored.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        if restored:
            self._upsert_records(changed)
        return GenerationLibraryActionResult(
            success=not errors,
            message="Generated image(s) restored.",
            image_ids=tuple(restored),
            errors=tuple(errors),
        )

    def delete(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        records_by_id = {record.image_id: record for record in self.list_records()}
        junked = []
        errors = []
        for image_id in ids:
            record = records_by_id.get(image_id)
            if not record:
                errors.append(f"Generated image not found: {image_id}")
                continue
            try:
                self.archive_service.archive_junk(record, metadata={"archive_reason": "removed"})
                junked.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        if junked:
            self._remove_records(junked)
            for image_id in junked:
                record = records_by_id[image_id]
                source = str(
                    dict(record.generation_metadata or {}).get("source")
                    or dict(record.generation_metadata or {}).get("workflow_type")
                    or "generation_library"
                )
                event_type = "inspire_discarded" if "inspir" in source else "deleted"
                self._learn_negative(record, event_type, source)
        return GenerationLibraryActionResult(
            success=not errors,
            message="Content moved to Archive / Removed Content.",
            image_ids=tuple(junked),
            errors=tuple(errors),
        )

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
                approval = self._approve_record_as_creator_asset(
                    record,
                    source_workflow="generation_library",
                    generation_engine=generation_engine,
                    ingestion_service=ingestion_service,
                    source_metadata={"approval_entrypoint": "generation_library_add_to_creator_os"},
                )
                if not approval.success or approval.asset_id is None:
                    raise RuntimeError("; ".join(approval.errors) or "Generated image was not approved into Creator OS.")
                asset_id = int(approval.asset_id)
                imported_asset_ids.append(asset_id)
                archived_record = replace(
                    record,
                    status="added_to_creator_os",
                    review_state="added_to_creator_os",
                    imported_asset_id=asset_id,
                    updated_at=utc_now(),
                )
                self._learn_positive(
                    archived_record,
                    "generation_library_retained",
                    "generation_library",
                )
                self.archive_service.archive_imported(archived_record, imported_asset_id=asset_id)
                self._remove_records((record.image_id,))
            except Exception as exc:
                errors.append(str(exc))
        return GenerationLibraryActionResult(
            success=not errors,
            message="Generated image(s) added to Creator OS." if not errors else "Some generated images could not be added.",
            image_ids=selected_ids,
            imported_asset_ids=tuple(imported_asset_ids),
            errors=tuple(errors),
        )

    def approve_creator_content(
        self,
        image_ids: Iterable[str],
        *,
        source_workflow: str,
        generation_engine: GenerationEngineService,
        ingestion_service: GenerationResultIngestionService,
        source_session_id: str | None = None,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> GenerationLibraryActionResult:
        imported_asset_ids = []
        approved_ids = []
        errors = []
        records_by_id = {record.image_id: record for record in self.list_records()}
        selected_ids = tuple(str(value) for value in image_ids)
        updated_records = []
        for record in self.list_records():
            if record.image_id not in selected_ids:
                continue
            try:
                if record.imported_asset_id is not None:
                    asset_id = int(record.imported_asset_id)
                else:
                    approval = self._approve_record_as_creator_asset(
                        record,
                        source_workflow=source_workflow,
                        generation_engine=generation_engine,
                        ingestion_service=ingestion_service,
                        source_session_id=source_session_id,
                        source_metadata=source_metadata,
                    )
                    if not approval.success or approval.asset_id is None:
                        raise RuntimeError("; ".join(approval.errors) or "Generated image was not approved into Creator OS.")
                    asset_id = int(approval.asset_id)
                imported_asset_ids.append(asset_id)
                approved_ids.append(record.image_id)
                updated_records.append(
                    replace(
                        record,
                        imported_asset_id=asset_id,
                        generation_metadata={
                            **dict(record.generation_metadata or {}),
                            "creator_approval_asset_id": asset_id,
                            "creator_approval_source_workflow": source_workflow,
                            "creator_approved_at": utc_now(),
                        },
                        updated_at=utc_now(),
                    )
                )
            except Exception as exc:
                errors.append(f"{record.image_id}: {exc}")
        missing = tuple(image_id for image_id in selected_ids if image_id not in records_by_id)
        errors.extend(f"Generated image not found: {image_id}" for image_id in missing)
        if approved_ids:
            self._upsert_records(updated_records)
        return GenerationLibraryActionResult(
            success=not errors,
            message="Content approved into Creator OS." if not errors else "Some content could not be approved into Creator OS.",
            image_ids=tuple(approved_ids),
            imported_asset_ids=tuple(imported_asset_ids),
            errors=tuple(errors),
        )

    def _approve_record_as_creator_asset(
        self,
        record: GeneratedImageRecord,
        *,
        source_workflow: str,
        generation_engine: GenerationEngineService,
        ingestion_service: GenerationResultIngestionService,
        source_session_id: str | None = None,
        source_metadata: Mapping[str, Any] | None = None,
    ):
        job = generation_engine.get_job(record.generation_job_id)
        if job.result is None:
            raise RuntimeError("Generation Job has no result.")
        return self.creator_approval.approve_generated_record(
            record,
            generation_job=job,
            ingestion_service=ingestion_service,
            source_workflow=source_workflow,
            source_session_id=source_session_id,
            source_metadata={
                "prompt_plan_id": record.prompt_plan_id,
                "photoshoot_session_id": source_session_id or record.photoshoot_session_id,
                "photoshoot_request_id": record.photoshoot_request_id,
                **dict(source_metadata or {}),
            },
        )

    def mark_published(
        self,
        image_id: str,
        *,
        platform: str,
        caption: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> GenerationLibraryActionResult:
        try:
            record = self.get(image_id)
            posted_record = replace(
                record,
                is_staged=False,
                staged_at=None,
                updated_at=utc_now(),
            )
            self.archive_service.archive_published(
                posted_record,
                platform=platform,
                caption=caption,
                metadata=metadata,
            )
            self._learn_positive(record, "published", "generation_library_publishing")
            self._remove_records((image_id,))
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Generated image could not be archived after publish.",
                image_ids=(str(image_id),),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Published image moved to Archive.",
            image_ids=(str(image_id),),
        )

    def mark_edited(
        self,
        image_ids: Iterable[str],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        records_by_id = {record.image_id: record for record in self.list_records()}
        archived = []
        errors = []
        for image_id in ids:
            record = records_by_id.get(image_id)
            if not record:
                errors.append(f"Generated image not found: {image_id}")
                continue
            try:
                self.archive_service.archive_edited(record, metadata=metadata)
                archived.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        if archived:
            self._remove_records(archived)
        return GenerationLibraryActionResult(
            success=not errors,
            message="Edited original image(s) moved to Archive.",
            image_ids=tuple(archived),
            errors=tuple(errors),
        )

    def send_to_pending_edit(self, image_id: str) -> GeneratedImageRecord:
        record = self.get(image_id)
        if record.status == "pending_edit":
            return record
        pending_path = self.archive_service.move_to_pending_edit(record)
        updated = replace(
            record,
            output_reference=str(pending_path),
            status="pending_edit",
            review_state="pending_edit",
            selected=False,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "pending_edit_started_at": utc_now(),
                "pending_edit_original_output_reference": record.output_reference,
                "output_reference": str(pending_path),
            },
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        return updated

    def send_to_pending_video(self, image_id: str) -> GeneratedImageRecord:
        return self._send_to_pending_creative_workflow(
            image_id,
            workflow="video",
            status="pending_video",
            queue_path=self.video_queue_path,
        )

    def send_to_pending_photoshoot(self, image_id: str) -> GeneratedImageRecord:
        record = self.get(image_id)
        if record.status == "pending_photoshoot":
            return record
        pending_path = self.archive_service.move_to_pending_workflow(record, workflow="photoshoot")
        updated = replace(
            record,
            output_reference=str(pending_path),
            status="pending_photoshoot",
            review_state="pending_photoshoot",
            selected=False,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "pending_photoshoot_started_at": utc_now(),
                "pending_photoshoot_original_output_reference": record.output_reference,
                "output_reference": str(pending_path),
            },
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        return updated

    def mark_photoshoot_session_records(
        self,
        image_ids: Iterable[str],
        *,
        session_id: str,
        session_title: str | None = None,
    ) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No Photoshoot images to isolate.", ())
        now = utc_now()
        updated = []
        marked = []
        errors = []
        session_dir = self._photoshoot_session_dir("active", session_id=session_id, session_title=session_title)
        for record in self.list_records():
            if record.image_id in ids:
                try:
                    candidate_path = self._move_record_file(
                        record,
                        session_dir,
                        f"Candidate_{record.image_id}",
                    )
                    updated.append(
                        replace(
                            record,
                            output_reference=str(candidate_path),
                            status="photoshoot_session",
                            review_state="photoshoot_candidate",
                            selected=False,
                            photoshoot_session_id=record.photoshoot_session_id or str(session_id),
                            generation_metadata={
                                **dict(record.generation_metadata or {}),
                                "photoshoot_session_id": str(session_id),
                                "photoshoot_session_name": session_dir.name,
                                "photoshoot_storage_state": "active_candidate",
                                "photoshoot_session_path": str(session_dir),
                                "photoshoot_session_isolated_at": now,
                                "pre_photoshoot_output_reference": record.output_reference,
                                "output_reference": str(candidate_path),
                            },
                            updated_at=now,
                        )
                    )
                    marked.append(record.image_id)
                except Exception as exc:
                    errors.append(f"{record.image_id}: {exc}")
        if marked:
            self._upsert_records(updated)
        return GenerationLibraryActionResult(
            success=not errors,
            message=(
                "Photoshoot image(s) moved into the active session."
                if not errors
                else "Some Photoshoot images could not be moved into the active session."
            ),
            image_ids=tuple(marked),
            errors=tuple(errors),
        )

    def approve_photoshoot_records(
        self,
        image_ids: Iterable[str],
        *,
        session_id: str,
        session_title: str | None = None,
    ) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No Photoshoot images selected for approval.", ())
        now = utc_now()
        session_dir = self._photoshoot_session_dir("active", session_id=session_id, session_title=session_title)
        records_by_id = {record.image_id: record for record in self.list_records()}
        approved = []
        errors = []
        for image_id in ids:
            record = records_by_id.get(image_id)
            if record is None:
                errors.append(f"Generated image not found: {image_id}")
                continue
            try:
                shot_number = self._next_photoshoot_shot_number(session_id=session_id, excluding_ids=ids)
                shot_path = self._move_record_file(record, session_dir, f"Shot_{shot_number:03d}", replace_existing=False)
                updated_record = replace(
                    record,
                    output_reference=str(shot_path),
                    status="photoshoot_session",
                    review_state="photoshoot_approved",
                    selected=False,
                    photoshoot_session_id=record.photoshoot_session_id or str(session_id),
                    generation_metadata={
                        **dict(record.generation_metadata or {}),
                        "photoshoot_session_id": str(session_id),
                        "photoshoot_session_name": session_dir.name,
                        "photoshoot_storage_state": "active_approved",
                        "photoshoot_session_path": str(session_dir),
                        "photoshoot_shot_number": shot_number,
                        "photoshoot_approved_at": now,
                        "output_reference": str(shot_path),
                    },
                    updated_at=now,
                )
                self._replace_record(updated_record)
                self._write_photoshoot_sidecar(shot_path, updated_record)
                approved.append(image_id)
            except Exception as exc:
                errors.append(f"{image_id}: {exc}")
        return GenerationLibraryActionResult(
            success=not errors,
            message="Photoshoot image(s) approved into the active session." if not errors else "Some Photoshoot images could not be approved.",
            image_ids=tuple(approved),
            errors=tuple(errors),
        )

    def finish_photoshoot_session(
        self,
        *,
        session_id: str,
        approved_image_ids: Iterable[str],
        session_title: str | None = None,
    ) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in approved_image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No approved Photoshoot images to complete.", ())
        records_by_id = {record.image_id: record for record in self.list_records()}
        updated_records = []
        completed = []
        errors = []
        now = utc_now()
        active_dir = self._photoshoot_session_dir("active", session_id=session_id, session_title=session_title)
        gallery_dir = self._photoshoot_session_dir("gallery", session_id=session_id, session_title=session_title)
        if active_dir.exists():
            gallery_dir.parent.mkdir(parents=True, exist_ok=True)
            gallery_dir = self._unique_path(gallery_dir) if gallery_dir.exists() else gallery_dir
            shutil.move(str(active_dir), str(gallery_dir))
        else:
            gallery_dir.mkdir(parents=True, exist_ok=True)
        for record in self.list_records():
            if record.image_id not in ids:
                continue
            try:
                output_reference = self._reference_after_session_move(record.output_reference, active_dir, gallery_dir)
                updated_records.append(
                    replace(
                        record,
                        output_reference=output_reference,
                        status="photoshoot_completed",
                        review_state="photoshoot_completed",
                        selected=False,
                        photoshoot_session_id=record.photoshoot_session_id or str(session_id),
                        generation_metadata={
                            **dict(record.generation_metadata or {}),
                            "photoshoot_session_id": str(session_id),
                            "photoshoot_session_name": gallery_dir.name,
                            "photoshoot_storage_state": "gallery",
                            "photoshoot_gallery_path": str(gallery_dir),
                            "photoshoot_finished_at": now,
                            "output_reference": output_reference,
                        },
                        updated_at=now,
                    )
                )
                completed.append(record.image_id)
            except Exception as exc:
                errors.append(f"{record.image_id}: {exc}")
        missing = tuple(image_id for image_id in ids if image_id not in records_by_id)
        errors.extend(f"Generated image not found: {image_id}" for image_id in missing)
        if completed:
            self._upsert_records(updated_records)
            self._write_photoshoot_session_manifest(gallery_dir, session_id=session_id, records=self.list_records())
        return GenerationLibraryActionResult(
            success=not errors,
            message=(
                "Photoshoot approved image(s) moved into Photoshoot Gallery."
                if not errors
                else "Some Photoshoot images could not be completed."
            ),
            image_ids=tuple(completed),
            errors=tuple(errors),
        )

    def move_completed_photoshoot_session_to_junk(
        self,
        *,
        session_id: str,
        approved_image_ids: Iterable[str],
        session_title: str | None = None,
        reason: str = "completed_session_junk",
    ) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in approved_image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No completed Photoshoot images selected for junk.", ())
        records_by_id = {record.image_id: record for record in self.list_records()}
        updated_records = []
        junked = []
        errors = []
        now = utc_now()
        gallery_dir = self._photoshoot_session_dir("gallery", session_id=session_id, session_title=session_title)
        junk_dir = self._photoshoot_session_dir("junk", session_id=session_id, session_title=session_title)
        if gallery_dir.exists():
            junk_dir.parent.mkdir(parents=True, exist_ok=True)
            if junk_dir.exists():
                for child in gallery_dir.iterdir():
                    target = junk_dir / child.name
                    if target.exists():
                        target = self._unique_path(target)
                    shutil.move(str(child), str(target))
                gallery_dir.rmdir()
            else:
                shutil.move(str(gallery_dir), str(junk_dir))
        else:
            junk_dir.mkdir(parents=True, exist_ok=True)
        for record in self.list_records():
            if record.image_id not in ids:
                continue
            try:
                output_reference = self._reference_after_session_move(record.output_reference, gallery_dir, junk_dir)
                updated_records.append(
                    replace(
                        record,
                        output_reference=output_reference,
                        status="photoshoot_junk",
                        review_state=reason,
                        selected=False,
                        photoshoot_session_id=record.photoshoot_session_id or str(session_id),
                        generation_metadata={
                            **dict(record.generation_metadata or {}),
                            "photoshoot_session_id": str(session_id),
                            "photoshoot_session_name": junk_dir.name,
                            "photoshoot_storage_state": "junk",
                            "photoshoot_junk_path": str(junk_dir),
                            "photoshoot_junked_at": now,
                            "photoshoot_junk_reason": reason,
                            "output_reference": output_reference,
                        },
                        updated_at=now,
                    )
                )
                junked.append(record.image_id)
            except Exception as exc:
                errors.append(f"{record.image_id}: {exc}")
        missing = tuple(image_id for image_id in ids if image_id not in records_by_id)
        errors.extend(f"Generated image not found: {image_id}" for image_id in missing)
        if junked:
            self._upsert_records(updated_records)
            self._write_photoshoot_session_manifest(junk_dir, session_id=session_id, records=self.list_records())
        return GenerationLibraryActionResult(
            success=not errors,
            message=(
                "Completed Photoshoot moved to Photoshoot Junk."
                if not errors
                else "Some completed Photoshoot images could not be moved to Junk."
            ),
            image_ids=tuple(junked),
            errors=tuple(errors),
        )

    def _send_to_pending_creative_workflow(
        self,
        image_id: str,
        *,
        workflow: str,
        status: str,
        queue_path: Path,
    ) -> GeneratedImageRecord:
        record = self.get(image_id)
        if record.status == status:
            return record
        pending_path = self.archive_service.move_to_pending_workflow(record, workflow=workflow)
        now = utc_now()
        queue = list(self._read_json(queue_path, []))
        if not any(str(item.get("image_id")) == record.image_id for item in queue if isinstance(item, Mapping)):
            queue.insert(
                0,
                {
                    "queue_id": f"{workflow}_queue_{hashlib.sha256((record.image_id + now).encode('utf-8')).hexdigest()[:16]}",
                    "workflow": workflow,
                    "image_id": record.image_id,
                    "creator_profile_id": record.creator_profile_id,
                    "source_output_reference": record.output_reference,
                    "pending_output_reference": str(pending_path),
                    "provider_id": record.provider_id,
                    "prompt_plan_id": record.prompt_plan_id,
                    "prompt_text": record.prompt_text,
                    "status": status,
                    "created_at": now,
                },
            )
            self._write_json(queue_path, queue)
        updated = replace(
            record,
            output_reference=str(pending_path),
            status=status,
            review_state=status,
            selected=False,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                f"{status}_started_at": now,
                f"{status}_original_output_reference": record.output_reference,
                "pending_workflow": workflow,
                "output_reference": str(pending_path),
            },
            updated_at=now,
        )
        self._replace_record(updated)
        return updated

    def return_pending_edit_to_library(self, image_id: str) -> GenerationLibraryActionResult:
        try:
            record = self.get(image_id)
            if record.status != "pending_edit":
                raise ValueError("Generated image is not pending edit.")
            active_path = self.archive_service.move_to_generation_active(record)
            updated = replace(
                record,
                output_reference=str(active_path),
                status="active",
                review_state="returned_from_edit",
                selected=False,
                generation_metadata={
                    **{
                        key: value
                        for key, value in dict(record.generation_metadata or {}).items()
                        if key not in {"latest_edit_candidate_id"}
                    },
                    "pending_edit_returned_at": utc_now(),
                    "output_reference": str(active_path),
                },
                updated_at=utc_now(),
            )
            self._replace_record(updated)
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Pending edit could not be returned to Generation Library.",
                image_ids=(str(image_id),),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Pending edit returned to Generation Library.",
            image_ids=(str(image_id),),
        )

    def return_photoshoot_seed_to_library(self, image_id: str) -> GenerationLibraryActionResult:
        try:
            record = self.get(image_id)
            if record.status == "active":
                return GenerationLibraryActionResult(
                    success=True,
                    message="Photoshoot seed is already active in Generation Library.",
                    image_ids=(record.image_id,),
                )
            active_path = self.archive_service.move_to_generation_active(record)
            updated = replace(
                record,
                output_reference=str(active_path),
                status="active",
                review_state="returned_from_photoshoot",
                selected=False,
                generation_metadata={
                    **dict(record.generation_metadata or {}),
                    "photoshoot_returned_at": utc_now(),
                    "output_reference": str(active_path),
                },
                updated_at=utc_now(),
            )
            self._replace_record(updated)
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Photoshoot seed could not be returned to Generation Library.",
                image_ids=(str(image_id),),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Photoshoot seed returned to Generation Library.",
            image_ids=(str(image_id),),
        )

    def save_rejected_photoshoot_candidate_to_library(self, image_id: str) -> GenerationLibraryActionResult:
        """Detach a rejected candidate from Photoshoot and retain it as a standalone generation."""
        try:
            record = self.get(image_id)
            active_path = self.archive_service.move_to_generation_active(record)
            standalone_metadata = {
                key: value
                for key, value in dict(record.generation_metadata or {}).items()
                if not str(key).startswith("photoshoot_")
            }
            updated = replace(
                record,
                output_reference=str(active_path),
                status="active",
                review_state="unreviewed",
                selected=False,
                photoshoot_session_id=None,
                photoshoot_request_id=None,
                generation_metadata={
                    **standalone_metadata,
                    "saved_to_generation_library_at": utc_now(),
                    "output_reference": str(active_path),
                },
                updated_at=utc_now(),
            )
            self._replace_record(updated)
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Rejected candidate could not be saved to Generation Library.",
                image_ids=(str(image_id),),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Rejected candidate saved to Generation Library as a standalone generation.",
            image_ids=(str(image_id),),
        )

    def discard_temporary_records(self, image_ids: Iterable[str]) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No temporary generated images to remove.", ())
        records_by_id = {record.image_id: record for record in self.list_records()}
        removed = []
        errors = []
        for image_id in ids:
            record = records_by_id.get(image_id)
            if record is None:
                continue
            try:
                self._delete_local_file(record.output_reference)
                removed.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        if removed:
            self._remove_records(removed)
        return GenerationLibraryActionResult(
            success=not errors,
            message="Temporary generated image(s) removed.",
            image_ids=tuple(removed),
            errors=tuple(errors),
        )

    def move_photoshoot_records_to_junk(
        self,
        image_ids: Iterable[str],
        *,
        session_id: str,
        session_title: str | None = None,
        reason: str = "photoshoot_junk",
    ) -> GenerationLibraryActionResult:
        ids = tuple(dict.fromkeys(str(image_id) for image_id in image_ids if str(image_id)))
        if not ids:
            return GenerationLibraryActionResult(True, "No Photoshoot images selected for junk.", ())
        records_by_id = {record.image_id: record for record in self.list_records()}
        junked = []
        errors = []
        junk_dir = self._photoshoot_session_dir("junk", session_id=session_id, session_title=session_title)
        now = utc_now()
        for image_id in ids:
            record = records_by_id.get(image_id)
            if not record:
                errors.append(f"Generated image not found: {image_id}")
                continue
            try:
                junk_path = self._move_record_file(
                    record,
                    junk_dir,
                    self._photoshoot_junk_file_stem(record),
                    replace_existing=False,
                )
                self._replace_record(
                    replace(
                        record,
                        output_reference=str(junk_path),
                        status="photoshoot_junk",
                        review_state=reason,
                        selected=False,
                        photoshoot_session_id=record.photoshoot_session_id or str(session_id),
                        generation_metadata={
                            **dict(record.generation_metadata or {}),
                            "photoshoot_session_id": str(session_id),
                            "photoshoot_session_name": junk_dir.name,
                            "photoshoot_storage_state": "junk",
                            "photoshoot_junk_path": str(junk_dir),
                            "photoshoot_junked_at": now,
                            "photoshoot_junk_reason": reason,
                            "output_reference": str(junk_path),
                        },
                        updated_at=now,
                    )
                )
                self._write_photoshoot_sidecar(junk_path, record, metadata={"archive_reason": reason})
                junked.append(image_id)
            except Exception as exc:
                errors.append(str(exc))
        return GenerationLibraryActionResult(
            success=not errors,
            message="Photoshoot image(s) moved to Photoshoot Junk.",
            image_ids=tuple(junked),
            errors=tuple(errors),
        )

    def pending_edit_record(self, *, creator_profile_id: int | None = None) -> GeneratedImageRecord | None:
        records = [
            record
            for record in self.list_records()
            if record.status == "pending_edit"
            and (creator_profile_id is None or record.creator_profile_id == int(creator_profile_id))
            and Path(record.output_reference).expanduser().exists()
        ]
        if not records:
            return None
        ordered = sorted(
            records,
            key=lambda record: (record.updated_at or record.created_at or "", record.image_id),
            reverse=True,
        )
        if len(ordered) > 1:
            ids = tuple(record.image_id for record in ordered)
            logging.getLogger(__name__).error(
                "Multiple pending Edit Studio records found for creator_profile_id=%s: %s",
                creator_profile_id,
                ids,
            )
            raise RuntimeError(
                "Multiple pending Edit Studio records require repair: " + ", ".join(ids)
            )
        return ordered[0]

    def create_asset_edit_workspace_source(self, *, creator_profile_id: int, asset_id: int,
                                           source_path: str, metadata: Mapping[str, Any]) -> GeneratedImageRecord:
        """Create a durable Edit Studio workspace reference without moving/copying its Asset."""
        image_id = f"edit-workspace-{uuid4().hex}"
        now = utc_now()
        record = GeneratedImageRecord(
            image_id=image_id, generation_job_id=image_id, generation_request_id=image_id,
            generation_result_id=image_id, output_reference=str(source_path),
            creator_profile_id=int(creator_profile_id), provider_id="asset_library",
            prompt_plan_id=image_id, prompt_text="", creative_mode="single_image",
            reference_asset_id=None, imported_asset_id=int(asset_id), status="pending_edit",
            review_state="pending_edit", generation_metadata={
                **dict(metadata), "workspace_source_only": True,
                "pending_edit_started_at": now, "output_reference": str(source_path),
            }, created_at=now, updated_at=now,
        )
        self._upsert_records((record,))
        return record

    def remove_asset_edit_workspace_source(self, image_id: str) -> None:
        record = self.get(image_id)
        if not bool(dict(record.generation_metadata or {}).get("workspace_source_only")):
            raise ValueError("Only an Edit Studio workspace reference can be removed this way.")
        self._remove_records((image_id,))

    def _photoshoot_session_dir(
        self,
        bucket: str,
        *,
        session_id: str,
        session_title: str | None = None,
    ) -> Path:
        bucket_name = {
            "active": "Active",
            "gallery": "Gallery",
            "junk": "Junk",
        }.get(str(bucket or "").strip().lower())
        if not bucket_name:
            raise ValueError(f"Unsupported Photoshoot storage bucket: {bucket}")
        return self.photoshoot_root / bucket_name / self._photoshoot_session_folder_name(
            session_id=session_id,
            session_title=session_title,
        )

    def _photoshoot_session_folder_name(self, *, session_id: str, session_title: str | None = None) -> str:
        title = str(session_title or "").strip()
        generic_titles = {"", "photoshoot studio", "photoshoot session", "generation library photoshoot"}
        if title.lower() not in generic_titles:
            return self._safe_storage_name(title)
        for record in self.list_records():
            if record.photoshoot_session_id != str(session_id):
                continue
            name = str(dict(record.generation_metadata or {}).get("photoshoot_session_name") or "").strip()
            if name:
                return self._safe_storage_name(name)
        digest = hashlib.sha256(str(session_id).encode("utf-8")).hexdigest()[:3]
        return f"Photoshoot_{utc_now()[:10]}_{digest}"

    @staticmethod
    def _safe_storage_name(value: str) -> str:
        cleaned = re.sub(r"[<>:\"/\\|?*\x00-\x1f]+", " ", str(value or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:120].strip(" .") or "Photoshoot Session"

    def _move_record_file(
        self,
        record: GeneratedImageRecord,
        destination: Path,
        stem: str,
        *,
        replace_existing: bool = False,
    ) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        source = str(record.output_reference or "").strip()
        suffix = Path(source).suffix or ".jpg"
        target = destination / f"{self._safe_storage_name(stem)}{suffix}"
        source_path = Path(source).expanduser()
        if not source_path.is_file() and target.is_file():
            return target
        if not source_path.is_file():
            matches = sorted(destination.glob(f"{self._safe_storage_name(stem)}.*"))
            if len(matches) == 1 and matches[0].is_file():
                return matches[0]
        if source_path.exists() and source_path.is_file():
            if source_path.resolve() == target.resolve():
                return target
            if not replace_existing and target.exists():
                target = self._unique_path(target)
            shutil.move(str(source_path), str(target))
            return target
        return Path(source or target)

    def _next_photoshoot_shot_number(self, *, session_id: str, excluding_ids: Iterable[str] = ()) -> int:
        excluded = {str(image_id) for image_id in excluding_ids}
        numbers = []
        for record in self.list_records():
            if record.image_id in excluded:
                continue
            if record.photoshoot_session_id != str(session_id):
                continue
            metadata = dict(record.generation_metadata or {})
            if record.status != "photoshoot_session":
                continue
            try:
                numbers.append(int(metadata.get("photoshoot_shot_number") or 0))
            except (TypeError, ValueError):
                pass
        return max(numbers or [0]) + 1

    @staticmethod
    def _photoshoot_junk_file_stem(record: GeneratedImageRecord) -> str:
        metadata = dict(record.generation_metadata or {})
        shot_number = metadata.get("photoshoot_shot_number")
        if shot_number:
            try:
                return f"Shot_{int(shot_number):03d}"
            except (TypeError, ValueError):
                pass
        return f"Rejected_{record.image_id}"

    @staticmethod
    def _reference_after_session_move(reference: str, source_dir: Path, destination_dir: Path) -> str:
        value = str(reference or "")
        try:
            source_path = Path(value).expanduser()
            relative = source_path.relative_to(source_dir)
            return str(destination_dir / relative)
        except (ValueError, OSError):
            return value

    def _write_photoshoot_sidecar(
        self,
        image_path: Path,
        record: GeneratedImageRecord,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        if not image_path:
            return
        sidecar = Path(image_path).with_suffix(".json")
        self._write_json(
            sidecar,
            {
                "image_id": record.image_id,
                "photoshoot_session_id": record.photoshoot_session_id,
                "photoshoot_request_id": record.photoshoot_request_id,
                "prompt_text": record.prompt_text,
                "provider_id": record.provider_id,
                "creative_mode": record.creative_mode,
                "provider_metadata": dict(record.provider_metadata or {}),
                "prompt_metadata": dict(record.prompt_metadata or {}),
                "generation_metadata": dict(record.generation_metadata or {}),
                "metadata": dict(metadata or {}),
                "updated_at": utc_now(),
            },
        )

    def _write_photoshoot_session_manifest(
        self,
        session_dir: Path,
        *,
        session_id: str,
        records: Iterable[GeneratedImageRecord],
    ) -> None:
        session_records = [
            asdict(record)
            for record in records
            if record.photoshoot_session_id == str(session_id)
        ]
        self._write_json(
            session_dir / "session.json",
            {
                "session_id": str(session_id),
                "records": session_records,
                "updated_at": utc_now(),
            },
        )

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        suffix = path.suffix
        digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:8]
        for index in range(1, 1000):
            candidate = path.with_name(f"{stem}_{digest}_{index}{suffix}")
            if not candidate.exists():
                return candidate
        return path.with_name(f"{stem}_{digest}{suffix}")

    def latest_edit_candidate_for_source(self, source_image_id: str) -> GeneratedImageRecord | None:
        try:
            source = self.get(source_image_id)
        except KeyError:
            source = None
        latest_id = dict((source.generation_metadata if source else {}) or {}).get("latest_edit_candidate_id")
        if latest_id:
            try:
                candidate = self.get(str(latest_id))
                if candidate.status == "edit_candidate":
                    return candidate
            except KeyError:
                pass
        candidates = [
            record
            for record in self.list_records()
            if record.status == "edit_candidate"
            and dict(record.generation_metadata or {}).get("edit_pending_source_image_id") == source_image_id
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda record: record.updated_at or record.created_at or "", reverse=True)[0]

    def mark_edit_candidate(
        self,
        image_id: str,
        *,
        pending_source_image_id: str | None = None,
    ) -> GeneratedImageRecord:
        record = self.get(image_id)
        source_id = str(pending_source_image_id or "").strip() or None
        updated = replace(
            record,
            status="edit_candidate",
            review_state="pending_edit_approval",
            selected=False,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "edit_pending_source_image_id": source_id,
                "output_reference": record.output_reference,
            },
            updated_at=utc_now(),
        )
        self._replace_record(updated)
        if source_id:
            try:
                source = self.get(source_id)
                self._replace_record(
                    replace(
                        source,
                        generation_metadata={
                            **dict(source.generation_metadata or {}),
                            "latest_edit_candidate_id": updated.image_id,
                        },
                        updated_at=utc_now(),
                    )
                )
            except KeyError:
                pass
        return updated

    def approve_edit_candidate(
        self,
        *,
        source_image_id: str,
        edited_image_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> GenerationLibraryActionResult:
        try:
            source_record = self.get(source_image_id)
            edited_record = self.get(edited_image_id)
            approval_timestamp = utc_now()
            archived_versions = self.archive_service.list_asset_versions(source_record.image_id)
            latest_archived_version = max(
                (int(item.metadata.get("version_number") or 0) for item in archived_versions),
                default=0,
            )
            source_version = max(
                1,
                int(dict(source_record.generation_metadata or {}).get("asset_version") or 0),
                latest_archived_version + 1,
            )
            version_approval_timestamp = str(
                dict(source_record.generation_metadata or {}).get("edit_approved_at")
                or approval_timestamp
            )
            archived_version = self.archive_service.archive_asset_version(
                source_record,
                version_number=source_version,
                approval_timestamp=version_approval_timestamp,
                edit_source=str(dict(metadata or {}).get("approved_from") or "edit_studio"),
            )
            active_approved_path = self.archive_service.move_to_generation_active(edited_record)
            merged_generation_metadata = {
                **dict(source_record.generation_metadata or {}),
                **dict(edited_record.generation_metadata or {}),
                "workflow_type": "edit",
                "edit_approved_at": approval_timestamp,
                "asset_version": source_version + 1,
                "asset_version_archive_id": archived_version.archive_id,
                "previous_version_archived_path": archived_version.current_file_path,
                "edit_original_output_reference": source_record.output_reference,
                "original_output_reference": (
                    dict(edited_record.generation_metadata or {}).get("original_output_reference")
                    or edited_record.output_reference
                ),
                "output_reference": str(active_approved_path),
                "edit_original_history_path": archived_version.current_file_path,
                "edit_approved_history_path": str(active_approved_path),
                "edit_candidate_image_id": edited_record.image_id,
                "edit_candidate_generation_job_id": edited_record.generation_job_id,
                "previous_generation_metadata": dict(source_record.generation_metadata or {}),
                "approved_edit_generation_metadata": dict(edited_record.generation_metadata or {}),
                **dict(metadata or {}),
            }
            updated_source = replace(
                source_record,
                generation_job_id=edited_record.generation_job_id,
                generation_request_id=edited_record.generation_request_id,
                generation_result_id=edited_record.generation_result_id,
                output_reference=str(active_approved_path),
                provider_id=edited_record.provider_id,
                prompt_plan_id=edited_record.prompt_plan_id,
                prompt_text=edited_record.prompt_text,
                creative_mode=edited_record.creative_mode,
                reference_asset_id=edited_record.reference_asset_id,
                generation_date=edited_record.generation_date,
                status="active",
                review_state="approved_edit",
                provider_metadata=dict(edited_record.provider_metadata or {}),
                prompt_metadata={
                    **dict(edited_record.prompt_metadata or {}),
                    "previous_prompt_metadata": dict(source_record.prompt_metadata or {}),
                    "approved_edit_prompt_metadata": dict(edited_record.prompt_metadata or {}),
                },
                generation_metadata=merged_generation_metadata,
                updated_at=utc_now(),
            )
            self._upsert_records((updated_source,))
            self._remove_records((edited_record.image_id,))
            self._record_reviewed_edit_output(edited_record, action="approved")
            self.creative_intelligence.record_positive_safely(
                creator_profile_id=updated_source.creator_profile_id,
                image_reference=updated_source.output_reference,
                event_type="edit_saved",
                source_workflow="edit_studio",
                source_image_id=updated_source.image_id,
                source_asset_id=updated_source.imported_asset_id,
                event_key=(
                    f"creative-intelligence:{updated_source.creator_profile_id}:"
                    f"edit_saved:{edited_record.image_id}"
                ),
                operational_metadata={"version": source_version + 1},
            )
            self._delete_local_file(source_record.output_reference)
            self._delete_local_file(edited_record.output_reference)
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Edited image could not be approved.",
                image_ids=(str(source_image_id), str(edited_image_id)),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Edited image approved.",
            image_ids=(str(source_image_id),),
        )

    def restore_asset_version(
        self,
        *,
        image_id: str,
        version_number: int,
    ) -> GeneratedImageRecord:
        """Promote an immutable archived snapshot as a new current version."""
        with self._version_restore_lock:
            current = self.get(image_id)
            if current.status != "active":
                raise ValueError("Only an active Generation Library record can be restored.")
            archived_versions = self.archive_service.list_asset_versions(current.image_id)
            latest_archived = max(
                (int(item.metadata.get("version_number") or 0) for item in archived_versions),
                default=0,
            )
            current_version = max(
                1,
                int(dict(current.generation_metadata or {}).get("asset_version") or 0),
                latest_archived + 1,
            )
            requested_version = int(version_number)
            if requested_version == current_version:
                raise ValueError("The current asset version cannot be restored.")
            selected = next((
                item for item in archived_versions
                if int(item.metadata.get("version_number") or 0) == requested_version
            ), None)
            if selected is None:
                raise KeyError(f"Archived asset version not found: {requested_version}")
            if not Path(selected.current_file_path).expanduser().is_file():
                raise FileNotFoundError("The selected archived version media is unavailable.")

            restore_timestamp = utc_now()
            archive_ids_before = {item.archive_id for item in archived_versions}
            current_archive = self.archive_service.archive_asset_version(
                current,
                version_number=current_version,
                approval_timestamp=str(
                    dict(current.generation_metadata or {}).get("edit_approved_at")
                    or restore_timestamp
                ),
                edit_source=str(
                    dict(current.generation_metadata or {}).get("approved_from")
                    or "version_restore"
                ),
            )
            staged_path: Path | None = None
            try:
                staged_path = self.archive_service.copy_asset_version_to_generation_active(selected)
                snapshot = dict(selected.generation_record or {})
                selected_metadata = dict(selected.metadata or {})
                restored_generation_metadata = {
                    **dict(snapshot.get("generation_metadata") or {}),
                    **dict(selected_metadata.get("generation_metadata") or {}),
                    "asset_version": current_version + 1,
                    "restored_from_version": requested_version,
                    "restore_timestamp": restore_timestamp,
                    "previous_current_version": current_version,
                    "restore_archive_record_id": selected.archive_id,
                    "asset_version_archive_id": current_archive.archive_id,
                    "previous_version_archived_path": current_archive.current_file_path,
                    "output_reference": str(staged_path),
                    "edit_approved_at": restore_timestamp,
                    "approved_from": "version_restore",
                }
                restored = replace(
                    current,
                    generation_job_id=str(snapshot.get("generation_job_id") or current.generation_job_id),
                    generation_request_id=str(snapshot.get("generation_request_id") or current.generation_request_id),
                    generation_result_id=str(snapshot.get("generation_result_id") or current.generation_result_id),
                    output_reference=str(staged_path),
                    provider_id=str(selected_metadata.get("provider") or selected.provider_id),
                    prompt_plan_id=str(selected_metadata.get("prompt_plan_id") or snapshot.get("prompt_plan_id") or ""),
                    prompt_text=str(selected_metadata.get("prompt") or selected.prompt_text or ""),
                    creative_mode=snapshot.get("creative_mode"),
                    reference_asset_id=snapshot.get("reference_asset_id"),
                    generation_date=str(snapshot.get("generation_date") or current.generation_date),
                    status="active",
                    review_state="restored_version",
                    selected=False,
                    imported_asset_id=snapshot.get("imported_asset_id"),
                    provider_metadata=dict(selected_metadata.get("provider_metadata") or snapshot.get("provider_metadata") or {}),
                    prompt_metadata=dict(selected_metadata.get("prompt_metadata") or snapshot.get("prompt_metadata") or {}),
                    generation_metadata=restored_generation_metadata,
                    updated_at=restore_timestamp,
                )
                self._upsert_records((restored,))
                old_active = Path(current.output_reference).expanduser()
                if old_active.resolve() != staged_path.resolve() and old_active.is_file():
                    old_active.unlink()
                return restored
            except Exception:
                self._upsert_records((current,))
                if staged_path is not None and staged_path.is_file():
                    staged_path.unlink()
                if current_archive.archive_id not in archive_ids_before:
                    self.archive_service.rollback_asset_version_archive(current_archive.archive_id)
                raise

    def discard_edit_candidate(self, edited_image_id: str) -> GenerationLibraryActionResult:
        try:
            edited_record = self.get(edited_image_id)
            self._remove_records((edited_record.image_id,))
            self._record_reviewed_edit_output(edited_record, action="discarded")
            self._delete_local_file(edited_record.output_reference)
        except Exception as exc:
            return GenerationLibraryActionResult(
                success=False,
                message="Edited image could not be discarded.",
                image_ids=(str(edited_image_id),),
                errors=(str(exc),),
            )
        return GenerationLibraryActionResult(
            success=True,
            message="Edited image discarded.",
            image_ids=(str(edited_image_id),),
        )

    def _learn_positive(
        self, record: GeneratedImageRecord, event_type: str, source_workflow: str
    ) -> None:
        self.creative_intelligence.record_positive_safely(
            creator_profile_id=record.creator_profile_id,
            image_reference=record.output_reference,
            event_type=event_type,
            source_workflow=source_workflow,
            source_image_id=record.image_id,
            source_asset_id=record.imported_asset_id,
        )

    def _learn_negative(
        self, record: GeneratedImageRecord, event_type: str, source_workflow: str
    ) -> None:
        self.creative_intelligence.record_negative_safely(
            creator_profile_id=record.creator_profile_id,
            image_reference=record.output_reference,
            event_type=event_type,
            source_workflow=source_workflow,
            source_image_id=record.image_id,
            source_asset_id=record.imported_asset_id,
        )

    def get(self, image_id: str) -> GeneratedImageRecord:
        canonical = self._canonical()
        if canonical is not None:
            self._ensure_canonical()
            payload = canonical.get_payload(str(image_id))
            if payload is not None:
                return self._record_from_dict(payload)
            raise KeyError(f"Generated image not found: {image_id}")
        for record in self.list_records():
            if record.image_id == image_id:
                return record
        raise KeyError(f"Generated image not found: {image_id}")

    def list_records(self) -> tuple[GeneratedImageRecord, ...]:
        canonical = self._canonical()
        if canonical is not None:
            self._ensure_canonical()
            return tuple(self._record_from_dict(item) for item in canonical.list_payloads())
        return tuple(self._record_from_dict(item) for item in self._read_json(self.records_path, []))

    def _archived_output_references(self) -> set[str]:
        references = self._reviewed_edit_output_references()
        for record in self.archive_service.list_records():
            for value in (record.original_output_reference, record.current_file_path):
                if value:
                    references.add(str(value))
            generation_record = dict(record.generation_record or {})
            for value in (
                generation_record.get("output_reference"),
                dict(generation_record.get("generation_metadata") or {}).get("output_reference"),
                dict(generation_record.get("generation_metadata") or {}).get("original_output_reference"),
            ):
                if value:
                    references.add(str(value))
            archive_metadata = dict(record.metadata or {})
            for value in (
                dict(archive_metadata.get("generation_metadata") or {}).get("output_reference"),
                dict(archive_metadata.get("generation_metadata") or {}).get("original_output_reference"),
            ):
                if value:
                    references.add(str(value))
        return references

    def _archived_image_ids(self) -> set[str]:
        image_ids = set()
        for record in self.archive_service.list_records():
            if record.image_id:
                image_ids.add(str(record.image_id))
            generation_record = dict(record.generation_record or {})
            if generation_record.get("image_id"):
                image_ids.add(str(generation_record.get("image_id")))
        return image_ids

    @staticmethod
    def _record_output_references(record: GeneratedImageRecord) -> set[str]:
        references = {str(record.output_reference)}
        metadata = dict(record.generation_metadata or {})
        request_metadata = dict(metadata.get("request_metadata") or {})
        for value in (
            metadata.get("output_reference"),
            metadata.get("original_output_reference"),
            metadata.get("pending_edit_original_output_reference"),
            metadata.get("pending_photoshoot_original_output_reference"),
            metadata.get("pending_video_original_output_reference"),
            metadata.get("pending_story_original_output_reference"),
            metadata.get("edit_original_output_reference"),
            metadata.get("edit_source_output_reference"),
            metadata.get("edit_reference_output_reference"),
            request_metadata.get("reference_image_url"),
            request_metadata.get("edit_source_output_reference"),
            request_metadata.get("edit_reference_output_reference"),
        ):
            if value:
                references.add(str(value))
        return references

    def _active_record_with_valid_file(self, record: GeneratedImageRecord) -> GeneratedImageRecord | None:
        if record.status != "active":
            return None
        if self._image_reference_available(record.output_reference):
            return record
        replacement = self._valid_active_replacement_reference(record)
        if not replacement:
            return None
        repaired = replace(
            record,
            output_reference=replacement,
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "output_reference": replacement,
                "active_path_repaired_at": utc_now(),
                "stale_output_reference": record.output_reference,
            },
            updated_at=utc_now(),
        )
        self._replace_record(repaired)
        return repaired

    def _valid_active_replacement_reference(self, record: GeneratedImageRecord) -> str | None:
        metadata = dict(record.generation_metadata or {})
        request_metadata = dict(metadata.get("request_metadata") or {})
        candidates = (
            metadata.get("output_reference"),
            request_metadata.get("output_reference"),
            metadata.get("original_output_reference"),
        )
        for candidate in candidates:
            reference = str(candidate or "").strip()
            if reference == str(record.output_reference or "").strip():
                continue
            if reference.startswith(("http://", "https://", "data:")):
                continue
            if not self._image_reference_available(reference):
                continue
            if self._is_archive_or_posted_reference(reference):
                continue
            return reference
        return None

    @staticmethod
    def _image_reference_available(reference: str | None) -> bool:
        source = str(reference or "").strip()
        if not source:
            return False
        if source.startswith(("http://", "https://", "data:")):
            return True
        return Path(source).expanduser().is_file()

    @staticmethod
    def _is_archive_or_posted_reference(reference: str | None) -> bool:
        normalized = str(reference or "").replace("/", "\\").lower()
        return "\\posted\\" in normalized or "\\archive\\" in normalized

    def _reviewed_edit_output_references(self) -> set[str]:
        references = set()
        for item in self._read_json(self.reviewed_edit_outputs_path, []):
            for value in (
                item.get("output_reference"),
                item.get("original_output_reference"),
            ):
                if value:
                    references.add(str(value))
        return references

    def _record_reviewed_edit_output(self, record: GeneratedImageRecord, *, action: str) -> None:
        reviewed = list(self._read_json(self.reviewed_edit_outputs_path, []))
        generation_metadata = dict(record.generation_metadata or {})
        reviewed.insert(
            0,
            {
                "image_id": record.image_id,
                "generation_job_id": record.generation_job_id,
                "action": str(action),
                "output_reference": record.output_reference,
                "original_output_reference": generation_metadata.get("original_output_reference"),
                "reviewed_at": utc_now(),
            },
        )
        self._write_json(self.reviewed_edit_outputs_path, reviewed)

    def _set_status(
        self,
        image_ids: Iterable[str],
        *,
        status: str,
        message: str,
    ) -> GenerationLibraryActionResult:
        ids = tuple(str(image_id) for image_id in image_ids)
        updated = []
        for image_id in ids:
            try: record = self.get(image_id)
            except KeyError: continue
            updated.append(replace(record, status=status, review_state=status, selected=False, updated_at=utc_now()))
        self._upsert_records(updated)
        return GenerationLibraryActionResult(True, message, ids)

    def _replace_record(self, updated: GeneratedImageRecord) -> None:
        if self._canonical() is not None:
            if self._canonical().get_payload(updated.image_id) is None:
                raise KeyError(f"Generated image not found: {updated.image_id}")
            self._upsert_records((updated,))
            return
        records = [updated if record.image_id == updated.image_id else record for record in self.list_records()]
        self._write_records(records)

    def _remove_records(self, image_ids: Iterable[str]) -> None:
        ids = set(str(image_id) for image_id in image_ids)
        canonical = self._canonical()
        if canonical is not None:
            started = time.perf_counter()
            revision = canonical.delete(ids)
            canonical_ms = (time.perf_counter() - started) * 1000
            projection = self._projection()
            projection_started = time.perf_counter()
            if projection is not None:
                projection.delete(ids, source_version=f"db:{revision}")
            projection_ms = (time.perf_counter() - projection_started) * 1000
            self._log_mutation("delete", len(ids), canonical_ms, projection_ms)
            return
        self._write_records([record for record in self.list_records() if record.image_id not in ids])

    @staticmethod
    def _delete_local_file(output_reference: str) -> None:
        path = Path(str(output_reference or "")).expanduser()
        if path.exists() and path.is_file():
            path.unlink()

    @staticmethod
    def _record_from_job(
        job: GenerationJob,
        output_reference: str,
        *,
        output_index: int = 0,
    ) -> GeneratedImageRecord:
        result = job.result
        request_metadata = dict(job.request.metadata or {})
        image_id = "generated_image_" + hashlib.sha256(
            f"{job.job_id}:{output_reference}".encode("utf-8")
        ).hexdigest()[:24]
        recipe_ids = tuple(result.generation_metadata.get("output_generation_recipe_ids") or ())
        recipe_id = str(recipe_ids[output_index]) if output_index < len(recipe_ids) and recipe_ids[output_index] else None
        return GeneratedImageRecord(
            image_id=image_id,
            generation_job_id=job.job_id,
            generation_request_id=job.request.request_id,
            generation_result_id=result.result_id,
            output_reference=output_reference,
            creator_profile_id=job.request.creator_profile_id,
            provider_id=job.request.provider_id,
            prompt_plan_id=job.request.prompt_plan_id,
            prompt_text=GenerationLibraryService._prompt_for_output(job, output_index),
            creative_mode=request_metadata.get("creative_mode"),
            reference_asset_id=job.request.reference_asset_id,
            generation_recipe_id=recipe_id,
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
    def _prompt_for_output(job: GenerationJob, output_index: int) -> str:
        """Return the prompt variation used for one persisted provider output."""
        request_metadata = dict(job.request.metadata or {})
        prompt_metadata = request_metadata.get("prompt_metadata") or {}
        candidates = (
            request_metadata.get("prompt_variations")
            or (
                prompt_metadata.get("prompt_variations")
                if isinstance(prompt_metadata, Mapping)
                else ()
            )
            or ()
        )
        prompts = tuple(str(prompt).strip() for prompt in candidates if str(prompt).strip())
        if not prompts:
            return job.request.prompt_text

        failed_variation_indexes = {
            int(failure.get("index")) - 1
            for failure in (job.result.execution_metadata or {}).get("failures", ())
            if isinstance(failure, Mapping)
            and str(failure.get("index") or "").isdigit()
            and int(failure.get("index")) > 0
        }
        successful_variation_indexes = (
            index
            for index in range(max(1, int(job.request.image_count or 1)))
            if index not in failed_variation_indexes
        )
        variation_index = next(
            (
                index
                for success_index, index in enumerate(successful_variation_indexes)
                if success_index == output_index
            ),
            output_index,
        )
        return prompts[variation_index % len(prompts)]

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
            generation_recipe_id=data.get("generation_recipe_id"),
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
            is_staged=bool(data.get("is_staged", False)),
            staged_at=data.get("staged_at"),
        )

    def _write_records(self, records: list[GeneratedImageRecord]) -> None:
        canonical = self._canonical()
        if canonical is not None:
            raise RuntimeError("Whole-library replacement is bootstrap-only; use targeted canonical mutation.")
        self._write_json(self.records_path, [asdict(record) for record in records])
        projection = self._projection()
        if projection is not None:
            projection.synchronize(records, source_version=self._source_version())

    def _append_records(self, records: Iterable[GeneratedImageRecord]) -> None:
        records = tuple(records)
        if not records:
            return
        if self._canonical() is not None:
            self._upsert_records(records)
            return
        current = list(self.list_records())
        current.extend(records)
        self._write_records(current)

    def _upsert_records(self, records: Iterable[GeneratedImageRecord]) -> None:
        records = tuple(
            replace(record, is_staged=False, staged_at=None)
            if record.status != "active" and record.is_staged else record
            for record in records
        )
        if not records:
            return
        canonical = self._canonical()
        if canonical is None:
            by_id = {record.image_id: record for record in self.list_records()}
            by_id.update({record.image_id: record for record in records})
            self._write_records(list(by_id.values()))
            return
        started = time.perf_counter()
        revision = canonical.upsert(records)
        canonical_ms = (time.perf_counter() - started) * 1000
        projection = self._projection()
        projection_started = time.perf_counter()
        if projection is not None:
            projection.upsert(records, source_version=f"db:{revision}")
        projection_ms = (time.perf_counter() - projection_started) * 1000
        self._log_mutation("upsert", len(records), canonical_ms, projection_ms)

    def _log_mutation(self, action: str, count: int, canonical_ms: float, projection_ms: float) -> None:
        total_ms = canonical_ms + projection_ms
        self._performance_logger.info(
            "component=generation_library_mutation action=%s records=%s canonical_ms=%.2f projection_ms=%.2f total_ms=%.2f",
            action, count, canonical_ms, projection_ms, total_ms,
        )
        if total_ms >= 100:
            self._performance_logger.warning(
                "component=generation_library_mutation event=slow action=%s records=%s total_ms=%.2f threshold_ms=100",
                action, count, total_ms,
            )

    def export_legacy_snapshot(self, path: str | Path | None = None) -> Path:
        """Explicit compatibility/export snapshot; PostgreSQL remains canonical."""
        target = Path(path) if path is not None else self.records_path
        self._write_json(target, [asdict(record) for record in self.list_records()])
        return target

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

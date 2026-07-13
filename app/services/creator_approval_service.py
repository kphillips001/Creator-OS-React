"""Shared creator approval boundary for content creation workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable, Mapping

from app.models.creator_approval import (
    ApprovedSourceIdentity,
    CreatorApprovalRequest,
    CreatorApprovalResult,
)
from app.models.creator_intent import CreatorIntent
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.generation_engine import GenerationJob, utc_now
from app.models.generation_library import GeneratedImageRecord
from app.models.photoshoot_queue import PHOTOSHOOT_ASSET_METADATA_KEY
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class CreatorApprovalService:
    """Orchestrates approved source items into canonical Creator OS Assets.

    The service intentionally delegates Asset creation to GenerationResultIngestionService
    and AIImportWorkflowService. Its ownership is approval semantics, source provenance,
    and source-to-Asset idempotency.
    """

    DEFAULT_STORAGE_DIR = Path("data") / "creator_approvals"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        content_intelligence_registrar: Any | None = None,
        commerce_registrar: Any | None = None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self._content_intelligence_registrar = content_intelligence_registrar
        self._commerce_registrar = commerce_registrar

    @property
    def records_path(self) -> Path:
        return self.storage_dir / "creator_approval_mappings.json"

    def approve_request(
        self,
        request: CreatorApprovalRequest,
        *,
        register_asset: Callable[[], int | None] | None = None,
        metadata_writer: Callable[[int], None] | None = None,
    ) -> CreatorApprovalResult:
        key = request.source.normalized_key()
        if not key:
            return CreatorApprovalResult(
                success=False,
                source=request.source,
                errors=("Approval idempotency key is required.",),
            )
        existing = self._mapping_for_key(key)
        if existing and existing.get("asset_id") is not None:
            asset_id = int(existing["asset_id"])
            if metadata_writer is not None:
                metadata_writer(asset_id)
            intelligence = self._register_content_intelligence(asset_id, request)
            commerce = self._register_commerce(asset_id, request, intelligence)
            return CreatorApprovalResult(
                success=True,
                source=replace(request.source, idempotency_key=key),
                asset_id=asset_id,
                reused_existing_mapping=True,
                workflow_metadata=dict(existing.get("workflow_metadata") or {}),
                intelligence_status=self._intelligence_status(intelligence),
                intelligence_ready=self._intelligence_ready(intelligence),
                intelligence_missing_components=self._intelligence_missing(intelligence),
                intelligence_error=self._intelligence_error(intelligence),
                commerce_registration_id=self._commerce_registration_id(commerce),
                commerce_registration_status=self._commerce_registration_status(commerce),
                business_lifecycle_state=self._commerce_lifecycle_state(commerce),
                commerce_destination_status=self._commerce_destination_status(commerce),
                selected_commerce_destination=self._selected_commerce_destination(commerce),
                commerce_ready=self._commerce_ready(commerce),
                commerce_product_ids=self._commerce_product_ids(commerce),
                commerce_experience_ids=self._commerce_experience_ids(commerce),
                commerce_product_draft_ids=self._commerce_product_draft_ids(commerce),
                commerce_missing_requirements=self._commerce_missing(commerce),
                commerce_error=self._commerce_error(commerce),
            )
        if register_asset is None:
            return CreatorApprovalResult(
                success=False,
                source=replace(request.source, idempotency_key=key),
                errors=("No canonical Asset registration callback was provided.",),
            )
        try:
            asset_id = register_asset()
            if asset_id is None:
                raise RuntimeError("Canonical Asset registration did not return an Asset ID.")
            asset_id = int(asset_id)
            if metadata_writer is not None:
                metadata_writer(asset_id)
            intelligence = self._register_content_intelligence(asset_id, request)
            commerce = self._register_commerce(asset_id, request, intelligence)
            workflow_metadata = {
                "media_reference": request.media_reference,
                "creator_profile_id": request.creator_profile_id,
                "source_metadata": dict(request.source_metadata or {}),
                "post_approval_policy": dict(request.post_approval_policy or {}),
                "approved_at": request.approved_at,
            }
            self._upsert_mapping(
                {
                    "idempotency_key": key,
                    "asset_id": asset_id,
                    "source": asdict(replace(request.source, idempotency_key=key)),
                    "workflow_metadata": workflow_metadata,
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            return CreatorApprovalResult(
                success=True,
                source=replace(request.source, idempotency_key=key),
                asset_id=asset_id,
                new_asset_created=True,
                workflow_metadata=workflow_metadata,
                intelligence_status=self._intelligence_status(intelligence),
                intelligence_ready=self._intelligence_ready(intelligence),
                intelligence_missing_components=self._intelligence_missing(intelligence),
                intelligence_error=self._intelligence_error(intelligence),
                commerce_registration_id=self._commerce_registration_id(commerce),
                commerce_registration_status=self._commerce_registration_status(commerce),
                business_lifecycle_state=self._commerce_lifecycle_state(commerce),
                commerce_destination_status=self._commerce_destination_status(commerce),
                selected_commerce_destination=self._selected_commerce_destination(commerce),
                commerce_ready=self._commerce_ready(commerce),
                commerce_product_ids=self._commerce_product_ids(commerce),
                commerce_experience_ids=self._commerce_experience_ids(commerce),
                commerce_product_draft_ids=self._commerce_product_draft_ids(commerce),
                commerce_missing_requirements=self._commerce_missing(commerce),
                commerce_error=self._commerce_error(commerce),
            )
        except Exception as exc:
            return CreatorApprovalResult(
                success=False,
                source=replace(request.source, idempotency_key=key),
                errors=(str(exc),),
            )

    def approve_generated_record(
        self,
        record: GeneratedImageRecord,
        *,
        generation_job: GenerationJob,
        ingestion_service: GenerationResultIngestionService,
        source_workflow: str = "generation_library",
        source_session_id: str | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        post_approval_policy: Mapping[str, Any] | None = None,
    ) -> CreatorApprovalResult:
        source = ApprovedSourceIdentity(
            source_workflow=source_workflow,
            source_item_id=record.image_id,
            source_session_id=source_session_id or record.photoshoot_session_id,
            idempotency_key=self._generated_record_key(
                record,
                source_workflow=source_workflow,
                source_session_id=source_session_id,
            ),
        )
        metadata = {
            "generation_job_id": record.generation_job_id,
            "generation_request_id": record.generation_request_id,
            "generation_result_id": record.generation_result_id,
            "generated_image_id": record.image_id,
            "output_reference": record.output_reference,
            "source_workflow": source_workflow,
            **dict(source_metadata or {}),
        }
        request = CreatorApprovalRequest(
            source=source,
            media_reference=record.output_reference,
            creator_profile_id=record.creator_profile_id,
            creator_intent=CreatorIntent.create(
                "single_asset",
                legacy_upload_intent="teaser_image",
                metadata={"source": source_workflow, **metadata},
            ),
            source_metadata=metadata,
            post_approval_policy=post_approval_policy or {},
        )
        preexisting_asset_id = self._existing_generation_asset_id(
            ingestion_service,
            generation_job_id=record.generation_job_id,
            output_reference=record.output_reference,
        )

        def register_asset() -> int | None:
            if preexisting_asset_id is not None:
                return preexisting_asset_id
            partial_job = replace(
                generation_job,
                result=replace(
                    generation_job.result,
                    output_references=(record.output_reference,),
                ),
            )
            ingestion = ingestion_service.ingest_job(partial_job)
            if not ingestion.success or not ingestion.imported_asset_ids:
                raise RuntimeError("; ".join(ingestion.errors) or "Generation output was not imported.")
            return int(ingestion.imported_asset_ids[0])

        result = self.approve_request(
            request,
            register_asset=register_asset,
            metadata_writer=lambda asset_id: self._merge_asset_approval_metadata(
                asset_id,
                request=request,
                ingestion_service=ingestion_service,
            ),
        )
        if result.success and preexisting_asset_id is not None and result.new_asset_created:
            return replace(result, new_asset_created=False)
        return result

    def repair_known_mapping(
        self,
        *,
        source: ApprovedSourceIdentity,
        asset_id: int,
        workflow_metadata: Mapping[str, Any] | None = None,
    ) -> CreatorApprovalResult:
        key = source.normalized_key()
        existing = self._mapping_for_key(key)
        if existing and existing.get("asset_id") and int(existing["asset_id"]) != int(asset_id):
            return CreatorApprovalResult(
                success=False,
                source=replace(source, idempotency_key=key),
                errors=("Existing approval mapping points at a different Asset ID.",),
            )
        self._upsert_mapping(
            {
                "idempotency_key": key,
                "asset_id": int(asset_id),
                "source": asdict(replace(source, idempotency_key=key)),
                "workflow_metadata": dict(workflow_metadata or {}),
                "created_at": existing.get("created_at") if existing else utc_now(),
                "updated_at": utc_now(),
            }
        )
        return CreatorApprovalResult(
            success=True,
            source=replace(source, idempotency_key=key),
            asset_id=int(asset_id),
            reused_existing_mapping=bool(existing),
            workflow_metadata=dict(workflow_metadata or {}),
        )

    def promote_existing_asset(
        self,
        asset_id: int,
        request: CreatorApprovalRequest,
        *,
        metadata_writer: Callable[[int], None] | None = None,
        asset_repository: Any | None = None,
    ) -> CreatorApprovalResult:
        """Promote an existing canonical Asset through creator approval."""

        if metadata_writer is None:
            metadata_writer = lambda approved_asset_id: self._merge_asset_approval_metadata_with_repository(
                approved_asset_id,
                request=request,
                asset_repository=asset_repository,
            )
        return self.approve_request(
            request,
            register_asset=lambda: int(asset_id),
            metadata_writer=metadata_writer,
        )

    @classmethod
    def _generated_record_key(
        cls,
        record: GeneratedImageRecord,
        *,
        source_workflow: str,
        source_session_id: str | None,
    ) -> str:
        if source_workflow == "photoshoot":
            session_id = source_session_id or record.photoshoot_session_id or ""
            request_id = record.photoshoot_request_id or ""
            return f"photoshoot:{session_id}:{request_id}:{record.image_id}"
        output_hash = hashlib.sha256(str(record.output_reference).encode("utf-8")).hexdigest()[:24]
        return f"generation_library:{record.generation_job_id}:{record.generation_result_id}:{output_hash}"

    @staticmethod
    def _existing_generation_asset_id(
        ingestion_service: GenerationResultIngestionService,
        *,
        generation_job_id: str,
        output_reference: str,
    ) -> int | None:
        records_for_job = getattr(ingestion_service, "records_for_job", None)
        if not callable(records_for_job):
            return None
        for record in records_for_job(generation_job_id):
            if (
                getattr(record, "output_reference", None) == output_reference
                and getattr(record, "status", None) == "imported"
                and getattr(record, "asset_id", None) is not None
            ):
                return int(record.asset_id)
        return None

    @staticmethod
    def _merge_asset_approval_metadata(
        asset_id: int,
        *,
        request: CreatorApprovalRequest,
        ingestion_service: GenerationResultIngestionService,
    ) -> None:
        assets = getattr(ingestion_service, "assets", None)
        if assets is None:
            return
        get_by_id = getattr(assets, "get_by_id", None)
        update = getattr(assets, "update_media_metadata", None)
        if not callable(get_by_id) or not callable(update):
            return
        CreatorApprovalService._write_asset_approval_metadata(
            asset_id,
            request=request,
            assets=assets,
        )

    @staticmethod
    def _merge_asset_approval_metadata_with_repository(
        asset_id: int,
        *,
        request: CreatorApprovalRequest,
        asset_repository: Any | None = None,
    ) -> None:
        assets = asset_repository
        if assets is None:
            from app.repositories.asset_repository import AssetRepository

            assets = AssetRepository()
        CreatorApprovalService._write_asset_approval_metadata(
            asset_id,
            request=request,
            assets=assets,
        )

    @staticmethod
    def _write_asset_approval_metadata(
        asset_id: int,
        *,
        request: CreatorApprovalRequest,
        assets: Any,
    ) -> None:
        get_by_id = getattr(assets, "get_by_id", None)
        update = getattr(assets, "update_media_metadata", None)
        if not callable(get_by_id) or not callable(update):
            return
        asset = get_by_id(asset_id)
        media_metadata = dict(getattr(asset, "media_metadata", None) or {})
        source_metadata = dict(request.source_metadata or {})
        media_metadata["creator_approval"] = {
            "source_workflow": request.source.source_workflow,
            "source_item_id": request.source.source_item_id,
            "source_session_id": request.source.source_session_id,
            "idempotency_key": request.source.normalized_key(),
            "approved_at": request.approved_at,
            "source_metadata": source_metadata,
        }
        media_metadata[ASSET_PROVENANCE_METADATA_KEY] = provenance_context(
            AssetProvenanceClassification.CREATOR_APPROVAL,
            source="CreatorApprovalService",
            source_workflow=request.source.source_workflow,
            metadata={
                "source_item_id": request.source.source_item_id,
                "source_session_id": request.source.source_session_id,
                "idempotency_key": request.source.normalized_key(),
            },
        )
        if request.source.source_workflow == "photoshoot":
            current_photoshoot = dict(media_metadata.get(PHOTOSHOOT_ASSET_METADATA_KEY) or {})
            media_metadata[PHOTOSHOOT_ASSET_METADATA_KEY] = {
                **current_photoshoot,
                "session_id": source_metadata.get("photoshoot_session_id") or request.source.source_session_id,
                "request_id": source_metadata.get("photoshoot_request_id"),
                "sequence_index": source_metadata.get("photoshoot_sequence_index"),
                "prompt_plan_id": source_metadata.get("prompt_plan_id"),
                "generated_image_id": source_metadata.get("generated_image_id") or request.source.source_item_id,
                "shot_number": source_metadata.get("photoshoot_shot_number"),
                "source_workflow": "photoshoot",
                "approval_timestamp": request.approved_at,
            }
        update(asset_id, media_metadata)

    @property
    def content_intelligence_registrar(self):
        if self._content_intelligence_registrar is None:
            from app.services.content_intelligence_registration_service import (
                ContentIntelligenceRegistrationService,
            )

            self._content_intelligence_registrar = (
                ContentIntelligenceRegistrationService()
            )
        return self._content_intelligence_registrar

    @property
    def commerce_registrar(self):
        if self._commerce_registrar is None:
            from app.services.commerce_registration_service import (
                CommerceRegistrationService,
            )

            self._commerce_registrar = CommerceRegistrationService()
        return self._commerce_registrar

    def _register_content_intelligence(
        self,
        asset_id: int,
        request: CreatorApprovalRequest,
    ) -> Any | None:
        registrar = self.content_intelligence_registrar
        register = getattr(registrar, "register_asset", None)
        if not callable(register):
            return None
        try:
            return register(
                asset_id,
                source_workflow=request.source.source_workflow,
                approval_identity={
                    "source_workflow": request.source.source_workflow,
                    "source_item_id": request.source.source_item_id,
                    "source_session_id": request.source.source_session_id,
                    "idempotency_key": request.source.normalized_key(),
                    "approved_at": request.approved_at,
                    "source_metadata": dict(request.source_metadata or {}),
                },
            )
        except Exception as error:
            return type(
                "ContentIntelligenceRegistrationError",
                (),
                {
                    "status": type("Status", (), {"value": "FAILED"})(),
                    "ready": False,
                    "missing_components": ("content_intelligence_profile",),
                    "error_message": str(error),
                },
            )()

    def _register_commerce(
        self,
        asset_id: int,
        request: CreatorApprovalRequest,
        intelligence: Any | None,
    ) -> Any | None:
        if not self._intelligence_ready(intelligence):
            return None
        registrar = self.commerce_registrar
        register = getattr(registrar, "register_asset", None)
        if not callable(register):
            return None
        try:
            from app.models.commerce_registration import (
                CommerceRegistrationRequest,
            )

            commerce_request = CommerceRegistrationRequest(
                asset_id=int(asset_id),
                creator_profile_id=request.creator_profile_id,
                content_intelligence_status=self._intelligence_status(intelligence)
                or "UNKNOWN",
                content_intelligence_ready=True,
                source_workflow=request.source.source_workflow,
                approval_identity={
                    "source_workflow": request.source.source_workflow,
                    "source_item_id": request.source.source_item_id,
                    "source_session_id": request.source.source_session_id,
                    "idempotency_key": request.source.normalized_key(),
                    "approved_at": request.approved_at,
                    "source_metadata": dict(request.source_metadata or {}),
                },
                creator_intent=self._creator_intent_context(request.creator_intent),
                idempotency_key=request.source.normalized_key(),
            )
            return register(
                int(asset_id),
                request=commerce_request,
                content_intelligence_profile=intelligence,
            )
        except Exception as error:
            return type(
                "CommerceRegistrationError",
                (),
                {
                    "success": False,
                    "record": None,
                    "commerce_readiness": None,
                    "errors": (str(error),),
                },
            )()

    @staticmethod
    def _intelligence_status(profile: Any | None) -> str | None:
        status = getattr(profile, "status", None)
        return getattr(status, "value", status)

    @staticmethod
    def _intelligence_ready(profile: Any | None) -> bool:
        return bool(getattr(profile, "ready", False))

    @staticmethod
    def _intelligence_missing(profile: Any | None) -> tuple[str, ...]:
        return tuple(getattr(profile, "missing_components", ()) or ())

    @staticmethod
    def _intelligence_error(profile: Any | None) -> str | None:
        return getattr(profile, "error_message", None)

    @staticmethod
    def _creator_intent_context(intent: Any | None) -> Mapping[str, Any]:
        if intent is None:
            return {}
        to_context = getattr(intent, "to_context", None)
        if callable(to_context):
            context = to_context()
            return context if isinstance(context, Mapping) else {}
        if isinstance(intent, Mapping):
            return intent
        return {"intent": str(intent)}

    @staticmethod
    def _commerce_record(result: Any | None) -> Any | None:
        return getattr(result, "record", None)

    @classmethod
    def _commerce_registration_id(cls, result: Any | None) -> str | None:
        record = cls._commerce_record(result)
        registration_id = getattr(record, "registration_id", None)
        return str(registration_id) if registration_id else None

    @classmethod
    def _commerce_registration_status(cls, result: Any | None) -> str | None:
        record = cls._commerce_record(result)
        status = getattr(
            record,
            "commerce_registration_status",
            getattr(record, "status", None),
        )
        return getattr(status, "value", status)

    @classmethod
    def _commerce_lifecycle_state(cls, result: Any | None) -> str | None:
        record = cls._commerce_record(result)
        state = getattr(
            record,
            "business_lifecycle_state",
            getattr(record, "lifecycle_state", None),
        )
        return getattr(state, "value", state)

    @classmethod
    def _commerce_destination_status(cls, result: Any | None) -> str | None:
        record = cls._commerce_record(result)
        status = getattr(
            record,
            "commerce_destination_status",
            getattr(record, "destination_status", None),
        )
        return getattr(status, "value", status)

    @classmethod
    def _selected_commerce_destination(cls, result: Any | None) -> str | None:
        record = cls._commerce_record(result)
        destination = getattr(record, "selected_commerce_destination", None)
        return getattr(destination, "value", destination)

    @staticmethod
    def _commerce_ready(result: Any | None) -> bool:
        readiness = getattr(result, "commerce_readiness", None)
        return bool(getattr(readiness, "ready_for_commerce_destination", False))

    @classmethod
    def _commerce_product_ids(cls, result: Any | None) -> tuple[str, ...]:
        record = cls._commerce_record(result)
        return tuple(getattr(record, "product_ids", ()) or ())

    @classmethod
    def _commerce_experience_ids(cls, result: Any | None) -> tuple[str, ...]:
        record = cls._commerce_record(result)
        return tuple(getattr(record, "experience_ids", ()) or ())

    @classmethod
    def _commerce_product_draft_ids(cls, result: Any | None) -> tuple[str, ...]:
        record = cls._commerce_record(result)
        return tuple(getattr(record, "product_draft_ids", ()) or ())

    @staticmethod
    def _commerce_missing(result: Any | None) -> tuple[str, ...]:
        record = getattr(result, "record", None)
        if record is not None:
            return tuple(getattr(record, "missing_requirements", ()) or ())
        return tuple(getattr(result, "errors", ()) or ())

    @staticmethod
    def _commerce_error(result: Any | None) -> str | None:
        record = getattr(result, "record", None)
        if record is not None:
            return getattr(record, "error_message", None)
        errors = tuple(getattr(result, "errors", ()) or ())
        return errors[0] if errors else None

    def _mapping_for_key(self, key: str) -> dict[str, Any] | None:
        for record in self._read_records():
            if record.get("idempotency_key") == key:
                return record
        return None

    def _upsert_mapping(self, mapping: Mapping[str, Any]) -> None:
        records = self._read_records()
        key = mapping.get("idempotency_key")
        for index, existing in enumerate(records):
            if existing.get("idempotency_key") == key:
                records[index] = {**existing, **dict(mapping), "updated_at": utc_now()}
                break
        else:
            records.append(dict(mapping))
        self._write_records(records)

    def _read_records(self) -> list[dict[str, Any]]:
        try:
            if not self.records_path.exists():
                return []
            with open(self.records_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            return list(payload if isinstance(payload, list) else [])
        except (OSError, json.JSONDecodeError):
            return []

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.records_path, "w", encoding="utf-8") as file:
            json.dump(records, file, indent=2, default=str)

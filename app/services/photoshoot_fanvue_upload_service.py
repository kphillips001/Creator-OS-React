"""Fanvue upload orchestration for completed Photoshoot sessions."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.generation_engine import utc_now
from app.models.generation_library import GeneratedImageRecord
from app.models.photoshoot_queue import PhotoshootSession
from app.services.fanvue_upload_trace import fanvue_upload_exception, fanvue_upload_trace
from app.services.fanvue_api_service import FanvueAPIService
from app.services.publishing_service import PublishingService
from app.services.runtime_media_resolver import RuntimeMediaResolver


FANVUE_PHOTOSHOOT_FOLDER = "Telegram Wall"
FANVUE_WALL_FOLDER = "Wall"


@dataclass(frozen=True)
class PhotoshootFanvueUploadProgress:
    current: int
    total: int
    record: GeneratedImageRecord


class PhotoshootFanvueUploadService:
    """Uploads completed Photoshoot images through the existing publishing path."""

    def __init__(
        self,
        *,
        publishing_service: PublishingService | None = None,
        api_service_factory: Callable[..., Any] = FanvueAPIService,
        folder_name: str = FANVUE_PHOTOSHOOT_FOLDER,
        runtime_media_resolver: RuntimeMediaResolver | None = None,
    ):
        self.publishing_service = publishing_service or PublishingService()
        self.api_service_factory = api_service_factory
        self.folder_name = folder_name
        self.runtime_media_resolver = runtime_media_resolver or RuntimeMediaResolver()

    def upload_completed_session(
        self,
        *,
        session: PhotoshootSession,
        records: Iterable[GeneratedImageRecord],
        fanvue_account_id: int | None,
        progress_callback: Callable[[PhotoshootFanvueUploadProgress], None] | None = None,
        reuse_existing_upload_metadata: bool = True,
    ) -> dict[str, Any]:
        trace_context = {
            "session_id": session.session_id,
            "folder_name": self.folder_name,
            "fanvue_account_id": fanvue_account_id,
        }
        fanvue_upload_trace(
            "photoshoot_upload.start",
            **trace_context,
            reuse_existing_upload_metadata=reuse_existing_upload_metadata,
        )
        if not fanvue_account_id:
            fanvue_upload_trace("photoshoot_upload.missing_account", **trace_context)
            return {
                "success": False,
                "reason": "missing_fanvue_account",
                "error": "No connected Fanvue account is selected.",
            }

        ordered_records = tuple(records)
        fanvue_upload_trace(
            "photoshoot_upload.records_loaded",
            **trace_context,
            image_ids=tuple(record.image_id for record in ordered_records),
            total_count=len(ordered_records),
        )
        if not ordered_records:
            fanvue_upload_trace("photoshoot_upload.no_records", **trace_context)
            return {
                "success": False,
                "reason": "no_photoshoot_images",
                "error": "No completed Photoshoot images were found.",
            }

        folder = self._resolve_folder(fanvue_account_id)
        if not folder.get("success"):
            fanvue_upload_trace(
                "photoshoot_upload.folder_lookup_failed",
                **trace_context,
                folder_result=folder,
            )
            return folder
        fanvue_upload_trace(
            "photoshoot_upload.folder_resolved",
            **trace_context,
            folder=folder.get("folder"),
        )

        missing_files = []
        for record in ordered_records:
            media = self._resolved_record_media(record)
            fanvue_upload_trace(
                "photoshoot_upload.local_file_check",
                **trace_context,
                image_id=record.image_id,
                filename=media["filename"],
                absolute_path=media["absolute_path"],
                file_size=media["file_size"],
                exists=media["exists"],
            )
            if not media["exists"]:
                missing_files.append(media)
        if missing_files:
            fanvue_upload_trace(
                "photoshoot_upload.local_file_missing",
                **trace_context,
                missing_files=missing_files,
            )
            return {
                "success": False,
                "reason": "local_file_missing",
                "error": "One or more completed Photoshoot files are missing locally.",
                "missing_files": tuple(missing_files),
            }

        existing_upload = self.upload_metadata(session) if reuse_existing_upload_metadata else {}
        uploaded_by_image_id = dict(existing_upload.get("uploaded_media_by_image_id") or {})
        uploaded_media_ids = list(existing_upload.get("uploaded_media_ids") or ())
        pending_records = tuple(
            record for record in ordered_records if record.image_id not in uploaded_by_image_id
        )
        fanvue_upload_trace(
            "photoshoot_upload.pending_records",
            **trace_context,
            uploaded_by_image_id=uploaded_by_image_id,
            pending_image_ids=tuple(record.image_id for record in pending_records),
            pending_count=len(pending_records),
        )

        failures: list[dict[str, Any]] = []
        uploaded_this_run: list[dict[str, Any]] = []
        total = len(pending_records)

        for index, record in enumerate(pending_records, start=1):
            if progress_callback:
                progress_callback(
                    PhotoshootFanvueUploadProgress(
                        current=index,
                        total=total,
                        record=record,
                    )
                )

            upload_item = {
                "id": record.image_id,
                "file_path": record.output_reference,
                "classification": "WALL_IMAGE",
                "folder_name": self.folder_name,
                "_fanvue_trace": {
                    **trace_context,
                    "image_id": record.image_id,
                },
            }
            fanvue_upload_trace(
                "photoshoot_upload.image_upload_start",
                **trace_context,
                image_id=record.image_id,
                index=index,
                total=total,
                upload_item=upload_item,
            )
            try:
                upload_result = self.publishing_service.upload_asset_media_item(
                    fanvue_account_id=int(fanvue_account_id),
                    item=upload_item,
                )
            except Exception as exc:
                fanvue_upload_exception(
                    "photoshoot_upload.image_upload_exception",
                    exc,
                    **trace_context,
                    image_id=record.image_id,
                    index=index,
                    total=total,
                    upload_item=upload_item,
                    stage="publishing_service_upload",
                )
                raise
            fanvue_upload_trace(
                "photoshoot_upload.publishing_service_result",
                **trace_context,
                image_id=record.image_id,
                upload_result=upload_result,
            )

            if not upload_result.get("success"):
                error = upload_result.get("error") or upload_result
                if isinstance(error, Mapping):
                    error = error.get("message") or error
                failures.append(
                    {
                        "image_id": record.image_id,
                        "file_path": record.output_reference,
                        "error": error,
                    }
                )
                continue

            media_id = (
                upload_result.get("media_uuid")
                or upload_result.get("full_uuid")
                or upload_result.get("preview_uuid")
            )
            if not media_id:
                failures.append(
                    {
                        "image_id": record.image_id,
                        "file_path": record.output_reference,
                        "error": "Fanvue upload did not return a media UUID.",
                    }
                )
                continue
            if self.folder_name and not upload_result.get("folder_success"):
                failures.append(
                    {
                        "image_id": record.image_id,
                        "file_path": record.output_reference,
                        "media_uuid": media_id,
                        "error": "Fanvue upload did not confirm Wall folder attachment.",
                    }
                )
                continue
            if media_id:
                uploaded_by_image_id[record.image_id] = media_id
                if media_id not in uploaded_media_ids:
                    uploaded_media_ids.append(media_id)
            uploaded_this_run.append(
                {
                    "image_id": record.image_id,
                    "media_id": media_id,
                    "upload_result": upload_result,
                }
            )

        uploaded_count = len(uploaded_by_image_id)
        total_count = len(ordered_records)
        complete = uploaded_count == total_count and not failures
        timestamp = utc_now()
        fanvue_upload_trace(
            "photoshoot_upload.complete",
            **trace_context,
            success=complete,
            uploaded_count=uploaded_count,
            total_count=total_count,
            failures=failures,
            uploaded_media_ids=uploaded_media_ids,
        )

        return {
            "success": complete,
            "partial_success": bool(uploaded_this_run) and not complete,
            "uploaded_to_fanvue": complete,
            "uploaded_folder": self.folder_name,
            "uploaded_timestamp": timestamp if complete else existing_upload.get("uploaded_timestamp"),
            "last_attempted_at": timestamp,
            "uploaded_media_ids": tuple(uploaded_media_ids),
            "uploaded_media_by_image_id": uploaded_by_image_id,
            "uploaded_count": uploaded_count,
            "total_count": total_count,
            "uploaded_this_run": tuple(uploaded_this_run),
            "failures": tuple(failures),
            "folder": folder.get("folder"),
        }

    def register_customer_conversations_fulfillment(
        self,
        *,
        session: PhotoshootSession,
        records: Iterable[GeneratedImageRecord],
        fanvue_account_id: int,
        fulfillment_service: Any,
    ) -> dict[str, Any]:
        """Upload Photoshoot chat fulfillment by canonical imported_asset_id."""

        results: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for record in records:
            asset_id = getattr(record, "imported_asset_id", None)
            if asset_id is None:
                failures.append(
                    {
                        "image_id": record.image_id,
                        "error": "missing_imported_asset_id",
                    }
                )
                continue
            result = fulfillment_service.upload_customer_conversations_asset(
                asset_id=int(asset_id),
                fanvue_account_id=int(fanvue_account_id),
            )
            payload = {
                "image_id": record.image_id,
                "asset_id": int(asset_id),
                "success": bool(getattr(result, "success", False)),
                "record": (
                    result.record.to_context()
                    if getattr(result, "record", None)
                    else None
                ),
                "errors": tuple(getattr(result, "errors", ()) or ()),
                "warnings": tuple(getattr(result, "warnings", ()) or ()),
            }
            results.append(payload)
            if not payload["success"]:
                failures.append(payload)
        return {
            "success": not failures,
            "partial_success": bool(results) and bool(failures),
            "session_id": session.session_id,
            "fanvue_account_id": int(fanvue_account_id),
            "results": tuple(results),
            "failures": tuple(failures),
        }

    def _resolve_folder(self, fanvue_account_id: int) -> dict[str, Any]:
        fanvue_upload_trace(
            "photoshoot_upload.folder_lookup_start",
            folder_name=self.folder_name,
            fanvue_account_id=fanvue_account_id,
            stage="folder_lookup",
        )
        try:
            api = self.api_service_factory(fanvue_account_id=int(fanvue_account_id))
            result = api.list_vault_folders()
        except Exception as exc:
            fanvue_upload_exception(
                "photoshoot_upload.folder_lookup_exception",
                exc,
                folder_name=self.folder_name,
                fanvue_account_id=fanvue_account_id,
                stage="folder_lookup",
            )
            return {
                "success": False,
                "reason": "fanvue_folder_lookup_failed",
                "error": str(exc),
            }
        fanvue_upload_trace(
            "photoshoot_upload.folder_lookup_result",
            folder_name=self.folder_name,
            fanvue_account_id=fanvue_account_id,
            result=result,
            stage="folder_lookup",
        )

        if not result or not result.get("success"):
            return {
                "success": False,
                "reason": "fanvue_folder_lookup_failed",
                "error": result,
            }

        for folder in result.get("data") or ():
            if self._folder_name(folder).strip().lower() == self.folder_name.lower():
                return {
                    "success": True,
                    "folder": folder,
                }

        return {
            "success": False,
            "reason": "fanvue_folder_not_found",
            "error": f'Fanvue Vault folder "{self.folder_name}" was not found.',
        }

    @staticmethod
    def _folder_name(folder: Mapping[str, Any]) -> str:
        return str(
            folder.get("name")
            or folder.get("title")
            or folder.get("folderName")
            or ""
        )

    @staticmethod
    def upload_metadata(session: PhotoshootSession) -> dict[str, Any]:
        metadata = dict(session.metadata or {})
        upload = metadata.get("fanvue_photoshoot_upload") or {}
        if isinstance(upload, Mapping):
            return dict(upload)
        return {}

    def _resolved_record_media(self, record: GeneratedImageRecord) -> dict[str, Any]:
        path = self.runtime_media_resolver.resolve_original_path(
            {"file_path": record.output_reference},
            require_exists=True,
        )
        if path is None:
            raw_path = Path(str(record.output_reference or "")).expanduser()
            return {
                "image_id": record.image_id,
                "filename": raw_path.name,
                "absolute_path": str(raw_path.resolve()),
                "file_size": None,
                "exists": False,
            }
        return {
            "image_id": record.image_id,
            "filename": path.name,
            "absolute_path": str(path.resolve()),
            "file_size": path.stat().st_size,
            "exists": True,
        }

    @staticmethod
    def local_file_exists(record: GeneratedImageRecord) -> bool:
        return Path(str(record.output_reference or "")).expanduser().is_file()

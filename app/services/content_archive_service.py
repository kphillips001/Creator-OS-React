"""Content Studio active generation archive service."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests

from app.config import settings
from app.models.content_archive import ContentArchiveRecord
from app.models.generation_engine import new_generation_id, utc_now
from app.models.generation_library import GeneratedImageRecord


logger = logging.getLogger(__name__)


class ContentArchiveService:
    """Owns Content root paths and generated-image lifecycle history."""

    DEFAULT_STORAGE_DIR = Path("data") / "content_archive"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        content_root: str | Path | None = None,
        http_client=None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.content_root = Path(content_root or settings.CONTENT_ROOT)
        self.http_client = http_client or requests

    @property
    def records_path(self) -> Path:
        return self.storage_dir / "content_archive.json"

    def content_paths(self) -> dict[str, Path]:
        root = self.content_root
        return {
            "generation_active": root / "Generation" / "Active",
            "generation_social": root / "Generation" / "Social",
            "generation_premium": root / "Generation" / "Premium",
            "generation_photoshoot_active": root / "Generation" / "Photoshoot" / "Active",
            "generation_photoshoot_gallery": root / "Generation" / "Photoshoot" / "Gallery",
            "generation_photoshoot_junk": root / "Generation" / "Photoshoot" / "Junk",
            "pending_edit": root / "Pending_Edit",
            "pending_photoshoot": root / "Pending_Photoshoot",
            "pending_video": root / "Pending_Video",
            "edited_originals": root / "Edited" / "Originals",
            "edited_approved": root / "Edited" / "Approved",
            "posted_x_main": root / "Posted" / "X" / "Main",
            "posted_x_slaves_staged": root / "Posted" / "X" / "Slaves" / "Staged",
            "posted_telegram_main": root / "Posted" / "Telegram" / "Main",
            "posted_telegram_vault": root / "Posted" / "Telegram" / "Vault",
            "posted_fanvue_free": root / "Posted" / "Fanvue" / "Free",
            "posted_fanvue_paid": root / "Posted" / "Fanvue" / "Paid",
            "archive_edited": root / "Archive" / "Edited",
            "archive_imported": root / "Archive" / "Imported",
            "archive_junk": root / "Archive" / "Removed Content",
            "archive_versions": root / "Archive" / "Versions",
        }

    def cms_paths(self) -> dict[str, Path]:
        cms_root = self.content_root.parent
        paths = dict(self.content_paths())
        paths.update(
            {
                "cms_root": cms_root,
                "content_root": self.content_root,
                "vault_original_images": cms_root / "Vault" / "Originals" / "Images",
                "vault_original_videos": cms_root / "Vault" / "Originals" / "Videos",
                "vault_thumbnails": cms_root / "Vault" / "Thumbnails",
                "vault_blurred": cms_root / "Vault" / "Blurred",
                "vault_transcoded": cms_root / "Vault" / "Transcoded",
                "exports": cms_root / "Exports",
                "backups": cms_root / "Backups",
                "logs": cms_root / "Logs",
            }
        )
        return paths

    def initialize_content_root(self) -> None:
        for path in self.cms_paths().values():
            path.mkdir(parents=True, exist_ok=True)

    def materialize_generation(self, record: GeneratedImageRecord) -> GeneratedImageRecord:
        """Put an active generated image in the CMS Generation folder."""
        self.initialize_content_root()
        destination = self._generation_destination_for_workflow(
            record.generation_metadata.get("workflow_type")
            or record.generation_metadata.get("source")
            or record.creative_mode
        )
        materialized_path = self._move_or_materialize(
            record.output_reference,
            destination,
            record.image_id,
        )
        if str(materialized_path) == record.output_reference:
            return record
        return replace(
            record,
            output_reference=str(materialized_path),
            generation_metadata={
                **dict(record.generation_metadata or {}),
                "original_output_reference": record.output_reference,
                "output_reference": str(materialized_path),
                "cms_content_root": str(self.content_root),
            },
            updated_at=utc_now(),
        )

    def copy_generation(self, record: GeneratedImageRecord) -> GeneratedImageRecord:
        """Copy durable source media into the active Generation Library without consuming it."""
        self.initialize_content_root()
        destination = self._generation_destination_for_workflow(
            record.generation_metadata.get("workflow_type")
            or record.generation_metadata.get("source")
            or record.creative_mode
        )
        copied_path = self._copy_or_materialize(
            record.output_reference, destination, record.image_id,
        )
        if str(copied_path) == record.output_reference:
            return record
        return replace(record, output_reference=str(copied_path), generation_metadata={
            **dict(record.generation_metadata or {}),
            "original_output_reference": record.output_reference,
            "output_reference": str(copied_path),
            "cms_content_root": str(self.content_root),
        }, updated_at=utc_now())

    def archive_published(
        self,
        record: GeneratedImageRecord,
        *,
        platform: str,
        caption: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentArchiveRecord:
        normalized_platform = str(platform or "").strip().lower()
        if normalized_platform == "telegram":
            post_to = str((metadata or {}).get("post_to") or "main").strip().lower()
            destination_key = "posted_telegram_vault" if post_to == "vault" else "posted_telegram_main"
            archive_type = "published_telegram"
            platform_label = "Telegram"
        elif normalized_platform == "fanvue":
            destination_key = "posted_fanvue_free"
            archive_type = "published_fanvue"
            platform_label = "Fanvue"
        else:
            destination_key = "posted_x_main"
            archive_type = "published_x"
            platform_label = "X"
        archived = self.archive_record(
            record,
            archive_type=archive_type,
            destination=self.content_paths()[destination_key],
            platform=platform_label,
            caption=caption,
            metadata={
                "publish_datetime": utc_now(),
                **dict(metadata or {}),
            },
        )
        if normalized_platform == "x" and self._includes_main_x_account(metadata):
            try:
                staged_path = self._stage_main_x_publish_for_slaves(
                    Path(archived.current_file_path)
                )
                logger.info(
                    "X slave staging copy ready | image_id=%s source=%s staged=%s",
                    record.image_id,
                    archived.current_file_path,
                    staged_path,
                )
            except Exception:
                logger.exception(
                    "X publish succeeded but slave staging copy failed | "
                    "image_id=%s source=%s destination=%s",
                    record.image_id,
                    archived.current_file_path,
                    self.content_paths()["posted_x_slaves_staged"],
                )
        return archived

    @staticmethod
    def _includes_main_x_account(metadata: Mapping[str, Any] | None) -> bool:
        values = dict(metadata or {})
        account_names = values.get("account_names") or ()
        return values.get("account_name") == "AvaBlackthorne" or "AvaBlackthorne" in account_names

    def _stage_main_x_publish_for_slaves(self, published_path: Path) -> Path:
        """Idempotently copy an X Main publication without transforming its bytes."""
        source = published_path.expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"Published X image is unavailable: {source}")
        destination = self.content_paths()["posted_x_slaves_staged"]
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / source.name
        source_digest = self._file_digest(source)
        if target.is_file():
            if self._file_digest(target) == source_digest:
                return target
            target = destination / f"{source.stem}_{source_digest[:12]}{source.suffix}"
            if target.is_file() and self._file_digest(target) == source_digest:
                return target
        shutil.copy2(source, target)
        return target

    @staticmethod
    def _file_digest(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def archive_edited(
        self,
        record: GeneratedImageRecord,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentArchiveRecord:
        return self.archive_record(
            record,
            archive_type="edited_original",
            destination=self.content_paths()["archive_edited"],
            metadata=metadata,
        )

    def move_to_pending_edit(self, record: GeneratedImageRecord) -> Path:
        return self._move_or_materialize(
            record.output_reference,
            self.content_paths()["pending_edit"],
            record.image_id,
        )

    def move_to_pending_workflow(self, record: GeneratedImageRecord, *, workflow: str) -> Path:
        normalized = str(workflow or "").strip().lower()
        destination_key = {
            "edit": "pending_edit",
            "photoshoot": "pending_photoshoot",
            "video": "pending_video",
        }.get(normalized)
        if not destination_key:
            raise ValueError(f"Unsupported pending workflow: {workflow}")
        return self._move_or_materialize(
            record.output_reference,
            self.content_paths()[destination_key],
            record.image_id,
        )

    def move_to_generation_active(self, record: GeneratedImageRecord) -> Path:
        return self._move_or_materialize(
            record.output_reference,
            self.content_paths()["generation_active"],
            record.image_id,
        )

    def copy_edit_history(
        self,
        record: GeneratedImageRecord,
        *,
        history_type: str,
    ) -> Path:
        paths = self.content_paths()
        destination = (
            paths["edited_approved"]
            if str(history_type or "").strip().lower() == "approved"
            else paths["edited_originals"]
        )
        return self._copy_or_materialize(record.output_reference, destination, record.image_id)

    def archive_asset_version(
        self,
        record: GeneratedImageRecord,
        *,
        version_number: int,
        approval_timestamp: str,
        edit_source: str,
    ) -> ContentArchiveRecord:
        """Preserve one superseded Generation Library version for future restore."""
        version = max(1, int(version_number))
        existing = next((
            item
            for item in self.list_asset_versions(record.image_id)
            if int(item.metadata.get("version_number") or 0) == version
            and item.original_output_reference == record.output_reference
            and Path(item.current_file_path).is_file()
        ), None)
        if existing is not None:
            return existing
        destination = (
            self.content_paths()["archive_versions"]
            / record.image_id
            / f"Version_{version:04d}"
        )
        self.initialize_content_root()
        archived_path = self._copy_or_materialize(
            record.output_reference,
            destination,
            record.image_id,
        )
        archive_record = ContentArchiveRecord(
            archive_id=new_generation_id("asset_version"),
            image_id=record.image_id,
            archive_type="asset_version",
            destination=str(destination),
            current_file_path=str(archived_path),
            original_output_reference=record.output_reference,
            provider_id=record.provider_id,
            workflow=record.generation_metadata.get("workflow_type") or record.generation_metadata.get("source"),
            prompt_text=record.prompt_text,
            imported_asset_id=record.imported_asset_id,
            generation_record=asdict(record),
            metadata={
                "generation_library_record_id": record.image_id,
                "version_number": version,
                "approval_timestamp": approval_timestamp,
                "provider": record.provider_id,
                "prompt": record.prompt_text,
                "prompt_plan_id": record.prompt_plan_id,
                "provider_metadata": dict(record.provider_metadata or {}),
                "prompt_metadata": dict(record.prompt_metadata or {}),
                "generation_metadata": dict(record.generation_metadata or {}),
                "original_file_path": record.output_reference,
                "archived_file_path": str(archived_path),
                "edit_source": str(edit_source or "edit_studio"),
            },
        )
        records = list(self.list_records())
        records.insert(0, archive_record)
        self._write_records(records)
        self._write_json(
            archived_path.with_suffix(archived_path.suffix + ".json"),
            asdict(archive_record),
        )
        return archive_record

    def list_asset_versions(self, image_id: str) -> tuple[ContentArchiveRecord, ...]:
        records = tuple(
            record
            for record in self.list_records(archive_type="asset_version")
            if record.image_id == str(image_id)
        )
        return tuple(
            sorted(
                records,
                key=lambda record: int(record.metadata.get("version_number") or 0),
                reverse=True,
            )
        )

    def copy_asset_version_to_generation_active(
        self,
        archive_record: ContentArchiveRecord,
    ) -> Path:
        """Copy an immutable archived version into active storage for promotion."""
        source = Path(archive_record.current_file_path).expanduser()
        if not source.is_file():
            raise FileNotFoundError(f"Archived version media is unavailable: {source}")
        restored = self._copy_or_materialize(
            str(source),
            self.content_paths()["generation_active"],
            archive_record.image_id,
        )
        if not restored.is_file():
            raise RuntimeError("Archived version media could not be staged in Generation Active.")
        return restored

    def rollback_asset_version_archive(self, archive_id: str) -> None:
        """Remove only a newly-created archive record from a failed promotion."""
        target = next((item for item in self.list_records() if item.archive_id == archive_id), None)
        if target is None or target.archive_type != "asset_version":
            return
        media = Path(target.current_file_path)
        manifest = media.with_suffix(media.suffix + ".json")
        if media.is_file():
            media.unlink()
        if manifest.is_file():
            manifest.unlink()
        try:
            media.parent.rmdir()
        except OSError:
            pass
        self._write_records([item for item in self.list_records() if item.archive_id != archive_id])

    def archive_imported(
        self,
        record: GeneratedImageRecord,
        *,
        imported_asset_id: int,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentArchiveRecord:
        return self.archive_record(
            record,
            archive_type="imported",
            destination=self.content_paths()["archive_imported"],
            imported_asset_id=imported_asset_id,
            metadata=metadata,
        )

    def archive_junk(
        self,
        record: GeneratedImageRecord,
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentArchiveRecord:
        return self.archive_record(
            record,
            archive_type="junk",
            destination=self.content_paths()["archive_junk"],
            metadata=metadata,
        )

    def archive_record(
        self,
        record: GeneratedImageRecord,
        *,
        archive_type: str,
        destination: Path,
        platform: str | None = None,
        caption: str | None = None,
        imported_asset_id: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ContentArchiveRecord:
        self.initialize_content_root()
        destination_path = self._move_or_materialize(record.output_reference, destination, record.image_id)
        archive_record = ContentArchiveRecord(
            archive_id=new_generation_id("content_archive"),
            image_id=record.image_id,
            archive_type=str(archive_type),
            destination=str(destination),
            current_file_path=str(destination_path),
            original_output_reference=record.output_reference,
            provider_id=record.provider_id,
            workflow=record.generation_metadata.get("workflow_type") or record.generation_metadata.get("source"),
            platform=platform,
            caption=caption,
            prompt_text=record.prompt_text,
            imported_asset_id=imported_asset_id,
            generation_record=asdict(record),
            metadata={
                "provider_metadata": dict(record.provider_metadata or {}),
                "prompt_metadata": dict(record.prompt_metadata or {}),
                "generation_metadata": dict(record.generation_metadata or {}),
                **dict(metadata or {}),
            },
        )
        records = list(self.list_records())
        records.insert(0, archive_record)
        self._write_records(records)
        return archive_record

    def restore_junk(self, image_id: str) -> GeneratedImageRecord:
        archive_record = self.get_latest(image_id, archive_type="junk")
        restored_path = self._move_or_materialize(
            archive_record.current_file_path,
            self._generation_destination(archive_record),
            image_id,
        )
        data = dict(archive_record.generation_record or {})
        data["output_reference"] = str(restored_path)
        data["status"] = "active"
        data["review_state"] = "restored"
        data["selected"] = False
        data["updated_at"] = utc_now()
        restored = self._generated_record_from_dict(data)
        updated_records = []
        for item in self.list_records():
            if item.archive_id == archive_record.archive_id:
                updated_records.append(
                    ContentArchiveRecord(
                        **{
                            **asdict(item),
                            "archive_type": "restored_from_junk",
                            "current_file_path": str(restored_path),
                            "updated_at": utc_now(),
                            "metadata": {
                                **dict(item.metadata or {}),
                                "restored_at": utc_now(),
                            },
                        }
                    )
                )
            else:
                updated_records.append(item)
        self._write_records(updated_records)
        return restored

    def permanent_delete_junk(self, image_id: str) -> bool:
        archive_record = self.get_latest(image_id, archive_type="junk")
        path = Path(archive_record.current_file_path)
        if path.exists():
            path.unlink()
        remaining = [item for item in self.list_records() if item.archive_id != archive_record.archive_id]
        self._write_records(remaining)
        return True

    def get_latest(self, image_id: str, *, archive_type: str | None = None) -> ContentArchiveRecord:
        for record in self.list_records():
            if record.image_id != image_id:
                continue
            if archive_type and record.archive_type != archive_type:
                continue
            return record
        raise KeyError(f"Archive record not found: {image_id}")

    def list_records(self, *, archive_type: str | None = None) -> tuple[ContentArchiveRecord, ...]:
        records = tuple(self._record_from_dict(item) for item in self._read_json(self.records_path, []))
        if archive_type:
            records = tuple(record for record in records if record.archive_type == archive_type)
        return records

    def _generation_destination(self, archive_record: ContentArchiveRecord) -> Path:
        return self._generation_destination_for_workflow(archive_record.workflow)

    def _generation_destination_for_workflow(self, workflow_value: Any) -> Path:
        workflow = str(workflow_value or "").strip().lower()
        if "photoshoot" in workflow:
            return self.content_paths()["generation_photoshoot_active"]
        return self.content_paths()["generation_active"]

    def _move_or_materialize(self, source_reference: str, destination: Path, image_id: str) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        source = str(source_reference or "").strip()
        suffix = Path(urlparse(source).path).suffix or Path(source).suffix or ".jpg"
        target = self._unique_path(destination / f"{image_id}{suffix}")
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            response = self.http_client.get(source, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status()
            target.write_bytes(response.content)
            return target
        source_path = Path(source).expanduser()
        if source_path.exists():
            if source_path.resolve() == target.resolve():
                return target
            shutil.move(str(source_path), str(target))
            return target
        return Path(source or target)

    def _copy_or_materialize(self, source_reference: str, destination: Path, image_id: str) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        source = str(source_reference or "").strip()
        suffix = Path(urlparse(source).path).suffix or Path(source).suffix or ".jpg"
        target = self._unique_path(destination / f"{image_id}{suffix}")
        parsed = urlparse(source)
        if parsed.scheme in {"http", "https"}:
            response = self.http_client.get(source, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status()
            target.write_bytes(response.content)
            return target
        source_path = Path(source).expanduser()
        if source_path.exists():
            if source_path.resolve() == target.resolve():
                return target
            shutil.copy2(str(source_path), str(target))
            return target
        return Path(source or target)

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

    @staticmethod
    def _generated_record_from_dict(data: Mapping[str, Any]) -> GeneratedImageRecord:
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
            generation_date=str(data.get("generation_date") or ""),
            status=str(data.get("status") or "active"),
            review_state=str(data.get("review_state") or "unreviewed"),
            selected=bool(data.get("selected", False)),
            imported_asset_id=data.get("imported_asset_id"),
            provider_metadata=data.get("provider_metadata") or {},
            prompt_metadata=data.get("prompt_metadata") or {},
            generation_metadata=data.get("generation_metadata") or {},
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _record_from_dict(data: Mapping[str, Any]) -> ContentArchiveRecord:
        return ContentArchiveRecord(
            archive_id=str(data.get("archive_id") or ""),
            image_id=str(data.get("image_id") or ""),
            archive_type=str(data.get("archive_type") or ""),
            destination=str(data.get("destination") or ""),
            current_file_path=str(data.get("current_file_path") or ""),
            original_output_reference=str(data.get("original_output_reference") or ""),
            provider_id=str(data.get("provider_id") or ""),
            workflow=data.get("workflow"),
            platform=data.get("platform"),
            caption=data.get("caption"),
            prompt_text=data.get("prompt_text"),
            imported_asset_id=data.get("imported_asset_id"),
            generation_record=data.get("generation_record") or {},
            metadata=data.get("metadata") or {},
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
        )

    def _write_records(self, records: list[ContentArchiveRecord]) -> None:
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

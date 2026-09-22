"""Read-only browser over Creator OS published-media storage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.content_archive import ContentArchiveRecord
from app.services.content_archive_service import ContentArchiveService
from app.services.generation_library_service import GenerationLibraryService


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@dataclass(frozen=True)
class PostedContentItem:
    content_id: str
    platform: str
    posted_at: str
    caption: str
    creator: str
    creator_profile_id: int | None
    generation_library_id: str
    provider: str
    prompt: str
    file_location: str
    media_url: str
    media_type: str
    move_eligible: bool


class PostedContentService:
    """Discovers publication history and delegates canonical library returns."""

    def __init__(self, archive_service: ContentArchiveService | None = None,
                 generation_library: GenerationLibraryService | None = None):
        self.archive_service = archive_service or ContentArchiveService()
        self.generation_library = generation_library or GenerationLibraryService(
            archive_service=self.archive_service
        )

    def published_folders(self) -> tuple[tuple[str, Path], ...]:
        paths = self.archive_service.content_paths()
        return (
            ("X", paths["posted_x_main"]),
            ("Telegram", paths["posted_telegram_main"]),
            ("Telegram", paths["posted_telegram_vault"]),
            ("Fanvue", paths["posted_fanvue_free"]),
            ("Fanvue", paths["posted_fanvue_paid"]),
        )

    def list_items(self) -> tuple[PostedContentItem, ...]:
        records = {
            self._normalized_path(record.current_file_path): record
            for record in self.archive_service.list_records()
            if record.archive_type.startswith("published_")
            and (record.metadata or {}).get("current_disposition") != "generation_library"
        }
        items: list[PostedContentItem] = []
        seen: set[str] = set()
        for platform, folder in self.published_folders():
            if not folder.is_dir():
                continue
            for path in folder.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                    continue
                normalized = self._normalized_path(path)
                if normalized in seen:
                    continue
                seen.add(normalized)
                items.append(self._item(path, platform, records.get(normalized)))
        return tuple(sorted(items, key=lambda item: (item.posted_at, item.content_id), reverse=True))

    def get(self, content_id: str) -> PostedContentItem:
        for item in self.list_items():
            if item.content_id == content_id:
                return item
        record = next((item for item in self.archive_service.list_records()
                       if item.archive_id == content_id
                       and item.archive_type.startswith("published_")), None)
        if record is not None and Path(record.current_file_path).is_file():
            return self._item(Path(record.current_file_path), record.platform or "", record)
        raise KeyError(f"Posted content not found: {content_id}")

    def move_to_generation_library(self, content_id: str) -> tuple[PostedContentItem, bool]:
        record = next((item for item in self.archive_service.list_records()
                       if item.archive_id == str(content_id)
                       and item.archive_type.startswith("published_")), None)
        if record is None:
            raise KeyError(f"Posted content not found: {content_id}")
        path = Path(record.current_file_path)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ValueError("Only published images can move to Generation Library.")
        if not self._move_eligible(record):
            raise ValueError("Published image lacks canonical Generation Library lineage.")
        restored, already_moved = self.generation_library.restore_published_archive(record)
        updated = next(item for item in self.archive_service.list_records()
                       if item.archive_id == record.archive_id)
        return self._item(Path(restored.output_reference), updated.platform or "", updated), already_moved

    @staticmethod
    def _item(path: Path, platform: str, record: ContentArchiveRecord | None) -> PostedContentItem:
        metadata = dict(record.metadata or {}) if record else {}
        generation = dict(record.generation_record or {}) if record else {}
        creator_profile_id = generation.get("creator_profile_id")
        creator_name = str(
            metadata.get("creator_name")
            or generation.get("creator_name")
            or (f"Creator #{creator_profile_id}" if creator_profile_id else "Current Creator")
        )
        posted_at = str(metadata.get("publish_datetime") or (record.created_at if record else ""))
        if not posted_at:
            posted_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        content_id = record.archive_id if record else "posted_" + hashlib.sha256(
            str(path.resolve()).encode("utf-8")
        ).hexdigest()[:24]
        generation_id = record.image_id if record else path.stem
        return PostedContentItem(
            content_id=content_id,
            platform=platform,
            posted_at=posted_at,
            caption=str(record.caption or "") if record else "",
            creator=creator_name,
            creator_profile_id=int(creator_profile_id) if creator_profile_id else None,
            generation_library_id=generation_id,
            provider=str(record.provider_id or "") if record else "",
            prompt=str(record.prompt_text or "") if record else "",
            file_location=str(path),
            media_url=f"/api/v1/posted-content/{content_id}/media",
            media_type="image",
            move_eligible=PostedContentService._move_eligible(record),
        )

    @staticmethod
    def _move_eligible(record: ContentArchiveRecord | None) -> bool:
        if record is None:
            return False
        snapshot = dict(record.generation_record or {})
        return bool(snapshot.get("image_id") and snapshot.get("creator_profile_id"))

    @staticmethod
    def _normalized_path(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve()).casefold()

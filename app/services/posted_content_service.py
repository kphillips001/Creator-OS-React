"""Read-only browser over Creator OS published-media storage."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.models.content_archive import ContentArchiveRecord
from app.services.content_archive_service import ContentArchiveService


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


class PostedContentService:
    """Discovers published files without moving or persisting anything."""

    def __init__(self, archive_service: ContentArchiveService | None = None):
        self.archive_service = archive_service or ContentArchiveService()

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
        raise KeyError(f"Posted content not found: {content_id}")

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
        )

    @staticmethod
    def _normalized_path(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve()).casefold()

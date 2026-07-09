"""Social Publishing marketing workflow service."""

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.models.generation_engine import new_generation_id, utc_now
from app.models.social_publishing import (
    SocialPlatform,
    SocialPublishHistory,
    SocialPublishRequest,
    SocialPublishStatus,
    SocialPublishingSession,
    SocialQueueItem,
)
from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.providers.social.x_provider import XPublishingProvider
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_library_service import GenerationLibraryService
from app.services.generation_result_ingestion_service import GenerationResultIngestionService


class SocialPublishingService:
    """Owns marketing queue state without posting or product publishing."""

    DEFAULT_STORAGE_DIR = Path("data") / "social_publishing"

    def __init__(
        self,
        *,
        storage_dir: str | Path | None = None,
        x_provider: XPublishingProvider | None = None,
        telegram_provider: TelegramPublishingProvider | None = None,
    ):
        self.storage_dir = Path(storage_dir or self.DEFAULT_STORAGE_DIR)
        self.x_provider = x_provider or XPublishingProvider()
        self.telegram_provider = telegram_provider or TelegramPublishingProvider()

    @property
    def queue_path(self) -> Path:
        return self.storage_dir / "social_queue.json"

    @property
    def sessions_path(self) -> Path:
        return self.storage_dir / "social_sessions.json"

    @property
    def publish_items_path(self) -> Path:
        return self.storage_dir / "social_publish_items.json"

    @property
    def history_path(self) -> Path:
        return self.storage_dir / "social_history.json"

    @staticmethod
    def platform_options() -> tuple[str, ...]:
        return tuple(platform.value for platform in SocialPlatform)

    def x_account_options(self) -> tuple[str, ...]:
        return self.x_provider.account_names()

    def create_queue_item(
        self,
        *,
        generated_image_id: str,
        generation_library: GenerationLibraryService,
        platform: str = SocialPlatform.X.value,
        creator_notes: str | None = None,
        scheduled_for: str | None = None,
    ) -> SocialQueueItem:
        platform = self.normalize_platform(platform)
        record = generation_library.get(generated_image_id)
        existing = self.find_queue_item(generated_image_id, platform=platform)
        if existing and existing.status != SocialPublishStatus.ARCHIVED.value:
            return existing
        item = SocialQueueItem(
            queue_item_id=new_generation_id("social_queue_item"),
            generated_image_id=record.image_id,
            creator_profile_id=record.creator_profile_id,
            platform=platform,
            scheduled_for=scheduled_for,
            creator_notes=creator_notes,
            generation_metadata={
                "generation_job_id": record.generation_job_id,
                "generation_request_id": record.generation_request_id,
                "generation_result_id": record.generation_result_id,
                "provider_id": record.provider_id,
                "provider_metadata": dict(record.provider_metadata or {}),
                "prompt_metadata": dict(record.prompt_metadata or {}),
                "image_metadata": dict(record.generation_metadata or {}),
            },
            reference_asset_id=record.reference_asset_id,
            creative_mode=record.creative_mode,
            prompt_text=record.prompt_text,
            output_reference=record.output_reference,
        )
        items = list(self.list_queue_items())
        items.insert(0, item)
        self._write_queue(items)
        return item

    def queue_many(
        self,
        *,
        generated_image_ids: Iterable[str],
        generation_library: GenerationLibraryService,
        platform: str,
        creator_notes: str | None = None,
    ) -> tuple[SocialQueueItem, ...]:
        return tuple(
            self.create_queue_item(
                generated_image_id=image_id,
                generation_library=generation_library,
                platform=platform,
                creator_notes=creator_notes,
            )
            for image_id in generated_image_ids
        )

    def remove_queue_item(self, queue_item_id: str) -> SocialQueueItem:
        item = self.get_queue_item(queue_item_id)
        items = [candidate for candidate in self.list_queue_items() if candidate.queue_item_id != queue_item_id]
        self._write_queue(items)
        self._append_history(item, status="removed", message="Removed from Social Queue.")
        return item

    def archive_queue_item(self, queue_item_id: str) -> SocialQueueItem:
        return self._set_status(queue_item_id, SocialPublishStatus.ARCHIVED.value, "Archived Social Queue item.")

    def move_back_to_generation_library(self, queue_item_id: str) -> SocialQueueItem:
        item = self.remove_queue_item(queue_item_id)
        self._append_history(item, status="moved_back", message="Moved back to Generation Library.")
        return item

    def send_to_creator_os(
        self,
        queue_item_id: str,
        *,
        generation_library: GenerationLibraryService,
        generation_engine: GenerationEngineService,
        ingestion_service: GenerationResultIngestionService,
    ):
        item = self.get_queue_item(queue_item_id)
        result = generation_library.add_to_creator_os(
            (item.generated_image_id,),
            generation_engine=generation_engine,
            ingestion_service=ingestion_service,
        )
        if result.success:
            self._append_history(
                item,
                status="sent_to_creator_os",
                message="Generated image sent to Creator OS import.",
                metadata={"imported_asset_ids": result.imported_asset_ids},
            )
        else:
            self._append_history(
                item,
                status="creator_os_import_failed",
                message="Creator OS import failed.",
                metadata={"errors": result.errors},
            )
        return result

    def assign_caption(self, queue_item_id: str, *, caption_id: str) -> SocialQueueItem:
        item = self.get_queue_item(queue_item_id)
        updated = replace(item, caption_id=str(caption_id), updated_at=utc_now())
        items = [
            updated if candidate.queue_item_id == queue_item_id else candidate
            for candidate in self.list_queue_items()
        ]
        self._write_queue(items)
        self._append_history(
            updated,
            status="caption_attached",
            message="Caption Studio result attached to Social Queue item.",
            metadata={"caption_id": caption_id},
        )
        return updated

    def create_session(
        self,
        *,
        creator_profile_id: int,
        queue_item_ids: Iterable[str],
        platform: str,
        title: str = "Social Publishing Session",
    ) -> SocialPublishingSession:
        ids = tuple(str(item_id) for item_id in queue_item_ids if str(item_id))
        if not ids:
            raise ValueError("At least one Social Queue item is required.")
        session = SocialPublishingSession(
            session_id=new_generation_id("social_publishing_session"),
            creator_profile_id=int(creator_profile_id),
            queue_item_ids=ids,
            platform=self.normalize_platform(platform),
            title=title,
        )
        sessions = list(self.list_sessions())
        sessions.insert(0, session)
        self._write_sessions(sessions)
        return session

    def create_publish_item(
        self,
        *,
        queue_item_id: str,
        platform: str,
        caption_id: str | None = None,
        scheduled_for: str | None = None,
    ) -> SocialPublishRequest:
        item = self.get_queue_item(queue_item_id)
        publish_item = SocialPublishRequest(
            publish_request_id=new_generation_id("social_publish_item"),
            queue_item_id=item.queue_item_id,
            platform=self.normalize_platform(platform),
            caption_id=caption_id,
            scheduled_for=scheduled_for,
            metadata={
                "posting_implemented": self.normalize_platform(platform)
                in {SocialPlatform.X.value, SocialPlatform.TELEGRAM.value}
            },
        )
        items = list(self.list_publish_items())
        items.insert(0, publish_item)
        self._write_publish_items(items)
        return publish_item

    def schedule_queue_item(self, queue_item_id: str, *, scheduled_for: str) -> SocialQueueItem:
        item = self.get_queue_item(queue_item_id)
        updated = replace(
            item,
            status=SocialPublishStatus.SCHEDULED.value,
            scheduled_for=str(scheduled_for or ""),
            updated_at=utc_now(),
        )
        self._replace_queue_item(updated)
        self._append_history(
            updated,
            status=SocialPublishStatus.SCHEDULED.value,
            message="Social Queue item scheduled.",
            metadata={"scheduled_for": updated.scheduled_for},
        )
        return updated

    def retry_queue_item(self, queue_item_id: str) -> SocialQueueItem:
        return self._set_status(
            queue_item_id,
            SocialPublishStatus.QUEUED.value,
            "Social Queue item returned to queue for retry.",
        )

    def publish_now(
        self,
        queue_item_id: str,
        *,
        caption_text: str,
        account_name: str | None = None,
        caption_id: str | None = None,
        telegram_post_to: str = "main",
        telegram_cta_enabled: bool = False,
        telegram_cta_label: str = "",
        telegram_cta_url: str = "",
    ) -> SocialQueueItem:
        item = self.get_queue_item(queue_item_id)
        publish_item = self.create_publish_item(
            queue_item_id=item.queue_item_id,
            platform=item.platform,
            caption_id=caption_id or item.caption_id,
        )
        if item.platform not in {SocialPlatform.X.value, SocialPlatform.TELEGRAM.value}:
            updated = replace(item, status=SocialPublishStatus.FAILED.value, updated_at=utc_now())
            self._replace_queue_item(updated)
            self._replace_publish_item(
                replace(
                    publish_item,
                    status=SocialPublishStatus.FAILED.value,
                    metadata={
                        **dict(publish_item.metadata or {}),
                        "error": f"Publishing is only implemented for X and Telegram. Platform: {item.platform}",
                    },
                )
            )
            self._append_history(
                updated,
                status=SocialPublishStatus.FAILED.value,
                message=f"Publishing is only implemented for X and Telegram. Platform: {item.platform}",
                metadata={"caption_id": caption_id or item.caption_id},
            )
            return updated
        try:
            if item.platform == SocialPlatform.TELEGRAM.value:
                result = self.telegram_provider.publish(
                    image_reference=item.output_reference or "",
                    caption=caption_text,
                    post_to=telegram_post_to,
                    cta_enabled=telegram_cta_enabled,
                    cta_label=telegram_cta_label,
                    cta_url=telegram_cta_url,
                )
            else:
                result = self.x_provider.publish(
                    image_reference=item.output_reference or "",
                    caption=caption_text,
                    account_name=account_name,
                )
        except Exception as exc:
            error_metadata = {
                "account_name": account_name,
                "caption_id": caption_id or item.caption_id,
                "telegram_post_to": telegram_post_to,
                "exception_type": exc.__class__.__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            updated = replace(item, status=SocialPublishStatus.FAILED.value, updated_at=utc_now())
            self._replace_queue_item(updated)
            self._replace_publish_item(
                replace(
                    publish_item,
                    status=SocialPublishStatus.FAILED.value,
                    metadata={
                        **dict(publish_item.metadata or {}),
                        **error_metadata,
                    },
                )
            )
            self._append_history(
                updated,
                status=SocialPublishStatus.FAILED.value,
                message=str(exc),
                metadata=error_metadata,
            )
            return updated

        updated = replace(item, status=SocialPublishStatus.POSTED.value, updated_at=utc_now())
        self._replace_queue_item(updated)
        self._replace_publish_item(
            replace(
                publish_item,
                status=SocialPublishStatus.POSTED.value,
                metadata={
                    **dict(publish_item.metadata or {}),
                    "account_name": getattr(result, "account_name", None),
                    "telegram_post_to": getattr(result, "post_to", None),
                    "provider_post_id": result.provider_post_id,
                    "provider_media_id": getattr(result, "provider_media_id", None),
                    "provider_output_url": getattr(result, "provider_output_url", None),
                    "provider_metadata": dict(result.metadata or {}),
                },
            )
        )
        self._append_history(
            updated,
            status=SocialPublishStatus.POSTED.value,
            message=result.message or ("Posted to Telegram." if item.platform == SocialPlatform.TELEGRAM.value else "Posted to X."),
            metadata={
                "account_name": getattr(result, "account_name", None),
                "telegram_post_to": getattr(result, "post_to", None),
                "caption_id": caption_id or item.caption_id,
                "provider_post_id": result.provider_post_id,
                "provider_media_id": getattr(result, "provider_media_id", None),
                "provider_output_url": getattr(result, "provider_output_url", None),
            },
        )
        return updated

    def list_queue_items(
        self,
        *,
        creator_profile_id: int | None = None,
        status: str | None = None,
        platform: str | None = None,
    ) -> tuple[SocialQueueItem, ...]:
        items = tuple(self._queue_item_from_dict(item) for item in self._read_json(self.queue_path, []))
        if creator_profile_id is not None:
            items = tuple(item for item in items if item.creator_profile_id == int(creator_profile_id))
        if status:
            items = tuple(item for item in items if item.status == status)
        if platform:
            normalized = self.normalize_platform(platform)
            items = tuple(item for item in items if item.platform == normalized)
        return items

    def list_sessions(self) -> tuple[SocialPublishingSession, ...]:
        return tuple(self._session_from_dict(item) for item in self._read_json(self.sessions_path, []))

    def list_publish_items(self) -> tuple[SocialPublishRequest, ...]:
        return tuple(self._publish_item_from_dict(item) for item in self._read_json(self.publish_items_path, []))

    def list_history(self) -> tuple[SocialPublishHistory, ...]:
        return tuple(self._history_from_dict(item) for item in self._read_json(self.history_path, []))

    def get_queue_item(self, queue_item_id: str) -> SocialQueueItem:
        for item in self.list_queue_items():
            if item.queue_item_id == queue_item_id:
                return item
        raise KeyError(f"Social Queue item not found: {queue_item_id}")

    def find_queue_item(self, generated_image_id: str, *, platform: str | None = None) -> SocialQueueItem | None:
        normalized = self.normalize_platform(platform) if platform else None
        for item in self.list_queue_items():
            if item.generated_image_id != generated_image_id:
                continue
            if normalized and item.platform != normalized:
                continue
            return item
        return None

    @staticmethod
    def normalize_platform(platform: str | None) -> str:
        candidate = str(platform or SocialPlatform.X.value).strip().lower()
        allowed = {item.value for item in SocialPlatform}
        return candidate if candidate in allowed else SocialPlatform.FUTURE_PROVIDER.value

    def _set_status(self, queue_item_id: str, status: str, message: str) -> SocialQueueItem:
        item = self.get_queue_item(queue_item_id)
        updated = replace(item, status=status, updated_at=utc_now())
        self._replace_queue_item(updated)
        self._append_history(updated, status=status, message=message)
        return updated

    def _replace_queue_item(self, updated: SocialQueueItem) -> None:
        items = [
            updated if candidate.queue_item_id == updated.queue_item_id else candidate
            for candidate in self.list_queue_items()
        ]
        self._write_queue(items)

    def _replace_publish_item(self, updated: SocialPublishRequest) -> None:
        items = [
            updated if candidate.publish_request_id == updated.publish_request_id else candidate
            for candidate in self.list_publish_items()
        ]
        self._write_publish_items(items)

    def _append_history(
        self,
        item: SocialQueueItem,
        *,
        status: str,
        message: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        history = list(self.list_history())
        history.insert(
            0,
            SocialPublishHistory(
                history_id=new_generation_id("social_publish_history"),
                queue_item_id=item.queue_item_id,
                platform=item.platform,
                status=status,
                message=message,
                metadata=dict(metadata or {}),
            ),
        )
        self._write_history(history)

    @staticmethod
    def _queue_item_from_dict(data: Mapping[str, Any]) -> SocialQueueItem:
        return SocialQueueItem(
            queue_item_id=str(data.get("queue_item_id") or ""),
            generated_image_id=str(data.get("generated_image_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            platform=str(data.get("platform") or SocialPlatform.X.value),
            status=str(data.get("status") or SocialPublishStatus.QUEUED.value),
            scheduled_for=data.get("scheduled_for"),
            creator_notes=data.get("creator_notes"),
            caption_id=data.get("caption_id"),
            generation_metadata=data.get("generation_metadata") or {},
            reference_asset_id=data.get("reference_asset_id"),
            creative_mode=data.get("creative_mode"),
            prompt_text=data.get("prompt_text"),
            output_reference=data.get("output_reference"),
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
        )

    @staticmethod
    def _session_from_dict(data: Mapping[str, Any]) -> SocialPublishingSession:
        return SocialPublishingSession(
            session_id=str(data.get("session_id") or ""),
            creator_profile_id=int(data.get("creator_profile_id") or 0),
            queue_item_ids=tuple(data.get("queue_item_ids") or ()),
            platform=str(data.get("platform") or SocialPlatform.X.value),
            title=str(data.get("title") or "Social Publishing Session"),
            status=str(data.get("status") or "draft"),
            created_at=str(data.get("created_at") or ""),
            updated_at=data.get("updated_at"),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _publish_item_from_dict(data: Mapping[str, Any]) -> SocialPublishRequest:
        return SocialPublishRequest(
            publish_request_id=str(data.get("publish_request_id") or ""),
            queue_item_id=str(data.get("queue_item_id") or ""),
            platform=str(data.get("platform") or SocialPlatform.X.value),
            caption_id=data.get("caption_id"),
            scheduled_for=data.get("scheduled_for"),
            status=str(data.get("status") or "draft"),
            created_at=str(data.get("created_at") or ""),
            metadata=data.get("metadata") or {},
        )

    @staticmethod
    def _history_from_dict(data: Mapping[str, Any]) -> SocialPublishHistory:
        return SocialPublishHistory(
            history_id=str(data.get("history_id") or ""),
            queue_item_id=str(data.get("queue_item_id") or ""),
            platform=str(data.get("platform") or SocialPlatform.X.value),
            status=str(data.get("status") or ""),
            message=data.get("message"),
            created_at=str(data.get("created_at") or ""),
            metadata=data.get("metadata") or {},
        )

    def _write_queue(self, items: list[SocialQueueItem]) -> None:
        self._write_json(self.queue_path, [asdict(item) for item in items])

    def _write_sessions(self, sessions: list[SocialPublishingSession]) -> None:
        self._write_json(self.sessions_path, [asdict(session) for session in sessions])

    def _write_publish_items(self, items: list[SocialPublishRequest]) -> None:
        self._write_json(self.publish_items_path, [asdict(item) for item in items])

    def _write_history(self, history: list[SocialPublishHistory]) -> None:
        self._write_json(self.history_path, [asdict(item) for item in history])

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

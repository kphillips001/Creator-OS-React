"""Bounded read model for recent creator Telegram Broadcast activity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Mapping

from app.services.social_publishing_service import SocialPublishingService


class RecentCreatorActivityContextService:
    """Project recent confirmed Broadcast publications without provider work."""

    WINDOW = timedelta(hours=12)
    LIMIT = 3

    def __init__(self, publishing: SocialPublishingService | None = None) -> None:
        self.publishing = publishing or SocialPublishingService()

    def build(
        self,
        *,
        creator_profile_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        observed_at = self._aware(now or datetime.now(UTC))
        boundary = observed_at - self.WINDOW
        queue = {
            item.queue_item_id: item
            for item in self.publishing.list_queue_items(
                creator_profile_id=int(creator_profile_id), platform="telegram"
            )
        }
        candidates: list[tuple[datetime, dict[str, Any]]] = []
        for publication in self.publishing.list_publish_items():
            if publication.platform != "telegram" or publication.status != "posted":
                continue
            item = queue.get(publication.queue_item_id)
            if item is None:
                continue
            metadata = dict(publication.metadata or {})
            if str(metadata.get("telegram_post_to") or "main").lower() != "main":
                continue
            published_at = self._published_at(publication, metadata)
            if published_at is None or not boundary <= published_at <= observed_at:
                continue
            message_id = self._message_id(metadata)
            if message_id is None:
                continue
            candidate = {
                "publishedAt": published_at.isoformat(),
                "telegramMessageId": message_id,
                "caption": self._caption(metadata),
                "generatedImageId": item.generated_image_id or None,
                "assetId": item.reference_asset_id,
                "mediaDescription": self._media_description(item),
            }
            candidates.append((published_at, candidate))
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        selected = [candidate for _, candidate in candidates[: self.LIMIT]]
        return {
            "schemaVersion": "recent_creator_activity_v1",
            "evidenceRole": "CONTEXTUAL_CANDIDATES_ONLY",
            "windowHours": 12,
            "candidateLimit": self.LIMIT,
            "candidates": selected,
        }

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)

    @classmethod
    def _published_at(cls, publication: Any, metadata: Mapping[str, Any]) -> datetime | None:
        provider = metadata.get("provider_metadata")
        provider = provider if isinstance(provider, Mapping) else {}
        response = provider.get("response")
        response = response if isinstance(response, Mapping) else {}
        result = response.get("result")
        result = result if isinstance(result, Mapping) else {}
        provider_date = result.get("date")
        if isinstance(provider_date, (int, float)) and not isinstance(provider_date, bool):
            return datetime.fromtimestamp(provider_date, tz=UTC)
        for value in (
            metadata.get("published_at"),
            metadata.get("provider_published_at"),
            publication.created_at,
        ):
            if not value:
                continue
            try:
                return cls._aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
            except ValueError:
                continue
        return None

    @staticmethod
    def _message_id(metadata: Mapping[str, Any]) -> int | None:
        provider = metadata.get("provider_metadata")
        provider = provider if isinstance(provider, Mapping) else {}
        response = provider.get("response")
        response = response if isinstance(response, Mapping) else {}
        result = response.get("result")
        result = result if isinstance(result, Mapping) else {}
        value = metadata.get("provider_post_id") or result.get("message_id")
        try:
            parsed = int(value)
            return parsed if parsed > 0 else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _caption(metadata: Mapping[str, Any]) -> str | None:
        provider = metadata.get("provider_metadata")
        provider = provider if isinstance(provider, Mapping) else {}
        response = provider.get("response")
        response = response if isinstance(response, Mapping) else {}
        result = response.get("result")
        result = result if isinstance(result, Mapping) else {}
        for value in (result.get("caption"), metadata.get("caption"), metadata.get("primary_caption")):
            text = " ".join(str(value or "").split())
            if text:
                return text[:500]
        return None

    @classmethod
    def _media_description(cls, item: Any) -> str | None:
        generation = dict(item.generation_metadata or {})
        sources = (
            generation.get("image_metadata"),
            generation.get("prompt_metadata"),
            generation.get("provider_metadata"),
        )
        preferred = (
            "description", "short_description", "content_summary",
            "analysis", "approved_prompt", "prompt",
        )
        for source in sources:
            if not isinstance(source, Mapping):
                continue
            for key in preferred:
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    return " ".join(value.split())[:280]
                if isinstance(value, Mapping):
                    for nested in ("description", "summary", "prompt"):
                        text = value.get(nested)
                        if isinstance(text, str) and text.strip():
                            return " ".join(text.split())[:280]
        prompt = " ".join(str(item.prompt_text or "").split())
        return prompt[:280] or None

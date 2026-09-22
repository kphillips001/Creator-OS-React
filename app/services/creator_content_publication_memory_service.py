"""Create permanent, provider-neutral memory for confirmed Broadcast posts."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from app.models.creator_content_publication import CreatorContentPublication
from app.repositories.creator_content_publication_repository import CreatorContentPublicationRepository


class CreatorContentPublicationMemoryService:
    """Snapshot existing intelligence; this service never invokes a provider."""

    def __init__(self, *, repository=None, caption_studio=None,
                 content_intelligence=None, asset_intelligence=None) -> None:
        self.repository = repository or CreatorContentPublicationRepository()
        self.caption_studio = caption_studio
        self.content_intelligence = content_intelligence
        self.asset_intelligence = asset_intelligence

    def record_confirmed_telegram_broadcast(self, *, record, publish_item,
                                             caption: str,
                                             caption_result_id: str | None = None, cta_snapshot: Mapping[str, Any] | None = None):
        metadata = dict(publish_item.metadata or {})
        if publish_item.status != "posted" or publish_item.platform != "telegram":
            raise ValueError("Publication memory requires a confirmed Telegram post.")
        destination = self._text(metadata.get("telegram_post_to")) or "main"
        if destination != "main":
            raise ValueError("Publication memory is limited to the main Broadcast destination.")
        provider = dict(metadata.get("provider_metadata") or {})
        result = dict(dict(provider.get("response") or {}).get("result") or {})
        channel_id = self._integer(dict(result.get("chat") or {}).get("id") or provider.get("chat_id"))
        message_id = self._integer(metadata.get("provider_post_id") or provider.get("message_id") or result.get("message_id"))
        if channel_id is None or message_id is None:
            raise ValueError("Confirmed Telegram channel and message IDs are required.")
        intelligence = self._snapshot(record, caption_result_id)
        published_at = self._published_at(result.get("date"), publish_item.created_at)
        lineage = self._bounded({
            "generationJobId": record.generation_job_id,
            "generationRequestId": record.generation_request_id,
            "generationResultId": record.generation_result_id,
            "promptPlanId": record.prompt_plan_id,
            "generationRecipeId": record.generation_recipe_id,
            "providerId": record.provider_id,
            "photoshootSessionId": record.photoshoot_session_id,
            "photoshootRequestId": record.photoshoot_request_id,
        })
        media = self._bounded({
            "generatedImageId": record.image_id,
            "outputReference": record.output_reference,
            "telegramFileUniqueIds": self._file_ids(result),
        })
        publication = CreatorContentPublication(
            publication_id=str(uuid5(NAMESPACE_URL, f"creator-os:telegram-publication:{destination}:{channel_id}:{message_id}")),
            creator_profile_id=int(record.creator_profile_id), platform="telegram",
            destination=destination, telegram_channel_id=channel_id,
            telegram_message_id=message_id, published_at=published_at,
            generated_image_id=str(record.image_id),
            # reference_asset_id is intentionally never used as the actual output.
            published_asset_id=self._integer(record.imported_asset_id),
            caption_result_id=caption_result_id,
            photoshoot_id=record.photoshoot_session_id or record.photoshoot_request_id,
            generation_lineage=lineage, media_identity=media,
            published_caption=str(caption or ""),
            cta_snapshot=self._bounded(cta_snapshot or {"selectedCtas": tuple(metadata.get("selected_ctas") or ())}),
            provider_identifiers=self._bounded({
                "publishRequestId": publish_item.publish_request_id,
                "telegramChannelId": channel_id, "telegramMessageId": message_id,
                "providerPostId": metadata.get("provider_post_id"),
            }),
            factual_visual_summary=intelligence.get("summary"),
            setting=intelligence.get("setting"), clothing=intelligence.get("clothing"),
            pose=intelligence.get("pose"), activity=intelligence.get("activity"),
            expression=intelligence.get("expression"),
            useful_objects=tuple(intelligence.get("objects") or ()),
            mood=intelligence.get("mood"), themes=tuple(intelligence.get("themes") or ()),
            safety_snapshot=dict(intelligence.get("safety") or {}),
            intelligence_source=intelligence["source"], intelligence_version=intelligence["version"],
            intelligence_provenance=dict(intelligence.get("provenance") or {}),
            search_document=self._search_document(caption, intelligence, lineage, published_at),
        )
        return self.repository.save_successful(publication)

    def _snapshot(self, record, caption_result_id):
        if caption_result_id and self.caption_studio is not None:
            try:
                caption_result = self.caption_studio.get_result(caption_result_id)
                vision = dict(caption_result.formatter_metadata.get("vision") or {})
            except (KeyError, TypeError, ValueError):
                vision = {}
            if vision:
                return self._from_mapping(vision, "CAPTION_STUDIO_GROK_VISION",
                    str(caption_result.formatter_metadata.get("formatter") or "CaptionStudioService"),
                    {"captionResultId": caption_result_id, "provider": "grok"})
        actual_asset_id = self._integer(record.imported_asset_id)
        if actual_asset_id is not None:
            content_service = self.content_intelligence
            if content_service is None:
                from app.services.content_intelligence_service import ContentIntelligenceService
                content_service = ContentIntelligenceService()
            try:
                content = content_service.get_asset_intelligence(actual_asset_id)
            except (KeyError, RuntimeError, TypeError, ValueError):
                content = None
            if content is not None:
                return {"summary": self._text(content.summary),
                    "setting": self._text(content.setting or content.environment),
                    "clothing": self._text(content.outfit or content.clothing),
                    "pose": self._text(content.pose), "activity": self._text(content.activity),
                    "expression": None, "objects": self._texts(content.objects),
                    "mood": self._text(content.mood), "themes": self._texts(content.themes),
                    "safety": self._bounded(dict(content.ai_metadata or {}).get("safety") or {}),
                    "source": "CONTENT_INTELLIGENCE", "version": "content_intelligence_v1",
                    "provenance": {"assetId": actual_asset_id, **self._bounded(content.provenance)}}
            asset_repository = self.asset_intelligence
            if asset_repository is None:
                from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
                asset_repository = AssetIntelligenceRepository()
            try:
                profile = asset_repository.get_profile(actual_asset_id)
            except (KeyError, RuntimeError, TypeError, ValueError):
                profile = None
            if profile is not None:
                return {"summary": self._text(profile.content_summary or profile.detailed_description or profile.short_description),
                    "setting": self._text(profile.setting or profile.environment),
                    "clothing": ", ".join(self._texts(profile.clothing)) or None,
                    "pose": self._text(profile.pose), "activity": self._text(profile.activity),
                    "expression": self._text(profile.expression), "objects": self._texts(profile.objects),
                    "mood": self._text(profile.mood), "themes": self._texts(profile.themes),
                    "safety": self._bounded({"nudityLevel": profile.nudity_level,
                        "explicitContent": profile.explicit_content,
                        "visibleBodyRegions": self._texts(profile.visible_body_regions),
                        "sexualIntensity": profile.sexual_intensity,
                        "safetyClassification": profile.safety_classification,
                        "riskFlags": self._texts(profile.risk_flags)}),
                    "source": "ASSET_INTELLIGENCE", "version": str(profile.schema_version),
                    "provenance": {"assetId": actual_asset_id}}
        fallback = {**dict(record.prompt_metadata or {}), **dict(record.generation_metadata or {})}
        result = self._from_mapping(fallback, "GENERATION_METADATA", "generation_metadata_v1",
                                    {"generatedImageId": record.image_id, "factuality": "UNVERIFIED_FALLBACK"})
        result["summary"] = result.get("summary") or self._text(record.prompt_text)[:1000] or None
        return result

    def _from_mapping(self, value, source, version, provenance):
        return {"summary": self._text(value.get("summary") or value.get("description")),
            "setting": self._text(value.get("setting") or value.get("environment") or value.get("location")),
            "clothing": self._text(value.get("clothing") or value.get("outfit") or value.get("wardrobe")),
            "pose": self._text(value.get("pose") or value.get("body_language")),
            "activity": self._text(value.get("activity")), "expression": self._text(value.get("expression")),
            "objects": self._texts(value.get("objects") or value.get("useful_objects")),
            "mood": self._text(value.get("mood")), "themes": self._texts(value.get("themes") or value.get("tags")),
            "safety": {}, "source": source, "version": version, "provenance": self._bounded(provenance)}

    @classmethod
    def _search_document(cls, caption, intelligence, lineage, published_at):
        values = [caption, intelligence.get("summary"), intelligence.get("setting"), intelligence.get("clothing"),
                  intelligence.get("pose"), intelligence.get("activity"), intelligence.get("expression"),
                  intelligence.get("mood"), *intelligence.get("objects", ()), *intelligence.get("themes", ()),
                  *lineage.values(), published_at.date().isoformat(), published_at.strftime("%B %Y")]
        return " ".join(dict.fromkeys(cls._text(v) for v in values if cls._text(v)))[:10000]

    @staticmethod
    def _file_ids(result):
        return tuple(dict.fromkeys(str(v.get("file_unique_id")) for v in (result.get("photo") or ())
                                   if isinstance(v, Mapping) and v.get("file_unique_id")))

    @staticmethod
    def _published_at(epoch, fallback):
        if isinstance(epoch, (int, float)):
            return datetime.fromtimestamp(epoch, tz=UTC)
        try:
            value = datetime.fromisoformat(str(fallback).replace("Z", "+00:00"))
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return datetime.now(UTC)

    @staticmethod
    def _text(value): return " ".join(str(value or "").split()).strip()

    @classmethod
    def _texts(cls, value):
        if isinstance(value, str): return (cls._text(value),) if cls._text(value) else ()
        if not isinstance(value, (list, tuple, set)): return ()
        return tuple(dict.fromkeys(cls._text(v) for v in value if cls._text(v)))[:50]

    @staticmethod
    def _integer(value):
        try: return int(value) if value is not None and str(value).strip() else None
        except (TypeError, ValueError): return None

    @classmethod
    def _bounded(cls, value):
        if not isinstance(value, Mapping): return {}
        result = {}
        for key, item in list(value.items())[:100]:
            if item is None or item == "" or item == () or item == []: continue
            if isinstance(item, Mapping): result[str(key)] = cls._bounded(item)
            elif isinstance(item, (list, tuple, set)): result[str(key)] = tuple(str(v)[:500] for v in list(item)[:50])
            else: result[str(key)] = item if isinstance(item, (bool, int, float)) else str(item)[:2000]
        return result

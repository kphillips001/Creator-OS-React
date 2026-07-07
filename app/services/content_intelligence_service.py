"""Canonical Content Intelligence boundary for Creator OS.

ContentIntelligenceService owns AI-generated content understanding. It reuses
the existing AssetUnderstandingService and does not perform Product Strategy,
Sales Strategy, Publishing, Telegram Commerce, or Creator Intent work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from app.models.content_intelligence import (
    ContentIntelligence,
    ContentRecommendation,
)


class ContentIntelligenceService:
    """Expose reusable AI-generated content understanding."""

    def __init__(
        self,
        *,
        asset_understanding_service: Any | None = None,
    ) -> None:
        self._asset_understanding = asset_understanding_service

    @property
    def asset_understanding(self) -> Any:
        if self._asset_understanding is None:
            from app.services.asset_understanding_service import (
                AssetUnderstandingService,
            )

            self._asset_understanding = AssetUnderstandingService()
        return self._asset_understanding

    def get_asset_intelligence(self, asset_id: int) -> ContentIntelligence | None:
        """Load existing AI understanding for an Asset without re-analysis."""

        getter = getattr(self.asset_understanding, "get_understanding", None)
        if not callable(getter):
            return None
        understanding = getter(asset_id)
        if understanding is None:
            return None
        return self.build_from_understanding(understanding)

    def build_from_asset(self, asset: Any) -> ContentIntelligence:
        """Normalize existing stored AI outputs from an Asset-like object."""

        understanding = self.build_asset_understanding(asset)
        return self.build_from_understanding(understanding)

    def build_asset_understanding(self, asset: Any) -> Any:
        """Compatibility helper returning the existing AssetUnderstanding."""

        builder = getattr(self.asset_understanding, "build_from_asset", None)
        if not callable(builder):
            raise TypeError("asset_understanding_service must build_from_asset")
        return builder(asset)

    def get_asset_understanding(self, asset_id: int) -> Any | None:
        """Compatibility helper returning the existing AssetUnderstanding."""

        record = self.get_asset_intelligence(asset_id)
        return record.asset_understanding if record is not None else None

    def build_from_understanding(self, understanding: Any) -> ContentIntelligence:
        visual = self._read(understanding, "visual")
        media = self._read(understanding, "media")
        classification = self._read(understanding, "classification")
        metadata = self._read(understanding, "metadata")
        provenance = self._read(understanding, "provenance")
        readiness = self._read(understanding, "readiness")
        gpt_vision_result = self._mapping(
            self._read(visual, "gpt_vision_result")
        )
        setting = self._text(self._read(visual, "setting"))
        outfit = self._text(self._read(visual, "outfit"))
        activity = self._text(self._read(visual, "activity"))
        themes = self._text_tuple(self._read(visual, "detected_themes"))
        tags = self._text_tuple(self._read(visual, "suggested_tags"))
        objects = self._text_tuple(self._read(visual, "objects"))
        environment = self._first_text(
            setting,
            self._read(gpt_vision_result, "environment"),
            self._read(gpt_vision_result, "location"),
            self._read(gpt_vision_result, "scene"),
            self._read(gpt_vision_result, "place"),
            self._read(gpt_vision_result, "background"),
        )
        activities = self._text_values(
            activity,
            self._read(gpt_vision_result, "activities"),
        )
        clothing = self._first_text(
            outfit,
            self._read(gpt_vision_result, "clothing"),
            self._read(gpt_vision_result, "wardrobe"),
        )
        keywords = self._text_values(
            tags,
            themes,
            objects,
            self._read(gpt_vision_result, "keywords"),
            self._read(gpt_vision_result, "suggested_keywords"),
        )

        technical_quality = self._technical_quality(media, readiness)
        content = ContentIntelligence(
            asset_id=self._asset_id(understanding),
            asset_understanding=understanding,
            summary=self._text(self._read(visual, "summary")),
            classification=self._text(
                self._read(classification, "final_classification")
                or self._read(classification, "classification")
            ),
            confidence=self._float_or_none(
                self._read(classification, "confidence")
            ),
            themes=themes,
            tags=tags,
            mood=self._text(self._read(visual, "mood")),
            setting=setting,
            outfit=outfit,
            pose=self._text(self._read(visual, "pose")),
            activity=activity,
            objects=objects,
            environment=environment,
            activities=activities,
            clothing=clothing,
            keywords=keywords,
            technical_quality=technical_quality,
            media_metadata=self._media_metadata(media, metadata),
            ai_metadata={
                "gpt_vision_result": dict(gpt_vision_result),
                "classification_result": dict(
                    self._mapping(
                        self._read(classification, "classification_result")
                    )
                ),
            },
            technical_metadata=self._technical_metadata(media, metadata),
            provenance=self._object_public_mapping(provenance),
            readiness=self._object_public_mapping(readiness),
            ownership={
                "content_intelligence_owner": "ContentIntelligenceService",
                "content_recommendation_owner": "ContentIntelligenceService",
                "asset_understanding_owner": "AssetUnderstandingService",
                "creator_intent_owner": "Creator Intent",
                "experience_owner": "ExperienceService",
                "product_strategy_owner": "not_content_intelligence",
                "sales_strategy_owner": "not_content_intelligence",
            },
        )
        cover = self._suggest_cover_image(content)
        return replace(
            content,
            suggested_cover_image=cover,
            recommendations={"suggested_cover_image": cover},
        )

    @classmethod
    def _asset_id(cls, understanding: Any) -> int | None:
        identity = cls._read(understanding, "identity")
        asset_id = (
            cls._read(identity, "asset_id")
            or cls._read(understanding, "asset_id")
        )
        try:
            return int(asset_id)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _media_metadata(cls, media: Any, metadata: Any) -> Mapping[str, Any]:
        existing = cls._mapping(cls._read(metadata, "media_metadata"))
        values = dict(existing)
        for key in (
            "media_type",
            "local_vault_path",
            "legacy_file_path",
            "runtime_path",
            "runtime_source",
            "runtime_exists",
            "mime_type",
            "file_extension",
        ):
            value = cls._read(media, key)
            if value is not None:
                values[key] = value
        return values

    @classmethod
    def _technical_metadata(cls, media: Any, metadata: Any) -> Mapping[str, Any]:
        values: dict[str, Any] = {}
        for key in (
            "size_bytes",
            "width",
            "height",
            "aspect_ratio",
            "duration_seconds",
            "codec",
            "frame_rate",
            "video_analysis_status",
        ):
            value = cls._read(media, key)
            if value is not None:
                values[key] = value
        for key in (
            "duplicate_detection_status",
            "similarity_group_id",
            "perceptual_hash",
            "checksum",
        ):
            value = cls._read(metadata, key)
            if value is not None:
                values[key] = value
        return values

    @classmethod
    def _technical_quality(
        cls,
        media: Any,
        readiness: Any,
    ) -> Mapping[str, Any]:
        values: dict[str, Any] = {}
        for key in (
            "has_runtime_media",
            "has_local_vault_media",
            "has_visual_summary",
            "has_classification",
            "needs_review",
            "review_reasons",
        ):
            value = cls._read(readiness, key)
            if value is not None:
                values[key] = value
        for key in (
            "runtime_exists",
            "width",
            "height",
            "aspect_ratio",
            "size_bytes",
            "duration_seconds",
            "video_analysis_status",
        ):
            value = cls._read(media, key)
            if value is not None:
                values[key] = value
        return values

    @classmethod
    def _object_public_mapping(cls, value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if value is None:
            return {}
        result = {}
        for key in dir(value):
            if key.startswith("_"):
                continue
            item = getattr(value, key)
            if callable(item):
                continue
            result[key] = item
        return result

    @classmethod
    def _suggest_cover_image(
        cls,
        content: ContentIntelligence,
    ) -> ContentRecommendation:
        """Recommend cover-image suitability from existing intelligence."""

        confidence = 0.0
        rationale: list[str] = []
        media_type = cls._normalized_text(
            content.media_metadata.get("media_type")
        )

        if media_type == "image":
            confidence += 0.25
            rationale.append("Asset media type is image.")
        elif media_type:
            rationale.append(
                f"Asset media type is {media_type}, not image."
            )
        else:
            rationale.append("Asset media type is unavailable.")

        if content.technical_quality.get("has_runtime_media"):
            confidence += 0.2
            rationale.append("Runtime media is available.")
        elif content.media_metadata.get("runtime_exists"):
            confidence += 0.2
            rationale.append("Runtime media exists.")
        else:
            rationale.append("Runtime media availability is not confirmed.")

        if content.summary:
            confidence += 0.15
            rationale.append("Visual summary is available.")
        if content.classification:
            confidence += 0.1
            rationale.append("Classification is available.")
        if content.confidence is not None:
            confidence += min(max(content.confidence, 0.0), 1.0) * 0.15
            rationale.append("Classification confidence is available.")
        if content.environment or content.mood or content.keywords:
            confidence += 0.1
            rationale.append("Reusable visual metadata is available.")
        if content.technical_quality.get("width") and content.technical_quality.get(
            "height"
        ):
            confidence += 0.05
            rationale.append("Image dimensions are available.")

        if content.technical_quality.get("needs_review"):
            confidence = min(confidence, 0.45)
            rationale.append("Asset is marked as needing review.")

        confidence = round(min(confidence, 1.0), 2)
        recommended = media_type == "image" and confidence >= 0.65
        evidence = {
            "media_type": media_type,
            "has_runtime_media": content.technical_quality.get(
                "has_runtime_media"
            ),
            "runtime_exists": content.media_metadata.get("runtime_exists"),
            "has_visual_summary": bool(content.summary),
            "has_classification": bool(content.classification),
            "needs_review": content.technical_quality.get("needs_review"),
        }
        return ContentRecommendation(
            recommendation_type="suggested_cover_image",
            asset_id=content.asset_id if recommended else None,
            recommended=recommended,
            confidence=confidence,
            rationale=tuple(rationale),
            evidence=evidence,
        )

    @staticmethod
    def _read(source: Any, key: str) -> Any:
        if source is None:
            return None
        if isinstance(source, Mapping):
            return source.get(key)
        return getattr(source, key, None)

    @staticmethod
    def _normalized_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().casefold()
        return text or None

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _text_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        try:
            return tuple(str(item) for item in value if str(item).strip())
        except TypeError:
            return (str(value),)

    @classmethod
    def _text_values(cls, *values: Any) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            for item in cls._iter_text_values(value):
                normalized = item.strip()
                key = normalized.casefold()
                if normalized and key not in seen:
                    seen.add(key)
                    result.append(normalized)
        return tuple(result)

    @classmethod
    def _iter_text_values(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,) if value.strip() else ()
        if isinstance(value, Mapping):
            return cls._text_values(value.values())
        try:
            return tuple(
                str(item)
                for item in value
                if item is not None and str(item).strip()
            )
        except TypeError:
            text = str(value).strip()
            return (text,) if text else ()

    @classmethod
    def _first_text(cls, *values: Any) -> str | None:
        for value in values:
            candidates = cls._text_values(value)
            if candidates:
                return candidates[0]
        return None

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

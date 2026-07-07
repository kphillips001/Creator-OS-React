"""Recommend how imported Assets relate as Experiences."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
import re
from typing import Any, TYPE_CHECKING

from app.models.experience import ExperienceType
from app.models.experience_intelligence import (
    ExperienceIntelligenceEvidence,
    ExperienceRecommendation,
)

if TYPE_CHECKING:
    from app.services.asset_understanding_service import AssetUnderstandingService


class ExperienceIntelligenceService:
    """Recommend Experience grouping from Content Intelligence inputs."""

    STORY_MARKERS = {
        "story",
        "sequence",
        "series",
        "part",
        "chapter",
        "progression",
        "before after",
        "behind the scenes",
    }

    def __init__(
        self,
        *,
        asset_understanding_service: "AssetUnderstandingService | None" = None,
    ):
        self._asset_understanding = asset_understanding_service

    @property
    def asset_understanding(self):
        if self._asset_understanding is None:
            from app.services.asset_understanding_service import (
                AssetUnderstandingService,
            )

            self._asset_understanding = AssetUnderstandingService()
        return self._asset_understanding

    def recommend_for_asset_ids(
        self,
        asset_ids: Iterable[int],
        *,
        package_type: str | None = None,
        import_session_id: str | None = None,
    ) -> ExperienceRecommendation | None:
        understandings = []
        for asset_id in asset_ids:
            understanding = self.asset_understanding.get_understanding(
                int(asset_id)
            )
            if understanding is not None:
                understandings.append(understanding)
        if not understandings:
            return None
        return self.recommend_for_understandings(
            understandings,
            package_type=package_type,
            import_session_id=import_session_id,
        )

    def recommend_for_understandings(
        self,
        understandings: Iterable[Any],
        *,
        package_type: str | None = None,
        import_session_id: str | None = None,
    ) -> ExperienceRecommendation | None:
        items = tuple(
            self._content_intelligence_view(item)
            for item in understandings
            if item is not None
        )
        if not items:
            return None

        asset_ids = tuple(item.identity.asset_id for item in items)
        if len(items) == 1:
            item = items[0]
            profile = self._intelligence_profile(
                items,
                package_type=package_type,
                import_session_id=import_session_id,
                photoshoot_score=None,
                story_score=None,
                evidence=(
                    ExperienceIntelligenceEvidence(
                        reason="single_asset_import",
                        detail="One imported Asset maps to a standalone Experience.",
                        weight=100,
                    ),
                ),
            )
            return ExperienceRecommendation(
                experience_type=ExperienceType.STANDALONE,
                asset_ids=asset_ids,
                suggested_name=self._standalone_name(item),
                suggested_summary=item.visual.summary,
                suggested_cover_asset_id=item.identity.asset_id,
                suggested_themes=profile["suggested_themes"],
                suggested_keywords=profile["suggested_keywords"],
                mood=profile["mood"],
                setting=profile["setting"],
                visual_continuity=profile["visual_continuity"],
                story_progression=profile["story_progression"],
                technical_continuity=profile["technical_continuity"],
                intelligence_metadata=profile["intelligence_metadata"],
                intelligence_provenance=profile["intelligence_provenance"],
                confidence=1.0,
                evidence=profile["evidence"],
                metadata={
                    "source": "experience_intelligence",
                    "package_type": package_type,
                    "import_session_id": import_session_id,
                    "experience_intelligence": profile["metadata_projection"],
                },
            )

        scores = self._collection_scores(
            items,
            package_type=package_type,
            import_session_id=import_session_id,
        )
        recommendation_type = (
            ExperienceType.STORY
            if scores["story"] > scores["photoshoot"]
            else ExperienceType.PHOTOSHOOT
        )
        confidence = min(
            0.95,
            max(scores["photoshoot"], scores["story"]) / 100,
        )
        evidence = tuple(scores["evidence"])
        cover_asset_id = self._cover_asset_id(items)
        profile = self._intelligence_profile(
            items,
            package_type=package_type,
            import_session_id=import_session_id,
            photoshoot_score=scores["photoshoot"],
            story_score=scores["story"],
            evidence=evidence,
        )

        return ExperienceRecommendation(
            experience_type=recommendation_type,
            asset_ids=asset_ids,
            suggested_name=self._collection_name(items, recommendation_type),
            suggested_summary=self._collection_summary(
                items,
                recommendation_type,
            ),
            suggested_cover_asset_id=cover_asset_id,
            suggested_themes=profile["suggested_themes"],
            suggested_keywords=profile["suggested_keywords"],
            mood=profile["mood"],
            setting=profile["setting"],
            visual_continuity=profile["visual_continuity"],
            story_progression=profile["story_progression"],
            technical_continuity=profile["technical_continuity"],
            intelligence_metadata=profile["intelligence_metadata"],
            intelligence_provenance=profile["intelligence_provenance"],
            confidence=round(confidence, 2),
            evidence=evidence,
            metadata={
                "source": "experience_intelligence",
                "package_type": package_type,
                "import_session_id": import_session_id,
                "photoshoot_score": scores["photoshoot"],
                "story_score": scores["story"],
                "experience_intelligence": profile["metadata_projection"],
            },
        )

    def _collection_scores(
        self,
        items: tuple[Any, ...],
        *,
        package_type: str | None,
        import_session_id: str | None,
    ) -> dict[str, Any]:
        photoshoot = 0
        story = 0
        evidence: list[ExperienceIntelligenceEvidence] = []
        normalized_package = (package_type or "").lower()

        if import_session_id:
            photoshoot += 25
            story += 15
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="import_session",
                    detail=import_session_id,
                    weight=25,
                )
            )

        if normalized_package in {"photo_set", "photoset", "photoshoot"}:
            photoshoot += 70
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="explicit_photo_set_import",
                    detail=normalized_package,
                    weight=70,
                )
            )
        elif normalized_package == "story":
            story += 70
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="explicit_story_import",
                    detail=normalized_package,
                    weight=70,
                )
            )
        else:
            photoshoot += 20
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="multi_asset_import",
                    detail=f"{len(items)} assets imported together.",
                    weight=20,
                )
            )

        media_types = {item.media.media_type for item in items}
        if media_types == {"image"}:
            photoshoot += 20
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="all_images",
                    detail="All candidate Assets are images.",
                    weight=20,
                )
            )
        elif len(media_types) > 1:
            story += 25
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="mixed_media",
                    detail=", ".join(sorted(media_types)),
                    weight=25,
                )
            )

        timestamp_evidence = self._timestamp_evidence(items)
        if timestamp_evidence:
            photoshoot += timestamp_evidence.weight
            story += max(5, timestamp_evidence.weight // 2)
            evidence.append(timestamp_evidence)

        filename_evidence = self._filename_sequence_evidence(items)
        if filename_evidence:
            story += filename_evidence.weight
            photoshoot += max(5, filename_evidence.weight // 2)
            evidence.append(filename_evidence)

        similarity_evidence = self._similarity_evidence(items)
        if similarity_evidence:
            photoshoot += similarity_evidence.weight
            evidence.append(similarity_evidence)

        technical_evidence = self._technical_metadata_evidence(items)
        if technical_evidence:
            photoshoot += technical_evidence.weight
            story += max(5, technical_evidence.weight // 3)
            evidence.append(technical_evidence)

        shared_themes = self._shared_terms(
            item.visual.detected_themes for item in items
        )
        shared_tags = self._shared_terms(
            item.visual.suggested_tags for item in items
        )
        if shared_themes:
            photoshoot += 15
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="shared_themes",
                    detail=", ".join(shared_themes[:5]),
                    weight=15,
                )
            )
        if shared_tags:
            photoshoot += 15
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="shared_tags",
                    detail=", ".join(shared_tags[:5]),
                    weight=15,
                )
            )

        common_setting = self._most_common_text(
            item.visual.setting for item in items
        )
        if common_setting:
            photoshoot += 10
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="shared_setting",
                    detail=common_setting,
                    weight=10,
                )
            )

        common_outfit = self._most_common_text(
            item.visual.outfit for item in items
        )
        if common_outfit:
            photoshoot += 10
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="shared_outfit",
                    detail=common_outfit,
                    weight=10,
                )
            )

        visual_continuity = self._visual_continuity_evidence(
            shared_themes=shared_themes,
            shared_tags=shared_tags,
            common_setting=common_setting,
            common_outfit=common_outfit,
        )
        if visual_continuity:
            photoshoot += visual_continuity.weight
            evidence.append(visual_continuity)

        story_markers = self._story_markers(items)
        if story_markers:
            story += 35
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="story_markers",
                    detail=", ".join(story_markers[:5]),
                    weight=35,
                )
            )

        varied_activities = self._distinct_text_count(
            item.visual.activity for item in items
        )
        if varied_activities >= 3:
            story += 15
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="story_progression",
                    detail=f"{varied_activities} distinct activities.",
                    weight=15,
                )
            )

        if filename_evidence and timestamp_evidence and varied_activities >= 2:
            story += 20
            evidence.append(
                ExperienceIntelligenceEvidence(
                    reason="ordered_story_progression",
                    detail="Filename order, timestamp proximity, and activity progression align.",
                    weight=20,
                )
            )

        return {
            "photoshoot": photoshoot,
            "story": story,
            "evidence": evidence,
        }

    def _intelligence_profile(
        self,
        items: tuple[Any, ...],
        *,
        package_type: str | None,
        import_session_id: str | None,
        photoshoot_score: int | None,
        story_score: int | None,
        evidence: tuple[ExperienceIntelligenceEvidence, ...],
    ) -> dict[str, Any]:
        suggested_themes = self._dedupe_terms(
            theme
            for item in items
            for theme in getattr(getattr(item, "visual", None), "detected_themes", ())
        )
        suggested_tags = self._dedupe_terms(
            tag
            for item in items
            for tag in getattr(getattr(item, "visual", None), "suggested_tags", ())
        )
        mood = self._most_common_optional(
            getattr(getattr(item, "visual", None), "mood", None)
            for item in items
        )
        setting = self._most_common_optional(
            getattr(getattr(item, "visual", None), "setting", None)
            for item in items
        )
        suggested_keywords = self._experience_keywords(
            items,
            themes=suggested_themes,
            tags=suggested_tags,
            mood=mood,
            setting=setting,
        )
        visual_continuity = self._visual_continuity_profile(
            items,
            themes=suggested_themes,
            tags=suggested_tags,
            mood=mood,
            setting=setting,
        )
        story_progression = self._story_progression_profile(items)
        technical_continuity = self._technical_continuity_profile(items)
        intelligence_metadata = {
            "asset_count": len(items),
            "package_type": package_type,
            "import_session_id": import_session_id,
            "media_types": tuple(
                sorted(
                    {
                        str(getattr(getattr(item, "media", None), "media_type", "unknown"))
                        for item in items
                    }
                )
            ),
            "photoshoot_score": photoshoot_score,
            "story_score": story_score,
        }
        intelligence_provenance = {
            "source": "experience_intelligence_service",
            "inputs": ("content_intelligence", "asset_understanding"),
            "new_ai_analysis": False,
            "evidence_reasons": tuple(item.reason for item in evidence),
        }
        metadata_projection = {
            "suggested_themes": suggested_themes,
            "suggested_keywords": suggested_keywords,
            "mood": mood,
            "setting": setting,
            "visual_continuity": visual_continuity,
            "story_progression": story_progression,
            "technical_continuity": technical_continuity,
            "intelligence_metadata": intelligence_metadata,
            "intelligence_provenance": intelligence_provenance,
        }
        return {
            "suggested_themes": suggested_themes,
            "suggested_keywords": suggested_keywords,
            "mood": mood,
            "setting": setting,
            "visual_continuity": visual_continuity,
            "story_progression": story_progression,
            "technical_continuity": technical_continuity,
            "intelligence_metadata": intelligence_metadata,
            "intelligence_provenance": intelligence_provenance,
            "metadata_projection": metadata_projection,
            "evidence": evidence,
        }

    def _experience_keywords(
        self,
        items: tuple[Any, ...],
        *,
        themes: tuple[str, ...],
        tags: tuple[str, ...],
        mood: str | None,
        setting: str | None,
    ) -> tuple[str, ...]:
        values: list[Any] = [*tags, *themes, mood, setting]
        for item in items:
            visual = getattr(item, "visual", None)
            classification = getattr(item, "classification", None)
            values.extend(
                (
                    getattr(visual, "outfit", None),
                    getattr(visual, "activity", None),
                    getattr(classification, "final_classification", None),
                )
            )
        return self._dedupe_terms(values)

    def _visual_continuity_profile(
        self,
        items: tuple[Any, ...],
        *,
        themes: tuple[str, ...],
        tags: tuple[str, ...],
        mood: str | None,
        setting: str | None,
    ) -> dict[str, Any]:
        shared_themes = self._shared_terms(
            item.visual.detected_themes for item in items
        )
        shared_tags = self._shared_terms(
            item.visual.suggested_tags for item in items
        )
        common_outfit = self._most_common_text(
            item.visual.outfit for item in items
        )
        common_activity = self._most_common_text(
            item.visual.activity for item in items
        )
        return {
            "shared_themes": shared_themes,
            "shared_tags": shared_tags,
            "mood": mood,
            "setting": setting,
            "outfit": common_outfit,
            "activity": common_activity,
            "signals": tuple(
                signal
                for signal, present in (
                    ("themes", bool(shared_themes or themes)),
                    ("tags", bool(shared_tags or tags)),
                    ("mood", bool(mood)),
                    ("setting", bool(setting)),
                    ("outfit", bool(common_outfit)),
                    ("activity", bool(common_activity)),
                )
                if present
            ),
        }

    def _story_progression_profile(
        self,
        items: tuple[Any, ...],
    ) -> dict[str, Any]:
        activities = self._dedupe_terms(
            getattr(getattr(item, "visual", None), "activity", None)
            for item in items
        )
        filenames = tuple(
            filename
            for filename in (self._filename(item) for item in items)
            if filename
        )
        return {
            "filename_sequence": self._filename_sequence_evidence(items) is not None,
            "timestamp_progression": self._timestamp_evidence(items) is not None,
            "activity_progression": len(activities) >= 2,
            "activities": activities,
            "story_markers": self._story_markers(items),
            "ordered_filenames": filenames,
        }

    def _technical_continuity_profile(
        self,
        items: tuple[Any, ...],
    ) -> dict[str, Any]:
        durations = tuple(
            value
            for value in (
                self._float_or_none(self._media_value(item, "duration_seconds"))
                for item in items
            )
            if value is not None
        )
        return {
            "media_types": self._dedupe_terms(
                self._media_value(item, "media_type") for item in items
            ),
            "mime_types": self._dedupe_terms(
                self._media_value(item, "mime_type") for item in items
            ),
            "dimensions": self._dedupe_terms(
                self._dimension_key(item) for item in items
            ),
            "duration_seconds": durations,
            "similarity_groups": self._dedupe_terms(
                self._metadata_value(item, "similarity_group_id") for item in items
            ),
            "perceptual_hashes": self._dedupe_terms(
                self._metadata_value(item, "perceptual_hash") for item in items
            ),
            "checksums": self._dedupe_terms(
                self._metadata_value(item, "checksum") for item in items
            ),
        }

    @classmethod
    def _timestamp_evidence(
        cls,
        items: tuple[Any, ...],
    ) -> ExperienceIntelligenceEvidence | None:
        timestamps = [
            timestamp
            for timestamp in (cls._created_at(item) for item in items)
            if timestamp is not None
        ]
        if len(timestamps) < 2:
            return None
        span_seconds = (max(timestamps) - min(timestamps)).total_seconds()
        if span_seconds <= 15 * 60:
            return ExperienceIntelligenceEvidence(
                reason="timestamp_proximity",
                detail=f"{len(timestamps)} assets imported within {int(span_seconds)} seconds.",
                weight=20,
            )
        if cls._monotonic_timestamps(timestamps):
            return ExperienceIntelligenceEvidence(
                reason="timestamp_progression",
                detail=f"{len(timestamps)} assets have ordered timestamps.",
                weight=15,
            )
        return None

    @classmethod
    def _filename_sequence_evidence(
        cls,
        items: tuple[Any, ...],
    ) -> ExperienceIntelligenceEvidence | None:
        names = [cls._filename(item) for item in items]
        parsed = [cls._filename_sequence_parts(name) for name in names if name]
        if len(parsed) < 2:
            return None
        prefixes = {prefix for prefix, _ in parsed if prefix}
        numbers = [number for _, number in parsed if number is not None]
        if len(numbers) < 2:
            return None
        ordered = numbers == sorted(numbers)
        adjacent = max(numbers) - min(numbers) <= len(numbers) + 2
        if ordered and adjacent:
            detail = ", ".join(name for name in names if name)
            return ExperienceIntelligenceEvidence(
                reason="filename_sequence",
                detail=detail,
                weight=25,
            )
        if len(prefixes) == 1:
            return ExperienceIntelligenceEvidence(
                reason="filename_pattern",
                detail=next(iter(prefixes)),
                weight=15,
            )
        return None

    @classmethod
    def _similarity_evidence(
        cls,
        items: tuple[Any, ...],
    ) -> ExperienceIntelligenceEvidence | None:
        similarity_groups = cls._shared_non_empty(
            cls._metadata_value(item, "similarity_group_id") for item in items
        )
        if similarity_groups:
            return ExperienceIntelligenceEvidence(
                reason="similarity_match",
                detail=", ".join(similarity_groups[:3]),
                weight=25,
            )
        hashes = cls._shared_non_empty(
            cls._metadata_value(item, "perceptual_hash")
            or cls._metadata_value(item, "checksum")
            for item in items
        )
        if hashes:
            return ExperienceIntelligenceEvidence(
                reason="hash_similarity",
                detail=f"{len(hashes)} shared hash/checksum value(s).",
                weight=20,
            )
        return None

    @classmethod
    def _technical_metadata_evidence(
        cls,
        items: tuple[Any, ...],
    ) -> ExperienceIntelligenceEvidence | None:
        mime_types = cls._shared_non_empty(cls._media_value(item, "mime_type") for item in items)
        dimensions = cls._shared_non_empty(
            cls._dimension_key(item) for item in items
        )
        durations = [
            cls._float_or_none(cls._media_value(item, "duration_seconds"))
            for item in items
        ]
        durations = [value for value in durations if value is not None]
        similar_duration = (
            len(durations) >= 2 and max(durations) - min(durations) <= 2.0
        )
        details = []
        if mime_types:
            details.append(f"mime={', '.join(mime_types[:3])}")
        if dimensions:
            details.append(f"dimensions={', '.join(dimensions[:3])}")
        if similar_duration:
            details.append("similar_duration")
        if not details:
            return None
        return ExperienceIntelligenceEvidence(
            reason="technical_metadata",
            detail="; ".join(details),
            weight=10,
        )

    @staticmethod
    def _visual_continuity_evidence(
        *,
        shared_themes: tuple[str, ...],
        shared_tags: tuple[str, ...],
        common_setting: str | None,
        common_outfit: str | None,
    ) -> ExperienceIntelligenceEvidence | None:
        signals = []
        if shared_themes:
            signals.append("themes")
        if shared_tags:
            signals.append("tags")
        if common_setting:
            signals.append("setting")
        if common_outfit:
            signals.append("outfit")
        if len(signals) < 2:
            return None
        return ExperienceIntelligenceEvidence(
            reason="visual_continuity",
            detail=", ".join(signals),
            weight=15,
        )

    @staticmethod
    def _shared_terms(term_groups: Iterable[Iterable[str]]) -> tuple[str, ...]:
        groups = [
            {str(term).strip().lower() for term in group if str(term).strip()}
            for group in term_groups
        ]
        if not groups:
            return ()
        shared = set.intersection(*groups)
        return tuple(sorted(shared))

    @staticmethod
    def _dedupe_terms(values: Iterable[Any]) -> tuple[str, ...]:
        seen = set()
        result = []
        for value in values:
            if value is None:
                continue
            clean = str(value).strip()
            if not clean:
                continue
            key = clean.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(clean)
        return tuple(result)

    @staticmethod
    def _most_common_optional(values: Iterable[Any]) -> str | None:
        normalized = [
            str(value).strip()
            for value in values
            if value is not None and str(value).strip()
        ]
        if not normalized:
            return None
        value, _ = Counter(value.lower() for value in normalized).most_common(1)[0]
        for candidate in normalized:
            if candidate.lower() == value:
                return candidate
        return None

    @staticmethod
    def _most_common_text(values: Iterable[str | None]) -> str | None:
        normalized = [
            str(value).strip().lower()
            for value in values
            if value and str(value).strip()
        ]
        if len(normalized) < 2:
            return None
        value, count = Counter(normalized).most_common(1)[0]
        return value if count >= 2 else None

    @staticmethod
    def _distinct_text_count(values: Iterable[str | None]) -> int:
        return len(
            {
                str(value).strip().lower()
                for value in values
                if value and str(value).strip()
            }
        )

    @classmethod
    def _story_markers(cls, items: tuple[Any, ...]) -> tuple[str, ...]:
        values = []
        for item in items:
            values.extend(item.visual.detected_themes)
            values.extend(item.visual.suggested_tags)
            if item.visual.summary:
                values.append(item.visual.summary)
        text = " ".join(str(value).lower() for value in values)
        return tuple(marker for marker in cls.STORY_MARKERS if marker in text)

    @staticmethod
    def _created_at(item: Any) -> datetime | None:
        value = getattr(getattr(item, "identity", None), "created_at", None)
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _monotonic_timestamps(values: list[datetime]) -> bool:
        return values == sorted(values) or values == sorted(values, reverse=True)

    @staticmethod
    def _filename(item: Any) -> str | None:
        identity = getattr(item, "identity", None)
        return (
            getattr(identity, "original_filename", None)
            or getattr(identity, "file_name", None)
        )

    @staticmethod
    def _filename_sequence_parts(name: str) -> tuple[str, int | None]:
        stem = Path(str(name)).stem.lower()
        match = re.search(r"^(.*?)(\d+)$", stem)
        if not match:
            match = re.search(r"^(.*?)[\s_-]+(\d+)(?:[\s_-].*)?$", stem)
        if not match:
            return stem, None
        prefix = re.sub(r"[\s_-]+$", "", match.group(1))
        return prefix, int(match.group(2))

    @staticmethod
    def _metadata_value(item: Any, name: str) -> Any:
        metadata = getattr(item, "metadata", None)
        return getattr(metadata, name, None)

    @staticmethod
    def _media_value(item: Any, name: str) -> Any:
        media = getattr(item, "media", None)
        return getattr(media, name, None)

    @classmethod
    def _dimension_key(cls, item: Any) -> str | None:
        width = cls._media_value(item, "width")
        height = cls._media_value(item, "height")
        if width is None or height is None:
            return None
        return f"{width}x{height}"

    @staticmethod
    def _shared_non_empty(values: Iterable[Any]) -> tuple[str, ...]:
        normalized = [
            str(value).strip().lower()
            for value in values
            if value is not None and str(value).strip()
        ]
        if len(normalized) < 2:
            return ()
        counts = Counter(normalized)
        return tuple(sorted(value for value, count in counts.items() if count >= 2))

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _cover_asset_id(items: tuple[Any, ...]) -> int | None:
        for item in items:
            if item.media.media_type == "image":
                return item.identity.asset_id
        return items[0].identity.asset_id if items else None

    @staticmethod
    def _content_intelligence_view(item: Any) -> Any:
        view = getattr(item, "to_asset_understanding_view", None)
        if callable(view):
            return view()
        return item

    def _standalone_name(self, item: Any) -> str:
        original = item.identity.original_filename or item.identity.file_name
        if original:
            stem = Path(str(original)).stem.replace("_", " ").replace("-", " ")
            return stem.strip().title() or f"Asset {item.identity.asset_id}"
        tags = item.visual.suggested_tags or item.visual.detected_themes
        if tags:
            return str(tags[0]).strip().title()
        return f"Asset {item.identity.asset_id}"

    def _collection_name(
        self,
        items: tuple[Any, ...],
        experience_type: ExperienceType,
    ) -> str:
        shared_tags = self._shared_terms(
            item.visual.suggested_tags for item in items
        )
        shared_themes = self._shared_terms(
            item.visual.detected_themes for item in items
        )
        term = (
            shared_tags[0]
            if shared_tags
            else shared_themes[0]
            if shared_themes
            else None
        )
        label = "Story" if experience_type == ExperienceType.STORY else "Photo Set"
        if term:
            return f"{term.title()} {label}"
        return f"{label} - {len(items)} Assets"

    @staticmethod
    def _collection_summary(
        items: tuple[Any, ...],
        experience_type: ExperienceType,
    ) -> str:
        summaries = [
            item.visual.summary
            for item in items
            if item.visual.summary
        ]
        label = (
            "Story sequence"
            if experience_type == ExperienceType.STORY
            else "Photoshoot"
        )
        if summaries:
            return f"{label} containing {len(items)} assets. {summaries[0]}"
        return f"{label} containing {len(items)} assets."

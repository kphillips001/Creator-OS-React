"""Deterministically merge persisted provider results into canonical Content Intelligence."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.models.asset_intelligence import AssetIntelligenceProviderResult, AssetIntelligenceStatus
from app.models.content_intelligence_profile import (
    CONTENT_INTELLIGENCE_SCHEMA_VERSION, ContentIntelligenceProfile,
    ContentIntelligenceProfileStatus,
)
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.asset_repository import AssetRepository
from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository


CONTENT_INTELLIGENCE_MERGE_VERSION = "business_asset_provider_merge_v1"
REQUIRED_PROVIDERS = ("nudenet", "gpt-vision", "grok-vision")


class MissingRequiredProviderResults(RuntimeError):
    def __init__(self, providers: tuple[str, ...]) -> None:
        self.providers = providers
        super().__init__(f"Missing successful provider results: {', '.join(providers)}")


class ContentIntelligenceMergeService:
    """Pure application merge; this service has no provider adapter dependency."""

    def __init__(self, *, intelligence=None, profiles=None, assets=None, now=None) -> None:
        self.intelligence = intelligence or AssetIntelligenceRepository()
        self.profiles = profiles or ContentIntelligenceProfileRepository()
        self.assets = assets or AssetRepository()
        self.now = now or (lambda: datetime.now(timezone.utc))

    def merge(self, asset_id: int, *, attempt_number: int = 1) -> ContentIntelligenceProfile:
        existing = self.profiles.get_by_asset_id(asset_id)
        if self.is_completed_merge(existing):
            return existing
        started = self.now()
        self.profiles.upsert_profile(ContentIntelligenceProfile(
            asset_id=asset_id, status=ContentIntelligenceProfileStatus.RUNNING,
            analysis_version=CONTENT_INTELLIGENCE_MERGE_VERSION,
            required_components=REQUIRED_PROVIDERS,
            retry_count=max(0, attempt_number - 1),
            provenance={"merge": {"schema_version": CONTENT_INTELLIGENCE_MERGE_VERSION,
                                  "attempt": attempt_number}},
            created_at=existing.created_at if existing else None,
            analysis_started_at=started,
            last_successful_analysis_at=existing.last_successful_analysis_at if existing else None,
        ))
        results = self._latest_successful(self.intelligence.list_provider_results(asset_id))
        missing = tuple(name for name in REQUIRED_PROVIDERS if name not in results)
        if missing:
            failed = self._failed_profile(asset_id, existing, started, attempt_number, missing)
            self.profiles.upsert_profile(failed)
            raise MissingRequiredProviderResults(missing)

        asset = self.assets.get_by_id(asset_id)
        if asset is None:
            failed = self._failed_profile(asset_id, existing, started, attempt_number, ("asset",))
            self.profiles.upsert_profile(failed)
            raise LookupError(f"Asset not found: {asset_id}")

        nude, vision, grok = (results[name] for name in REQUIRED_PROVIDERS)
        content, context, provenance, warnings = self._merge_values(asset, nude, vision, grok)
        completed = self.now()
        profile = ContentIntelligenceProfile(
            asset_id=asset_id, status=ContentIntelligenceProfileStatus.COMPLETE,
            schema_version=CONTENT_INTELLIGENCE_SCHEMA_VERSION,
            analysis_version=CONTENT_INTELLIGENCE_MERGE_VERSION,
            required_components=REQUIRED_PROVIDERS,
            completed_components=REQUIRED_PROVIDERS,
            missing_components=(), retry_count=max(0, attempt_number - 1),
            source_workflow=self._source_workflow(asset),
            approval_identity=self._approval_identity(asset), provenance=provenance,
            content_profile=content, normalized_context=context,
            search_document=self._search_document(content, context),
            reanalysis_reason="provider_result_merge" if attempt_number > 1 else None,
            created_at=existing.created_at if existing else None,
            analysis_started_at=started, analysis_completed_at=completed,
            last_successful_analysis_at=completed,
            error_code=None, error_message=None,
        )
        # Warnings remain queryable without polluting the consumer-facing fields.
        if warnings:
            profile = ContentIntelligenceProfile(
                **{**profile.__dict__, "provenance": {**provenance, "warnings": warnings}}
            )
        return self.profiles.upsert_profile(profile)

    @staticmethod
    def is_completed_merge(profile: ContentIntelligenceProfile | None) -> bool:
        return bool(profile and profile.status == ContentIntelligenceProfileStatus.COMPLETE
                    and profile.analysis_version == CONTENT_INTELLIGENCE_MERGE_VERSION)

    def record_failure(self, asset_id: int, error: Exception, *, attempt_number: int) -> ContentIntelligenceProfile:
        existing = self.profiles.get_by_asset_id(asset_id)
        profile = ContentIntelligenceProfile(
            asset_id=asset_id, status=ContentIntelligenceProfileStatus.FAILED,
            analysis_version=CONTENT_INTELLIGENCE_MERGE_VERSION,
            required_components=REQUIRED_PROVIDERS,
            retry_count=max(0, attempt_number - 1),
            provenance={"merge": {"schema_version": CONTENT_INTELLIGENCE_MERGE_VERSION,
                                  "attempt": attempt_number}},
            error_code=type(error).__name__, error_message=str(error),
            created_at=existing.created_at if existing else None,
            analysis_started_at=existing.analysis_started_at if existing else None,
            analysis_completed_at=self.now(),
            last_successful_analysis_at=existing.last_successful_analysis_at if existing else None,
        )
        return self.profiles.upsert_profile(profile)

    def _failed_profile(self, asset_id, existing, started, attempt, missing):
        return ContentIntelligenceProfile(
            asset_id=asset_id, status=ContentIntelligenceProfileStatus.FAILED,
            analysis_version=CONTENT_INTELLIGENCE_MERGE_VERSION,
            required_components=REQUIRED_PROVIDERS,
            completed_components=tuple(name for name in REQUIRED_PROVIDERS if name not in missing),
            missing_components=missing, retry_count=max(0, attempt - 1),
            provenance={"merge": {"schema_version": CONTENT_INTELLIGENCE_MERGE_VERSION,
                                  "attempt": attempt}},
            error_code="MISSING_REQUIRED_PROVIDER_RESULT" if missing != ("asset",) else "ASSET_NOT_FOUND",
            error_message=(f"Missing successful provider results: {', '.join(missing)}"),
            created_at=existing.created_at if existing else None,
            analysis_started_at=started, analysis_completed_at=self.now(),
            last_successful_analysis_at=existing.last_successful_analysis_at if existing else None,
        )

    def _merge_values(self, asset, nude, vision, grok):
        nv, vv, gv = map(lambda result: dict(result.normalized_fields or {}), (nude, vision, grok))
        vr, gr = dict(vision.raw_response or {}), dict(grok.raw_response or {})
        detections = tuple(item for item in (nude.raw_response or ()) if isinstance(item, Mapping))
        labels = self._dedupe(item.get("class") for item in detections)
        scores = [self._number(item.get("score")) for item in detections]
        scores = [value for value in scores if value is not None]

        vision_tags = self._dedupe(vv.get("tags"), vr.get("suggested_tags"), vr.get("tags"))
        semantic_tags = self._dedupe(gv.get("tags"), gr.get("tags"))
        themes = self._dedupe(gv.get("themes"), gr.get("themes"))
        semantic_keywords = self._dedupe(gv.get("keywords"), gv.get("search_phrases"), gr.get("search_phrases"))
        visual_keywords = self._dedupe(vv.get("keywords"), vr.get("keywords"), vr.get("suggested_keywords"))
        keywords = self._dedupe(visual_keywords, labels, semantic_keywords)
        objects = self._dedupe(vv.get("objects"), vr.get("objects"), vr.get("detected_objects"))
        activities = self._dedupe(vv.get("activities"), vr.get("activities"), vr.get("activity"))
        clothing_values = self._dedupe(vv.get("clothing"), vr.get("clothing"), vr.get("wardrobe"), vr.get("outfit"))
        setting = self._first(vv.get("setting"), vr.get("setting"), vr.get("location"))
        environment = self._first(vv.get("environment"), vr.get("environment"), vr.get("scene"), vr.get("background"))
        classification = self._first(vv.get("classification"), vr.get("final_classification"),
                                     vr.get("classification"), getattr(asset, "classification", None))
        summary = self._first(gv.get("content_summary"), gv.get("short_description"),
                              gr.get("descriptive_summary"), gr.get("short_description"))
        title = self._first(gv.get("title"), gr.get("title"))
        safety = self._first(nv.get("safety_classification"))
        explicit = safety == "EXPLICIT" or any(token in label for label in labels for token in ("GENITALIA", "ANUS"))
        exposed = any("EXPOSED" in label for label in labels)
        nudity_level = "explicit" if explicit else "partial" if exposed else "none"

        media = dict(getattr(asset, "media_metadata", None) or {})
        runtime_exists = media.get("runtime_exists")
        if runtime_exists is None:
            runtime_exists = media.get("has_runtime_media")
        technical_quality = {
            key: value for key, value in {
                "has_runtime_media": bool(runtime_exists) if runtime_exists is not None else False,
                "runtime_exists": bool(runtime_exists) if runtime_exists is not None else False,
                "width": media.get("width"), "height": media.get("height"),
                "aspect_ratio": media.get("aspect_ratio"), "size_bytes": media.get("size_bytes"),
            }.items() if value is not None
        }
        confidence_values = []
        for result in (nude, vision, grok):
            confidence_values.extend(self._number(value) for value in result.field_confidence.values())
        confidence_values.extend(scores)
        confidence_values = [value for value in confidence_values if value is not None]
        confidence = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None

        content = {
            "asset_id": int(asset.id), "title": title, "summary": summary, "classification": classification,
            "confidence": confidence, "themes": themes,
            "tags": self._dedupe(vision_tags, semantic_tags),
            "mood": self._first(gv.get("mood"), gr.get("mood")),
            "setting": setting, "outfit": clothing_values[0] if clothing_values else None,
            "pose": self._first(vv.get("pose"), vr.get("pose")),
            "activity": activities[0] if activities else None, "objects": objects,
            "environment": environment, "activities": activities,
            "clothing": clothing_values[0] if clothing_values else None,
            "keywords": keywords, "technical_quality": technical_quality,
            "media_metadata": media,
            "ai_metadata": {
                "safety": {"safety_classification": safety, "nudity_level": nudity_level,
                           "detected_explicit_regions": labels, "exposure_detected": exposed,
                           "explicit_content": explicit,
                           "confidence": max(scores) if scores else self._confidence(nude, "safety_classification")},
                "semantic": {key: value for key, value in {
                    "atmosphere": self._first(gv.get("atmosphere"), gr.get("atmosphere")),
                    "emotional_tone": self._first(gv.get("emotional_tone"), gr.get("emotional_tone")),
                    "visual_style": self._first(gv.get("visual_style"), gr.get("visual_style")),
                    "suggested_collections": self._dedupe(gv.get("suggested_collections"), gr.get("suggested_collections")),
                    "search_phrases": self._dedupe(gv.get("search_phrases"), gr.get("search_phrases")),
                    "lifestyle_context": self._first(gv.get("lifestyle_context"), gr.get("lifestyle_context")),
                }.items() if value not in (None, ())},
            },
            "technical_metadata": {key: media[key] for key in ("width", "height", "aspect_ratio", "size_bytes") if key in media},
            "readiness": {"analysis_ready": True, "component_completion": {
                "nudenet": True, "gpt-vision": True, "grok-vision": True}},
            "ownership": {"factual_visual": "gpt-vision", "safety": "nudenet",
                          "semantic": "grok-vision"},
        }
        content = self._clean_mapping(content)
        context = {**{key: content.get(key) for key in (
            "asset_id", "title", "summary", "classification", "confidence", "themes", "tags", "mood",
            "setting", "outfit", "pose", "activity", "objects", "environment", "activities",
            "clothing", "keywords", "technical_quality")},
            **content.get("ai_metadata", {}).get("safety", {}),
            **content.get("ai_metadata", {}).get("semantic", {})}
        context = self._clean_mapping(context)
        merged_at = self.now()
        provider_refs = {name: self._provider_ref(result) for name, result in zip(REQUIRED_PROVIDERS, (nude, vision, grok))}
        provenance = {
            "merge": {"schema_version": CONTENT_INTELLIGENCE_MERGE_VERSION,
                      "merged_at": merged_at.isoformat(), "deterministic": True},
            "providers": provider_refs,
            "field_ownership": {
                "classification": provider_refs["gpt-vision"], "setting": provider_refs["gpt-vision"],
                "environment": provider_refs["gpt-vision"], "activity": provider_refs["gpt-vision"],
                "outfit": provider_refs["gpt-vision"], "pose": provider_refs["gpt-vision"],
                "objects": provider_refs["gpt-vision"], "safety": provider_refs["nudenet"],
                "nudity_level": provider_refs["nudenet"], "summary": provider_refs["grok-vision"],
                "title": provider_refs["grok-vision"],
                "themes": provider_refs["grok-vision"], "mood": provider_refs["grok-vision"],
                "semantic": provider_refs["grok-vision"],
            },
        }
        warnings = self._warnings(content, runtime_exists)
        return content, context, provenance, warnings

    @classmethod
    def _latest_successful(cls, results):
        selected = {}
        for result in sorted(results, key=cls._result_key):
            if result.status != AssetIntelligenceStatus.READY:
                continue
            stage = str(result.metadata.get("stage") or "").upper()
            name = ("nudenet" if result.provider == "nudenet" or stage == "NUDENET"
                    else "gpt-vision" if result.provider == "gpt-vision" or stage == "VISION"
                    else "grok-vision" if result.provider == "grok-vision" or stage == "GROK" else None)
            if name:
                selected[name] = result
        return selected

    @staticmethod
    def _result_key(result):
        moment = result.analyzed_at or result.created_at
        return ((moment.timestamp() if moment else 0.0), result.result_id)

    @staticmethod
    def _provider_ref(result):
        return {"provider": result.provider, "provider_version": result.provider_version,
                "provider_result_id": result.result_id,
                "source_confidence": dict(result.field_confidence)}

    @classmethod
    def _dedupe(cls, *values):
        output, seen = [], set()
        for value in values:
            items = (value,) if isinstance(value, str) else value or ()
            if isinstance(items, Mapping): items = items.values()
            try: iterator = iter(items)
            except TypeError: iterator = iter((items,))
            for item in iterator:
                text = str(item).strip() if item is not None else ""
                key = text.casefold()
                if text and key not in seen:
                    seen.add(key); output.append(text)
        return tuple(output)

    @classmethod
    def _first(cls, *values):
        items = cls._dedupe(*values)
        return items[0] if items else None

    @staticmethod
    def _number(value):
        try: return max(0.0, min(1.0, float(value))) if value is not None else None
        except (TypeError, ValueError): return None

    @classmethod
    def _confidence(cls, result, field): return cls._number(result.field_confidence.get(field))

    @staticmethod
    def _clean_mapping(value):
        return {key: item for key, item in value.items() if item not in (None, "", (), [], {})}

    @staticmethod
    def _source_workflow(asset):
        approval = dict((getattr(asset, "media_metadata", None) or {}).get("creator_approval") or {})
        return approval.get("source_workflow")

    @staticmethod
    def _approval_identity(asset):
        return dict((getattr(asset, "media_metadata", None) or {}).get("creator_approval") or {})

    @staticmethod
    def _warnings(content, runtime_exists):
        warnings = []
        for field in ("classification", "summary", "themes", "tags", "mood", "setting", "activity", "objects"):
            if content.get(field) in (None, (), ""):
                warnings.append(f"missing_optional_field:{field}")
        if runtime_exists is None: warnings.append("runtime_media_status_unavailable")
        return tuple(warnings)

    @classmethod
    def _search_document(cls, content, context):
        semantic = content.get("ai_metadata", {}).get("semantic", {})
        safety = content.get("ai_metadata", {}).get("safety", {})
        terms = cls._dedupe(
            content.get("classification"), content.get("setting"), content.get("environment"),
            content.get("outfit"), content.get("clothing"), content.get("activity"),
            content.get("activities"), content.get("objects"), content.get("themes"),
            content.get("mood"), semantic.get("visual_style"), content.get("keywords"),
            semantic.get("search_phrases"), safety.get("safety_classification"), safety.get("nudity_level"),
        )
        return " ".join(terms)

"""Register approved Assets into durable Content Intelligence profiles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.content_intelligence_profile import (
    CONTENT_INTELLIGENCE_ANALYSIS_VERSION,
    CONTENT_INTELLIGENCE_SCHEMA_VERSION,
    ContentIntelligenceProfile,
    ContentIntelligenceProfileStatus,
)


class ContentIntelligenceRegistrationService:
    """Persist content-only intelligence for approved canonical Assets."""

    IMAGE_ANALYSIS_WORKFLOWS = {"generation_library", "photoshoot"}

    def __init__(
        self,
        *,
        profile_repository: Any | None = None,
        asset_repository: Any | None = None,
        content_intelligence_service: Any | None = None,
        nudenet_runner: Callable[[Path], list] | None = None,
        vision_runner: Callable[[Path, str], dict] | None = None,
        tier_rule_applier: Callable[[dict, list], dict] | None = None,
    ) -> None:
        self._profiles = profile_repository
        self._assets = asset_repository
        self._content_intelligence = content_intelligence_service
        self._nudenet_runner = nudenet_runner
        self._vision_runner = vision_runner
        self._tier_rule_applier = tier_rule_applier

    @property
    def profiles(self):
        if self._profiles is None:
            from app.repositories.content_intelligence_repository import (
                ContentIntelligenceProfileRepository,
            )

            self._profiles = ContentIntelligenceProfileRepository()
        return self._profiles

    @property
    def assets(self):
        if self._assets is None:
            from app.repositories.asset_repository import AssetRepository

            self._assets = AssetRepository()
        return self._assets

    @property
    def content_intelligence(self):
        if self._content_intelligence is None:
            from app.services.asset_understanding_service import AssetUnderstandingService
            from app.services.content_intelligence_service import ContentIntelligenceService

            self._content_intelligence = ContentIntelligenceService(
                asset_understanding_service=AssetUnderstandingService(
                    asset_repository=self.assets
                )
            )
        return self._content_intelligence

    @property
    def nudenet_runner(self):
        if self._nudenet_runner is None:
            from app.services.content_classification_service import run_nudenet

            self._nudenet_runner = run_nudenet
        return self._nudenet_runner

    @property
    def vision_runner(self):
        if self._vision_runner is None:
            from app.services.content_classification_service import run_gpt_vision

            self._vision_runner = run_gpt_vision
        return self._vision_runner

    @property
    def tier_rule_applier(self):
        if self._tier_rule_applier is None:
            from app.services.content_classification_service import apply_tier_rules

            self._tier_rule_applier = apply_tier_rules
        return self._tier_rule_applier

    def register_asset(
        self,
        asset_id: int,
        *,
        source_workflow: str | None = None,
        approval_identity: Mapping[str, Any] | None = None,
        force: bool = False,
        reanalysis_reason: str | None = None,
    ) -> ContentIntelligenceProfile | None:
        existing = self.profiles.get_by_asset_id(int(asset_id))
        if (
            existing is not None
            and existing.status == ContentIntelligenceProfileStatus.COMPLETE
            and existing.schema_version == CONTENT_INTELLIGENCE_SCHEMA_VERSION
            and existing.analysis_version == CONTENT_INTELLIGENCE_ANALYSIS_VERSION
            and not force
        ):
            return existing

        asset = self.assets.get_by_id(int(asset_id))
        if asset is None or str(getattr(asset, "status", "") or "") != "approved":
            return None

        started_at = self._now()
        running = ContentIntelligenceProfile(
            asset_id=int(asset_id),
            status=ContentIntelligenceProfileStatus.RUNNING,
            retry_count=(existing.retry_count + 1 if existing else 0),
            source_workflow=source_workflow or self._source_workflow(asset),
            approval_identity=dict(approval_identity or self._approval_identity(asset)),
            provenance={
                "registrar": "ContentIntelligenceRegistrationService",
                "schema_version": CONTENT_INTELLIGENCE_SCHEMA_VERSION,
                "analysis_version": CONTENT_INTELLIGENCE_ANALYSIS_VERSION,
            },
            reanalysis_reason=reanalysis_reason,
            created_at=existing.created_at if existing else None,
            analysis_started_at=started_at,
            last_successful_analysis_at=(
                existing.last_successful_analysis_at if existing else None
            ),
        )
        self.profiles.upsert_profile(running)

        try:
            asset = self._ensure_required_asset_analysis(
                asset,
                source_workflow=running.source_workflow,
            )
            content = self.content_intelligence.build_from_asset(asset)
            required, completed, missing = self._component_state(asset, content)
            completed_at = self._now()
            status = (
                ContentIntelligenceProfileStatus.COMPLETE
                if not missing
                else ContentIntelligenceProfileStatus.PARTIAL
            )
            profile = ContentIntelligenceProfile(
                asset_id=int(asset_id),
                status=status,
                required_components=required,
                completed_components=completed,
                missing_components=missing,
                retry_count=running.retry_count,
                source_workflow=running.source_workflow,
                approval_identity=running.approval_identity,
                provenance=self._profile_provenance(asset),
                content_profile=content.to_context(),
                normalized_context=self._normalized_context(asset, content),
                search_document=self._search_document(asset, content),
                reanalysis_reason=reanalysis_reason,
                created_at=running.created_at,
                analysis_started_at=started_at,
                analysis_completed_at=completed_at,
                last_successful_analysis_at=(
                    completed_at
                    if status == ContentIntelligenceProfileStatus.COMPLETE
                    else running.last_successful_analysis_at
                ),
            )
            return self.profiles.upsert_profile(profile)
        except Exception as error:
            failed = ContentIntelligenceProfile(
                asset_id=int(asset_id),
                status=ContentIntelligenceProfileStatus.FAILED,
                retry_count=running.retry_count,
                source_workflow=running.source_workflow,
                approval_identity=running.approval_identity,
                provenance=running.provenance,
                error_code=type(error).__name__,
                error_message=str(error),
                reanalysis_reason=reanalysis_reason,
                created_at=running.created_at,
                analysis_started_at=started_at,
                analysis_completed_at=self._now(),
                last_successful_analysis_at=running.last_successful_analysis_at,
            )
            return self.profiles.upsert_profile(failed)

    def retry_failed_components(
        self,
        asset_id: int,
        *,
        reason: str = "retry_failed_components",
    ) -> ContentIntelligenceProfile | None:
        return self.register_asset(
            asset_id,
            force=True,
            reanalysis_reason=reason,
        )

    def mark_reanalysis_required(
        self,
        asset_id: int,
        *,
        reason: str,
    ) -> ContentIntelligenceProfile | None:
        existing = self.profiles.get_by_asset_id(int(asset_id))
        if existing is None:
            return None
        return self.profiles.upsert_profile(
            replace(
                existing,
                status=ContentIntelligenceProfileStatus.REANALYSIS_REQUIRED,
                reanalysis_reason=reason,
            )
        )

    def _ensure_required_asset_analysis(
        self,
        asset: Any,
        *,
        source_workflow: str | None,
    ) -> Any:
        if getattr(asset, "media_type", None) != "image":
            return asset
        if source_workflow not in self.IMAGE_ANALYSIS_WORKFLOWS:
            return asset
        needs_nudenet = not self._has_nudenet(asset)
        needs_vision = not self._has_vision(asset)
        if not needs_nudenet and not needs_vision:
            return asset

        image_path = self._analysis_path(asset)
        if image_path is None:
            return asset
        gpt_result = dict(getattr(asset, "gpt_vision_result", None) or {})
        if needs_vision:
            gpt_result = dict(self.vision_runner(image_path, getattr(asset, "upload_intent", None) or "teaser_image") or {})
        nudenet_result = getattr(asset, "nudenet_result", None)
        if needs_nudenet:
            nudenet_result = self.nudenet_runner(image_path) or []
        final_result = dict(self.tier_rule_applier(gpt_result, list(nudenet_result or [])) or {})
        final_classification = final_result.get("final_classification") or getattr(asset, "classification", None)
        labels = self._nudenet_labels(nudenet_result)
        provenance = dict(getattr(asset, "analysis_provenance", None) or {})
        provenance.update(
            {
                "content_intelligence_registration": True,
                "analysis_version": CONTENT_INTELLIGENCE_ANALYSIS_VERSION,
                "nudenet_enabled": True,
                "nudenet_repaired_for_approved_asset": needs_nudenet,
                "vision_repaired_for_approved_asset": needs_vision,
                "upload_intent": getattr(asset, "upload_intent", None),
            }
        )
        fields = {
            "classification": final_classification,
            "confidence": gpt_result.get("confidence"),
            "detected_themes": gpt_result.get("detected_themes", ()),
            "suggested_tags": gpt_result.get("suggested_tags", ()),
            "nudity_labels": labels,
            "nudity_level": self._nudity_level(labels, final_classification),
            "sexual_intensity": self._sexual_intensity(final_classification),
            "is_explicit": final_classification == "PREMIUM",
            "short_safe_summary": gpt_result.get("short_safe_summary"),
            "risk_flags": gpt_result.get("risk_flags", ()),
            "analysis_reasoning": gpt_result.get("reasoning"),
            "analysis_provenance": provenance,
            "gpt_vision_result": gpt_result,
            "nudenet_result": nudenet_result,
            "classification_result": final_result,
        }
        updater = getattr(self.assets, "update_analysis_fields", None)
        if callable(updater):
            updater(int(getattr(asset, "id")), fields)
        return self.assets.get_by_id(int(getattr(asset, "id"))) or asset

    def _component_state(
        self,
        asset: Any,
        content: Any,
    ) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        required = ["asset", "runtime_media", "classification"]
        if getattr(asset, "media_type", None) == "image":
            required.extend(["vision", "nudenet"])
        else:
            required.append("media_analysis")
        completed = []
        if asset is not None:
            completed.append("asset")
        if (content.technical_quality or {}).get("has_runtime_media") or (
            content.media_metadata or {}
        ).get("runtime_exists"):
            completed.append("runtime_media")
        if content.classification:
            completed.append("classification")
        if self._has_vision(asset):
            completed.append("vision")
        if self._has_nudenet(asset):
            completed.append("nudenet")
        if getattr(asset, "media_type", None) != "image":
            completed.append("media_analysis")
        missing = tuple(component for component in required if component not in completed)
        return tuple(required), tuple(completed), missing

    @staticmethod
    def _has_vision(asset: Any) -> bool:
        result = getattr(asset, "gpt_vision_result", None) or {}
        return isinstance(result, Mapping) and bool(result) and not result.get("error")

    @staticmethod
    def _has_nudenet(asset: Any) -> bool:
        result = getattr(asset, "nudenet_result", None)
        provenance = getattr(asset, "analysis_provenance", None) or {}
        if not isinstance(result, list):
            return False
        if any(isinstance(item, Mapping) and item.get("error") for item in result):
            return False
        return bool(provenance.get("nudenet_enabled"))

    @staticmethod
    def _analysis_path(asset: Any) -> Path | None:
        metadata = dict(getattr(asset, "media_metadata", None) or {})
        for value in (
            metadata.get("local_vault_path"),
            getattr(asset, "local_vault_path", None),
            getattr(asset, "file_path", None),
        ):
            if value:
                path = Path(str(value))
                if path.exists():
                    return path
        return None

    @staticmethod
    def _source_workflow(asset: Any) -> str | None:
        metadata = dict(getattr(asset, "media_metadata", None) or {})
        approval = dict(metadata.get("creator_approval") or {})
        return approval.get("source_workflow")

    @staticmethod
    def _approval_identity(asset: Any) -> Mapping[str, Any]:
        metadata = dict(getattr(asset, "media_metadata", None) or {})
        return dict(metadata.get("creator_approval") or {})

    @staticmethod
    def _profile_provenance(asset: Any) -> Mapping[str, Any]:
        provenance = dict(getattr(asset, "analysis_provenance", None) or {})
        provenance.update(
            {
                "registrar": "ContentIntelligenceRegistrationService",
                "schema_version": CONTENT_INTELLIGENCE_SCHEMA_VERSION,
                "analysis_version": CONTENT_INTELLIGENCE_ANALYSIS_VERSION,
            }
        )
        return provenance

    @staticmethod
    def _normalized_context(asset: Any, content: Any) -> Mapping[str, Any]:
        return {
            "asset_id": getattr(asset, "id", None),
            "media_type": getattr(asset, "media_type", None),
            "upload_intent": getattr(asset, "upload_intent", None),
            "classification": content.classification,
            "confidence": content.confidence,
            "summary": content.summary,
            "themes": content.themes,
            "tags": content.tags,
            "keywords": content.keywords,
            "mood": content.mood,
            "setting": content.setting,
            "environment": content.environment,
            "clothing": content.clothing,
            "pose": content.pose,
            "activity": content.activity,
            "objects": content.objects,
            "nudity_labels": getattr(asset, "nudity_labels", ()),
            "nudity_level": getattr(asset, "nudity_level", None),
            "sexual_intensity": getattr(asset, "sexual_intensity", None),
            "is_explicit": getattr(asset, "is_explicit", False),
            "risk_flags": getattr(asset, "risk_flags", ()),
        }

    @classmethod
    def _search_document(cls, asset: Any, content: Any) -> str:
        values = [
            getattr(asset, "file_name", None),
            content.summary,
            content.classification,
            content.mood,
            content.setting,
            content.environment,
            content.clothing,
            content.pose,
            content.activity,
            *content.themes,
            *content.tags,
            *content.keywords,
            *content.objects,
        ]
        return " ".join(str(value) for value in values if value)

    @staticmethod
    def _nudenet_labels(nudenet_result: Any) -> tuple[str, ...]:
        labels = []
        if isinstance(nudenet_result, list):
            for item in nudenet_result:
                if isinstance(item, Mapping) and item.get("class"):
                    labels.append(str(item["class"]))
        return tuple(labels)

    @staticmethod
    def _nudity_level(labels: tuple[str, ...], classification: str | None) -> str:
        if classification == "PREMIUM":
            return "full"
        if "FEMALE_BREAST_EXPOSED" in labels:
            return "partial"
        if any("COVERED" in label for label in labels):
            return "covered"
        return "none"

    @staticmethod
    def _sexual_intensity(classification: str | None) -> str:
        if classification == "PREMIUM":
            return "high"
        if classification == "VIP":
            return "medium"
        if classification == "TEASE":
            return "low"
        return "unknown"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

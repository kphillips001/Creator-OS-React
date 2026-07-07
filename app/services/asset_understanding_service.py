"""Normalize stored Asset intelligence into AssetUnderstanding."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.asset_understanding import (
    AssetUnderstanding,
    AssetUnderstandingClassification,
    AssetUnderstandingIdentity,
    AssetUnderstandingMedia,
    AssetUnderstandingMetadata,
    AssetUnderstandingProvenance,
    AssetUnderstandingReadiness,
    AssetUnderstandingSafety,
    AssetUnderstandingVisual,
)

if TYPE_CHECKING:
    from app.repositories.asset_repository import AssetRepository
    from app.services.runtime_media_resolver import RuntimeMediaResolver


class AssetUnderstandingService:
    """Build canonical AssetUnderstanding from existing stored Asset data."""

    def __init__(
        self,
        *,
        asset_repository: "AssetRepository | None" = None,
        runtime_media_resolver: "RuntimeMediaResolver | None" = None,
    ):
        self._assets = asset_repository
        self._runtime_media_resolver = runtime_media_resolver

    @property
    def assets(self):
        if self._assets is None:
            from app.repositories.asset_repository import AssetRepository

            self._assets = AssetRepository()
        return self._assets

    @property
    def runtime_media_resolver(self):
        if self._runtime_media_resolver is None:
            from app.services.runtime_media_resolver import RuntimeMediaResolver

            self._runtime_media_resolver = RuntimeMediaResolver()
        return self._runtime_media_resolver

    def get_understanding(self, asset_id: int) -> AssetUnderstanding | None:
        asset = self.assets.get_by_id(asset_id)
        if not asset:
            return None
        return self.build_from_asset(asset)

    def build_from_asset(self, asset: Any) -> AssetUnderstanding:
        media_metadata = self._coerce_mapping(
            self._get(asset, "media_metadata")
        )
        gpt_vision_result = self._coerce_mapping(
            self._get(asset, "gpt_vision_result")
        )
        classification_result = self._coerce_mapping(
            self._get(asset, "classification_result")
        )
        analysis_provenance = self._coerce_mapping(
            self._get(asset, "analysis_provenance")
        )
        runtime = self.runtime_media_resolver.resolve_original(
            asset,
            require_exists=True,
        )
        classification = (
            classification_result.get("final_classification")
            or self._get(asset, "classification")
        )
        review_reasons = self._review_reasons(
            asset=asset,
            classification=classification,
            runtime_exists=runtime.exists,
            gpt_vision_result=gpt_vision_result,
        )
        local_vault_path = (
            media_metadata.get("local_vault_path")
            or self._get(asset, "local_vault_path")
        )

        return AssetUnderstanding(
            identity=AssetUnderstandingIdentity(
                asset_id=int(self._get(asset, "id")),
                creator_profile_id=self._get(asset, "creator_profile_id"),
                file_name=self._get(asset, "file_name"),
                original_filename=media_metadata.get("original_filename"),
                upload_intent=self._get(asset, "upload_intent"),
                created_at=self._get(asset, "created_at"),
            ),
            media=AssetUnderstandingMedia(
                media_type=self._get(asset, "media_type", "unknown"),
                local_vault_path=str(local_vault_path) if local_vault_path else None,
                legacy_file_path=self._get(asset, "file_path"),
                runtime_path=runtime.path_string,
                runtime_source=runtime.source,
                runtime_exists=runtime.exists,
                mime_type=media_metadata.get("mime_type"),
                file_extension=media_metadata.get("file_extension"),
                size_bytes=self._coerce_int(media_metadata.get("size_bytes")),
                width=self._coerce_int(media_metadata.get("width")),
                height=self._coerce_int(media_metadata.get("height")),
                aspect_ratio=media_metadata.get("aspect_ratio"),
                duration_seconds=self._coerce_float(
                    media_metadata.get("duration_seconds")
                ),
                codec=media_metadata.get("codec"),
                frame_rate=self._coerce_float(media_metadata.get("frame_rate")),
                video_analysis_status=media_metadata.get(
                    "video_analysis_status",
                    "not_available",
                ),
            ),
            visual=AssetUnderstandingVisual(
                summary=(
                    self._get(asset, "summary")
                    or gpt_vision_result.get("short_safe_summary")
                ),
                detected_themes=self._coerce_tuple(
                    self._get(asset, "detected_themes")
                    or gpt_vision_result.get("detected_themes")
                ),
                suggested_tags=self._coerce_tuple(
                    self._get(asset, "suggested_tags")
                    or gpt_vision_result.get("suggested_tags")
                ),
                mood=gpt_vision_result.get("mood"),
                setting=gpt_vision_result.get("setting"),
                outfit=gpt_vision_result.get("outfit"),
                pose=gpt_vision_result.get("pose"),
                activity=gpt_vision_result.get("activity"),
                objects=self._coerce_tuple(gpt_vision_result.get("objects")),
                gpt_vision_result=gpt_vision_result,
            ),
            safety=AssetUnderstandingSafety(
                risk_flags=self._coerce_tuple(
                    self._get(asset, "risk_flags")
                    or gpt_vision_result.get("risk_flags")
                ),
                nudity_labels=self._coerce_tuple(
                    self._get(asset, "nudity_labels")
                ),
                nudity_level=self._get(asset, "nudity_level"),
                sexual_intensity=self._get(asset, "sexual_intensity"),
                is_explicit=bool(self._get(asset, "is_explicit", False)),
                nudenet_result=self._get(asset, "nudenet_result"),
            ),
            classification=AssetUnderstandingClassification(
                classification=self._get(asset, "classification"),
                confidence=self._coerce_float(self._get(asset, "confidence")),
                raw_gpt_classification=classification_result.get(
                    "raw_gpt_classification"
                )
                or gpt_vision_result.get("classification"),
                final_classification=classification,
                rule_applied=classification_result.get("rule_applied"),
                classification_result=classification_result,
            ),
            metadata=AssetUnderstandingMetadata(
                media_metadata=media_metadata,
                duplicate_detection_status=media_metadata.get(
                    "duplicate_detection_status",
                    "not_available",
                ),
                similarity_group_id=media_metadata.get("similarity_group_id"),
                perceptual_hash=media_metadata.get("perceptual_hash"),
                checksum=media_metadata.get("checksum"),
            ),
            provenance=AssetUnderstandingProvenance(
                source=analysis_provenance.get("source"),
                analysis_version=analysis_provenance.get("analysis_version"),
                vision_model=analysis_provenance.get("vision_model"),
                nudenet_enabled=bool(
                    analysis_provenance.get("nudenet_enabled", False)
                ),
                upload_intent=analysis_provenance.get("upload_intent"),
                analysis_provenance=analysis_provenance,
                reasoning=(
                    self._get(asset, "reasoning")
                    or gpt_vision_result.get("reasoning")
                ),
            ),
            readiness=AssetUnderstandingReadiness(
                status=self._get(asset, "status"),
                is_active=bool(self._get(asset, "is_active", False)),
                is_test=bool(self._get(asset, "is_test", False)),
                ready_for_rotation=bool(
                    self._get(asset, "ready_for_rotation", False)
                ),
                has_runtime_media=runtime.exists,
                has_local_vault_media=bool(local_vault_path),
                has_visual_summary=bool(
                    self._get(asset, "summary")
                    or gpt_vision_result.get("short_safe_summary")
                ),
                has_classification=bool(classification),
                needs_review=bool(review_reasons),
                review_reasons=review_reasons,
            ),
        )

    @classmethod
    def _review_reasons(
        cls,
        *,
        asset: Any,
        classification: str | None,
        runtime_exists: bool,
        gpt_vision_result: Mapping[str, Any],
    ) -> tuple[str, ...]:
        reasons = []
        if not runtime_exists:
            reasons.append("runtime_media_missing")
        if not classification:
            reasons.append("classification_missing")
        if str(classification or "").upper() == "EDGE_CASE":
            reasons.append("edge_case_classification")
        if gpt_vision_result.get("error"):
            reasons.append("vision_result_error")
        if cls._get(asset, "status") not in {None, "approved"}:
            reasons.append("asset_not_approved")
        return tuple(reasons)

    @staticmethod
    def _get(asset: Any, key: str, default: Any = None) -> Any:
        if isinstance(asset, Mapping):
            return asset.get(key, default)
        return getattr(asset, key, default)

    @staticmethod
    def _coerce_mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, Mapping):
                return parsed
        return {}

    @staticmethod
    def _coerce_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (list, tuple)):
                value = parsed
            else:
                return (value,) if value.strip() else ()
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item).strip())
        return (str(value),) if str(value).strip() else ()

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

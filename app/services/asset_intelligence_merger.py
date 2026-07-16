"""Deterministic merger for normalized provider contributions."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timezone
from typing import Any, Iterable

from app.models.asset_intelligence import (
    AssetIntelligenceProfile,
    AssetIntelligenceProviderResult,
    AssetIntelligenceStatus,
)


class AssetIntelligenceMerger:
    """Merge provider-normalized fields without knowing provider APIs."""

    _PROTECTED_FIELDS = {
        "asset_id", "creator_profile_id", "schema_version", "analysis_status",
        "analyzed_at", "created_at", "updated_at", "error_code", "error_message",
        "field_confidence", "provider_agreement", "overall_confidence",
    }

    def merge(
        self,
        profile: AssetIntelligenceProfile,
        provider_results: Iterable[AssetIntelligenceProviderResult],
    ) -> AssetIntelligenceProfile:
        results = tuple(provider_results)
        successful = tuple(
            result
            for result in results
            if result.status in {
                AssetIntelligenceStatus.READY,
                AssetIntelligenceStatus.PARTIAL,
            }
        )
        if not results:
            return profile
        if not successful:
            pending_status = (
                AssetIntelligenceStatus.ANALYZING
                if any(
                    result.status == AssetIntelligenceStatus.ANALYZING
                    for result in results
                )
                else AssetIntelligenceStatus.PENDING
                if any(
                    result.status == AssetIntelligenceStatus.PENDING
                    for result in results
                )
                else AssetIntelligenceStatus.FAILED
            )
            return replace(
                profile,
                analysis_status=pending_status,
                updated_at=self._now(),
            )

        allowed = {
            item.name for item in fields(AssetIntelligenceProfile)
        } - self._PROTECTED_FIELDS
        candidates: dict[str, list[tuple[float, str, Any]]] = {}
        for result in successful:
            for name, value in dict(result.normalized_fields).items():
                if name not in allowed or value is None:
                    continue
                confidence = float(result.field_confidence.get(name, 0.0) or 0.0)
                candidates.setdefault(name, []).append(
                    (confidence, result.provider, value)
                )

        updates: dict[str, Any] = {}
        confidence_by_field: dict[str, float] = {}
        agreement: dict[str, Any] = {}
        for name, values in candidates.items():
            winner = max(values, key=lambda item: (item[0], item[1]))
            updates[name] = self._coerce_profile_value(profile, name, winner[2])
            confidence_by_field[name] = winner[0]
            comparable = [self._comparable(item[2]) for item in values]
            agreement[name] = {
                "providers": tuple(item[1] for item in values),
                "agreement": (
                    1.0
                    if len(comparable) <= 1
                    else comparable.count(comparable[0]) / len(comparable)
                ),
                "selected_provider": winner[1],
            }

        statuses = {result.status for result in results}
        status = (
            AssetIntelligenceStatus.READY
            if updates and statuses == {AssetIntelligenceStatus.READY}
            else AssetIntelligenceStatus.PARTIAL
        )
        now = self._now()
        return replace(
            profile,
            **updates,
            analysis_status=status,
            analyzed_at=max(
                (result.analyzed_at for result in successful if result.analyzed_at),
                default=now,
            ),
            overall_confidence=(
                sum(confidence_by_field.values()) / len(confidence_by_field)
                if confidence_by_field else None
            ),
            field_confidence=confidence_by_field,
            provider_agreement=agreement,
            error_code=None,
            error_message=None,
            updated_at=now,
        )

    @staticmethod
    def _coerce_profile_value(profile, name: str, value: Any) -> Any:
        current = getattr(profile, name)
        if isinstance(current, tuple) or name in {
            "objects", "clothing", "accessories", "colors",
            "visible_body_regions", "risk_flags", "tags", "themes",
            "keywords", "content_categories", "suggested_collections",
            "suggested_use_cases",
        }:
            if isinstance(value, str):
                return (value,)
            return tuple(value or ())
        return value

    @staticmethod
    def _comparable(value: Any) -> str:
        return repr(value).strip().lower()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

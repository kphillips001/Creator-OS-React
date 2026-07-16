"""Provider-neutral orchestration for Asset Intelligence lifecycle."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from app.models.asset_intelligence import (
    AssetIntelligenceProfile,
    AssetIntelligenceProviderResult,
    AssetIntelligenceStatus,
)
from app.repositories.asset_intelligence_repository import (
    AssetIntelligenceRepository,
)
from app.services.asset_intelligence_merger import AssetIntelligenceMerger


class AssetIntelligenceService:
    """Owns lifecycle and normalization; it does not execute providers."""

    def __init__(
        self,
        repository: AssetIntelligenceRepository | None = None,
        merger: AssetIntelligenceMerger | None = None,
    ) -> None:
        self.repository = repository or AssetIntelligenceRepository()
        self.merger = merger or AssetIntelligenceMerger()

    def initialize_pending(
        self,
        *,
        asset_id: int,
        creator_profile_id: int,
    ) -> AssetIntelligenceProfile:
        existing = self.repository.get_profile(int(asset_id))
        if existing is not None:
            if existing.creator_profile_id != int(creator_profile_id):
                raise ValueError("Asset Intelligence creator ownership mismatch.")
            return existing
        return self.repository.upsert_profile(
            AssetIntelligenceProfile(
                asset_id=int(asset_id),
                creator_profile_id=int(creator_profile_id),
                analysis_status=AssetIntelligenceStatus.PENDING,
            )
        )

    def begin_analysis(self, asset_id: int) -> AssetIntelligenceProfile:
        profile = self._required_profile(asset_id)
        if profile.analysis_status not in {
            AssetIntelligenceStatus.PENDING,
            AssetIntelligenceStatus.PARTIAL,
            AssetIntelligenceStatus.FAILED,
        }:
            return profile
        return self.repository.upsert_profile(
            replace(
                profile,
                analysis_status=AssetIntelligenceStatus.ANALYZING,
                error_code=None,
                error_message=None,
            )
        )

    def record_provider_result(
        self,
        result: AssetIntelligenceProviderResult,
    ) -> AssetIntelligenceProviderResult:
        profile = self._required_profile(result.asset_id)
        if profile.creator_profile_id != result.creator_profile_id:
            raise ValueError("Provider result creator ownership mismatch.")
        return self.repository.save_provider_result(result)

    def merge_provider_results(self, asset_id: int) -> AssetIntelligenceProfile:
        profile = self._required_profile(asset_id)
        merged = self.merger.merge(
            profile,
            self.repository.list_provider_results(int(asset_id)),
        )
        return self.repository.upsert_profile(merged)

    def mark_failed(
        self,
        asset_id: int,
        *,
        error_code: str,
        error_message: str,
    ) -> AssetIntelligenceProfile:
        profile = self._required_profile(asset_id)
        return self.repository.upsert_profile(
            replace(
                profile,
                analysis_status=AssetIntelligenceStatus.FAILED,
                analyzed_at=datetime.now(timezone.utc),
                error_code=error_code,
                error_message=error_message,
            )
        )

    def get_profile(self, asset_id: int) -> AssetIntelligenceProfile | None:
        return self.repository.get_profile(int(asset_id))

    def _required_profile(self, asset_id: int) -> AssetIntelligenceProfile:
        profile = self.repository.get_profile(int(asset_id))
        if profile is None:
            raise LookupError(f"Asset Intelligence profile not found: {asset_id}")
        return profile

"""Synchronous Phase 2A Asset Intelligence workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.models.asset_intelligence_execution import AssetIntelligenceProviderPolicy
from app.repositories.asset_intelligence_run_repository import AssetIntelligenceRunRepository
from app.repositories.asset_repository import AssetRepository
from app.services.asset_intelligence_orchestrator import AssetIntelligenceOrchestrator
from app.services.asset_intelligence_provider_adapters import (
    GptVisionAssetIntelligenceAdapter,
    GrokVisionAssetIntelligenceAdapter,
    NudeNetAssetIntelligenceAdapter,
)
from app.services.asset_intelligence_service import AssetIntelligenceService


class AssetIntelligenceAnalysisService:
    PROVIDER_LABELS = {
        "gpt-vision": "GPT Vision",
        "grok-vision": "Grok Vision",
        "nudenet": "NudeNet",
    }

    def __init__(self, *, asset_repository: AssetRepository | None = None,
                 orchestrator: AssetIntelligenceOrchestrator | None = None) -> None:
        self.assets = asset_repository or AssetRepository()
        self.orchestrator = orchestrator or AssetIntelligenceOrchestrator(
            run_repository=AssetIntelligenceRunRepository(),
            intelligence_service=AssetIntelligenceService(),
            adapters={
                "gpt-vision": GptVisionAssetIntelligenceAdapter(),
                "grok-vision": GrokVisionAssetIntelligenceAdapter(),
                "nudenet": NudeNetAssetIntelligenceAdapter(),
            },
        )

    def analyze(self, *, asset_id: int, creator_profile_id: int,
                progress: Callable[[str], None] | None = None):
        asset = self.assets.get_by_id(asset_id)
        if asset is None:
            raise LookupError(f"Asset not found: {asset_id}")
        if asset.creator_profile_id != creator_profile_id:
            raise ValueError("Asset creator ownership mismatch.")
        managed_path = str(asset.local_vault_path or asset.file_path or "")
        if not Path(managed_path).is_file():
            raise FileNotFoundError(f"Managed asset media not found: {managed_path}")

        def provider_progress(name: str) -> None:
            if progress:
                progress(self.PROVIDER_LABELS.get(name, name))

        run = self.orchestrator.execute_analysis(
            asset_id=asset_id, creator_profile_id=creator_profile_id,
            media_type="image", managed_media_path=managed_path,
            original_filename=asset.file_name or Path(managed_path).name,
            # Phase 2A requires all three integrations before library visibility.
            policy=AssetIntelligenceProviderPolicy(
                required_providers=("gpt-vision", "grok-vision", "nudenet"),
            ),
            progress=provider_progress,
        )
        if run.status.value != "READY":
            raise RuntimeError(f"Asset analysis did not complete successfully: {run.status.value}")
        profile = self.orchestrator.intelligence.get_profile(asset_id)
        if profile is None or profile.analysis_status.value != "READY":
            raise RuntimeError("Unified Asset Intelligence Profile is not READY.")
        # Maintain the existing Asset Library tag/theme read model during migration.
        self.assets.update_analysis_fields(asset_id, {
            "short_safe_summary": profile.short_description,
            "suggested_tags": list(profile.tags),
            "detected_themes": list(profile.themes),
            "confidence": profile.quality_score,
        })
        if progress:
            progress("Building Asset Intelligence")
        return run

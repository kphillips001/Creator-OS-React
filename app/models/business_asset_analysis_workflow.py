"""Provider-neutral Business Asset analysis workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.asset_intelligence import AssetIntelligenceStatus


PROVIDER_SEQUENCE = ("NUDENET", "VISION", "GROK", "CONTENT_INTELLIGENCE")
IMPLEMENTED_PROVIDERS = frozenset({"NUDENET"})


@dataclass(frozen=True)
class AnalysisWorkflowDecision:
    asset_id: int
    previous_state: AssetIntelligenceStatus
    current_state: AssetIntelligenceStatus
    next_provider: str | None = None
    dispatched: bool = False
    complete: bool = False
    retry_required: bool = False
    changed: bool = False

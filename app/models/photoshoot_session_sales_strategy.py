"""Versioned Photoshoot-only playbook consumed by the Session Sales Brain."""

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class SessionShotSalesRecommendation:
    asset_id: int
    shot_order: int
    sales_position: int
    sales_role: str
    teaser_recommended: bool
    access_recommendation: str
    recommended_progression: str
    suggested_next_asset_id: int | None
    customer_journey_purpose: str
    escalation_role: str
    psychological_objective: str
    conversation_goal: str


@dataclass(frozen=True)
class PhotoshootSessionSalesStrategy:
    photoshoot_session_id: str
    deliverable_id: UUID
    creator_profile_id: int
    strategy_version: str
    intelligence_version: str
    status: str
    best_teaser_asset_id: int
    recommended_customer_entry_point: str
    suggested_sales_progression: tuple[int, ...]
    recommended_stopping_points: tuple[Mapping[str, Any], ...]
    session_completion_strategy: str
    customer_engagement_strategy: str
    escalation_pacing: str
    overall_selling_approach: str
    shots: tuple[SessionShotSalesRecommendation, ...]
    model: str
    generated_at: datetime
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(
            self, "recommended_stopping_points",
            tuple(MappingProxyType(dict(item)) for item in self.recommended_stopping_points),
        )

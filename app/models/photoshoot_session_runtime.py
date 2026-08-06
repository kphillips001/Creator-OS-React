"""Deterministic execution state for one customer Photoshoot session."""

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


class PhotoshootSessionRuntimeStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    ABANDONED = "ABANDONED"


@dataclass(frozen=True)
class PhotoshootSessionRuntimeState:
    customer_commerce_profile_id: UUID
    photoshoot_session_id: str
    lifecycle_id: UUID | None
    status: PhotoshootSessionRuntimeStatus
    strategy_version: str
    current_position: int
    total_positions: int
    current_asset_id: int | None
    current_sales_role: str | None
    next_asset_id: int | None
    next_sales_role: str | None
    owned_asset_ids: tuple[int, ...]
    conversation_goal: str | None
    psychological_objective: str | None
    customer_engagement_strategy: str
    escalation_pacing: str
    session_completion_strategy: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_context(self) -> dict[str, Any]:
        return {
            "customerCommerceProfileId": str(self.customer_commerce_profile_id),
            "photoshootSessionId": self.photoshoot_session_id,
            "lifecycleId": str(self.lifecycle_id) if self.lifecycle_id else None,
            "sessionStatus": self.status.value,
            "strategyVersion": self.strategy_version,
            "currentPosition": self.current_position,
            "totalPositions": self.total_positions,
            "currentAssetId": self.current_asset_id,
            "currentSalesRole": self.current_sales_role,
            "nextAssetId": self.next_asset_id,
            "nextSalesRole": self.next_sales_role,
            "ownedAssetIds": list(self.owned_asset_ids),
            "conversationGoal": self.conversation_goal,
            "psychologicalObjective": self.psychological_objective,
            "customerEngagementStrategy": self.customer_engagement_strategy,
            "escalationPacing": self.escalation_pacing,
            "sessionCompletionStrategy": self.session_completion_strategy,
            "metadata": dict(self.metadata),
        }

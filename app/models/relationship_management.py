"""Provider-neutral Relationship Management recommendation read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class RelationshipRecommendationType(str, Enum):
    BUILD_TRUST = "BUILD_TRUST"
    CONTINUE_RELATIONSHIP = "CONTINUE_RELATIONSHIP"
    DELAY_SELLING = "DELAY_SELLING"
    INCREASE_SELLING = "INCREASE_SELLING"
    CONTINUE_EXPERIENCE = "CONTINUE_EXPERIENCE"
    VIP_OPPORTUNITY = "VIP_OPPORTUNITY"
    AT_RISK_CUSTOMER = "AT_RISK_CUSTOMER"
    DISENGAGED_CUSTOMER = "DISENGAGED_CUSTOMER"
    FOLLOW_UP = "FOLLOW_UP"
    RE_ENGAGE_CUSTOMER = "RE_ENGAGE_CUSTOMER"
    NO_RELATIONSHIP_ACTION = "NO_RELATIONSHIP_ACTION"


class RelationshipHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    TRUST_BUILDING = "TRUST_BUILDING"
    HEALTHY = "HEALTHY"
    SELLING_READY = "SELLING_READY"
    VIP_OPPORTUNITY = "VIP_OPPORTUNITY"
    AT_RISK = "AT_RISK"
    DISENGAGED = "DISENGAGED"


class RelationshipPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class RelationshipRecommendation:
    """Recommended relationship action for a customer."""

    recommendation_type: RelationshipRecommendationType
    relationship_health: RelationshipHealth = RelationshipHealth.UNKNOWN
    priority: RelationshipPriority = RelationshipPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Relationship Context"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    customer_reference: str | None = None
    experience_reference: str | None = None
    source: str = "RelationshipManagementService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationshipManagement:
    """Canonical read-only relationship state for one customer."""

    customer_id: str | None = None
    provider: str = "telegram"
    relationship_stage: str | None = None
    relationship_health: RelationshipHealth = RelationshipHealth.UNKNOWN
    engagement_score: int = 0
    engagement_level: str | None = None
    commerce_maturity: str | None = None
    recommendation: RelationshipRecommendation = field(
        default_factory=lambda: RelationshipRecommendation(
            recommendation_type=RelationshipRecommendationType.NO_RELATIONSHIP_ACTION,
            relationship_health=RelationshipHealth.UNKNOWN,
            priority=RelationshipPriority.LOW,
            recommended_next_action="No Relationship Action",
        )
    )
    recommendations: tuple[RelationshipRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

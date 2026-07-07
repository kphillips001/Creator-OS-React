"""Provider-neutral Customer Business read models.

Phase 3.4 introduces Customer Business as a canonical aggregation layer. These
models do not own Customer Intelligence, Telegram operations, Product state,
Publishing, Business Learning, Commerce Strategy, or runtime execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class CustomerBusinessHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    OPPORTUNITY = "OPPORTUNITY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    AT_RISK = "AT_RISK"
    DORMANT = "DORMANT"
    VIP = "VIP"


class CustomerBusinessLifecycleStage(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    DISCOVERY = "DISCOVERY"
    ACTIVE_RELATIONSHIP = "ACTIVE_RELATIONSHIP"
    EXPERIENCE_ACTIVE = "EXPERIENCE_ACTIVE"
    OFFER_ACTIVE = "OFFER_ACTIVE"
    CUSTOMER = "CUSTOMER"
    REPEAT_CUSTOMER = "REPEAT_CUSTOMER"
    VIP = "VIP"
    RETENTION = "RETENTION"
    DORMANT = "DORMANT"


class CustomerBusinessPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class CustomerJourneyStage(str, Enum):
    NEW_CUSTOMER = "NEW_CUSTOMER"
    RELATIONSHIP_BUILDING = "RELATIONSHIP_BUILDING"
    PRODUCT_DISCOVERY = "PRODUCT_DISCOVERY"
    ACTIVE_BUYER = "ACTIVE_BUYER"
    REPEAT_BUYER = "REPEAT_BUYER"
    VIP_GROWTH = "VIP_GROWTH"
    RETENTION = "RETENTION"
    RE_ENGAGEMENT = "RE_ENGAGEMENT"


class CustomerValueTier(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    ENGAGED = "ENGAGED"
    BUYER = "BUYER"
    REPEAT_BUYER = "REPEAT_BUYER"
    HIGH_VALUE = "HIGH_VALUE"
    VIP_POTENTIAL = "VIP_POTENTIAL"
    VIP = "VIP"
    AT_RISK = "AT_RISK"
    DORMANT = "DORMANT"


class CustomerValueTrend(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEW = "NEW"
    RISING = "RISING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"
    DORMANT = "DORMANT"


class CustomerRetentionRisk(str, Enum):
    HEALTHY = "HEALTHY"
    MONITOR = "MONITOR"
    COOLING_OFF = "COOLING_OFF"
    AT_RISK = "AT_RISK"
    DORMANT = "DORMANT"
    RE_ENGAGEMENT_CANDIDATE = "RE_ENGAGEMENT_CANDIDATE"
    RETAINED = "RETAINED"


class CustomerGrowthStage(str, Enum):
    EARLY_RELATIONSHIP = "EARLY_RELATIONSHIP"
    DISCOVERY = "DISCOVERY"
    ACTIVE_GROWTH = "ACTIVE_GROWTH"
    EXPANSION = "EXPANSION"
    REPEAT_BUYER = "REPEAT_BUYER"
    VIP_DEVELOPMENT = "VIP_DEVELOPMENT"
    MATURE_CUSTOMER = "MATURE_CUSTOMER"


@dataclass(frozen=True)
class CustomerGrowthSignal:
    """Provider-neutral growth signal derived from aggregate business evidence."""

    signal_type: str
    value: Any = None
    weight: float = 0.0
    source: str = "CustomerBusinessService"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerGrowthOpportunity:
    """Read-only long-term customer growth opportunity."""

    opportunity_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Continue nurturing"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerGrowthRecommendation:
    """Advisory recommendation for customer growth management."""

    recommendation_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Continue nurturing"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerGrowthSummary:
    """Canonical provider-neutral customer growth read model."""

    stage: CustomerGrowthStage = CustomerGrowthStage.EARLY_RELATIONSHIP
    opportunities: tuple[CustomerGrowthOpportunity, ...] = ()
    signals: tuple[CustomerGrowthSignal, ...] = ()
    expansion_readiness: str = "unknown"
    upsell_readiness: str = "unknown"
    cross_sell_readiness: str = "unknown"
    vip_growth_readiness: str = "unknown"
    recommended_growth_action: str = "Continue nurturing"
    recommendations: tuple[CustomerGrowthRecommendation, ...] = ()
    confidence: float = 0.0
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class CustomerRetentionSignal:
    """Provider-neutral signal used to assess retention state."""

    signal_type: str
    value: Any = None
    weight: float = 0.0
    source: str = "CustomerBusinessService"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerRetentionOpportunity:
    """Read-only retention opportunity for one customer."""

    opportunity_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Recommend follow-up"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerRetentionRecommendation:
    """Advisory retention recommendation."""

    recommendation_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Continue relationship building"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerRetentionSummary:
    """Canonical provider-neutral retention read model."""

    risk: CustomerRetentionRisk = CustomerRetentionRisk.MONITOR
    signals: tuple[CustomerRetentionSignal, ...] = ()
    opportunities: tuple[CustomerRetentionOpportunity, ...] = ()
    re_engagement_readiness: str = "unknown"
    last_engagement_summary: Mapping[str, Any] = field(default_factory=dict)
    recommended_follow_up: str | None = None
    recommendations: tuple[CustomerRetentionRecommendation, ...] = ()
    confidence: float = 0.0
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class CustomerValueSignal:
    """Provider-neutral value signal derived from existing business evidence."""

    signal_type: str
    value: Any = None
    weight: float = 0.0
    source: str = "CustomerBusinessService"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerValueRecommendation:
    """Advisory recommendation for customer value management."""

    recommendation_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Build relationship"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerValueSummary:
    """Canonical provider-neutral customer value read model."""

    tier: CustomerValueTier = CustomerValueTier.UNKNOWN
    trend: CustomerValueTrend = CustomerValueTrend.UNKNOWN
    signals: tuple[CustomerValueSignal, ...] = ()
    lifetime_value_summary: Mapping[str, Any] = field(default_factory=dict)
    purchase_potential: str = "unknown"
    vip_potential: bool = False
    retention_risk: str = "unknown"
    growth_opportunities: tuple[str, ...] = ()
    recommendations: tuple[CustomerValueRecommendation, ...] = ()
    confidence: float = 0.0
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class CustomerJourneyMilestone:
    """Read-only milestone in a customer's long-term business journey."""

    milestone_id: str
    label: str
    completed: bool = False
    source: str = "CustomerBusinessService"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerJourneyProgress:
    """Deterministic journey progress projection."""

    stage: CustomerJourneyStage = CustomerJourneyStage.NEW_CUSTOMER
    completed_count: int = 0
    total_count: int = 0
    progress_percentage: int = 0
    confidence: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerJourneyRecommendation:
    """Advisory customer journey recommendation."""

    recommendation_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Continue relationship"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerJourneySummary:
    """Canonical provider-neutral customer journey read model."""

    stage: CustomerJourneyStage = CustomerJourneyStage.NEW_CUSTOMER
    completed_milestones: tuple[CustomerJourneyMilestone, ...] = ()
    next_milestone: CustomerJourneyMilestone | None = None
    progress: CustomerJourneyProgress = field(default_factory=CustomerJourneyProgress)
    current_experience_progress: Mapping[str, Any] = field(default_factory=dict)
    recommended_next_experience: str | None = None
    recommended_next_product_discovery: str | None = None
    recommendations: tuple[CustomerJourneyRecommendation, ...] = ()
    confidence: float = 0.0
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)


@dataclass(frozen=True)
class CustomerBusinessOpportunity:
    """Read-only business opportunity surfaced for one customer."""

    opportunity_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Review Customer"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerBusinessRecommendation:
    """Advisory next action for Customer Business consumers."""

    recommendation_type: str
    priority: CustomerBusinessPriority = CustomerBusinessPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Customer"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "CustomerBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerBusinessSummary:
    """Compact provider-neutral Customer Business summary."""

    customer_id: str | None = None
    display_name: str | None = None
    provider: str = "provider_neutral"
    relationship_stage: str | None = None
    lifecycle_stage: CustomerBusinessLifecycleStage = (
        CustomerBusinessLifecycleStage.UNKNOWN
    )
    health: CustomerBusinessHealth = CustomerBusinessHealth.UNKNOWN
    current_journey: str = "unknown"
    current_experience_id: str | None = None
    current_product_ids: tuple[str, ...] = ()
    active_offer_ids: tuple[str, ...] = ()
    opportunity_count: int = 0
    recommendation_count: int = 0
    next_recommended_action: str = "Review Customer"
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerBusinessSnapshot:
    """Canonical provider-neutral business state for one customer."""

    customer_id: str | None = None
    provider: str = "provider_neutral"
    customer_identity: Mapping[str, Any] = field(default_factory=dict)
    relationship_stage: str | None = None
    lifecycle_stage: CustomerBusinessLifecycleStage = (
        CustomerBusinessLifecycleStage.UNKNOWN
    )
    customer_health: CustomerBusinessHealth = CustomerBusinessHealth.UNKNOWN
    current_journey: CustomerJourneySummary = field(default_factory=CustomerJourneySummary)
    journey_stage: CustomerJourneyStage = CustomerJourneyStage.NEW_CUSTOMER
    completed_milestones: tuple[CustomerJourneyMilestone, ...] = ()
    next_milestone: CustomerJourneyMilestone | None = None
    current_experience_progress: Mapping[str, Any] = field(default_factory=dict)
    recommended_next_experience: str | None = None
    recommended_next_product_discovery: str | None = None
    journey_confidence: float = 0.0
    customer_value: CustomerValueSummary = field(default_factory=CustomerValueSummary)
    value_tier: CustomerValueTier = CustomerValueTier.UNKNOWN
    value_trend: CustomerValueTrend = CustomerValueTrend.UNKNOWN
    value_signals: tuple[CustomerValueSignal, ...] = ()
    lifetime_value_summary: Mapping[str, Any] = field(default_factory=dict)
    purchase_potential: str = "unknown"
    vip_potential: bool = False
    retention_risk: str = "unknown"
    retention_summary: CustomerRetentionSummary = field(
        default_factory=CustomerRetentionSummary
    )
    retention_signals: tuple[CustomerRetentionSignal, ...] = ()
    retention_opportunities: tuple[CustomerRetentionOpportunity, ...] = ()
    re_engagement_readiness: str = "unknown"
    last_engagement_summary: Mapping[str, Any] = field(default_factory=dict)
    recommended_follow_up: str | None = None
    retention_confidence: float = 0.0
    growth_summary: CustomerGrowthSummary = field(default_factory=CustomerGrowthSummary)
    growth_stage: CustomerGrowthStage = CustomerGrowthStage.EARLY_RELATIONSHIP
    growth_opportunities: tuple[CustomerGrowthOpportunity, ...] = ()
    growth_signals: tuple[CustomerGrowthSignal, ...] = ()
    expansion_readiness: str = "unknown"
    upsell_readiness: str = "unknown"
    cross_sell_readiness: str = "unknown"
    vip_growth_readiness: str = "unknown"
    recommended_growth_action: str = "Continue nurturing"
    growth_confidence: float = 0.0
    experience_progress: Mapping[str, Any] = field(default_factory=dict)
    product_discovery: Mapping[str, Any] = field(default_factory=dict)
    commerce_readiness: Mapping[str, Any] = field(default_factory=dict)
    telegram_business: Mapping[str, Any] = field(default_factory=dict)
    sales_signals: Mapping[str, Any] = field(default_factory=dict)
    delivery_signals: Mapping[str, Any] = field(default_factory=dict)
    relationship_signals: Mapping[str, Any] = field(default_factory=dict)
    business_learning_evidence: Mapping[str, Any] = field(default_factory=dict)
    opportunities: tuple[CustomerBusinessOpportunity, ...] = ()
    recommendations: tuple[CustomerBusinessRecommendation, ...] = ()
    next_recommended_action: str = "Review Customer"
    summary: CustomerBusinessSummary = field(default_factory=CustomerBusinessSummary)
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

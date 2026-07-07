"""Provider-neutral Business Optimization read models.

Business Optimization is a canonical aggregation layer. It does not own Product
Business, Telegram operations, Customer Business, Product Strategy, Commerce
Strategy, Publishing execution, Business Learning, or runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class BusinessOptimizationHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    OPPORTUNITY = "OPPORTUNITY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    AT_RISK = "AT_RISK"


class BusinessOptimizationPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BusinessPerformanceHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    OPPORTUNITY = "OPPORTUNITY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    AT_RISK = "AT_RISK"


class BusinessPerformanceTrend(str, Enum):
    UNKNOWN = "UNKNOWN"
    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"
    MIXED = "MIXED"


class BusinessStrategyHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    OPPORTUNITY = "OPPORTUNITY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    AT_RISK = "AT_RISK"


class BusinessOpportunityCategory(str, Enum):
    UNKNOWN = "UNKNOWN"
    REVENUE = "REVENUE"
    CUSTOMER = "CUSTOMER"
    PRODUCT = "PRODUCT"
    PUBLISHING = "PUBLISHING"
    STRATEGY = "STRATEGY"
    TELEGRAM = "TELEGRAM"
    LEARNING = "LEARNING"


class BusinessOpportunityImpact(str, Enum):
    UNKNOWN = "UNKNOWN"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BusinessRecommendationPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BusinessRecommendationCategory(str, Enum):
    UNKNOWN = "UNKNOWN"
    PRODUCT = "PRODUCT"
    TELEGRAM = "TELEGRAM"
    CUSTOMER = "CUSTOMER"
    STRATEGY = "STRATEGY"
    PUBLISHING = "PUBLISHING"
    LEARNING = "LEARNING"
    REVENUE = "REVENUE"


@dataclass(frozen=True)
class BusinessPerformanceSignal:
    """Provider-neutral performance signal derived from existing domains."""

    signal_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    detail: str = "Review Business Performance"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessPerformanceRecommendation:
    """Advisory recommendation for improving overall business performance."""

    recommendation_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Business Performance"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessPerformanceSummary:
    """Compact provider-neutral performance summary."""

    health: BusinessPerformanceHealth = BusinessPerformanceHealth.UNKNOWN
    trend: BusinessPerformanceTrend = BusinessPerformanceTrend.UNKNOWN
    confidence: float = 0.0
    signal_count: int = 0
    recommendation_count: int = 0
    recommendations: tuple[BusinessPerformanceRecommendation, ...] = ()
    next_recommended_performance_action: str = "Review Business Performance"
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessRecommendationSignal:
    """Provider-neutral signal used to build a unified business action plan."""

    signal_type: str
    category: BusinessRecommendationCategory = BusinessRecommendationCategory.UNKNOWN
    priority: BusinessRecommendationPriority = BusinessRecommendationPriority.MEDIUM
    confidence: float = 0.0
    recommended_action: str = "Review Business Recommendation"
    timeframe: str = "this_week"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessRecommendationAction:
    """Prioritized advisory business action."""

    action_type: str
    category: BusinessRecommendationCategory = BusinessRecommendationCategory.UNKNOWN
    priority: BusinessRecommendationPriority = BusinessRecommendationPriority.MEDIUM
    confidence: float = 0.0
    recommended_action: str = "Review Business Recommendation"
    timeframe: str = "this_week"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessRecommendationSummary:
    """Unified provider-neutral business action plan summary."""

    recommendation_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    today_count: int = 0
    this_week_count: int = 0
    confidence: float = 0.0
    next_recommended_action: str = "Review Business Recommendations"
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOpportunitySignal:
    """Provider-neutral opportunity signal across Creator OS business domains."""

    opportunity_type: str
    category: BusinessOpportunityCategory = BusinessOpportunityCategory.UNKNOWN
    impact: BusinessOpportunityImpact = BusinessOpportunityImpact.MEDIUM
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Review Business Opportunity"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOpportunityRecommendation:
    """Advisory recommendation for prioritizing a business opportunity."""

    recommendation_type: str
    category: BusinessOpportunityCategory = BusinessOpportunityCategory.UNKNOWN
    impact: BusinessOpportunityImpact = BusinessOpportunityImpact.MEDIUM
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Business Opportunity"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOpportunitySummary:
    """Compact provider-neutral opportunity summary."""

    opportunity_count: int = 0
    high_impact_count: int = 0
    revenue_count: int = 0
    customer_count: int = 0
    product_count: int = 0
    publishing_count: int = 0
    strategy_count: int = 0
    confidence: float = 0.0
    recommendation_count: int = 0
    recommended_opportunity_actions: tuple[str, ...] = ()
    recommendations: tuple[BusinessOpportunityRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessStrategySignal:
    """Provider-neutral signal for overall business strategy quality."""

    signal_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    detail: str = "Review Business Strategy"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessStrategyOpportunity:
    """Advisory strategy opportunity derived from existing strategy domains."""

    opportunity_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Review Business Strategy"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessStrategyRecommendation:
    """Provider-neutral advisory strategy recommendation."""

    recommendation_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Business Strategy"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessStrategySummary:
    """Compact provider-neutral strategy optimization summary."""

    health: BusinessStrategyHealth = BusinessStrategyHealth.UNKNOWN
    confidence: float = 0.0
    signal_count: int = 0
    opportunity_count: int = 0
    recommendation_count: int = 0
    recommended_strategy_actions: tuple[str, ...] = ()
    recommendations: tuple[BusinessStrategyRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOptimizationOpportunity:
    """Read-only cross-domain business optimization opportunity."""

    opportunity_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_action: str = "Review Business"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOptimizationRecommendation:
    """Advisory recommendation for whole-business optimization."""

    recommendation_type: str
    priority: BusinessOptimizationPriority = BusinessOptimizationPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Business"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "BusinessOptimizationService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOptimizationSummary:
    """Compact provider-neutral Business Optimization summary."""

    health: BusinessOptimizationHealth = BusinessOptimizationHealth.UNKNOWN
    revenue_readiness: str = "unknown"
    risk_count: int = 0
    opportunity_count: int = 0
    recommendation_count: int = 0
    next_recommended_business_action: str = "Review Business"
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOptimizationSnapshot:
    """Canonical provider-neutral optimization view across Creator OS."""

    health: BusinessOptimizationHealth = BusinessOptimizationHealth.UNKNOWN
    product_business_summary: Mapping[str, Any] = field(default_factory=dict)
    telegram_business_summary: Mapping[str, Any] = field(default_factory=dict)
    customer_business_summary: Mapping[str, Any] = field(default_factory=dict)
    product_strategy_summary: Mapping[str, Any] = field(default_factory=dict)
    commerce_strategy_summary: Mapping[str, Any] = field(default_factory=dict)
    publishing_summary: Mapping[str, Any] = field(default_factory=dict)
    business_learning_summary: Mapping[str, Any] = field(default_factory=dict)
    revenue_readiness: str = "unknown"
    performance_summary: BusinessPerformanceSummary = field(
        default_factory=BusinessPerformanceSummary
    )
    performance_health: BusinessPerformanceHealth = BusinessPerformanceHealth.UNKNOWN
    performance_trend: BusinessPerformanceTrend = BusinessPerformanceTrend.UNKNOWN
    performance_signals: tuple[BusinessPerformanceSignal, ...] = ()
    product_performance_summary: Mapping[str, Any] = field(default_factory=dict)
    customer_performance_summary: Mapping[str, Any] = field(default_factory=dict)
    commerce_performance_summary: Mapping[str, Any] = field(default_factory=dict)
    publishing_performance_summary: Mapping[str, Any] = field(default_factory=dict)
    performance_confidence: float = 0.0
    strategy_summary: BusinessStrategySummary = field(
        default_factory=BusinessStrategySummary
    )
    strategy_health: BusinessStrategyHealth = BusinessStrategyHealth.UNKNOWN
    strategy_signals: tuple[BusinessStrategySignal, ...] = ()
    strategy_opportunities: tuple[BusinessStrategyOpportunity, ...] = ()
    strategy_confidence: float = 0.0
    recommended_strategy_actions: tuple[str, ...] = ()
    opportunity_summary: BusinessOpportunitySummary = field(
        default_factory=BusinessOpportunitySummary
    )
    opportunity_categories: tuple[BusinessOpportunityCategory, ...] = ()
    opportunity_signals: tuple[BusinessOpportunitySignal, ...] = ()
    high_impact_opportunities: tuple[BusinessOpportunitySignal, ...] = ()
    revenue_opportunities: tuple[BusinessOpportunitySignal, ...] = ()
    customer_opportunities: tuple[BusinessOpportunitySignal, ...] = ()
    product_opportunities: tuple[BusinessOpportunitySignal, ...] = ()
    publishing_opportunities: tuple[BusinessOpportunitySignal, ...] = ()
    strategy_opportunity_signals: tuple[BusinessOpportunitySignal, ...] = ()
    recommended_opportunity_actions: tuple[str, ...] = ()
    opportunity_confidence: float = 0.0
    recommendation_summary: BusinessRecommendationSummary = field(
        default_factory=BusinessRecommendationSummary
    )
    prioritized_recommendations: tuple[BusinessRecommendationAction, ...] = ()
    recommendation_categories: tuple[BusinessRecommendationCategory, ...] = ()
    recommendation_signals: tuple[BusinessRecommendationSignal, ...] = ()
    recommended_today_actions: tuple[BusinessRecommendationAction, ...] = ()
    recommended_this_week_actions: tuple[BusinessRecommendationAction, ...] = ()
    recommendation_confidence: float = 0.0
    business_risks: tuple[Mapping[str, Any], ...] = ()
    opportunities: tuple[BusinessOptimizationOpportunity, ...] = ()
    recommendations: tuple[BusinessOptimizationRecommendation, ...] = ()
    next_recommended_business_action: str = "Review Business"
    summary: BusinessOptimizationSummary = field(
        default_factory=BusinessOptimizationSummary
    )
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

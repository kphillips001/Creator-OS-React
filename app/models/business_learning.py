"""Provider-neutral Business Learning read models.

Business Learning is the canonical analytics and learning boundary for Creator
OS. These models describe historical outcomes and evidence only; they do not
make decisions, execute commerce, or mutate strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class BusinessOutcomeType(str, Enum):
    PRODUCT_OFFERED = "PRODUCT_OFFERED"
    PRODUCT_PURCHASED = "PRODUCT_PURCHASED"
    PRODUCT_DELIVERED = "PRODUCT_DELIVERED"
    PRODUCT_DECLINED = "PRODUCT_DECLINED"
    BUNDLE_PURCHASED = "BUNDLE_PURCHASED"
    STORY_COMPLETED = "STORY_COMPLETED"
    PHOTOSHOOT_PURCHASED = "PHOTOSHOOT_PURCHASED"
    FREE_ASSET_DELIVERED = "FREE_ASSET_DELIVERED"
    CONVERSATION_CONTINUED = "CONVERSATION_CONTINUED"
    CONVERSATION_ENDED = "CONVERSATION_ENDED"
    CTA_PRESENTED = "CTA_PRESENTED"
    CTA_CLICKED = "CTA_CLICKED"
    EXPERIENCE_COMPLETED = "EXPERIENCE_COMPLETED"


@dataclass(frozen=True)
class LearningMetadata:
    source: str = "business_learning"
    owner: str = "BusinessLearningService"
    provider_neutral: bool = True
    read_only: bool = True
    generates_decisions: bool = False
    executes_commerce: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessOutcome:
    outcome_id: str | None = None
    outcome_type: str | None = None
    timestamp: str | None = None
    subject_type: str | None = None
    subject_id: str | None = None
    customer_id: str | None = None
    customer_reference: str | None = None
    product_id: str | None = None
    product_reference: str | None = None
    experience_id: str | None = None
    experience_reference: str | None = None
    strategy_source: str | None = None
    recommendation_id: str | None = None
    status: str | None = None
    value_cents: int = 0
    occurred_at: str | None = None
    signals: Mapping[str, Any] = field(default_factory=dict)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    evidence_metadata: Mapping[str, Any] = field(default_factory=dict)
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessPerformanceSummary:
    total_outcomes: int = 0
    successful_outcomes: int = 0
    failed_outcomes: int = 0
    neutral_outcomes: int = 0
    total_value_cents: int = 0
    outcome_type_counts: Mapping[str, int] = field(default_factory=dict)
    strategy_source_counts: Mapping[str, int] = field(default_factory=dict)
    success_rate: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerformanceEvidence:
    evidence_type: str | None = None
    outcome_ids: tuple[str, ...] = ()
    outcome_types: tuple[str, ...] = ()
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerformanceMetric:
    metric_name: str
    metric_type: str
    count: int = 0
    success_count: int = 0
    failure_count: int = 0
    neutral_count: int = 0
    success_rate: float = 0.0
    confidence: float = 0.0
    supporting_evidence: tuple[PerformanceEvidence, ...] = ()
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerformanceSnapshot:
    metrics: tuple[PerformanceMetric, ...] = ()
    summary: Mapping[str, Any] = field(default_factory=dict)
    metadata: LearningMetadata = field(default_factory=LearningMetadata)


@dataclass(frozen=True)
class RecommendationEvidence:
    recommendation_id: str | None = None
    strategy_source: str | None = None
    evidence_type: str | None = None
    confidence: float = 0.0
    supporting_outcome_ids: tuple[str, ...] = ()
    positive_signal_count: int = 0
    negative_signal_count: int = 0
    rationale: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningInsight:
    insight_id: str | None = None
    insight_type: str | None = None
    subject: str | None = None
    description: str | None = None
    confidence: float = 0.0
    supporting_metric_types: tuple[str, ...] = ()
    supporting_outcome_ids: tuple[str, ...] = ()
    recommendation_evidence: tuple[RecommendationEvidence, ...] = ()
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningRecommendation:
    recommendation_id: str | None = None
    recommendation_type: str | None = None
    summary: str | None = None
    evidence: tuple[RecommendationEvidence, ...] = ()
    confidence: float = 0.0
    supporting_insight_ids: tuple[str, ...] = ()
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningSummary:
    total_insights: int = 0
    total_recommendations: int = 0
    top_performer_count: int = 0
    underperformer_count: int = 0
    average_confidence: float = 0.0
    insight_types: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningContext:
    context_type: str
    subject_reference: str | None = None
    learning_summary: LearningSummary = field(default_factory=LearningSummary)
    recommendation_evidence: tuple[RecommendationEvidence, ...] = ()
    learning_insights: tuple[LearningInsight, ...] = ()
    learning_recommendations: tuple[LearningRecommendation, ...] = ()
    performance_snapshot: PerformanceSnapshot = field(default_factory=PerformanceSnapshot)
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessLearningReviewSummary:
    total_outcomes: int = 0
    total_metrics: int = 0
    total_insights: int = 0
    recommendation_evidence_count: int = 0
    top_performer_count: int = 0
    underperformer_count: int = 0
    average_confidence: float = 0.0
    has_learning_history: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessLearningReview:
    outcomes: tuple[BusinessOutcome, ...] = ()
    performance_metrics: tuple[PerformanceMetric, ...] = ()
    learning_insights: tuple[LearningInsight, ...] = ()
    recommendation_evidence: tuple[RecommendationEvidence, ...] = ()
    top_performers: tuple[PerformanceMetric, ...] = ()
    underperformers: tuple[PerformanceMetric, ...] = ()
    historical_comparisons: Mapping[str, Any] = field(default_factory=dict)
    learning_summary: LearningSummary = field(default_factory=LearningSummary)
    review_summary: BusinessLearningReviewSummary = field(
        default_factory=BusinessLearningReviewSummary
    )
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BusinessLearningSnapshot:
    outcomes: tuple[BusinessOutcome, ...] = ()
    outcome_categories: Mapping[str, tuple[BusinessOutcome, ...]] = field(
        default_factory=dict
    )
    outcome_summary: Mapping[str, Any] = field(default_factory=dict)
    performance_summary: BusinessPerformanceSummary = field(
        default_factory=BusinessPerformanceSummary
    )
    performance_snapshot: PerformanceSnapshot = field(default_factory=PerformanceSnapshot)
    recommendation_evidence: tuple[RecommendationEvidence, ...] = ()
    learning_insights: tuple[LearningInsight, ...] = ()
    learning_recommendations: tuple[LearningRecommendation, ...] = ()
    learning_intelligence_summary: LearningSummary = field(default_factory=LearningSummary)
    learning_summary: Mapping[str, Any] = field(default_factory=dict)
    metadata: LearningMetadata = field(default_factory=LearningMetadata)

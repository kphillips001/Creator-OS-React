"""Provider-neutral Content Opportunity Intelligence read models.

Content Opportunity owns customer demand signals, matched requests, unmatched
requests, opportunity signals, demand trends, and future content opportunity
summaries. It does not own Products, Experiences, Publishing, Telegram,
DecisionEngine behavior, Customer Intelligence, Business Learning, Product
Strategy, or Commerce Strategy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class ContentOpportunityStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    MATCHED = "MATCHED"
    UNMATCHED = "UNMATCHED"
    PENDING = "PENDING"


class ContentOpportunitySource(str, Enum):
    UNKNOWN = "UNKNOWN"
    TELEGRAM = "TELEGRAM"
    CREATOR_AGENT = "CREATOR_AGENT"
    CREATOR_HQ = "CREATOR_HQ"
    MANUAL = "MANUAL"
    IMPORT = "IMPORT"


class ContentOpportunityMatchType(str, Enum):
    NONE = "NONE"
    PRODUCT = "PRODUCT"
    EXPERIENCE = "EXPERIENCE"
    ASSET = "ASSET"
    MIXED = "MIXED"


class ContentOpportunityPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContentOpportunityRecommendationType(str, Enum):
    CREATE_NEW_EXPERIENCE = "CREATE_NEW_EXPERIENCE"
    CREATE_NEW_PRODUCT = "CREATE_NEW_PRODUCT"
    CREATE_BUNDLE = "CREATE_BUNDLE"
    EXPAND_EXISTING_EXPERIENCE = "EXPAND_EXISTING_EXPERIENCE"
    CREATE_STORY = "CREATE_STORY"
    CREATE_VIDEO = "CREATE_VIDEO"
    CREATE_FREE_PREVIEW = "CREATE_FREE_PREVIEW"
    IMPROVE_PUBLISHING_READINESS = "IMPROVE_PUBLISHING_READINESS"
    REUSE_EXISTING_MATCHED_PRODUCT = "REUSE_EXISTING_MATCHED_PRODUCT"
    PROMOTE_EXISTING_PRODUCT_WITH_DEMAND = "PROMOTE_EXISTING_PRODUCT_WITH_DEMAND"


class ContentOpportunityRecommendationPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContentOpportunityResolutionStatus(str, Enum):
    RESOLUTION_READY = "RESOLUTION_READY"
    RESOLVED = "RESOLVED"
    FOLLOW_UP_PENDING = "FOLLOW_UP_PENDING"
    FOLLOW_UP_CREATED = "FOLLOW_UP_CREATED"
    EXPIRED = "EXPIRED"
    IGNORED = "IGNORED"


class ContentOpportunityResolutionSource(str, Enum):
    UNKNOWN = "UNKNOWN"
    PRODUCT = "PRODUCT"
    EXPERIENCE = "EXPERIENCE"
    ASSET = "ASSET"
    NEW_CONTENT = "NEW_CONTENT"
    MANUAL = "MANUAL"


class ContentOpportunityFollowUpStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    PRESENTED = "PRESENTED"
    COMPLETED = "COMPLETED"
    IGNORED = "IGNORED"
    EXPIRED = "EXPIRED"


class ContentOpportunityFollowUpPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ContentOpportunityHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    OPPORTUNITY = "OPPORTUNITY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    HIGH_DEMAND = "HIGH_DEMAND"


class ContentDemandTrend(str, Enum):
    UNKNOWN = "UNKNOWN"
    STABLE = "STABLE"
    GROWING = "GROWING"
    DECLINING = "DECLINING"
    SATISFIED = "SATISFIED"
    UNSATISFIED = "UNSATISFIED"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ContentDemandSignal:
    """Canonical provider-neutral signal that a customer requested content."""

    signal_id: str
    customer_id: str | None = None
    provider: str = "provider_neutral"
    provider_customer_id: str | None = None
    request_text: str = ""
    normalized_terms: tuple[str, ...] = ()
    requested_content_type: str | None = None
    requested_format: str | None = None
    source: ContentOpportunitySource = ContentOpportunitySource.UNKNOWN
    conversation_id: str | None = None
    message_id: str | None = None
    source_metadata: Mapping[str, Any] = field(default_factory=dict)
    is_vip: bool = False
    customer_importance: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentRequestMatch:
    """Read-only evidence that existing content satisfies a demand signal."""

    match_id: str
    demand_signal: ContentDemandSignal
    match_type: ContentOpportunityMatchType = ContentOpportunityMatchType.NONE
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    status: ContentOpportunityStatus = ContentOpportunityStatus.MATCHED
    can_offer_existing_content: bool = False
    match_evidence: Mapping[str, Any] = field(default_factory=dict)
    safe_response_guidance: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunity:
    """Canonical matched or unmatched customer demand opportunity."""

    opportunity_id: str
    demand_signal: ContentDemandSignal
    status: ContentOpportunityStatus = ContentOpportunityStatus.UNKNOWN
    priority: ContentOpportunityPriority = ContentOpportunityPriority.NORMAL
    normalized_terms: tuple[str, ...] = ()
    demand_count: int = 1
    match: ContentRequestMatch | None = None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    asset_ids: tuple[str, ...] = ()
    confidence: float = 0.0
    repeat_demand: bool = False
    vip_demand: bool = False
    safe_response_guidance: Mapping[str, Any] = field(default_factory=dict)
    next_recommended_action: str = "Review content opportunity"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunityRecommendationEvidence:
    """Evidence supporting an advisory creator recommendation."""

    topic_key: str
    request_count: int = 0
    customer_count: int = 0
    vip_customer_count: int = 0
    matched_request_count: int = 0
    unmatched_request_count: int = 0
    matched_percentage: float = 0.0
    unmet_percentage: float = 0.0
    customer_segments: Mapping[str, int] = field(default_factory=dict)
    requested_formats: Mapping[str, int] = field(default_factory=dict)
    requested_content_types: Mapping[str, int] = field(default_factory=dict)
    match_statistics: Mapping[str, Any] = field(default_factory=dict)
    source: str = "ContentOpportunityService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunityRecommendation:
    """Provider-neutral advisory recommendation for the creator."""

    recommendation_id: str
    recommendation_type: ContentOpportunityRecommendationType
    title: str
    summary: str
    normalized_terms: tuple[str, ...] = ()
    requested_content_type: str | None = None
    requested_format: str | None = None
    priority: ContentOpportunityRecommendationPriority = (
        ContentOpportunityRecommendationPriority.NORMAL
    )
    confidence: float = 0.0
    evidence: ContentOpportunityRecommendationEvidence = field(
        default_factory=lambda: ContentOpportunityRecommendationEvidence(topic_key="")
    )
    related_opportunity_ids: tuple[str, ...] = ()
    related_product_ids: tuple[str, ...] = ()
    related_experience_ids: tuple[str, ...] = ()
    related_asset_ids: tuple[str, ...] = ()
    customer_count: int = 0
    vip_customer_count: int = 0
    request_count: int = 0
    matched_request_count: int = 0
    unmatched_request_count: int = 0
    safe_creator_note: str = (
        "Advisory only. The creator owns creative decisions and customer communication."
    )
    created_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunityResolution:
    """Provider-neutral resolution record for previously unmet demand."""

    resolution_id: str
    opportunity_id: str
    normalized_terms: tuple[str, ...] = ()
    matched_product_ids: tuple[str, ...] = ()
    matched_experience_ids: tuple[str, ...] = ()
    matched_asset_ids: tuple[str, ...] = ()
    waiting_customer_ids: tuple[str, ...] = ()
    waiting_provider_customer_ids: tuple[str, ...] = ()
    request_count: int = 0
    customer_count: int = 0
    vip_customer_count: int = 0
    confidence: float = 0.0
    evidence: Mapping[str, Any] = field(default_factory=dict)
    status: ContentOpportunityResolutionStatus = (
        ContentOpportunityResolutionStatus.RESOLUTION_READY
    )
    source: ContentOpportunityResolutionSource = (
        ContentOpportunityResolutionSource.UNKNOWN
    )
    safe_guidance: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    notes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunityFollowUp:
    """Provider-neutral follow-up opportunity for resolved customer demand."""

    follow_up_id: str
    resolution_id: str
    opportunity_id: str
    customer_id: str | None = None
    provider: str = "provider_neutral"
    provider_customer_id: str | None = None
    matched_product_ids: tuple[str, ...] = ()
    matched_experience_ids: tuple[str, ...] = ()
    matched_asset_ids: tuple[str, ...] = ()
    original_request_text: str = ""
    normalized_terms: tuple[str, ...] = ()
    vip_customer: bool = False
    priority: ContentOpportunityFollowUpPriority = (
        ContentOpportunityFollowUpPriority.NORMAL
    )
    confidence: float = 0.0
    evidence: Mapping[str, Any] = field(default_factory=dict)
    status: ContentOpportunityFollowUpStatus = ContentOpportunityFollowUpStatus.READY
    safe_guidance: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    completed_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentDemandTopicSummary:
    """Aggregated demand intelligence for a normalized request topic."""

    topic_key: str
    terms: tuple[str, ...] = ()
    request_count: int = 0
    matched_count: int = 0
    unmatched_count: int = 0
    matched_percentage: float = 0.0
    unmet_percentage: float = 0.0
    unique_customers: int = 0
    vip_request_count: int = 0
    customer_segments: Mapping[str, int] = field(default_factory=dict)
    requested_content_types: Mapping[str, int] = field(default_factory=dict)
    requested_formats: Mapping[str, int] = field(default_factory=dict)
    trend: ContentDemandTrend = ContentDemandTrend.STABLE
    priority: ContentOpportunityPriority = ContentOpportunityPriority.NORMAL
    opportunity_health: ContentOpportunityHealth = ContentOpportunityHealth.UNKNOWN
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentDemandSummary:
    """Top-level provider-neutral demand intelligence summary."""

    total_requests: int = 0
    matched_requests: int = 0
    unmatched_requests: int = 0
    matched_percentage: float = 0.0
    unmet_percentage: float = 0.0
    repeat_request_count: int = 0
    vip_request_count: int = 0
    unique_customers: int = 0
    demand_by_content_type: Mapping[str, int] = field(default_factory=dict)
    demand_by_format: Mapping[str, int] = field(default_factory=dict)
    demand_by_customer_segment: Mapping[str, int] = field(default_factory=dict)
    opportunity_health: ContentOpportunityHealth = ContentOpportunityHealth.UNKNOWN
    evidence: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContentOpportunitySnapshot:
    """Read-only Content Opportunity Intelligence summary for future consumers."""

    demand_signals: tuple[ContentDemandSignal, ...] = ()
    matched_requests: tuple[ContentRequestMatch, ...] = ()
    unmatched_opportunities: tuple[ContentOpportunity, ...] = ()
    opportunities: tuple[ContentOpportunity, ...] = ()
    repeat_demand_terms: Mapping[str, int] = field(default_factory=dict)
    vip_opportunities: tuple[ContentOpportunity, ...] = ()
    next_recommended_actions: tuple[str, ...] = ()
    matched_count: int = 0
    unmatched_count: int = 0
    repeat_demand_count: int = 0
    vip_demand_count: int = 0
    total_requests: int = 0
    matched_percentage: float = 0.0
    unmet_percentage: float = 0.0
    repeat_request_count: int = 0
    vip_request_count: int = 0
    unique_customers: int = 0
    top_requested_topics: tuple[ContentDemandTopicSummary, ...] = ()
    trending_topics: tuple[ContentDemandTopicSummary, ...] = ()
    growing_topics: tuple[ContentDemandTopicSummary, ...] = ()
    satisfied_topics: tuple[ContentDemandTopicSummary, ...] = ()
    unsatisfied_topics: tuple[ContentDemandTopicSummary, ...] = ()
    demand_by_content_type: Mapping[str, int] = field(default_factory=dict)
    demand_by_format: Mapping[str, int] = field(default_factory=dict)
    demand_by_customer_segment: Mapping[str, int] = field(default_factory=dict)
    highest_priority_opportunities: tuple[ContentOpportunity, ...] = ()
    opportunity_health: ContentOpportunityHealth = ContentOpportunityHealth.UNKNOWN
    demand_summary: ContentDemandSummary = field(default_factory=ContentDemandSummary)
    creator_recommendations: tuple[ContentOpportunityRecommendation, ...] = ()
    recommendation_count: int = 0
    resolution_records: tuple[ContentOpportunityResolution, ...] = ()
    resolution_ready_count: int = 0
    waiting_customers: tuple[Mapping[str, Any], ...] = ()
    waiting_customer_count: int = 0
    follow_up_opportunities: tuple[ContentOpportunityFollowUp, ...] = ()
    pending_follow_up_count: int = 0
    ready_follow_up_count: int = 0
    safe_response_guidance: Mapping[str, Any] = field(default_factory=dict)
    summary: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

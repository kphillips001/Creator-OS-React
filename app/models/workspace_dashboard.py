"""Presentation models for the Creator Workspace dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from app.models.creator_attention import CreatorAttentionSummary
from app.models.creator_review_optimization import CreatorReviewStatus
from app.models.creator_workflow import CreatorWorkflowSnapshot
from app.models.product_lifecycle import ProductLifecycle
from app.models.creator_review import CreatorReviewDashboardSummary
from app.models.product_availability import ProductAvailability
from app.models.product_business import ProductBusinessSnapshot
from app.models.product_catalog_management import ProductCatalogHealth
from app.models.product_improvement import ProductImprovement
from app.models.product_performance import ProductPerformance
from app.models.product_review import ProductReviewSummary
from app.models.publishing_automation import PublishingAutomationStatus
from app.models.telegram_business import TelegramBusinessSnapshot
from app.models.conversation_operations import ConversationOperation
from app.models.sales_management import SalesManagement
from app.models.delivery_management import DeliveryManagement
from app.models.relationship_management import RelationshipManagement
from app.models.customer_business import CustomerBusinessSnapshot
from app.models.business_optimization import BusinessOptimizationSnapshot
from app.models.content_opportunity import ContentOpportunitySnapshot
from app.models.runtime_control import RuntimeControlSnapshot


@dataclass(frozen=True)
class WorkspaceMetric:
    label: str
    value: str
    detail: str = ""


@dataclass(frozen=True)
class WorkspaceSummary:
    title: str
    metrics: tuple[WorkspaceMetric, ...]
    note: str = ""


@dataclass(frozen=True)
class WorkspaceAssetsSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceExperiencesSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceProductsSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspacePublishingSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceTelegramOperationsSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceCustomerBusinessSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceBusinessOptimizationSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceContentOpportunitySummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceRuntimeControlSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceConversationSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceActivitySummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceActivityEvent:
    event_type: str
    title: str
    detail: str
    source: str
    timestamp: datetime | None = None
    future_ready: bool = False


@dataclass(frozen=True)
class WorkspaceNotificationSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceNotification:
    notification_type: str
    title: str
    detail: str
    severity: str
    status: str
    action_required: bool
    source: str
    timestamp: datetime | None = None
    future_ready: bool = False


@dataclass(frozen=True)
class WorkspacePublishingQueueItem:
    queue_type: str
    title: str
    detail: str
    status: str
    severity: str
    action_required: bool
    source: str
    timestamp: datetime | None = None
    future_ready: bool = False


@dataclass(frozen=True)
class WorkspaceTelegramOperationItem:
    operation_type: str
    title: str
    detail: str
    status: str
    severity: str
    target: str | None
    source: str
    action_required: bool = False
    future_ready: bool = False


@dataclass(frozen=True)
class WorkspaceTelegramBusinessCard:
    customer_id: str | None
    provider: str
    telegram_business: TelegramBusinessSnapshot
    conversation_operation: ConversationOperation
    sales_management: SalesManagement
    delivery_management: DeliveryManagement
    relationship_management: RelationshipManagement
    next_recommended_action: str
    relationship_health: str
    conversation_status: str
    sales_action: str
    delivery_action: str
    business_health: str
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceCustomerBusinessCard:
    customer_id: str | None
    provider: str
    customer_business: CustomerBusinessSnapshot
    customer_health: str
    journey_stage: str
    value_tier: str
    retention_status: str
    growth_stage: str
    next_recommended_action: str
    growth_opportunity_count: int = 0
    retention_opportunity_count: int = 0
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceBusinessOptimizationCard:
    business_optimization: BusinessOptimizationSnapshot
    overall_business_health: str
    performance_health: str
    strategy_health: str
    revenue_readiness: str
    publishing_readiness: str
    product_health: str
    customer_health: str
    telegram_health: str
    high_impact_opportunity_count: int = 0
    critical_recommendation_count: int = 0
    today_action_count: int = 0
    this_week_action_count: int = 0
    next_recommended_business_action: str = "Review Business"
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceContentOpportunityCard:
    content_opportunity: ContentOpportunitySnapshot
    opportunity_health: str
    total_requests: int = 0
    matched_requests: int = 0
    unmatched_requests: int = 0
    matched_percentage: float = 0.0
    unmatched_percentage: float = 0.0
    trending_topic_count: int = 0
    growing_topic_count: int = 0
    repeat_demand_count: int = 0
    vip_demand_count: int = 0
    highest_priority_opportunity_count: int = 0
    creator_recommendation_count: int = 0
    resolution_ready_count: int = 0
    waiting_customer_count: int = 0
    waiting_customers: tuple[Mapping[str, Any], ...] = ()
    resolved_opportunity_count: int = 0
    pending_follow_up_count: int = 0
    ready_follow_up_count: int = 0
    completed_follow_up_count: int = 0
    next_recommended_action: str = "Review Content Opportunities"
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceRuntimeControlCard:
    runtime: RuntimeControlSnapshot
    runtime_status: str
    current_mode: str
    last_started: str
    last_stopped: str
    active_conversations: int = 0
    pending_deliveries: int = 0
    pending_offers: int = 0
    current_runtime_provider: str = "telegram"
    warning_banner: str = ""
    observed_recommendation_count: int = 0
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceInsight:
    insight_type: str
    category: str
    title: str
    current_value: str
    trend: str
    delta: str
    detail: str
    future_ready: bool = False


@dataclass(frozen=True)
class WorkspaceRecommendedAction:
    title: str
    detail: str
    priority: str
    target: str | None
    source: str


@dataclass(frozen=True)
class WorkspaceWorkflowItem:
    product_id: str | None
    product_name: str
    workflow_snapshot: CreatorWorkflowSnapshot
    product_lifecycle: ProductLifecycle
    review_status: CreatorReviewStatus
    publishing_status: PublishingAutomationStatus
    attention_summary: CreatorAttentionSummary
    compatibility: bool = False

    @property
    def current_workflow_stage(self) -> str:
        return self.workflow_snapshot.current_stage.value

    @property
    def current_lifecycle_stage(self) -> str:
        return self.product_lifecycle.stage.value

    @property
    def next_recommended_action(self) -> str:
        return self.attention_summary.recommended_action


@dataclass(frozen=True)
class WorkspaceExperiencePublishingReadiness:
    status: str
    detail: str
    asset_count: int = 0
    ready_asset_count: int = 0
    source: str = "PublishingService"
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceExperienceCard:
    experience_id: str | None
    title: str
    experience_type: str
    summary: str
    cover_asset_id: int | None
    asset_count: int
    product_count: int
    publishing_readiness: WorkspaceExperiencePublishingReadiness
    delivery_types: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    mood: str | None = None
    story_progression: str | None = None
    intelligence_coverage: str = "Unavailable"
    relationship_source: str = "ExperienceService"
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceProductCard:
    product_id: str
    name: str
    product_type: str
    delivery_type: str
    product_origin: str = "Product"
    experience_name: str | None = None
    experience_type: str | None = None
    status: str = "Unknown"
    review_status: str = "Review"
    approval_status: str = "NEEDS_REVIEW"
    commerce_override_count: int = 0
    has_commerce_overrides: bool = False
    ready_to_publish: bool = False
    publishing_readiness: str = "Unknown"
    provider_status: str = "Unknown"
    telegram_delivery_status: str = "Unknown"
    price: str = "-"
    suggested_price: str = "-"
    asset_count: int = 0
    experience_relationship: str = "Missing"
    publishing_relationship: str = "Unknown"
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceProductBusinessCard:
    product_id: str | None
    product_name: str
    product_business: ProductBusinessSnapshot
    availability: ProductAvailability
    performance: ProductPerformance
    improvement: ProductImprovement
    compatibility: bool = False

    @property
    def product_health(self) -> str:
        return self.product_business.product_health.value

    @property
    def availability_status(self) -> str:
        return self.availability.status.value

    @property
    def performance_status(self) -> str:
        return self.performance.status.value

    @property
    def next_recommended_action(self) -> str:
        if self.improvement.next_recommendation is not None:
            return self.improvement.next_recommendation.recommended_next_action
        return self.product_business.next_recommended_business_action


@dataclass(frozen=True)
class WorkspacePublishingCard:
    product_id: str
    product_name: str
    experience_name: str | None
    product_type: str
    delivery_type: str
    publishing_status: str
    publishing_readiness: str
    provider: str
    provider_status: str
    provider_error: str | None = None
    media_link_status: str = "Missing"
    telegram_delivery_intent: str = "Unknown"
    missing_requirements: tuple[str, ...] = ()
    ready_to_publish: bool = False
    published_active: bool = False
    compatibility: bool = False


@dataclass(frozen=True)
class WorkspaceAdministrationSummary(WorkspaceSummary):
    pass


@dataclass(frozen=True)
class WorkspaceDashboard:
    summaries: dict[str, WorkspaceSummary]
    activity_feed: tuple[WorkspaceActivityEvent, ...] = ()
    notifications: tuple[WorkspaceNotification, ...] = ()
    publishing_queue: tuple[WorkspacePublishingQueueItem, ...] = ()
    telegram_operations: tuple[WorkspaceTelegramOperationItem, ...] = ()
    insights: tuple[WorkspaceInsight, ...] = ()
    recommended_actions: tuple[WorkspaceRecommendedAction, ...] = ()
    creator_review: CreatorReviewDashboardSummary | None = None
    product_review: ProductReviewSummary | None = None
    workflow_items: tuple[WorkspaceWorkflowItem, ...] = ()
    experience_cards: tuple[WorkspaceExperienceCard, ...] = ()
    product_cards: tuple[WorkspaceProductCard, ...] = ()
    product_business_health: ProductCatalogHealth | None = None
    product_business_cards: tuple[WorkspaceProductBusinessCard, ...] = ()
    publishing_cards: tuple[WorkspacePublishingCard, ...] = ()
    telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = ()
    customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = ()
    business_optimization_card: WorkspaceBusinessOptimizationCard | None = None
    content_opportunity_card: WorkspaceContentOpportunityCard | None = None
    runtime_control_card: WorkspaceRuntimeControlCard | None = None

    def summary(self, title: str) -> WorkspaceSummary:
        return self.summaries[title]

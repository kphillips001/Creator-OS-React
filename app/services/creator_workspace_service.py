"""Read-only dashboard orchestration for Creator Workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.models.product import ProductFulfillmentStatus
from app.models.workspace_dashboard import (
    WorkspaceActivityEvent,
    WorkspaceActivitySummary,
    WorkspaceAdministrationSummary,
    WorkspaceAssetsSummary,
    WorkspaceBusinessOptimizationCard,
    WorkspaceBusinessOptimizationSummary,
    WorkspaceContentOpportunityCard,
    WorkspaceContentOpportunitySummary,
    WorkspaceConversationSummary,
    WorkspaceDashboard,
    WorkspaceExperienceCard,
    WorkspaceExperiencePublishingReadiness,
    WorkspaceExperiencesSummary,
    WorkspaceCustomerBusinessCard,
    WorkspaceCustomerBusinessSummary,
    WorkspaceInsight,
    WorkspaceMetric,
    WorkspaceNotification,
    WorkspaceNotificationSummary,
    WorkspaceTelegramBusinessCard,
    WorkspaceProductBusinessCard,
    WorkspaceProductCard,
    WorkspacePublishingCard,
    WorkspaceProductsSummary,
    WorkspaceRecommendedAction,
    WorkspacePublishingQueueItem,
    WorkspacePublishingSummary,
    WorkspaceRuntimeControlCard,
    WorkspaceRuntimeControlSummary,
    WorkspaceTelegramOperationItem,
    WorkspaceTelegramOperationsSummary,
    WorkspaceWorkflowItem,
    WorkspaceSummary,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.delayed_message_dashboard_repository import (
    build_delayed_message_dashboard_summary,
)
from app.repositories.delayed_message_queue_repository import (
    get_delayed_message_queue_counts,
)
from app.repositories.fanvue_user_repository import get_relationship_stats
from app.repositories.mass_ppv_campaign_repository import (
    get_failed_queue_count,
    get_pending_queue_count,
)
from app.repositories.product_repository import ProductRepository
from app.repositories.wall_post_repository import fetch_wall_queue_counts
from app.models.asset_library import AssetLibraryFilter
from app.services.asset_library_service import AssetLibraryService
from app.services.creator_review_service import CreatorReviewService
from app.services.creator_review_optimization_service import (
    CreatorReviewOptimizationService,
)
from app.services.creator_workflow_service import CreatorWorkflowService
from app.services.experience_service import ExperienceService
from app.services.product_availability_service import ProductAvailabilityService
from app.services.product_business_service import ProductBusinessService
from app.services.product_catalog_management_service import (
    ProductCatalogManagementService,
)
from app.services.product_catalog_service import ProductCatalogService
from app.services.product_improvement_service import ProductImprovementService
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.product_performance_service import ProductPerformanceService
from app.services.product_review_service import ProductReviewService
from app.services.publishing_automation_service import PublishingAutomationService
from app.services.publishing_service import PublishingService
from app.services.creator_attention_service import CreatorAttentionService
from app.services.chat_commerce_inventory_service import ChatCommerceInventoryService
from app.services.telegram_business_service import TelegramBusinessService
from app.services.conversation_operations_service import ConversationOperationsService
from app.services.sales_management_service import SalesManagementService
from app.services.delivery_management_service import DeliveryManagementService
from app.services.relationship_management_service import RelationshipManagementService
from app.services.customer_business_service import CustomerBusinessService
from app.services.business_optimization_service import BusinessOptimizationService
from app.services.content_opportunity_service import ContentOpportunityService
from app.services.runtime_control_service import RuntimeControlService
from app.services import workspace_summary_read_models as workspace_summaries


class CreatorWorkspaceService:
    """Constructs the Creator Workspace dashboard from existing services."""

    def __init__(
        self,
        *,
        asset_repository: AssetRepository | None = None,
        asset_library_service: AssetLibraryService | None = None,
        product_repository: ProductRepository | None = None,
        product_catalog_service: ProductCatalogService | None = None,
        experience_service: ExperienceService | None = None,
        publishing_service: PublishingService | None = None,
        creator_review_service: CreatorReviewService | None = None,
        product_review_service: ProductReviewService | None = None,
        creator_workflow_service: CreatorWorkflowService | None = None,
        product_lifecycle_service: ProductLifecycleService | None = None,
        creator_review_optimization_service: CreatorReviewOptimizationService | None = None,
        publishing_automation_service: PublishingAutomationService | None = None,
        creator_attention_service: CreatorAttentionService | None = None,
        product_business_service: ProductBusinessService | None = None,
        product_catalog_management_service: ProductCatalogManagementService | None = None,
        product_availability_service: ProductAvailabilityService | None = None,
        product_performance_service: ProductPerformanceService | None = None,
        product_improvement_service: ProductImprovementService | None = None,
        telegram_business_service: TelegramBusinessService | None = None,
        conversation_operations_service: ConversationOperationsService | None = None,
        sales_management_service: SalesManagementService | None = None,
        delivery_management_service: DeliveryManagementService | None = None,
        relationship_management_service: RelationshipManagementService | None = None,
        telegram_business_contexts_fetcher: Callable[..., tuple[dict[str, Any], ...]] | None = None,
        customer_business_service: CustomerBusinessService | None = None,
        customer_business_contexts_fetcher: Callable[..., tuple[dict[str, Any], ...]] | None = None,
        business_optimization_service: BusinessOptimizationService | None = None,
        content_opportunity_service: ContentOpportunityService | None = None,
        runtime_control_service: RuntimeControlService | None = None,
        chat_commerce_inventory_service: ChatCommerceInventoryService | None = None,
        wall_counts_fetcher: Callable[..., dict] = fetch_wall_queue_counts,
        pending_mass_ppv_fetcher: Callable[[], int] = get_pending_queue_count,
        failed_mass_ppv_fetcher: Callable[[], int] = get_failed_queue_count,
        relationship_stats_fetcher: Callable[[int], dict] = get_relationship_stats,
        delayed_counts_fetcher: Callable[..., dict] = get_delayed_message_queue_counts,
    ):
        self.asset_repository = asset_repository or AssetRepository()
        self.asset_library_service = asset_library_service or AssetLibraryService(
            asset_repository=self.asset_repository
        )
        self.product_repository = product_repository or ProductRepository()
        self.experience_service = experience_service or ExperienceService()
        self.publishing_service = publishing_service or PublishingService()
        self.product_catalog_service = product_catalog_service or ProductCatalogService(
            product_repository=self.product_repository,
            asset_repository=self.asset_repository,
            experience_service=self.experience_service,
            publishing_service=self.publishing_service,
        )
        self.creator_review_service = creator_review_service or CreatorReviewService(
            experience_service=self.experience_service
        )
        self.product_review_service = product_review_service or ProductReviewService(
            product_catalog_service=self.product_catalog_service,
            publishing_service=self.publishing_service,
        )
        self.creator_workflow_service = creator_workflow_service or CreatorWorkflowService(
            product_review_service=self.product_review_service,
            publishing_service=self.publishing_service,
        )
        self.product_lifecycle_service = (
            product_lifecycle_service or ProductLifecycleService()
        )
        self.creator_review_optimization_service = (
            creator_review_optimization_service
            or CreatorReviewOptimizationService(
                product_lifecycle_service=self.product_lifecycle_service,
            )
        )
        self.publishing_automation_service = (
            publishing_automation_service
            or PublishingAutomationService(
                product_lifecycle_service=self.product_lifecycle_service,
                publishing_service=self.publishing_service,
            )
        )
        self.creator_attention_service = creator_attention_service or CreatorAttentionService(
            product_lifecycle_service=self.product_lifecycle_service,
            review_optimization_service=self.creator_review_optimization_service,
            publishing_automation_service=self.publishing_automation_service,
        )
        self._chat_commerce_inventory_service = chat_commerce_inventory_service
        self.product_business_service = product_business_service or ProductBusinessService(
            product_catalog_service=self.product_catalog_service,
            product_lifecycle_service=self.product_lifecycle_service,
            publishing_automation_service=self.publishing_automation_service,
        )
        self.product_catalog_management_service = (
            product_catalog_management_service
            or ProductCatalogManagementService(
                product_business_service=self.product_business_service,
                product_catalog_service=self.product_catalog_service,
            )
        )
        self.product_availability_service = (
            product_availability_service
            or ProductAvailabilityService(
                product_business_service=self.product_business_service,
                product_lifecycle_service=self.product_lifecycle_service,
                publishing_automation_service=self.publishing_automation_service,
                product_catalog_service=self.product_catalog_service,
            )
        )
        self.product_performance_service = (
            product_performance_service
            or ProductPerformanceService(
                product_business_service=self.product_business_service,
                product_catalog_service=self.product_catalog_service,
            )
        )
        self.product_improvement_service = (
            product_improvement_service or ProductImprovementService()
        )
        self.telegram_business_service = (
            telegram_business_service or TelegramBusinessService()
        )
        self.conversation_operations_service = (
            conversation_operations_service
            or ConversationOperationsService(
                telegram_business_service=self.telegram_business_service,
            )
        )
        self.sales_management_service = (
            sales_management_service
            or SalesManagementService(
                telegram_business_service=self.telegram_business_service,
                conversation_operations_service=self.conversation_operations_service,
            )
        )
        self.delivery_management_service = (
            delivery_management_service
            or DeliveryManagementService(
                telegram_business_service=self.telegram_business_service,
                conversation_operations_service=self.conversation_operations_service,
                sales_management_service=self.sales_management_service,
            )
        )
        self.relationship_management_service = (
            relationship_management_service
            or RelationshipManagementService(
                telegram_business_service=self.telegram_business_service,
                conversation_operations_service=self.conversation_operations_service,
                sales_management_service=self.sales_management_service,
                delivery_management_service=self.delivery_management_service,
            )
        )
        self.telegram_business_contexts_fetcher = telegram_business_contexts_fetcher
        self.customer_business_service = (
            customer_business_service or CustomerBusinessService()
        )
        self.customer_business_contexts_fetcher = customer_business_contexts_fetcher
        self.business_optimization_service = (
            business_optimization_service or BusinessOptimizationService()
        )
        self.content_opportunity_service = (
            content_opportunity_service or ContentOpportunityService()
        )
        self.runtime_control_service = (
            runtime_control_service or RuntimeControlService()
        )
        self.wall_counts_fetcher = wall_counts_fetcher
        self.pending_mass_ppv_fetcher = pending_mass_ppv_fetcher
        self.failed_mass_ppv_fetcher = failed_mass_ppv_fetcher
        self.relationship_stats_fetcher = relationship_stats_fetcher
        self.delayed_counts_fetcher = delayed_counts_fetcher

    def build_dashboard(
        self,
        *,
        creator_profile: dict | None = None,
        active_account: dict | None = None,
    ) -> WorkspaceDashboard:
        creator_profile_id = (creator_profile or {}).get("id")
        account_id = (active_account or {}).get("id")
        summaries: dict[str, WorkspaceSummary] = {
            "Assets": self._safe_summary("Assets", self._asset_summary),
            "Experiences": self._safe_summary(
                "Experiences",
                lambda: self._experience_summary(creator_profile_id),
            ),
            "Products": self._safe_summary(
                "Products",
                lambda: self._product_summary(creator_profile_id),
            ),
            "Publishing": self._safe_summary(
                "Publishing",
                lambda: self._publishing_summary(
                    account_id,
                    creator_profile_id,
                ),
            ),
            "Customer Conversations": self._safe_summary(
                "Customer Conversations",
                lambda: self._conversation_summary(account_id),
            ),
            "Activity": self._safe_summary(
                "Activity",
                lambda: self._activity_summary(account_id),
            ),
        }
        telegram_business_cards = self._safe_telegram_business_cards(
            creator_profile=creator_profile,
            active_account=active_account,
        )
        customer_business_cards = self._safe_customer_business_cards(
            creator_profile=creator_profile,
            active_account=active_account,
        )
        summaries["Telegram Operations"] = self._safe_summary(
            "Telegram Operations",
            lambda: self._telegram_operations_summary(
                summaries,
                telegram_business_cards=telegram_business_cards,
            ),
        )
        summaries["Customer Business"] = self._safe_summary(
            "Customer Business",
            lambda: self._customer_business_summary(
                customer_business_cards=customer_business_cards,
            ),
        )
        summaries["Notifications"] = self._notification_summary(
            creator_profile,
            active_account,
            summaries["Publishing"],
            summaries["Activity"],
        )
        runtime_control_card = self._safe_runtime_control_card(creator_profile_id)
        summaries["Runtime Control"] = self._safe_summary(
            "Runtime Control",
            lambda: self._runtime_control_summary(runtime_control_card),
        )
        summaries["Administration"] = WorkspaceAdministrationSummary(
            title="Administration",
            metrics=(
                WorkspaceMetric(
                    "Creator Profile",
                    "Loaded" if creator_profile else "Missing",
                ),
                WorkspaceMetric("System Overview", "Available"),
                WorkspaceMetric("Runtime Control", "Available"),
                WorkspaceMetric("Provider Auth", "Available"),
            ),
        )
        activity_feed = self._safe_activity_feed(
            creator_profile=creator_profile,
            active_account=active_account,
            summaries=summaries,
        )
        notifications = self._safe_notifications(
            creator_profile=creator_profile,
            active_account=active_account,
            summaries=summaries,
        )
        publishing_queue = self._safe_publishing_queue(summaries=summaries)
        telegram_operations = self._safe_telegram_operations(
            summaries=summaries,
            telegram_business_cards=telegram_business_cards,
        )
        experience_cards = self._safe_experience_cards(creator_profile_id)
        product_cards = self._safe_product_cards(creator_profile_id)
        product_business_health, product_business_cards = (
            self._safe_product_business_dashboard(creator_profile_id)
        )
        business_optimization_card = self._safe_business_optimization_card(
            summaries=summaries,
            product_business_cards=product_business_cards,
            telegram_business_cards=telegram_business_cards,
            customer_business_cards=customer_business_cards,
        )
        summaries["Business Optimization"] = self._safe_summary(
            "Business Optimization",
            lambda: self._business_optimization_summary(
                business_optimization_card=business_optimization_card,
            ),
        )
        content_opportunity_card = self._safe_content_opportunity_card()
        summaries["Content Opportunity"] = self._safe_summary(
            "Content Opportunity",
            lambda: self._content_opportunity_summary(
                content_opportunity_card=content_opportunity_card,
            ),
        )
        product_review = self._safe_product_review_summary(creator_profile_id)
        publishing_cards = self._safe_publishing_cards(creator_profile_id)
        workflow_items = self._safe_workflow_items(creator_profile_id)
        notifications = self._sort_notifications(
            list(notifications)
            + list(
                self._content_opportunity_notifications(
                    content_opportunity_card,
                )
            )
        )
        insights = self._safe_insights(summaries=summaries)
        recommended_actions = self._safe_recommended_actions(
            summaries=summaries,
            notifications=notifications,
            workflow_items=workflow_items,
            telegram_business_cards=telegram_business_cards,
            customer_business_cards=customer_business_cards,
            business_optimization_card=business_optimization_card,
            content_opportunity_card=content_opportunity_card,
        )
        creator_review = self._safe_creator_review(
            summaries=summaries,
            experience_cards=experience_cards,
            product_cards=product_cards,
            publishing_cards=publishing_cards,
        )
        return WorkspaceDashboard(
            summaries=summaries,
            activity_feed=activity_feed,
            notifications=notifications,
            publishing_queue=publishing_queue,
            telegram_operations=telegram_operations,
            insights=insights,
            recommended_actions=recommended_actions,
            creator_review=creator_review,
            product_review=product_review,
            workflow_items=workflow_items,
            experience_cards=experience_cards,
            product_cards=product_cards,
            product_business_health=product_business_health,
            product_business_cards=product_business_cards,
            publishing_cards=publishing_cards,
            telegram_business_cards=telegram_business_cards,
            customer_business_cards=customer_business_cards,
            business_optimization_card=business_optimization_card,
            content_opportunity_card=content_opportunity_card,
            runtime_control_card=runtime_control_card,
        )

    @staticmethod
    def _format_count(value: Any) -> str:
        return workspace_summaries.format_count(value)

    def _safe_runtime_control_card(
        self,
        creator_profile_id: Any,
    ) -> WorkspaceRuntimeControlCard | None:
        try:
            snapshot = self.runtime_control_service.build_snapshot(
                creator_profile_id=creator_profile_id,
            )
        except Exception:
            return None
        return WorkspaceRuntimeControlCard(
            runtime=snapshot,
            runtime_status=self._value(snapshot.runtime_status),
            current_mode=self._value(snapshot.current_mode),
            last_started=self._format_datetime(snapshot.last_started),
            last_stopped=self._format_datetime(snapshot.last_stopped),
            active_conversations=int(snapshot.active_conversations or 0),
            pending_deliveries=int(snapshot.pending_deliveries or 0),
            pending_offers=int(snapshot.pending_offers or 0),
            current_runtime_provider=str(snapshot.current_runtime_provider),
            warning_banner=str(snapshot.warning_banner),
            observed_recommendation_count=len(
                tuple(snapshot.observed_recommendations or ())
            ),
            compatibility=bool(snapshot.compatibility.get("owns_runtime_state")),
        )

    def _runtime_control_summary(
        self,
        card: WorkspaceRuntimeControlCard | None,
    ) -> WorkspaceRuntimeControlSummary:
        if card is None:
            return WorkspaceRuntimeControlSummary(
                title="Runtime Control",
                metrics=(
                    WorkspaceMetric("Runtime Status", "OFFLINE"),
                    WorkspaceMetric("Current Mode", "OFFLINE"),
                    WorkspaceMetric("Current Runtime Provider", "telegram"),
                ),
                note="Runtime Control read model is unavailable.",
            )
        return WorkspaceRuntimeControlSummary(
            title="Runtime Control",
            metrics=(
                WorkspaceMetric("Runtime Status", card.runtime_status),
                WorkspaceMetric("Last Started", card.last_started),
                WorkspaceMetric("Last Stopped", card.last_stopped),
                WorkspaceMetric("Current Mode", card.current_mode),
                WorkspaceMetric(
                    "Active Conversations",
                    self._format_count(card.active_conversations),
                ),
                WorkspaceMetric(
                    "Pending Deliveries",
                    self._format_count(card.pending_deliveries),
                ),
                WorkspaceMetric("Pending Offers", self._format_count(card.pending_offers)),
                WorkspaceMetric(
                    "Current Runtime Provider",
                    card.current_runtime_provider,
                ),
                WorkspaceMetric(
                    "Observed Recommendations",
                    self._format_count(card.observed_recommendation_count),
                ),
            ),
            note=card.warning_banner,
        )

    @staticmethod
    def _format_datetime(value: Any) -> str:
        if value is None:
            return "-"
        formatter = getattr(value, "strftime", None)
        if callable(formatter):
            return formatter("%Y-%m-%d %H:%M")
        return str(value)

    @staticmethod
    def _attribute(item: Any, name: str, default: Any = None) -> Any:
        return workspace_summaries.attribute(item, name, default)

    @staticmethod
    def _value(value: Any) -> str:
        return workspace_summaries.enum_value(value)

    @staticmethod
    def _metric_value_as_int(summary: WorkspaceSummary, label: str) -> int:
        return workspace_summaries.metric_value_as_int(summary, label)

    @staticmethod
    def _metric_value(summary: WorkspaceSummary, label: str) -> str:
        return workspace_summaries.metric_value(summary, label)

    @staticmethod
    def _is_recent(value: datetime | None, *, after: datetime) -> bool:
        return workspace_summaries.is_recent(value, after=after)

    def _safe_summary(
        self,
        title: str,
        builder: Callable[[], WorkspaceSummary],
    ) -> WorkspaceSummary:
        try:
            return builder()
        except Exception:
            return WorkspaceSummary(
                title=title,
                metrics=(WorkspaceMetric("Status", "Unavailable"),),
                note="Data source unavailable.",
            )

    def _safe_activity_feed(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceActivityEvent, ...]:
        try:
            return self._activity_feed(
                creator_profile=creator_profile,
                active_account=active_account,
                summaries=summaries,
            )
        except Exception:
            return (
                WorkspaceActivityEvent(
                    event_type="system",
                    title="Activity feed unavailable",
                    detail="One or more read-only activity sources could not be loaded.",
                    source="CreatorWorkspaceService",
                    future_ready=True,
                ),
            )

    def _safe_notifications(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceNotification, ...]:
        try:
            return self._notifications(
                creator_profile=creator_profile,
                active_account=active_account,
                summaries=summaries,
            )
        except Exception:
            return (
                WorkspaceNotification(
                    notification_type="system",
                    title="Notifications unavailable",
                    detail="One or more read-only notification sources could not be loaded.",
                    severity="warning",
                    status="open",
                    action_required=False,
                    source="CreatorWorkspaceService",
                    future_ready=True,
                ),
            )

    def _notifications(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceNotification, ...]:
        notifications: list[WorkspaceNotification] = []
        assets = summaries["Assets"]
        products = summaries["Products"]
        publishing = summaries["Publishing"]
        customers = summaries["Customer Conversations"]
        activity = summaries["Activity"]

        if not creator_profile:
            notifications.append(
                WorkspaceNotification(
                    notification_type="creator_profile",
                    title="Creator profile is missing",
                    detail="Complete Administration setup before operating the workspace.",
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Administration",
                )
            )

        oauth_connected = bool(
            (active_account or {}).get("oauth_access_token")
            or (active_account or {}).get("oauth_refresh_token")
            or (active_account or {}).get("fanvue_user_uuid")
        )
        if not oauth_connected:
            notifications.append(
                WorkspaceNotification(
                    notification_type="oauth",
                    title="Provider OAuth needs attention",
                    detail="Connect or refresh the provider account before publishing.",
                    severity="critical",
                    status="open",
                    action_required=True,
                    source="Administration",
                )
            )

        notifications.extend(self._asset_notifications(assets))
        notifications.extend(self._product_notifications(products))
        notifications.extend(self._publishing_notifications(publishing))
        notifications.extend(self._customer_notifications(customers))
        notifications.extend(self._activity_notifications(activity))
        notifications.extend(self._future_notification_placeholders())

        return self._sort_notifications(notifications)

    def _asset_notifications(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceNotification, ...]:
        needs_classification = self._metric_value_as_int(
            summary,
            "Needs Classification",
        )
        processing = self._metric_value_as_int(summary, "Assets Processing")
        asset_alerts = self._metric_value_as_int(summary, "Asset Alerts")
        notifications: list[WorkspaceNotification] = []
        if asset_alerts:
            notifications.append(
                WorkspaceNotification(
                    notification_type="asset_processing_failure",
                    title="Asset processing alerts detected",
                    detail=f"{self._format_count(asset_alerts)} asset(s) need review.",
                    severity="critical",
                    status="open",
                    action_required=True,
                    source="Assets",
                )
            )
        if needs_classification:
            notifications.append(
                WorkspaceNotification(
                    notification_type="asset_classification",
                    title="Assets require classification",
                    detail=(
                        f"{self._format_count(needs_classification)} asset(s) "
                        "are missing classification metadata."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Assets",
                )
            )
        if processing:
            notifications.append(
                WorkspaceNotification(
                    notification_type="asset_processing",
                    title="Assets are still processing",
                    detail=f"{self._format_count(processing)} asset(s) are in progress.",
                    severity="info",
                    status="monitoring",
                    action_required=False,
                    source="Assets",
                )
            )
        return tuple(notifications)

    def _product_notifications(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceNotification, ...]:
        missing_price = self._metric_value_as_int(summary, "Missing Price")
        not_ready = self._metric_value_as_int(summary, "Not Ready")
        failed = self._metric_value_as_int(summary, "Fulfillment Failed")
        notifications: list[WorkspaceNotification] = []
        if failed:
            notifications.append(
                WorkspaceNotification(
                    notification_type="product_fulfillment",
                    title="Product fulfillment failures detected",
                    detail=f"{self._format_count(failed)} product(s) failed fulfillment checks.",
                    severity="critical",
                    status="open",
                    action_required=True,
                    source="Products",
                )
            )
        if missing_price:
            notifications.append(
                WorkspaceNotification(
                    notification_type="product_pricing",
                    title="Products are missing pricing",
                    detail=f"{self._format_count(missing_price)} active product(s) need prices.",
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Products",
                )
            )
        if not_ready:
            notifications.append(
                WorkspaceNotification(
                    notification_type="product_review",
                    title="Products require review",
                    detail=f"{self._format_count(not_ready)} product(s) are not ready.",
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Products",
                )
            )
        return tuple(notifications)

    def _publishing_notifications(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceNotification, ...]:
        failures = self._metric_value_as_int(summary, "Failed Uploads")
        queue_attention = self._metric_value_as_int(summary, "Queue Attention")
        pending = self._metric_value_as_int(summary, "Pending Uploads")
        missing_media_link = self._metric_value_as_int(
            summary,
            "Missing Media Link",
        )
        notifications: list[WorkspaceNotification] = []
        if failures:
            notifications.append(
                WorkspaceNotification(
                    notification_type="publishing_failure",
                    title="Publishing failures require attention",
                    detail=f"{self._format_count(failures)} publishing item(s) failed.",
                    severity="critical",
                    status="open",
                    action_required=True,
                    source="Publishing",
                )
            )
        if missing_media_link:
            notifications.append(
                WorkspaceNotification(
                    notification_type="publishing_missing_media_link",
                    title="Products are missing media links",
                    detail=(
                        f"{self._format_count(missing_media_link)} Product(s) "
                        "need media links before publishing."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Publishing",
                )
            )
        if queue_attention:
            notifications.append(
                WorkspaceNotification(
                    notification_type="queue_attention",
                    title="Publishing queue needs review",
                    detail=f"{self._format_count(queue_attention)} queue item(s) need attention.",
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Publishing",
                )
            )
        if pending:
            notifications.append(
                WorkspaceNotification(
                    notification_type="publishing_pending",
                    title="Publishing queue has pending work",
                    detail=f"{self._format_count(pending)} publishing item(s) are pending.",
                    severity="info",
                    status="monitoring",
                    action_required=False,
                    source="Publishing",
                )
            )
        return tuple(notifications)

    def _customer_notifications(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceNotification, ...]:
        missing = self._metric_value_as_int(summary, "Missing Profiles")
        if not missing:
            return ()
        return (
            WorkspaceNotification(
                notification_type="customer_sync",
                title="Customer profiles need sync review",
                detail=f"{self._format_count(missing)} customer profile(s) are missing.",
                severity="info",
                status="open",
                action_required=False,
                source="Customer Conversations",
            ),
        )

    def _activity_notifications(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceNotification, ...]:
        failed = self._metric_value_as_int(summary, "Delayed Failed")
        expired = self._metric_value_as_int(summary, "Delayed Expired")
        notifications: list[WorkspaceNotification] = []
        if failed:
            notifications.append(
                WorkspaceNotification(
                    notification_type="delayed_message_failure",
                    title="Delayed followups failed",
                    detail=f"{self._format_count(failed)} delayed followup(s) failed.",
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Activity",
                )
            )
        if expired:
            notifications.append(
                WorkspaceNotification(
                    notification_type="delayed_message_expired",
                    title="Delayed followups expired",
                    detail=f"{self._format_count(expired)} delayed followup(s) expired.",
                    severity="info",
                    status="open",
                    action_required=False,
                    source="Activity",
                )
            )
        return tuple(notifications)

    def _future_notification_placeholders(self) -> tuple[WorkspaceNotification, ...]:
        return (
            WorkspaceNotification(
                notification_type="synchronization",
                title="Synchronization notifications",
                detail="Cross-provider sync notification source is not yet exposed.",
                severity="info",
                status="future",
                action_required=False,
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
            WorkspaceNotification(
                notification_type="ai_recommendation",
                title="Future AI recommendations",
                detail="AI recommendation notifications will surface in a later phase.",
                severity="info",
                status="future",
                action_required=False,
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
        )

    @staticmethod
    def _sort_notifications(
        notifications: list[WorkspaceNotification],
    ) -> tuple[WorkspaceNotification, ...]:
        severity_order = {
            "critical": 0,
            "warning": 1,
            "info": 2,
        }

        def sort_key(notification: WorkspaceNotification) -> tuple[int, int, str]:
            return (
                severity_order.get(notification.severity, 3),
                0 if notification.action_required else 1,
                notification.title,
            )

        return tuple(sorted(notifications, key=sort_key))

    def _safe_recommended_actions(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        notifications: tuple[WorkspaceNotification, ...],
        workflow_items: tuple[WorkspaceWorkflowItem, ...] = (),
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
        customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = (),
        business_optimization_card: WorkspaceBusinessOptimizationCard | None = None,
        content_opportunity_card: WorkspaceContentOpportunityCard | None = None,
    ) -> tuple[WorkspaceRecommendedAction, ...]:
        try:
            return self._recommended_actions(
                summaries=summaries,
                notifications=notifications,
                workflow_items=workflow_items,
                telegram_business_cards=telegram_business_cards,
                customer_business_cards=customer_business_cards,
                business_optimization_card=business_optimization_card,
                content_opportunity_card=content_opportunity_card,
            )
        except Exception:
            return ()

    def _recommended_actions(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        notifications: tuple[WorkspaceNotification, ...],
        workflow_items: tuple[WorkspaceWorkflowItem, ...] = (),
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
        customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = (),
        business_optimization_card: WorkspaceBusinessOptimizationCard | None = None,
        content_opportunity_card: WorkspaceContentOpportunityCard | None = None,
    ) -> tuple[WorkspaceRecommendedAction, ...]:
        actions: list[WorkspaceRecommendedAction] = []
        for notification in notifications:
            if not notification.action_required:
                continue
            actions.append(
                WorkspaceRecommendedAction(
                    title=notification.title,
                    detail=notification.detail,
                    priority=notification.severity,
                    target=self._recommended_target_for_source(
                        notification.source
                    ),
                    source=notification.source,
                )
            )

        for workflow_item in workflow_items:
            for attention_item in workflow_item.attention_summary.actionable_items:
                actions.append(
                    WorkspaceRecommendedAction(
                        title=attention_item.recommended_action,
                        detail=(
                            f"{workflow_item.product_name}: "
                            f"{attention_item.reason}"
                        ),
                        priority=self._attention_priority_to_workspace(
                            attention_item.priority.value
                        ),
                        target=self._target_for_attention_category(
                            attention_item.category.value
                        ),
                        source="CreatorAttentionService",
                    )
                )

        publishing = summaries["Publishing"]
        products = summaries["Products"]
        assets = summaries["Assets"]
        experiences = summaries["Experiences"]
        telegram = summaries.get("Telegram Operations")
        ready_to_publish = self._metric_value_as_int(
            publishing,
            "Ready To Publish",
        )
        if ready_to_publish:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review ready-to-publish Products",
                    detail=(
                        f"{self._format_count(ready_to_publish)} Product(s) "
                        "are ready for publishing review."
                    ),
                    priority="info",
                    target="Wall Scheduler",
                    source="Publishing",
                )
            )

        waiting_media_link = self._metric_value_as_int(
            publishing,
            "Waiting For Media Link",
        )
        if waiting_media_link:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review Waiting For Media Links",
                    detail=(
                        f"{self._format_count(waiting_media_link)} Publishing Job(s) "
                        "need manual Media Link verification."
                    ),
                    priority="warning",
                    target="Publishing Queue",
                    source="Publishing",
                )
            )

        retry_required = self._metric_value_as_int(
            publishing,
            "Retry Required Count",
        )
        if retry_required:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review Retry Required",
                    detail=(
                        f"{self._format_count(retry_required)} Publishing Job(s) "
                        "are ready for retry review."
                    ),
                    priority="warning",
                    target="Publishing Queue",
                    source="Publishing",
                )
            )

        failed_jobs = self._metric_value_as_int(publishing, "Failed Count")
        if failed_jobs:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review Failed Uploads",
                    detail=(
                        f"{self._format_count(failed_jobs)} Publishing Job upload(s) failed."
                    ),
                    priority="critical",
                    target="Publishing Queue",
                    source="Publishing",
                )
            )

        publishing_complete = self._metric_value_as_int(
            publishing,
            "Publishing Complete",
        )
        if publishing_complete:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review Publishing Complete",
                    detail=(
                        f"{self._format_count(publishing_complete)} Publishing Job(s) "
                        "are complete."
                    ),
                    priority="info",
                    target="Publishing Queue",
                    source="Publishing",
                )
            )

        missing_media_link = self._metric_value_as_int(
            publishing,
            "Missing Media Link",
        )
        if missing_media_link:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Add missing media links",
                    detail=(
                        f"{self._format_count(missing_media_link)} Product(s) "
                        "are missing media links."
                    ),
                    priority="warning",
                    target="Product Catalog",
                    source="Publishing",
                )
            )

        missing_assets = self._metric_value_as_int(products, "Missing Assets")
        if missing_assets:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Attach missing Product Assets",
                    detail=(
                        f"{self._format_count(missing_assets)} Product(s) "
                        "need attached Assets."
                    ),
                    priority="warning",
                    target="Product Catalog",
                    source="Products",
                )
            )

        needs_classification = self._metric_value_as_int(
            assets,
            "Needs Classification",
        )
        if needs_classification:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review unclassified Assets",
                    detail=(
                        f"{self._format_count(needs_classification)} Asset(s) "
                        "need classification."
                    ),
                    priority="warning",
                    target="Asset Library",
                    source="Assets",
                )
            )

        experiences_needing_review = self._metric_value_as_int(
            experiences,
            "Needs Review",
        )
        if experiences_needing_review:
            actions.append(
                WorkspaceRecommendedAction(
                    title="Review Experience organization",
                    detail=(
                        f"{self._format_count(experiences_needing_review)} "
                        "Experience(s) need review."
                    ),
                    priority="info",
                    target=None,
                    source="Experiences",
                )
            )

        if telegram is not None:
            followup = self._metric_value_as_int(
                telegram,
                "Customers Needing Follow-Up",
            )
            if followup:
                actions.append(
                    WorkspaceRecommendedAction(
                        title="Review Customers Needing Follow-Up",
                        detail=(
                            f"{self._format_count(followup)} customer(s) need "
                            "Telegram Commerce follow-up."
                        ),
                        priority="warning",
                        target="Customer Workspace",
                        source="Telegram Operations",
                    )
                )
            paid_offers = self._metric_value_as_int(
                telegram,
                "PAID Media Link Deliveries",
            )
            if paid_offers:
                actions.append(
                    WorkspaceRecommendedAction(
                        title="Review Recent Paid Offers",
                        detail=(
                            f"{self._format_count(paid_offers)} PAID Media Link "
                            "offer item(s) are ready for review."
                        ),
                        priority="info",
                        target="Customer Workspace",
                        source="Telegram Operations",
                    )
                )
            active_experiences = self._metric_value_as_int(
                telegram,
                "Active Experiences",
            )
            if active_experiences:
                actions.append(
                    WorkspaceRecommendedAction(
                        title="Review Current Experiences",
                        detail=(
                            f"{self._format_count(active_experiences)} active "
                            "Experience(s) are visible in Telegram operations."
                        ),
                        priority="info",
                        target="Customer Workspace",
                        source="Telegram Operations",
                    )
                )

        for card in telegram_business_cards:
            action = card.next_recommended_action
            if not action or action == "No Relationship Action":
                continue
            actions.append(
                WorkspaceRecommendedAction(
                    title=action,
                    detail=(
                        f"{card.customer_id or 'Telegram customer'}: "
                        f"{card.relationship_health} | {card.conversation_status}"
                    ),
                    priority=self._telegram_business_priority(card),
                    target="Customer Workspace",
                    source="Telegram Business",
                )
            )

        for card in customer_business_cards:
            action = card.next_recommended_action
            if not action:
                continue
            actions.append(
                WorkspaceRecommendedAction(
                    title=action,
                    detail=(
                        f"{card.customer_id or 'Customer'}: "
                        f"{card.customer_health} | {card.journey_stage} | "
                        f"{card.value_tier}"
                    ),
                    priority=self._customer_business_priority(card),
                    target="Customer Workspace",
                    source="Customer Business",
                )
            )

        if business_optimization_card is not None:
            for action in self._attribute(
                business_optimization_card.business_optimization,
                "prioritized_recommendations",
                (),
            )[:6]:
                title = self._attribute(action, "recommended_action")
                if not title:
                    continue
                actions.append(
                    WorkspaceRecommendedAction(
                        title=title,
                        detail=(
                            f"{business_optimization_card.overall_business_health} | "
                            f"Performance: {business_optimization_card.performance_health} | "
                            f"Strategy: {business_optimization_card.strategy_health}"
                        ),
                        priority=self._business_optimization_priority(action),
                        target=self._business_optimization_target(action),
                        source="Business Optimization",
                    )
                )

        if content_opportunity_card is not None:
            for recommendation in self._attribute(
                content_opportunity_card.content_opportunity,
                "creator_recommendations",
                (),
            )[:6]:
                title = self._attribute(recommendation, "title")
                if not title:
                    continue
                actions.append(
                    WorkspaceRecommendedAction(
                        title=title,
                        detail=self._attribute(recommendation, "summary", ""),
                        priority=self._content_opportunity_priority(
                            self._attribute(recommendation, "priority", "")
                        ),
                        target="Content Opportunity Center",
                        source="Content Opportunity",
                    )
                )
            if content_opportunity_card.resolution_ready_count:
                actions.append(
                    WorkspaceRecommendedAction(
                        title="Review content opportunity resolutions",
                        detail=(
                            f"{self._format_count(content_opportunity_card.resolution_ready_count)} "
                            "opportunity resolution(s) are ready for creator review."
                        ),
                        priority="warning",
                        target="Content Opportunity Center",
                        source="Content Opportunity",
                    )
                )
            if content_opportunity_card.ready_follow_up_count:
                actions.append(
                    WorkspaceRecommendedAction(
                        title="Review content follow-up opportunities",
                        detail=(
                            f"{self._format_count(content_opportunity_card.ready_follow_up_count)} "
                            "customer follow-up opportunity/opportunities are ready."
                        ),
                        priority="warning",
                        target="Content Opportunity Center",
                        source="Content Opportunity",
                    )
                )

        return self._sort_recommended_actions(actions)

    @staticmethod
    def _attention_priority_to_workspace(priority: str) -> str:
        mapping = {
            "CRITICAL": "critical",
            "HIGH": "warning",
            "NORMAL": "info",
            "LOW": "info",
        }
        return mapping.get(priority, "info")

    @staticmethod
    def _telegram_business_priority(card: WorkspaceTelegramBusinessCard) -> str:
        health = str(card.relationship_health or "").upper()
        status = str(card.conversation_status or "").upper()
        if health in {"AT_RISK", "DISENGAGED"}:
            return "warning"
        if health == "VIP_OPPORTUNITY":
            return "info"
        if status in {"STALLED", "WAITING_FOR_CREATOR_OS"}:
            return "warning"
        return "info"

    @staticmethod
    def _customer_business_priority(card: WorkspaceCustomerBusinessCard) -> str:
        health = str(card.customer_health or "").upper()
        retention = str(card.retention_status or "").upper()
        if health in {"AT_RISK", "DORMANT", "NEEDS_ATTENTION"}:
            return "warning"
        if retention in {"AT_RISK", "DORMANT", "RE_ENGAGEMENT_CANDIDATE"}:
            return "warning"
        if card.growth_opportunity_count or str(card.value_tier).upper() in {
            "VIP",
            "VIP_POTENTIAL",
        }:
            return "info"
        return "info"

    @staticmethod
    def _business_optimization_priority(action: Any) -> str:
        priority = str(
            getattr(
                getattr(action, "priority", ""),
                "value",
                getattr(action, "priority", ""),
            )
        ).upper()
        if priority == "CRITICAL":
            return "critical"
        if priority == "HIGH":
            return "warning"
        return "info"

    @staticmethod
    def _business_optimization_target(action: Any) -> str | None:
        category = str(
            getattr(
                getattr(action, "category", ""),
                "value",
                getattr(action, "category", ""),
            )
        ).upper()
        return {
            "PRODUCT": "Product Catalog",
            "PUBLISHING": "Publishing Queue",
            "CUSTOMER": "Customer Workspace",
            "TELEGRAM": "Customer Workspace",
            "REVENUE": "Product Catalog",
        }.get(category)

    @staticmethod
    def _content_opportunity_priority(priority: Any) -> str:
        value = str(getattr(priority, "value", priority)).upper()
        if value == "CRITICAL":
            return "critical"
        if value in {"HIGH", "ELEVATED"}:
            return "warning"
        return "info"

    @staticmethod
    def _target_for_attention_category(category: str) -> str | None:
        mapping = {
            "REVIEW": "Product Review",
            "APPROVAL": "Product Review",
            "PUBLISHING": "Publishing Queue",
            "MEDIA_LINK": "Publishing Queue",
            "FAILURE": "Publishing Queue",
            "INFORMATION": None,
        }
        return mapping.get(category)

    @staticmethod
    def _recommended_target_for_source(source: str) -> str | None:
        return {
            "Assets": "Asset Library",
            "Products": "Product Catalog",
            "Publishing": "Publishing Queue",
            "Activity": "Activity Feed",
            "Customer Conversations": "Customer Workspace",
            "Telegram Operations": "Customer Workspace",
            "Administration": "Creator Profile",
            "Content Opportunity": "Content Opportunity Center",
        }.get(source)

    @staticmethod
    def _sort_recommended_actions(
        actions: list[WorkspaceRecommendedAction],
    ) -> tuple[WorkspaceRecommendedAction, ...]:
        priority_order = {
            "critical": 0,
            "warning": 1,
            "info": 2,
        }
        deduped: list[WorkspaceRecommendedAction] = []
        seen = set()
        for action in actions:
            key = (action.title, action.source, action.target)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(action)
        return tuple(
            sorted(
                deduped,
                key=lambda action: (
                    priority_order.get(action.priority, 3),
                    action.title,
                ),
            )
        )

    def _safe_publishing_queue(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspacePublishingQueueItem, ...]:
        try:
            return self._publishing_queue(summaries["Publishing"])
        except Exception:
            return (
                WorkspacePublishingQueueItem(
                    queue_type="system",
                    title="Publishing Queue unavailable",
                    detail="Publishing Queue summary could not be loaded.",
                    status="Requires Attention",
                    severity="warning",
                    action_required=False,
                    source="CreatorWorkspaceService",
                    future_ready=True,
                ),
            )

    def _publishing_queue(
        self,
        publishing: WorkspaceSummary,
    ) -> tuple[WorkspacePublishingQueueItem, ...]:
        pending_total = self._metric_value_as_int(publishing, "Pending Uploads")
        failed_total = self._metric_value_as_int(publishing, "Failed Uploads")
        completed = self._metric_value_as_int(publishing, "Recently Published")
        queue_count = self._metric_value_as_int(publishing, "Publishing Queue Count")
        uploading_count = self._metric_value_as_int(publishing, "Uploading Count")
        uploaded_count = self._metric_value_as_int(publishing, "Uploaded Count")
        waiting_media_link = self._metric_value_as_int(
            publishing,
            "Waiting For Media Link",
        )
        failed_jobs = self._metric_value_as_int(publishing, "Failed Count")
        retry_required = self._metric_value_as_int(
            publishing,
            "Retry Required Count",
        )
        publishing_complete = self._metric_value_as_int(
            publishing,
            "Publishing Complete",
        )
        wall_pending = self._metric_value_as_int(publishing, "Wall Pending")
        wall_processing = self._metric_value_as_int(publishing, "Wall Processing")
        wall_failed = self._metric_value_as_int(publishing, "Wall Failed")
        mass_pending = self._metric_value_as_int(publishing, "Mass PPV Pending")
        mass_failed = self._metric_value_as_int(publishing, "Mass PPV Failed")
        queue_attention = self._metric_value_as_int(publishing, "Queue Attention")

        items: list[WorkspacePublishingQueueItem] = []

        if queue_count:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_queue_overview",
                    title="Publishing Queue overview",
                    detail=f"{self._format_count(queue_count)} Publishing Job(s) are in the operational queue.",
                    status="Ready",
                    severity="info",
                    action_required=False,
                    source="Publishing",
                )
            )
        if waiting_media_link:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="waiting_media_links",
                    title="Waiting for Media Links",
                    detail=f"{self._format_count(waiting_media_link)} Publishing Job(s) need manual Fanvue Media Links.",
                    status="Requires Attention",
                    severity="warning",
                    action_required=True,
                    source="Publishing",
                )
            )
        if retry_required:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_retry_required",
                    title="Retry required",
                    detail=f"{self._format_count(retry_required)} Publishing Job(s) are ready for retry review.",
                    status="Requires Attention",
                    severity="warning",
                    action_required=True,
                    source="Publishing",
                )
            )
        if failed_jobs:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_job_failures",
                    title="Failed Publishing Jobs",
                    detail=f"{self._format_count(failed_jobs)} Publishing Job upload(s) failed.",
                    status="Failed",
                    severity="critical",
                    action_required=True,
                    source="Publishing",
                )
            )
        if uploading_count or uploaded_count:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_upload_progress",
                    title="Upload progress",
                    detail=(
                        f"{self._format_count(uploading_count)} uploading, "
                        f"{self._format_count(uploaded_count)} uploaded."
                    ),
                    status="Publishing" if uploading_count else "Ready",
                    severity="info",
                    action_required=False,
                    source="Publishing",
                )
            )
        if publishing_complete:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_complete",
                    title="Publishing complete",
                    detail=f"{self._format_count(publishing_complete)} Publishing Job(s) are complete.",
                    status="Completed",
                    severity="info",
                    action_required=False,
                    source="Publishing",
                )
            )
        if failed_total:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_failures",
                    title="Publishing failures",
                    detail=f"{self._format_count(failed_total)} publishing item(s) failed.",
                    status="Failed",
                    severity="critical",
                    action_required=True,
                    source="Publishing",
                )
            )
        if queue_attention:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="queue_attention",
                    title="Publishing queue attention",
                    detail=f"{self._format_count(queue_attention)} queue item(s) require review.",
                    status="Requires Attention",
                    severity="warning",
                    action_required=True,
                    source="Publishing",
                )
            )
        if wall_failed:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="wall_publishing",
                    title="Wall publishing failures",
                    detail=f"{self._format_count(wall_failed)} wall publishing item(s) failed.",
                    status="Failed",
                    severity="critical",
                    action_required=True,
                    source="Wall Publishing",
                )
            )
        if wall_processing:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="wall_publishing",
                    title="Wall publishing in progress",
                    detail=f"{self._format_count(wall_processing)} wall publishing item(s) are processing.",
                    status="Publishing",
                    severity="info",
                    action_required=False,
                    source="Wall Publishing",
                )
            )
        if wall_pending:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="wall_publishing",
                    title="Wall publishing pending",
                    detail=f"{self._format_count(wall_pending)} wall publishing item(s) are ready.",
                    status="Ready",
                    severity="info",
                    action_required=False,
                    source="Wall Publishing",
                )
            )
        if mass_failed:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="mass_ppv_publishing",
                    title="Mass PPV publishing failures",
                    detail=f"{self._format_count(mass_failed)} Mass PPV publishing item(s) failed.",
                    status="Failed",
                    severity="critical",
                    action_required=True,
                    source="Mass PPV Publishing",
                )
            )
        if mass_pending:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="mass_ppv_publishing",
                    title="Mass PPV publishing pending",
                    detail=f"{self._format_count(mass_pending)} Mass PPV publishing item(s) are ready.",
                    status="Ready",
                    severity="info",
                    action_required=False,
                    source="Mass PPV Publishing",
                )
            )
        if completed:
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="completed_publishing",
                    title="Recently completed publishing",
                    detail=f"{self._format_count(completed)} publishing item(s) completed recently.",
                    status="Completed",
                    severity="info",
                    action_required=False,
                    source="Publishing",
                )
            )
        if pending_total and not (wall_pending or mass_pending):
            items.append(
                WorkspacePublishingQueueItem(
                    queue_type="publishing_pending",
                    title="Publishing work pending",
                    detail=f"{self._format_count(pending_total)} publishing item(s) are pending.",
                    status="Ready",
                    severity="info",
                    action_required=False,
                    source="Publishing",
                )
            )

        items.extend(self._future_publishing_queue_placeholders())
        return self._sort_publishing_queue(items)

    def _safe_business_optimization_card(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        product_business_cards: tuple[WorkspaceProductBusinessCard, ...] = (),
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
        customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = (),
    ) -> WorkspaceBusinessOptimizationCard | None:
        try:
            return self._business_optimization_card(
                summaries=summaries,
                product_business_cards=product_business_cards,
                telegram_business_cards=telegram_business_cards,
                customer_business_cards=customer_business_cards,
            )
        except Exception:
            return None

    def _business_optimization_card(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        product_business_cards: tuple[WorkspaceProductBusinessCard, ...] = (),
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
        customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = (),
    ) -> WorkspaceBusinessOptimizationCard:
        publishing = summaries.get("Publishing")
        snapshot = self.business_optimization_service.build_snapshot(
            product_business_snapshots=tuple(
                card.product_business for card in product_business_cards
            ),
            telegram_business_snapshots=tuple(
                card.telegram_business for card in telegram_business_cards
            ),
            customer_business_snapshots=tuple(
                card.customer_business for card in customer_business_cards
            ),
            publishing_summary=(
                self._business_optimization_publishing_summary(publishing)
                if publishing is not None
                else None
            ),
            metadata={"source": "CreatorWorkspaceService"},
        )
        product_summary = self._attribute(snapshot, "product_business_summary", {})
        customer_summary = self._attribute(snapshot, "customer_business_summary", {})
        telegram_summary = self._attribute(snapshot, "telegram_business_summary", {})
        publishing_summary = self._attribute(snapshot, "publishing_summary", {})
        return WorkspaceBusinessOptimizationCard(
            business_optimization=snapshot,
            overall_business_health=self._value(self._attribute(snapshot, "health", "UNKNOWN")),
            performance_health=self._value(self._attribute(snapshot, "performance_health", "UNKNOWN")),
            strategy_health=self._value(self._attribute(snapshot, "strategy_health", "UNKNOWN")),
            revenue_readiness=str(self._attribute(snapshot, "revenue_readiness", "unknown")),
            publishing_readiness=(
                "needs_media_links"
                if self._attribute(publishing_summary, "waiting_media_link_count", 0)
                else "blocked"
                if self._attribute(publishing_summary, "failed_count", 0)
                else "ready"
                if self._attribute(publishing_summary, "available")
                else "unknown"
            ),
            product_health=self._business_optimization_rollup_health(
                product_summary,
                "needs_attention_count",
                "product_count",
            ),
            customer_health=self._business_optimization_rollup_health(
                customer_summary,
                "at_risk_count",
                "customer_count",
            ),
            telegram_health=self._business_optimization_rollup_health(
                telegram_summary,
                "needs_attention_count",
                "customer_count",
            ),
            high_impact_opportunity_count=len(
                tuple(self._attribute(snapshot, "high_impact_opportunities", ()) or ())
            ),
            critical_recommendation_count=sum(
                1
                for action in tuple(
                    self._attribute(snapshot, "prioritized_recommendations", ()) or ()
                )
                if self._value(self._attribute(action, "priority", "")) == "CRITICAL"
            ),
            today_action_count=len(
                tuple(self._attribute(snapshot, "recommended_today_actions", ()) or ())
            ),
            this_week_action_count=len(
                tuple(self._attribute(snapshot, "recommended_this_week_actions", ()) or ())
            ),
            next_recommended_business_action=(
                self._attribute(snapshot, "next_recommended_business_action")
                or self._attribute(
                    self._attribute(snapshot, "recommendation_summary", {}),
                    "next_recommended_action",
                )
                or "Review Business"
            ),
            compatibility=bool(
                self._attribute(
                    self._attribute(snapshot, "compatibility", {}),
                    "read_only",
                    True,
                )
            ),
        )

    @staticmethod
    def _business_optimization_rollup_health(
        summary: Any,
        attention_key: str,
        count_key: str,
    ) -> str:
        if not summary:
            return "UNKNOWN"
        if isinstance(summary, dict):
            attention = int(summary.get(attention_key) or 0)
            count = int(summary.get(count_key) or 0)
        else:
            attention = int(getattr(summary, attention_key, 0) or 0)
            count = int(getattr(summary, count_key, 0) or 0)
        if attention:
            return "NEEDS_ATTENTION"
        if count:
            return "HEALTHY"
        return "UNKNOWN"

    def _business_optimization_publishing_summary(
        self,
        publishing: WorkspaceSummary,
    ) -> dict[str, int]:
        return {
            "queue_count": self._metric_value_as_int(
                publishing,
                "Publishing Queue Count",
            ),
            "waiting_media_link_count": self._metric_value_as_int(
                publishing,
                "Waiting For Media Link",
            )
            or self._metric_value_as_int(publishing, "Missing Media Link"),
            "failed_count": self._metric_value_as_int(publishing, "Failed Count")
            or self._metric_value_as_int(publishing, "Failed Uploads"),
            "ready_count": self._metric_value_as_int(publishing, "Ready To Publish"),
        }

    def _business_optimization_summary(
        self,
        *,
        business_optimization_card: WorkspaceBusinessOptimizationCard | None = None,
    ) -> WorkspaceBusinessOptimizationSummary:
        if business_optimization_card is None:
            return WorkspaceBusinessOptimizationSummary(
                title="Business Optimization",
                metrics=(
                    WorkspaceMetric("Overall Business Health", "UNKNOWN"),
                    WorkspaceMetric("Performance Health", "UNKNOWN"),
                    WorkspaceMetric("Strategy Health", "UNKNOWN"),
                    WorkspaceMetric("Revenue Readiness", "unknown"),
                    WorkspaceMetric("Publishing Readiness", "unknown"),
                    WorkspaceMetric("Product Health", "UNKNOWN"),
                    WorkspaceMetric("Customer Health", "UNKNOWN"),
                    WorkspaceMetric("Telegram Health", "UNKNOWN"),
                    WorkspaceMetric("High-impact Opportunities", "0"),
                    WorkspaceMetric("Critical Recommendations", "0"),
                    WorkspaceMetric("Today's Business Actions", "0"),
                    WorkspaceMetric("This Week's Business Actions", "0"),
                    WorkspaceMetric("Next Recommended Business Action", "Review Business"),
                ),
                note="Business Optimization read model is unavailable.",
            )
        return WorkspaceBusinessOptimizationSummary(
            title="Business Optimization",
            metrics=(
                WorkspaceMetric("Overall Business Health", business_optimization_card.overall_business_health),
                WorkspaceMetric("Performance Health", business_optimization_card.performance_health),
                WorkspaceMetric("Strategy Health", business_optimization_card.strategy_health),
                WorkspaceMetric("Revenue Readiness", business_optimization_card.revenue_readiness),
                WorkspaceMetric("Publishing Readiness", business_optimization_card.publishing_readiness),
                WorkspaceMetric("Product Health", business_optimization_card.product_health),
                WorkspaceMetric("Customer Health", business_optimization_card.customer_health),
                WorkspaceMetric("Telegram Health", business_optimization_card.telegram_health),
                WorkspaceMetric("High-impact Opportunities", self._format_count(business_optimization_card.high_impact_opportunity_count)),
                WorkspaceMetric("Critical Recommendations", self._format_count(business_optimization_card.critical_recommendation_count)),
                WorkspaceMetric("Today's Business Actions", self._format_count(business_optimization_card.today_action_count)),
                WorkspaceMetric("This Week's Business Actions", self._format_count(business_optimization_card.this_week_action_count)),
                WorkspaceMetric("Next Recommended Business Action", business_optimization_card.next_recommended_business_action),
            ),
            note="Presentation-only Business Optimization dashboard; BusinessOptimizationService owns aggregation.",
        )

    def _safe_content_opportunity_card(self) -> WorkspaceContentOpportunityCard | None:
        try:
            return self._content_opportunity_card()
        except Exception:
            return None

    def _content_opportunity_card(self) -> WorkspaceContentOpportunityCard:
        snapshot = self.content_opportunity_service.build_snapshot()
        completed_follow_ups = sum(
            1
            for item in tuple(
                self._attribute(snapshot, "follow_up_opportunities", ()) or ()
            )
            if self._value(self._attribute(item, "status", "")).upper()
            == "COMPLETED"
        )
        next_action = (
            tuple(self._attribute(snapshot, "next_recommended_actions", ()) or ())
            or tuple(
                self._attribute(
                    self._attribute(snapshot, "summary", {}),
                    "next_recommended_actions",
                    (),
                )
                or ()
            )
            or ("Review Content Opportunities",)
        )[0]
        return WorkspaceContentOpportunityCard(
            content_opportunity=snapshot,
            opportunity_health=self._value(
                self._attribute(snapshot, "opportunity_health", "UNKNOWN")
            ),
            total_requests=int(self._attribute(snapshot, "total_requests", 0) or 0),
            matched_requests=int(self._attribute(snapshot, "matched_count", 0) or 0),
            unmatched_requests=int(self._attribute(snapshot, "unmatched_count", 0) or 0),
            matched_percentage=float(
                self._attribute(snapshot, "matched_percentage", 0.0) or 0.0
            ),
            unmatched_percentage=float(
                self._attribute(snapshot, "unmet_percentage", 0.0) or 0.0
            ),
            trending_topic_count=len(
                tuple(self._attribute(snapshot, "trending_topics", ()) or ())
            ),
            growing_topic_count=len(
                tuple(self._attribute(snapshot, "growing_topics", ()) or ())
            ),
            repeat_demand_count=int(
                self._attribute(snapshot, "repeat_request_count", 0) or 0
            ),
            vip_demand_count=int(
                self._attribute(snapshot, "vip_request_count", 0) or 0
            ),
            highest_priority_opportunity_count=len(
                tuple(
                    self._attribute(
                        snapshot,
                        "highest_priority_opportunities",
                        (),
                    )
                    or ()
                )
            ),
            creator_recommendation_count=int(
                self._attribute(snapshot, "recommendation_count", 0) or 0
            ),
            resolution_ready_count=int(
                self._attribute(snapshot, "resolution_ready_count", 0) or 0
            ),
            waiting_customer_count=int(
                self._attribute(snapshot, "waiting_customer_count", 0) or 0
            ),
            waiting_customers=tuple(
                self._attribute(snapshot, "waiting_customers", ()) or ()
            ),
            resolved_opportunity_count=len(
                tuple(self._attribute(snapshot, "resolution_records", ()) or ())
            ),
            pending_follow_up_count=int(
                self._attribute(snapshot, "pending_follow_up_count", 0) or 0
            ),
            ready_follow_up_count=int(
                self._attribute(snapshot, "ready_follow_up_count", 0) or 0
            ),
            completed_follow_up_count=completed_follow_ups,
            next_recommended_action=str(next_action),
            compatibility=bool(
                self._attribute(
                    self._attribute(snapshot, "compatibility", {}),
                    "read_only",
                    True,
                )
            ),
        )

    def _content_opportunity_summary(
        self,
        *,
        content_opportunity_card: WorkspaceContentOpportunityCard | None = None,
    ) -> WorkspaceContentOpportunitySummary:
        if content_opportunity_card is None:
            return WorkspaceContentOpportunitySummary(
                title="Content Opportunity",
                metrics=(
                    WorkspaceMetric("Total Requests", "0"),
                    WorkspaceMetric("Matched Requests", "0"),
                    WorkspaceMetric("Unmatched Requests", "0"),
                    WorkspaceMetric("Matched Percentage", "0%"),
                    WorkspaceMetric("Unmatched Percentage", "0%"),
                    WorkspaceMetric("Opportunity Health", "UNKNOWN"),
                    WorkspaceMetric("Trending Topics", "0"),
                    WorkspaceMetric("Growing Topics", "0"),
                    WorkspaceMetric("Repeat Demand", "0"),
                    WorkspaceMetric("VIP Demand", "0"),
                    WorkspaceMetric("Highest Priority Opportunities", "0"),
                    WorkspaceMetric("Suggested Creator Opportunities", "0"),
                    WorkspaceMetric("Resolution Ready", "0"),
                    WorkspaceMetric("Waiting Customers", "0"),
                    WorkspaceMetric("Resolved Opportunities", "0"),
                    WorkspaceMetric("Pending Follow-ups", "0"),
                    WorkspaceMetric("Ready Follow-ups", "0"),
                    WorkspaceMetric("Completed Follow-ups", "0"),
                    WorkspaceMetric(
                        "Next Recommended Action",
                        "Review Content Opportunities",
                    ),
                ),
                note="Content Opportunity read model is unavailable.",
            )
        return WorkspaceContentOpportunitySummary(
            title="Content Opportunity",
            metrics=(
                WorkspaceMetric("Total Requests", self._format_count(content_opportunity_card.total_requests)),
                WorkspaceMetric("Matched Requests", self._format_count(content_opportunity_card.matched_requests)),
                WorkspaceMetric("Unmatched Requests", self._format_count(content_opportunity_card.unmatched_requests)),
                WorkspaceMetric("Matched Percentage", f"{content_opportunity_card.matched_percentage:.0%}"),
                WorkspaceMetric("Unmatched Percentage", f"{content_opportunity_card.unmatched_percentage:.0%}"),
                WorkspaceMetric("Opportunity Health", content_opportunity_card.opportunity_health),
                WorkspaceMetric("Trending Topics", self._format_count(content_opportunity_card.trending_topic_count)),
                WorkspaceMetric("Growing Topics", self._format_count(content_opportunity_card.growing_topic_count)),
                WorkspaceMetric("Repeat Demand", self._format_count(content_opportunity_card.repeat_demand_count)),
                WorkspaceMetric("VIP Demand", self._format_count(content_opportunity_card.vip_demand_count)),
                WorkspaceMetric("Highest Priority Opportunities", self._format_count(content_opportunity_card.highest_priority_opportunity_count)),
                WorkspaceMetric("Suggested Creator Opportunities", self._format_count(content_opportunity_card.creator_recommendation_count)),
                WorkspaceMetric("Resolution Ready", self._format_count(content_opportunity_card.resolution_ready_count)),
                WorkspaceMetric("Waiting Customers", self._format_count(content_opportunity_card.waiting_customer_count)),
                WorkspaceMetric("Resolved Opportunities", self._format_count(content_opportunity_card.resolved_opportunity_count)),
                WorkspaceMetric("Pending Follow-ups", self._format_count(content_opportunity_card.pending_follow_up_count)),
                WorkspaceMetric("Ready Follow-ups", self._format_count(content_opportunity_card.ready_follow_up_count)),
                WorkspaceMetric("Completed Follow-ups", self._format_count(content_opportunity_card.completed_follow_up_count)),
                WorkspaceMetric("Next Recommended Action", content_opportunity_card.next_recommended_action),
            ),
            note="Presentation-only Content Opportunity Center; ContentOpportunityService owns demand intelligence.",
        )

    def _content_opportunity_notifications(
        self,
        card: WorkspaceContentOpportunityCard | None,
    ) -> tuple[WorkspaceNotification, ...]:
        if card is None:
            return ()
        notifications: list[WorkspaceNotification] = []
        if card.matched_requests:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_match",
                    title="Existing Product matched customer demand",
                    detail=(
                        f"{self._format_count(card.matched_requests)} matched "
                        "content request(s) are available for review."
                    ),
                    severity="info",
                    status="monitoring",
                    action_required=False,
                    source="Content Opportunity",
                )
            )
        if card.unmatched_requests:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_new_demand",
                    title="New customer demand recorded",
                    detail=(
                        f"{self._format_count(card.unmatched_requests)} unmatched "
                        "content request(s) are visible in Content Opportunity."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        if card.growing_topic_count:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_growing_demand",
                    title="Growing content demand detected",
                    detail=(
                        f"{self._format_count(card.growing_topic_count)} growing "
                        "topic(s) need creator review."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        if card.vip_demand_count:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_vip_demand",
                    title="VIP content request received",
                    detail=(
                        f"{self._format_count(card.vip_demand_count)} VIP demand "
                        "signal(s) are present."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        if card.resolution_ready_count:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_resolution_ready",
                    title="New Product satisfies previous requests",
                    detail=(
                        f"{self._format_count(card.resolution_ready_count)} "
                        "resolution(s) are ready for creator review."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        if card.ready_follow_up_count:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_follow_up_ready",
                    title="Follow-up opportunities ready",
                    detail=(
                        f"{self._format_count(card.ready_follow_up_count)} "
                        "waiting customer follow-up(s) are ready."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        if card.highest_priority_opportunity_count:
            notifications.append(
                WorkspaceNotification(
                    notification_type="content_opportunity_high_priority",
                    title="High-priority content opportunity detected",
                    detail=(
                        f"{self._format_count(card.highest_priority_opportunity_count)} "
                        "high-priority opportunity/opportunities are visible."
                    ),
                    severity="warning",
                    status="open",
                    action_required=True,
                    source="Content Opportunity",
                )
            )
        return tuple(notifications)

    def _safe_customer_business_cards(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[WorkspaceCustomerBusinessCard, ...]:
        try:
            return self._customer_business_cards(
                creator_profile=creator_profile,
                active_account=active_account,
            )
        except Exception:
            return ()

    def _customer_business_cards(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[WorkspaceCustomerBusinessCard, ...]:
        cards: list[WorkspaceCustomerBusinessCard] = []
        for context in self._customer_business_contexts(
            creator_profile=creator_profile,
            active_account=active_account,
        ):
            try:
                cards.append(self._customer_business_card(context))
            except Exception:
                continue
        return tuple(cards)

    def _customer_business_contexts(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[dict[str, Any], ...]:
        if self.customer_business_contexts_fetcher is None:
            return ()
        raw_contexts = self.customer_business_contexts_fetcher(
            creator_profile=creator_profile,
            active_account=active_account,
        )
        contexts = []
        for item in tuple(raw_contexts or ()):
            if isinstance(item, dict):
                contexts.append(item)
            else:
                contexts.append({"customer_business_snapshot": item})
        return tuple(contexts)

    def _customer_business_card(
        self,
        context: dict[str, Any],
    ) -> WorkspaceCustomerBusinessCard:
        snapshot = context.get(
            "customer_business_snapshot",
        ) or self.customer_business_service.build_snapshot(**context)
        retention = self._attribute(snapshot, "retention_summary")
        growth = self._attribute(snapshot, "growth_summary")
        value = self._attribute(snapshot, "customer_value")
        return WorkspaceCustomerBusinessCard(
            customer_id=(
                self._attribute(snapshot, "customer_id")
                or self._attribute(
                    self._attribute(snapshot, "customer_identity", {}),
                    "customer_id",
                )
            ),
            provider=self._attribute(snapshot, "provider", "provider_neutral")
            or "provider_neutral",
            customer_business=snapshot,
            customer_health=self._value(
                self._attribute(snapshot, "customer_health", "UNKNOWN")
            ),
            journey_stage=self._value(
                self._attribute(snapshot, "journey_stage", "UNKNOWN")
            ),
            value_tier=self._value(
                self._attribute(snapshot, "value_tier", "UNKNOWN")
            ),
            retention_status=self._value(
                self._attribute(retention, "risk", "UNKNOWN")
            ),
            growth_stage=self._value(
                self._attribute(growth, "stage", "UNKNOWN")
            ),
            next_recommended_action=(
                self._attribute(snapshot, "next_recommended_action")
                or self._attribute(growth, "recommended_growth_action")
                or self._attribute(retention, "recommended_follow_up")
                or "Review Customer"
            ),
            growth_opportunity_count=len(
                tuple(self._attribute(growth, "opportunities", ()) or ())
            ),
            retention_opportunity_count=len(
                tuple(self._attribute(retention, "opportunities", ()) or ())
            ),
            compatibility=bool(
                self._attribute(
                    self._attribute(snapshot, "compatibility", {}),
                    "read_only",
                    True,
                )
            ),
        )

    def _customer_business_summary(
        self,
        *,
        customer_business_cards: tuple[WorkspaceCustomerBusinessCard, ...] = (),
    ) -> WorkspaceCustomerBusinessSummary:
        total = len(customer_business_cards)
        active = sum(
            1
            for card in customer_business_cards
            if card.customer_health in {"HEALTHY", "OPPORTUNITY", "VIP"}
        )
        new_customers = sum(
            1 for card in customer_business_cards if card.value_tier == "NEW"
        )
        returning = sum(
            1
            for card in customer_business_cards
            if card.journey_stage
            in {"RELATIONSHIP_BUILDING", "PRODUCT_DISCOVERY", "ACTIVE_BUYER"}
        )
        vip = sum(
            1
            for card in customer_business_cards
            if card.value_tier in {"VIP", "VIP_POTENTIAL"}
        )
        at_risk = sum(
            1
            for card in customer_business_cards
            if card.customer_health in {"AT_RISK", "NEEDS_ATTENTION"}
            or card.retention_status in {"AT_RISK", "RE_ENGAGEMENT_CANDIDATE"}
        )
        dormant = sum(
            1
            for card in customer_business_cards
            if card.customer_health == "DORMANT"
            or card.retention_status == "DORMANT"
        )
        growth_opportunities = sum(
            card.growth_opportunity_count for card in customer_business_cards
        )
        retention_opportunities = sum(
            card.retention_opportunity_count for card in customer_business_cards
        )
        next_actions = sum(
            1
            for card in customer_business_cards
            if card.next_recommended_action
            and card.next_recommended_action != "No Customer Business Action"
        )
        return WorkspaceCustomerBusinessSummary(
            title="Customer Business",
            metrics=(
                WorkspaceMetric("Customer Business Customers", self._format_count(total)),
                WorkspaceMetric("Active Customers", self._format_count(active)),
                WorkspaceMetric("New Customers", self._format_count(new_customers)),
                WorkspaceMetric("Returning Customers", self._format_count(returning)),
                WorkspaceMetric("VIP Customers", self._format_count(vip)),
                WorkspaceMetric("At-risk Customers", self._format_count(at_risk)),
                WorkspaceMetric("Dormant Customers", self._format_count(dormant)),
                WorkspaceMetric("Growth Opportunities", self._format_count(growth_opportunities)),
                WorkspaceMetric("Retention Opportunities", self._format_count(retention_opportunities)),
                WorkspaceMetric("Recommended Customer Actions", self._format_count(next_actions)),
                WorkspaceMetric(
                    "Operating State",
                    "Everything operating normally"
                    if total and not at_risk and not dormant
                    else "Needs Review"
                    if total and (at_risk or dormant or next_actions)
                    else "No Customer Business customers",
                ),
            ),
            note="Presentation-only Customer Business dashboard; CustomerBusinessService owns aggregation.",
        )

    def _safe_telegram_business_cards(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[WorkspaceTelegramBusinessCard, ...]:
        try:
            return self._telegram_business_cards(
                creator_profile=creator_profile,
                active_account=active_account,
            )
        except Exception:
            return ()

    def _telegram_business_cards(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[WorkspaceTelegramBusinessCard, ...]:
        contexts = self._telegram_business_contexts(
            creator_profile=creator_profile,
            active_account=active_account,
        )
        cards: list[WorkspaceTelegramBusinessCard] = []
        for context in contexts:
            try:
                cards.append(self._telegram_business_card(context))
            except Exception:
                continue
        return tuple(cards)

    def _telegram_business_contexts(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
    ) -> tuple[dict[str, Any], ...]:
        if self.telegram_business_contexts_fetcher is None:
            return ()
        raw_contexts = self.telegram_business_contexts_fetcher(
            creator_profile=creator_profile,
            active_account=active_account,
        )
        contexts = []
        for item in tuple(raw_contexts or ()):
            if isinstance(item, dict):
                contexts.append(item)
            else:
                contexts.append({"telegram_business_snapshot": item})
        return tuple(contexts)

    def _telegram_business_card(
        self,
        context: dict[str, Any],
    ) -> WorkspaceTelegramBusinessCard:
        snapshot = context.get(
            "telegram_business_snapshot",
        ) or self.telegram_business_service.build_snapshot(**context)
        operation = context.get(
            "conversation_operation",
        ) or self.conversation_operations_service.build_operation(
            telegram_business_snapshot=snapshot,
        )
        sales = context.get(
            "sales_management",
        ) or self.sales_management_service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
        )
        delivery = context.get(
            "delivery_management",
        ) or self.delivery_management_service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
        )
        relationship = context.get(
            "relationship_management",
        ) or self.relationship_management_service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            delivery_management=delivery,
        )
        relationship_recommendation = self._attribute(
            relationship,
            "recommendation",
        )
        sales_recommendation = self._attribute(sales, "recommendation")
        delivery_recommendation = self._attribute(delivery, "recommendation")
        return WorkspaceTelegramBusinessCard(
            customer_id=(
                self._attribute(snapshot, "customer_id")
                or self._attribute(
                    self._attribute(snapshot, "customer_identity", {}),
                    "customer_id",
                )
            ),
            provider=self._attribute(snapshot, "provider", "telegram") or "telegram",
            telegram_business=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            delivery_management=delivery,
            relationship_management=relationship,
            next_recommended_action=(
                self._attribute(
                    relationship_recommendation,
                    "recommended_next_action",
                )
                or self._attribute(snapshot, "next_recommended_business_action")
                or "No Relationship Action"
            ),
            relationship_health=self._value(
                self._attribute(relationship, "relationship_health", "UNKNOWN")
            ),
            conversation_status=self._value(
                self._attribute(operation, "status", "UNKNOWN")
            ),
            sales_action=(
                self._attribute(sales_recommendation, "recommended_next_action")
                or "No Sales Action"
            ),
            delivery_action=(
                self._attribute(delivery_recommendation, "recommended_next_action")
                or "No Delivery"
            ),
            business_health=self._attribute(
                snapshot,
                "business_health",
                "UNKNOWN",
            )
            or "UNKNOWN",
            compatibility=True,
        )

    def _telegram_operations_summary(
        self,
        summaries: dict[str, WorkspaceSummary],
        *,
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
    ) -> WorkspaceTelegramOperationsSummary:
        customers = summaries["Customer Conversations"]
        experiences = summaries["Experiences"]
        publishing = summaries["Publishing"]
        products = summaries["Products"]

        active_conversations = self._metric_value_as_int(customers, "Known Customers")
        active_experiences = self._metric_value_as_int(
            experiences,
            "Ready for Product Review",
        )
        customers_needing_followup = self._metric_value_as_int(
            customers,
            "Missing Profiles",
        )
        free_deliveries = self._metric_value_as_int(products, "Free Products")
        paid_offers = self._metric_value_as_int(products, "Paid Products")
        recent_delivery_decisions = free_deliveries + paid_offers
        active_journeys = max(
            active_conversations - customers_needing_followup,
            0,
        )
        active_current_experiences = self._metric_value_as_int(
            experiences,
            "Story Ready",
        )
        memory_summaries = active_conversations
        telegram_ready = self._metric_value_as_int(
            publishing,
            "Telegram-ready Items",
        )
        recommended_actions = sum(
            1
            for value in (
                customers_needing_followup,
                active_current_experiences,
                paid_offers,
            )
            if value
        )
        if telegram_business_cards:
            active_conversations = len(telegram_business_cards)
            active_current_experiences = sum(
                1
                for card in telegram_business_cards
                if self._attribute(
                    card.telegram_business,
                    "current_experience_id",
                )
            )
            active_experiences = active_current_experiences
            active_journeys = sum(
                1
                for card in telegram_business_cards
                if card.conversation_status
                not in {"COMPLETED", "UNKNOWN", "IDLE"}
            )
            free_deliveries = sum(
                1
                for card in telegram_business_cards
                if card.delivery_action == "Deliver FREE Product"
            )
            paid_offers = sum(
                1
                for card in telegram_business_cards
                if card.sales_action
                in {"Offer Premium Product", "Offer Bundle", "Offer Story"}
            )
            recent_delivery_decisions = sum(
                1
                for card in telegram_business_cards
                if card.delivery_action
                not in {"No Delivery", "Wait"}
            )
            memory_summaries = len(telegram_business_cards)
            customers_needing_followup = sum(
                1
                for card in telegram_business_cards
                if card.next_recommended_action
                in {"Follow Up", "Re-engage Customer"}
            )
            recommended_actions = sum(
                1
                for card in telegram_business_cards
                if card.next_recommended_action
                and card.next_recommended_action != "No Relationship Action"
            )
            pending_offers = sum(
                len(
                    self._attribute(
                        card.conversation_operation,
                        "pending_offer_ids",
                        (),
                    )
                    or ()
                )
                for card in telegram_business_cards
            )
            pending_deliveries = sum(
                1
                for card in telegram_business_cards
                if card.delivery_action
                in {
                    "Deliver FREE Product",
                    "Deliver Premium Product",
                    "Deliver Bundle",
                    "Deliver Story",
                    "Send Media Link",
                }
            )
            vip_opportunities = sum(
                1
                for card in telegram_business_cards
                if card.relationship_health == "VIP_OPPORTUNITY"
            )
        else:
            pending_offers = paid_offers
            pending_deliveries = recent_delivery_decisions
            vip_opportunities = 0
        operating_normally = (
            bool(telegram_business_cards)
            and not customers_needing_followup
            and not pending_deliveries
            and not pending_offers
        )

        return WorkspaceTelegramOperationsSummary(
            title="Telegram Operations",
            metrics=(
                WorkspaceMetric("Active Conversations", self._format_count(active_conversations)),
                WorkspaceMetric("Active Experiences", self._format_count(active_current_experiences)),
                WorkspaceMetric("Current Customer Journeys", self._format_count(active_journeys)),
                WorkspaceMetric("Recent Delivery Decisions", self._format_count(recent_delivery_decisions)),
                WorkspaceMetric("FREE Deliveries", self._format_count(free_deliveries)),
                WorkspaceMetric("PAID Media Link Deliveries", self._format_count(paid_offers)),
                WorkspaceMetric("Commerce Memory Summaries", self._format_count(memory_summaries)),
                WorkspaceMetric("Customers Needing Follow-Up", self._format_count(customers_needing_followup)),
                WorkspaceMetric("Pending Offers", self._format_count(pending_offers)),
                WorkspaceMetric("Pending Deliveries", self._format_count(pending_deliveries)),
                WorkspaceMetric("VIP Opportunities", self._format_count(vip_opportunities)),
                WorkspaceMetric("Recommended Telegram Actions", self._format_count(recommended_actions)),
                WorkspaceMetric("Telegram-ready Items", self._format_count(telegram_ready)),
                WorkspaceMetric(
                    "Telegram Business Customers",
                    self._format_count(len(telegram_business_cards)),
                ),
                WorkspaceMetric(
                    "Operating State",
                    "Everything operating normally"
                    if operating_normally
                    else "Needs Review"
                    if recommended_actions
                    else "No Telegram Business customers",
                ),
            ),
            note="Presentation-only Telegram Business hub; domain services retain ownership.",
        )

    def _safe_telegram_operations(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
    ) -> tuple[WorkspaceTelegramOperationItem, ...]:
        try:
            return self._telegram_operations(
                summaries["Telegram Operations"],
                telegram_business_cards=telegram_business_cards,
            )
        except Exception:
            return (
                WorkspaceTelegramOperationItem(
                    operation_type="system",
                    title="Telegram Operations unavailable",
                    detail="Telegram Commerce operation summaries could not be loaded.",
                    status="Requires Attention",
                    severity="warning",
                    target="Customer Workspace",
                    source="CreatorWorkspaceService",
                    future_ready=True,
                ),
            )

    def _telegram_operations(
        self,
        telegram: WorkspaceSummary,
        *,
        telegram_business_cards: tuple[WorkspaceTelegramBusinessCard, ...] = (),
    ) -> tuple[WorkspaceTelegramOperationItem, ...]:
        active_conversations = self._metric_value_as_int(
            telegram,
            "Active Conversations",
        )
        active_experiences = self._metric_value_as_int(
            telegram,
            "Active Experiences",
        )
        delivery_decisions = self._metric_value_as_int(
            telegram,
            "Recent Delivery Decisions",
        )
        commerce_memory = self._metric_value_as_int(
            telegram,
            "Commerce Memory Summaries",
        )
        free_deliveries = self._metric_value_as_int(telegram, "FREE Deliveries")
        paid_offers = self._metric_value_as_int(
            telegram,
            "PAID Media Link Deliveries",
        )
        followup = self._metric_value_as_int(
            telegram,
            "Customers Needing Follow-Up",
        )

        items: list[WorkspaceTelegramOperationItem] = []
        for card in telegram_business_cards:
            action_required = card.next_recommended_action in {
                "Follow Up",
                "Re-engage Customer",
                "Delay Selling",
            }
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="telegram_business_customer",
                    title=f"Telegram Business: {card.customer_id or 'Customer'}",
                    detail=(
                        f"{card.relationship_health} | "
                        f"{card.conversation_status} | "
                        f"Next: {card.next_recommended_action}"
                    ),
                    status=card.conversation_status,
                    severity=self._telegram_business_priority(card),
                    target="Customer Workspace",
                    source="Telegram Business",
                    action_required=action_required,
                )
            )
        if telegram_business_cards and not any(
            item.action_required for item in items
        ):
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="telegram_business_normal",
                    title="Everything operating normally",
                    detail="Telegram Business read models show no urgent customer action.",
                    status="Normal",
                    severity="info",
                    target="Customer Workspace",
                    source="Telegram Business",
                )
            )
        if active_conversations:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="active_conversations",
                    title="Active Conversations",
                    detail=f"{self._format_count(active_conversations)} customer conversation(s) are visible for Telegram Commerce review.",
                    status="Active",
                    severity="info",
                    target="Customer Workspace",
                    source="CustomerService",
                )
            )
        if active_experiences:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="current_experiences",
                    title="Current Experiences",
                    detail=f"{self._format_count(active_experiences)} Experience(s) are active in Telegram operations.",
                    status="Active",
                    severity="info",
                    target="Customer Workspace",
                    source="ExperienceService",
                )
            )
        if delivery_decisions:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="delivery_decisions",
                    title="Delivery Decisions",
                    detail=f"{self._format_count(delivery_decisions)} FREE/PAID delivery decision(s) are represented in workspace data.",
                    status="Ready",
                    severity="info",
                    target="Customer Workspace",
                    source="TelegramCommerceService",
                )
            )
        if commerce_memory:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="commerce_memory",
                    title="Commerce Memory",
                    detail=f"{self._format_count(commerce_memory)} Commerce Memory summary slot(s) are available through Customer Workspace.",
                    status="Ready",
                    severity="info",
                    target="Customer Workspace",
                    source="TelegramCommerceService",
                )
            )
        if free_deliveries:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="recent_free_deliveries",
                    title="Recent FREE Deliveries",
                    detail=f"{self._format_count(free_deliveries)} FREE delivery item(s) are available for review.",
                    status="Ready",
                    severity="info",
                    target="Customer Workspace",
                    source="TelegramCommerceService",
                )
            )
        if paid_offers:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="recent_paid_offers",
                    title="Recent PAID Offers",
                    detail=f"{self._format_count(paid_offers)} PAID Media Link offer item(s) are available for review.",
                    status="Ready",
                    severity="info",
                    target="Customer Workspace",
                    source="PublishingService",
                )
            )
        if followup:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="customers_needing_followup",
                    title="Customers Needing Follow-Up",
                    detail=f"{self._format_count(followup)} customer profile(s) need follow-up or sync review.",
                    status="Requires Attention",
                    severity="warning",
                    target="Customer Workspace",
                    source="CustomerService",
                    action_required=True,
                )
            )
        if not items:
            items.append(
                WorkspaceTelegramOperationItem(
                    operation_type="telegram_operations_empty",
                    title="Telegram Operations",
                    detail="No Telegram Commerce operations are currently surfaced.",
                    status="Idle",
                    severity="info",
                    target="Customer Workspace",
                    source="CreatorWorkspaceService",
                )
            )
        return tuple(items)

    def _future_publishing_queue_placeholders(
        self,
    ) -> tuple[WorkspacePublishingQueueItem, ...]:
        return (
            WorkspacePublishingQueueItem(
                queue_type="vault_publishing",
                title="Vault publishing queue",
                detail="Vault queue detail is not yet exposed to Creator Workspace.",
                status="Future",
                severity="info",
                action_required=False,
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
        )

    @staticmethod
    def _sort_publishing_queue(
        items: list[WorkspacePublishingQueueItem],
    ) -> tuple[WorkspacePublishingQueueItem, ...]:
        severity_order = {
            "critical": 0,
            "warning": 1,
            "info": 2,
        }
        status_order = {
            "Failed": 0,
            "Requires Attention": 1,
            "Publishing": 2,
            "Ready": 3,
            "Completed": 4,
            "Future": 5,
        }

        def sort_key(item: WorkspacePublishingQueueItem) -> tuple[int, int, int, str]:
            return (
                severity_order.get(item.severity, 3),
                status_order.get(item.status, 6),
                0 if item.action_required else 1,
                item.title,
            )

        return tuple(sorted(items, key=sort_key))

    def _safe_insights(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceInsight, ...]:
        try:
            return self._insights(summaries)
        except Exception:
            return (
                WorkspaceInsight(
                    insight_type="system",
                    category="Workspace Health",
                    title="Workspace insights unavailable",
                    current_value="Unavailable",
                    trend="Unknown",
                    delta="Unavailable",
                    detail="One or more read-only insight sources could not be loaded.",
                    future_ready=True,
                ),
            )

    def _safe_experience_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceExperienceCard, ...]:
        try:
            return self._experience_cards(creator_profile_id)
        except Exception:
            return ()

    def _safe_creator_review(
        self,
        *,
        summaries: dict[str, WorkspaceSummary],
        experience_cards: tuple[WorkspaceExperienceCard, ...],
        product_cards: tuple[WorkspaceProductCard, ...],
        publishing_cards: tuple[WorkspacePublishingCard, ...],
    ):
        try:
            return self.creator_review_service.build_workspace_review_summary(
                asset_summary=summaries["Assets"],
                experience_cards=experience_cards,
                product_cards=product_cards,
                publishing_cards=publishing_cards,
            )
        except Exception:
            return None

    def _experience_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceExperienceCard, ...]:
        if not creator_profile_id:
            return ()
        experiences = self.experience_service.list_experiences(
            creator_profile_id=creator_profile_id,
            include_archived=True,
            limit=6,
        )
        return tuple(
            self._build_experience_card(
                experience,
                creator_profile_id=creator_profile_id,
            )
            for experience in experiences
        )

    def _build_experience_card(
        self,
        experience: Any,
        *,
        creator_profile_id: int | None,
    ) -> WorkspaceExperienceCard:
        metadata = dict(self._attribute(experience, "metadata", {}) or {})
        experience_id = self._experience_id(experience)
        product_relationships = self._safe_experience_product_relationships(
            experience_id
        )
        relationship_metadata = self._relationship_metadata(product_relationships)
        merged_metadata = {**metadata, **relationship_metadata}
        product_ids = tuple(
            str(self._attribute(relationship, "product_id"))
            for relationship in product_relationships
            if self._attribute(relationship, "product_id")
        )
        delivery_types = self._product_delivery_types(
            product_ids,
            creator_profile_id=creator_profile_id,
        )
        readiness = self._experience_publishing_readiness(experience)
        compatibility = bool(
            any(
                bool(self._attribute(relationship, "compatibility", False))
                or bool(
                    self._attribute(
                        relationship,
                        "compatibility_experience_id",
                        False,
                    )
                )
                for relationship in product_relationships
            )
            or merged_metadata.get("compatibility", False)
        )
        relationship_source = self._relationship_source(
            product_relationships,
            metadata,
        )
        return WorkspaceExperienceCard(
            experience_id=experience_id,
            title=str(self._attribute(experience, "title") or "Untitled Experience"),
            experience_type=self._value(
                self._attribute(experience, "experience_type")
            )
            or "Unknown",
            summary=str(
                self._attribute(experience, "description")
                or merged_metadata.get("experience_summary")
                or merged_metadata.get("summary")
                or ""
            ),
            cover_asset_id=self._attribute(experience, "cover_asset_id"),
            asset_count=len(
                self._attribute(experience, "ordered_asset_ids", None)
                or self._attribute(experience, "asset_ids", ())
                or ()
            ),
            product_count=len(product_ids),
            publishing_readiness=readiness,
            delivery_types=delivery_types,
            themes=self._metadata_tuple(
                merged_metadata,
                "suggested_themes",
                "themes",
                "experience_themes",
            ),
            keywords=self._metadata_tuple(
                merged_metadata,
                "suggested_keywords",
                "keywords",
                "experience_keywords",
            ),
            mood=self._first_metadata_value(merged_metadata, "mood"),
            story_progression=self._first_metadata_value(
                merged_metadata,
                "story_progression",
            ),
            intelligence_coverage=self._experience_intelligence_coverage(
                merged_metadata
            ),
            relationship_source=relationship_source,
            compatibility=compatibility,
        )

    def _safe_experience_product_relationships(
        self,
        experience_id: str | None,
    ) -> tuple[Any, ...]:
        if not experience_id:
            return ()
        try:
            return tuple(
                self.experience_service.list_experience_product_relationships(
                    experience_id
                )
            )
        except Exception:
            return ()

    def _product_delivery_types(
        self,
        product_ids: tuple[str, ...],
        *,
        creator_profile_id: int | None,
    ) -> tuple[str, ...]:
        values: list[str] = []
        for product_id in product_ids:
            try:
                product = self.product_repository.get_by_id(
                    product_id,
                    creator_profile_id=creator_profile_id,
                )
            except Exception:
                product = None
            delivery_type = self._value(
                self._attribute(product, "delivery_type")
            )
            if delivery_type and delivery_type not in values:
                values.append(delivery_type)
        return tuple(values)

    def _experience_publishing_readiness(
        self,
        experience: Any,
    ) -> WorkspaceExperiencePublishingReadiness:
        try:
            asset_records = self._experience_asset_publishing_records(experience)
            readiness = self.publishing_service.project_experience_readiness(
                experience,
                asset_records=asset_records,
            )
        except Exception:
            readiness = None
        if not readiness:
            return WorkspaceExperiencePublishingReadiness(
                status="unknown",
                detail="Experience publishing readiness is unavailable.",
                source="CreatorWorkspaceService",
                compatibility=False,
            )
        return WorkspaceExperiencePublishingReadiness(
            status=str(self._attribute(readiness, "status") or "unknown"),
            detail=str(self._attribute(readiness, "detail") or ""),
            asset_count=int(self._attribute(readiness, "asset_count", 0) or 0),
            ready_asset_count=int(
                self._attribute(readiness, "ready_asset_count", 0) or 0
            ),
            source=str(
                self._attribute(readiness, "source", "PublishingService")
                or "PublishingService"
            ),
            compatibility=bool(self._attribute(readiness, "compatibility", False)),
        )

    def _experience_asset_publishing_records(
        self,
        experience: Any,
    ) -> tuple[dict[str, Any], ...]:
        asset_ids = tuple(
            self._attribute(experience, "ordered_asset_ids", None)
            or self._attribute(experience, "asset_ids", ())
            or ()
        )
        if not asset_ids:
            return ()
        try:
            items = self.asset_library_service.get_asset_items(asset_ids)
        except Exception:
            return ()
        records = []
        for item in items:
            publishing = self._attribute(item, "publishing")
            records.append(
                {
                    "asset_id": self._attribute(item, "asset_id"),
                    "provider_media_id": self._attribute(
                        publishing,
                        "provider_media_id",
                    ),
                    "provider_status": self._attribute(publishing, "status"),
                }
            )
        return tuple(records)

    @staticmethod
    def _experience_id(experience: Any) -> str | None:
        value = workspace_summaries.attribute(experience, "experience_id")
        return str(value) if value not in (None, "") else None

    @staticmethod
    def _relationship_metadata(relationships: tuple[Any, ...]) -> dict:
        merged: dict[str, Any] = {}
        for relationship in relationships:
            metadata = workspace_summaries.attribute(
                relationship,
                "metadata",
                {},
            )
            if metadata:
                merged.update(dict(metadata))
        return merged

    @staticmethod
    def _relationship_source(
        relationships: tuple[Any, ...],
        metadata: dict,
    ) -> str:
        for relationship in relationships:
            source = workspace_summaries.attribute(relationship, "source")
            if source:
                return str(source)
        return str(metadata.get("source") or "ExperienceService")

    @staticmethod
    def _first_metadata_value(metadata: dict, *keys: str) -> str | None:
        for key in keys:
            value = metadata.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @staticmethod
    def _metadata_tuple(metadata: dict, *keys: str) -> tuple[str, ...]:
        for key in keys:
            value = metadata.get(key)
            if not value:
                continue
            if isinstance(value, str):
                return (value,)
            return tuple(str(item) for item in value if str(item).strip())
        return ()

    def _experience_intelligence_coverage(self, metadata: dict) -> str:
        intelligence_markers = (
            "experience_intelligence",
            "intelligence_provenance",
            "suggested_themes",
            "suggested_keywords",
            "mood",
            "story_progression",
            "technical_continuity",
            "visual_continuity",
        )
        present = [
            marker
            for marker in intelligence_markers
            if bool(metadata.get(marker))
        ]
        if not present:
            return "Missing"
        if len(present) >= 4:
            return "Rich"
        return "Partial"

    def _safe_product_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceProductCard, ...]:
        try:
            return self._product_cards(creator_profile_id)
        except Exception:
            return ()

    def _safe_product_business_dashboard(
        self,
        creator_profile_id: int | None,
    ):
        try:
            return self._product_business_dashboard(creator_profile_id)
        except Exception:
            return None, ()

    def _product_business_dashboard(
        self,
        creator_profile_id: int | None,
    ):
        if not creator_profile_id:
            return None, ()
        displays = self._product_display_models(
            creator_profile_id=creator_profile_id,
            limit=8,
        )
        snapshots = tuple(
            self.product_business_service.build_snapshot(product_display=display)
            for display in displays
        )
        catalog_health = self.product_catalog_management_service.build_catalog_health(
            product_business_snapshots=snapshots
        )
        cards = tuple(
            self._build_product_business_card(
                display,
                product_business_snapshot=snapshot,
                catalog_health=catalog_health,
            )
            for display, snapshot in zip(displays, snapshots)
        )
        return catalog_health, cards

    def _build_product_business_card(
        self,
        display: Any,
        *,
        product_business_snapshot: Any,
        catalog_health: Any,
    ) -> WorkspaceProductBusinessCard:
        product = self._attribute(display, "product")
        availability = self.product_availability_service.build_availability(
            product=self._attribute(display, "product"),
            product_business_snapshot=product_business_snapshot,
        )
        performance = self.product_performance_service.build_performance(
            product=self._attribute(display, "product"),
            product_business_snapshot=product_business_snapshot,
        )
        improvement = self.product_improvement_service.build_improvement(
            product_business_snapshot=product_business_snapshot,
            availability=availability,
            performance=performance,
            catalog_health=catalog_health,
        )
        return WorkspaceProductBusinessCard(
            product_id=product_business_snapshot.product_id,
            product_name=str(
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or product_business_snapshot.product_name
                or "Untitled Product"
            ),
            product_business=product_business_snapshot,
            availability=availability,
            performance=performance,
            improvement=improvement,
            compatibility=bool(
                self._attribute(product, "legacy_content_item_id", None)
            ),
        )

    def _product_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceProductCard, ...]:
        if not creator_profile_id:
            return ()
        displays = self._product_display_models(
            creator_profile_id=creator_profile_id,
            limit=6,
        )
        return tuple(self._build_product_card(display) for display in displays)

    def _safe_product_review_summary(
        self,
        creator_profile_id: int | None,
    ):
        if not creator_profile_id:
            return None
        try:
            return self.product_review_service.build_summary(
                creator_profile_id=creator_profile_id,
                include_archived=False,
                limit=100,
            )
        except Exception:
            return None

    def _safe_workflow_items(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceWorkflowItem, ...]:
        try:
            return self._workflow_items(creator_profile_id)
        except Exception:
            return ()

    def _workflow_items(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceWorkflowItem, ...]:
        if not creator_profile_id:
            return ()
        displays = self._product_display_models(
            creator_profile_id=creator_profile_id,
            limit=8,
        )
        items: list[WorkspaceWorkflowItem] = []
        for display in displays:
            item = self._build_workflow_item(display)
            if item is not None:
                items.append(item)
        return tuple(items)

    def _build_workflow_item(self, display: Any) -> WorkspaceWorkflowItem | None:
        product = self._attribute(display, "product")
        if product is None:
            return None
        workflow_snapshot = self.creator_workflow_service.build_from_product_display(
            display,
            metadata={"workspace_projection": True},
        )
        product_lifecycle = self.product_lifecycle_service.build_from_workflow_snapshot(
            workflow_snapshot
        )
        review_status = self.creator_review_optimization_service.build_review_status(
            workflow_snapshot=workflow_snapshot,
            lifecycle=product_lifecycle,
            product_review=self._safe_product_review_for_display(display),
        )
        publishing_status = self.publishing_automation_service.build_status(
            workflow_snapshot=workflow_snapshot,
            lifecycle=product_lifecycle,
        )
        attention_summary = self.creator_attention_service.build_attention_summary(
            workflow_snapshot=workflow_snapshot,
            lifecycle=product_lifecycle,
            review_status=review_status,
            publishing_status=publishing_status,
            chat_registration_records=self._safe_chat_attention_records(),
        )
        return WorkspaceWorkflowItem(
            product_id=workflow_snapshot.product_id,
            product_name=str(
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or "Untitled Product"
            ),
            workflow_snapshot=workflow_snapshot,
            product_lifecycle=product_lifecycle,
            review_status=review_status,
            publishing_status=publishing_status,
            attention_summary=attention_summary,
            compatibility=bool(
                self._attribute(product, "legacy_content_item_id", None)
            ),
        )

    def _safe_chat_attention_records(self) -> tuple[Any, ...]:
        try:
            if self._chat_commerce_inventory_service is None:
                self._chat_commerce_inventory_service = ChatCommerceInventoryService(
                    asset_library_service=self.asset_library_service,
                )
            return self._chat_commerce_inventory_service.attention_chat_records(limit=50)
        except Exception:
            return ()

    def _build_product_card(self, display: Any) -> WorkspaceProductCard:
        product = self._attribute(display, "product")
        experience = self._attribute(display, "experience_presentation")
        publishing = self._attribute(display, "publishing")
        review = self._safe_product_review_for_display(display)
        metadata = dict(self._attribute(product, "metadata", {}) or {})
        commerce = dict(metadata.get("commerce_intelligence") or {})
        price = self._format_price(
            self._attribute(product, "price_cents"),
            self._attribute(product, "currency", "USD"),
        )
        suggested_price = self._format_price(
            self._nested_value(
                commerce,
                "price",
                "suggested_price_cents",
            )
            or self._attribute(product, "base_price_cents"),
            self._attribute(product, "currency", "USD"),
        )
        delivery_type = self._value(self._attribute(product, "delivery_type"))
        fulfillment_status = self._value(
            self._attribute(product, "fulfillment_status")
        )
        status = self._value(self._attribute(product, "status"))
        provider_status = str(
            self._attribute(publishing, "status", "Unknown") or "Unknown"
        )
        experience_relationship = self._product_experience_relationship_label(
            experience
        )
        commerce_override_count = 0
        if review is not None:
            commerce_override_count = len(
                self._attribute(
                    self._attribute(review, "commerce_overrides", None),
                    "data",
                    {},
                ).get("overridden_fields", ())
            )
        return WorkspaceProductCard(
            product_id=str(self._attribute(product, "id", "")),
            name=str(
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or "Untitled Product"
            ),
            product_type=self._value(self._attribute(product, "product_type"))
            or "Unknown",
            delivery_type=delivery_type or "Unknown",
            product_origin=(
                self._attribute(review, "product_origin", None)
                if review is not None
                else "Product"
            )
            or "Product",
            experience_name=self._attribute(experience, "title"),
            experience_type=self._attribute(experience, "experience_type"),
            status=status or "Unknown",
            review_status=self._product_review_status(product, display),
            approval_status=(
                self._attribute(review, "approval_status", None)
                if review is not None
                else "NEEDS_REVIEW"
            )
            or "NEEDS_REVIEW",
            commerce_override_count=commerce_override_count,
            has_commerce_overrides=commerce_override_count > 0,
            ready_to_publish=(
                self._attribute(review, "review_status", None) == "Ready To Publish"
                if review is not None
                else False
            ),
            publishing_readiness=fulfillment_status or "Unknown",
            provider_status=provider_status,
            telegram_delivery_status=self._telegram_delivery_status(product),
            price=price,
            suggested_price=suggested_price,
            asset_count=len(self._attribute(display, "ordered_assets", ()) or ()),
            experience_relationship=experience_relationship,
            publishing_relationship=provider_status,
            compatibility=bool(
                self._attribute(experience, "compatibility", False)
                or self._attribute(product, "legacy_content_item_id", None)
            ),
        )

    def _safe_product_review_for_display(self, display: Any):
        try:
            return self.product_review_service.build_review_from_display(display)
        except Exception:
            return None

    def _product_display_models(
        self,
        *,
        creator_profile_id: int,
        limit: int,
    ) -> tuple[Any, ...]:
        return tuple(
            self.product_catalog_service.list_workspace_display_models(
                creator_profile_id=creator_profile_id,
                include_archived=True,
                limit=limit,
            )
        )

    def _product_summary_items(
        self,
        *,
        creator_profile_id: int,
        limit: int,
    ) -> tuple[Any, ...]:
        list_displays = getattr(
            self.product_catalog_service,
            "list_workspace_display_models",
            None,
        )
        if callable(list_displays):
            return tuple(
                list_displays(
                    creator_profile_id=creator_profile_id,
                    include_archived=True,
                    limit=limit,
                )
            )
        list_products = getattr(
            self.product_catalog_service,
            "list_workspace_products",
            None,
        )
        if callable(list_products):
            return tuple(
                list_products(
                    creator_profile_id=creator_profile_id,
                    include_archived=True,
                    limit=limit,
                )
            )
        return tuple(
            self._attribute(display, "product")
            for display in self._product_display_models(
                creator_profile_id=creator_profile_id,
                limit=limit,
            )
        )

    def _product_status_counts(
        self,
        creator_profile_id: int,
    ) -> dict[str, int]:
        count_products = getattr(
            self.product_catalog_service,
            "count_workspace_products",
            None,
        )
        if callable(count_products):
            return count_products(creator_profile_id)
        return self.product_repository.count_by_status(creator_profile_id)

    @staticmethod
    def _format_price(value: Any, currency: str | None) -> str:
        if value is None:
            return "-"
        try:
            amount = int(value) / 100
        except (TypeError, ValueError):
            return str(value)
        return f"{currency or 'USD'} {amount:,.2f}"

    @staticmethod
    def _nested_value(data: dict, *keys: str) -> Any | None:
        current: Any = data
        for key in keys:
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    def _product_review_status(self, product: Any, display: Any) -> str:
        status = self._value(self._attribute(product, "status"))
        fulfillment = self._value(self._attribute(product, "fulfillment_status"))
        asset_count = len(self._attribute(display, "ordered_assets", ()) or ())
        if not asset_count:
            return "Needs Assets"
        if not self._attribute(display, "experience_presentation"):
            return "Needs Experience"
        if status == "DRAFT":
            return "Draft"
        if fulfillment == "READY":
            return "Ready"
        return "Review"

    def _telegram_delivery_status(self, product: Any) -> str:
        delivery_type = self._value(self._attribute(product, "delivery_type"))
        if not delivery_type:
            return "Delivery type unavailable"
        return f"{delivery_type} delivery intent"

    def _product_experience_relationship_label(self, experience: Any) -> str:
        if not experience:
            return "Missing"
        source = str(
            self._attribute(experience, "relationship_source", "")
            or "ExperienceService"
        )
        if self._attribute(experience, "compatibility", False):
            return f"{source} (compatibility)"
        return source

    def _safe_publishing_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspacePublishingCard, ...]:
        try:
            return self._publishing_cards(creator_profile_id)
        except Exception:
            return ()

    def _publishing_cards(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspacePublishingCard, ...]:
        if not creator_profile_id:
            return ()
        displays = self._product_display_models(
            creator_profile_id=creator_profile_id,
            limit=8,
        )
        return tuple(self._build_publishing_card(display) for display in displays)

    def _build_publishing_card(self, display: Any) -> WorkspacePublishingCard:
        product = self._attribute(display, "product")
        experience = self._attribute(display, "experience_presentation")
        publishing = self._attribute(display, "publishing")
        product_record = self.publishing_service.project_legacy_product_record(
            product
        )
        provider_error = self._attribute(product_record, "provider_error")
        provider_status = str(
            self._attribute(publishing, "status", "Unknown") or "Unknown"
        )
        fulfillment_status = self._value(
            self._attribute(product, "fulfillment_status")
        )
        status = self._value(self._attribute(product, "status"))
        missing = self._publishing_missing_requirements(
            product,
            display,
            provider_status,
        )
        ready = fulfillment_status == "READY" and not missing
        published_active = (
            status == "ACTIVE"
            and (
                "Uploaded" in provider_status
                or "URL available" in provider_status
            )
        )
        return WorkspacePublishingCard(
            product_id=str(self._attribute(product, "id", "")),
            product_name=str(
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or "Untitled Product"
            ),
            experience_name=self._attribute(experience, "title"),
            product_type=self._value(self._attribute(product, "product_type"))
            or "Unknown",
            delivery_type=self._value(self._attribute(product, "delivery_type"))
            or "Unknown",
            publishing_status=provider_status,
            publishing_readiness=fulfillment_status or "Unknown",
            provider="Fanvue",
            provider_status=provider_status,
            provider_error=str(provider_error) if provider_error else None,
            media_link_status=(
                "Available"
                if self._attribute(product, "media_link")
                else "Missing"
            ),
            telegram_delivery_intent=self._telegram_delivery_status(product),
            missing_requirements=missing,
            ready_to_publish=ready,
            published_active=published_active,
            compatibility=bool(
                self._attribute(experience, "compatibility", False)
                or self._attribute(product, "legacy_content_item_id", None)
            ),
        )

    def _publishing_missing_requirements(
        self,
        product: Any,
        display: Any,
        provider_status: str,
    ) -> tuple[str, ...]:
        missing: list[str] = []
        if not (self._attribute(display, "ordered_assets", ()) or ()):
            missing.append("Assets")
        if self._attribute(display, "experience_presentation") is None:
            missing.append("Experience")
        if (
            self._value(self._attribute(product, "delivery_type")) == "PAID"
            and self._attribute(product, "price_cents") is None
        ):
            missing.append("Price")
        if not self._attribute(product, "media_link"):
            missing.append("Media Link")
        if "Failed" in provider_status:
            missing.append("Provider Status")
        return tuple(missing)

    def _insights(
        self,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceInsight, ...]:
        assets = summaries["Assets"]
        experiences = summaries["Experiences"]
        products = summaries["Products"]
        publishing = summaries["Publishing"]
        customers = summaries["Customer Conversations"]
        activity = summaries["Activity"]
        notifications = summaries["Notifications"]

        insights = (
            self._asset_growth_insight(assets),
            self._import_trend_insight(assets),
            self._experience_growth_insight(experiences),
            self._product_growth_insight(products),
            self._dashboard_readiness_insight(products, publishing),
            self._customer_growth_insight(customers),
            self._publishing_health_insight(publishing),
            self._publishing_trend_insight(publishing),
            self._workspace_health_insight(notifications),
            self._activity_operations_insight(activity),
            self._customer_engagement_placeholder(customers),
            self._recommendation_trend_placeholder(),
        )
        return insights

    def _asset_growth_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        total = self._metric_value(summary, "Total Assets")
        recent = self._metric_value(summary, "Recently Imported")
        return WorkspaceInsight(
            insight_type="asset_growth",
            category="Assets",
            title="Asset library size",
            current_value=total,
            trend="Current",
            delta="Historical baseline unavailable",
            detail=f"{recent} asset(s) imported in the recent window.",
            future_ready=True,
        )

    def _import_trend_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        processing = self._metric_value(summary, "Assets Processing")
        needs_classification = self._metric_value(summary, "Needs Classification")
        return WorkspaceInsight(
            insight_type="import_trend",
            category="Assets",
            title="Import readiness",
            current_value=f"{processing} processing",
            trend="Monitoring",
            delta="Trend history unavailable",
            detail=f"{needs_classification} asset(s) still need classification.",
            future_ready=True,
        )

    def _experience_growth_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        total = self._metric_value(summary, "Total Experiences")
        collections = self._metric_value(summary, "Collections")
        return WorkspaceInsight(
            insight_type="experience_growth",
            category="Experiences",
            title="Experience coverage",
            current_value=total,
            trend="Current",
            delta="Historical baseline unavailable",
            detail=f"{collections} collection-style experience(s) are available.",
            future_ready=True,
        )

    def _product_growth_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        active = self._metric_value(summary, "Active Products")
        draft = self._metric_value(summary, "Draft Products")
        ready = self._metric_value(summary, "Ready for Publishing")
        return WorkspaceInsight(
            insight_type="product_growth",
            category="Products",
            title="Product catalog health",
            current_value=f"{active} active",
            trend="Current",
            delta="Historical baseline unavailable",
            detail=f"{draft} draft product(s), {ready} ready for publishing.",
            future_ready=True,
        )

    def _dashboard_readiness_insight(
        self,
        products: WorkspaceSummary,
        publishing: WorkspaceSummary,
    ) -> WorkspaceInsight:
        ready = self._metric_value(publishing, "Ready To Publish")
        review = self._metric_value(products, "Products Needing Review")
        attention = self._metric_value(publishing, "Needs Attention")
        return WorkspaceInsight(
            insight_type="dashboard_readiness",
            category="Dashboard",
            title="Operational readiness",
            current_value=f"{ready} ready",
            trend="Needs Attention" if attention != "0" else "Ready",
            delta="Current summary state",
            detail=(
                f"{review} Product(s) need review; "
                f"{attention} publishing item(s) need attention."
            ),
            future_ready=False,
        )

    def _customer_growth_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        known = self._metric_value(summary, "Known Customers")
        subscribers = self._metric_value(summary, "Subscribers")
        return WorkspaceInsight(
            insight_type="customer_growth",
            category="Customers",
            title="Customer base",
            current_value=known,
            trend="Current",
            delta="Historical baseline unavailable",
            detail=f"{subscribers} subscriber(s) are currently known.",
            future_ready=True,
        )

    def _publishing_health_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        health = self._metric_value(summary, "Publishing Health")
        failures = self._metric_value(summary, "Failed Uploads")
        trend = "Healthy" if health == "OK" else "Needs Attention"
        return WorkspaceInsight(
            insight_type="publishing_health",
            category="Publishing",
            title="Publishing health",
            current_value=health,
            trend=trend,
            delta="Current queue state",
            detail=f"{failures} failed publishing item(s) are currently reported.",
            future_ready=False,
        )

    def _publishing_trend_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        pending = self._metric_value(summary, "Pending Uploads")
        completed = self._metric_value(summary, "Recently Published")
        return WorkspaceInsight(
            insight_type="publishing_trend",
            category="Publishing",
            title="Publishing throughput",
            current_value=f"{completed} completed",
            trend="Monitoring",
            delta="Trend history unavailable",
            detail=f"{pending} publishing item(s) are pending.",
            future_ready=True,
        )

    def _workspace_health_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        attention = self._metric_value(summary, "Attention Items")
        trend = "Stable" if attention == "0" else "Needs Attention"
        return WorkspaceInsight(
            insight_type="workspace_health",
            category="Workspace Health",
            title="Workspace health",
            current_value=f"{attention} attention item(s)",
            trend=trend,
            delta="Current summary state",
            detail="Workspace health is derived from current notification rollups.",
            future_ready=False,
        )

    def _activity_operations_insight(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        pending = self._metric_value(summary, "Delayed Pending")
        failed = self._metric_value(summary, "Delayed Failed")
        return WorkspaceInsight(
            insight_type="operations_trend",
            category="Activity",
            title="Operational followups",
            current_value=f"{pending} pending",
            trend="Monitoring",
            delta="Trend history unavailable",
            detail=f"{failed} delayed followup(s) failed.",
            future_ready=True,
        )

    def _customer_engagement_placeholder(
        self,
        summary: WorkspaceSummary,
    ) -> WorkspaceInsight:
        active = self._metric_value(summary, "Active Conversations")
        return WorkspaceInsight(
            insight_type="customer_engagement",
            category="Customers",
            title="Customer engagement",
            current_value=active,
            trend="Future",
            delta="Unavailable",
            detail="Conversation engagement trend source is not yet exposed.",
            future_ready=True,
        )

    @staticmethod
    def _recommendation_trend_placeholder() -> WorkspaceInsight:
        return WorkspaceInsight(
            insight_type="recommendation_trend",
            category="Recommendations",
            title="Recommendation trends",
            current_value="Coming Soon",
            trend="Future",
            delta="Unavailable",
            detail="Recommendation trend source is not yet exposed.",
            future_ready=True,
        )

    def _activity_feed(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
        summaries: dict[str, WorkspaceSummary],
    ) -> tuple[WorkspaceActivityEvent, ...]:
        creator_profile_id = (creator_profile or {}).get("id")
        account_id = (active_account or {}).get("id")
        events: list[WorkspaceActivityEvent] = []

        events.extend(self._asset_activity_events())
        events.extend(self._experience_activity_events(creator_profile_id))
        events.extend(self._product_activity_events(creator_profile_id))
        events.extend(self._publishing_activity_events(summaries["Publishing"]))
        events.extend(self._customer_activity_events(summaries["Customer Conversations"]))
        events.extend(self._delayed_message_activity_events(summaries["Activity"]))
        events.extend(self._decision_engine_activity_events())
        events.extend(
            self._system_activity_events(
                creator_profile=creator_profile,
                active_account=active_account,
                account_id=account_id,
            )
        )

        return self._sort_activity_events(events)

    def _asset_activity_events(self) -> tuple[WorkspaceActivityEvent, ...]:
        assets = self._asset_library_items(limit=25)
        events: list[WorkspaceActivityEvent] = []
        for asset in assets[:25]:
            asset_id = (
                self._attribute(asset, "asset_id")
                or self._attribute(asset, "id", "unknown")
            )
            status = str(self._attribute(asset, "status") or "unknown")
            file_name = (
                self._attribute(asset, "file_name")
                or f"Asset {asset_id}"
            )
            events.append(
                WorkspaceActivityEvent(
                    event_type="asset_import",
                    title=f"Asset imported: {file_name}",
                    detail=f"Asset {asset_id} is {status}.",
                    source="AssetLibraryService",
                    timestamp=self._attribute(asset, "created_at"),
                )
            )
            if status.lower() in {"importing", "processing"}:
                events.append(
                    WorkspaceActivityEvent(
                        event_type="asset_processing",
                        title=f"Asset processing: {file_name}",
                        detail=f"Asset {asset_id} is still in {status}.",
                        source="AssetLibraryService",
                        timestamp=self._attribute(asset, "created_at"),
                    )
                )
        return tuple(events)

    def _experience_activity_events(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        if not creator_profile_id:
            return (
                WorkspaceActivityEvent(
                    event_type="experience",
                    title="Experience activity unavailable",
                    detail="Creator profile is required for Experience activity.",
                    source="ExperienceService",
                    future_ready=True,
                ),
            )
        experiences = self.experience_service.list_experiences(
            creator_profile_id=creator_profile_id,
            include_archived=True,
            limit=25,
        )
        events = []
        for experience in experiences:
            title = self._attribute(experience, "title") or "Untitled experience"
            asset_count = len(self._attribute(experience, "asset_ids", ()) or ())
            events.append(
                WorkspaceActivityEvent(
                    event_type="experience_created",
                    title=f"Experience available: {title}",
                    detail=f"{asset_count} asset(s) organized in this experience.",
                    source="ExperienceService",
                    timestamp=(
                        self._attribute(experience, "created_at")
                        or self._attribute(experience, "updated_at")
                    ),
                )
            )
        return tuple(events)

    def _product_activity_events(
        self,
        creator_profile_id: int | None,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        if not creator_profile_id:
            return (
                WorkspaceActivityEvent(
                    event_type="product",
                    title="Product activity unavailable",
                    detail="Creator profile is required for Product activity.",
                    source="ProductRepository",
                    future_ready=True,
                ),
            )
        displays = self._product_display_models(
            creator_profile_id=creator_profile_id,
            limit=25,
        )
        events = []
        for display in displays:
            product = self._attribute(display, "product")
            name = (
                self._attribute(product, "display_name")
                or self._attribute(product, "internal_name")
                or "Untitled product"
            )
            status = self._value(self._attribute(product, "status")) or "unknown"
            fulfillment_status = self._value(
                self._attribute(product, "fulfillment_status")
            )
            created_at = self._attribute(product, "created_at")
            updated_at = self._attribute(product, "updated_at") or created_at
            events.append(
                WorkspaceActivityEvent(
                    event_type="product_created",
                    title=f"Product tracked: {name}",
                    detail=f"Product status is {status}.",
                    source="ProductCatalogService",
                    timestamp=created_at,
                )
            )
            if fulfillment_status == ProductFulfillmentStatus.READY.value:
                events.append(
                    WorkspaceActivityEvent(
                        event_type="product_publishing",
                        title=f"Product ready for publishing: {name}",
                        detail="Fulfillment status is READY.",
                        source="ProductCatalogService",
                        timestamp=updated_at,
                    )
                )
        return tuple(events)

    def _publishing_activity_events(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        pending = self._metric_value_as_int(summary, "Pending Uploads")
        failed = self._metric_value_as_int(summary, "Failed Uploads")
        health = next(
            (
                metric.value
                for metric in summary.metrics
                if metric.label == "Publishing Health"
            ),
            "Unavailable",
        )
        return (
            WorkspaceActivityEvent(
                event_type="publishing",
                title="Publishing queue summary",
                detail=(
                    f"{self._format_count(pending)} pending upload(s), "
                    f"{self._format_count(failed)} failed upload(s)."
                ),
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
            WorkspaceActivityEvent(
                event_type="publishing",
                title="Publishing health",
                detail=f"Current publishing health is {health}.",
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
        )

    def _customer_activity_events(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        known = self._metric_value_as_int(summary, "Known Customers")
        subscribers = self._metric_value_as_int(summary, "Subscribers")
        return (
            WorkspaceActivityEvent(
                event_type="customer",
                title="Customer activity summary",
                detail=(
                    f"{self._format_count(known)} known customer(s), "
                    f"{self._format_count(subscribers)} subscriber(s)."
                ),
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
        )

    def _delayed_message_activity_events(
        self,
        summary: WorkspaceSummary,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        pending = self._metric_value_as_int(summary, "Delayed Pending")
        failed = self._metric_value_as_int(summary, "Delayed Failed")
        return (
            WorkspaceActivityEvent(
                event_type="delayed_message",
                title="Delayed message queue summary",
                detail=(
                    f"{self._format_count(pending)} pending followup(s), "
                    f"{self._format_count(failed)} failed followup(s)."
                ),
                source="CreatorWorkspaceService",
                future_ready=True,
            ),
        )

    def _decision_engine_activity_events(self) -> tuple[WorkspaceActivityEvent, ...]:
        return (
            WorkspaceActivityEvent(
                event_type="decision_engine",
                title="DecisionEngine activity summary",
                detail="DecisionEngine event stream is not yet exposed to Creator Workspace.",
                source="DecisionEngine",
                future_ready=True,
            ),
        )

    def _system_activity_events(
        self,
        *,
        creator_profile: dict | None,
        active_account: dict | None,
        account_id: int | None,
    ) -> tuple[WorkspaceActivityEvent, ...]:
        profile_name = (
            (creator_profile or {}).get("display_name")
            or (creator_profile or {}).get("persona_name")
            or "Creator profile"
        )
        account_name = (
            (active_account or {}).get("display_name")
            or (active_account or {}).get("account_name")
            or (active_account or {}).get("username")
            or "No provider account"
        )
        return (
            WorkspaceActivityEvent(
                event_type="system",
                title="Creator profile loaded" if creator_profile else "Creator profile missing",
                detail=profile_name if creator_profile else "Administration setup is incomplete.",
                source="CreatorWorkspaceService",
                future_ready=not bool(creator_profile),
            ),
            WorkspaceActivityEvent(
                event_type="system",
                title="Provider account selected" if account_id else "Provider account missing",
                detail=account_name,
                source="CreatorWorkspaceService",
                future_ready=not bool(account_id),
            ),
        )

    @staticmethod
    def _sort_activity_events(
        events: list[WorkspaceActivityEvent],
    ) -> tuple[WorkspaceActivityEvent, ...]:
        def sort_key(event: WorkspaceActivityEvent) -> tuple[int, datetime]:
            timestamp = event.timestamp
            if timestamp is None:
                return (0, datetime.min.replace(tzinfo=timezone.utc))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            return (1, timestamp)

        return tuple(sorted(events, key=sort_key, reverse=True))

    def _asset_summary(self) -> WorkspaceAssetsSummary:
        return workspace_summaries.build_asset_summary(
            self._asset_library_items(limit=5000)
        )

    def _asset_library_items(self, *, limit: int) -> tuple[Any, ...]:
        try:
            result = self.asset_library_service.search_assets(
                AssetLibraryFilter(
                    eligible_only=False,
                    limit=limit,
                )
            )
            return tuple(result.items)
        except Exception:
            return tuple(self.asset_repository.list_all()[:limit])

    def _experience_summary(
        self,
        creator_profile_id: int | None,
    ) -> WorkspaceExperiencesSummary:
        if not creator_profile_id:
            return workspace_summaries.build_missing_experience_summary()
        experiences = self.experience_service.list_experiences(
            creator_profile_id=creator_profile_id,
            include_archived=True,
            limit=500,
        )
        return workspace_summaries.build_experience_summary(experiences)

    def _product_summary(
        self,
        creator_profile_id: int | None,
    ) -> WorkspaceProductsSummary:
        if not creator_profile_id:
            return workspace_summaries.build_missing_product_summary()
        counts = self._product_status_counts(creator_profile_id)
        products = self._product_summary_items(
            creator_profile_id=creator_profile_id,
            limit=500,
        )
        return workspace_summaries.build_product_summary(counts, products)

    def _publishing_summary(
        self,
        account_id: int | None,
        creator_profile_id: int | None = None,
    ) -> WorkspacePublishingSummary:
        if not account_id:
            return workspace_summaries.build_missing_publishing_summary()
        wall_counts = self.wall_counts_fetcher(fanvue_account_id=account_id)
        pending_mass = self.pending_mass_ppv_fetcher()
        failed_mass = self.failed_mass_ppv_fetcher()
        products = (
            self._product_summary_items(
                creator_profile_id=creator_profile_id,
                limit=500,
            )
            if creator_profile_id
            else ()
        )
        try:
            publishing_queue_items = self.publishing_service.list_publishing_queue_items(
                limit=500,
            )
        except Exception:
            publishing_queue_items = ()
        return workspace_summaries.build_publishing_summary(
            wall_counts=wall_counts,
            pending_mass=pending_mass,
            failed_mass=failed_mass,
            products=products,
            publishing_queue_items=publishing_queue_items,
        )

    def _conversation_summary(
        self,
        account_id: int | None,
    ) -> WorkspaceConversationSummary:
        if not account_id:
            return workspace_summaries.build_missing_conversation_summary()
        stats = self.relationship_stats_fetcher(account_id) or {}
        return workspace_summaries.build_conversation_summary(stats)

    def _activity_summary(
        self,
        account_id: int | None,
    ) -> WorkspaceActivitySummary:
        if not account_id:
            return workspace_summaries.build_missing_activity_summary()
        delayed = build_delayed_message_dashboard_summary(
            self.delayed_counts_fetcher(fanvue_account_id=account_id)
        )
        return workspace_summaries.build_activity_summary(delayed)

    def _notification_summary(
        self,
        creator_profile: dict | None,
        active_account: dict | None,
        publishing: WorkspaceSummary,
        activity: WorkspaceSummary,
    ) -> WorkspaceNotificationSummary:
        return workspace_summaries.build_notification_summary(
            creator_profile=creator_profile,
            active_account=active_account,
            publishing=publishing,
            activity=activity,
        )


def build_workspace_summaries(
    *,
    creator_profile: dict | None = None,
    active_account: dict | None = None,
    **service_kwargs,
) -> dict[str, WorkspaceSummary]:
    return CreatorWorkspaceService(**service_kwargs).build_dashboard(
        creator_profile=creator_profile,
        active_account=active_account,
    ).summaries

"""Product Business read-model aggregation service.

ProductBusinessService assembles existing Creator OS domain outputs into one
provider-neutral ProductBusinessSnapshot. It is intentionally read-only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.business_learning import (
    BusinessLearningSnapshot,
    LearningContext,
    PerformanceMetric,
    PerformanceSnapshot,
)
from app.models.customer_intelligence import CustomerIntelligenceSnapshot
from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessHealth,
    ProductBusinessRecommendation,
    ProductBusinessSnapshot,
)
from app.models.product_lifecycle import ProductLifecycle, ProductLifecycleStage
from app.models.publishing_automation import (
    PublishingAutomationState,
    PublishingAutomationStatus,
)

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.product_catalog_service import ProductCatalogService
    from app.services.product_lifecycle_service import ProductLifecycleService
    from app.services.publishing_automation_service import PublishingAutomationService


class ProductBusinessService:
    """Build Product Business snapshots without mutating domain state."""

    def __init__(
        self,
        *,
        product_catalog_service: "ProductCatalogService | None" = None,
        product_lifecycle_service: "ProductLifecycleService | None" = None,
        publishing_automation_service: "PublishingAutomationService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
    ) -> None:
        self._product_catalog = product_catalog_service
        self._product_lifecycle = product_lifecycle_service
        self._publishing_automation = publishing_automation_service
        self._customer_intelligence = customer_intelligence_service
        self._business_learning = business_learning_service

    @property
    def product_catalog(self) -> "ProductCatalogService":
        if self._product_catalog is None:
            from app.services.product_catalog_service import ProductCatalogService

            self._product_catalog = ProductCatalogService()
        return self._product_catalog

    @property
    def product_lifecycle(self) -> "ProductLifecycleService":
        if self._product_lifecycle is None:
            from app.services.product_lifecycle_service import ProductLifecycleService

            self._product_lifecycle = ProductLifecycleService()
        return self._product_lifecycle

    @property
    def publishing_automation(self) -> "PublishingAutomationService":
        if self._publishing_automation is None:
            from app.services.publishing_automation_service import (
                PublishingAutomationService,
            )

            self._publishing_automation = PublishingAutomationService(
                product_lifecycle_service=self.product_lifecycle,
            )
        return self._publishing_automation

    @property
    def customer_intelligence(self) -> "CustomerIntelligenceService":
        if self._customer_intelligence is None:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceService,
            )

            self._customer_intelligence = CustomerIntelligenceService()
        return self._customer_intelligence

    @property
    def business_learning(self) -> "BusinessLearningService":
        if self._business_learning is None:
            from app.services.business_learning_service import BusinessLearningService

            self._business_learning = BusinessLearningService()
        return self._business_learning

    def build_snapshot(
        self,
        *,
        product: Any | None = None,
        product_display: Any | None = None,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        workflow_snapshot: Any | None = None,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        customer_snapshot: CustomerIntelligenceSnapshot | Mapping[str, Any] | None = None,
        customer_snapshots: Iterable[
            CustomerIntelligenceSnapshot | Mapping[str, Any]
        ]
        | None = None,
        customer_context: Mapping[str, Any] | None = None,
        learning_context: LearningContext | Mapping[str, Any] | None = None,
        learning_snapshot: BusinessLearningSnapshot | Mapping[str, Any] | None = None,
        performance_snapshot: PerformanceSnapshot | Mapping[str, Any] | None = None,
        business_outcomes: Any | None = None,
        product_strategy_result: Any | None = None,
        commerce_strategy_result: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductBusinessSnapshot:
        product_obj = product or self._read(product_display, "product")
        resolved_lifecycle = self._resolve_lifecycle(lifecycle, workflow_snapshot)
        resolved_publishing = self._resolve_publishing_status(
            publishing_status,
            lifecycle=resolved_lifecycle,
            workflow_snapshot=workflow_snapshot,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
        )
        product_id = (
            self._safe_text(self._read(product_obj, "id"))
            or self._safe_text(self._read(product_display, "product_id"))
            or self._safe_text(self._read(resolved_lifecycle, "product_id"))
            or self._safe_text(self._read(resolved_publishing, "product_id"))
        )
        product_status = (
            self._enum_value(self._read(product_obj, "status"))
            or self._safe_text(self._read(resolved_lifecycle, "product_status"))
        )
        availability = self.determine_availability(
            product_status=product_status,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
        )
        publishing_readiness = self.summarize_publishing_readiness(
            resolved_publishing,
            lifecycle=resolved_lifecycle,
        )
        customer_reach = self.summarize_customer_reach(
            customer_snapshot=customer_snapshot,
            customer_snapshots=customer_snapshots,
            customer_context=customer_context,
            product_id=product_id,
        )
        performance_summary = self.summarize_performance(
            learning_context=learning_context,
            learning_snapshot=learning_snapshot,
            performance_snapshot=performance_snapshot,
            business_outcomes=business_outcomes,
            product_id=product_id,
        )
        health = self.determine_product_health(
            availability=availability,
            publishing_readiness=publishing_readiness,
            performance_summary=performance_summary,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
        )
        recommendation = self.recommend_next_business_action(
            health=health,
            availability=availability,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
            performance_summary=performance_summary,
        )
        return ProductBusinessSnapshot(
            product_id=product_id,
            product_name=(
                self._safe_text(self._read(product_obj, "display_name"))
                or self._safe_text(self._read(product_obj, "internal_name"))
            ),
            product_type=self._enum_value(self._read(product_obj, "product_type")),
            delivery_type=self._enum_value(self._read(product_obj, "delivery_type")),
            product_status=product_status,
            lifecycle=resolved_lifecycle,
            publishing_status=resolved_publishing,
            publishing_readiness=publishing_readiness,
            availability=availability,
            customer_reach=customer_reach,
            performance_summary=performance_summary,
            product_health=health,
            next_business_recommendation=recommendation,
            strategy_summary=self.summarize_product_strategy(product_strategy_result),
            commerce_summary=self.summarize_commerce_strategy(commerce_strategy_result),
            compatibility={
                "source": "product_business",
                "owner": "ProductBusinessService",
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "creates_products": False,
                "modifies_products": False,
                "generates_product_strategy": False,
                "generates_commerce_strategy": False,
                "publishes_products": False,
                "executes_telegram": False,
                "records_business_learning": False,
                "product_catalog_consumed": product_obj is not None,
                "product_lifecycle_consumed": resolved_lifecycle is not None,
                "publishing_consumed": resolved_publishing is not None,
                "customer_intelligence_consumed": bool(
                    customer_snapshot or customer_snapshots or customer_context
                ),
                "business_learning_consumed": bool(
                    learning_context
                    or learning_snapshot
                    or performance_snapshot
                    or business_outcomes
                ),
            },
            metadata=dict(metadata or {}),
        )

    def build_for_product_id(self, product_id: Any, **context: Any) -> ProductBusinessSnapshot:
        product = self.product_catalog.products.get_by_id(product_id)
        display = (
            self.product_catalog.load_display_model(product) if product is not None else None
        )
        return self.build_snapshot(product_display=display, **context)

    def determine_availability(
        self,
        *,
        product_status: str | None,
        lifecycle: ProductLifecycle | None = None,
        publishing_status: PublishingAutomationStatus | None = None,
    ) -> ProductBusinessAvailability:
        lifecycle_stage = self._read(lifecycle, "stage")
        publishing_state = self._read(publishing_status, "state")
        if publishing_state == PublishingAutomationState.READY_FOR_TELEGRAM:
            return ProductBusinessAvailability.TELEGRAM_READY
        if lifecycle_stage == ProductLifecycleStage.TELEGRAM_READY:
            return ProductBusinessAvailability.TELEGRAM_READY
        if self._text(product_status) == "ACTIVE":
            return ProductBusinessAvailability.AVAILABLE
        if lifecycle_stage == ProductLifecycleStage.ACTIVE:
            return ProductBusinessAvailability.AVAILABLE
        if publishing_state in {
            PublishingAutomationState.WAITING_FOR_MEDIA_LINK,
            PublishingAutomationState.VERIFY_MEDIA_LINK,
        }:
            return ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK
        if lifecycle_stage == ProductLifecycleStage.WAITING_FOR_MEDIA_LINK:
            return ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK
        if publishing_state in {
            PublishingAutomationState.QUEUED,
            PublishingAutomationState.UPLOAD_IN_PROGRESS,
            PublishingAutomationState.READY_TO_PUBLISH,
        }:
            return ProductBusinessAvailability.PUBLISHING
        if lifecycle_stage in {
            ProductLifecycleStage.APPROVED,
            ProductLifecycleStage.PUBLISHING_READY,
            ProductLifecycleStage.PUBLISHING,
        }:
            return ProductBusinessAvailability.PUBLISHING
        if self._text(product_status) in {"DRAFT", None}:
            return ProductBusinessAvailability.DRAFT
        if self._text(product_status) in {"DISABLED", "ARCHIVED"}:
            return ProductBusinessAvailability.UNAVAILABLE
        return ProductBusinessAvailability.UNKNOWN

    def determine_product_health(
        self,
        *,
        availability: ProductBusinessAvailability,
        publishing_readiness: Mapping[str, Any],
        performance_summary: Mapping[str, Any],
        lifecycle: ProductLifecycle | None = None,
        publishing_status: PublishingAutomationStatus | None = None,
    ) -> ProductBusinessHealth:
        if self._bool(self._read(publishing_status, "attention_required")):
            return ProductBusinessHealth.NEEDS_ATTENTION
        if publishing_readiness.get("attention_required"):
            return ProductBusinessHealth.NEEDS_ATTENTION
        if performance_summary.get("underperforming"):
            return ProductBusinessHealth.UNDERPERFORMING
        if (
            availability == ProductBusinessAvailability.TELEGRAM_READY
            and self._float(performance_summary.get("success_rate")) >= 0.5
            and self._int(performance_summary.get("outcome_count")) > 0
        ):
            return ProductBusinessHealth.HEALTHY
        if availability in {
            ProductBusinessAvailability.AVAILABLE,
            ProductBusinessAvailability.TELEGRAM_READY,
        }:
            return ProductBusinessHealth.ACTIVE
        if availability == ProductBusinessAvailability.PUBLISHING:
            return ProductBusinessHealth.READY
        if availability == ProductBusinessAvailability.DRAFT:
            return ProductBusinessHealth.DRAFT
        return ProductBusinessHealth.UNKNOWN

    def recommend_next_business_action(
        self,
        *,
        health: ProductBusinessHealth,
        availability: ProductBusinessAvailability,
        lifecycle: ProductLifecycle | None = None,
        publishing_status: PublishingAutomationStatus | None = None,
        performance_summary: Mapping[str, Any] | None = None,
    ) -> ProductBusinessRecommendation:
        if health == ProductBusinessHealth.NEEDS_ATTENTION:
            return ProductBusinessRecommendation(
                label="Review Product Business Issue",
                reason="Publishing or Product Business status requires attention.",
            )
        if availability == ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK:
            return ProductBusinessRecommendation(
                label="Paste Media Link",
                reason="Publishing is waiting for manual media link completion.",
            )
        if publishing_status is not None and self._read(
            publishing_status, "next_recommended_action"
        ):
            return ProductBusinessRecommendation(
                label=str(self._read(publishing_status, "next_recommended_action")),
                reason=self._safe_text(
                    self._read(self._read(publishing_status, "recommendation"), "reason")
                ),
            )
        if lifecycle is not None and self._read(lifecycle, "next_recommended_action"):
            return ProductBusinessRecommendation(
                label=str(self._read(lifecycle, "next_recommended_action")),
                reason=self._safe_text(
                    self._read(self._read(lifecycle, "recommendation"), "reason")
                ),
            )
        if health == ProductBusinessHealth.UNDERPERFORMING:
            return ProductBusinessRecommendation(
                label="Review Product Performance",
                reason="Business Learning evidence indicates weak performance.",
            )
        return ProductBusinessRecommendation(
            label="No Product Business Action",
            reason="No actionable Product Business issue was found.",
        )

    def summarize_publishing_readiness(
        self,
        publishing_status: PublishingAutomationStatus | None,
        *,
        lifecycle: ProductLifecycle | None = None,
    ) -> Mapping[str, Any]:
        return {
            "state": self._enum_value(self._read(publishing_status, "state")),
            "publishing_status": self._safe_text(
                self._read(publishing_status, "publishing_status")
                or self._read(lifecycle, "publishing_status")
            ),
            "media_link_status": self._safe_text(
                self._read(publishing_status, "media_link_status")
                or self._read(lifecycle, "media_link_status")
            ),
            "manual_media_link_required": self._bool(
                self._read(publishing_status, "manual_media_link_required")
            ),
            "attention_required": self._bool(
                self._read(publishing_status, "attention_required")
            ),
            "telegram_ready": self._bool(
                self._read(publishing_status, "telegram_ready")
                or self._read(lifecycle, "telegram_ready")
            ),
        }

    def summarize_customer_reach(
        self,
        *,
        customer_snapshot: CustomerIntelligenceSnapshot | Mapping[str, Any] | None,
        customer_snapshots: Iterable[
            CustomerIntelligenceSnapshot | Mapping[str, Any]
        ]
        | None,
        customer_context: Mapping[str, Any] | None,
        product_id: str | None,
    ) -> Mapping[str, Any]:
        snapshots: list[CustomerIntelligenceSnapshot | Mapping[str, Any]] = []
        if customer_snapshot is not None:
            snapshots.append(customer_snapshot)
        snapshots.extend(tuple(customer_snapshots or ()))
        if customer_context:
            snapshots.append(
                self.customer_intelligence.build_customer_snapshot(**dict(customer_context))
            )
        offered = purchased = delivered = 0
        for snapshot in snapshots:
            memory = self._read(snapshot, "commerce_memory")
            offered += int(product_id in self._text_tuple(self._read(memory, "products_offered")))
            purchased += int(
                product_id in self._text_tuple(self._read(memory, "products_purchased"))
            )
            delivered += int(
                product_id
                in (
                    self._text_tuple(self._read(memory, "delivered_free_products"))
                    + self._text_tuple(self._read(memory, "delivered_paid_products"))
                    + self._text_tuple(self._read(memory, "paid_products_delivered"))
                )
            )
        return {
            "customer_count": len(snapshots),
            "offered_count": offered,
            "purchased_count": purchased,
            "delivered_count": delivered,
            "has_customer_reach": bool(offered or purchased or delivered),
        }

    def summarize_performance(
        self,
        *,
        learning_context: LearningContext | Mapping[str, Any] | None,
        learning_snapshot: BusinessLearningSnapshot | Mapping[str, Any] | None,
        performance_snapshot: PerformanceSnapshot | Mapping[str, Any] | None,
        business_outcomes: Any | None,
        product_id: str | None,
    ) -> Mapping[str, Any]:
        context = learning_context
        snapshot = learning_snapshot
        performance = performance_snapshot
        if context is None and snapshot is None and performance is None and business_outcomes:
            context = self.business_learning.build_product_learning_context(
                outcomes=business_outcomes,
                product_reference=product_id,
            )
        performance = (
            performance
            or self._read(context, "performance_snapshot")
            or self._read(snapshot, "performance_snapshot")
        )
        metrics = tuple(self._read(performance, "metrics") or ())
        metric = self._select_product_metric(metrics) if metrics else None
        success_rate = self._float(
            self._read(metric, "success_rate")
            or self._read(self._read(snapshot, "performance_summary"), "success_rate")
        )
        outcome_count = self._int(
            self._read(metric, "count")
            or self._read(self._read(snapshot, "performance_summary"), "total_outcomes")
        )
        confidence = self._float(self._read(metric, "confidence"))
        return {
            "metric_type": self._safe_text(self._read(metric, "metric_type")),
            "outcome_count": outcome_count,
            "success_count": self._int(self._read(metric, "success_count")),
            "failure_count": self._int(self._read(metric, "failure_count")),
            "success_rate": success_rate,
            "confidence": confidence,
            "underperforming": bool(outcome_count >= 3 and success_rate < 0.25),
            "has_performance_history": bool(outcome_count),
        }

    def summarize_product_strategy(self, product_strategy_result: Any | None) -> Mapping[str, Any]:
        recommendations = tuple(self._read(product_strategy_result, "recommendations") or ())
        return {
            "recommendation_count": len(recommendations),
            "confidence": self._float(self._read(product_strategy_result, "confidence")),
            "source": self._safe_text(self._read(product_strategy_result, "source")),
            "consumed": product_strategy_result is not None,
        }

    def summarize_commerce_strategy(self, commerce_strategy_result: Any | None) -> Mapping[str, Any]:
        recommendations = tuple(self._read(commerce_strategy_result, "recommendations") or ())
        return {
            "recommendation_count": len(recommendations),
            "confidence": self._float(self._read(commerce_strategy_result, "confidence")),
            "source": self._safe_text(self._read(commerce_strategy_result, "source")),
            "consumed": commerce_strategy_result is not None,
        }

    def _resolve_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None,
        workflow_snapshot: Any | None,
    ) -> ProductLifecycle | None:
        if isinstance(lifecycle, ProductLifecycle):
            return lifecycle
        if lifecycle is not None:
            return self.product_lifecycle.build_lifecycle(lifecycle)
        if workflow_snapshot is not None:
            return self.product_lifecycle.build_lifecycle(workflow_snapshot)
        return None

    def _resolve_publishing_status(
        self,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None,
        *,
        lifecycle: ProductLifecycle | None,
        workflow_snapshot: Any | None,
        publishing_projection: Any | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
    ) -> PublishingAutomationStatus | None:
        if isinstance(publishing_status, PublishingAutomationStatus):
            return publishing_status
        if publishing_status is not None:
            return self.publishing_automation.build_status(
                lifecycle=lifecycle,
                publishing_projection=publishing_status,
            )
        if any(
            item is not None
            for item in (
                lifecycle,
                workflow_snapshot,
                publishing_projection,
                publishing_job,
                publishing_queue_item,
            )
        ):
            return self.publishing_automation.build_status(
                lifecycle=lifecycle,
                workflow_snapshot=workflow_snapshot,
                publishing_projection=publishing_projection,
                publishing_job=publishing_job,
                publishing_queue_item=publishing_queue_item,
            )
        return None

    @staticmethod
    def _select_product_metric(metrics: Iterable[Any]) -> Any | None:
        candidates = tuple(metrics)
        for metric in candidates:
            if ProductBusinessService._safe_text(
                ProductBusinessService._read(metric, "metric_type")
            ) == "product_performance":
                return metric
        for metric in candidates:
            if isinstance(metric, PerformanceMetric):
                return metric
        return candidates[0] if candidates else None

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _enum_value(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value)).strip().upper()

    @staticmethod
    def _text_tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        try:
            return tuple(str(getattr(item, "value", item)) for item in value)
        except TypeError:
            return (str(value),)

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _bool(value: Any) -> bool:
        return bool(value)

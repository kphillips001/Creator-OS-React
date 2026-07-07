"""Product Performance aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.business_learning import (
    BusinessLearningSnapshot,
    BusinessOutcome,
    BusinessOutcomeType,
    LearningContext,
    PerformanceMetric,
    PerformanceSnapshot,
)
from app.models.customer_intelligence import CustomerIntelligenceSnapshot
from app.models.product_business import ProductBusinessSnapshot
from app.models.product_performance import (
    ProductPerformance,
    ProductPerformanceRecommendation,
    ProductPerformanceStatus,
    ProductPerformanceSummary,
)

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.product_business_service import ProductBusinessService
    from app.services.product_catalog_service import ProductCatalogService


class ProductPerformanceService:
    """Build Product-level performance guidance without mutating state."""

    def __init__(
        self,
        *,
        business_learning_service: "BusinessLearningService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        product_business_service: "ProductBusinessService | None" = None,
        product_catalog_service: "ProductCatalogService | None" = None,
    ) -> None:
        self._business_learning = business_learning_service
        self._customer_intelligence = customer_intelligence_service
        self._product_business = product_business_service
        self._product_catalog = product_catalog_service

    @property
    def business_learning(self) -> "BusinessLearningService":
        if self._business_learning is None:
            from app.services.business_learning_service import BusinessLearningService

            self._business_learning = BusinessLearningService()
        return self._business_learning

    @property
    def customer_intelligence(self) -> "CustomerIntelligenceService":
        if self._customer_intelligence is None:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceService,
            )

            self._customer_intelligence = CustomerIntelligenceService()
        return self._customer_intelligence

    @property
    def product_business(self) -> "ProductBusinessService":
        if self._product_business is None:
            from app.services.product_business_service import ProductBusinessService

            self._product_business = ProductBusinessService()
        return self._product_business

    @property
    def product_catalog(self) -> "ProductCatalogService":
        if self._product_catalog is None:
            from app.services.product_catalog_service import ProductCatalogService

            self._product_catalog = ProductCatalogService()
        return self._product_catalog

    def build_performance(
        self,
        *,
        product: Any | None = None,
        product_business_snapshot: ProductBusinessSnapshot | Mapping[str, Any] | None = None,
        learning_context: LearningContext | Mapping[str, Any] | None = None,
        learning_snapshot: BusinessLearningSnapshot | Mapping[str, Any] | None = None,
        performance_snapshot: PerformanceSnapshot | Mapping[str, Any] | None = None,
        business_outcomes: Any | None = None,
        customer_snapshot: CustomerIntelligenceSnapshot | Mapping[str, Any] | None = None,
        customer_snapshots: Iterable[
            CustomerIntelligenceSnapshot | Mapping[str, Any]
        ]
        | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductPerformance:
        product_business = self._resolve_product_business(
            product_business_snapshot,
            product=product,
        )
        product_id = (
            self._safe_text(self._read(product, "id"))
            or self._safe_text(self._read(product_business, "product_id"))
            or self._safe_text(self._read(learning_context, "subject_reference"))
        )
        context = self._resolve_learning_context(
            learning_context=learning_context,
            learning_snapshot=learning_snapshot,
            performance_snapshot=performance_snapshot,
            business_outcomes=business_outcomes,
            product_id=product_id,
        )
        performance = (
            performance_snapshot
            or self._read(context, "performance_snapshot")
            or self._read(learning_snapshot, "performance_snapshot")
        )
        metrics = self._metrics(performance)
        outcomes = self._normalized_outcomes(business_outcomes)
        customer_reach = self._customer_reach(
            product_business=product_business,
            customer_snapshot=customer_snapshot,
            customer_snapshots=customer_snapshots,
            product_id=product_id,
        )
        summary = self.build_summary(
            metrics=metrics,
            outcomes=outcomes,
            customer_reach=customer_reach,
            product_business_snapshot=product_business,
            metadata=metadata,
        )
        status = self.determine_status(summary=summary, metrics=metrics)
        recommendation = self.recommend_next_action(status, summary=summary)
        return ProductPerformance(
            product_id=product_id,
            status=status,
            summary=summary,
            recommendation=recommendation,
            product_business_snapshot=product_business,
            performance_metrics=metrics,
            evidence={
                "metric_types": tuple(metric.metric_type for metric in metrics),
                "business_outcome_count": len(outcomes),
                "business_learning_owner": "BusinessLearningService",
                "customer_reach": customer_reach,
            },
            compatibility={
                "source": "product_performance",
                "owner": "ProductPerformanceService",
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "records_business_learning": False,
                "modifies_products": False,
                "publishes_products": False,
                "executes_telegram": False,
                "generates_product_strategy": False,
                "business_learning_owner_preserved": True,
                "product_catalog_owner_preserved": True,
                "business_learning_consumed": bool(
                    context or learning_snapshot or performance_snapshot or business_outcomes
                ),
                "customer_intelligence_consumed": bool(
                    customer_snapshot or customer_snapshots
                ),
                "product_business_consumed": product_business is not None,
            },
        )

    def build_for_product_id(self, product_id: Any, **context: Any) -> ProductPerformance:
        product = self.product_catalog.products.get_by_id(product_id)
        return self.build_performance(product=product, **context)

    def build_summary(
        self,
        *,
        metrics: tuple[PerformanceMetric, ...],
        outcomes: tuple[BusinessOutcome, ...],
        customer_reach: Mapping[str, Any],
        product_business_snapshot: ProductBusinessSnapshot | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductPerformanceSummary:
        product_metric = self._metric_summary(metrics, "product_performance")
        offer_metric = self._metric_summary(metrics, "offer_effectiveness")
        delivery_metric = self._metric_summary(metrics, "delivery_effectiveness")
        bundle_metric = self._metric_summary(metrics, "bundle_performance")
        story_metric = self._metric_summary(metrics, "story_performance")
        photoshoot_metric = self._metric_summary(metrics, "photoshoot_performance")
        engagement_metric = self._metric_summary(metrics, "customer_engagement")
        conversion_rate = self._conversion_rate(outcomes, offer_metric, product_metric)
        trend = self._trend(product_metric)
        overall_health = self._overall_health(
            product_metric=product_metric,
            conversion_rate=conversion_rate,
            customer_reach=customer_reach,
            product_business_snapshot=product_business_snapshot,
        )
        return ProductPerformanceSummary(
            sales_performance=product_metric,
            free_conversion_performance=delivery_metric,
            bundle_performance=bundle_metric,
            story_performance=story_metric,
            photoshoot_performance=photoshoot_metric,
            customer_engagement=engagement_metric,
            conversion_rate=conversion_rate,
            customer_reach=dict(customer_reach),
            trend=trend,
            overall_health=overall_health,
            metadata={
                **dict(metadata or {}),
                "offer_effectiveness": offer_metric,
                "business_learning_owner": "BusinessLearningService",
            },
        )

    @staticmethod
    def determine_status(
        *,
        summary: ProductPerformanceSummary,
        metrics: tuple[PerformanceMetric, ...],
    ) -> ProductPerformanceStatus:
        observations = sum(metric.count for metric in metrics)
        sales = summary.sales_performance
        success_rate = ProductPerformanceService._float(sales.get("success_rate"))
        confidence = ProductPerformanceService._float(sales.get("confidence"))
        if observations == 0:
            return ProductPerformanceStatus.NO_DATA
        if summary.overall_health == "needs_review":
            return ProductPerformanceStatus.NEEDS_REVIEW
        if sales.get("count", 0) >= 3 and success_rate < 0.25:
            return ProductPerformanceStatus.UNDERPERFORMING
        if confidence < 0.3:
            return ProductPerformanceStatus.MONITOR
        if success_rate >= 0.6 and confidence >= 0.3:
            return ProductPerformanceStatus.STRONG_PERFORMER
        return ProductPerformanceStatus.AVERAGE_PERFORMER

    @staticmethod
    def recommend_next_action(
        status: ProductPerformanceStatus,
        *,
        summary: ProductPerformanceSummary,
    ) -> ProductPerformanceRecommendation:
        mapping = {
            ProductPerformanceStatus.STRONG_PERFORMER: (
                "Strong Performer",
                "Performance evidence shows strong conversion or sales outcomes.",
            ),
            ProductPerformanceStatus.AVERAGE_PERFORMER: (
                "Average Performer",
                "Performance is acceptable but not clearly exceptional.",
            ),
            ProductPerformanceStatus.UNDERPERFORMING: (
                "Underperforming",
                "Business Learning evidence shows weak conversion or sales outcomes.",
            ),
            ProductPerformanceStatus.NEEDS_REVIEW: (
                "Needs Review",
                "Product Business health indicates the Product should be reviewed.",
            ),
            ProductPerformanceStatus.MONITOR: (
                "Monitor",
                "Performance evidence is limited and should be monitored.",
            ),
            ProductPerformanceStatus.NO_DATA: (
                "Monitor",
                "No Product Performance evidence is available yet.",
            ),
        }
        label, reason = mapping[status]
        return ProductPerformanceRecommendation(
            label=label,
            reason=reason,
            metadata={
                "conversion_rate": summary.conversion_rate,
                "trend": summary.trend,
                "overall_health": summary.overall_health,
            },
        )

    def _resolve_product_business(
        self,
        value: ProductBusinessSnapshot | Mapping[str, Any] | None,
        *,
        product: Any | None,
    ) -> ProductBusinessSnapshot | None:
        if isinstance(value, ProductBusinessSnapshot):
            return value
        if isinstance(value, Mapping):
            return ProductBusinessSnapshot(
                product_id=self._safe_text(value.get("product_id") or value.get("id")),
                product_name=self._safe_text(value.get("product_name")),
                product_status=self._safe_text(value.get("product_status")),
                customer_reach=value.get("customer_reach") or {},
                performance_summary=value.get("performance_summary") or {},
                product_health=value.get("product_health"),
                metadata=value.get("metadata") or {},
            )
        if product is not None:
            return self.product_business.build_snapshot(product=product)
        return None

    def _resolve_learning_context(
        self,
        *,
        learning_context: LearningContext | Mapping[str, Any] | None,
        learning_snapshot: BusinessLearningSnapshot | Mapping[str, Any] | None,
        performance_snapshot: PerformanceSnapshot | Mapping[str, Any] | None,
        business_outcomes: Any | None,
        product_id: str | None,
    ) -> LearningContext | Mapping[str, Any] | None:
        if learning_context is not None:
            return learning_context
        if performance_snapshot is not None:
            return {"performance_snapshot": performance_snapshot}
        if learning_snapshot is not None:
            return {"performance_snapshot": self._read(learning_snapshot, "performance_snapshot")}
        if business_outcomes:
            return self.business_learning.build_product_learning_context(
                outcomes=business_outcomes,
                product_reference=product_id,
            )
        return None

    def _customer_reach(
        self,
        *,
        product_business: ProductBusinessSnapshot | None,
        customer_snapshot: CustomerIntelligenceSnapshot | Mapping[str, Any] | None,
        customer_snapshots: Iterable[CustomerIntelligenceSnapshot | Mapping[str, Any]]
        | None,
        product_id: str | None,
    ) -> Mapping[str, Any]:
        explicit_snapshots = bool(customer_snapshot or customer_snapshots)
        if (
            not explicit_snapshots
            and product_business is not None
            and product_business.customer_reach
        ):
            return dict(product_business.customer_reach)
        snapshots = []
        if customer_snapshot is not None:
            snapshots.append(customer_snapshot)
        snapshots.extend(tuple(customer_snapshots or ()))
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

    @staticmethod
    def _metrics(value: Any) -> tuple[PerformanceMetric, ...]:
        metrics = tuple(ProductPerformanceService._read(value, "metrics") or ())
        return tuple(metric for metric in metrics if isinstance(metric, PerformanceMetric))

    def _normalized_outcomes(self, outcomes: Any | None) -> tuple[BusinessOutcome, ...]:
        if not outcomes:
            return ()
        return self.business_learning.normalize_business_outcomes(outcomes)

    @staticmethod
    def _metric_summary(
        metrics: tuple[PerformanceMetric, ...],
        metric_type: str,
    ) -> Mapping[str, Any]:
        metric = next((item for item in metrics if item.metric_type == metric_type), None)
        if metric is None:
            return {
                "metric_type": metric_type,
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "neutral_count": 0,
                "success_rate": 0.0,
                "confidence": 0.0,
            }
        return {
            "metric_type": metric.metric_type,
            "count": metric.count,
            "success_count": metric.success_count,
            "failure_count": metric.failure_count,
            "neutral_count": metric.neutral_count,
            "success_rate": metric.success_rate,
            "confidence": metric.confidence,
        }

    @staticmethod
    def _conversion_rate(
        outcomes: tuple[BusinessOutcome, ...],
        offer_metric: Mapping[str, Any],
        product_metric: Mapping[str, Any],
    ) -> float:
        offered = sum(
            1
            for outcome in outcomes
            if outcome.outcome_type == BusinessOutcomeType.PRODUCT_OFFERED.value
        )
        purchased = sum(
            1
            for outcome in outcomes
            if outcome.outcome_type == BusinessOutcomeType.PRODUCT_PURCHASED.value
        )
        if offered:
            return purchased / offered
        if offer_metric.get("count"):
            return ProductPerformanceService._float(offer_metric.get("success_rate"))
        return ProductPerformanceService._float(product_metric.get("success_rate"))

    @staticmethod
    def _trend(product_metric: Mapping[str, Any]) -> str:
        count = ProductPerformanceService._int(product_metric.get("count"))
        success_rate = ProductPerformanceService._float(product_metric.get("success_rate"))
        if count == 0:
            return "unknown"
        if success_rate >= 0.6:
            return "strong"
        if success_rate < 0.25 and count >= 3:
            return "declining"
        return "stable"

    @staticmethod
    def _overall_health(
        *,
        product_metric: Mapping[str, Any],
        conversion_rate: float,
        customer_reach: Mapping[str, Any],
        product_business_snapshot: ProductBusinessSnapshot | None,
    ) -> str:
        product_health = ProductPerformanceService._safe_text(
            ProductPerformanceService._read(product_business_snapshot, "product_health")
        )
        if product_health in {"NEEDS_ATTENTION", "UNDERPERFORMING"}:
            return "needs_review" if product_health == "NEEDS_ATTENTION" else "weak"
        if ProductPerformanceService._int(product_metric.get("count")) == 0:
            return "unknown"
        if conversion_rate >= 0.5 and customer_reach.get("has_customer_reach"):
            return "strong"
        if conversion_rate < 0.25 and ProductPerformanceService._int(
            product_metric.get("count")
        ) >= 3:
            return "weak"
        return "average"

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

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

"""Product Improvement advisory service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.models.product_availability import ProductAvailability, ProductAvailabilityStatus
from app.models.product_business import ProductBusinessHealth, ProductBusinessSnapshot
from app.models.product_catalog_management import (
    ProductCatalogHealth,
    ProductCatalogRecommendationType,
)
from app.models.product_composition import (
    ProductCompositionRecommendation,
    ProductCompositionType,
)
from app.models.product_improvement import (
    ProductImprovement,
    ProductImprovementPriority,
    ProductImprovementRecommendation,
    ProductImprovementType,
)
from app.models.product_performance import ProductPerformance, ProductPerformanceStatus


class ProductImprovementService:
    """Generate advisory Product Improvement recommendations only."""

    def build_improvement(
        self,
        *,
        product_business_snapshot: ProductBusinessSnapshot | Mapping[str, Any] | None = None,
        availability: ProductAvailability | Mapping[str, Any] | None = None,
        performance: ProductPerformance | Mapping[str, Any] | None = None,
        catalog_health: ProductCatalogHealth | Mapping[str, Any] | None = None,
        composition_recommendations: Iterable[
            ProductCompositionRecommendation | Mapping[str, Any]
        ]
        | None = None,
        business_learning_context: Any | None = None,
        customer_intelligence_context: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductImprovement:
        business = self._business(product_business_snapshot)
        availability_model = self._availability(availability)
        performance_model = self._performance(performance)
        catalog = self._catalog_health(catalog_health)
        compositions = tuple(
            self._composition(item) for item in tuple(composition_recommendations or ())
        )
        product_id = (
            self._safe_text(self._read(business, "product_id"))
            or self._safe_text(self._read(availability_model, "product_id"))
            or self._safe_text(self._read(performance_model, "product_id"))
        )
        recommendations: list[ProductImprovementRecommendation] = []
        recommendations.extend(
            self._availability_recommendations(availability_model, product_id)
        )
        recommendations.extend(self._performance_recommendations(performance_model, product_id))
        recommendations.extend(self._catalog_recommendations(catalog, product_id))
        recommendations.extend(self._composition_recommendations(compositions, product_id))
        recommendations.extend(self._business_recommendations(business, product_id))
        if not recommendations:
            recommendations.append(
                self._recommendation(
                    ProductImprovementType.MONITOR_PRODUCT,
                    ProductImprovementPriority.LOW,
                    "Monitor Product",
                    "Monitor Product",
                    product_id=product_id,
                    confidence=0.4,
                    rationale=("No immediate Product Improvement issue was detected.",),
                    evidence={"source": "default_monitor"},
                )
            )
        ordered = tuple(
            sorted(
                self._dedupe(recommendations),
                key=lambda item: (
                    self._priority_rank(item.priority),
                    -item.confidence,
                    item.label,
                ),
            )
        )
        return ProductImprovement(
            product_id=product_id,
            recommendations=ordered,
            summary={
                "recommendation_count": len(ordered),
                "highest_priority": ordered[0].priority.value if ordered else None,
                "types": tuple(item.improvement_type.value for item in ordered),
                "business_learning_context_consumed": business_learning_context is not None,
                "customer_intelligence_context_consumed": (
                    customer_intelligence_context is not None
                ),
            },
            compatibility={
                "source": "product_improvement",
                "owner": "ProductImprovementService",
                "read_only": True,
                "provider_neutral": True,
                "advisory_only": True,
                "modifies_products": False,
                "creates_products": False,
                "archives_products": False,
                "publishes_products": False,
                "executes_telegram": False,
                "generates_product_strategy": False,
                "records_business_learning": False,
                "product_ownership_preserved": True,
                "product_catalog_ownership_preserved": True,
                "product_strategy_ownership_preserved": True,
                "publishing_ownership_preserved": True,
                "business_learning_ownership_preserved": True,
            },
            metadata=dict(metadata or {}),
        )

    def _availability_recommendations(
        self,
        availability: ProductAvailability | None,
        product_id: str | None,
    ) -> tuple[ProductImprovementRecommendation, ...]:
        if availability is None:
            return ()
        status = availability.status
        if status in {
            ProductAvailabilityStatus.NEEDS_ATTENTION,
            ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK,
            ProductAvailabilityStatus.PUBLISHING,
            ProductAvailabilityStatus.UNAVAILABLE,
        }:
            return (
                self._recommendation(
                    ProductImprovementType.FIX_AVAILABILITY,
                    (
                        ProductImprovementPriority.CRITICAL
                        if status == ProductAvailabilityStatus.NEEDS_ATTENTION
                        else ProductImprovementPriority.HIGH
                    ),
                    "Fix Availability",
                    self._availability_next_action(availability),
                    product_id=product_id,
                    confidence=0.85,
                    rationale=(
                        f"Product availability is {status.value}.",
                        "Availability must be resolved before reliable selling.",
                    ),
                    evidence={
                        "availability_status": status.value,
                        "media_link_status": availability.media_link_status,
                    },
                ),
            )
        if status == ProductAvailabilityStatus.ARCHIVED:
            return (
                self._recommendation(
                    ProductImprovementType.RETIRE_PRODUCT,
                    ProductImprovementPriority.LOW,
                    "Retire Product",
                    "Keep Product Retired",
                    product_id=product_id,
                    confidence=0.65,
                    rationale=("Product is archived and unavailable.",),
                    evidence={"availability_status": status.value},
                ),
            )
        return ()

    @staticmethod
    def _availability_next_action(availability: ProductAvailability) -> str:
        if availability.status == ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK:
            return "Paste Media Link"
        if availability.status == ProductAvailabilityStatus.NEEDS_ATTENTION:
            return "Resolve Publishing"
        if availability.status == ProductAvailabilityStatus.PUBLISHING:
            return "Publish Product"
        if availability.status == ProductAvailabilityStatus.UNAVAILABLE:
            return "Review Availability"
        return availability.next_recommended_action

    def _performance_recommendations(
        self,
        performance: ProductPerformance | None,
        product_id: str | None,
    ) -> tuple[ProductImprovementRecommendation, ...]:
        if performance is None:
            return ()
        status = performance.status
        if status == ProductPerformanceStatus.STRONG_PERFORMER:
            return (
                self._recommendation(
                    ProductImprovementType.PROMOTE_STRONG_PERFORMER,
                    ProductImprovementPriority.NORMAL,
                    "Promote Strong Performer",
                    "Promote Product",
                    product_id=product_id,
                    confidence=0.8,
                    rationale=("Product Performance indicates strong outcomes.",),
                    evidence={
                        "performance_status": status.value,
                        "conversion_rate": performance.summary.conversion_rate,
                    },
                ),
            )
        if status == ProductPerformanceStatus.UNDERPERFORMING:
            return (
                self._recommendation(
                    ProductImprovementType.REFRESH_PRODUCT,
                    ProductImprovementPriority.HIGH,
                    "Refresh Product",
                    "Review and Refresh Product",
                    product_id=product_id,
                    confidence=0.78,
                    rationale=("Product is underperforming against Business Learning evidence.",),
                    evidence={
                        "performance_status": status.value,
                        "sales_performance": performance.summary.sales_performance,
                    },
                ),
                self._recommendation(
                    ProductImprovementType.RETIRE_PRODUCT,
                    ProductImprovementPriority.NORMAL,
                    "Consider Product Retirement",
                    "Evaluate Product Retirement",
                    product_id=product_id,
                    confidence=0.55,
                    rationale=("Sustained underperformance may justify retirement.",),
                    evidence={"performance_status": status.value},
                ),
            )
        if status in {ProductPerformanceStatus.MONITOR, ProductPerformanceStatus.NO_DATA}:
            return (
                self._recommendation(
                    ProductImprovementType.MONITOR_PRODUCT,
                    ProductImprovementPriority.LOW,
                    "Monitor Product",
                    "Monitor Product",
                    product_id=product_id,
                    confidence=0.45,
                    rationale=("Performance evidence is limited.",),
                    evidence={"performance_status": status.value},
                ),
            )
        if status == ProductPerformanceStatus.NEEDS_REVIEW:
            return (
                self._recommendation(
                    ProductImprovementType.REFRESH_PRODUCT,
                    ProductImprovementPriority.HIGH,
                    "Refresh Product",
                    "Review Product",
                    product_id=product_id,
                    confidence=0.72,
                    rationale=("Product Performance indicates review is needed.",),
                    evidence={"performance_status": status.value},
                ),
            )
        return ()

    def _catalog_recommendations(
        self,
        catalog: ProductCatalogHealth | None,
        product_id: str | None,
    ) -> tuple[ProductImprovementRecommendation, ...]:
        if catalog is None:
            return ()
        items = []
        for recommendation in catalog.recommendations:
            recommendation_type = recommendation.recommendation_type
            mapping = {
                ProductCatalogRecommendationType.CREATE_FREE_PREVIEW: (
                    ProductImprovementType.CREATE_FREE_PREVIEW,
                    "Create FREE Preview",
                    "Create FREE Preview",
                ),
                ProductCatalogRecommendationType.CREATE_BUNDLE: (
                    ProductImprovementType.CREATE_BUNDLE,
                    "Create Bundle",
                    "Create Bundle",
                ),
                ProductCatalogRecommendationType.CREATE_PREMIUM_PRODUCT: (
                    ProductImprovementType.CREATE_PRODUCT,
                    "Create Product",
                    "Create Premium Product",
                ),
                ProductCatalogRecommendationType.REMOVE_DUPLICATE: (
                    ProductImprovementType.CONSOLIDATE_DUPLICATES,
                    "Consolidate Duplicate Products",
                    "Review Duplicate Products",
                ),
            }
            if recommendation_type not in mapping:
                continue
            improvement_type, label, action = mapping[recommendation_type]
            items.append(
                self._recommendation(
                    improvement_type,
                    (
                        ProductImprovementPriority.HIGH
                        if improvement_type
                        in {
                            ProductImprovementType.CREATE_FREE_PREVIEW,
                            ProductImprovementType.CREATE_PRODUCT,
                        }
                        else ProductImprovementPriority.NORMAL
                    ),
                    label,
                    action,
                    product_id=product_id,
                    confidence=0.7,
                    rationale=tuple(filter(None, (recommendation.reason,))),
                    evidence={
                        "catalog_recommendation_type": recommendation_type.value,
                        "catalog_product_ids": recommendation.product_ids,
                    },
                )
            )
        return tuple(items)

    def _composition_recommendations(
        self,
        compositions: tuple[ProductCompositionRecommendation, ...],
        product_id: str | None,
    ) -> tuple[ProductImprovementRecommendation, ...]:
        items = []
        for recommendation in compositions:
            composition_type = recommendation.composition_type
            if composition_type == ProductCompositionType.FREE_PREVIEW:
                improvement_type = ProductImprovementType.IMPROVE_FREE_PREVIEW
                label = "Improve FREE Preview"
                action = "Review FREE Preview Composition"
            elif composition_type in {
                ProductCompositionType.BUNDLE,
                ProductCompositionType.STORY_PRODUCT,
                ProductCompositionType.PHOTOSHOOT_PRODUCT,
                ProductCompositionType.COLLECTION,
            }:
                improvement_type = ProductImprovementType.IMPROVE_COMPOSITION
                label = "Improve Product Composition"
                action = "Review Product Composition"
            else:
                continue
            items.append(
                self._recommendation(
                    improvement_type,
                    ProductImprovementPriority.NORMAL,
                    label,
                    action,
                    product_id=product_id,
                    confidence=recommendation.confidence or 0.55,
                    rationale=recommendation.rationale
                    or (f"Composition recommendation: {recommendation.label}.",),
                    evidence={
                        "composition_type": composition_type.value,
                        "included_asset_ids": recommendation.composition.included_asset_ids,
                        "cover_asset_id": recommendation.composition.cover_asset_id,
                    },
                )
            )
        return tuple(items)

    def _business_recommendations(
        self,
        business: ProductBusinessSnapshot | None,
        product_id: str | None,
    ) -> tuple[ProductImprovementRecommendation, ...]:
        if business is None:
            return ()
        if business.product_health == ProductBusinessHealth.UNDERPERFORMING:
            return (
                self._recommendation(
                    ProductImprovementType.REFRESH_PRODUCT,
                    ProductImprovementPriority.HIGH,
                    "Refresh Product",
                    "Review Product Business Health",
                    product_id=product_id,
                    confidence=0.7,
                    rationale=("Product Business marks this Product as underperforming.",),
                    evidence={"product_health": business.product_health.value},
                ),
            )
        if business.product_health == ProductBusinessHealth.HEALTHY:
            return (
                self._recommendation(
                    ProductImprovementType.PROMOTE_STRONG_PERFORMER,
                    ProductImprovementPriority.LOW,
                    "Promote Strong Performer",
                    "Consider Promotion",
                    product_id=product_id,
                    confidence=0.6,
                    rationale=("Product Business marks this Product as healthy.",),
                    evidence={"product_health": business.product_health.value},
                ),
            )
        return ()

    @staticmethod
    def _recommendation(
        improvement_type: ProductImprovementType,
        priority: ProductImprovementPriority,
        label: str,
        next_action: str,
        *,
        product_id: str | None,
        confidence: float,
        rationale: tuple[str, ...],
        evidence: Mapping[str, Any],
    ) -> ProductImprovementRecommendation:
        return ProductImprovementRecommendation(
            improvement_type=improvement_type,
            priority=priority,
            label=label,
            recommended_next_action=next_action,
            product_id=product_id,
            confidence=confidence,
            rationale=rationale,
            supporting_evidence=dict(evidence),
        )

    @staticmethod
    def _dedupe(
        recommendations: list[ProductImprovementRecommendation],
    ) -> tuple[ProductImprovementRecommendation, ...]:
        seen = set()
        deduped = []
        for recommendation in recommendations:
            key = (recommendation.improvement_type, recommendation.product_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(recommendation)
        return tuple(deduped)

    @staticmethod
    def _priority_rank(priority: ProductImprovementPriority) -> int:
        return {
            ProductImprovementPriority.CRITICAL: 0,
            ProductImprovementPriority.HIGH: 1,
            ProductImprovementPriority.NORMAL: 2,
            ProductImprovementPriority.LOW: 3,
        }[priority]

    @staticmethod
    def _business(value: ProductBusinessSnapshot | Mapping[str, Any] | None) -> ProductBusinessSnapshot | None:
        if isinstance(value, ProductBusinessSnapshot):
            return value
        if isinstance(value, Mapping):
            health = value.get("product_health")
            if not isinstance(health, ProductBusinessHealth):
                try:
                    health = ProductBusinessHealth(str(health))
                except (TypeError, ValueError):
                    health = ProductBusinessHealth.UNKNOWN
            return ProductBusinessSnapshot(
                product_id=ProductImprovementService._safe_text(
                    value.get("product_id") or value.get("id")
                ),
                product_health=health,
                metadata=value.get("metadata") or {},
            )
        return None

    @staticmethod
    def _availability(value: ProductAvailability | Mapping[str, Any] | None) -> ProductAvailability | None:
        if isinstance(value, ProductAvailability):
            return value
        if isinstance(value, Mapping):
            status = value.get("status")
            if not isinstance(status, ProductAvailabilityStatus):
                try:
                    status = ProductAvailabilityStatus(str(status))
                except (TypeError, ValueError):
                    status = ProductAvailabilityStatus.UNAVAILABLE
            return ProductAvailability(
                product_id=ProductImprovementService._safe_text(value.get("product_id")),
                status=status,
                media_link_status=ProductImprovementService._safe_text(
                    value.get("media_link_status")
                ),
            )
        return None

    @staticmethod
    def _performance(value: ProductPerformance | Mapping[str, Any] | None) -> ProductPerformance | None:
        if isinstance(value, ProductPerformance):
            return value
        if isinstance(value, Mapping):
            status = value.get("status")
            if not isinstance(status, ProductPerformanceStatus):
                try:
                    status = ProductPerformanceStatus(str(status))
                except (TypeError, ValueError):
                    status = ProductPerformanceStatus.NO_DATA
            return ProductPerformance(
                product_id=ProductImprovementService._safe_text(value.get("product_id")),
                status=status,
            )
        return None

    @staticmethod
    def _catalog_health(value: ProductCatalogHealth | Mapping[str, Any] | None) -> ProductCatalogHealth | None:
        if isinstance(value, ProductCatalogHealth):
            return value
        return None

    @staticmethod
    def _composition(
        value: ProductCompositionRecommendation | Mapping[str, Any],
    ) -> ProductCompositionRecommendation:
        if isinstance(value, ProductCompositionRecommendation):
            return value
        from app.models.product_composition import ProductComposition

        composition_type = value.get("composition_type")
        if not isinstance(composition_type, ProductCompositionType):
            composition_type = ProductCompositionType(str(composition_type))
        return ProductCompositionRecommendation(
            composition=ProductComposition(
                composition_type=composition_type,
                included_asset_ids=tuple(value.get("included_asset_ids") or ()),
                cover_asset_id=value.get("cover_asset_id"),
            ),
            label=str(value.get("label") or composition_type.value),
            confidence=float(value.get("confidence") or 0.0),
            rationale=tuple(value.get("rationale") or ()),
        )

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

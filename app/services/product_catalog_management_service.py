"""Product Catalog Management advisory service.

This service evaluates the Product Catalog as a living portfolio using existing
Product Business and Product Strategy read models. It does not create, modify,
publish, execute, or generate Product Strategy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessHealth,
    ProductBusinessSnapshot,
)
from app.models.product_catalog_management import (
    ProductCatalogHealth,
    ProductCatalogHealthStatus,
    ProductCatalogRecommendation,
    ProductCatalogRecommendationType,
)

if TYPE_CHECKING:
    from app.services.product_business_service import ProductBusinessService
    from app.services.product_catalog_service import ProductCatalogService


PHOTOSHOOT_TYPES = {"PHOTO_SET", "VIDEO_SET", "SESSION"}
COLLECTION_RECOMMENDATION_TYPES = {"collection", "vip_collection"}


class ProductCatalogManagementService:
    """Generate advisory Product Catalog health and recommendations."""

    def __init__(
        self,
        *,
        product_business_service: "ProductBusinessService | None" = None,
        product_catalog_service: "ProductCatalogService | None" = None,
    ) -> None:
        self._product_business = product_business_service
        self._product_catalog = product_catalog_service

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

    def build_catalog_health(
        self,
        *,
        products: Iterable[Any] | None = None,
        product_business_snapshots: Iterable[
            ProductBusinessSnapshot | Mapping[str, Any]
        ]
        | None = None,
        product_strategy_result: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ProductCatalogHealth:
        snapshots = self._normalize_snapshots(
            products=products,
            product_business_snapshots=product_business_snapshots,
        )
        duplicate_groups = self.detect_duplicate_products(snapshots)
        incomplete_ids = self.detect_incomplete_products(snapshots)
        gaps = self.detect_portfolio_gaps(
            snapshots,
            product_strategy_result=product_strategy_result,
        )
        recommendations = self.generate_recommendations(
            snapshots=snapshots,
            duplicate_groups=duplicate_groups,
            incomplete_product_ids=incomplete_ids,
            portfolio_gaps=gaps,
            product_strategy_result=product_strategy_result,
        )
        counts = self._portfolio_counts(snapshots)
        status = self.determine_health_status(
            snapshots=snapshots,
            duplicate_groups=duplicate_groups,
            incomplete_product_ids=incomplete_ids,
            portfolio_gaps=gaps,
        )
        return ProductCatalogHealth(
            status=status,
            products=snapshots,
            total_products=len(snapshots),
            active_products=counts["active"],
            draft_products=counts["draft"],
            free_products=counts["free"],
            paid_products=counts["paid"],
            bundle_products=counts["bundle"],
            story_products=counts["story"],
            photoshoot_products=counts["photoshoot"],
            collection_products=counts["collection"],
            missing_product_types=tuple(gaps),
            duplicate_groups=duplicate_groups,
            incomplete_product_ids=incomplete_ids,
            portfolio_gaps=tuple(gaps),
            recommendations=recommendations,
            compatibility={
                "source": "product_catalog_management",
                "owner": "ProductCatalogManagementService",
                "read_only": True,
                "provider_neutral": True,
                "advisory_only": True,
                "creates_products": False,
                "modifies_products": False,
                "publishes_products": False,
                "executes_telegram": False,
                "generates_product_strategy": False,
                "product_catalog_owner_preserved": True,
                "product_strategy_owner_preserved": True,
                "product_business_consumed": bool(snapshots),
                "product_strategy_consumed": product_strategy_result is not None,
            },
            metadata=dict(metadata or {}),
        )

    def build_from_catalog(self, **context: Any) -> ProductCatalogHealth:
        displays = self.product_catalog.list_workspace_display_models()
        return self.build_catalog_health(products=displays, **context)

    def detect_duplicate_products(
        self,
        snapshots: Iterable[ProductBusinessSnapshot],
    ) -> Mapping[str, tuple[str, ...]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for snapshot in snapshots:
            key = self._duplicate_key(snapshot)
            if not key:
                continue
            product_id = self._safe_text(snapshot.product_id)
            if product_id:
                groups[key].append(product_id)
        return {
            key: tuple(product_ids)
            for key, product_ids in groups.items()
            if len(product_ids) > 1
        }

    def detect_incomplete_products(
        self,
        snapshots: Iterable[ProductBusinessSnapshot],
    ) -> tuple[str, ...]:
        incomplete: list[str] = []
        for snapshot in snapshots:
            if self._is_incomplete(snapshot):
                product_id = self._safe_text(snapshot.product_id)
                if product_id:
                    incomplete.append(product_id)
        return tuple(dict.fromkeys(incomplete))

    def detect_portfolio_gaps(
        self,
        snapshots: Iterable[ProductBusinessSnapshot],
        *,
        product_strategy_result: Any | None = None,
    ) -> tuple[str, ...]:
        items = tuple(snapshots)
        counts = self._portfolio_counts(items)
        gaps: list[str] = []
        if not items:
            gaps.append("missing_products")
        if counts["free"] == 0:
            gaps.append("missing_free_preview")
        if counts["paid"] == 0:
            gaps.append("missing_premium_product")
        if counts["bundle"] == 0:
            gaps.append("missing_bundle")
        if counts["story"] == 0:
            gaps.append("missing_story_product")
        if counts["photoshoot"] == 0:
            gaps.append("missing_photoshoot_product")
        strategy_types = self._strategy_recommendation_types(product_strategy_result)
        if COLLECTION_RECOMMENDATION_TYPES & set(strategy_types) and counts["collection"] == 0:
            gaps.append("missing_collection_product")
        if "story_product" in strategy_types and counts["story"] == 0:
            gaps.append("missing_strategy_story_product")
        if "bundle" in strategy_types and counts["bundle"] == 0:
            gaps.append("missing_strategy_bundle")
        if "photoshoot_product" in strategy_types and counts["photoshoot"] == 0:
            gaps.append("missing_strategy_photoshoot_product")
        if "free_preview" in strategy_types and counts["free"] == 0:
            gaps.append("missing_strategy_free_preview")
        return tuple(dict.fromkeys(gaps))

    def generate_recommendations(
        self,
        *,
        snapshots: Iterable[ProductBusinessSnapshot],
        duplicate_groups: Mapping[str, tuple[str, ...]],
        incomplete_product_ids: tuple[str, ...],
        portfolio_gaps: tuple[str, ...],
        product_strategy_result: Any | None = None,
    ) -> tuple[ProductCatalogRecommendation, ...]:
        recommendations: list[ProductCatalogRecommendation] = []
        gap_map = {
            "missing_free_preview": (
                ProductCatalogRecommendationType.CREATE_FREE_PREVIEW,
                "Create FREE Preview",
                "Catalog has no FREE Product to build trust or provide a preview.",
                "FREE",
                None,
            ),
            "missing_premium_product": (
                ProductCatalogRecommendationType.CREATE_PREMIUM_PRODUCT,
                "Create Premium Product",
                "Catalog has no PAID Product available for monetization.",
                "PAID",
                None,
            ),
            "missing_bundle": (
                ProductCatalogRecommendationType.CREATE_BUNDLE,
                "Create Bundle",
                "Catalog has no Bundle Product.",
                None,
                "BUNDLE",
            ),
            "missing_story_product": (
                ProductCatalogRecommendationType.CREATE_STORY_PRODUCT,
                "Create Story Product",
                "Catalog has no Story Product.",
                None,
                "STORY",
            ),
            "missing_photoshoot_product": (
                ProductCatalogRecommendationType.COMPLETE_PHOTOSHOOT_CATALOG,
                "Complete Photoshoot Catalog",
                "Catalog has no Photoshoot-style Product.",
                None,
                "PHOTO_SET",
            ),
            "missing_collection_product": (
                ProductCatalogRecommendationType.CREATE_COLLECTION_PRODUCT,
                "Create Collection Product",
                "Product Strategy indicates collection potential, but no Collection-style Product is present.",
                None,
                "BUNDLE",
            ),
        }
        normalized_gaps = set(portfolio_gaps)
        for gap, data in gap_map.items():
            if gap not in normalized_gaps:
                continue
            rec_type, label, reason, delivery_type, product_type = data
            recommendations.append(
                ProductCatalogRecommendation(
                    recommendation_type=rec_type,
                    label=label,
                    reason=reason,
                    priority="HIGH" if gap in {"missing_free_preview", "missing_premium_product"} else "NORMAL",
                    target_delivery_type=delivery_type,
                    target_product_type=product_type,
                    evidence={
                        "gap": gap,
                        "strategy_recommendation_types": self._strategy_recommendation_types(
                            product_strategy_result
                        ),
                    },
                )
            )
        if incomplete_product_ids:
            recommendations.append(
                ProductCatalogRecommendation(
                    recommendation_type=ProductCatalogRecommendationType.COMPLETE_PRODUCT,
                    label="Complete Product Catalog",
                    reason="One or more Products are incomplete or need attention.",
                    priority="HIGH",
                    product_ids=incomplete_product_ids,
                    evidence={"incomplete_product_ids": incomplete_product_ids},
                )
            )
        for key, product_ids in duplicate_groups.items():
            recommendations.append(
                ProductCatalogRecommendation(
                    recommendation_type=ProductCatalogRecommendationType.REMOVE_DUPLICATE,
                    label="Review Duplicate Product",
                    reason="Multiple Products appear to represent the same catalog item.",
                    priority="NORMAL",
                    product_ids=product_ids,
                    evidence={"duplicate_key": key},
                )
            )
        if not recommendations and tuple(snapshots):
            recommendations.append(
                ProductCatalogRecommendation(
                    recommendation_type=ProductCatalogRecommendationType.CATALOG_COMPLETE,
                    label="Catalog Complete",
                    reason="No missing, duplicate, or incomplete Product gaps were detected.",
                    priority="LOW",
                )
            )
        return tuple(recommendations)

    def determine_health_status(
        self,
        *,
        snapshots: Iterable[ProductBusinessSnapshot],
        duplicate_groups: Mapping[str, tuple[str, ...]],
        incomplete_product_ids: tuple[str, ...],
        portfolio_gaps: tuple[str, ...],
    ) -> ProductCatalogHealthStatus:
        items = tuple(snapshots)
        if not items:
            return ProductCatalogHealthStatus.EMPTY
        if incomplete_product_ids or duplicate_groups:
            return ProductCatalogHealthStatus.NEEDS_ATTENTION
        if portfolio_gaps:
            return ProductCatalogHealthStatus.INCOMPLETE
        return ProductCatalogHealthStatus.HEALTHY

    def _normalize_snapshots(
        self,
        *,
        products: Iterable[Any] | None,
        product_business_snapshots: Iterable[
            ProductBusinessSnapshot | Mapping[str, Any]
        ]
        | None,
    ) -> tuple[ProductBusinessSnapshot, ...]:
        snapshots: list[ProductBusinessSnapshot] = []
        for snapshot in tuple(product_business_snapshots or ()):
            if isinstance(snapshot, ProductBusinessSnapshot):
                snapshots.append(snapshot)
            else:
                snapshots.append(self._snapshot_from_mapping(snapshot))
        for product in tuple(products or ()):
            if isinstance(product, ProductBusinessSnapshot):
                snapshots.append(product)
            elif isinstance(product, Mapping) and (
                "product_id" in product or "product_health" in product
            ):
                snapshots.append(self._snapshot_from_mapping(product))
            else:
                snapshots.append(
                    self.product_business.build_snapshot(
                        product_display=product if self._read(product, "product") else None,
                        product=None if self._read(product, "product") else product,
                    )
                )
        return tuple(snapshots)

    @staticmethod
    def _snapshot_from_mapping(value: Mapping[str, Any]) -> ProductBusinessSnapshot:
        return ProductBusinessSnapshot(
            product_id=ProductCatalogManagementService._safe_text(
                value.get("product_id") or value.get("id")
            ),
            product_name=ProductCatalogManagementService._safe_text(
                value.get("product_name") or value.get("display_name")
            ),
            product_type=ProductCatalogManagementService._safe_text(
                value.get("product_type")
            ),
            delivery_type=ProductCatalogManagementService._safe_text(
                value.get("delivery_type")
            ),
            product_status=ProductCatalogManagementService._safe_text(
                value.get("product_status") or value.get("status")
            ),
            availability=ProductCatalogManagementService._enum_or_default(
                ProductBusinessAvailability,
                value.get("availability"),
                ProductBusinessAvailability.UNKNOWN,
            ),
            product_health=ProductCatalogManagementService._enum_or_default(
                ProductBusinessHealth,
                value.get("product_health"),
                ProductBusinessHealth.UNKNOWN,
            ),
            publishing_readiness=value.get("publishing_readiness") or {},
            customer_reach=value.get("customer_reach") or {},
            performance_summary=value.get("performance_summary") or {},
            metadata=value.get("metadata") or {},
        )

    @staticmethod
    def _portfolio_counts(
        snapshots: Iterable[ProductBusinessSnapshot],
    ) -> Counter[str]:
        counts: Counter[str] = Counter()
        for snapshot in snapshots:
            product_type = ProductCatalogManagementService._text(snapshot.product_type)
            delivery_type = ProductCatalogManagementService._text(snapshot.delivery_type)
            availability = snapshot.availability
            if availability in {
                ProductBusinessAvailability.AVAILABLE,
                ProductBusinessAvailability.TELEGRAM_READY,
            }:
                counts["active"] += 1
            if availability == ProductBusinessAvailability.DRAFT:
                counts["draft"] += 1
            if delivery_type == "FREE":
                counts["free"] += 1
            if delivery_type == "PAID":
                counts["paid"] += 1
            if product_type == "BUNDLE":
                counts["bundle"] += 1
            if product_type == "STORY":
                counts["story"] += 1
            if product_type in PHOTOSHOOT_TYPES:
                counts["photoshoot"] += 1
            if product_type in {"BUNDLE", "CUSTOM"}:
                counts["collection"] += 1
        return counts

    @staticmethod
    def _is_incomplete(snapshot: ProductBusinessSnapshot) -> bool:
        return any(
            (
                not snapshot.product_id,
                not snapshot.product_type,
                not snapshot.delivery_type,
                snapshot.availability
                in {
                    ProductBusinessAvailability.UNKNOWN,
                    ProductBusinessAvailability.DRAFT,
                    ProductBusinessAvailability.UNAVAILABLE,
                },
                snapshot.product_health
                in {
                    ProductBusinessHealth.NEEDS_ATTENTION,
                    ProductBusinessHealth.DRAFT,
                    ProductBusinessHealth.UNKNOWN,
                },
                bool(snapshot.publishing_readiness.get("attention_required")),
            )
        )

    @staticmethod
    def _duplicate_key(snapshot: ProductBusinessSnapshot) -> str | None:
        name = ProductCatalogManagementService._safe_text(snapshot.product_name)
        if name:
            return f"name:{name.strip().lower()}"
        product_type = ProductCatalogManagementService._text(snapshot.product_type)
        delivery_type = ProductCatalogManagementService._text(snapshot.delivery_type)
        if product_type and delivery_type:
            return f"type:{product_type}:{delivery_type}"
        return None

    @staticmethod
    def _strategy_recommendation_types(product_strategy_result: Any | None) -> tuple[str, ...]:
        recommendations = tuple(
            ProductCatalogManagementService._read(
                product_strategy_result,
                "recommendations",
            )
            or ()
        )
        catalog = ProductCatalogManagementService._read(
            product_strategy_result,
            "catalog_recommendation",
        )
        recommendations += tuple(
            ProductCatalogManagementService._read(catalog, "recommended_products") or ()
        )
        return tuple(
            dict.fromkeys(
                str(
                    ProductCatalogManagementService._read(
                        recommendation,
                        "recommendation_type",
                    )
                    or ""
                )
                for recommendation in recommendations
                if ProductCatalogManagementService._read(
                    recommendation,
                    "recommendation_type",
                )
            )
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

    @staticmethod
    def _text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value)).strip().upper()

    @staticmethod
    def _enum_or_default(enum_type: Any, value: Any, default: Any) -> Any:
        if isinstance(value, enum_type):
            return value
        if value in (None, ""):
            return default
        try:
            return enum_type(str(getattr(value, "value", value)))
        except ValueError:
            return default

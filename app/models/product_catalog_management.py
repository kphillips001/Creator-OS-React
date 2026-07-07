"""Provider-neutral Product Catalog Management read models.

Catalog Management evaluates the Product Catalog as a business portfolio. It is
advisory only: it does not create, modify, publish, or retire Products.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.product_business import ProductBusinessSnapshot


class ProductCatalogHealthStatus(str, Enum):
    EMPTY = "EMPTY"
    INCOMPLETE = "INCOMPLETE"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    HEALTHY = "HEALTHY"


class ProductCatalogRecommendationType(str, Enum):
    CREATE_FREE_PREVIEW = "CREATE_FREE_PREVIEW"
    CREATE_PREMIUM_PRODUCT = "CREATE_PREMIUM_PRODUCT"
    CREATE_BUNDLE = "CREATE_BUNDLE"
    CREATE_STORY_PRODUCT = "CREATE_STORY_PRODUCT"
    COMPLETE_PHOTOSHOOT_CATALOG = "COMPLETE_PHOTOSHOOT_CATALOG"
    CREATE_COLLECTION_PRODUCT = "CREATE_COLLECTION_PRODUCT"
    COMPLETE_PRODUCT = "COMPLETE_PRODUCT"
    REMOVE_DUPLICATE = "REMOVE_DUPLICATE"
    CATALOG_COMPLETE = "CATALOG_COMPLETE"


@dataclass(frozen=True)
class ProductCatalogRecommendation:
    recommendation_type: ProductCatalogRecommendationType
    label: str
    reason: str | None = None
    priority: str = "NORMAL"
    target_product_type: str | None = None
    target_delivery_type: str | None = None
    product_ids: tuple[str, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "ProductCatalogManagementService"


@dataclass(frozen=True)
class ProductCatalogHealth:
    status: ProductCatalogHealthStatus
    products: tuple[ProductBusinessSnapshot, ...] = ()
    total_products: int = 0
    active_products: int = 0
    draft_products: int = 0
    free_products: int = 0
    paid_products: int = 0
    bundle_products: int = 0
    story_products: int = 0
    photoshoot_products: int = 0
    collection_products: int = 0
    missing_product_types: tuple[str, ...] = ()
    duplicate_groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    incomplete_product_ids: tuple[str, ...] = ()
    portfolio_gaps: tuple[str, ...] = ()
    recommendations: tuple[ProductCatalogRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommendation(self) -> ProductCatalogRecommendation | None:
        return self.recommendations[0] if self.recommendations else None

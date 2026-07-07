"""Commerce recommendation models for imported Creator OS material."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.product import ProductDeliveryType, ProductType


@dataclass(frozen=True)
class CommerceIntelligenceEvidence:
    reason: str
    detail: str | None = None
    weight: int = 0


@dataclass(frozen=True)
class CommercePriceRecommendation:
    suggested_price_cents: int
    min_price_cents: int
    max_price_cents: int
    currency: str = "USD"
    pricing_rule: str | None = None


@dataclass(frozen=True)
class PublishingReadinessRecommendation:
    status: str
    action: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class CommerceRecommendation:
    source_type: str
    source_id: str
    asset_ids: tuple[int, ...]
    product_type: ProductType
    delivery_type: ProductDeliveryType
    suggested_name: str
    suggested_description: str | None
    suggested_tags: tuple[str, ...] = ()
    suggested_themes: tuple[str, ...] = ()
    suggested_keywords: tuple[str, ...] = ()
    price: CommercePriceRecommendation | None = None
    publishing: PublishingReadinessRecommendation | None = None
    confidence: float = 0.0
    evidence: tuple[CommerceIntelligenceEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

"""Provider-neutral Sales Management recommendation read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class SalesRecommendationType(str, Enum):
    CONTINUE_RELATIONSHIP = "CONTINUE_RELATIONSHIP"
    OFFER_FREE_PRODUCT = "OFFER_FREE_PRODUCT"
    OFFER_PREMIUM_PRODUCT = "OFFER_PREMIUM_PRODUCT"
    OFFER_BUNDLE = "OFFER_BUNDLE"
    OFFER_STORY = "OFFER_STORY"
    OFFER_PHOTOSHOOT = "OFFER_PHOTOSHOOT"
    UPSELL = "UPSELL"
    CROSS_SELL = "CROSS_SELL"
    DELAY_SELLING = "DELAY_SELLING"
    CONTINUE_EXPERIENCE = "CONTINUE_EXPERIENCE"
    NO_SALES_ACTION = "NO_SALES_ACTION"


class SalesPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class SalesRecommendation:
    """Recommended commercial action for a customer."""

    recommendation_type: SalesRecommendationType
    priority: SalesPriority = SalesPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Sales Context"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    product_reference: str | None = None
    offer_reference: str | None = None
    experience_reference: str | None = None
    customer_reference: str | None = None
    source: str = "SalesManagementService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SalesManagement:
    """Canonical read-only sales opportunity state for one customer."""

    customer_id: str | None = None
    provider: str = "telegram"
    relationship_stage: str | None = None
    conversation_status: str | None = None
    business_health: str = "UNKNOWN"
    current_product_ids: tuple[str, ...] = ()
    active_offer_ids: tuple[str, ...] = ()
    recommendation: SalesRecommendation = field(
        default_factory=lambda: SalesRecommendation(
            recommendation_type=SalesRecommendationType.NO_SALES_ACTION,
            priority=SalesPriority.LOW,
            recommended_next_action="No Sales Action",
        )
    )
    recommendations: tuple[SalesRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

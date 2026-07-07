"""Provider-neutral Product Business read models.

Product Business is a read-only aggregation layer over Product Catalog,
Lifecycle, Publishing, Customer Intelligence, and Business Learning. It does
not own Product persistence, strategy generation, publishing execution, or
learning mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.product_lifecycle import ProductLifecycle
from app.models.publishing_automation import PublishingAutomationStatus


class ProductBusinessHealth(str, Enum):
    UNKNOWN = "UNKNOWN"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    DRAFT = "DRAFT"
    READY = "READY"
    ACTIVE = "ACTIVE"
    HEALTHY = "HEALTHY"
    UNDERPERFORMING = "UNDERPERFORMING"


class ProductBusinessAvailability(str, Enum):
    UNKNOWN = "UNKNOWN"
    UNAVAILABLE = "UNAVAILABLE"
    DRAFT = "DRAFT"
    PUBLISHING = "PUBLISHING"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    AVAILABLE = "AVAILABLE"
    TELEGRAM_READY = "TELEGRAM_READY"


@dataclass(frozen=True)
class ProductBusinessRecommendation:
    label: str
    reason: str | None = None
    source: str = "ProductBusinessService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductBusinessSnapshot:
    """Canonical read model for a Product's business health."""

    product_id: str | None = None
    product_name: str | None = None
    product_type: str | None = None
    delivery_type: str | None = None
    product_status: str | None = None
    lifecycle: ProductLifecycle | None = None
    publishing_status: PublishingAutomationStatus | None = None
    publishing_readiness: Mapping[str, Any] = field(default_factory=dict)
    availability: ProductBusinessAvailability = ProductBusinessAvailability.UNKNOWN
    customer_reach: Mapping[str, Any] = field(default_factory=dict)
    performance_summary: Mapping[str, Any] = field(default_factory=dict)
    product_health: ProductBusinessHealth = ProductBusinessHealth.UNKNOWN
    next_business_recommendation: ProductBusinessRecommendation = field(
        default_factory=lambda: ProductBusinessRecommendation(
            label="No Product Business Action",
            reason="No Product Business context was available.",
        )
    )
    strategy_summary: Mapping[str, Any] = field(default_factory=dict)
    commerce_summary: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommended_business_action(self) -> str:
        return self.next_business_recommendation.label

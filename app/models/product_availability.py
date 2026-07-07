"""Provider-neutral Product Availability read models.

Product Availability summarizes whether a Product is truly available to
customers. It aggregates Product status, lifecycle, publishing, media link, and
Telegram readiness without replacing any of those domains.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.product_business import ProductBusinessSnapshot
from app.models.product_lifecycle import ProductLifecycle
from app.models.publishing_automation import PublishingAutomationStatus


class ProductAvailabilityStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    PUBLISHING = "PUBLISHING"
    ARCHIVED = "ARCHIVED"
    DRAFT = "DRAFT"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


@dataclass(frozen=True)
class ProductAvailabilityRecommendation:
    label: str
    reason: str | None = None
    source: str = "ProductAvailabilityService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductAvailability:
    product_id: str | None = None
    status: ProductAvailabilityStatus = ProductAvailabilityStatus.UNAVAILABLE
    recommendation: ProductAvailabilityRecommendation = field(
        default_factory=lambda: ProductAvailabilityRecommendation(
            label="Unavailable",
            reason="No availability context was available.",
        )
    )
    product_status: str | None = None
    lifecycle: ProductLifecycle | None = None
    publishing_status: PublishingAutomationStatus | None = None
    product_business_snapshot: ProductBusinessSnapshot | None = None
    publishing_state: str | None = None
    media_link_status: str | None = None
    provider_status: str | None = None
    telegram_ready: bool = False
    available_for_customers: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommended_action(self) -> str:
        return self.recommendation.label

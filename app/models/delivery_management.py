"""Provider-neutral Delivery Management recommendation read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class DeliveryRecommendationType(str, Enum):
    DELIVER_FREE_PRODUCT = "DELIVER_FREE_PRODUCT"
    DELIVER_PREMIUM_PRODUCT = "DELIVER_PREMIUM_PRODUCT"
    DELIVER_BUNDLE = "DELIVER_BUNDLE"
    DELIVER_STORY = "DELIVER_STORY"
    SEND_MEDIA_LINK = "SEND_MEDIA_LINK"
    PREVENT_DUPLICATE_DELIVERY = "PREVENT_DUPLICATE_DELIVERY"
    WAIT = "WAIT"
    NO_DELIVERY = "NO_DELIVERY"


class DeliveryPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DeliveryRecommendation:
    """Recommended delivery action for a customer and product."""

    recommendation_type: DeliveryRecommendationType
    priority: DeliveryPriority = DeliveryPriority.NORMAL
    confidence: float = 0.0
    recommended_next_action: str = "Review Delivery Context"
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    product_reference: str | None = None
    offer_reference: str | None = None
    experience_reference: str | None = None
    delivery_method: str | None = None
    source: str = "DeliveryManagementService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryManagement:
    """Canonical read-only delivery opportunity state."""

    customer_id: str | None = None
    provider: str = "telegram"
    business_health: str = "UNKNOWN"
    operation_status: str | None = None
    current_product_ids: tuple[str, ...] = ()
    active_offer_ids: tuple[str, ...] = ()
    delivery_history: Mapping[str, Any] = field(default_factory=dict)
    recommendation: DeliveryRecommendation = field(
        default_factory=lambda: DeliveryRecommendation(
            recommendation_type=DeliveryRecommendationType.NO_DELIVERY,
            priority=DeliveryPriority.LOW,
            recommended_next_action="No Delivery",
        )
    )
    recommendations: tuple[DeliveryRecommendation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

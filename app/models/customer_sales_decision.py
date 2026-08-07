"""Immutable output of the deterministic Customer Sales Brain."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from app.models.photoshoot_experience_recommendation import (
    PhotoshootExperienceRecommendation,
)
from app.models.autonomous_sales_progression import NextSalesAction


class CustomerSalesDecisionType(str, Enum):
    CONTINUE_CONVERSATION = "CONTINUE_CONVERSATION"
    PRESENT_OFFER = "PRESENT_OFFER"
    WAIT = "WAIT"
    NUDGE_ACTIVE_OFFER = "NUDGE_ACTIVE_OFFER"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    CONGRATULATE_PURCHASE = "CONGRATULATE_PURCHASE"
    UPSELL = "UPSELL"
    CROSS_SELL = "CROSS_SELL"
    NO_SALE = "NO_SALE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class CustomerSalesReasonCode(str, Enum):
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    NO_COMMERCE_PROFILE = "NO_COMMERCE_PROFILE"
    NO_ACTIVE_OFFER = "NO_ACTIVE_OFFER"
    ACTIVE_OFFER_PRESENTED = "ACTIVE_OFFER_PRESENTED"
    ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE = (
        "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE"
    )
    ACTIVE_OFFER_NUDGE_ELIGIBLE = "ACTIVE_OFFER_NUDGE_ELIGIBLE"
    ACTIVE_OFFER_EXPIRED = "ACTIVE_OFFER_EXPIRED"
    PAYMENT_RECONCILIATION_PENDING = "PAYMENT_RECONCILIATION_PENDING"
    PAYMENT_ATTRIBUTION_UNKNOWN = "PAYMENT_ATTRIBUTION_UNKNOWN"
    PURCHASE_VERIFIED = "PURCHASE_VERIFIED"
    FIRST_PURCHASE = "FIRST_PURCHASE"
    REPEAT_BUYER = "REPEAT_BUYER"
    RECENT_PURCHASE_COOLDOWN = "RECENT_PURCHASE_COOLDOWN"
    SELLING_COOLDOWN = "SELLING_COOLDOWN"
    NO_ELIGIBLE_OFFERING = "NO_ELIGIBLE_OFFERING"
    NO_SELLING_STRATEGY = "NO_SELLING_STRATEGY"
    OFFERING_ALREADY_ACTIVE = "OFFERING_ALREADY_ACTIVE"
    OFFERING_UNAVAILABLE = "OFFERING_UNAVAILABLE"
    PUBLICATION_NOT_LIVE = "PUBLICATION_NOT_LIVE"
    CUSTOMER_NOT_ELIGIBLE = "CUSTOMER_NOT_ELIGIBLE"
    CURRENT_TURN_NOT_READY = "CURRENT_TURN_NOT_READY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class CustomerBuyerStage(str, Enum):
    UNKNOWN = "UNKNOWN"
    PROSPECT = "PROSPECT"
    FIRST_TIME_BUYER = "FIRST_TIME_BUYER"
    REPEAT_BUYER = "REPEAT_BUYER"
    HIGH_VALUE_BUYER = "HIGH_VALUE_BUYER"
    INACTIVE_BUYER = "INACTIVE_BUYER"


@dataclass(frozen=True)
class CustomerSalesDecision:
    creator_profile_id: int
    fanvue_account_id: int
    external_fanvue_buyer_uuid: UUID | None
    telegram_user_id: int | None
    identity_resolved: bool
    decision: CustomerSalesDecisionType
    reason_code: CustomerSalesReasonCode
    reason_summary: str
    buyer_stage: CustomerBuyerStage
    commerce_signal: Mapping[str, Any]
    active_purchase_intent_id: UUID | None
    active_offering_id: UUID | None
    active_offer_status: str | None
    active_offer_conversion_state: str
    recommended_offering_id: UUID | None
    recommended_publication_id: UUID | None
    recommended_delivery_url: str | None
    sell_allowed: bool
    nudge_allowed: bool
    upsell_allowed: bool
    cross_sell_allowed: bool
    congratulate_allowed: bool
    cooldown_until: datetime | None
    evaluated_at: datetime
    decision_metadata: Mapping[str, Any]
    recommended_offering_title: str | None = None
    recommended_offering_short_description: str | None = None
    recommended_offering_price_minor: int | None = None
    recommended_offering_currency: str | None = None
    recommended_photoshoot_experience: PhotoshootExperienceRecommendation | None = None
    next_sales_action: NextSalesAction | None = None
    bundle_sales_context: Mapping[str, Any] | None = None


def immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))

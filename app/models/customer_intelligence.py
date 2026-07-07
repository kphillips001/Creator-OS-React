"""Provider-neutral Customer Intelligence models.

Customer Intelligence is the long-term customer knowledge boundary for Creator
OS. These models are read models only; they do not define persistence, runtime
execution, provider APIs, or DecisionEngine behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class CustomerRelationshipStage(str, Enum):
    NEW = "new"
    RETURNING = "returning"
    ACTIVE = "active"
    ENGAGED = "engaged"
    PURCHASER = "purchaser"
    REPEAT_PURCHASER = "repeat_purchaser"
    VIP = "vip"
    DORMANT = "dormant"


@dataclass(frozen=True)
class CustomerIdentity:
    canonical_customer_id: str | None = None
    customer_id: str | None = None
    provider: str | None = None
    provider_customer_id: str | None = None
    provider_account_id: str | None = None
    telegram_identifier: str | None = None
    platform_identifiers: Mapping[str, str] = field(default_factory=dict)
    provider_identities: Mapping[str, Mapping[str, str]] = field(default_factory=dict)
    future_provider_identifiers: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerProfile:
    display_name: str | None = None
    username: str | None = None
    preferred_name: str | None = None
    timezone: str | None = None
    language: str | None = None
    interests: tuple[str, ...] = ()
    preferences: Mapping[str, Any] = field(default_factory=dict)
    creator_notes: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    customer_segments: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerCommerceMemory:
    products_offered: tuple[str, ...] = ()
    products_purchased: tuple[str, ...] = ()
    free_assets_delivered: tuple[str, ...] = ()
    paid_products_delivered: tuple[str, ...] = ()
    delivered_free_products: tuple[str, ...] = ()
    delivered_paid_products: tuple[str, ...] = ()
    purchased_bundles: tuple[str, ...] = ()
    purchased_photoshoots: tuple[str, ...] = ()
    purchased_stories: tuple[str, ...] = ()
    completed_experience_ids: tuple[str, ...] = ()
    previous_offers: tuple[str, ...] = ()
    previous_purchases: tuple[str, ...] = ()
    declined_offers: tuple[str, ...] = ()
    offer_outcomes: Mapping[str, str] = field(default_factory=dict)
    offer_timestamps: Mapping[str, Any] = field(default_factory=dict)
    purchase_timestamps: Mapping[str, Any] = field(default_factory=dict)
    delivery_timestamps: Mapping[str, Any] = field(default_factory=dict)
    offer_events: tuple[Mapping[str, Any], ...] = ()
    purchase_events: tuple[Mapping[str, Any], ...] = ()
    delivery_events: tuple[Mapping[str, Any], ...] = ()
    completed_experience_events: tuple[Mapping[str, Any], ...] = ()
    duplicate_prevention_signals: tuple[str, ...] = ()
    last_purchase: Mapping[str, Any] = field(default_factory=dict)
    last_delivery: Mapping[str, Any] = field(default_factory=dict)
    customer_spending_summary: Mapping[str, Any] = field(default_factory=dict)
    customer_engagement_summary: Mapping[str, Any] = field(default_factory=dict)
    commerce_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerExperienceProgress:
    current_experience_id: str | None = None
    current_product_id: str | None = None
    current_asset_id: str | None = None
    conversation_progress: str | None = None
    commerce_progress: str | None = None
    current_position: str | None = None
    progress_percentage: int = 0
    completed_experience_ids: tuple[str, ...] = ()
    seen_experience_ids: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerRelationshipIntelligence:
    stage: CustomerRelationshipStage = CustomerRelationshipStage.NEW
    engagement_score: int = 0
    engagement_level: str = "none"
    commerce_maturity: str = "none"
    relationship_progression: Mapping[str, Any] = field(default_factory=dict)
    engagement_indicators: Mapping[str, Any] = field(default_factory=dict)
    recommendations: tuple[str, ...] = ()
    primary_recommendation: str | None = None
    last_interaction_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerIntelligenceSnapshot:
    identity: CustomerIdentity = field(default_factory=CustomerIdentity)
    profile: CustomerProfile = field(default_factory=CustomerProfile)
    relationship_stage: CustomerRelationshipStage = CustomerRelationshipStage.NEW
    relationship_intelligence: CustomerRelationshipIntelligence = field(
        default_factory=CustomerRelationshipIntelligence
    )
    commerce_memory: CustomerCommerceMemory = field(
        default_factory=CustomerCommerceMemory
    )
    experience_progress: CustomerExperienceProgress = field(
        default_factory=CustomerExperienceProgress
    )
    last_interaction_metadata: Mapping[str, Any] = field(default_factory=dict)
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerIntelligenceReview:
    customer_id: str | None = None
    display_name: str | None = None
    provider: str | None = None
    relationship_stage: str = CustomerRelationshipStage.NEW.value
    engagement_level: str = "none"
    commerce_maturity: str = "none"
    profile: Mapping[str, Any] = field(default_factory=dict)
    relationship: Mapping[str, Any] = field(default_factory=dict)
    commerce_history: Mapping[str, Any] = field(default_factory=dict)
    purchase_history_summary: Mapping[str, Any] = field(default_factory=dict)
    delivery_history_summary: Mapping[str, Any] = field(default_factory=dict)
    experience_progress: Mapping[str, Any] = field(default_factory=dict)
    interests: tuple[str, ...] = ()
    preferences: Mapping[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    customer_segments: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()
    recommendation_rationale: tuple[str, ...] = ()
    activity_summary: Mapping[str, Any] = field(default_factory=dict)
    compatibility_metadata: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerIntelligenceReviewSummary:
    total_customers: int = 0
    relationship_stage_counts: Mapping[str, int] = field(default_factory=dict)
    engagement_level_counts: Mapping[str, int] = field(default_factory=dict)
    commerce_maturity_counts: Mapping[str, int] = field(default_factory=dict)
    customers_with_purchases: int = 0
    customers_with_active_experience: int = 0
    recommendation_counts: Mapping[str, int] = field(default_factory=dict)
    items: tuple[CustomerIntelligenceReview, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

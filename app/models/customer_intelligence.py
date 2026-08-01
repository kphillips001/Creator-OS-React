"""Provider-neutral Customer Intelligence models.

Customer Intelligence is the long-term customer knowledge boundary for Creator
OS. These models are read models only; they do not define persistence, runtime
execution, provider APIs, or DecisionEngine behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections.abc import Iterator
from types import MappingProxyType
from typing import Any, Mapping


class FrozenMapping(Mapping[str, Any]):
    """Small recursively immutable mapping used by canonical read models."""

    __slots__ = ("__values",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        object.__setattr__(self, "_FrozenMapping__values", MappingProxyType({
            str(key): deep_freeze(value) for key, value in (values or {}).items()
        }))

    def __getitem__(self, key: str) -> Any:
        return self.__values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.__values)

    def __len__(self) -> int:
        return len(self.__values)

    def __copy__(self) -> "FrozenMapping":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "FrozenMapping":
        return self


def deep_freeze(value: Any) -> Any:
    """Recursively detach and freeze canonical evidence values."""

    if isinstance(value, FrozenMapping):
        return value
    if isinstance(value, Mapping):
        return FrozenMapping(value)
    if isinstance(value, (tuple, list, set, frozenset)):
        return tuple(deep_freeze(item) for item in value)
    return value


class CustomerRelationshipStage(str, Enum):
    NEW = "new"
    RETURNING = "returning"
    ACTIVE = "active"
    ENGAGED = "engaged"
    PURCHASER = "purchaser"
    REPEAT_PURCHASER = "repeat_purchaser"
    VIP = "vip"
    DORMANT = "dormant"


class CustomerIntelligenceState(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    PARTIAL = "PARTIAL"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"


class CustomerSignalQuality(str, Enum):
    STRONG_COMMERCIAL = "STRONG_COMMERCIAL"
    STRONG_BEHAVIORAL = "STRONG_BEHAVIORAL"
    SUPPORTING = "SUPPORTING"
    WEAK = "WEAK"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class CustomerEvidenceReference:
    authority: str
    record_id: str | None
    creator_profile_id: int
    customer_identity_path: str
    lifecycle: str | None = None
    timestamp: str | None = None
    currency: str | None = None
    quality: CustomerSignalQuality = CustomerSignalQuality.SUPPORTING
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", deep_freeze(self.metadata))


@dataclass(frozen=True)
class CustomerIntelligenceMetric:
    name: str
    value: Any
    unit: str
    state: CustomerIntelligenceState
    calculation_method: str
    calculated_at: str
    currency: str | None = None
    numerator: float | int | None = None
    denominator: float | int | None = None
    included_records: tuple[str, ...] = ()
    excluded_records: tuple[str, ...] = ()
    lifecycle_filters: tuple[str, ...] = ()
    confidence: float = 0.0
    conflicts: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", deep_freeze(self.value))
        object.__setattr__(self, "provenance", deep_freeze(self.provenance))


@dataclass(frozen=True)
class CustomerIntelligencePreference:
    dimension: str
    subject: str
    direction: str
    state: CustomerIntelligenceState
    quality: CustomerSignalQuality
    confidence: float
    positive_evidence: tuple[str, ...] = ()
    contradictory_evidence: tuple[str, ...] = ()
    observation_count: int = 0
    exposure_count: int = 0
    latest_evidence_at: str | None = None
    derivation_method: str = "evidence_count"
    conflicts: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()
    supporting_evidence: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provenance", deep_freeze(self.provenance))


@dataclass(frozen=True)
class CanonicalCustomerIntelligenceProfile:
    profile_state: CustomerIntelligenceState
    customer_context: Mapping[str, Any]
    identity_confidence: float
    facts: tuple[CustomerEvidenceReference, ...]
    commercial_summary: Mapping[str, Any]
    unified_purchase_history: tuple[Mapping[str, Any], ...]
    spending_profile: Mapping[str, CustomerIntelligenceMetric]
    ownership_summary: Mapping[str, Any]
    session_profile: Mapping[str, Any]
    purchase_preferences: tuple[CustomerIntelligencePreference, ...]
    media_preferences: tuple[CustomerIntelligencePreference, ...]
    bundle_behavior: Mapping[str, Any]
    video_conversion: Mapping[str, Any]
    engagement_profile: Mapping[str, Any]
    recommendation_history: Mapping[str, Any]
    interests: tuple[Mapping[str, Any], ...]
    aversions: tuple[Mapping[str, Any], ...]
    opportunities: tuple[Mapping[str, Any], ...]
    risks: tuple[Mapping[str, Any], ...]
    classifications: tuple[Mapping[str, Any], ...]
    section_states: Mapping[str, CustomerIntelligenceState]
    section_state_reasons: Mapping[str, tuple[str, ...]]
    conflicts: tuple[str, ...]
    insufficiencies: tuple[str, ...]
    provenance: Mapping[str, Any]
    calculation_metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, deep_freeze(getattr(self, name)))


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

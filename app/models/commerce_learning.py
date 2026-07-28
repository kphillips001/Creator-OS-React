"""Observed-only customer Commerce learning contracts."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class CommerceRecommendationOutcomeType(str, Enum):
    PRESENTED = "PRESENTED"
    OPENED = "OPENED"
    PURCHASED = "PURCHASED"
    IGNORED = "IGNORED"
    EXPIRED = "EXPIRED"
    DECLINED = "DECLINED"
    ABANDONED = "ABANDONED"
    REFUNDED = "REFUNDED"
    WOULD_HAVE_SOLD = "WOULD_HAVE_SOLD"


@dataclass(frozen=True)
class CommerceRecommendationOutcome:
    outcome_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    external_fanvue_user_uuid: UUID
    telegram_user_id: int | None
    commercial_offering_id: UUID
    purchase_intent_id: UUID | None
    outcome_type: CommerceRecommendationOutcomeType
    observed_at: datetime
    source_event_key: str
    evidence: Mapping[str, Any] = field(default_factory=dict)
    recommendation_trace: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerCommerceLearningProfile:
    learning_profile_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    external_fanvue_user_uuid: UUID
    telegram_user_id: int | None
    preferences: Mapping[str, Any]
    outcome_counts: Mapping[str, int]
    preferred_offering_type: str | None
    favorite_media_type: str | None
    average_price_minor: int | None
    preferred_price_min_minor: int | None
    preferred_price_max_minor: int | None
    repeat_purchase_frequency: float
    average_purchase_interval_days: float | None
    confidence: float
    evidence_count: int
    last_observed_at: datetime | None
    created_at: datetime
    updated_at: datetime

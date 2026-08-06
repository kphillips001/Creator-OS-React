"""Immutable output from deterministic Commercial Offering selection."""
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from app.models.commerce_recommendation import RecommendationResult
from app.models.photoshoot_experience_recommendation import (
    PhotoshootExperienceRecommendation,
)


class OfferingSelectionReason(str, Enum):
    ACTIVE_INTENT = "ACTIVE_INTENT"
    FEATURED = "FEATURED"
    MOST_RECENT = "MOST_RECENT"
    DEFAULT_ORDER = "DEFAULT_ORDER"
    INTELLIGENT_RANKING = "INTELLIGENT_RANKING"
    NO_ELIGIBLE_OFFERING = "NO_ELIGIBLE_OFFERING"


class OfferingExclusionReason(str, Enum):
    OFFERING_NOT_ACTIVE = "OFFERING_NOT_ACTIVE"
    OFFERING_ARCHIVED = "OFFERING_ARCHIVED"
    PUBLICATION_NOT_LIVE = "PUBLICATION_NOT_LIVE"
    DELIVERY_URL_MISSING = "DELIVERY_URL_MISSING"
    PROVIDER_NOT_ENABLED = "PROVIDER_NOT_ENABLED"
    CREATOR_MISMATCH = "CREATOR_MISMATCH"
    SALES_CHANNEL_MISMATCH = "SALES_CHANNEL_MISMATCH"
    OFFERING_ALREADY_ACTIVE = "OFFERING_ALREADY_ACTIVE"
    OFFERING_ALREADY_PURCHASED = "OFFERING_ALREADY_PURCHASED"
    DESTINATION_NOT_COMMERCIALLY_AVAILABLE = (
        "DESTINATION_NOT_COMMERCIALLY_AVAILABLE"
    )
    PRICE_INVALID = "PRICE_INVALID"
    PROVIDER_RESOURCE_NOT_PRESENT = "PROVIDER_RESOURCE_NOT_PRESENT"
    DELIVERY_ARTIFACT_MISSING = "DELIVERY_ARTIFACT_MISSING"
    OFFERING_EXPIRED = "OFFERING_EXPIRED"
    OFFERING_WITHDRAWN = "OFFERING_WITHDRAWN"
    OFFERING_DISABLED = "OFFERING_DISABLED"
    CANONICAL_REFERENCE_ASSET = "CANONICAL_REFERENCE_ASSET"


@dataclass(frozen=True)
class OfferingEligibilityEvaluation:
    offering_id: UUID
    title: str
    eligible: bool
    exclusion_reasons: tuple[str, ...]
    publication_id: UUID | None
    publication_provider: str | None
    publication_status: str | None
    delivery_url_available: bool
    offering_status: str
    offering_type: str
    primary_sales_channel: str
    published_at: str | None


@dataclass(frozen=True)
class SelectedOfferingResult:
    offering_id: UUID | None
    publication_id: UUID | None
    publication_provider: str | None
    delivery_url: str | None
    offering_type: str | None
    primary_sales_channel: str | None
    selection_reason: OfferingSelectionReason
    exclusion_reasons: tuple[str, ...]
    evaluations: tuple[OfferingEligibilityEvaluation, ...]
    selector_metadata: Mapping[str, Any]
    title: str | None = None
    short_description: str | None = None
    price_minor: int | None = None
    currency: str | None = None
    recommendation_result: RecommendationResult | None = None
    photoshoot_experience: PhotoshootExperienceRecommendation | None = None


def immutable_selector_metadata(
    value: Mapping[str, Any] | None,
) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))

"""Immutable inputs and outputs for side-effect-free Commerce ranking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class RecommendationContext:
    creator_profile_id: int
    active_purchase_intent_offering_id: UUID | None
    evaluated_at: datetime
    requested_media_type: str | None = None
    conversation_id: str | None = None
    current_request: str | None = None
    requested_themes: tuple[str, ...] = ()
    recent_conversation_requests: tuple[str, ...] = ()
    verified_affinity_tags: tuple[str, ...] = ()
    verified_affinity_offering_types: tuple[str, ...] = ()
    recent_offer_history: tuple["RecommendationHistoryEntry", ...] = ()
    commerce_learning_profile: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RecommendationHistoryEntry:
    offering_id: UUID
    offering_type: str
    status: str
    presented_at: datetime | None
    purchased_at: datetime | None = None
    attribution_result: str | None = None
    photoshoot_identifier: str | None = None
    intelligence_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecommendationCandidate:
    offering_id: UUID
    creator_profile_id: int
    title: str
    description: str
    offering_type: str
    price_minor: int
    currency: str
    published_at: datetime | None
    publication_id: UUID
    delivery_url: str
    hero_asset_id: int
    member_asset_ids: tuple[int, ...]
    commercially_eligible: bool = True
    photoshoot_identifier: str | None = None
    intelligence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "intelligence",
            MappingProxyType({
                str(key): tuple(values)
                for key, values in dict(self.intelligence).items()
            }),
        )

    @classmethod
    def from_eligible_projection(cls, value) -> "RecommendationCandidate":
        return cls(
            offering_id=UUID(str(value["offering_id"])),
            creator_profile_id=int(value["creator_profile_id"]),
            title=str(value.get("title") or ""),
            description=str(value.get("description") or ""),
            offering_type=str(value.get("offering_type") or ""),
            price_minor=int(value["price_minor"]),
            currency=str(value.get("currency") or ""),
            published_at=value.get("published_at"),
            publication_id=UUID(str(value["publication_id"])),
            delivery_url=str(value["delivery_url"]),
            hero_asset_id=int(value["hero_asset_id"]),
            member_asset_ids=tuple(int(item) for item in value.get("asset_ids") or ()),
            commercially_eligible=bool(value.get("commercially_eligible", True)),
            photoshoot_identifier=(
                str(value["photoshoot_identifier"])
                if value.get("photoshoot_identifier") else None
            ),
            intelligence={
                str(key): tuple(str(item) for item in items)
                for key, items in dict(
                    value.get("recommendation_intelligence") or {}
                ).items()
            },
        )


@dataclass(frozen=True)
class RecommendationScoreComponent:
    key: str
    raw_value: Any
    ordering_value: Any
    contribution: float
    explanation: str
    affected_ranking: bool
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "evidence", MappingProxyType(dict(self.evidence))
        )


@dataclass(frozen=True)
class RankedRecommendationCandidate:
    rank: int
    candidate: RecommendationCandidate
    components: tuple[RecommendationScoreComponent, ...]
    deterministic_reason: str
    selected: bool
    final_score: float = 0.0


@dataclass(frozen=True)
class RecommendationWeights:
    semantic_match: float = 0.45
    customer_affinity: float = 0.25
    freshness: float = 0.15
    diversification: float = 0.10
    recent_offer_history: float = 0.05

    def __post_init__(self) -> None:
        values = (
            self.semantic_match, self.customer_affinity, self.freshness,
            self.diversification, self.recent_offer_history,
        )
        if any(value < 0 or value > 1 for value in values):
            raise ValueError("Recommendation weights must be between 0 and 1.")
        if abs(sum(values) - 1.0) > 1e-9:
            raise ValueError("Recommendation weights must sum to 1.0.")

    def for_key(self, key: str) -> float:
        try:
            return float(getattr(self, key))
        except AttributeError as error:
            raise KeyError(f"Unknown recommendation weight: {key}") from error


@dataclass(frozen=True)
class RecommendationResult:
    ranked_candidates: tuple[RankedRecommendationCandidate, ...]
    selected_candidate: RecommendationCandidate | None
    selection_reason: str
    engine_version: str
    candidate_count: int
    rejection_count: int | None = None
    recommendation_summary: str | None = None

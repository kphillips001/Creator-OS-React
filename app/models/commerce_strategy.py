"""Provider-neutral Commerce Strategy recommendation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class CommerceStrategyEvidence:
    reason: str
    detail: str | None = None
    weight: int = 0


@dataclass(frozen=True)
class CommerceStrategyRecommendation:
    recommendation_type: str
    source_type: str
    source_id: str | None
    recommended_objective: str | None = None
    customer_journey: CustomerJourneyRecommendation | None = None
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[CommerceStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CustomerJourneyRecommendation:
    journey_stage: str
    recommended_objective: str
    suggested_progression: str
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[CommerceStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommerceStrategyResult:
    source_type: str
    source_id: str | None
    recommendations: tuple[CommerceStrategyRecommendation, ...] = ()
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[CommerceStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

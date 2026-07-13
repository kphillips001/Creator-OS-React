"""Provider-neutral Content Recommendation Engine contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


CONTENT_RECOMMENDATION_SCHEMA_VERSION = (
    "phase_3_10_7_content_recommendation_v1"
)


@dataclass(frozen=True)
class RecommendationRequest:
    """Runtime-neutral request for ranking Chat Ready Business Assets."""

    creator_profile_id: int | None = None
    customer_context: Mapping[str, Any] = field(default_factory=dict)
    conversation_context: Mapping[str, Any] = field(default_factory=dict)
    decision_context: Mapping[str, Any] = field(default_factory=dict)
    business_context: Mapping[str, Any] = field(default_factory=dict)
    product_strategy_context: Mapping[str, Any] = field(default_factory=dict)
    commerce_strategy_context: Mapping[str, Any] = field(default_factory=dict)
    learning_context: Any | None = None
    offer_type: str | None = None
    persona: str | None = None
    limit: int = 10
    candidate_limit: int = 100
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "creator_profile_id": self.creator_profile_id,
            "customer_context": dict(self.customer_context or {}),
            "conversation_context": dict(self.conversation_context or {}),
            "decision_context": dict(self.decision_context or {}),
            "business_context": dict(self.business_context or {}),
            "product_strategy_context": dict(self.product_strategy_context or {}),
            "commerce_strategy_context": dict(self.commerce_strategy_context or {}),
            "offer_type": self.offer_type,
            "persona": self.persona,
            "limit": self.limit,
            "candidate_limit": self.candidate_limit,
            "metadata": dict(self.metadata or {}),
            "schema_version": CONTENT_RECOMMENDATION_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class RecommendationEvidence:
    category: str
    signal: str
    weight: float = 0.0
    value: Any = None
    rationale: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "signal": self.signal,
            "weight": self.weight,
            "value": self.value,
            "rationale": self.rationale,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class RecommendationReason:
    category: str
    rationale: str
    evidence_signals: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "rationale": self.rationale,
            "evidence_signals": self.evidence_signals,
        }


@dataclass(frozen=True)
class RecommendationScore:
    total: float
    customer_fit: float = 0.0
    conversation_fit: float = 0.0
    content_fit: float = 0.0
    business_fit: float = 0.0
    suppression_penalty: float = 0.0
    confidence: float = 0.0

    def to_context(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 3),
            "customer_fit": round(self.customer_fit, 3),
            "conversation_fit": round(self.conversation_fit, 3),
            "content_fit": round(self.content_fit, 3),
            "business_fit": round(self.business_fit, 3),
            "suppression_penalty": round(self.suppression_penalty, 3),
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class RecommendationCandidate:
    asset_id: int
    source_candidate: Any
    score: RecommendationScore
    confidence: float
    evidence: tuple[RecommendationEvidence, ...] = ()
    reasons: tuple[RecommendationReason, ...] = ()
    suppressed: bool = False
    suppression_reasons: tuple[str, ...] = ()
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    media_link: str | None = None
    provider_media_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def recommendation_reason(self) -> str:
        if self.suppressed:
            return "suppressed:" + ",".join(self.suppression_reasons)
        if not self.reasons:
            return "chat_ready_ranked"
        return "; ".join(reason.rationale for reason in self.reasons)

    def to_context(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "score": self.score.to_context(),
            "confidence": round(self.confidence, 3),
            "evidence": tuple(item.to_context() for item in self.evidence),
            "reasons": tuple(item.to_context() for item in self.reasons),
            "suppressed": self.suppressed,
            "suppression_reasons": self.suppression_reasons,
            "product_ids": self.product_ids,
            "experience_ids": self.experience_ids,
            "media_link": self.media_link,
            "provider_media_id": self.provider_media_id,
            "metadata": dict(self.metadata or {}),
        }

    def to_legacy_payload(self, persona: str, offer_type: str) -> dict[str, Any]:
        payload = self.source_candidate.to_legacy_payload(persona, offer_type)
        payload.update(
            {
                "source": "content_recommendation_engine",
                "recommendation_id": self.metadata.get("recommendation_id"),
                "recommendation_reason": self.recommendation_reason,
                "recommendation_score": round(self.score.total, 3),
                "recommendation_confidence": round(self.confidence, 3),
                "recommendation_suppressed": self.suppressed,
                "recommendation_suppression_reasons": list(
                    self.suppression_reasons
                ),
                "recommendation_evidence": [
                    item.to_context() for item in self.evidence
                ],
                "recommendation_metadata": {
                    **dict(payload.get("recommendation_metadata") or {}),
                    **dict(self.metadata or {}),
                    "score": self.score.to_context(),
                    "reasons": [item.to_context() for item in self.reasons],
                    "engine": "ContentRecommendationService",
                },
            }
        )
        return payload


@dataclass(frozen=True)
class RecommendationResult:
    request: RecommendationRequest
    ranked_assets: tuple[RecommendationCandidate, ...] = ()
    rejected_candidates: tuple[RecommendationCandidate, ...] = ()
    confidence: float = 0.0
    supporting_evidence: tuple[RecommendationEvidence, ...] = ()
    business_rationale: tuple[str, ...] = ()
    customer_rationale: tuple[str, ...] = ()
    content_rationale: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def top_candidate(self) -> RecommendationCandidate | None:
        return self.ranked_assets[0] if self.ranked_assets else None

    @property
    def all_candidates(self) -> tuple[RecommendationCandidate, ...]:
        return self.ranked_assets + self.rejected_candidates

    def to_context(self) -> dict[str, Any]:
        return {
            "request": self.request.to_context(),
            "ranked_assets": tuple(item.to_context() for item in self.ranked_assets),
            "rejected_candidates": tuple(
                item.to_context() for item in self.rejected_candidates
            ),
            "confidence": round(self.confidence, 3),
            "supporting_evidence": tuple(
                item.to_context() for item in self.supporting_evidence
            ),
            "business_rationale": self.business_rationale,
            "customer_rationale": self.customer_rationale,
            "content_rationale": self.content_rationale,
            "metadata": dict(self.metadata or {}),
            "schema_version": CONTENT_RECOMMENDATION_SCHEMA_VERSION,
        }

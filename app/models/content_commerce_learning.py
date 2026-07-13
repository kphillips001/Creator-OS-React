"""Content commerce learning contracts.

These provider-neutral records connect recommendation, delivery, and commerce
outcomes to the existing Business Learning boundary. They are compact ledger
entries, not duplicate intelligence payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, uuid5


CONTENT_COMMERCE_LEARNING_SCHEMA_VERSION = (
    "phase_3_10_11_content_commerce_learning_v1"
)


class RecommendationEventState(str, Enum):
    GENERATED = "GENERATED"
    SELECTED = "SELECTED"
    PRESENTED = "PRESENTED"
    OFFERED = "OFFERED"
    DELIVERED = "DELIVERED"
    PURCHASED = "PURCHASED"
    DECLINED = "DECLINED"
    IGNORED = "IGNORED"
    SUPPRESSED = "SUPPRESSED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    DELIVERY_PREPARED = "DELIVERY_PREPARED"
    DELIVERY_BLOCKED = "DELIVERY_BLOCKED"
    DELIVERY_FAILED = "DELIVERY_FAILED"
    RETRIED = "RETRIED"
    REFUNDED = "REFUNDED"
    UNMATCHED = "UNMATCHED"
    LEARNING_FAILED = "LEARNING_FAILED"


@dataclass(frozen=True)
class RecommendationEvent:
    event_id: str
    recommendation_id: str | None
    event_state: str
    event_timestamp: str | None = None
    asset_id: int | None = None
    business_registration_id: str | None = None
    chat_registration_id: str | None = None
    fulfillment_registration_id: str | None = None
    delivery_id: str | None = None
    product_id: str | None = None
    experience_id: str | None = None
    customer_id: str | None = None
    conversation_id: str | None = None
    provider: str | None = None
    recommendation_score: float | None = None
    recommendation_confidence: float | None = None
    recommendation_rationale: tuple[str, ...] = ()
    score_breakdown: Mapping[str, Any] = field(default_factory=dict)
    supporting_evidence: tuple[Mapping[str, Any], ...] = ()
    suppression_reasons: tuple[str, ...] = ()
    rejected_candidate_reasons: tuple[str, ...] = ()
    conversation_context_reference: str | None = None
    customer_intelligence_reference: str | None = None
    content_intelligence_reference: str | None = None
    business_learning_context_reference: str | None = None
    outcome_metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = CONTENT_COMMERCE_LEARNING_SCHEMA_VERSION

    @staticmethod
    def deterministic_id(
        *,
        recommendation_id: str | None,
        event_state: str,
        asset_id: int | str | None = None,
        delivery_id: str | None = None,
        provider_transaction_id: str | None = None,
    ) -> str:
        key = "|".join(
            (
                str(recommendation_id or ""),
                str(event_state or ""),
                str(asset_id or ""),
                str(delivery_id or ""),
                str(provider_transaction_id or ""),
            )
        )
        return str(uuid5(NAMESPACE_URL, f"creator-os:recommendation-event:{key}"))

    def to_context(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "recommendation_id": self.recommendation_id,
            "event_state": self.event_state,
            "event_timestamp": self.event_timestamp,
            "asset_id": self.asset_id,
            "business_registration_id": self.business_registration_id,
            "chat_registration_id": self.chat_registration_id,
            "fulfillment_registration_id": self.fulfillment_registration_id,
            "delivery_id": self.delivery_id,
            "product_id": self.product_id,
            "experience_id": self.experience_id,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation_id,
            "provider": self.provider,
            "recommendation_score": self.recommendation_score,
            "recommendation_confidence": self.recommendation_confidence,
            "recommendation_rationale": list(self.recommendation_rationale),
            "score_breakdown": dict(self.score_breakdown or {}),
            "supporting_evidence": [
                dict(item or {}) for item in self.supporting_evidence
            ],
            "suppression_reasons": list(self.suppression_reasons),
            "rejected_candidate_reasons": list(self.rejected_candidate_reasons),
            "conversation_context_reference": self.conversation_context_reference,
            "customer_intelligence_reference": self.customer_intelligence_reference,
            "content_intelligence_reference": self.content_intelligence_reference,
            "business_learning_context_reference": (
                self.business_learning_context_reference
            ),
            "outcome_metadata": dict(self.outcome_metadata or {}),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class AssetLearningProfile:
    asset_id: int
    recommendation_count: int = 0
    offer_count: int = 0
    delivery_count: int = 0
    purchase_count: int = 0
    refund_count: int = 0
    suppressed_count: int = 0
    rejected_count: int = 0
    delivery_failure_count: int = 0
    retry_count: int = 0
    gross_revenue_cents: int = 0
    tip_cents: int = 0
    refund_cents: int = 0
    net_revenue_cents: int = 0
    conversion_rate: float | None = None
    delivery_to_purchase_conversion: float | None = None
    average_revenue_per_recommendation_cents: float | None = None
    average_revenue_per_delivery_cents: float | None = None
    average_purchase_delay_seconds: float | None = None
    confidence: float = 0.0
    sample_size: int = 0
    score: float = 0.0
    evidence_freshness: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "recommendation_count": self.recommendation_count,
            "offer_count": self.offer_count,
            "delivery_count": self.delivery_count,
            "purchase_count": self.purchase_count,
            "refund_count": self.refund_count,
            "suppressed_count": self.suppressed_count,
            "rejected_count": self.rejected_count,
            "delivery_failure_count": self.delivery_failure_count,
            "retry_count": self.retry_count,
            "gross_revenue_cents": self.gross_revenue_cents,
            "tip_cents": self.tip_cents,
            "refund_cents": self.refund_cents,
            "net_revenue_cents": self.net_revenue_cents,
            "conversion_rate": self.conversion_rate,
            "delivery_to_purchase_conversion": self.delivery_to_purchase_conversion,
            "average_revenue_per_recommendation_cents": (
                self.average_revenue_per_recommendation_cents
            ),
            "average_revenue_per_delivery_cents": (
                self.average_revenue_per_delivery_cents
            ),
            "average_purchase_delay_seconds": self.average_purchase_delay_seconds,
            "confidence": self.confidence,
            "sample_size": self.sample_size,
            "score": self.score,
            "evidence_freshness": self.evidence_freshness,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class RuntimeLearningContext:
    context_id: str
    asset_scores: Mapping[str, float] = field(default_factory=dict)
    asset_profiles: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    product_scores: Mapping[str, float] = field(default_factory=dict)
    experience_scores: Mapping[str, float] = field(default_factory=dict)
    customer_evidence: Mapping[str, Any] = field(default_factory=dict)
    cohort_evidence: Mapping[str, Any] = field(default_factory=dict)
    business_priorities: tuple[str, ...] = ()
    top_performers: tuple[str, ...] = ()
    underperformers: tuple[str, ...] = ()
    suppression_evidence: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "asset_scores": dict(self.asset_scores or {}),
            "asset_profiles": {
                str(key): dict(value or {})
                for key, value in (self.asset_profiles or {}).items()
            },
            "product_scores": dict(self.product_scores or {}),
            "experience_scores": dict(self.experience_scores or {}),
            "customer_evidence": dict(self.customer_evidence or {}),
            "cohort_evidence": dict(self.cohort_evidence or {}),
            "business_priorities": list(self.business_priorities),
            "top_performers": list(self.top_performers),
            "underperformers": list(self.underperformers),
            "suppression_evidence": dict(self.suppression_evidence or {}),
            "metadata": dict(self.metadata or {}),
            "schema_version": CONTENT_COMMERCE_LEARNING_SCHEMA_VERSION,
        }

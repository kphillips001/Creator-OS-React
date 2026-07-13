"""Provider-neutral Commerce Outcome Synchronization contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.business_learning import BusinessOutcome, BusinessOutcomeType


COMMERCE_OUTCOME_SCHEMA_VERSION = "phase_3_10_10_commerce_outcome_v1"


class CommerceOutcomeStatus(str, Enum):
    RECEIVED = "RECEIVED"
    SYNCHRONIZED = "SYNCHRONIZED"
    DUPLICATE = "DUPLICATE"
    UNMATCHED = "UNMATCHED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PurchaseStatus(str, Enum):
    PURCHASED = "PURCHASED"
    PAID = "PAID"
    PENDING = "PENDING"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PurchaseOutcome:
    provider_transaction_id: str | None
    purchase_status: PurchaseStatus = PurchaseStatus.UNKNOWN
    purchased_at: str | None = None
    currency: str = "USD"
    gross_revenue_cents: int = 0
    tip_cents: int = 0
    refund_cents: int = 0
    fee_cents: int = 0
    net_revenue_cents: int = 0
    provider_media_uuid: str | None = None
    provider_customer_id: str | None = None
    provider_account_id: str | None = None
    provider_raw_status: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "provider_transaction_id": self.provider_transaction_id,
            "purchase_status": self.purchase_status.value,
            "purchased_at": self.purchased_at,
            "currency": self.currency,
            "gross_revenue_cents": self.gross_revenue_cents,
            "tip_cents": self.tip_cents,
            "refund_cents": self.refund_cents,
            "fee_cents": self.fee_cents,
            "net_revenue_cents": self.net_revenue_cents,
            "provider_media_uuid": self.provider_media_uuid,
            "provider_customer_id": self.provider_customer_id,
            "provider_account_id": self.provider_account_id,
            "provider_raw_status": self.provider_raw_status,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class RecommendationOutcome:
    recommendation_id: str | None = None
    delivery_id: str | None = None
    recommended: bool = False
    delivered: bool = False
    purchased: bool = False
    revenue_cents: int = 0
    success: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "delivery_id": self.delivery_id,
            "recommended": self.recommended,
            "delivered": self.delivered,
            "purchased": self.purchased,
            "revenue_cents": self.revenue_cents,
            "success": self.success,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class RevenueAttribution:
    recommendation_id: str | None = None
    delivery_id: str | None = None
    asset_id: int | None = None
    business_asset_id: int | None = None
    product_id: str | None = None
    experience_id: str | None = None
    customer_id: str | None = None
    conversation_id: str | None = None
    provider_media_uuid: str | None = None
    matched_by: str | None = None
    confidence: float = 0.0
    unresolved_fields: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def matched(self) -> bool:
        return not self.unresolved_fields

    def to_context(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "delivery_id": self.delivery_id,
            "asset_id": self.asset_id,
            "business_asset_id": self.business_asset_id,
            "product_id": self.product_id,
            "experience_id": self.experience_id,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation_id,
            "provider_media_uuid": self.provider_media_uuid,
            "matched_by": self.matched_by,
            "confidence": round(float(self.confidence or 0.0), 3),
            "unresolved_fields": list(self.unresolved_fields),
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class CommerceOutcome:
    outcome_id: UUID
    provider: str
    purchase: PurchaseOutcome
    attribution: RevenueAttribution
    recommendation_outcome: RecommendationOutcome
    status: CommerceOutcomeStatus = CommerceOutcomeStatus.RECEIVED
    source: str | None = None
    received_at: str | None = None
    synchronized_at: str | None = None
    failure_reason: str | None = None
    raw_payload: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = COMMERCE_OUTCOME_SCHEMA_VERSION

    @classmethod
    def deterministic_id(
        cls,
        *,
        provider: str,
        provider_transaction_id: str | None,
    ) -> UUID:
        key = provider_transaction_id or "missing-transaction"
        return uuid5(
            NAMESPACE_URL,
            f"creator-os:commerce-outcome:{provider}:{key}",
        )

    def to_context(self) -> dict[str, Any]:
        return {
            "outcome_id": str(self.outcome_id),
            "provider": self.provider,
            "purchase": self.purchase.to_context(),
            "attribution": self.attribution.to_context(),
            "recommendation_outcome": self.recommendation_outcome.to_context(),
            "status": self.status.value,
            "source": self.source,
            "received_at": self.received_at,
            "synchronized_at": self.synchronized_at,
            "failure_reason": self.failure_reason,
            "raw_payload": dict(self.raw_payload or {}),
            "schema_version": self.schema_version,
        }

    def to_business_outcome(self) -> BusinessOutcome:
        outcome_type = (
            "PRODUCT_REFUNDED"
            if self.status == CommerceOutcomeStatus.REFUNDED
            or self.purchase.refund_cents > 0
            else BusinessOutcomeType.PRODUCT_PURCHASED.value
        )
        return BusinessOutcome(
            outcome_id=str(self.outcome_id),
            outcome_type=outcome_type,
            timestamp=self.purchase.purchased_at or self.received_at,
            subject_type="asset" if self.attribution.asset_id else "commerce",
            subject_id=(
                str(self.attribution.asset_id)
                if self.attribution.asset_id is not None
                else self.purchase.provider_transaction_id
            ),
            customer_id=self.attribution.customer_id,
            customer_reference=self.purchase.provider_customer_id,
            product_id=self.attribution.product_id,
            product_reference=self.attribution.product_id,
            experience_id=self.attribution.experience_id,
            experience_reference=self.attribution.experience_id,
            recommendation_id=self.attribution.recommendation_id,
            status=self.status.value,
            value_cents=self.purchase.net_revenue_cents,
            occurred_at=self.purchase.purchased_at or self.received_at,
            provider_metadata={
                "provider": self.provider,
                "provider_transaction_id": self.purchase.provider_transaction_id,
                "provider_media_uuid": self.purchase.provider_media_uuid,
                "delivery_id": self.attribution.delivery_id,
                "asset_id": self.attribution.asset_id,
                "business_asset_id": self.attribution.business_asset_id,
                "conversation_id": self.attribution.conversation_id,
                "gross_revenue_cents": self.purchase.gross_revenue_cents,
                "tip_cents": self.purchase.tip_cents,
                "refund_cents": self.purchase.refund_cents,
                "currency": self.purchase.currency,
            },
            metadata={
                "source": "CommerceOutcomeSynchronizationService",
                "schema_version": self.schema_version,
                "attribution": self.attribution.to_context(),
            },
        )


@dataclass(frozen=True)
class CommerceOutcomeRequest:
    provider_payload: Mapping[str, Any]
    provider: str = "fanvue"
    source: str = "provider"
    provider_account_id: str | int | None = None
    received_at: str | None = None
    idempotency_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "provider_payload": dict(self.provider_payload or {}),
            "provider": self.provider,
            "source": self.source,
            "provider_account_id": self.provider_account_id,
            "received_at": self.received_at,
            "idempotency_key": self.idempotency_key,
            "metadata": dict(self.metadata or {}),
            "schema_version": COMMERCE_OUTCOME_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class CommerceOutcomeResult:
    success: bool
    outcome: CommerceOutcome | None = None
    duplicate: bool = False
    retryable: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    business_learning_result: Any | None = None
    customer_history_result: Any | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "outcome": self.outcome.to_context() if self.outcome else None,
            "duplicate": self.duplicate,
            "retryable": self.retryable,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "business_learning_result": self.business_learning_result,
            "customer_history_result": self.customer_history_result,
            "metadata": dict(self.metadata or {}),
            "schema_version": COMMERCE_OUTCOME_SCHEMA_VERSION,
        }


def utc_now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

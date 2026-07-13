"""Provider-neutral Chat Commerce Delivery contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5


CHAT_COMMERCE_DELIVERY_SCHEMA_VERSION = "phase_3_10_8_chat_commerce_delivery_v1"


class ChatDeliveryStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    DELIVERED = "DELIVERED"
    RETRY_REQUIRED = "RETRY_REQUIRED"


@dataclass(frozen=True)
class DeliveryEvidence:
    category: str
    signal: str
    value: Any = None
    rationale: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "signal": self.signal,
            "value": self.value,
            "rationale": self.rationale,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class DeliveryValidation:
    valid: bool
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    retryable: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "retryable": self.retryable,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class DeliveryPayload:
    delivery_id: UUID
    asset_id: int
    chat_registration_id: UUID | str | None = None
    fulfillment_id: UUID | str | None = None
    product_id: str | None = None
    experience_id: str | None = None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    fanvue_media_link: str | None = None
    provider_media_uuid: str | None = None
    provider: str | None = None
    customer_id: str | None = None
    conversation_id: str | None = None
    recommendation_id: str | None = None
    delivery_type: str | None = "PAID"
    delivery_method: str | None = "paid_media_link"
    delivery_ready: bool = False
    readiness: Mapping[str, Any] = field(default_factory=dict)
    payload_version: str = CHAT_COMMERCE_DELIVERY_SCHEMA_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "delivery_id": str(self.delivery_id),
            "asset_id": self.asset_id,
            "chat_registration_id": (
                str(self.chat_registration_id)
                if self.chat_registration_id is not None
                else None
            ),
            "fulfillment_id": (
                str(self.fulfillment_id) if self.fulfillment_id is not None else None
            ),
            "product_id": self.product_id,
            "experience_id": self.experience_id,
            "product_ids": list(self.product_ids),
            "experience_ids": list(self.experience_ids),
            "fanvue_media_link": self.fanvue_media_link,
            "media_link": self.fanvue_media_link,
            "provider_media_uuid": self.provider_media_uuid,
            "provider_media_id": self.provider_media_uuid,
            "provider": self.provider,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation_id,
            "recommendation_id": self.recommendation_id,
            "delivery_type": self.delivery_type,
            "delivery_method": self.delivery_method,
            "delivery_ready": self.delivery_ready,
            "readiness": dict(self.readiness or {}),
            "payload_version": self.payload_version,
            "metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class ChatDeliveryRequest:
    asset_id: int
    recommendation: Any | None = None
    recommendation_id: str | None = None
    customer_context: Mapping[str, Any] = field(default_factory=dict)
    conversation_context: Mapping[str, Any] = field(default_factory=dict)
    decision_context: Mapping[str, Any] = field(default_factory=dict)
    provider: str = "telegram"
    customer_id: str | None = None
    conversation_id: str | None = None
    idempotency_key: str | None = None
    retry_of_delivery_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def delivery_id(self) -> UUID:
        key = self.idempotency_key or "|".join(
            (
                str(self.asset_id),
                str(self.customer_id or self.customer_context.get("customer_id") or ""),
                str(self.conversation_id or ""),
                str(self.recommendation_id or self._recommendation_id_hint() or ""),
            )
        )
        return uuid5(NAMESPACE_URL, f"creator-os:chat-commerce-delivery:{key}")

    def _recommendation_id_hint(self) -> str | None:
        if isinstance(self.recommendation, Mapping):
            metadata = self.recommendation.get("recommendation_metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            value = (
                self.recommendation.get("recommendation_id")
                or metadata.get("recommendation_id")
            )
            return str(value) if value is not None else None
        return None

    def to_context(self) -> dict[str, Any]:
        return {
            "delivery_id": str(self.delivery_id),
            "asset_id": self.asset_id,
            "recommendation_id": self.recommendation_id
            or self._recommendation_id_hint(),
            "customer_context": dict(self.customer_context or {}),
            "conversation_context": dict(self.conversation_context or {}),
            "decision_context": dict(self.decision_context or {}),
            "provider": self.provider,
            "customer_id": self.customer_id,
            "conversation_id": self.conversation_id,
            "idempotency_key": self.idempotency_key,
            "retry_of_delivery_id": self.retry_of_delivery_id,
            "metadata": dict(self.metadata or {}),
            "schema_version": CHAT_COMMERCE_DELIVERY_SCHEMA_VERSION,
        }


@dataclass(frozen=True)
class ChatDeliveryResult:
    success: bool
    status: ChatDeliveryStatus
    request: ChatDeliveryRequest
    payload: DeliveryPayload | None = None
    validation: DeliveryValidation = field(
        default_factory=lambda: DeliveryValidation(valid=False)
    )
    evidence: tuple[DeliveryEvidence, ...] = ()
    failure_reason: str | None = None
    retryable: bool = False
    created_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def delivery_id(self) -> UUID:
        return self.request.delivery_id

    def to_context(self) -> dict[str, Any]:
        return {
            "delivery_id": str(self.delivery_id),
            "success": self.success,
            "status": self.status.value,
            "request": self.request.to_context(),
            "payload": self.payload.to_context() if self.payload else None,
            "validation": self.validation.to_context(),
            "evidence": [item.to_context() for item in self.evidence],
            "failure_reason": self.failure_reason,
            "retryable": self.retryable,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": dict(self.metadata or {}),
            "schema_version": CHAT_COMMERCE_DELIVERY_SCHEMA_VERSION,
        }

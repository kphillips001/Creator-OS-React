"""Deterministic lifecycle state for one presented commercial offering."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class PurchaseIntentStatus(str, Enum):
    CREATED = "CREATED"
    PRESENTED = "PRESENTED"
    CLICKED = "CLICKED"
    PURCHASED = "PURCHASED"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    UNKNOWN = "UNKNOWN"
    SUPERSEDED = "SUPERSEDED"
    ADMIN_CLOSED = "ADMIN_CLOSED"


class AttributionResult(str, Enum):
    PENDING = "PENDING"
    ATTRIBUTED = "ATTRIBUTED"
    UNKNOWN = "UNKNOWN"


ACTIVE_PURCHASE_INTENT_STATUSES = frozenset({
    PurchaseIntentStatus.CREATED,
    PurchaseIntentStatus.PRESENTED,
    PurchaseIntentStatus.CLICKED,
})


@dataclass(frozen=True)
class PurchaseIntent:
    purchase_intent_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    telegram_identity_mapping_id: int | None
    telegram_user_id: int
    telegram_chat_id: int
    external_fanvue_user_uuid: UUID | None
    commercial_offering_id: UUID
    commercial_publication_id: UUID
    provider: str
    provider_resource_id: str
    delivery_url: str
    telegram_message_id: int | None
    conversation_id: str | None
    correlation_id: UUID
    expected_price_minor: int
    expected_currency: str
    status: PurchaseIntentStatus
    created_at: datetime
    presented_at: datetime | None
    clicked_at: datetime | None
    expires_at: datetime
    abandoned_at: datetime | None
    purchased_at: datetime | None
    provider_transaction_order_id: str | None
    provider_payment_id: str | None
    provider_event_id: str | None
    attribution_result: AttributionResult
    attribution_reason: str | None
    created_metadata: dict[str, Any]
    updated_at: datetime
    purchase_acknowledged_at: datetime | None = None
    configured_base_price_minor: int | None = None
    actual_charged_price_minor: int | None = None
    identity_bootstrap_mode: str = "NONE"
    admin_closed_at: datetime | None = None
    administrative_close_reason: str | None = None


@dataclass(frozen=True)
class PurchaseIntentStatistics:
    total: int
    active: int
    purchased: int
    expired: int
    abandoned: int
    unknown: int
    superseded: int

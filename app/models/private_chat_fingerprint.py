"""Durable private-chat first-purchase identity bootstrap contracts."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class FingerprintReservationState(str, Enum):
    RESERVED = "RESERVED"
    ACTIVE = "ACTIVE"
    PURCHASED = "PURCHASED"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    RETIRED = "RETIRED"
    FAILED = "FAILED"
    UNCERTAIN = "UNCERTAIN"


class RuntimeMediaLinkState(str, Enum):
    PENDING_CREATE = "PENDING_CREATE"
    CREATING = "CREATING"
    ACTIVE = "ACTIVE"
    PURCHASED = "PURCHASED"
    EXPIRED = "EXPIRED"
    DELETE_REQUESTED = "DELETE_REQUESTED"
    DELETED = "DELETED"
    DELETE_FAILED = "DELETE_FAILED"
    ORPHANED = "ORPHANED"
    UNCERTAIN = "UNCERTAIN"
    CREATE_FAILED = "CREATE_FAILED"


@dataclass(frozen=True)
class UnlockGrant:
    unlock_grant_id: UUID
    purchase_intent_id: UUID
    telegram_user_id: int
    telegram_chat_id: int
    commercial_offering_id: UUID
    commercial_publication_id: UUID
    fanvue_account_id: int
    currency: str
    state: str
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None
    use_count: int = 0
    audit_metadata: dict[str, Any] = field(default_factory=dict)
    public_alias_hash: str | None = None
    public_alias_generation: int | None = None


@dataclass(frozen=True)
class FingerprintReservation:
    fingerprint_reservation_id: UUID
    fanvue_account_id: int
    currency: str
    exact_price_minor: int
    configured_base_price_minor: int
    purchase_intent_id: UUID
    telegram_user_id: int
    state: FingerprintReservationState
    created_at: datetime
    activated_at: datetime | None = None
    purchased_at: datetime | None = None
    expired_at: datetime | None = None
    retired_at: datetime | None = None
    provider_transaction_reference: str | None = None
    recovery_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeMediaLink:
    runtime_media_link_id: UUID
    purchase_intent_id: UUID
    fingerprint_reservation_id: UUID
    provider_media_link_uuid: str | None
    provider_url: str | None
    state: RuntimeMediaLinkState
    creation_operation_key: UUID
    created_at: datetime
    expires_at: datetime
    deleted_at: datetime | None = None
    last_attempt_at: datetime | None = None
    attempt_count: int = 0
    last_error: str | None = None
    reconciliation_metadata: dict[str, Any] = field(default_factory=dict)

"""Provider-neutral customer entitlement model."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class EntitlementStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    EXPIRED = "expired"
    REVOKED = "revoked"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"


class EntitlementSourceType(str, Enum):
    PURCHASE = "purchase"
    PPV_UNLOCK = "ppv_unlock"
    SUBSCRIPTION = "subscription"
    PROMOTION = "promotion"
    MANUAL_GRANT = "manual_grant"
    CUSTOM_FULFILLMENT = "custom_fulfillment"


@dataclass(frozen=True)
class CustomerEntitlement:
    id: UUID
    core_user_id: UUID | None
    legacy_fanvue_account_id: int | None
    legacy_fanvue_user_id: str | None
    product_id: UUID
    status: EntitlementStatus
    source_type: EntitlementSourceType
    commerce_provider: str | None
    provider_transaction_id: str | None
    provider_event_id: str | None
    granted_at: datetime
    valid_from: datetime
    expires_at: datetime | None
    fulfilled_at: datetime | None
    revoked_at: datetime | None
    revocation_reason: str | None
    metadata: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "CustomerEntitlement":
        return cls(
            id=row["id"],
            core_user_id=row.get("core_user_id"),
            legacy_fanvue_account_id=row.get("legacy_fanvue_account_id"),
            legacy_fanvue_user_id=row.get("legacy_fanvue_user_id"),
            product_id=row["product_id"],
            status=EntitlementStatus(row["status"]),
            source_type=EntitlementSourceType(row["source_type"]),
            commerce_provider=row.get("commerce_provider"),
            provider_transaction_id=row.get("provider_transaction_id"),
            provider_event_id=row.get("provider_event_id"),
            granted_at=row["granted_at"],
            valid_from=row["valid_from"],
            expires_at=row.get("expires_at"),
            fulfilled_at=row.get("fulfilled_at"),
            revoked_at=row.get("revoked_at"),
            revocation_reason=row.get("revocation_reason"),
            metadata=row.get("metadata") or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

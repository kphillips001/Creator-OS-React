"""Chat Commerce Registration contracts for fulfilled Business Assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5


CHAT_COMMERCE_REGISTRATION_SCHEMA_VERSION = (
    "phase_3_10_6_chat_commerce_registration_v1"
)


class ChatAvailabilityState(str, Enum):
    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    CHAT_READY = "CHAT_READY"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    RETIRED = "RETIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class ChatEligibility:
    chat_ready: bool
    fulfillment_ready: bool
    recommendation_eligible: bool
    delivery_eligible: bool
    destination_valid: bool
    product_prerequisites_satisfied: bool = True
    temporarily_unavailable: bool = False
    retired: bool = False
    block_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "chat_ready": self.chat_ready,
            "fulfillment_ready": self.fulfillment_ready,
            "recommendation_eligible": self.recommendation_eligible,
            "delivery_eligible": self.delivery_eligible,
            "destination_valid": self.destination_valid,
            "product_prerequisites_satisfied": (
                self.product_prerequisites_satisfied
            ),
            "temporarily_unavailable": self.temporarily_unavailable,
            "retired": self.retired,
            "block_reasons": list(self.block_reasons),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata or {}),
            "source": "ChatCommerceRegistrationService",
        }


@dataclass(frozen=True)
class ChatCommerceRegistrationRequest:
    asset_id: int
    registration_id: UUID | str
    fulfillment_id: UUID | str
    commerce_destination: str | None
    creator_profile_id: int | None = None
    source_workflow: str | None = None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    creator_note: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ChatCommerceAssetRecord:
    chat_registration_id: UUID
    asset_id: int
    registration_id: UUID
    fulfillment_id: UUID
    creator_profile_id: int | None
    commerce_destination: str | None
    availability_state: ChatAvailabilityState
    chat_ready: bool
    fulfillment_ready: bool
    recommendation_eligible: bool
    delivery_eligible: bool
    active: bool = True
    temporarily_unavailable: bool = False
    retired: bool = False
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    source_workflow: str | None = None
    media_link: str | None = None
    provider_media_id: str | None = None
    provider: str | None = None
    registered_at: datetime | None = None
    chat_ready_at: datetime | None = None
    temporarily_unavailable_at: datetime | None = None
    retired_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    registration_provenance: Mapping[str, Any] = field(default_factory=dict)
    block_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: str = CHAT_COMMERCE_REGISTRATION_SCHEMA_VERSION

    @classmethod
    def deterministic_id(cls, asset_id: int) -> UUID:
        return uuid5(
            NAMESPACE_URL,
            f"creator-os:chat-commerce-registration:{int(asset_id)}",
        )

    @property
    def eligibility(self) -> ChatEligibility:
        return ChatEligibility(
            chat_ready=self.chat_ready
            and self.availability_state == ChatAvailabilityState.CHAT_READY,
            fulfillment_ready=self.fulfillment_ready,
            recommendation_eligible=self.recommendation_eligible,
            delivery_eligible=self.delivery_eligible,
            destination_valid="invalid_destination" not in self.block_reasons,
            temporarily_unavailable=self.temporarily_unavailable,
            retired=self.retired,
            block_reasons=self.block_reasons,
            warnings=self.warnings,
            metadata={
                "chat_registration_id": str(self.chat_registration_id),
                "asset_id": self.asset_id,
                "registration_id": str(self.registration_id),
                "fulfillment_id": str(self.fulfillment_id),
                "availability_state": self.availability_state.value,
                "product_ids": list(self.product_ids),
                "experience_ids": list(self.experience_ids),
            },
        )

    def to_context(self) -> dict[str, Any]:
        return {
            "chat_registration_id": str(self.chat_registration_id),
            "asset_id": self.asset_id,
            "registration_id": str(self.registration_id),
            "fulfillment_id": str(self.fulfillment_id),
            "creator_profile_id": self.creator_profile_id,
            "commerce_destination": self.commerce_destination,
            "availability_state": self.availability_state.value,
            "chat_ready": self.chat_ready,
            "fulfillment_ready": self.fulfillment_ready,
            "recommendation_eligible": self.recommendation_eligible,
            "delivery_eligible": self.delivery_eligible,
            "active": self.active,
            "temporarily_unavailable": self.temporarily_unavailable,
            "retired": self.retired,
            "product_ids": list(self.product_ids),
            "experience_ids": list(self.experience_ids),
            "source_workflow": self.source_workflow,
            "media_link": self.media_link,
            "provider_media_id": self.provider_media_id,
            "provider": self.provider,
            "registered_at": _datetime_context(self.registered_at),
            "chat_ready_at": _datetime_context(self.chat_ready_at),
            "temporarily_unavailable_at": _datetime_context(
                self.temporarily_unavailable_at
            ),
            "retired_at": _datetime_context(self.retired_at),
            "last_refreshed_at": _datetime_context(self.last_refreshed_at),
            "registration_provenance": dict(self.registration_provenance or {}),
            "block_reasons": list(self.block_reasons),
            "warnings": list(self.warnings),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": _datetime_context(self.created_at),
            "updated_at": _datetime_context(self.updated_at),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ChatInventoryCandidate:
    asset_id: int
    chat_registration_id: UUID
    creator_profile_id: int | None
    media_link: str | None
    provider_media_id: str | None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    recommendation_eligible: bool = True
    delivery_eligible: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_record(cls, record: ChatCommerceAssetRecord) -> "ChatInventoryCandidate":
        return cls(
            asset_id=record.asset_id,
            chat_registration_id=record.chat_registration_id,
            creator_profile_id=record.creator_profile_id,
            media_link=record.media_link,
            provider_media_id=record.provider_media_id,
            product_ids=record.product_ids,
            experience_ids=record.experience_ids,
            recommendation_eligible=record.recommendation_eligible,
            delivery_eligible=record.delivery_eligible,
            metadata={
                "source": "ChatCommerceInventory",
                "availability_state": record.availability_state.value,
                "commerce_destination": record.commerce_destination,
            },
        )

    def to_legacy_payload(self, persona: str, offer_type: str) -> dict[str, Any]:
        return {
            "id": self.asset_id,
            "content_item_id": self.asset_id,
            "asset_id": self.asset_id,
            "chat_registration_id": str(self.chat_registration_id),
            "product_id": self.product_ids[0] if self.product_ids else None,
            "tag": f"chat_asset_{self.asset_id}",
            "type": offer_type,
            "tier": "chat_ready",
            "price": 0,
            "caption": None,
            "checkout_url": self.media_link,
            "fanvue_link": self.media_link,
            "persona": persona,
            "classification": str(offer_type or "chat").upper(),
            "file_path": None,
            "file_name": f"Asset {self.asset_id}",
            "source": "chat_commerce_inventory",
            "recommendation_reason": "chat_ready_inventory",
            "recommendation_score": 0,
            "delivery_type": "PAID" if self.media_link else None,
            "delivery_permission_mode": "paid" if self.media_link else None,
            "delivery_allowed": self.delivery_eligible,
            "delivery_requires_payment": bool(self.media_link),
            "chat_ready": True,
            "canonical_asset_id": self.asset_id,
            "product_ids": list(self.product_ids),
            "experience_ids": list(self.experience_ids),
            "chat_inventory_metadata": dict(self.metadata or {}),
        }


@dataclass(frozen=True)
class ChatCommerceRegistrationResult:
    success: bool
    asset_id: int
    chat_registration_id: UUID | None = None
    availability_state: ChatAvailabilityState | None = None
    chat_ready: bool = False
    fulfillment_ready: bool = False
    recommendation_eligible: bool = False
    delivery_eligible: bool = False
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    block_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    record: ChatCommerceAssetRecord | None = None

    @classmethod
    def from_record(
        cls,
        record: ChatCommerceAssetRecord,
        *,
        success: bool | None = None,
        errors: tuple[str, ...] = (),
    ) -> "ChatCommerceRegistrationResult":
        return cls(
            success=record.chat_ready if success is None else success,
            asset_id=record.asset_id,
            chat_registration_id=record.chat_registration_id,
            availability_state=record.availability_state,
            chat_ready=record.chat_ready,
            fulfillment_ready=record.fulfillment_ready,
            recommendation_eligible=record.recommendation_eligible,
            delivery_eligible=record.delivery_eligible,
            product_ids=record.product_ids,
            experience_ids=record.experience_ids,
            block_reasons=record.block_reasons,
            warnings=record.warnings,
            errors=errors,
            record=record,
        )


def _datetime_context(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

"""Durable Commerce Registration contracts for canonical Assets."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, NAMESPACE_URL, uuid5


COMMERCE_REGISTRATION_SCHEMA_VERSION = "phase_3_10_3_commerce_registration_v1"


class CommerceRegistrationStatus(str, Enum):
    PENDING = "PENDING"
    REGISTERED = "REGISTERED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    RETIRED = "RETIRED"


class BusinessAssetLifecycleState(str, Enum):
    APPROVED = "APPROVED"
    INTELLIGENCE_PENDING = "INTELLIGENCE_PENDING"
    INTELLIGENCE_READY = "INTELLIGENCE_READY"
    COMMERCE_REGISTERED = "COMMERCE_REGISTERED"
    AWAITING_DESTINATION = "AWAITING_DESTINATION"
    DESTINATION_SELECTED = "DESTINATION_SELECTED"
    ROUTING_PENDING = "ROUTING_PENDING"
    ROUTED = "ROUTED"
    ROUTING_FAILED = "ROUTING_FAILED"
    PUBLISHING_READY = "PUBLISHING_READY"
    AWAITING_UPLOAD = "AWAITING_UPLOAD"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    FULFILLMENT_READY = "FULFILLMENT_READY"
    CHAT_READY = "CHAT_READY"
    RETIRED = "RETIRED"


class CommerceDestinationStatus(str, Enum):
    NOT_READY = "NOT_READY"
    AWAITING_DESTINATION = "AWAITING_DESTINATION"
    DESTINATION_SELECTED = "DESTINATION_SELECTED"
    ROUTING_PENDING = "ROUTING_PENDING"
    ROUTED = "ROUTED"
    ROUTING_FAILED = "ROUTING_FAILED"


@dataclass(frozen=True)
class CommerceRegistrationRequest:
    asset_id: int
    creator_profile_id: int | None = None
    content_intelligence_status: str | None = None
    content_intelligence_ready: bool = False
    source_workflow: str | None = None
    approval_identity: Mapping[str, Any] = field(default_factory=dict)
    creator_intent: Mapping[str, Any] = field(default_factory=dict)
    existing_product_ids: tuple[str, ...] = ()
    existing_experience_ids: tuple[str, ...] = ()
    product_draft_ids: tuple[str, ...] = ()
    delivery_type_recommendation: str | None = None
    commerce_intelligence_refs: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass(frozen=True)
class CommerceReadiness:
    ready_for_commerce_destination: bool
    delivery_type_status: str
    publishing_readiness_status: str
    fulfillment_readiness_status: str = "UNKNOWN"
    missing_requirements: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "ready_for_commerce_destination": self.ready_for_commerce_destination,
            "delivery_type_status": self.delivery_type_status,
            "publishing_readiness_status": self.publishing_readiness_status,
            "fulfillment_readiness_status": self.fulfillment_readiness_status,
            "missing_requirements": list(self.missing_requirements),
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BusinessAssetRecord:
    registration_id: UUID
    asset_id: int
    creator_profile_id: int | None
    approval_status: str
    content_intelligence_status: str
    content_intelligence_ready: bool
    commerce_registration_status: CommerceRegistrationStatus
    business_lifecycle_state: BusinessAssetLifecycleState
    commerce_destination_status: CommerceDestinationStatus
    selected_commerce_destination: str | None = None
    destination_selected_at: datetime | None = None
    destination_selected_by_profile_id: int | None = None
    destination_source_workflow: str | None = None
    destination_routing_state: str | None = None
    destination_change_note: str | None = None
    destination_revision: int = 0
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    product_draft_ids: tuple[str, ...] = ()
    delivery_type: str | None = None
    delivery_type_source: str | None = None
    delivery_type_requires_review: bool = False
    commerce_intelligence_refs: Mapping[str, Any] = field(default_factory=dict)
    publishing_readiness: Mapping[str, Any] = field(default_factory=dict)
    fulfillment_readiness: Mapping[str, Any] = field(default_factory=dict)
    relationship_provenance: Mapping[str, Any] = field(default_factory=dict)
    registration_provenance: Mapping[str, Any] = field(default_factory=dict)
    missing_requirements: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    registered_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: str = COMMERCE_REGISTRATION_SCHEMA_VERSION

    @property
    def commerce_readiness(self) -> CommerceReadiness:
        return CommerceReadiness(
            ready_for_commerce_destination=(
                self.commerce_registration_status
                == CommerceRegistrationStatus.REGISTERED
                and self.business_lifecycle_state
                in {
                    BusinessAssetLifecycleState.AWAITING_DESTINATION,
                    BusinessAssetLifecycleState.DESTINATION_SELECTED,
                    BusinessAssetLifecycleState.ROUTING_PENDING,
                }
            ),
            delivery_type_status=(
                "RESOLVED" if self.delivery_type else "UNRESOLVED"
            ),
            publishing_readiness_status=str(
                self.publishing_readiness.get("status") or "UNKNOWN"
            ),
            fulfillment_readiness_status=str(
                self.fulfillment_readiness.get("status") or "UNKNOWN"
            ),
            missing_requirements=self.missing_requirements,
            warnings=self.warnings,
        )

    @classmethod
    def deterministic_id(cls, asset_id: int) -> UUID:
        return uuid5(NAMESPACE_URL, f"creator-os:commerce-registration:{int(asset_id)}")

    def to_context(self) -> dict[str, Any]:
        return {
            "registration_id": str(self.registration_id),
            "asset_id": self.asset_id,
            "creator_profile_id": self.creator_profile_id,
            "approval_status": self.approval_status,
            "content_intelligence_status": self.content_intelligence_status,
            "content_intelligence_ready": self.content_intelligence_ready,
            "commerce_registration_status": self.commerce_registration_status.value,
            "business_lifecycle_state": self.business_lifecycle_state.value,
            "commerce_destination_status": self.commerce_destination_status.value,
            "selected_commerce_destination": self.selected_commerce_destination,
            "destination_selected_at": (
                self.destination_selected_at.isoformat()
                if self.destination_selected_at
                else None
            ),
            "destination_selected_by_profile_id": self.destination_selected_by_profile_id,
            "destination_source_workflow": self.destination_source_workflow,
            "destination_routing_state": self.destination_routing_state,
            "destination_change_note": self.destination_change_note,
            "destination_revision": self.destination_revision,
            "product_ids": list(self.product_ids),
            "experience_ids": list(self.experience_ids),
            "product_draft_ids": list(self.product_draft_ids),
            "delivery_type": self.delivery_type,
            "delivery_type_source": self.delivery_type_source,
            "delivery_type_requires_review": self.delivery_type_requires_review,
            "commerce_intelligence_refs": dict(self.commerce_intelligence_refs),
            "publishing_readiness": dict(self.publishing_readiness),
            "fulfillment_readiness": dict(self.fulfillment_readiness),
            "relationship_provenance": dict(self.relationship_provenance),
            "registration_provenance": dict(self.registration_provenance),
            "missing_requirements": list(self.missing_requirements),
            "warnings": list(self.warnings),
            "error_code": self.error_code,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "last_refreshed_at": (
                self.last_refreshed_at.isoformat()
                if self.last_refreshed_at
                else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class CommerceRegistrationResult:
    success: bool
    asset_id: int
    registration_id: UUID | None = None
    business_lifecycle_state: BusinessAssetLifecycleState | None = None
    commerce_readiness: CommerceReadiness | None = None
    product_ids: tuple[str, ...] = ()
    experience_ids: tuple[str, ...] = ()
    product_draft_ids: tuple[str, ...] = ()
    delivery_type_status: str = "UNRESOLVED"
    publishing_readiness_status: str = "UNKNOWN"
    missing_requirements: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    record: BusinessAssetRecord | None = None

    @classmethod
    def from_record(cls, record: BusinessAssetRecord) -> "CommerceRegistrationResult":
        readiness = record.commerce_readiness
        return cls(
            success=(
                record.commerce_registration_status
                == CommerceRegistrationStatus.REGISTERED
            ),
            asset_id=record.asset_id,
            registration_id=record.registration_id,
            business_lifecycle_state=record.business_lifecycle_state,
            commerce_readiness=readiness,
            product_ids=record.product_ids,
            experience_ids=record.experience_ids,
            product_draft_ids=record.product_draft_ids,
            delivery_type_status=readiness.delivery_type_status,
            publishing_readiness_status=readiness.publishing_readiness_status,
            missing_requirements=record.missing_requirements,
            warnings=record.warnings,
            errors=((record.error_message,) if record.error_message else ()),
            record=record,
        )

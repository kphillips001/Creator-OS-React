"""Commerce Destination contracts for creator-selected Business Asset routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


COMMERCE_DESTINATION_SCHEMA_VERSION = "phase_3_10_4_commerce_destination_v1"


class CommerceDestination(str, Enum):
    TELEGRAM_WALL = "TELEGRAM_WALL"
    CUSTOMER_CONVERSATIONS = "CUSTOMER_CONVERSATIONS"
    BOTH = "BOTH"
    ARCHIVE_ONLY = "ARCHIVE_ONLY"


class DestinationRoutingStatus(str, Enum):
    ROUTING_PENDING = "ROUTING_PENDING"
    ROUTING = "ROUTING"
    UPLOAD_IN_PROGRESS = "UPLOAD_IN_PROGRESS"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    FULFILLMENT_READY = "FULFILLMENT_READY"
    ROUTED = "ROUTED"
    ROUTING_FAILED = "ROUTING_FAILED"
    CANCELLED = "CANCELLED"


class DestinationRoutingOwner(str, Enum):
    TELEGRAM_WALL = "TELEGRAM_WALL"
    CUSTOMER_CONVERSATIONS = "CUSTOMER_CONVERSATIONS"
    ARCHIVE = "ARCHIVE"


@dataclass(frozen=True)
class CommerceDestinationRequest:
    asset_id: int
    registration_id: UUID | str
    destination: CommerceDestination | str
    creator_profile_id: int | None = None
    creator_identity: Mapping[str, Any] = field(default_factory=dict)
    source_workflow: str | None = None
    source_session_id: str | None = None
    reason: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class DestinationRoutingIntent:
    routing_intent_id: UUID
    asset_id: int
    registration_id: UUID
    selected_destination: CommerceDestination
    routing_owner: DestinationRoutingOwner
    routing_status: DestinationRoutingStatus
    source_workflow: str | None = None
    downstream_owner_service: str | None = None
    downstream_prerequisites: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: str = COMMERCE_DESTINATION_SCHEMA_VERSION

    def to_context(self) -> dict[str, Any]:
        return {
            "routing_intent_id": str(self.routing_intent_id),
            "asset_id": self.asset_id,
            "registration_id": str(self.registration_id),
            "selected_destination": self.selected_destination.value,
            "routing_owner": self.routing_owner.value,
            "routing_status": self.routing_status.value,
            "source_workflow": self.source_workflow,
            "downstream_owner_service": self.downstream_owner_service,
            "downstream_prerequisites": list(self.downstream_prerequisites),
            "metadata": dict(self.metadata),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class CommerceDestinationHistoryEntry:
    history_id: UUID
    asset_id: int
    registration_id: UUID
    previous_destination: CommerceDestination | None
    new_destination: CommerceDestination | None
    creator_profile_id: int | None = None
    creator_identity: Mapping[str, Any] = field(default_factory=dict)
    source_workflow: str | None = None
    source_session_id: str | None = None
    reason: str | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = COMMERCE_DESTINATION_SCHEMA_VERSION


@dataclass(frozen=True)
class CommerceDestinationResult:
    success: bool
    asset_id: int
    selected_destination: CommerceDestination | None = None
    previous_destination: CommerceDestination | None = None
    destination_status: str | None = None
    routing_intents_created: tuple[DestinationRoutingIntent, ...] = ()
    routing_intents: tuple[DestinationRoutingIntent, ...] = ()
    changed: bool = False
    unchanged: bool = False
    creator_profile_id: int | None = None
    timestamp: datetime | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "asset_id": self.asset_id,
            "selected_destination": (
                self.selected_destination.value if self.selected_destination else None
            ),
            "previous_destination": (
                self.previous_destination.value if self.previous_destination else None
            ),
            "destination_status": self.destination_status,
            "routing_intents_created": [
                intent.to_context() for intent in self.routing_intents_created
            ],
            "routing_intents": [intent.to_context() for intent in self.routing_intents],
            "changed": self.changed,
            "unchanged": self.unchanged,
            "creator_profile_id": self.creator_profile_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

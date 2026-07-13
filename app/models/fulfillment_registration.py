"""Provider-neutral fulfillment registration contracts for Business Assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.commerce_destination import DestinationRoutingOwner


FULFILLMENT_REGISTRATION_SCHEMA_VERSION = (
    "phase_3_10_5_fulfillment_registration_v1"
)


class FulfillmentRoute(str, Enum):
    CUSTOMER_CONVERSATIONS = "CUSTOMER_CONVERSATIONS"


class FulfillmentLifecycleState(str, Enum):
    ROUTING_PENDING = "ROUTING_PENDING"
    READY_FOR_UPLOAD = "READY_FOR_UPLOAD"
    UPLOAD_QUEUED = "UPLOAD_QUEUED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    MEDIA_READY = "MEDIA_READY"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    MEDIA_LINK_SUBMITTED = "MEDIA_LINK_SUBMITTED"
    MEDIA_LINK_VERIFIED = "MEDIA_LINK_VERIFIED"
    FULFILLMENT_READY = "FULFILLMENT_READY"
    FAILED = "FAILED"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    RETIRED = "RETIRED"


class MediaLinkVerificationState(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    MISSING = "MISSING"
    SUBMITTED = "SUBMITTED"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class FulfillmentReadiness:
    status: FulfillmentLifecycleState
    provider: str | None = None
    provider_media_id: str | None = None
    upload_ready: bool = False
    waiting_for_media_link: bool = False
    media_link_submitted: bool = False
    media_link_verified: bool = False
    fulfillment_ready: bool = False
    retry_required: bool = False
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_context(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "provider": self.provider,
            "provider_media_id": self.provider_media_id,
            "upload_ready": self.upload_ready,
            "waiting_for_media_link": self.waiting_for_media_link,
            "media_link_submitted": self.media_link_submitted,
            "media_link_verified": self.media_link_verified,
            "fulfillment_ready": self.fulfillment_ready,
            "retry_required": self.retry_required,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "updated_at": _datetime_context(self.updated_at),
            "metadata": dict(self.metadata or {}),
            "owns_fulfillment": False,
            "source": "FulfillmentRegistrationService",
        }


@dataclass(frozen=True)
class FulfillmentRegistrationRequest:
    asset_id: int
    registration_id: UUID
    routing_intent_id: UUID
    route: FulfillmentRoute = FulfillmentRoute.CUSTOMER_CONVERSATIONS
    provider: str = "fanvue"
    provider_account_id: int | None = None
    creator_profile_id: int | None = None
    source_workflow: str | None = None
    source_session_id: str | None = None
    idempotency_key: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MediaLinkSubmission:
    asset_id: int
    media_link: str | None
    creator_profile_id: int
    route: FulfillmentRoute = FulfillmentRoute.CUSTOMER_CONVERSATIONS
    submitted_by: Mapping[str, Any] = field(default_factory=dict)
    replace_existing: bool = False
    idempotency_key: str | None = None


@dataclass(frozen=True)
class MediaLinkVerificationResult:
    success: bool
    asset_id: int
    media_link: str | None = None
    verification_state: MediaLinkVerificationState | None = None
    record: "BusinessAssetFulfillmentRecord | None" = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class BusinessAssetFulfillmentRecord:
    fulfillment_id: UUID
    asset_id: int
    registration_id: UUID
    routing_intent_id: UUID
    route: FulfillmentRoute
    route_owner: DestinationRoutingOwner
    provider: str
    lifecycle_state: FulfillmentLifecycleState
    provider_account_id: int | None = None
    publishing_job_id: UUID | None = None
    upload_attempt_id: UUID | str | None = None
    provider_media_id: str | None = None
    provider_preview_media_id: str | None = None
    provider_full_media_id: str | None = None
    provider_processing_status: str | None = None
    media_link: str | None = None
    media_link_verification_state: MediaLinkVerificationState = (
        MediaLinkVerificationState.MISSING
    )
    media_link_submitted_at: datetime | None = None
    media_link_verified_at: datetime | None = None
    fulfillment_ready_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    retry_count: int = 0
    retry_required: bool = False
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    schema_version: str = FULFILLMENT_REGISTRATION_SCHEMA_VERSION

    @classmethod
    def deterministic_id(
        cls,
        asset_id: int,
        route: FulfillmentRoute | str,
    ) -> UUID:
        route_value = route.value if isinstance(route, FulfillmentRoute) else str(route)
        return uuid5(
            NAMESPACE_URL,
            f"creator-os:business-asset-fulfillment:{int(asset_id)}:{route_value}",
        )

    @property
    def readiness(self) -> FulfillmentReadiness:
        return FulfillmentReadiness(
            status=self.lifecycle_state,
            provider=self.provider,
            provider_media_id=(
                self.provider_media_id
                or self.provider_full_media_id
                or self.provider_preview_media_id
            ),
            upload_ready=self.lifecycle_state
            in {
                FulfillmentLifecycleState.READY_FOR_UPLOAD,
                FulfillmentLifecycleState.UPLOAD_QUEUED,
                FulfillmentLifecycleState.RETRY_REQUIRED,
            },
            waiting_for_media_link=(
                self.lifecycle_state
                == FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK
            ),
            media_link_submitted=(
                self.media_link_verification_state
                in {
                    MediaLinkVerificationState.SUBMITTED,
                    MediaLinkVerificationState.VERIFIED,
                }
            ),
            media_link_verified=(
                self.media_link_verification_state
                == MediaLinkVerificationState.VERIFIED
            ),
            fulfillment_ready=(
                self.lifecycle_state == FulfillmentLifecycleState.FULFILLMENT_READY
            ),
            retry_required=self.retry_required,
            error_code=self.failure_code,
            error_message=self.failure_message,
            updated_at=self.updated_at,
            metadata={
                "fulfillment_id": str(self.fulfillment_id),
                "route": self.route.value,
                "route_owner": self.route_owner.value,
                "routing_intent_id": str(self.routing_intent_id),
                "publishing_job_id": (
                    str(self.publishing_job_id) if self.publishing_job_id else None
                ),
                "media_link": self.media_link,
                "media_link_verification_state": (
                    self.media_link_verification_state.value
                ),
            },
        )

    def to_context(self) -> dict[str, Any]:
        return {
            "fulfillment_id": str(self.fulfillment_id),
            "asset_id": self.asset_id,
            "registration_id": str(self.registration_id),
            "routing_intent_id": str(self.routing_intent_id),
            "route": self.route.value,
            "route_owner": self.route_owner.value,
            "provider": self.provider,
            "provider_account_id": self.provider_account_id,
            "publishing_job_id": (
                str(self.publishing_job_id) if self.publishing_job_id else None
            ),
            "upload_attempt_id": (
                str(self.upload_attempt_id) if self.upload_attempt_id else None
            ),
            "provider_media_id": self.provider_media_id,
            "provider_preview_media_id": self.provider_preview_media_id,
            "provider_full_media_id": self.provider_full_media_id,
            "provider_processing_status": self.provider_processing_status,
            "lifecycle_state": self.lifecycle_state.value,
            "media_link": self.media_link,
            "media_link_verification_state": self.media_link_verification_state.value,
            "media_link_submitted_at": _datetime_context(
                self.media_link_submitted_at
            ),
            "media_link_verified_at": _datetime_context(
                self.media_link_verified_at
            ),
            "fulfillment_ready_at": _datetime_context(self.fulfillment_ready_at),
            "failure_code": self.failure_code,
            "failure_message": self.failure_message,
            "retry_count": self.retry_count,
            "retry_required": self.retry_required,
            "provider_metadata": dict(self.provider_metadata or {}),
            "provenance": dict(self.provenance or {}),
            "created_at": _datetime_context(self.created_at),
            "updated_at": _datetime_context(self.updated_at),
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class FulfillmentRegistrationResult:
    success: bool
    asset_id: int
    record: BusinessAssetFulfillmentRecord | None = None
    publishing_job: Any | None = None
    upload_result: Mapping[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_context(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "asset_id": self.asset_id,
            "record": self.record.to_context() if self.record else None,
            "upload_result": dict(self.upload_result or {}),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


def _datetime_context(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)

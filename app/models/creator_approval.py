"""Provider-neutral creator approval contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.generation_engine import utc_now


@dataclass(frozen=True)
class ApprovedSourceIdentity:
    source_workflow: str
    source_item_id: str
    source_session_id: str | None = None
    idempotency_key: str | None = None

    def normalized_key(self) -> str:
        if self.idempotency_key:
            return str(self.idempotency_key)
        parts = [self.source_workflow, self.source_session_id or "", self.source_item_id]
        return ":".join(str(part).strip() for part in parts if str(part).strip())


@dataclass(frozen=True)
class CreatorApprovalRequest:
    source: ApprovedSourceIdentity
    media_reference: str
    creator_profile_id: int | None
    creator_intent: Any | None = None
    source_metadata: Mapping[str, Any] = field(default_factory=dict)
    post_approval_policy: Mapping[str, Any] = field(default_factory=dict)
    approved_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CreatorApprovalAdapterRequest:
    source_workflow: str
    source_item_id: str
    media_reference: str
    creator_profile_id: int | None
    approval_intent: Any | None
    idempotency_key: str
    source_session_id: str | None = None
    source_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_approval_request(self) -> CreatorApprovalRequest:
        if not self.source_workflow:
            raise ValueError("source_workflow is required")
        if not self.source_item_id:
            raise ValueError("source_item_id is required")
        if not self.media_reference:
            raise ValueError("media_reference is required")
        if not self.idempotency_key:
            raise ValueError("idempotency_key is required")
        return CreatorApprovalRequest(
            source=ApprovedSourceIdentity(
                source_workflow=self.source_workflow,
                source_item_id=self.source_item_id,
                source_session_id=self.source_session_id,
                idempotency_key=self.idempotency_key,
            ),
            media_reference=self.media_reference,
            creator_profile_id=self.creator_profile_id,
            creator_intent=self.approval_intent,
            source_metadata={
                "adapter_contract": "CreatorApprovalAdapterRequest",
                **dict(self.source_metadata or {}),
            },
        )


@dataclass(frozen=True)
class CreatorApprovalResult:
    success: bool
    source: ApprovedSourceIdentity
    asset_id: int | None = None
    new_asset_created: bool = False
    reused_existing_mapping: bool = False
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    workflow_metadata: Mapping[str, Any] = field(default_factory=dict)
    intelligence_status: str | None = None
    intelligence_ready: bool = False
    intelligence_missing_components: tuple[str, ...] = ()
    intelligence_error: str | None = None
    commerce_registration_id: str | None = None
    commerce_registration_status: str | None = None
    business_lifecycle_state: str | None = None
    commerce_destination_status: str | None = None
    selected_commerce_destination: str | None = None
    commerce_ready: bool = False
    commerce_product_ids: tuple[str, ...] = ()
    commerce_experience_ids: tuple[str, ...] = ()
    commerce_product_draft_ids: tuple[str, ...] = ()
    commerce_missing_requirements: tuple[str, ...] = ()
    commerce_error: str | None = None

"""Immutable, provider-neutral answers to canonical ownership questions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID


class OwnershipSource(str, Enum):
    OFFERING_PURCHASE = "ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE"
    PRODUCT_ENTITLEMENT = "PRODUCT_ENTITLEMENT"
    CORE_USER_ENTITLEMENT = "CORE_USER_PRODUCT_ENTITLEMENT"
    LEGACY_OWNERSHIP = "LEGACY_CONTENT_USAGE"
    PROVIDER_RESOURCE_PURCHASE = "PROVIDER_RESOURCE_PURCHASE"
    SOURCE_UNAVAILABLE = "OWNERSHIP_SOURCE_UNAVAILABLE"


class OwnershipLifecycle(str, Enum):
    PURCHASED = "PURCHASED"
    ACTIVE = "ACTIVE"
    FULFILLED = "FULFILLED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REFUNDED = "REFUNDED"
    PENDING = "PENDING"
    INCOMPLETE = "INCOMPLETE"
    CONFLICTING = "CONFLICTING"
    AMBIGUOUS = "AMBIGUOUS"
    ABANDONED = "ABANDONED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"


class CoverageState(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    NONE = "NONE"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class OwnershipAnswerState(str, Enum):
    CONFIRMED_OWNERSHIP = "CONFIRMED_OWNERSHIP"
    NO_DEMONSTRATED_OWNERSHIP = "NO_DEMONSTRATED_OWNERSHIP"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


@dataclass(frozen=True)
class OwnershipIdentity:
    creator_profile_id: int
    fanvue_account_id: int
    external_fanvue_user_uuid: UUID | None = None
    telegram_user_id: int | None = None
    legacy_fanvue_user_id: str | None = None
    core_user_id: UUID | None = None


@dataclass(frozen=True)
class OwnershipEvidence:
    source: OwnershipSource
    lifecycle: OwnershipLifecycle
    identity_path: str
    supporting_record_id: str | None
    creator_profile_id: int | None = None
    fanvue_account_id: int | None = None
    asset_ids: tuple[int, ...] = ()
    offering_id: UUID | None = None
    product_id: UUID | None = None
    sales_session_id: UUID | None = None
    proves_ownership: bool = False
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OwnershipCoverage:
    state: CoverageState
    represented_asset_ids: tuple[int, ...]
    owned_asset_ids: tuple[int, ...]
    remaining_asset_ids: tuple[int, ...]
    evidence: tuple[OwnershipEvidence, ...]
    conflicts: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.state is CoverageState.COMPLETE

    @property
    def partial(self) -> bool:
        return self.state is CoverageState.PARTIAL


@dataclass(frozen=True)
class SessionPurchaseChronology:
    purchase_intent_id: UUID
    sequence: int
    associated_at: Any
    asset_ids: tuple[int, ...]


@dataclass(frozen=True)
class SessionOwnershipCoverage:
    sales_session_id: UUID
    foundation: str | None
    coverage: OwnershipCoverage
    session_purchased_asset_ids: tuple[int, ...]
    overlapping_external_asset_ids: tuple[int, ...]
    remaining_asset_ids: tuple[int, ...]
    chronology: tuple[SessionPurchaseChronology, ...]


@dataclass(frozen=True)
class OwnershipWorkspaceView:
    answer: "CanonicalOwnershipAnswer"
    bundle_coverage: Mapping[str, OwnershipCoverage]
    session_coverage: Mapping[str, SessionOwnershipCoverage]
    remaining_asset_ids: tuple[int, ...]


@dataclass(frozen=True)
class OwnershipLineageContext:
    """Non-authoritative lineage visibility alongside explicit ownership."""

    asset_id: int
    ancestor_asset_ids: tuple[int, ...]
    descendant_asset_ids: tuple[int, ...]
    sibling_asset_ids: tuple[int, ...]
    family_asset_ids: tuple[int, ...]
    owned_related_asset_ids: tuple[int, ...]
    unowned_related_asset_ids: tuple[int, ...]


@dataclass(frozen=True)
class CanonicalOwnershipAnswer:
    identity: OwnershipIdentity
    evidence: tuple[OwnershipEvidence, ...]
    owned_offering_ids: tuple[UUID, ...]
    owned_product_ids: tuple[UUID, ...]
    owned_asset_ids: tuple[int, ...]
    conflicts: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()
    diagnostics: Mapping[str, Any] = field(default_factory=dict)
    state: OwnershipAnswerState = OwnershipAnswerState.NO_DEMONSTRATED_OWNERSHIP
    lineage_contexts: Mapping[int, OwnershipLineageContext] = field(
        default_factory=dict
    )

    @property
    def evidence_sufficient(self) -> bool:
        return not self.conflicts and not self.insufficiencies


def immutable_details(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))

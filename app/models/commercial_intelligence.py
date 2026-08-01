"""Immutable, provider-neutral Commercial Intelligence decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID
from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer,
    OwnershipCoverage as CanonicalOwnershipCoverage,
    SessionOwnershipCoverage,
)


class SellingStrategy(str, Enum):
    SESSION_SELLING = "SESSION_SELLING"
    LIBRARY_SELLING = "LIBRARY_SELLING"
    BUNDLE_SELLING = "BUNDLE_SELLING"


class StrategyDecisionReason(str, Enum):
    ACTIVE_SESSION_CONTINUATION = "ACTIVE_SESSION_CONTINUATION"
    CUSTOMER_REQUEST_MATCH = "CUSTOMER_REQUEST_MATCH"
    COMPLETE_SET_REQUEST = "COMPLETE_SET_REQUEST"
    CONTINUATION_REQUIRED = "CONTINUATION_REQUIRED"
    COMPLETE_VALUE_OWNED = "COMPLETE_VALUE_OWNED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    INSUFFICIENT_OWNERSHIP_EVIDENCE = "INSUFFICIENT_OWNERSHIP_EVIDENCE"


class BundleEligibility(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    MISSED_ORIGINAL_SESSION = "MISSED_ORIGINAL_SESSION"
    PARTICIPATED_NO_PURCHASE = "PARTICIPATED_NO_PURCHASE"
    PARTIAL_SESSION_PURCHASE = "PARTIAL_SESSION_PURCHASE"
    COMPLETE_VALUE_OWNED = "COMPLETE_VALUE_OWNED"
    CONTINUATION_REQUIRED = "CONTINUATION_REQUIRED"
    INSUFFICIENT_OWNERSHIP_EVIDENCE = "INSUFFICIENT_OWNERSHIP_EVIDENCE"
    BUNDLE_ELIGIBLE = "BUNDLE_ELIGIBLE"


@dataclass(frozen=True)
class StrategyConstraints:
    required_offering_types: tuple[str, ...] = ()
    excluded_offering_types: tuple[str, ...] = ()
    required_photoshoot_reference: str | None = None
    progression: str | None = None
    approved_commercial_roles: tuple[str, ...] = ()
    requested_media_type: str | None = None
    requested_themes: tuple[str, ...] = ()
    complete_set_required: bool = False
    excluded_asset_ids: tuple[int, ...] = ()
    remaining_value_required: bool = False
    continuation_required: bool = False
    publication_ready_required: bool = True
    fulfillment_ready_required: bool = True


@dataclass(frozen=True)
class OwnershipCoverage:
    owned_offering_ids: tuple[UUID, ...] = ()
    owned_asset_ids: tuple[int, ...] = ()
    session_owned_asset_ids: tuple[int, ...] = ()
    evidence_sources: tuple[str, ...] = ()
    incomplete: bool = False
    conflicts: tuple[str, ...] = ()


@dataclass(frozen=True)
class BundleCompositionEvidence:
    photoshoot_reference: str
    asset_ids: tuple[int, ...]
    complete_set: bool
    provenance: tuple[str, ...] = ()


@dataclass(frozen=True)
class CommercialIntelligenceContext:
    creator_profile_id: int
    fanvue_account_id: int
    telegram_user_id: int | None
    active_sales_session_id: UUID | None = None
    sales_session_state: str | None = None
    sales_session_progression: str | None = None
    sales_session_foundation_type: str | None = None
    sales_session_foundation: str | None = None
    session_participated: bool = False
    session_purchase_count: int = 0
    approved_commercial_roles: tuple[str, ...] = ()
    latest_message: str | None = None
    requested_media_type: str | None = None
    requested_themes: tuple[str, ...] = ()
    recent_conversation_requests: tuple[str, ...] = ()
    available_offering_types: tuple[str, ...] = ()
    intended_photoshoot_reference: str | None = None
    bundle_compositions: tuple[BundleCompositionEvidence, ...] = ()
    canonical_bundle_coverage: CanonicalOwnershipCoverage | None = None
    canonical_session_coverage: SessionOwnershipCoverage | None = None
    canonical_ownership_answer: CanonicalOwnershipAnswer | None = None
    ownership: OwnershipCoverage = field(default_factory=OwnershipCoverage)
    lineage_evidence: Mapping[str, Any] = field(default_factory=dict)
    durable_evidence: Mapping[str, Any] = field(default_factory=dict)
    conversation_evidence: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class CommercialIntelligenceDecision:
    strategy: SellingStrategy | None
    reason: StrategyDecisionReason
    reason_summary: str
    evidence: tuple[str, ...]
    evidence_provenance: Mapping[str, tuple[str, ...]]
    constraints: StrategyConstraints
    sales_session_context: Mapping[str, Any]
    customer_request_context: Mapping[str, Any]
    ownership_considerations: Mapping[str, Any]
    bundle_eligibility: BundleEligibility
    continuation_guidance: str | None
    evidence_sufficient: bool
    conflicts: tuple[str, ...]
    diagnostic_context: Mapping[str, Any]


def immutable_mapping(value: Mapping[str, Any] | None) -> Mapping[str, Any]:
    return MappingProxyType(dict(value or {}))

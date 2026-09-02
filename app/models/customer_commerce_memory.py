"""Immutable, customer-scoped commerce memory used by Sales Brain."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer,
    OwnershipIdentity,
)


@dataclass(frozen=True)
class CustomerPurchaseEvent:
    source_type: str
    source_record_id: str
    creator_profile_id: int
    fanvue_account_id: int
    purchased_at: datetime
    channel: str | None = None
    sale_type: str | None = None
    offering_id: UUID | None = None
    product_id: UUID | None = None
    sales_session_id: UUID | None = None
    photoshoot_reference: str | None = None
    asset_ids: tuple[int, ...] = ()
    gross_minor: int | None = None
    net_minor: int | None = None
    currency: str | None = None
    provider_transaction_reference: str | None = None
    completion_state: str = "VERIFIED"
    delivery_state: str | None = None
    intelligence_tags: tuple[str, ...] = ()
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_ids", tuple(sorted(set(self.asset_ids))))
        object.__setattr__(self, "provenance", MappingProxyType(dict(self.provenance)))


@dataclass(frozen=True)
class CustomerCommerceAffinity:
    offering_type_weights: Mapping[str, float] = field(default_factory=dict)
    tag_weights: Mapping[str, float] = field(default_factory=dict)
    channel_weights: Mapping[str, float] = field(default_factory=dict)
    typical_price_min_minor: int | None = None
    typical_price_max_minor: int | None = None
    recent_purchase_count: int = 0
    historical_purchase_count: int = 0

    def __post_init__(self) -> None:
        for name in ("offering_type_weights", "tag_weights", "channel_weights"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))


@dataclass(frozen=True)
class CustomerCommerceMemory:
    identity: OwnershipIdentity
    ownership: CanonicalOwnershipAnswer
    purchase_events: tuple[CustomerPurchaseEvent, ...] = ()
    unmatched_financial_evidence: tuple[Mapping[str, Any], ...] = ()
    purchase_count: int = 0
    first_purchase_at: datetime | None = None
    last_purchase_at: datetime | None = None
    lifetime_gross_minor: int = 0
    lifetime_net_minor: int = 0
    average_order_value_minor: int = 0
    largest_order_minor: int = 0
    channels_purchased_through: tuple[str, ...] = ()
    purchase_type_history: tuple[str, ...] = ()
    affinity: CustomerCommerceAffinity = field(default_factory=CustomerCommerceAffinity)
    active_purchase_state: Mapping[str, Any] = field(default_factory=dict)
    attribution_insufficiencies: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "unmatched_financial_evidence",
            tuple(MappingProxyType(dict(item)) for item in self.unmatched_financial_evidence),
        )
        object.__setattr__(self, "active_purchase_state", MappingProxyType(dict(self.active_purchase_state)))

    @property
    def owned_asset_ids(self) -> tuple[int, ...]:
        return self.ownership.owned_asset_ids

    @property
    def owned_offering_ids(self) -> tuple[UUID, ...]:
        return self.ownership.owned_offering_ids

    @property
    def owned_product_ids(self) -> tuple[UUID, ...]:
        return self.ownership.owned_product_ids


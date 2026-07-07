"""Provider-neutral Customer domain read model.

C.3.2 foundation only. These models do not define persistence, repositories,
runtime workflows, or provider adapters. They aggregate existing customer
business concepts for future Customer Workspace read models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class CustomerRelationshipStatus(str, Enum):
    UNKNOWN = "unknown"
    PROSPECT = "prospect"
    FOLLOWER = "follower"
    SUBSCRIBER = "subscriber"
    CUSTOMER = "customer"
    LAPSED = "lapsed"
    MISSING = "missing"


@dataclass(frozen=True)
class CustomerProviderIdentity:
    provider: str
    provider_customer_id: str
    provider_account_id: str | None = None
    channel: str | None = None
    username: str | None = None
    display_name: str | None = None
    is_active: bool = True
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", str(self.provider).strip().lower())
        object.__setattr__(
            self,
            "provider_customer_id",
            str(self.provider_customer_id),
        )
        if self.provider_account_id is not None:
            object.__setattr__(
                self,
                "provider_account_id",
                str(self.provider_account_id),
            )
        if self.channel is not None:
            object.__setattr__(self, "channel", str(self.channel).strip().lower())
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class CustomerRelationshipSummary:
    status: CustomerRelationshipStatus = CustomerRelationshipStatus.UNKNOWN
    is_follower: bool = False
    is_subscriber: bool = False
    value_tier: str | None = None
    buyer_tier: str | None = None
    total_spend_cents: int = 0
    purchase_count: int = 0
    last_active_at: datetime | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "status",
            CustomerRelationshipStatus(self.status),
        )
        object.__setattr__(self, "total_spend_cents", int(self.total_spend_cents or 0))
        object.__setattr__(self, "purchase_count", int(self.purchase_count or 0))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class CustomerConversationSummary:
    thread_count: int = 0
    message_count: int = 0
    inbound_message_count: int = 0
    outbound_message_count: int = 0
    last_message_at: datetime | None = None
    last_inbound_at: datetime | None = None
    last_outbound_at: datetime | None = None
    current_mode: str | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "thread_count",
            "message_count",
            "inbound_message_count",
            "outbound_message_count",
        ):
            object.__setattr__(
                self,
                field_name,
                int(getattr(self, field_name) or 0),
            )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class CustomerProgressionSummary:
    current_experience_id: str | None = None
    current_position: str | None = None
    completed_experience_ids: tuple[str, ...] = ()
    seen_experience_ids: tuple[str, ...] = ()
    seen_content_tags: tuple[str, ...] = ()
    active_session: bool = False
    session_step: int = 0
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "completed_experience_ids",
            "seen_experience_ids",
            "seen_content_tags",
        ):
            object.__setattr__(
                self,
                field_name,
                _coerce_text_tuple(getattr(self, field_name)),
            )
        object.__setattr__(self, "session_step", int(self.session_step or 0))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class CustomerOwnershipSummary:
    owned_product_ids: tuple[str, ...] = ()
    owned_experience_ids: tuple[str, ...] = ()
    entitlement_count: int = 0
    purchase_count: int = 0
    last_purchase_at: datetime | None = None
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "owned_product_ids",
            _coerce_text_tuple(self.owned_product_ids),
        )
        object.__setattr__(
            self,
            "owned_experience_ids",
            _coerce_text_tuple(self.owned_experience_ids),
        )
        object.__setattr__(self, "entitlement_count", int(self.entitlement_count or 0))
        object.__setattr__(self, "purchase_count", int(self.purchase_count or 0))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def owns_product(self, product_id: str) -> bool:
        return str(product_id) in self.owned_product_ids

    def owns_experience(self, experience_id: str) -> bool:
        return str(experience_id) in self.owned_experience_ids


@dataclass(frozen=True)
class CustomerRecommendationSummary:
    seen_offer_ids: tuple[str, ...] = ()
    recent_product_ids: tuple[str, ...] = ()
    last_offer_id: str | None = None
    last_offer_kind: str | None = None
    last_offer_at: datetime | None = None
    offer_count: int = 0
    accepted_offer_count: int = 0
    rejected_offer_count: int = 0
    preferred_tags: tuple[str, ...] = ()
    preferred_themes: tuple[str, ...] = ()
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "seen_offer_ids",
            "recent_product_ids",
            "preferred_tags",
            "preferred_themes",
        ):
            object.__setattr__(
                self,
                field_name,
                _coerce_text_tuple(getattr(self, field_name)),
            )
        for field_name in (
            "offer_count",
            "accepted_offer_count",
            "rejected_offer_count",
        ):
            object.__setattr__(
                self,
                field_name,
                int(getattr(self, field_name) or 0),
            )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))


@dataclass(frozen=True)
class Customer:
    customer_id: str
    display_name: str | None = None
    provider_identities: tuple[CustomerProviderIdentity, ...] = ()
    relationship: CustomerRelationshipSummary = field(
        default_factory=CustomerRelationshipSummary
    )
    conversation: CustomerConversationSummary = field(
        default_factory=CustomerConversationSummary
    )
    progression: CustomerProgressionSummary = field(
        default_factory=CustomerProgressionSummary
    )
    ownership: CustomerOwnershipSummary = field(
        default_factory=CustomerOwnershipSummary
    )
    recommendation: CustomerRecommendationSummary = field(
        default_factory=CustomerRecommendationSummary
    )
    metadata: Mapping[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "customer_id", str(self.customer_id))
        object.__setattr__(
            self,
            "provider_identities",
            tuple(self.provider_identities or ()),
        )
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def identity_for(self, provider: str) -> CustomerProviderIdentity | None:
        normalized_provider = str(provider).strip().lower()
        for identity in self.provider_identities:
            if identity.provider == normalized_provider:
                return identity
        return None

    def has_provider_identity(self, provider: str) -> bool:
        return self.identity_for(provider) is not None


def _coerce_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        values = (value,)
    else:
        values = tuple(value)
    return tuple(str(item) for item in values if item is not None)

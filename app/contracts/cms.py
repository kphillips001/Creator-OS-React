"""Provider-neutral CMS contracts for DecisionEngine inputs.

These dataclasses are the public Creator OS contract surface. They avoid
database rows, repository objects, provider-specific fields, and local storage
details so the DecisionEngine can eventually depend on stable CMS concepts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class ExperienceKind(str, Enum):
    STANDALONE = "standalone"
    PHOTOSHOOT = "photoshoot"
    STORY = "story"


class ProductAvailability(str, Enum):
    DRAFT = "draft"
    AVAILABLE = "available"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ProductDeliveryType(str, Enum):
    FREE = "FREE"
    PAID = "PAID"


class PublishingState(str, Enum):
    UNKNOWN = "unknown"
    NOT_PUBLISHED = "not_published"
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


class DeliveryMode(str, Enum):
    PREVIEW = "preview"
    PAID = "paid"
    INCLUDED = "included"
    MANUAL = "manual"


class DeliverySubjectType(str, Enum):
    PRODUCT = "product"
    EXPERIENCE = "experience"


class OfferKind(str, Enum):
    TEASE = "tease"
    VIP = "vip"
    PREMIUM = "premium"
    CUSTOM = "custom"


@dataclass(frozen=True)
class CustomerIdentity:
    customer_id: str
    creator_id: str | None = None
    channel: str | None = None
    display_name: str | None = None


@dataclass(frozen=True)
class RuntimeCustomerContext:
    identity: CustomerIdentity
    traits: Mapping[str, Any]
    conversation_state: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "traits", dict(self.traits or {}))
        object.__setattr__(
            self,
            "conversation_state",
            dict(self.conversation_state or {}),
        )


@dataclass(frozen=True)
class AvailableExperience:
    experience_id: str
    experience_kind: ExperienceKind
    title: str
    description: str | None = None
    cover_media_ref: str | None = None
    ordered_media_refs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    classification: str | None = None
    presentation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "experience_kind",
            ExperienceKind(self.experience_kind),
        )
        object.__setattr__(
            self,
            "ordered_media_refs",
            _coerce_text_tuple(self.ordered_media_refs),
        )
        object.__setattr__(self, "tags", _coerce_text_tuple(self.tags))
        object.__setattr__(self, "themes", _coerce_text_tuple(self.themes))
        object.__setattr__(self, "presentation", dict(self.presentation or {}))


@dataclass(frozen=True)
class AvailableProduct:
    product_id: str
    title: str
    product_type: str
    availability: ProductAvailability
    delivery_type: ProductDeliveryType = ProductDeliveryType.PAID
    description: str | None = None
    experience_id: str | None = None
    price_cents: int | None = None
    currency: str = "USD"
    tags: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    offer_metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "availability",
            ProductAvailability(self.availability),
        )
        object.__setattr__(
            self,
            "delivery_type",
            ProductDeliveryType(self.delivery_type),
        )
        object.__setattr__(self, "currency", (self.currency or "USD").upper())
        object.__setattr__(self, "tags", _coerce_text_tuple(self.tags))
        object.__setattr__(self, "themes", _coerce_text_tuple(self.themes))
        object.__setattr__(
            self,
            "offer_metadata",
            dict(self.offer_metadata or {}),
        )


@dataclass(frozen=True)
class PublishingStatus:
    subject_id: str
    subject_type: DeliverySubjectType
    state: PublishingState
    is_deliverable: bool = False
    available_delivery_modes: tuple[DeliveryMode, ...] = ()
    reason: str | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_type",
            DeliverySubjectType(self.subject_type),
        )
        object.__setattr__(self, "state", PublishingState(self.state))
        object.__setattr__(
            self,
            "available_delivery_modes",
            tuple(DeliveryMode(mode) for mode in self.available_delivery_modes),
        )


@dataclass(frozen=True)
class CustomerProgress:
    customer_id: str
    seen_offer_ids: tuple[str, ...] = ()
    seen_experience_ids: tuple[str, ...] = ()
    owned_product_ids: tuple[str, ...] = ()
    owned_experience_ids: tuple[str, ...] = ()
    preferred_tags: tuple[str, ...] = ()
    preferred_themes: tuple[str, ...] = ()
    offer_count: int = 0
    purchase_count: int = 0
    total_spend_cents: int = 0
    last_offer_id: str | None = None
    last_offer_kind: OfferKind | None = None
    cooldown_until: datetime | None = None
    signals: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "seen_offer_ids",
            "seen_experience_ids",
            "owned_product_ids",
            "owned_experience_ids",
            "preferred_tags",
            "preferred_themes",
        ):
            object.__setattr__(
                self,
                field_name,
                _coerce_text_tuple(getattr(self, field_name)),
            )
        if self.last_offer_kind is not None:
            object.__setattr__(
                self,
                "last_offer_kind",
                OfferKind(self.last_offer_kind),
            )
        object.__setattr__(self, "signals", dict(self.signals or {}))

    def has_seen_experience(self, experience_id: str) -> bool:
        return str(experience_id) in self.seen_experience_ids

    def owns_product(self, product_id: str) -> bool:
        return str(product_id) in self.owned_product_ids


@dataclass(frozen=True)
class DeliveryPermission:
    subject_id: str
    subject_type: DeliverySubjectType
    delivery_mode: DeliveryMode
    allowed: bool
    reason: str | None = None
    requires_payment: bool = False
    price_cents: int | None = None
    currency: str = "USD"
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject_type",
            DeliverySubjectType(self.subject_type),
        )
        object.__setattr__(
            self,
            "delivery_mode",
            DeliveryMode(self.delivery_mode),
        )
        object.__setattr__(self, "currency", (self.currency or "USD").upper())


@dataclass(frozen=True)
class OfferCandidate:
    offer_id: str
    offer_kind: OfferKind
    title: str
    product: AvailableProduct | None = None
    experience: AvailableExperience | None = None
    delivery_permission: DeliveryPermission | None = None
    publishing_status: PublishingStatus | None = None
    description: str | None = None
    price_cents: int | None = None
    currency: str = "USD"
    score: int = 0
    reason: str | None = None
    presentation: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "offer_kind", OfferKind(self.offer_kind))
        object.__setattr__(self, "currency", (self.currency or "USD").upper())
        object.__setattr__(self, "presentation", dict(self.presentation or {}))

    @property
    def is_deliverable(self) -> bool:
        if self.delivery_permission is not None:
            return self.delivery_permission.allowed
        if self.publishing_status is not None:
            return self.publishing_status.is_deliverable
        return False


def _coerce_text_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        values = (value,)
    else:
        values = tuple(value)
    return tuple(str(item) for item in values if item is not None)

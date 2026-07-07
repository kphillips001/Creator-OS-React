"""Canonical Telegram Business read models.

Telegram Business is a provider-neutral read model over existing Creator OS
domains. It does not execute Telegram, generate strategy, mutate customer
state, publish Products, or record learning outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class TelegramBusinessSummary:
    """Compact business state for one Telegram customer."""

    relationship_stage: str | None = None
    conversation_state: str | None = None
    current_experience_id: str | None = None
    current_product_ids: tuple[str, ...] = ()
    active_offer_ids: tuple[str, ...] = ()
    delivery_count: int = 0
    business_health: str = "UNKNOWN"
    operation_status: str = "UNKNOWN"
    next_recommended_action: str = "Review Telegram Business Context"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelegramBusinessSnapshot:
    """Unified read-only Telegram Business state for one customer."""

    customer_id: str | None = None
    provider: str = "telegram"
    customer_identity: Mapping[str, Any] = field(default_factory=dict)
    relationship: Mapping[str, Any] = field(default_factory=dict)
    conversation: Mapping[str, Any] = field(default_factory=dict)
    experience: Mapping[str, Any] = field(default_factory=dict)
    products: tuple[Mapping[str, Any], ...] = ()
    active_offers: tuple[Mapping[str, Any], ...] = ()
    delivery_history: Mapping[str, Any] = field(default_factory=dict)
    commerce_strategy: Mapping[str, Any] = field(default_factory=dict)
    product_business: Mapping[str, Any] = field(default_factory=dict)
    publishing: Mapping[str, Any] = field(default_factory=dict)
    business_learning: Mapping[str, Any] = field(default_factory=dict)
    telegram_commerce: Mapping[str, Any] = field(default_factory=dict)
    operation_status: str = "UNKNOWN"
    business_health: str = "UNKNOWN"
    next_recommended_business_action: str = "Review Telegram Business Context"
    summary: TelegramBusinessSummary = field(default_factory=TelegramBusinessSummary)
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def relationship_stage(self) -> str | None:
        return self.summary.relationship_stage

    @property
    def conversation_state(self) -> str | None:
        return self.summary.conversation_state

    @property
    def current_experience_id(self) -> str | None:
        return self.summary.current_experience_id

    @property
    def current_product_ids(self) -> tuple[str, ...]:
        return self.summary.current_product_ids

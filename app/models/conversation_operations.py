"""Provider-neutral Conversation Operations read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ConversationOperationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    WAITING_FOR_CUSTOMER = "WAITING_FOR_CUSTOMER"
    WAITING_FOR_CREATOR_OS = "WAITING_FOR_CREATOR_OS"
    PAUSED = "PAUSED"
    STALLED = "STALLED"
    OFFER_PENDING = "OFFER_PENDING"
    DELIVERY_PENDING = "DELIVERY_PENDING"
    EXPERIENCE_ACTIVE = "EXPERIENCE_ACTIVE"
    COMPLETED = "COMPLETED"


@dataclass(frozen=True)
class ConversationOperation:
    """Canonical read-only operation state for one conversation."""

    operation_id: str | None = None
    customer_id: str | None = None
    provider: str = "telegram"
    status: ConversationOperationStatus = ConversationOperationStatus.ACTIVE
    relationship_stage: str | None = None
    conversation_state: str | None = None
    commerce_state: str | None = None
    current_experience_id: str | None = None
    experience_state: str | None = None
    progress_percentage: int = 0
    current_product_ids: tuple[str, ...] = ()
    pending_offer_ids: tuple[str, ...] = ()
    pending_delivery_methods: tuple[str, ...] = ()
    delivery_count: int = 0
    next_operational_action: str = "Continue Conversation"
    business_health: str = "UNKNOWN"
    operation_source: str = "ConversationOperationsService"
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status in {
            ConversationOperationStatus.ACTIVE,
            ConversationOperationStatus.EXPERIENCE_ACTIVE,
            ConversationOperationStatus.OFFER_PENDING,
            ConversationOperationStatus.DELIVERY_PENDING,
        }


@dataclass(frozen=True)
class ConversationOperationSummary:
    """Aggregate read model for a group of conversation operations."""

    total_operations: int = 0
    active_count: int = 0
    paused_count: int = 0
    waiting_for_customer_count: int = 0
    waiting_for_creator_os_count: int = 0
    stalled_count: int = 0
    offer_pending_count: int = 0
    delivery_pending_count: int = 0
    experience_active_count: int = 0
    completed_count: int = 0
    next_actions: Mapping[str, int] = field(default_factory=dict)
    operations: tuple[ConversationOperation, ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

"""Durable customer relationship with one canonical Photoshoot Experience."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class CustomerPhotoshootStatus(str, Enum):
    ACTIVE = "ACTIVE"
    OBJECTION = "OBJECTION"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"
    DECLINED = "DECLINED"


class FinaleDecision(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    PURCHASED = "PURCHASED"
    DECLINED = "DECLINED"


@dataclass(frozen=True)
class CustomerPhotoshootLifecycle:
    lifecycle_id: UUID
    creator_profile_id: int
    customer_commerce_profile_id: UUID
    photoshoot_id: str
    status: CustomerPhotoshootStatus
    current_position: int = 0
    first_started_at: datetime | None = None
    last_activity_at: datetime | None = None
    paused_at: datetime | None = None
    completed_at: datetime | None = None
    abandoned_at: datetime | None = None
    revival_eligible_at: datetime | None = None
    first_sales_session_id: UUID | None = None
    last_sales_session_id: UUID | None = None
    last_purchase_intent_id: UUID | None = None
    selected_offering_id: UUID | None = None
    recommendation_reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None
    closed_at: datetime | None = None
    finale_decision: FinaleDecision = FinaleDecision.NOT_APPLICABLE
    objection_attempts: int = 0
    objection_at: datetime | None = None

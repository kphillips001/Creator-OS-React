"""Canonical commercial experience state for one creator and customer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class SalesSessionState(str, Enum):
    ACTIVE = "ACTIVE"
    OFFERING = "OFFERING"
    AWAITING_PAYMENT = "AWAITING_PAYMENT"
    CONTINUING = "CONTINUING"
    COMPLETED = "COMPLETED"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    CANCELLED = "CANCELLED"


class SalesSessionProgression(str, Enum):
    DISCOVERY = "DISCOVERY"
    CORE = "CORE"
    PROGRESSION = "PROGRESSION"
    PREMIUM = "PREMIUM"
    FINALE = "FINALE"
    BONUS = "BONUS"


class SalesSessionOutcome(str, Enum):
    COMPLETED_WITH_PURCHASE = "COMPLETED_WITH_PURCHASE"
    COMPLETED_WITHOUT_PURCHASE = "COMPLETED_WITHOUT_PURCHASE"
    EXPIRED = "EXPIRED"
    ABANDONED = "ABANDONED"
    CANCELLED = "CANCELLED"


class SalesSessionActorType(str, Enum):
    AI = "AI"
    CREATOR = "CREATOR"
    OPERATOR = "OPERATOR"
    SYSTEM = "SYSTEM"


ACTIVE_SALES_SESSION_STATES = frozenset({
    SalesSessionState.ACTIVE,
    SalesSessionState.OFFERING,
    SalesSessionState.AWAITING_PAYMENT,
    SalesSessionState.CONTINUING,
})


@dataclass(frozen=True)
class SalesSession:
    sales_session_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    fanvue_user_id: int
    external_fanvue_user_uuid: UUID
    telegram_identity_mapping_id: int | None
    conversation_thread_id: int | None
    commercial_foundation_type: str
    commercial_foundation_reference: str
    state: SalesSessionState
    progression_stage: SalesSessionProgression
    objective: str | None
    commercial_context: Mapping[str, Any] = field(default_factory=dict)
    outcome: SalesSessionOutcome | None = None
    terminal_reason: str | None = None
    started_by_type: SalesSessionActorType = SalesSessionActorType.OPERATOR
    started_by_identifier: str | None = None
    started_at: datetime | None = None
    last_activity_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class SalesSessionHistoryEntry:
    history_id: int
    sales_session_id: UUID
    creator_profile_id: int
    event_type: str
    previous_state: SalesSessionState | None
    new_state: SalesSessionState
    previous_progression_stage: SalesSessionProgression | None
    new_progression_stage: SalesSessionProgression
    purchase_intent_id: UUID | None
    actor_type: SalesSessionActorType
    actor_identifier: str | None
    reason: str | None
    occurred_at: datetime

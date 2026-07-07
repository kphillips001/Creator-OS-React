"""Provider-neutral Creator OS runtime control models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


class RuntimeMode(str, Enum):
    OFFLINE = "OFFLINE"
    OBSERVE = "OBSERVE"
    LIVE = "LIVE"


class RuntimeStatus(str, Enum):
    OFFLINE = "OFFLINE"
    OBSERVE = "OBSERVE"
    LIVE = "LIVE"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RuntimeObservation:
    observation_id: str
    creator_profile_id: str
    customer_id: str | None = None
    conversation_id: str | None = None
    message_text: str = ""
    suggested_reply: str | None = None
    suggested_offer: Mapping[str, Any] = field(default_factory=dict)
    suggested_delivery: Mapping[str, Any] = field(default_factory=dict)
    suggested_follow_up: Mapping[str, Any] = field(default_factory=dict)
    provider: str = "telegram"
    created_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeControlState:
    creator_profile_id: str
    mode: RuntimeMode = RuntimeMode.OFFLINE
    status: RuntimeStatus = RuntimeStatus.OFFLINE
    current_runtime_provider: str = "telegram"
    last_started: datetime | None = None
    last_stopped: datetime | None = None
    active_conversations: int = 0
    pending_deliveries: int = 0
    pending_offers: int = 0
    observed_recommendations: tuple[RuntimeObservation, ...] = ()
    updated_at: datetime = field(default_factory=utc_now)
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeControlSnapshot:
    creator_profile_id: str
    runtime_status: RuntimeStatus
    current_mode: RuntimeMode
    last_started: datetime | None = None
    last_stopped: datetime | None = None
    active_conversations: int = 0
    pending_deliveries: int = 0
    pending_offers: int = 0
    current_runtime_provider: str = "telegram"
    observed_recommendations: tuple[RuntimeObservation, ...] = ()
    warning_banner: str = ""
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    summary: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeControlDecision:
    mode: RuntimeMode
    status: RuntimeStatus
    allow_decision_engine: bool
    allow_replies: bool
    allow_offers: bool
    allow_deliveries: bool
    observe_only: bool = False
    reason: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

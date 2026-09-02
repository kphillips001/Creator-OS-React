"""Standalone, noncommercial Free Engagement Teaser delivery domain."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


SEND_FREE_ENGAGEMENT_TEASER = "SEND_FREE_ENGAGEMENT_TEASER"


class FreeEngagementTeaserDeliveryState(str, Enum):
    CREATED = "CREATED"
    SENDING = "SENDING"
    TELEGRAM_ACCEPTED = "TELEGRAM_ACCEPTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class FreeEngagementTeaserOperation:
    operation_id: UUID
    correlation_id: str
    creator_profile_id: int
    fanvue_account_id: int
    fanvue_user_id: int
    conversation_thread_id: int
    telegram_chat_id: int
    inbound_telegram_message_id: int | None
    teaser_asset_id: int
    media_reference: str
    caption: str
    state: FreeEngagementTeaserDeliveryState
    outbound_telegram_message_id: int | None = None
    failure_reason: str | None = None
    created_at: datetime | None = None
    sending_at: datetime | None = None
    telegram_accepted_at: datetime | None = None
    confirmed_at: datetime | None = None
    failed_at: datetime | None = None
    updated_at: datetime | None = None
    engagement_strategy: str | None = None
    decision_reason_code: str | None = None
    decision_evidence: dict | None = None
    policy_version: str | None = None
    next_inbound_message_id: int | None = None
    next_inbound_at: datetime | None = None
    response_latency_seconds: int | None = None
    response_attribution: str | None = None


@dataclass(frozen=True)
class FreeEngagementTeaserPreparation:
    status: str
    action: str = SEND_FREE_ENGAGEMENT_TEASER
    operation: FreeEngagementTeaserOperation | None = None
    reason: str | None = None


@dataclass(frozen=True)
class FreeEngagementTeaserExecution:
    status: str
    executed: bool
    operation: FreeEngagementTeaserOperation | None = None
    reason: str | None = None

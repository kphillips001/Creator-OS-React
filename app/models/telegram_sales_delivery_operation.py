"""Durable boundary around one commercial Telegram delivery."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class TelegramSalesDeliveryState(str, Enum):
    CREATED = "CREATED"
    RETRYABLE = "RETRYABLE"
    SENDING = "SENDING"
    TELEGRAM_ACCEPTED = "TELEGRAM_ACCEPTED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class TelegramSalesDeliveryOperation:
    operation_id: UUID
    correlation_id: str
    creator_profile_id: int
    fanvue_account_id: int
    conversation_thread_id: int
    fanvue_user_id: int
    telegram_chat_id: int
    inbound_telegram_message_id: int
    outbound_telegram_message_id: int | None
    purchase_intent_id: UUID
    commercial_offering_id: UUID
    commercial_publication_id: UUID
    response_text: str
    delivery_payload: dict[str, Any]
    state: TelegramSalesDeliveryState
    failure_reason: str | None
    created_at: datetime
    sending_at: datetime | None
    telegram_accepted_at: datetime | None
    confirmed_at: datetime | None
    failed_at: datetime | None
    updated_at: datetime

"""Durable lifecycle for one ordinary reply to one Telegram inbound message."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class OrdinaryChatReplyState(str, Enum):
    PENDING_GENERATION = "PENDING_GENERATION"
    GENERATING = "GENERATING"
    GENERATED = "GENERATED"
    SENDING = "SENDING"
    SENT_CONFIRMED = "SENT_CONFIRMED"
    RETRYABLE = "RETRYABLE"
    SEND_UNCERTAIN = "SEND_UNCERTAIN"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True)
class OrdinaryChatReplyOperation:
    operation_id: UUID
    telegram_account_scope: str
    telegram_chat_id: int
    inbound_telegram_message_id: int
    inbound_sender_telegram_user_id: int
    inbound_message_text: str | None
    inbound_received_at: datetime | None
    conversation_thread_id: int | None
    correlation_id: str
    response_payload: dict[str, Any] | None
    response_text: str | None
    response_content_sha256: str | None
    delivery_payload: dict[str, Any] | None
    state: OrdinaryChatReplyState
    outbound_telegram_message_id: int | None
    generation_attempt_count: int
    send_attempt_count: int
    max_generation_attempts: int
    max_send_attempts: int
    claim_owner: str | None
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    next_retry_at: datetime | None
    last_error: str | None
    generated_at: datetime | None
    sending_at: datetime | None
    sent_confirmed_at: datetime | None
    uncertain_at: datetime | None
    failed_at: datetime | None
    created_at: datetime
    updated_at: datetime

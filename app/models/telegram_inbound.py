"""SDK-free contracts for normalized Telegram-like inbound messages."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TelegramInboundAttachment:
    attachment_id: str
    telegram_message_id: int
    telegram_chat_id: int
    telegram_user_id: int
    media_kind: str
    telegram_media_id: str
    mime_type: str | None = None
    original_filename: str | None = None
    reported_size_bytes: int | None = None
    width: int | None = None
    height: int | None = None
    grouped_id: str | None = None
    has_caption: bool = False
    received_at: datetime | None = None


@dataclass(frozen=True)
class TelegramInboundPayload:
    telegram_user_id: int
    telegram_chat_id: int
    message_text: str
    message_id: int
    chat_history: list[Any] = field(default_factory=list)
    correlation_id: str | None = None
    telegram_username: str | None = None
    telegram_display_name: str | None = None
    reply_to_message_id: int | None = None
    received_at: datetime | None = None
    sleep_context: dict[str, Any] = field(default_factory=dict)
    attachments: tuple[TelegramInboundAttachment, ...] = ()
    current_turn_visual_context: dict[str, Any] = field(default_factory=dict)
    quality_correction_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TelegramInboundResult:
    correlation_id: str
    telegram_chat_id: int
    telegram_user_id: int
    message_id: int
    engine_user_id: str
    response_text: str
    offer_authorized: bool
    offer_link: str | None
    blocked: bool
    error_code: str | None
    delivery_type: str | None = None
    delivery_mode: str | None = None
    delivery_requires_payment: bool | None = None
    delivery_payload: dict[str, Any] = field(default_factory=dict)
    diagnostic_metadata: dict[str, Any] = field(default_factory=dict)

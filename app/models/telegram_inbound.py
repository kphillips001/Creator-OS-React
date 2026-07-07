"""SDK-free contracts for normalized Telegram-like inbound messages."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TelegramInboundPayload:
    telegram_user_id: int
    telegram_chat_id: int
    message_text: str
    message_id: int
    chat_history: list[Any] = field(default_factory=list)
    correlation_id: str | None = None


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

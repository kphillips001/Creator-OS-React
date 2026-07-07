"""Channel-neutral contracts for invoking the conversation brain."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConversationGatewayInput:
    """Normalized input accepted at the application/brain boundary."""

    engine_user_id: str
    message_text: str
    chat_history: list[Any]
    correlation_id: str


@dataclass(frozen=True)
class ConversationGatewayOutput:
    """Normalized result returned without transport-specific behavior."""

    correlation_id: str
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

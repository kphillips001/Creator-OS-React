"""Channel-neutral contracts for invoking the conversation brain."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ConversationBrainContext:
    """Transport-neutral identity and execution context for one brain turn."""

    creator_profile_id: int | None
    customer_identifier: str
    conversation_identifier: str
    primary_sales_channel: str = "AI_CHAT"
    developer_mode: bool = False
    telegram_user_id: int | None = None
    telegram_chat_id: int | None = None
    fanvue_account_id: int | None = None
    external_fanvue_buyer_uuid: str | None = None
    fanvue_user_id: int | None = None
    conversation_thread_id: int | None = None
    purchase_acknowledgement_pending: bool = False
    purchase_acknowledgement_intent_id: str | None = None
    conversational_memory: dict[str, Any] = field(default_factory=dict)
    sleep_context: dict[str, Any] = field(default_factory=dict)
    customer_behavior_evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationGatewayInput:
    """Normalized input accepted at the application/brain boundary."""

    engine_user_id: str
    message_text: str
    chat_history: list[Any]
    correlation_id: str
    brain_context: ConversationBrainContext | None = None


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

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TelegramPrivateInboundMessage:
    inbound_id: UUID
    telegram_account_scope: str
    telegram_user_id: int
    telegram_chat_id: int
    telegram_message_id: int
    received_at: datetime
    customer_text: str
    has_media: bool
    media_types: tuple[str, ...] = field(default_factory=tuple)
    reconciliation_state: str = "CAPTURED"
    mapped_customer_id: int | None = None
    prospect_id: UUID | None = None


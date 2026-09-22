"""Durable Telegram Broadcast-to-private-chat attribution contracts."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CreatorContentEntryAttribution:
    attribution_id: str
    creator_profile_id: int
    publication_id: str
    token_digest: str
    source_platform: str = "telegram"
    provenance_method: str = "TELEGRAM_DIRECT_CHAT_DRAFT"
    status: str = "TOKEN_CREATED"
    token_created_at: datetime | None = None
    cta_attached_at: datetime | None = None
    last_error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CreatorContentEntryEvent:
    entry_event_id: str
    attribution_id: str
    creator_profile_id: int
    publication_id: str
    telegram_user_id: int
    telegram_chat_id: int
    inbound_telegram_message_id: int
    observed_at: datetime
    event_status: str = "ENTRY_OBSERVED"
    created_at: datetime | None = None

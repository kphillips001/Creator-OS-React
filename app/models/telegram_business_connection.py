"""Canonical Telegram Business connection lifecycle state."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class TelegramBusinessConnection:
    business_connection_id: str
    business_owner_telegram_user_id: int
    bot_telegram_user_id: int
    is_enabled: bool
    can_reply: bool
    rights: dict[str, Any]
    provider_updated_at: datetime
    observed_at: datetime
    superseded_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @property
    def usable(self) -> bool:
        return self.is_enabled and self.can_reply and self.superseded_at is None

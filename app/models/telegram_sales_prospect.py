"""Provider-independent Telegram prospect state before first Fanvue mapping."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TelegramSalesProspect:
    telegram_sales_prospect_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    telegram_user_id: int
    telegram_chat_id: int
    relationship_state: dict[str, Any] = field(default_factory=dict)
    preference_state: dict[str, Any] = field(default_factory=dict)
    inbound_message_count: int = 0
    first_observed_at: datetime | None = None
    last_observed_at: datetime | None = None
    graduated_mapping_id: int | None = None
    graduated_at: datetime | None = None

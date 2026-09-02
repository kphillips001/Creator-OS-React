"""Telegram-owned Session state before a verified Fanvue identity exists."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class TelegramProvisionalSalesSession:
    provisional_session_id: UUID
    telegram_sales_prospect_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    telegram_user_id: int
    telegram_chat_id: int
    photoshoot_reference: str
    session_strategy: str
    state: str
    progression_stage: str
    current_position: int
    configured_base_price_minor: int
    actual_fingerprint_price_minor: int | None
    first_purchase_intent_id: UUID | None
    first_purchase_recorded_at: datetime | None
    commercial_context: dict[str, Any] = field(default_factory=dict)
    mapped_sales_session_id: UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    graduated_at: datetime | None = None
    administratively_closed_at: datetime | None = None
    administrative_close_reason: str | None = None

"""Reconcile provider Business Connection lifecycle updates only."""

from __future__ import annotations

from datetime import datetime, timezone

from app.repositories.telegram_business_connection_repository import (
    TelegramBusinessConnectionRepository,
)


class TelegramBusinessConnectionService:
    def __init__(self, *, repository=None, bot_telegram_user_id: int):
        self.repository = repository or TelegramBusinessConnectionRepository()
        self.bot_telegram_user_id = int(bot_telegram_user_id)

    def capture(self, event):
        return self.repository.reconcile(
            business_connection_id=event.business_connection_id,
            business_owner_telegram_user_id=event.business_user_id,
            bot_telegram_user_id=self.bot_telegram_user_id,
            is_enabled=event.is_enabled,
            can_reply=event.rights.get("can_reply") is True,
            rights=event.rights,
            provider_updated_at=datetime.fromtimestamp(
                event.connected_at, tz=timezone.utc,
            ),
        )

    def active(self, *, business_owner_telegram_user_id: int):
        return self.repository.get_active(
            business_owner_telegram_user_id=int(business_owner_telegram_user_id),
            bot_telegram_user_id=self.bot_telegram_user_id,
        )

    def current(self, *, business_owner_telegram_user_id: int):
        return self.repository.get_current(
            business_owner_telegram_user_id=int(business_owner_telegram_user_id),
            bot_telegram_user_id=self.bot_telegram_user_id,
        )

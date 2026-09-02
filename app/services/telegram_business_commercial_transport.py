"""Commercial-only Telegram Business transport for private-chat offers."""

from __future__ import annotations

import os

from app.integrations.telegram.bot_api_sender import TelegramBotApiSender
from app.services.telegram_business_connection_service import (
    TelegramBusinessConnectionService,
)


class TelegramBusinessTransportError(RuntimeError):
    code = "BUSINESS_CONNECTION_UNAVAILABLE"


class TelegramBusinessConnectionDisabledError(TelegramBusinessTransportError):
    code = "BUSINESS_CONNECTION_DISABLED"


class TelegramBusinessReplyNotAllowedError(TelegramBusinessTransportError):
    code = "BUSINESS_REPLY_NOT_ALLOWED"


class TelegramBusinessCommercialTransport:
    """Resolve one active Ava connection and perform one verified send."""

    BUTTON_LABEL = "🔓 Unlock"

    def __init__(self, *, enabled=None, owner_user_id=None, bot_id=None,
                 connection_service=None, sender=None, bot_token=None):
        self.enabled = (
            str(os.getenv("TELEGRAM_BUSINESS_COMMERCIAL_TRANSPORT_ENABLED", "false"))
            .strip().lower() == "true"
            if enabled is None else bool(enabled)
        )
        self.owner_user_id = self._positive_id(
            owner_user_id if owner_user_id is not None
            else os.getenv("TELEGRAM_BUSINESS_OWNER_USER_ID", "")
        )
        self.bot_id = self._positive_id(
            bot_id if bot_id is not None
            else os.getenv("TELEGRAM_BUSINESS_BOT_ID", "")
        )
        self.connection_service = connection_service
        self.sender = sender
        self.bot_token = (
            bot_token if bot_token is not None
            else os.getenv("TELEGRAM_BOT_TOKEN_AVA", "")
        )

    def send_text(self, *, chat_id, message_text, button_label, button_url):
        if not self.enabled:
            raise TelegramBusinessTransportError(
                "Telegram Business commercial transport is disabled."
            )
        if not self.owner_user_id or not self.bot_id:
            raise TelegramBusinessTransportError(
                "Telegram Business identity configuration is unavailable."
            )
        service = self.connection_service or TelegramBusinessConnectionService(
            bot_telegram_user_id=self.bot_id,
        )
        current = getattr(service, "current", None)
        connection = (
            current(business_owner_telegram_user_id=self.owner_user_id)
            if callable(current) else service.active(
                business_owner_telegram_user_id=self.owner_user_id,
            )
        )
        if connection is None:
            raise TelegramBusinessTransportError(
                "No Telegram Business connection is available."
            )
        if not connection.is_enabled:
            raise TelegramBusinessConnectionDisabledError(
                "Telegram Business connection is disabled."
            )
        if not connection.can_reply:
            raise TelegramBusinessReplyNotAllowedError(
                "Telegram Business connection cannot reply."
            )
        active_connection = service.active(
            business_owner_telegram_user_id=self.owner_user_id,
        )
        if active_connection is None:
            raise TelegramBusinessTransportError(
                "No active Telegram Business connection is available."
            )
        if button_label != self.BUTTON_LABEL:
            raise ValueError("Private-chat commercial button label is not canonical.")
        sender = self.sender or TelegramBotApiSender(bot_token=self.bot_token)
        return sender.send_text(
            business_connection_id=active_connection.business_connection_id,
            chat_id=int(chat_id), message_text=message_text,
            button_label=button_label, button_url=button_url,
            expected_business_owner_user_id=self.owner_user_id,
            expected_business_bot_id=self.bot_id,
        )

    @staticmethod
    def _positive_id(value):
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

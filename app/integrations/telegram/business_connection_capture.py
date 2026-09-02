"""Isolated read-only capture for Telegram Business connection updates.

This module deliberately has no dependency on ConversationGateway or any
customer/commerce service.  It only inspects provider configuration events.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import requests


BOT_API_ALLOWED_UPDATES = (
    "message",
    "channel_post",
    "my_chat_member",
    "business_connection",
)


class TelegramBusinessConnectionCaptureError(RuntimeError):
    """Sanitized failure while inspecting Bot API configuration updates."""


@dataclass(frozen=True)
class TelegramBusinessConnectionEvent:
    update_id: int
    business_connection_id: str
    business_user_id: int
    business_user_first_name: str | None
    business_user_last_name: str | None
    business_user_username: str | None
    user_chat_id: int
    connected_at: int
    is_enabled: bool
    rights: Mapping[str, bool]


class TelegramBusinessConnectionCapture:
    """Peek at connection events without acknowledging or routing updates."""

    def __init__(self, *, bot_token: str, session=None) -> None:
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token is required")
        self._endpoint = (
            f"https://api.telegram.org/bot{bot_token.strip()}/getUpdates"
        )
        self._session = session or requests.Session()

    def configure_and_peek(self) -> tuple[TelegramBusinessConnectionEvent, ...]:
        try:
            response = self._session.get(
                self._endpoint,
                params={
                    "timeout": 0,
                    "limit": 100,
                    "allowed_updates": json.dumps(BOT_API_ALLOWED_UPDATES),
                },
                timeout=10,
            )
            response.raise_for_status()
            payload: Any = response.json()
        except Exception:
            raise TelegramBusinessConnectionCaptureError(
                "Telegram Business connection capture failed."
            ) from None
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise TelegramBusinessConnectionCaptureError(
                "Telegram returned an invalid Business connection response."
            )
        updates = payload.get("result")
        if not isinstance(updates, list):
            raise TelegramBusinessConnectionCaptureError(
                "Telegram Business connection updates were invalid."
            )
        captured = []
        for update in updates:
            event = self._parse(update)
            if event is not None:
                captured.append(event)
        return tuple(captured)

    @staticmethod
    def _parse(update: Any) -> TelegramBusinessConnectionEvent | None:
        if not isinstance(update, Mapping):
            return None
        connection = update.get("business_connection")
        if not isinstance(connection, Mapping):
            return None
        user = connection.get("user")
        rights = connection.get("rights")
        if not isinstance(user, Mapping) or not isinstance(rights, Mapping):
            return None
        try:
            return TelegramBusinessConnectionEvent(
                update_id=int(update["update_id"]),
                business_connection_id=str(connection["id"]),
                business_user_id=int(user["id"]),
                business_user_first_name=(str(user.get("first_name") or "").strip() or None),
                business_user_last_name=(str(user.get("last_name") or "").strip() or None),
                business_user_username=(str(user.get("username") or "").strip() or None),
                user_chat_id=int(connection["user_chat_id"]),
                connected_at=int(connection["date"]),
                is_enabled=connection.get("is_enabled") is True,
                rights={str(key): value is True for key, value in rights.items()},
            )
        except (KeyError, TypeError, ValueError):
            return None

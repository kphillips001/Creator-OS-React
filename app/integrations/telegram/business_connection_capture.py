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
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
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


@dataclass(frozen=True)
class TelegramBusinessPeerEvent:
    update_id: int
    event_type: str
    business_connection_id: str
    telegram_peer_user_id: int
    telegram_chat_id: int
    telegram_message_id: int
    provider_timestamp: int | None
    sender_telegram_user_id: int | None


class TelegramBusinessConnectionCapture:
    """Peek at connection events without acknowledging or routing updates."""

    def __init__(self, *, bot_token: str, session=None) -> None:
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token is required")
        self._endpoint = (
            f"https://api.telegram.org/bot{bot_token.strip()}/getUpdates"
        )
        self._session = session or requests.Session()

    def configure_and_peek(self) -> tuple[
        TelegramBusinessConnectionEvent | TelegramBusinessPeerEvent, ...
    ]:
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
            captured.extend(self.parse(update))
        return tuple(captured)

    @classmethod
    def parse(cls, update: Any) -> tuple[
        TelegramBusinessConnectionEvent | TelegramBusinessPeerEvent, ...
    ]:
        connection = cls._parse(update)
        if connection is not None:
            return (connection,)
        if not isinstance(update, Mapping):
            return ()
        for event_type in ("business_message", "edited_business_message"):
            message = update.get(event_type)
            if isinstance(message, Mapping):
                event = cls._parse_peer_message(update, event_type, message)
                return (event,) if event is not None else ()
        deleted = update.get("deleted_business_messages")
        if isinstance(deleted, Mapping):
            return cls._parse_deleted_peer_messages(update, deleted)
        return ()

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

    @staticmethod
    def _parse_peer_message(update, event_type, message):
        chat = message.get("chat")
        sender = message.get("from")
        if not isinstance(chat, Mapping):
            return None
        try:
            chat_id = int(chat["id"])
            if chat_id <= 0 or str(chat.get("type") or "private") != "private":
                return None
            timestamp = message.get("edit_date") or message.get("date")
            return TelegramBusinessPeerEvent(
                update_id=int(update["update_id"]),
                event_type=event_type,
                business_connection_id=str(message["business_connection_id"]),
                telegram_peer_user_id=chat_id,
                telegram_chat_id=chat_id,
                telegram_message_id=int(message["message_id"]),
                provider_timestamp=int(timestamp) if timestamp is not None else None,
                sender_telegram_user_id=(
                    int(sender["id"]) if isinstance(sender, Mapping)
                    and sender.get("id") is not None else None
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _parse_deleted_peer_messages(update, deleted):
        chat = deleted.get("chat")
        message_ids = deleted.get("message_ids")
        if not isinstance(chat, Mapping) or not isinstance(message_ids, list):
            return ()
        try:
            chat_id = int(chat["id"])
            connection_id = str(deleted["business_connection_id"])
            update_id = int(update["update_id"])
            if chat_id <= 0 or not connection_id:
                return ()
            return tuple(
                TelegramBusinessPeerEvent(
                    update_id=update_id,
                    event_type="deleted_business_messages",
                    business_connection_id=connection_id,
                    telegram_peer_user_id=chat_id,
                    telegram_chat_id=chat_id,
                    telegram_message_id=int(message_id),
                    provider_timestamp=None,
                    sender_telegram_user_id=None,
                )
                for message_id in message_ids
                if isinstance(message_id, int) and not isinstance(message_id, bool)
            )
        except (KeyError, TypeError, ValueError):
            return ()

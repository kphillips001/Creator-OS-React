"""Telethon user-account transport for private plain-text messages."""

import logging
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from telethon import events

from app.models.telegram_inbound import TelegramInboundPayload


InboundHandler = Callable[[TelegramInboundPayload], Awaitable[None]]


class TelethonTransportError(RuntimeError):
    """A sanitized user-account transport failure."""


class TelethonUserTransport:
    """Receive and send Telegram DMs through an authorized user session."""

    def __init__(
        self,
        *,
        client: Any,
        logger: logging.Logger | None = None,
    ) -> None:
        if client is None:
            raise ValueError("client is required")
        self._client = client
        self._logger = logger or logging.getLogger("telethon-transport")
        self._inbound_handler: InboundHandler | None = None
        self._handler_registered = False

    def set_inbound_handler(self, handler: InboundHandler) -> None:
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._inbound_handler = handler

    async def start(self) -> None:
        """Connect an existing authorized session and register one handler."""

        try:
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise TelethonTransportError(
                    "Telethon session is not authorized; run telethon_login first."
                )
            if not self._handler_registered:
                self._client.add_event_handler(
                    self._receive_event,
                    events.NewMessage(incoming=True),
                )
                self._handler_registered = True
        except TelethonTransportError:
            raise
        except Exception as error:
            self._logger.exception(
                "[TELETHON ERROR] operation=startup chat_id=unknown "
                "exception_type=%s exception_message=%s",
                type(error).__name__,
                str(error),
            )
            raise TelethonTransportError("Telethon startup failed.") from None

    async def run_until_disconnected(self) -> None:
        try:
            await self._client.run_until_disconnected()
        except Exception as error:
            self._log_error("receive loop", error)
            raise TelethonTransportError("Telethon receive loop failed.") from None

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except Exception as error:
            self._log_error("disconnect", error)

    async def send_text(self, *, chat_id: int, message_text: str) -> int | None:
        if isinstance(chat_id, bool) or not isinstance(chat_id, int) or chat_id <= 0:
            raise ValueError("chat_id must be a positive private-chat identifier")
        if not isinstance(message_text, str) or not message_text.strip():
            raise ValueError("message_text must be a non-empty string")

        self._logger.info(
            "[TELETHON SEND] chat_id=%s message_length=%s",
            chat_id,
            len(message_text),
        )
        try:
            message = await self._client.send_message(chat_id, message_text)
            message_id = getattr(message, "id", None)
            return message_id if isinstance(message_id, int) else None
        except Exception as error:
            self._log_error("send", error, chat_id=chat_id)
            raise TelethonTransportError("Telethon send failed.") from None

    async def send_asset(
        self, *, chat_id: int, asset_path: str, message_text: str = "",
    ) -> int | None:
        if isinstance(chat_id, bool) or not isinstance(chat_id, int) or chat_id <= 0:
            raise ValueError("chat_id must be a positive private-chat identifier")
        path = Path(str(asset_path or ""))
        if not path.is_file():
            raise ValueError("asset_path must reference an existing file")
        try:
            message = await self._client.send_file(
                chat_id, str(path), caption=message_text.strip() or None,
            )
            message_id = getattr(message, "id", None)
            return message_id if isinstance(message_id, int) else None
        except Exception as error:
            self._log_error("send_asset", error, chat_id=chat_id)
            raise TelethonTransportError("Telethon Asset send failed.") from None

    async def _receive_event(self, event: Any) -> None:
        try:
            payload = await self.normalize_event(event)
            if payload is None:
                return

            self._logger.info(
                "[TELETHON RECEIVE] chat_id=%s user_id=%s message_id=%s "
                "message_length=%s",
                payload.telegram_chat_id,
                payload.telegram_user_id,
                payload.message_id,
                len(payload.message_text),
            )
            if self._inbound_handler is None:
                raise TelethonTransportError("Inbound handler is not configured.")
            await self._inbound_handler(payload)
        except Exception as error:
            self._log_error("receive", error)

    @staticmethod
    async def normalize_event(event: Any) -> TelegramInboundPayload | None:
        """Normalize one incoming private Telethon text event."""

        if event is None:
            return None
        if getattr(event, "out", False) or not getattr(event, "is_private", False):
            return None

        message_text = getattr(event, "raw_text", None)
        if not isinstance(message_text, str) or not message_text.strip():
            return None

        sender = await event.get_sender()
        if sender is None or getattr(sender, "bot", False):
            return None

        telegram_user_id = getattr(sender, "id", None)
        telegram_chat_id = getattr(event, "chat_id", None)
        message_id = getattr(event, "id", None)
        if not all(
            isinstance(value, int) and not isinstance(value, bool) and value > 0
            for value in (telegram_user_id, telegram_chat_id, message_id)
        ):
            return None

        return TelegramInboundPayload(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            message_text=message_text.strip(),
            message_id=message_id,
        )

    def _log_error(
        self,
        operation: str,
        error: Exception,
        *,
        chat_id: int | None = None,
    ) -> None:
        self._logger.error(
            "[TELETHON ERROR] operation=%s chat_id=%s error_type=%s",
            operation,
            chat_id if chat_id is not None else "unknown",
            type(error).__name__,
        )

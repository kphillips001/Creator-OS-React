"""Minimal private-chat, plain-text Telegram Bot API sender."""

import logging
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import requests


TELEGRAM_TEXT_LIMIT = 4096


class TelegramOutboundSendError(RuntimeError):
    """A sanitized Telegram outbound delivery failure."""


class TelegramBotApiSender:
    """Send one plain-text message to a private Telegram chat."""

    def __init__(
        self,
        *,
        bot_token: str,
        session: requests.Session | None = None,
        timeout_seconds: int = 15,
        logger: logging.Logger | None = None,
    ) -> None:
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token is required")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive integer")

        self._endpoint = (
            f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
        )
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds
        self._logger = logger or logging.getLogger("telegram-bot-api-sender")

    def send_text(self, *, chat_id: int, message_text: str) -> None:
        self._validate_private_chat_id(chat_id)
        self._validate_message_text(message_text)

        self._logger.info(
            "[TELEGRAM SEND]\nchat_id=%s\nmessage_length=%s",
            chat_id,
            len(message_text),
        )

        try:
            response = self._session.post(
                self._endpoint,
                json={"chat_id": chat_id, "text": message_text},
                timeout=self._timeout_seconds,
            )
        except Exception:
            self._logger.error(
                "[TELEGRAM API RESPONSE] status=request_failed"
            )
            raise TelegramOutboundSendError(
                "Telegram sendMessage request failed."
            ) from None

        try:
            payload: Any = response.json()
        except Exception:
            payload = None

        api_ok = isinstance(payload, Mapping) and payload.get("ok") is True
        self._logger.info(
            "[TELEGRAM API RESPONSE] status_code=%s ok=%s",
            getattr(response, "status_code", "unknown"),
            api_ok,
        )

        try:
            response.raise_for_status()
        except Exception:
            raise TelegramOutboundSendError(
                "Telegram sendMessage request failed."
            ) from None

        if not api_ok:
            raise TelegramOutboundSendError(
                "Telegram rejected the sendMessage request."
            )

    def send_asset(
        self, *, chat_id: int, asset_path: str, message_text: str = "",
    ) -> int | None:
        self._validate_private_chat_id(chat_id)
        path = Path(str(asset_path or ""))
        if not path.is_file():
            raise ValueError("asset_path must reference an existing file")
        endpoint = self._endpoint.replace("/sendMessage", "/sendPhoto")
        try:
            with path.open("rb") as media:
                response = self._session.post(
                    endpoint,
                    data={"chat_id": chat_id, "caption": message_text.strip()},
                    files={"photo": (path.name, media)},
                    timeout=self._timeout_seconds,
                )
            payload = response.json()
            response.raise_for_status()
        except Exception:
            raise TelegramOutboundSendError("Telegram sendPhoto request failed.") from None
        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise TelegramOutboundSendError("Telegram rejected the Asset send request.")
        message_id = (payload.get("result") or {}).get("message_id")
        return message_id if isinstance(message_id, int) else None

    @staticmethod
    def _validate_private_chat_id(chat_id: int) -> None:
        if isinstance(chat_id, bool) or not isinstance(chat_id, int):
            raise ValueError("chat_id must be a positive integer")
        if chat_id <= 0:
            raise ValueError("Only private Telegram chat IDs are supported")

    @staticmethod
    def _validate_message_text(message_text: str) -> None:
        if not isinstance(message_text, str) or not message_text.strip():
            raise ValueError("message_text must be a non-empty string")
        if len(message_text) > TELEGRAM_TEXT_LIMIT:
            raise ValueError(
                f"message_text must not exceed {TELEGRAM_TEXT_LIMIT} characters"
            )

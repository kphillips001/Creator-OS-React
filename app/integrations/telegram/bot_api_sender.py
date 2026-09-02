"""Minimal private-chat, plain-text Telegram Bot API sender."""

import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import requests

from app.services.telegram_image_normalization_service import TelegramImageNormalizationService


TELEGRAM_TEXT_LIMIT = 4096


class TelegramOutboundSendError(RuntimeError):
    """A sanitized Telegram outbound delivery failure."""

    code = "BUSINESS_SEND_REJECTED"


class TelegramOutboundSendAmbiguousError(ConnectionError):
    code = "BUSINESS_SEND_AMBIGUOUS"


class TelegramBusinessPeerUsageMissingError(RuntimeError):
    code = "BUSINESS_PEER_USAGE_MISSING"


class TelegramBusinessProviderVerificationError(RuntimeError):
    code = "BUSINESS_PROVIDER_VERIFICATION_FAILED"


@dataclass(frozen=True)
class TelegramBotSendReceipt:
    id: int
    final_text: str
    actionable_destination_attached: bool
    provider_action_verified: bool
    provider_markup_included: bool
    provider_markup_verified: bool
    attachment_mode: str
    business_connection_id: str | None = None
    sender_business_bot: dict[str, Any] | None = None
    sender: dict[str, Any] | None = None
    provider_payload: dict[str, Any] | None = None


class TelegramBotApiSender:
    """Send one plain-text message to a private Telegram chat."""

    def __init__(
        self,
        *,
        bot_token: str,
        session: requests.Session | None = None,
        timeout_seconds: int = 15,
        logger: logging.Logger | None = None,
        image_normalizer: TelegramImageNormalizationService | None = None,
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
        self._image_normalizer = image_normalizer or TelegramImageNormalizationService()

    def send_text(
        self, *, chat_id: int, message_text: str,
        button_label: str | None = None, button_url: str | None = None,
        business_connection_id: str | None = None,
        expected_business_owner_user_id: int | None = None,
        expected_business_bot_id: int | None = None,
    ) -> int | TelegramBotSendReceipt:
        self._validate_private_chat_id(chat_id)
        self._validate_message_text(message_text)

        self._logger.info(
            "[TELEGRAM SEND]\nchat_id=%s\nmessage_length=%s",
            chat_id,
            len(message_text),
        )

        request_payload = {
            "chat_id": chat_id, "text": message_text,
            **({"business_connection_id": business_connection_id}
               if business_connection_id else {}),
            **({"reply_markup": {"inline_keyboard": [[{
                "text": button_label, "url": button_url,
            }]]}} if button_label and button_url else {}),
        }
        try:
            response = self._session.post(
                self._endpoint,
                json=request_payload,
                timeout=self._timeout_seconds,
            )
        except Exception:
            self._logger.error(
                "[TELEGRAM API RESPONSE] status=request_failed"
            )
            raise TelegramOutboundSendAmbiguousError(
                "Telegram sendMessage acceptance is unknown."
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

        if not api_ok:
            description = str(
                payload.get("description") if isinstance(payload, Mapping) else ""
            )
            if "BUSINESS_PEER_USAGE_MISSING" in description:
                raise TelegramBusinessPeerUsageMissingError(
                    "Telegram Business peer is not currently reply-eligible."
                )
            raise TelegramOutboundSendError(
                "Telegram rejected the sendMessage request."
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message object."
            )
        message_id = result.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message ID."
            )
        if not business_connection_id:
            return message_id
        keyboard = ((result.get("reply_markup") or {}).get("inline_keyboard") or [])
        provider_button = (
            keyboard[0][0]
            if keyboard and isinstance(keyboard[0], list) and keyboard[0]
            else {}
        )
        sender = dict(result.get("from") or {})
        sender_bot = dict(result.get("sender_business_bot") or {})
        verified = all((
            result.get("business_connection_id") == business_connection_id,
            (result.get("chat") or {}).get("id") == chat_id,
            result.get("text") == message_text,
            provider_button.get("text") == button_label,
            provider_button.get("url") == button_url,
            expected_business_owner_user_id is None
            or sender.get("id") == expected_business_owner_user_id,
            expected_business_bot_id is None
            or sender_bot.get("id") == expected_business_bot_id,
        ))
        if not verified:
            raise TelegramBusinessProviderVerificationError(
                "Telegram Business message failed provider verification."
            )
        return TelegramBotSendReceipt(
            id=message_id, final_text=message_text,
            actionable_destination_attached=True,
            provider_action_verified=True,
            provider_markup_included=True,
            provider_markup_verified=True,
            attachment_mode="TELEGRAM_BUSINESS_INLINE_BUTTON",
            business_connection_id=business_connection_id,
            sender_business_bot=sender_bot, sender=sender,
            provider_payload=dict(result),
        )

    def send_asset(
        self, *, chat_id: int, asset_path: str, message_text: str = "",
    ) -> int | None:
        self._validate_private_chat_id(chat_id)
        path = Path(str(asset_path or ""))
        if not path.is_file():
            raise ValueError("asset_path must reference an existing file")
        endpoint = self._endpoint.replace("/sendMessage", "/sendPhoto")
        upload_path = (
            self._image_normalizer.normalize(path).path
            if self._image_normalizer.is_supported_image(path)
            else path
        )
        try:
            with upload_path.open("rb") as media:
                response = self._session.post(
                    endpoint,
                    data={"chat_id": chat_id, "caption": message_text.strip()},
                    files={"photo": (upload_path.name, media)},
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

"""Minimal private-chat, plain-text Telegram Bot API sender."""

from app.models.telegram_transport_contract import validate_local_payload

import json
from datetime import datetime, timezone
from hashlib import sha256
import logging
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import requests

from app.models.telegram_transport_contract import DeliveryCertainty, TelegramPreflightError, TelegramReachability
from app.services.telegram_transport_boundary import capture_acknowledgement

from app.services.telegram_image_normalization_service import TelegramImageNormalizationService


TELEGRAM_TEXT_LIMIT = 4096


class TelegramOutboundSendError(RuntimeError):
    """A sanitized Telegram outbound delivery failure."""

    certainty = DeliveryCertainty.REJECTED
    code = "BUSINESS_SEND_REJECTED"

    def __init__(self, message, *, http_status=None, telegram_error_code=None,
                 telegram_description=None):
        super().__init__(message)
        self.http_status = http_status
        self.telegram_error_code = telegram_error_code
        self.telegram_description = telegram_description

    @property
    def definitive_not_delivered(self) -> bool:
        """A parsed Bot API rejection proves Telegram did not accept the send."""
        return True

    @property
    def peer_id_invalid(self) -> bool:
        return "PEER_ID_INVALID" in str(self.telegram_description or "").upper()

    @property
    def non_retryable(self) -> bool:
        """Permanent client rejections need separately authorized repair."""
        status = self.http_status
        code = self.telegram_error_code
        return self.peer_id_invalid or (
            (isinstance(status, int) and 400 <= status < 500 and status != 429)
            or (isinstance(code, int) and 400 <= code < 500 and code != 429)
        )


class TelegramOutboundSendAmbiguousError(ConnectionError):
    certainty = DeliveryCertainty.UNKNOWN
    code = "BUSINESS_SEND_AMBIGUOUS"


class TelegramBusinessPeerUsageMissingError(RuntimeError):
    certainty = DeliveryCertainty.REJECTED
    code = "BUSINESS_PEER_USAGE_MISSING"


class TelegramBusinessProviderVerificationError(ConnectionError):
    certainty = DeliveryCertainty.UNKNOWN

    def __init__(self, message, *, provider_evidence=None):
        super().__init__(message)
        self.provider_evidence = dict(provider_evidence or {})
        if self.provider_evidence.get("telegram_message_id"):
            self.certainty = DeliveryCertainty.ACCEPTED

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
    provider_media_included: bool = False


class TelegramBotApiSender:
    """Send one plain-text message to a private Telegram chat."""

    validate_delivery = staticmethod(validate_local_payload)

    def __init__(
        self,
        *,
        bot_token: str,
        session: requests.Session | None = None,
        timeout_seconds: int = 15,
        logger: logging.Logger | None = None,
        image_normalizer: TelegramImageNormalizationService | None = None,
        peer_evidence=None, sender_scope=None,
    ) -> None:
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token is required")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a positive integer")

        self._known_peers = {}
        self._peer_evidence = peer_evidence or self._known_peers.get
        bot_identity = bot_token.partition(":")[0]
        self._bot_id = int(bot_identity) if bot_identity.isdigit() else None
        self.sender_scope = sender_scope or "bot:" + (str(self._bot_id) if self._bot_id else sha256(bot_token.encode()).hexdigest()[:16])
        self._endpoint = (
            f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
        )
        self._session = session or requests.Session()
        self._timeout_seconds = timeout_seconds
        self._logger = logger or logging.getLogger("telegram-bot-api-sender")
        self._image_normalizer = image_normalizer or TelegramImageNormalizationService()

    def observe_inbound(self, chat_id):
        """Only called for an inbound obtained by this sender's configured bot runtime."""
        self._validate_private_chat_id(chat_id)
        self._known_peers[chat_id] = TelegramReachability("BOT_API", self.sender_scope,
            chat_id, "BOT_INBOUND", datetime.now(timezone.utc), sender_id=self._bot_id)

    def prepare_delivery(self, *, chat_id, requirements):
        self._validate_private_chat_id(chat_id)
        evidence = self._peer_evidence(chat_id) if callable(self._peer_evidence) else None
        if evidence is None or evidence.transport != "BOT_API" or evidence.sender_scope != self.sender_scope or evidence.peer_id != chat_id:
            raise TelegramPreflightError("No peer evidence for this bot identity.")
        evidence.validate(requirements)
        return evidence

    def send_text(
        self, *, chat_id: int, message_text: str,
        button_label: str | None = None, button_url: str | None = None,
        business_connection_id: str | None = None,
        expected_business_owner_user_id: int | None = None,
        expected_business_bot_id: int | None = None,
        disable_link_preview: bool = False,
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
            **({"link_preview_options": {"is_disabled": True}}
               if disable_link_preview else {}),
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

        if not api_ok and not (
            isinstance(payload, Mapping) and payload.get("ok") is False
            and isinstance(payload.get("error_code"), int)
            and not isinstance(payload.get("error_code"), bool)
            and isinstance(payload.get("description"), str)
            and payload.get("description")
        ):
            raise TelegramOutboundSendAmbiguousError(
                "Telegram returned an unreadable or malformed acceptance response.")
        if not api_ok:
            description = str(
                payload.get("description") if isinstance(payload, Mapping) else ""
            )
            if "BUSINESS_PEER_USAGE_MISSING" in description:
                raise TelegramBusinessPeerUsageMissingError(
                    "Telegram Business peer is not currently reply-eligible."
                )
            status = getattr(response, "status_code", None)
            error_code = payload.get("error_code") if isinstance(payload, Mapping) else None
            raise TelegramOutboundSendError(
                "Telegram rejected sendMessage "
                f"(HTTP {status if status is not None else 'unknown'}, "
                f"error_code {error_code if error_code is not None else 'unknown'}): "
                f"{description or 'No provider description.'}",
                http_status=status, telegram_error_code=error_code,
                telegram_description=description or None,
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message object."
            )
        message_id = result.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message ID."
            )
        capture_acknowledgement(message_id,
            business_connection_id=result.get("business_connection_id"),
            provider_chat_id=(result.get("chat") or {}).get("id") if isinstance(result.get("chat"), Mapping) else None,
            provider_sender_id=(result.get("from") or {}).get("id") if isinstance(result.get("from"), Mapping) else None)
        if not business_connection_id:
            if button_label and button_url:
                self._verify_url_action(result, message_id, button_label, button_url)
                return TelegramBotSendReceipt(message_id, message_text, True, True,
                    True, True, "BOT_API_URL_BUTTON")
            return message_id
        keyboard = ((result.get("reply_markup") or {}).get("inline_keyboard") or [])
        provider_button = (
            keyboard[0][0]
            if keyboard and isinstance(keyboard[0], list) and keyboard[0]
            else {}
        )
        sender = dict(result.get("from") or {})
        sender_bot = dict(result.get("sender_business_bot") or {})
        button_verified = (
            provider_button.get("text") == button_label
            and provider_button.get("url") == button_url
        ) if button_label and button_url else not keyboard
        verified = all((
            result.get("business_connection_id") == business_connection_id,
            (result.get("chat") or {}).get("id") == chat_id,
            result.get("text") == message_text,
            button_verified,
            expected_business_owner_user_id is None
            or sender.get("id") == expected_business_owner_user_id,
            expected_business_bot_id is None
            or sender_bot.get("id") == expected_business_bot_id,
        ))
        if not verified:
            raise TelegramBusinessProviderVerificationError(
                "Telegram Business message failed provider verification.",
                provider_evidence={"telegram_message_id": message_id, "business_connection_id": business_connection_id, "accepted": True}
            )
        return TelegramBotSendReceipt(
            id=message_id, final_text=message_text,
            actionable_destination_attached=bool(button_label and button_url),
            provider_action_verified=True,
            provider_markup_included=bool(button_label and button_url),
            provider_markup_verified=button_verified,
            attachment_mode=("TELEGRAM_BUSINESS_INLINE_BUTTON"
                             if button_label and button_url else "TELEGRAM_BUSINESS_TEXT"),
            business_connection_id=business_connection_id,
            sender_business_bot=sender_bot, sender=sender,
            provider_payload=dict(result),
        )

    def send_asset(
        self, *, chat_id: int, asset_path: str, message_text: str = "",
        button_label: str | None = None, button_url: str | None = None,
        business_connection_id: str | None = None,
        expected_business_owner_user_id: int | None = None,
        expected_business_bot_id: int | None = None,
        disable_link_preview: bool = False,
    ) -> int | TelegramBotSendReceipt | None:
        self._validate_private_chat_id(chat_id)
        if (button_label is None) != (button_url is None):
            raise ValueError("Telegram button label and URL must be supplied together.")
        if len(message_text) > 1024:
            raise ValueError("Telegram photo captions must not exceed 1024 characters")
        path = Path(str(asset_path or ""))
        if not path.is_file():
            raise ValueError("asset_path must reference an existing file")
        endpoint = self._endpoint.replace("/sendMessage", "/sendPhoto")
        upload_path = (
            self._image_normalizer.normalize(path).path
            if self._image_normalizer.is_supported_image(path)
            else path
        )
        request_data = {
            "chat_id": chat_id, "caption": message_text.strip(),
            **({"business_connection_id": business_connection_id}
               if business_connection_id else {}),
            **({"reply_markup": json.dumps({"inline_keyboard": [[{
                "text": button_label, "url": button_url,
            }]]})} if button_label and button_url else {}),
        }
        try:
            with upload_path.open("rb") as media:
                response = self._session.post(
                    endpoint,
                    data=request_data,
                    files={"photo": (upload_path.name, media)},
                    timeout=self._timeout_seconds,
                )
        except Exception:
            self._logger.error("[TELEGRAM PHOTO RESPONSE] status=request_failed")
            raise TelegramOutboundSendAmbiguousError(
                "Telegram sendPhoto acceptance is unknown."
            ) from None
        try:
            payload = response.json()
        except Exception:
            self._logger.error(
                "[TELEGRAM PHOTO RESPONSE] status_code=%s payload=unreadable",
                getattr(response, "status_code", "unknown"),
            )
            raise TelegramOutboundSendAmbiguousError(
                "Telegram sendPhoto acceptance could not be verified."
            ) from None
        api_ok = isinstance(payload, Mapping) and payload.get("ok") is True
        self._logger.info(
            "[TELEGRAM PHOTO RESPONSE] status_code=%s ok=%s",
            getattr(response, "status_code", "unknown"), api_ok,
        )
        if not api_ok and not (
            isinstance(payload, Mapping) and payload.get("ok") is False
            and isinstance(payload.get("error_code"), int)
            and not isinstance(payload.get("error_code"), bool)
            and isinstance(payload.get("description"), str)
            and payload.get("description")
        ):
            raise TelegramOutboundSendAmbiguousError(
                "Telegram returned an unreadable or malformed acceptance response.")
        if not api_ok:
            status = getattr(response, "status_code", None)
            error_code = payload.get("error_code") if isinstance(payload, Mapping) else None
            description = str(
                payload.get("description") if isinstance(payload, Mapping) else ""
            )
            raise TelegramOutboundSendError(
                "Telegram rejected sendPhoto "
                f"(HTTP {status if status is not None else 'unknown'}, "
                f"error_code {error_code if error_code is not None else 'unknown'}): "
                f"{description or 'No provider description.'}",
                http_status=status, telegram_error_code=error_code,
                telegram_description=description or None,
            )
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message object.")
        message_id = result.get("message_id")
        if not isinstance(message_id, int) or isinstance(message_id, bool) or message_id <= 0:
            raise TelegramBusinessProviderVerificationError(
                "Telegram acceptance lacked a provider message ID.")
        capture_acknowledgement(message_id,
            business_connection_id=result.get("business_connection_id"),
            provider_chat_id=(result.get("chat") or {}).get("id") if isinstance(result.get("chat"), Mapping) else None,
            provider_sender_id=(result.get("from") or {}).get("id") if isinstance(result.get("from"), Mapping) else None)
        if not business_connection_id:
            if not result.get("photo") or result.get("caption", "") != message_text.strip():
                raise TelegramBusinessProviderVerificationError(
                    "Telegram photo/caption verification failed.",
                    provider_evidence={"telegram_message_id": message_id, "accepted": True})
            if button_label and button_url:
                self._verify_url_action(result, message_id, button_label, button_url)
            return TelegramBotSendReceipt(message_id, message_text.strip(), bool(button_url), True,
                bool(button_url), True, "BOT_API_PHOTO", provider_media_included=True)
        keyboard = ((result.get("reply_markup") or {}).get("inline_keyboard") or [])
        provider_button = keyboard[0][0] if keyboard and keyboard[0] else {}
        sender = dict(result.get("from") or {})
        sender_bot = dict(result.get("sender_business_bot") or {})
        button_verified = (
            provider_button.get("text") == button_label
            and provider_button.get("url") == button_url
        ) if button_label and button_url else True
        photo = result.get("photo") or []
        verified = all((
            result.get("business_connection_id") == business_connection_id,
            (result.get("chat") or {}).get("id") == chat_id,
            result.get("caption", "") == message_text.strip(),
            bool(photo), button_verified,
            expected_business_owner_user_id is None
            or sender.get("id") == expected_business_owner_user_id,
            expected_business_bot_id is None
            or sender_bot.get("id") == expected_business_bot_id,
        ))
        if not verified:
            raise TelegramBusinessProviderVerificationError(
                "Telegram Business media message failed provider verification.",
                provider_evidence={"telegram_message_id": message_id, "business_connection_id": business_connection_id, "accepted": True})
        return TelegramBotSendReceipt(
            id=message_id, final_text=message_text.strip(),
            actionable_destination_attached=bool(button_url), provider_action_verified=True,
            provider_markup_included=bool(button_url), provider_markup_verified=button_verified,
            attachment_mode=("TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON" if button_url else "TELEGRAM_BUSINESS_MEDIA"),
            business_connection_id=business_connection_id,
            sender_business_bot=sender_bot, sender=sender,
            provider_payload=dict(result), provider_media_included=True,
        )

    @staticmethod
    def _verify_url_action(result, message_id, label, url):
        markup = result.get("reply_markup")
        rows = markup.get("inline_keyboard", []) if isinstance(markup, Mapping) else []
        if not any(isinstance(button, Mapping) and button.get("text") == label and button.get("url") == url
                   for row in rows if isinstance(row, list) for button in row):
            raise TelegramBusinessProviderVerificationError(
                "Telegram accepted the message but the required URL action was not verified.",
                provider_evidence={"telegram_message_id": message_id, "accepted": True})

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

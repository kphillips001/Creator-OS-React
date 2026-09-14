"""Telethon user-account transport for private plain-text messages."""

import logging
import asyncio
import time
import io
from uuid import NAMESPACE_URL, uuid5
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Awaitable, Callable
from typing import Any

from telethon import Button, events
from telethon.tl import functions, types

from app.models.telegram_inbound import TelegramInboundPayload
from app.models.telegram_inbound import TelegramInboundAttachment
from app.services.telegram_image_normalization_service import TelegramImageNormalizationService


InboundHandler = Callable[[TelegramInboundPayload], Awaitable[None]]


class TelethonTransportError(RuntimeError):
    """A sanitized user-account transport failure."""


class TelethonAuthorizationRequiredError(TelethonTransportError):
    """The configured session cannot run without explicit operator authorization."""


class TelethonTransientError(TelethonTransportError):
    """A connection failure that can be retried without operator intervention."""


class TelethonCommercialVerificationError(ConnectionError, TelethonTransportError):
    """Telegram accepted a send whose commercial action could not be verified."""


@dataclass(frozen=True)
class TelethonSendReceipt:
    id: int
    final_text: str
    actionable_destination_attached: bool
    provider_action_verified: bool
    provider_markup_included: bool
    provider_markup_verified: bool
    attachment_mode: str | None = None


class TelethonUserTransport:
    """Receive and send Telegram DMs through an authorized user session."""

    def __init__(
        self,
        *,
        client: Any,
        logger: logging.Logger | None = None,
        image_normalizer: TelegramImageNormalizationService | None = None,
    ) -> None:
        if client is None:
            raise ValueError("client is required")
        self._client = client
        self._logger = logger or logging.getLogger("telethon-transport")
        self._inbound_handler: InboundHandler | None = None
        self._handler_registered = False
        self._image_normalizer = image_normalizer or TelegramImageNormalizationService()

    def set_inbound_handler(self, handler: InboundHandler) -> None:
        if not callable(handler):
            raise ValueError("handler must be callable")
        self._inbound_handler = handler

    async def start(self) -> None:
        """Connect an existing authorized session and register one handler."""

        try:
            await self._client.connect()
            if not await self._client.is_user_authorized():
                raise TelethonAuthorizationRequiredError(
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
            failure = TelethonTransientError if isinstance(
                error, (ConnectionError, TimeoutError, OSError)
            ) else TelethonTransportError
            raise failure("Telethon startup failed.") from error

    async def run_until_disconnected(self) -> None:
        try:
            await self._client.run_until_disconnected()
        except Exception as error:
            self._log_error("receive loop", error)
            raise TelethonTransientError("Telethon receive loop failed.") from error

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except Exception as error:
            self._log_error("disconnect", error)

    async def show_typing_while(
        self, *, chat_id: int, operation: Awaitable[None],
        telegram_user_id: int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Publish and refresh native typing while an authoritative wait runs.

        The first MTProto request is awaited, unlike Telethon's ``action``
        context which schedules it in a background task. Typing remains
        ephemeral, best-effort UX and grants no delivery authority.
        """

        if isinstance(chat_id, bool) or not isinstance(chat_id, int) or chat_id <= 0:
            raise ValueError("chat_id must be a positive private-chat identifier")
        safe_chat_id = self._safe_identifier(chat_id)
        safe_user_id = self._safe_identifier(telegram_user_id)
        started_at = datetime.now(timezone.utc)
        started_monotonic = time.monotonic()
        peer = None
        refresh_task = None
        published = False
        try:
            peer = await self._client.get_input_entity(chat_id)
            peer_type = type(peer).__name__
            self._logger.info(
                "event=telegram_typing_request correlation_id=%s chat_id=%s "
                "user_id=%s peer_type=%s request_started_at=%s status=started",
                correlation_id or "unknown", safe_chat_id, safe_user_id,
                peer_type, started_at.isoformat(),
            )
            await self._client(functions.messages.SetTypingRequest(
                peer, types.SendMessageTypingAction(),
            ))
            published = True
            completed_at = datetime.now(timezone.utc)
            self._logger.info(
                "event=telegram_typing_request correlation_id=%s chat_id=%s "
                "user_id=%s peer_type=%s request_started_at=%s "
                "request_completed_at=%s status=success",
                correlation_id or "unknown", safe_chat_id, safe_user_id,
                peer_type, started_at.isoformat(), completed_at.isoformat(),
            )
            refresh_task = asyncio.create_task(self._refresh_typing(peer))
        except Exception as error:
            self._logger.warning(
                "event=telegram_typing_request correlation_id=%s chat_id=%s "
                "user_id=%s peer_type=%s request_started_at=%s "
                "request_completed_at=%s status=failure exception_category=%s",
                correlation_id or "unknown", safe_chat_id, safe_user_id,
                type(peer).__name__ if peer is not None else "unresolved",
                started_at.isoformat(), datetime.now(timezone.utc).isoformat(),
                type(error).__name__,
            )
        try:
            await operation
        finally:
            if refresh_task is not None:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
                except Exception as error:
                    self._logger.warning(
                        "event=telegram_typing_refresh correlation_id=%s chat_id=%s "
                        "status=failure exception_category=%s",
                        correlation_id or "unknown", safe_chat_id,
                        type(error).__name__,
                    )
            cancelled_at = datetime.now(timezone.utc)
            try:
                if published and peer is not None:
                    await self._client(functions.messages.SetTypingRequest(
                        peer, types.SendMessageCancelAction(),
                    ))
                self._logger.info(
                    "event=telegram_typing_complete correlation_id=%s chat_id=%s "
                    "user_id=%s peer_type=%s status=%s active_duration_ms=%s "
                    "cancellation_at=%s",
                    correlation_id or "unknown", safe_chat_id, safe_user_id,
                    type(peer).__name__ if peer is not None else "unresolved",
                    "cancelled" if published else "not_published",
                    round((time.monotonic() - started_monotonic) * 1000),
                    cancelled_at.isoformat(),
                )
            except Exception as error:
                self._logger.warning(
                    "event=telegram_typing_complete correlation_id=%s chat_id=%s "
                    "user_id=%s peer_type=%s status=cancel_failed "
                    "active_duration_ms=%s cancellation_at=%s exception_category=%s",
                    correlation_id or "unknown", safe_chat_id, safe_user_id,
                    type(peer).__name__ if peer is not None else "unresolved",
                    round((time.monotonic() - started_monotonic) * 1000),
                    cancelled_at.isoformat(), type(error).__name__,
                )

    async def _refresh_typing(self, peer: Any, *, interval_seconds: float = 4.0) -> None:
        while True:
            await asyncio.sleep(interval_seconds)
            await self._client(functions.messages.SetTypingRequest(
                peer, types.SendMessageTypingAction(),
            ))

    @staticmethod
    def _safe_identifier(value: int | None) -> str:
        text = str(value or "unknown")
        return text if len(text) <= 6 else f"{text[:4]}...{text[-4:]}"

    async def send_text(
        self, *, chat_id: int, message_text: str,
        button_label: str | None = None, button_url: str | None = None,
    ) -> int | TelethonSendReceipt | None:
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
            commercial = bool(button_label and button_url)
            is_bot_method = getattr(self._client, "is_bot", None)
            is_bot = bool(await is_bot_method()) if commercial and callable(is_bot_method) else False
            final_text = message_text
            buttons = None
            attachment_mode = None
            if commercial and is_bot:
                buttons = [[Button.url(button_label, button_url)]]
                attachment_mode = "INLINE_BUTTON"
            elif commercial:
                # Telegram user accounts cannot attach bot inline keyboards.
                # Preserve zero-friction access with a visible, clickable URL.
                final_text = f"{message_text.rstrip()}\n\n{button_label}: {button_url}"
                attachment_mode = "VISIBLE_URL"
            send_options = {"buttons": buttons} if buttons is not None else {}
            message = await self._client.send_message(
                chat_id, final_text, **send_options,
            )
            message_id = getattr(message, "id", None)
            if not isinstance(message_id, int):
                return None
            if not commercial:
                return message_id
            provider_message = await self._client.get_messages(chat_id, ids=message_id)
            provider_text = str(
                getattr(provider_message, "raw_text", None)
                or getattr(provider_message, "message", None)
                or ""
            )
            if attachment_mode == "INLINE_BUTTON":
                provider_buttons = getattr(provider_message, "buttons", None) or []
                verified = any(
                    getattr(button, "url", None) == button_url
                    for row in provider_buttons for button in row
                )
            else:
                verified = button_url in provider_text
            if not verified:
                raise TelethonCommercialVerificationError(
                    "Telegram commercial action could not be verified provider-side."
                )
            return TelethonSendReceipt(
                id=message_id,
                final_text=provider_text,
                actionable_destination_attached=True,
                provider_action_verified=True,
                provider_markup_included=(attachment_mode == "INLINE_BUTTON"),
                provider_markup_verified=(attachment_mode == "INLINE_BUTTON"),
                attachment_mode=attachment_mode,
            )
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
        upload_path = (
            self._image_normalizer.normalize(path).path
            if self._image_normalizer.is_supported_image(path)
            else path
        )
        try:
            message = await self._client.send_file(
                chat_id, str(upload_path), caption=message_text.strip() or None,
            )
            message_id = getattr(message, "id", None)
            return message_id if isinstance(message_id, int) else None
        except TelethonCommercialVerificationError:
            raise
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
        """Normalize one incoming private text and/or supported media event."""

        if event is None:
            return None
        if getattr(event, "out", False) or not getattr(event, "is_private", False):
            return None

        message_text = getattr(event, "raw_text", None)
        message_text = message_text.strip() if isinstance(message_text, str) else ""

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

        attachment = TelethonUserTransport._attachment_from_event(
            event, telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id, message_id=message_id,
            caption=message_text,
        )
        if not message_text and attachment is None:
            return None

        return TelegramInboundPayload(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            message_text=message_text,
            message_id=message_id,
            telegram_username=(str(getattr(sender, "username", "") or "").strip() or None),
            telegram_display_name=(" ".join(filter(None, (
                str(getattr(sender, "first_name", "") or "").strip(),
                str(getattr(sender, "last_name", "") or "").strip(),
            ))) or None),
            reply_to_message_id=(
                int(getattr(getattr(event, "message", None), "reply_to_msg_id"))
                if isinstance(getattr(getattr(event, "message", None), "reply_to_msg_id", None), int)
                else None
            ),
            received_at=getattr(event, "date", None),
            attachments=(attachment,) if attachment is not None else (),
        )

    @staticmethod
    def _attachment_from_event(event, *, telegram_user_id, telegram_chat_id,
                               message_id, caption):
        message = getattr(event, "message", None) or event
        photo = getattr(event, "photo", None) or getattr(message, "photo", None)
        document = getattr(event, "document", None) or getattr(message, "document", None)
        media = photo or document
        if media is None:
            return None
        kind = "PHOTO" if photo is not None else "IMAGE_DOCUMENT"
        mime = getattr(document, "mime_type", None)
        attributes = list(getattr(document, "attributes", None) or ())
        filename = next((getattr(item, "file_name", None) for item in attributes
                         if getattr(item, "file_name", None)), None)
        width = getattr(media, "w", None)
        height = getattr(media, "h", None)
        if photo is not None:
            sizes = list(getattr(photo, "sizes", None) or ())
            width = max((getattr(item, "w", 0) or 0 for item in sizes), default=0) or None
            height = max((getattr(item, "h", 0) or 0 for item in sizes), default=0) or None
        grouped = getattr(message, "grouped_id", None) or getattr(event, "grouped_id", None)
        media_id = getattr(media, "id", None)
        if not isinstance(media_id, int):
            return None
        stable = uuid5(NAMESPACE_URL, f"telegram-media:{telegram_chat_id}:{message_id}:{media_id}")
        return TelegramInboundAttachment(
            attachment_id=str(stable), telegram_message_id=message_id,
            telegram_chat_id=telegram_chat_id, telegram_user_id=telegram_user_id,
            media_kind=kind, telegram_media_id=str(media_id),
            mime_type=str(mime) if mime else ("image/jpeg" if photo is not None else None),
            original_filename=str(filename) if filename else None,
            reported_size_bytes=getattr(document, "size", None),
            width=width, height=height,
            grouped_id=str(grouped) if grouped is not None else None,
            has_caption=bool(caption), received_at=getattr(event, "date", None),
        )

    async def download_inbound_attachment(self, attachment, *, maximum_bytes, timeout_seconds):
        class BoundedBuffer(io.BytesIO):
            def write(self, value):
                if self.tell() + len(value) > maximum_bytes:
                    raise ValueError("actual media size exceeds configured limit")
                return super().write(value)
        message = await self._client.get_messages(
            attachment.telegram_chat_id, ids=attachment.telegram_message_id,
        )
        if message is None:
            raise FileNotFoundError("originating Telegram media is unavailable")
        target = BoundedBuffer()
        result = await asyncio.wait_for(
            self._client.download_media(message, file=target),
            timeout=timeout_seconds,
        )
        data = target.getvalue()
        if not data and isinstance(result, (bytes, bytearray)):
            data = bytes(result)
        if not data:
            raise FileNotFoundError("originating Telegram media returned no bytes")
        return data

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

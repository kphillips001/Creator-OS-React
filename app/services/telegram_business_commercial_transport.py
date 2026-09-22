"""Commercial-only Telegram Business transport for private-chat offers."""

from __future__ import annotations

from app.models.telegram_transport_contract import validate_local_payload

import os
from app.models.telegram_transport_contract import TelegramReachability, TelegramPreflightError, TelegramPeerUnavailableError

from app.integrations.telegram.bot_api_sender import TelegramBotApiSender
from app.services.telegram_business_connection_service import (
    TelegramBusinessConnectionService,
)


class TelegramBusinessTransportError(RuntimeError):
    health_scope = "RECIPIENT_REACHABILITY"
    code = "BUSINESS_CONNECTION_UNAVAILABLE"


class TelegramBusinessConnectionDisabledError(TelegramBusinessTransportError):
    code = "BUSINESS_CONNECTION_DISABLED"


class TelegramBusinessReplyNotAllowedError(TelegramBusinessTransportError):
    code = "BUSINESS_REPLY_NOT_ALLOWED"


class TelegramBusinessCommercialTransport:
    """Resolve one active Ava connection and perform one verified send."""

    BUTTON_LABEL = "🔓 Unlock"

    validate_delivery = staticmethod(validate_local_payload)

    def __init__(self, *, enabled=None, owner_user_id=None, bot_id=None,
                 connection_service=None, sender=None, bot_token=None, peer_observations=None):
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
        self.peer_observations = peer_observations
        self.connection_service = connection_service
        self.sender = sender
        self.bot_token = (
            bot_token if bot_token is not None
            else os.getenv("TELEGRAM_BOT_TOKEN_AVA", "")
        )

    def prepare_delivery(self, *, chat_id, requirements):
        connection = self._active_connection()
        from app.repositories.telegram_business_peer_observation_repository import TelegramBusinessPeerObservationRepository
        peers = self.peer_observations or TelegramBusinessPeerObservationRepository()
        evidence = peers.evidence(business_connection_id=connection.business_connection_id,
            telegram_peer_user_id=int(chat_id), telegram_chat_id=int(chat_id))
        if not evidence or not evidence.get("last_business_inbound_at") or not evidence.get("is_enabled") or not evidence.get("can_reply"):
            raise TelegramPeerUnavailableError("No current Business peer reply evidence.")
        result = TelegramReachability("TELEGRAM_BUSINESS", f"business:{self.owner_user_id}:bot:{self.bot_id}", int(chat_id),
            "BUSINESS_INBOUND", evidence["last_business_inbound_at"], connection.business_connection_id,
            sender_id=self.owner_user_id)
        result.validate(requirements)
        return result

    def send_text(self, *, chat_id, message_text, button_label, button_url,
                  expected_business_connection_id=None, disable_link_preview=True):
        active_connection = self._active_connection(expected_business_connection_id)
        self._validate_button(button_label, button_url)
        sender = self.sender or TelegramBotApiSender(bot_token=self.bot_token)
        return sender.send_text(
            business_connection_id=active_connection.business_connection_id,
            chat_id=int(chat_id), message_text=message_text,
            button_label=button_label, button_url=button_url,
            disable_link_preview=disable_link_preview,
            expected_business_owner_user_id=self.owner_user_id,
            expected_business_bot_id=self.bot_id,
        )

    def send_asset(self, *, chat_id, asset_path, message_text,
                   button_label, button_url,
                   expected_business_connection_id=None, disable_link_preview=True):
        active_connection = self._active_connection(expected_business_connection_id)
        self._validate_button(button_label, button_url)
        sender = self.sender or TelegramBotApiSender(bot_token=self.bot_token)
        return sender.send_asset(
            business_connection_id=active_connection.business_connection_id,
            chat_id=int(chat_id), asset_path=asset_path,
            message_text=message_text, button_label=button_label,
            button_url=button_url, disable_link_preview=disable_link_preview,
            expected_business_owner_user_id=self.owner_user_id,
            expected_business_bot_id=self.bot_id,
        )

    def _active_connection(self, expected_business_connection_id=None):
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
        if (expected_business_connection_id is not None and
                active_connection.business_connection_id != expected_business_connection_id):
            raise TelegramBusinessTransportError(
                "The prepared Telegram Business connection is no longer active."
            )
        return active_connection

    def _validate_button(self, button_label, button_url):
        if (button_label is None) != (button_url is None):
            raise ValueError("Telegram button label and URL must be supplied together.")
        from app.models.telegram_transport_contract import TelegramRequirements
        TelegramRequirements.from_send(button_label=button_label, button_url=button_url)

    @staticmethod
    def _positive_id(value):
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

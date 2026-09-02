"""One-shot Telegram Bot Token runtime with plain-text outbound delivery."""

import json
import logging
import os
from collections.abc import Mapping
from typing import Any, Protocol

import requests

from app.integrations.telegram.business_connection_capture import (
    BOT_API_ALLOWED_UPDATES,
)
from app.models.telegram_inbound import (
    TelegramInboundPayload,
    TelegramInboundResult,
)
from app.integrations.telegram.bot_api_sender import TelegramBotApiSender
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


class TelegramBotRuntimeError(RuntimeError):
    """A sanitized failure from the one-shot Bot API runtime."""


class OneShotUpdateSource(Protocol):
    def receive_one_update(self) -> Mapping[str, Any] | None:
        ...


class PlainTextSender(Protocol):
    def send_text(self, *, chat_id: int, message_text: str) -> None:
        ...


class TelegramBotTokenUpdateSource:
    """Fetch at most one message update through the Telegram Bot API."""

    def __init__(
        self,
        *,
        bot_token: str,
        timeout_seconds: int = 30,
        offset: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        if not isinstance(bot_token, str) or not bot_token.strip():
            raise ValueError("bot_token is required")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or not 0 <= timeout_seconds <= 50
        ):
            raise ValueError("timeout_seconds must be between 0 and 50")
        if offset is not None and (
            isinstance(offset, bool) or not isinstance(offset, int)
        ):
            raise ValueError("offset must be an integer when provided")

        self._endpoint = (
            f"https://api.telegram.org/bot{bot_token.strip()}/getUpdates"
        )
        self._timeout_seconds = timeout_seconds
        self._offset = offset
        self._session = session or requests.Session()

    def receive_one_update(self) -> Mapping[str, Any] | None:
        params: dict[str, Any] = {
            "timeout": self._timeout_seconds,
            "limit": 1,
            "allowed_updates": json.dumps(BOT_API_ALLOWED_UPDATES),
        }
        if self._offset is not None:
            params["offset"] = self._offset

        try:
            response = self._session.get(
                self._endpoint,
                params=params,
                timeout=self._timeout_seconds + 5,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            raise TelegramBotRuntimeError(
                "Telegram getUpdates request failed."
            ) from None

        if not isinstance(payload, Mapping) or payload.get("ok") is not True:
            raise TelegramBotRuntimeError(
                "Telegram returned an invalid getUpdates response."
            )

        updates = payload.get("result")
        if not isinstance(updates, list):
            raise TelegramBotRuntimeError(
                "Telegram getUpdates result was not a list."
            )
        if not updates:
            return None

        update = updates[0]
        if not isinstance(update, Mapping):
            raise TelegramBotRuntimeError(
                "Telegram update was not an object."
            )
        return update


class MemoryInitializingDecisionEngine:
    """Ensure the temporary engine key owns memory before brain execution."""

    def __init__(self, decision_engine: Any) -> None:
        self._decision_engine = decision_engine

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history=None,
    ):
        self._decision_engine.memory.get_or_create_user_memory(user_id)
        return self._decision_engine.process_message(
            user_id,
            message,
            chat_history=chat_history,
        )


class TelegramBotTokenRuntimeSpike:
    """Receive, process, and reply to one private text update."""

    def __init__(
        self,
        *,
        update_source: OneShotUpdateSource,
        inbound_adapter: TelegramInboundAdapter,
        outbound_sender: PlainTextSender,
        delivery_executor: TelegramDeliveryExecutor | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._update_source = update_source
        self._inbound_adapter = inbound_adapter
        self._outbound_sender = outbound_sender
        self._delivery_executor = delivery_executor or TelegramDeliveryExecutor()
        self._logger = logger or logging.getLogger(
            "telegram-bot-token-runtime-spike"
        )

    def run_once(self) -> TelegramInboundResult | None:
        update = self._update_source.receive_one_update()
        if update is None:
            self._logger.info("No Telegram update received.")
            return None

        payload = self._normalize_update(update)
        if payload is None:
            self._logger.info("Telegram update ignored: unsupported update.")
            return None

        result = self._inbound_adapter.execute(payload)
        self._logger.info(
            "Telegram inbound normalized: correlation_id=%s user_id=%s "
            "chat_id=%s message_id=%s engine_user_id=%s blocked=%s "
            "offer_authorized=%s error_code=%s response_length=%s",
            result.correlation_id,
            result.telegram_user_id,
            result.telegram_chat_id,
            result.message_id,
            result.engine_user_id,
            result.blocked,
            result.offer_authorized,
            result.error_code,
            len(result.response_text),
        )

        if result.response_text:
            execution = self._delivery_executor.execute(
                result.delivery_payload,
                context={
                    "chat_id": payload.telegram_chat_id,
                    "correlation_id": result.correlation_id,
                    "engine_user_id": result.engine_user_id,
                    "creator_profile_id": result.diagnostic_metadata.get("creator_profile_id"),
                    "fanvue_account_id": result.diagnostic_metadata.get("fanvue_account_id"),
                    "fanvue_user_id": result.diagnostic_metadata.get("fanvue_user_id"),
                    "fallback_message_text": result.response_text,
                    "raise_on_failure": True,
                    "text_sender": self._outbound_sender,
                },
            )
            if not execution.executed:
                self._logger.warning(
                    "Telegram response not sent: delivery execution status=%s.",
                    execution.status,
                )
        else:
            self._logger.warning(
                "Telegram response not sent: normalized response was empty."
            )
        return result

    @staticmethod
    def _normalize_update(
        update: Mapping[str, Any],
    ) -> TelegramInboundPayload | None:
        message = update.get("message")
        if not isinstance(message, Mapping):
            return None

        sender = message.get("from")
        chat = message.get("chat")
        if not isinstance(sender, Mapping) or not isinstance(chat, Mapping):
            return None
        if sender.get("is_bot") is True or chat.get("type") != "private":
            return None

        telegram_user_id = sender.get("id")
        telegram_chat_id = chat.get("id")
        message_id = message.get("message_id")
        message_text = message.get("text")
        if not isinstance(message_text, str) or not message_text.strip():
            return None

        return TelegramInboundPayload(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            message_text=message_text,
            message_id=message_id,
        )


def build_default_runtime_from_environment() -> TelegramBotTokenRuntimeSpike:
    """Compose the spike from environment configuration and existing services."""

    # Keep database and model initialization out of module import and unit tests.
    from app.config import settings
    from app.engine.decision_engine import DecisionEngine
    from app.engine.mode_engine import ModeEngine
    from app.services.content_service import ContentService
    from app.services.gpt_service import GPTService
    from app.services.global_automation_safety_service import GlobalAutomationSafetyService
    from app.services.intent_service import IntentService
    from app.services.memory_service import MemoryService
    from app.services.offer_service import OfferService
    from app.services.post_offer_service import PostOfferService
    from app.services.telegram_commerce_service import TelegramCommerceService
    from app.services.timing_engine import TimingEngine
    from app.services.user_value_service import UserValueService

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    account_id_text = os.getenv("AVA_FANVUE_ACCOUNT_ID", "").strip()
    if not bot_token:
        raise TelegramBotRuntimeError("TELEGRAM_BOT_TOKEN is required.")
    try:
        engine_account_id = int(account_id_text)
    except ValueError:
        raise TelegramBotRuntimeError(
            "AVA_FANVUE_ACCOUNT_ID must be an integer."
        ) from None

    allowed_hosts = [
        host.strip()
        for host in os.getenv(
            "TELEGRAM_ALLOWED_FANVUE_HOSTNAMES",
            "fanvue.com",
        ).split(",")
        if host.strip()
    ]
    try:
        timeout_seconds = int(
            os.getenv("TELEGRAM_GET_UPDATES_TIMEOUT", "30")
        )
    except ValueError:
        raise TelegramBotRuntimeError(
            "TELEGRAM_GET_UPDATES_TIMEOUT must be an integer."
        ) from None

    memory_service = MemoryService()
    decision_engine = DecisionEngine(
        memory_service=memory_service,
        intent_service=IntentService(),
        user_value_service=UserValueService(),
        mode_engine=ModeEngine(),
        offer_service=OfferService(),
        content_service=ContentService(),
        post_offer_service=PostOfferService(),
        timing_engine=TimingEngine(),
        gpt_service=GPTService(settings.OPENAI_API_KEY),
        settings=settings,
        logger=logging.getLogger("telegram-decision-engine"),
    )
    global_safety = GlobalAutomationSafetyService()
    gateway = ConversationGateway(
        MemoryInitializingDecisionEngine(decision_engine),
        allowed_fanvue_hostnames=allowed_hosts,
        telegram_commerce_service=TelegramCommerceService(
            decision_engine=decision_engine,
            memory_service=memory_service,
        ),
        global_automation_safety_service=global_safety,
    )
    inbound_adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(
            engine_account_id=engine_account_id
        ),
        conversation_gateway=gateway,
    )
    update_source = TelegramBotTokenUpdateSource(
        bot_token=bot_token,
        timeout_seconds=timeout_seconds,
    )
    outbound_sender = TelegramBotApiSender(bot_token=bot_token)
    return TelegramBotTokenRuntimeSpike(
        update_source=update_source,
        inbound_adapter=inbound_adapter,
        outbound_sender=outbound_sender,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    build_default_runtime_from_environment().run_once()


if __name__ == "__main__":
    main()

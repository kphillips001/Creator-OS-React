"""Composition and execution of the Telethon transport MVP."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, TYPE_CHECKING

from dotenv import load_dotenv
from app.config import ENV_PATH
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.repositories.chat_message_repository import get_or_create_chat_thread

if TYPE_CHECKING:
    from app.integrations.telegram.telethon_transport import TelethonUserTransport


class TelethonRuntimeError(RuntimeError):
    """A sanitized Telethon runtime or configuration failure."""


class MemoryInitializingDecisionEngine:
    """Ensure the temporary engine identity owns memory before execution."""

    def __init__(self, decision_engine: Any) -> None:
        self._decision_engine = decision_engine

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history=None,
        runtime_injection=None,
    ):
        self._decision_engine.memory.get_or_create_user_memory(user_id)
        return self._decision_engine.process_message(
            user_id,
            message,
            chat_history=chat_history,
            runtime_injection=runtime_injection,
        )


class TelethonRuntime:
    """Run private messages through the existing synchronous brain pipeline."""

    def __init__(
        self,
        *,
        transport: TelethonUserTransport,
        inbound_adapter: TelegramInboundAdapter,
        delivery_executor: TelegramDeliveryExecutor | None = None,
        logger: logging.Logger | None = None,
        heartbeat_service: WorkerHeartbeatService | None = None,
        global_safety_service: Any | None = None,
        purchase_intent_service: Any | None = None,
    ) -> None:
        if transport is None:
            raise ValueError("transport is required")
        if inbound_adapter is None:
            raise ValueError("inbound_adapter is required")
        self._transport = transport
        self._inbound_adapter = inbound_adapter
        self._delivery_executor = delivery_executor or TelegramDeliveryExecutor()
        if global_safety_service is None:
            from app.services.global_automation_safety_service import GlobalAutomationSafetyService
            global_safety_service = GlobalAutomationSafetyService()
        self._global_safety_service = global_safety_service
        self._purchase_intents = purchase_intent_service
        self._logger = logger or logging.getLogger("telethon-runtime")
        self._heartbeat = heartbeat_service or WorkerHeartbeatService(
            worker_name="Telegram", worker_type="transport_runtime", poll_interval_seconds=30,
        )
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._transport.set_inbound_handler(self.handle_payload)

    async def run(self) -> None:
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "startup", self._heartbeat.register_startup)
        heartbeat_task = None
        failed = False
        try:
            await self._transport.start()
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            await self._transport.run_until_disconnected()
        except Exception as error:
            failed = True
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "failure", lambda: self._heartbeat.record_failure(error))
            raise
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            await self._transport.disconnect()
            if not failed:
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "stopping", self._heartbeat.record_stopping)
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "shutdown", self._heartbeat.record_shutdown)

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "poll", self._heartbeat.record_poll)
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "success", lambda: self._heartbeat.record_success(idle=True))
            await asyncio.sleep(30)

    async def handle_payload(
        self,
        payload: TelegramInboundPayload,
    ) -> TelegramInboundResult | None:
        """Execute the gateway off-loop and send only its response text."""

        replies_enabled = (
            os.getenv("TELEGRAM_REPLIES_ENABLED", "true").strip().lower()
            != "false"
        )
        if not replies_enabled:
            self._logger.info(
                "[TELEGRAM PAUSED] inbound message suppressed "
                "chat_id=%s user_id=%s",
                payload.telegram_chat_id,
                payload.telegram_user_id,
            )
            return None

        global_result = self._global_safety_service.check_global_safety()
        if not global_result.get("allowed", False):
            self._logger.info(
                "[TELEGRAM AUTONOMY BLOCKED] chat_id=%s reason=%s",
                payload.telegram_chat_id, global_result.get("reason"),
            )
            return None

        lock = self._chat_locks.setdefault(payload.telegram_chat_id, asyncio.Lock())
        async with lock:
            try:
                result = await asyncio.to_thread(
                    self._inbound_adapter.execute,
                    payload,
                )
                if result.response_text:
                    intent = None
                    if self._purchase_intents is not None:
                        intent = await asyncio.to_thread(
                            self._purchase_intents.create_before_delivery,
                            result, payload,
                        )
                    try:
                        execution = await self._delivery_executor.execute_async(
                            result.delivery_payload,
                            context={
                                "chat_id": payload.telegram_chat_id,
                                "correlation_id": result.correlation_id,
                                "engine_user_id": result.engine_user_id,
                                "fallback_message_text": result.response_text,
                                "raise_on_failure": True,
                                "transport": self._transport,
                            },
                        )
                    except Exception:
                        if self._purchase_intents is not None:
                            await asyncio.to_thread(
                                self._purchase_intents.abandon_delivery, intent,
                            )
                        raise
                    if execution.executed and self._purchase_intents is not None:
                        await asyncio.to_thread(
                            self._purchase_intents.confirm_delivery, intent,
                            telegram_message_id=execution.metadata.get(
                                "telegram_message_id"
                            ),
                        )
                        acknowledgement_id = (
                            result.diagnostic_metadata.get(
                                "purchase_acknowledgement_intent_id"
                            )
                        )
                        if (
                            acknowledgement_id
                            and result.diagnostic_metadata.get(
                                "customer_sales_decision"
                            ) == "CONGRATULATE_PURCHASE"
                        ):
                            await asyncio.to_thread(
                                self._purchase_intents.acknowledge_purchase,
                                acknowledgement_id,
                            )
                    elif self._purchase_intents is not None:
                        await asyncio.to_thread(
                            self._purchase_intents.abandon_delivery, intent,
                        )
                    if not execution.executed:
                        self._logger.warning(
                            "Telegram response not sent: "
                            "delivery execution status=%s.",
                            execution.status,
                        )
                return result
            except Exception as error:
                self._logger.error(
                    "[TELETHON ERROR] operation=gateway chat_id=%s "
                    "message_id=%s error_type=%s",
                    payload.telegram_chat_id,
                    payload.message_id,
                    type(error).__name__,
                )
                return None


def _required_positive_int(name: str) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        raise TelethonRuntimeError(f"{name} must be a positive integer.") from None
    if value <= 0:
        raise TelethonRuntimeError(f"{name} must be a positive integer.")
    return value


def _required_text(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise TelethonRuntimeError(f"{name} is required.")
    return value


def build_default_runtime_from_environment() -> TelethonRuntime:
    """Compose Telethon with the existing gateway and DecisionEngine."""

    load_dotenv(dotenv_path=ENV_PATH, override=True)

    # Heavy services remain lazy so transport unit tests stay offline.
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
    from app.services.chat_commerce_service import ChatCommerceService
    from app.services.customer_sales_brain_service import (
        CustomerSalesBrainService,
    )
    from app.services.runtime_control_service import RuntimeControlService
    from app.services.telegram_purchase_intent_service import (
        TelegramPurchaseIntentService,
    )
    from app.services.timing_engine import TimingEngine
    from app.services.user_value_service import UserValueService
    from app.repositories.creator_profile_repository import (
        get_active_creator_profile,
    )

    api_id = _required_positive_int("TG_API_ID")
    api_hash = _required_text("TG_API_HASH")
    engine_account_id = _required_positive_int("AVA_FANVUE_ACCOUNT_ID")
    session_path = os.getenv("TG_SESSION_PATH", "tg_sessions/ava").strip()
    if not session_path:
        raise TelethonRuntimeError("TG_SESSION_PATH must not be empty.")

    from telethon import TelegramClient
    from app.integrations.telegram.telethon_transport import TelethonUserTransport

    allowed_hosts = [
        host.strip()
        for host in os.getenv(
            "TELEGRAM_ALLOWED_FANVUE_HOSTNAMES",
            "fanvue.com,www.fanvue.com",
        ).split(",")
        if host.strip()
    ]

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
    creator_profile = get_active_creator_profile(str(engine_account_id)) or {}
    creator_profile_id = int(creator_profile.get("id") or 0)
    gateway = ConversationGateway(
        MemoryInitializingDecisionEngine(decision_engine),
        allowed_fanvue_hostnames=allowed_hosts,
        chat_commerce_service=ChatCommerceService(
            commerce_mode=ChatCommerceService.AUTHORITATIVE_MODE
        ),
        customer_sales_brain_service=CustomerSalesBrainService(),
        creator_profile_id=creator_profile_id or None,
        runtime_control_service=RuntimeControlService(),
        global_automation_safety_service=global_safety,
    )
    purchase_intents = (
        TelegramPurchaseIntentService(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=engine_account_id,
        ) if creator_profile_id else None
    )
    inbound_adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(
            engine_account_id=engine_account_id,
        ),
        conversation_gateway=gateway,
        creator_profile_id=creator_profile_id or None,
        fanvue_account_id=engine_account_id,
        purchase_intent_service=purchase_intents,
    )
    client = TelegramClient(session_path, api_id, api_hash)
    transport = TelethonUserTransport(client=client)
    return TelethonRuntime(
        transport=transport,
        inbound_adapter=inbound_adapter,
        heartbeat_service=WorkerHeartbeatService(
            worker_name="Telegram", worker_type="transport_runtime",
            account_id=engine_account_id, poll_interval_seconds=30,
        ),
        global_safety_service=global_safety,
        purchase_intent_service=purchase_intents,
        conversation_thread_resolver=get_or_create_chat_thread,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(build_default_runtime_from_environment().run())


if __name__ == "__main__":
    main()

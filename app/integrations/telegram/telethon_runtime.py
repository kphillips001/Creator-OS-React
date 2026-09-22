"""Composition and execution of the Telethon transport MVP."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import signal
from datetime import timedelta, timezone
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TYPE_CHECKING
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from app.config import ENV_PATH
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.services.worker_heartbeat_instrumentation import record_heartbeat_safely
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.telegram_worker_ownership_service import TelegramWorkerOwnershipService
from app.integrations.telegram.telethon_transport import (
    TelethonAuthorizationRequiredError,
    TelethonProviderRejectedError,
    TelethonTransientError,
)
from app.integrations.telegram.bot_api_sender import TelegramOutboundSendError
from app.repositories.chat_message_repository import (
    get_or_create_chat_thread,
    get_recent_messages_for_gpt,
    save_chat_message,
)

if TYPE_CHECKING:
    from app.integrations.telegram.telethon_transport import TelethonUserTransport


class TelethonRuntimeError(RuntimeError):
    """A sanitized Telethon runtime or configuration failure."""


class MemoryInitializingDecisionEngine:
    """Ensure the temporary engine identity owns memory before execution."""

    def __init__(self, decision_engine: Any) -> None:
        self._decision_engine = decision_engine

    def classify_current_turn(self, *, user_id: str, message: str):
        """Expose the engine's classifier so the gateway can compute it once."""
        memory = self._decision_engine.memory.get_or_create_user_memory(user_id)
        return self._decision_engine.gpt_intent_classifier.classify_message(
            message=message,
            memory=memory,
        )

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

    ACCOUNT_SCOPE = "AVA_TELETHON_PRIVATE"

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
        photoshoot_lifecycle_service: Any | None = None,
        conversation_message_saver: Any | None = None,
        sales_delivery_service: Any | None = None,
        engagement_teaser_service: Any | None = None,
        scheduled_engagement_worker: Any | None = None,
        ordinary_reply_service: Any | None = None,
        ownership_service: Any | None = None,
        reconnect_initial_seconds: float = 1.0,
        reconnect_max_seconds: float = 30.0,
        reconnect_stable_reset_seconds: float = 60.0,
        jitter: Any | None = None,
        heartbeat_interval_seconds: float = 30.0,
        controlled_autonomy_service=None,
        response_pacing_service=None,
        business_connection_worker=None,
        sleep_service=None,
        inbound_media_service=None,
        inbound_image_safety_service=None,
        media_processing_scope_service=None,
        media_cleanup_interval_seconds=None,
        visual_turn_service=None,
        turn_reservation_service=None,
        ordinary_reply_schema_preflight=None,
        availability_failure_backoff_initial_seconds: float = 1.0,
        availability_failure_backoff_max_seconds: float = 30.0,
        availability_service=None,
        private_inbound_backlog_service=None,
        operator_message_repository=None,
        manual_offer_dispatcher=None,
        transport_certification_service=None,
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
        if controlled_autonomy_service is None:
            from app.services.controlled_autonomy_test_service import (
                ControlledAutonomyTestService,
            )
            controlled_autonomy_service = ControlledAutonomyTestService()
        self._controlled_autonomy = controlled_autonomy_service
        if media_processing_scope_service is None:
            from app.services.customer_media_processing_scope_service import (
                CustomerMediaProcessingScopeService,
            )
            media_processing_scope_service = CustomerMediaProcessingScopeService()
        self._media_processing_scope = media_processing_scope_service
        self._blocked_media_groups: set[tuple[int, str]] = set()
        if response_pacing_service is None:
            from app.services.telegram_response_pacing_service import TelegramResponsePacingService
            response_pacing_service = TelegramResponsePacingService()
        self._response_pacing = response_pacing_service
        self._business_connection_worker = business_connection_worker
        if sleep_service is None:
            from app.services.ava_sleep_service import AvaSleepService
            sleep_service = AvaSleepService()
        self._sleep_service = sleep_service
        self._purchase_intents = purchase_intent_service
        if photoshoot_lifecycle_service is None:
            from app.services.customer_photoshoot_lifecycle_service import (
                CustomerPhotoshootLifecycleService,
            )
            photoshoot_lifecycle_service = CustomerPhotoshootLifecycleService()
        self._photoshoot_lifecycles = photoshoot_lifecycle_service
        self._conversation_message_saver = conversation_message_saver
        self._sales_deliveries = sales_delivery_service
        self._engagement_teasers = engagement_teaser_service
        if scheduled_engagement_worker is None and engagement_teaser_service is not None:
            from app.services.scheduled_engagement_teaser_worker import ScheduledEngagementTeaserWorker
            scheduled_engagement_worker = ScheduledEngagementTeaserWorker(
                orchestrator=engagement_teaser_service)
        self._scheduled_engagement_worker = scheduled_engagement_worker
        self._ordinary_replies = ordinary_reply_service
        self._availability = availability_service
        self._private_inbound_backlog = private_inbound_backlog_service
        self._operator_messages = operator_message_repository
        self._manual_offer_dispatcher = manual_offer_dispatcher
        self._transport_certification = transport_certification_service
        if inbound_media_service is None:
            from app.services.telegram_inbound_media_service import TelegramInboundMediaService
            inbound_media_service = TelegramInboundMediaService()
        self._inbound_media = inbound_media_service
        self._visual_turns = visual_turn_service
        self._turn_reservations = turn_reservation_service
        if (inbound_image_safety_service is None and
                os.getenv("TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED", "false").lower()
                in {"1", "true", "yes", "on"}):
            from app.services.customer_inbound_image_safety_service import CustomerInboundImageSafetyService
            inbound_image_safety_service = CustomerInboundImageSafetyService()
        self._inbound_image_safety = inbound_image_safety_service
        self._media_cleanup_interval=max(60.0,float(
            media_cleanup_interval_seconds or
            os.getenv("TELEGRAM_CUSTOMER_MEDIA_CLEANUP_INTERVAL_SECONDS",3600)))
        self._image_response_enabled = (
            os.getenv("TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED", "false")
            .strip().lower() in {"1", "true", "yes", "on"}
        )
        self._ownership = ownership_service
        self._reconnect_initial = max(0.01, float(reconnect_initial_seconds))
        self._reconnect_max = max(self._reconnect_initial, float(reconnect_max_seconds))
        self._stable_reset = max(0.0, float(reconnect_stable_reset_seconds))
        self._jitter = jitter or (lambda delay: random.uniform(delay * .8, delay * 1.2))
        self._shutdown = asyncio.Event()
        self._reconnect_attempts = 0
        self._heartbeat_interval = max(0.01, float(heartbeat_interval_seconds))
        self._ordinary_reply_schema_preflight = ordinary_reply_schema_preflight
        self._availability_failure_backoff_initial = max(
            0.01, float(availability_failure_backoff_initial_seconds)
        )
        self._availability_failure_backoff_max = max(
            self._availability_failure_backoff_initial,
            float(availability_failure_backoff_max_seconds),
        )
        self._availability_failure_count = 0
        self._ordinary_resume_tasks: dict[tuple[int, int], asyncio.Task] = {}
        self._ordinary_resume_failures: dict[tuple[int, int], dict[str, Any]] = {}
        self._fatal_background_error: Exception | None = None
        self._transport_connected = False
        self._startup_history_recovery = {
            "complete": False, "status": "NOT_STARTED",
        }
        self._logger = logger or logging.getLogger("telethon-runtime")
        self._heartbeat = heartbeat_service or WorkerHeartbeatService(
            worker_name="Telegram", worker_type="transport_runtime", poll_interval_seconds=30,
        )
        self._chat_locks: dict[int, asyncio.Lock] = {}
        self._transport.set_inbound_handler(self._handle_payload_observed)

    async def _handle_payload_observed(self, payload: TelegramInboundPayload):
        if self._ownership is not None:
            await asyncio.to_thread(self._ownership.check)
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "inbound", lambda: self._heartbeat.heartbeat(metadata={
            "last_inbound_event_time": self._heartbeat.now().isoformat(),
            "last_inbound_chat_id": payload.telegram_chat_id,
        }))
        captured_inbound = None
        if self._private_inbound_backlog is not None:
            self._global_safety_service.refresh()
            configured = getattr(self._global_safety_service, "behavior_config", {}) or {}
            capture_result = await asyncio.to_thread(
                self._private_inbound_backlog.capture, payload,
                account_scope=self.ACCOUNT_SCOPE,
                automation_state=("ON" if configured.get("global_automation_enabled") else "OFF"),
                creator_profile_id=getattr(self._inbound_adapter, "_creator_profile_id", None),
                fanvue_account_id=getattr(self._inbound_adapter, "_fanvue_account_id", None),
            )
            if isinstance(capture_result, tuple) and capture_result:
                captured_inbound = capture_result[0]
        # Availability governs response work, never whether a relationship exists.
        # This bounded, idempotent observation performs no memory, provider, sales,
        # generation, or send work.
        observer = getattr(self._inbound_adapter, "observe_identity_and_relationship", None)
        observed_identity = None
        if callable(observer):
            observed_identity = await asyncio.to_thread(observer, payload)
        control_observer = getattr(
            self._inbound_adapter, "observe_content_entry_control", None)
        if callable(control_observer):
            control_result = await asyncio.to_thread(
                control_observer, payload, observed_identity=observed_identity)
            if control_result is not None:
                control_consumer = getattr(
                    self._private_inbound_backlog, "consume_control", None)
                if callable(control_consumer):
                    await asyncio.to_thread(
                        control_consumer, payload, account_scope=self.ACCOUNT_SCOPE)
                self._logger.info(
                    "event=telegram_content_entry_control_consumed chat_id=%s "
                    "message_id=%s disposition=%s ordinary_reply_operations=0 "
                    "ai_generation_count=0 commercial_execution_count=0 automatic_send_count=0",
                    self._safe_telegram_identifier(payload.telegram_chat_id),
                    payload.message_id, control_result.error_code)
                return control_result
        controls = getattr(self._inbound_adapter, "_relationship_controls", None)
        creator_id = getattr(self._inbound_adapter, "_creator_profile_id", None)
        account_id = getattr(self._inbound_adapter, "_fanvue_account_id", None)
        if controls is not None and creator_id and account_id:
            _allowed, relationship_control = await asyncio.to_thread(
                controls.autonomous_allowed, creator_profile_id=int(creator_id),
                fanvue_account_id=int(account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id))
            if getattr(relationship_control, "ignored", False):
                if self._ordinary_replies is not None:
                    operation, _created = await asyncio.to_thread(
                        self._ordinary_replies.begin, payload)
                    await asyncio.to_thread(
                        self._ordinary_replies.suppress_ignored, operation)
                self._logger.info(
                    "event=telegram_inbound_relationship_ignored chat_id=%s reason=RELATIONSHIP_IGNORED ai_generation_count=0",
                    self._safe_telegram_identifier(payload.telegram_chat_id))
                return None
        text_reservation = None
        if (not payload.attachments and captured_inbound is not None
                and self._visual_turns is not None):
            associated = await asyncio.to_thread(
                self._visual_turns.attach_adjacent_text,
                creator_profile_id=int(creator_id), fanvue_account_id=int(account_id),
                telegram_chat_id=payload.telegram_chat_id, inbound=captured_inbound,
            )
            if associated is not None:
                self._logger.info(
                    "event=telegram_media_text_associated chat_id=%s message_id=%s",
                    self._safe_telegram_identifier(payload.telegram_chat_id),
                    payload.message_id,
                )
                return None
        if (not payload.attachments and captured_inbound is not None
                and self._turn_reservations is not None
                and payload.message_text.strip()):
            text_reservation = await asyncio.to_thread(
                self._turn_reservations.reserve_text,
                creator_profile_id=int(creator_id), fanvue_account_id=int(account_id),
                inbound=captured_inbound,
            )
        if payload.attachments:
            scope = self._media_processing_scope.decide(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
            )
            if not scope.allowed:
                grouped_id = next((item.grouped_id for item in payload.attachments if item.grouped_id), None)
                group_key = (payload.telegram_chat_id, str(grouped_id)) if grouped_id else None
                if group_key is None or group_key not in self._blocked_media_groups:
                    self._logger.info(
                        "event=telegram_customer_media_scope status=blocked reason=%s "
                        "mode=%s chat_id=%s user_id=%s grouped=%s",
                        scope.reason, scope.mode,
                        self._safe_telegram_identifier(payload.telegram_chat_id),
                        self._safe_telegram_identifier(payload.telegram_user_id),
                        bool(grouped_id),
                    )
                if group_key is not None:
                    if len(self._blocked_media_groups) >= 1024:
                        self._blocked_media_groups.clear()
                    self._blocked_media_groups.add(group_key)
                # Preserve the historical text path for a genuine caption, but
                # remove attachments so no downstream image authority exists.
                if payload.message_text.strip():
                    return await self.handle_payload(replace(payload, attachments=()))
                return None
            media_operation = await self._inbound_media.process(
                creator_profile_id=int(self._inbound_adapter._creator_profile_id),
                fanvue_account_id=int(self._inbound_adapter._fanvue_account_id),
                payload=payload,
                downloader=self._transport.download_inbound_attachment,
            )
            joined_reservation = None
            if self._turn_reservations is not None and captured_inbound is not None:
                joined_reservation = await asyncio.to_thread(
                    self._turn_reservations.join_media,
                    creator_profile_id=int(creator_id), fanvue_account_id=int(account_id),
                    inbound=captured_inbound,
                )
            media_turn = None
            if self._visual_turns is not None and captured_inbound is not None:
                media_turn = await asyncio.to_thread(
                    self._visual_turns.establish,
                    media_operation=media_operation,
                    inbound_members=({
                        "inbound_id": captured_inbound.inbound_id,
                        "telegram_message_id": captured_inbound.telegram_message_id,
                        "has_media": captured_inbound.has_media,
                    },),
                )
            if self._inbound_image_safety is not None:
                image_policy = await self._inbound_image_safety.process_operation(
                    media_operation, immediate_messages=payload.chat_history,
                )
            else:
                image_policy = None
            if image_policy is not None and self._image_response_enabled:
                visual_context = await self._inbound_image_safety.response_context(
                    media_operation,image_policy)
                if media_turn is not None:
                    visual_context["media_turn_id"] = str(media_turn["media_turn_id"])
                canonical_message_id=min(
                    item.telegram_message_id for item in payload.attachments)
                payload=replace(payload,message_id=canonical_message_id,
                    current_turn_visual_context=visual_context)
                if (joined_reservation is not None
                        and joined_reservation.get("authoritative_response_operation_id")):
                    owner = await asyncio.to_thread(
                        self._ordinary_replies.repository.get,
                        joined_reservation["authoritative_response_operation_id"],
                    )
                    if owner is not None:
                        payload = replace(
                            payload, message_id=int(owner.inbound_telegram_message_id),
                            message_text=str(owner.inbound_message_text or ""),
                            ordinary_reply_operation_id=str(owner.operation_id),
                        )
                result=await self.handle_payload(payload)
            else:
                result = await asyncio.to_thread(
                    self._inbound_adapter.execute, payload, observe_only=True,
                )
        else:
            result = await self.handle_payload(payload)
            if text_reservation is not None:
                await asyncio.to_thread(
                    self._turn_reservations.bind_captured_owner,
                    text_reservation["reservation_id"], captured_inbound.inbound_id,
                )
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "inbound_success", lambda: self._heartbeat.heartbeat(metadata={
            "last_successful_inbound_handling_time": self._heartbeat.now().isoformat(),
        }))
        return result

    async def _wait_with_typing(
        self, *, chat_id: int, decision: Any,
        telegram_user_id: int | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Overlay native typing and its narrow UX floor on certified pacing."""

        show_typing_while = getattr(self._transport, "show_typing_while", None)
        if not callable(show_typing_while) or decision.applied_delay_ms <= 0:
            await self._response_pacing.wait(decision)
            return
        # This is a presentation floor, not a second pacing algorithm. The
        # calculated/persisted pacing decision and its 9-second ceiling remain
        # unchanged; only a short customer-visible typing wait is extended.
        visible_delay_ms = max(2000, int(decision.applied_delay_ms))
        visible_decision = replace(decision, applied_delay_ms=visible_delay_ms)
        self._logger.info(
            "event=telegram_typing_window correlation_id=%s chat_id=%s "
            "certified_delay_ms=%s visible_delay_ms=%s",
            correlation_id or "unknown",
            self._safe_telegram_identifier(chat_id),
            decision.applied_delay_ms, visible_delay_ms,
        )
        await show_typing_while(
            chat_id=chat_id,
            telegram_user_id=telegram_user_id,
            correlation_id=correlation_id,
            operation=self._response_pacing.wait(visible_decision),
        )

    @staticmethod
    def _safe_telegram_identifier(value: int) -> str:
        text = str(value)
        return text if len(text) <= 6 else f"{text[:4]}...{text[-4:]}"

    @staticmethod
    def _safe_correlation_id(value: str) -> str:
        """Keep a joinable fingerprint without leaking embedded Telegram IDs."""
        import hashlib
        return f"sha256:{hashlib.sha256(str(value).encode()).hexdigest()[:16]}"

    async def run(self) -> None:
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "startup", self._heartbeat.register_startup)
        heartbeat_task = None
        engagement_task = None
        business_connection_task = None
        sleep_wake_task = None
        availability_task = None
        media_cleanup_task = None
        failed = False
        try:
            if self._ordinary_reply_schema_preflight is not None:
                await asyncio.to_thread(self._ordinary_reply_schema_preflight)
            if self._ownership is not None and not await asyncio.to_thread(self._ownership.acquire):
                raise TelethonRuntimeError("Another authoritative Ava Telegram worker owns the account scope.")
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "ownership", lambda: self._heartbeat.heartbeat(metadata={
                "account_scope": self.ACCOUNT_SCOPE,
                "database_healthy": True,
                "lifecycle_state": "STARTING",
            }))
            if self._sales_deliveries is not None:
                await asyncio.to_thread(self._sales_deliveries.recover_startup)
                await asyncio.to_thread(self._sales_deliveries.recover_accepted)
            if self._ordinary_replies is not None:
                await asyncio.to_thread(self._ordinary_replies.recover_startup)
            if self._engagement_teasers is not None:
                await asyncio.to_thread(self._engagement_teasers.delivery.recover_startup)
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            if self._inbound_image_safety is not None:
                media_cleanup_task = asyncio.create_task(self._media_cleanup_loop())
            if self._scheduled_engagement_worker is not None:
                engagement_task = asyncio.create_task(self._scheduled_engagement_loop())
            if self._business_connection_worker is not None:
                business_connection_task = asyncio.create_task(
                    self._business_connection_loop()
                )
            if self._ordinary_replies is not None:
                sleep_wake_task = asyncio.create_task(self._sleep_wake_loop())
                if self._availability is not None:
                    availability_task = asyncio.create_task(
                        self._availability_loop(), name="ordinary-reply-availability-scheduler"
                    )
                    availability_task.add_done_callback(
                        self._availability_task_completed
                    )
            await self._connection_loop()
            if self._fatal_background_error is not None:
                raise self._fatal_background_error
        except TelethonAuthorizationRequiredError as error:
            failed = True
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "authorization", lambda: self._heartbeat.record_terminal_failure(error, metadata={"lifecycle_state": "FAILED", "authorization_required": True}))
            raise
        except Exception as error:
            failed = True
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "failure", lambda: self._heartbeat.record_terminal_failure(error, metadata={"lifecycle_state": "FAILED"}))
            raise
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass
            if engagement_task is not None:
                engagement_task.cancel()
                try:
                    await engagement_task
                except asyncio.CancelledError:
                    pass
            if business_connection_task is not None:
                business_connection_task.cancel()
                try:
                    await business_connection_task
                except asyncio.CancelledError:
                    pass
            if sleep_wake_task is not None:
                sleep_wake_task.cancel()
                try:
                    await sleep_wake_task
                except asyncio.CancelledError:
                    pass
            if availability_task is not None:
                availability_task.cancel()
                try:
                    await availability_task
                except asyncio.CancelledError:
                    pass
            resume_tasks = tuple(self._ordinary_resume_tasks.values())
            for task in resume_tasks:
                task.cancel()
            if resume_tasks:
                await asyncio.gather(*resume_tasks, return_exceptions=True)
            if media_cleanup_task is not None:
                media_cleanup_task.cancel()
                try:
                    await media_cleanup_task
                except asyncio.CancelledError:
                    pass
            await self._transport.disconnect()
            if self._ownership is not None:
                await asyncio.to_thread(self._ownership.release)
            if not failed:
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "shutdown_reason", lambda: self._heartbeat.heartbeat(metadata={
                    "lifecycle_state": "STOPPING",
                    "shutdown_reason": getattr(self, "_shutdown_reason", "runtime_completed"),
                }))
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "stopping", self._heartbeat.record_stopping)
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "shutdown", self._heartbeat.record_shutdown)

    def request_shutdown(self, reason: str = "intentional_shutdown") -> None:
        self._shutdown_reason = reason
        self._shutdown.set()

    async def _connection_loop(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._shutdown.is_set():
            connected_at = loop.time()
            try:
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "connecting", lambda: self._heartbeat.heartbeat(metadata={
                    "lifecycle_state": "CONNECTING", "reconnect_attempt_count": self._reconnect_attempts,
                    "next_retry_at": None, "database_healthy": True,
                }))
                await self._transport.start()
                self._transport_connected = True
                try:
                    recovery = await self._recover_startup_history()
                except Exception as error:
                    self._startup_history_recovery = {
                        "complete": False, "status": "FAILED",
                        "error": type(error).__name__,
                    }
                    await asyncio.to_thread(
                        record_heartbeat_safely, self._logger,
                        "startup_history_recovery_failure",
                        lambda: self._heartbeat.record_failure(error, metadata={
                            "startup_history_recovery_complete": False,
                            "startup_history_recovery_status": "FAILED",
                            "startup_history_recovery_error": type(error).__name__,
                        }),
                    )
                    raise
                self._startup_history_recovery = recovery
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "connection_success", lambda: self._heartbeat.record_success(idle=False))
                await asyncio.to_thread(record_heartbeat_safely, self._logger, "connected", lambda: self._heartbeat.heartbeat(metadata={
                    "lifecycle_state": "CONNECTED", "authorized": True,
                    "last_telegram_connection_success": self._heartbeat.now().isoformat(),
                    "next_retry_at": None, "next_retry_at_epoch": None,
                    "reconnect_attempt_count": self._reconnect_attempts,
                    "startup_history_recovery_complete": recovery["complete"],
                    "startup_history_recovery_status": recovery["status"],
                    "startup_history_recovery_last_success": self._heartbeat.now().isoformat(),
                    "startup_history_recovery_inspected": recovery["inspected"],
                    "startup_history_recovery_captured": recovery["captured"],
                    "startup_history_recovery_chats": recovery["chats"],
                    "startup_history_recovery_operations": recovery["operations"],
                    **self._controlled_autonomy.audit_metadata(),
                    **self._media_processing_scope.audit_metadata(),
                }))
                if self._image_response_enabled and self._inbound_image_safety is not None:
                    recovery_payloads=await self._inbound_image_safety.recovery_payloads()
                    for recovery_payload in recovery_payloads:
                        scope = self._media_processing_scope.decide(
                            telegram_user_id=recovery_payload.telegram_user_id,
                            telegram_chat_id=recovery_payload.telegram_chat_id,
                        )
                        if scope.allowed:
                            await self.handle_payload(recovery_payload)
                        else:
                            self._logger.info(
                                "event=telegram_customer_media_recovery_scope status=blocked "
                                "reason=%s mode=%s chat_id=%s user_id=%s",
                                scope.reason, scope.mode,
                                self._safe_telegram_identifier(recovery_payload.telegram_chat_id),
                                self._safe_telegram_identifier(recovery_payload.telegram_user_id),
                            )
                await self._transport.run_until_disconnected()
                if self._shutdown.is_set():
                    return
                raise ConnectionError("Telethon disconnected unexpectedly.")
            except TelethonAuthorizationRequiredError:
                raise
            except asyncio.CancelledError:
                raise
            except (TelethonTransientError, ConnectionError, TimeoutError, OSError) as error:
                await self._schedule_reconnect(error, loop.time() - connected_at)
            finally:
                self._transport_connected = False
                await self._transport.disconnect()

    async def _recover_startup_history(self) -> dict[str, Any]:
        """Capture and reconcile a bounded, archive-idempotent history overlap."""
        reader = getattr(self._transport, "bounded_private_inbound_history", None)
        boundary_reader = getattr(self._private_inbound_backlog, "latest_boundary", None)
        if not callable(reader) or not callable(boundary_reader):
            return {"complete": True, "status": "NOT_CONFIGURED", "inspected": 0,
                    "captured": 0, "chats": 0, "operations": 0}
        now = self._heartbeat.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        overlap_hours = max(1, min(24, int(os.getenv(
            "TELEGRAM_STARTUP_HISTORY_OVERLAP_HOURS", "6"))))
        lookback_hours = max(overlap_hours, min(72, int(os.getenv(
            "TELEGRAM_STARTUP_HISTORY_MAX_LOOKBACK_HOURS", "24"))))
        boundary = await asyncio.to_thread(
            boundary_reader, account_scope=self.ACCOUNT_SCOPE)
        floor = now - timedelta(hours=lookback_hours)
        since = floor
        if boundary and boundary.get("received_at") is not None:
            since = max(floor, boundary["received_at"] - timedelta(hours=overlap_hours))
        payloads = await reader(
            since=since,
            dialog_limit=max(1, min(250, int(os.getenv(
                "TELEGRAM_STARTUP_HISTORY_DIALOG_LIMIT", "100")))),
            per_dialog_limit=max(1, min(500, int(os.getenv(
                "TELEGRAM_STARTUP_HISTORY_PER_DIALOG_LIMIT", "100")))),
        )
        chats: dict[int, TelegramInboundPayload] = {}
        captured = 0
        for payload in payloads:
            _row, created = await asyncio.to_thread(
                self._private_inbound_backlog.capture, payload,
                account_scope=self.ACCOUNT_SCOPE, automation_state="OFF",
                creator_profile_id=getattr(self._inbound_adapter, "_creator_profile_id", None),
                fanvue_account_id=getattr(self._inbound_adapter, "_fanvue_account_id", None),
                provenance="TELETHON_STARTUP_HISTORY_RECOVERY",
            )
            captured += int(created)
            observer = getattr(self._inbound_adapter, "observe_identity_and_relationship", None)
            if callable(observer):
                await asyncio.to_thread(observer, payload)
            chats[payload.telegram_chat_id] = payload
        self._global_safety_service.refresh()
        configured = getattr(self._global_safety_service, "behavior_config", {}) or {}
        operations = 0
        if configured.get("global_automation_enabled"):
            controls = getattr(self._inbound_adapter, "_relationship_controls", None)
            creator_id = getattr(self._inbound_adapter, "_creator_profile_id", None)
            account_id = getattr(self._inbound_adapter, "_fanvue_account_id", None)
            for chat_id, payload in chats.items():
                response_allowed = True
                if controls is not None and creator_id and account_id:
                    response_allowed, _control = await asyncio.to_thread(
                        controls.autonomous_allowed,
                        creator_profile_id=int(creator_id),
                        fanvue_account_id=int(account_id),
                        telegram_user_id=int(payload.telegram_user_id),
                        telegram_chat_id=int(payload.telegram_chat_id),
                    )
                result = await asyncio.to_thread(
                    self._private_inbound_backlog.reconcile_chat,
                    account_scope=self.ACCOUNT_SCOPE, chat_id=chat_id,
                    response_allowed=bool(response_allowed),
                )
                operations += int(bool(result.get("response_operation_id")))
        result = {"complete": True, "status": "COMPLETE",
                  "inspected": len(payloads), "captured": captured,
                  "chats": len(chats), "operations": operations,
                  "since": since.isoformat()}
        self._logger.info(
            "event=telegram_startup_history_recovery status=complete "
            "inspected=%s captured=%s chats=%s operations=%s",
            result["inspected"], result["captured"], result["chats"],
            result["operations"],
        )
        return result

    async def _schedule_reconnect(self, error: Exception, connected_seconds: float) -> None:
        if connected_seconds >= self._stable_reset:
            self._reconnect_attempts = 0
        self._reconnect_attempts += 1
        raw_delay = min(self._reconnect_max, self._reconnect_initial * (2 ** (self._reconnect_attempts - 1)))
        delay = max(0.0, float(self._jitter(raw_delay)))
        next_retry = self._heartbeat.now().timestamp() + delay
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "reconnecting", lambda: self._heartbeat.record_failure(error))
        await asyncio.to_thread(record_heartbeat_safely, self._logger, "retry", lambda: self._heartbeat.heartbeat(metadata={
            "lifecycle_state": "RECONNECTING", "last_telegram_disconnect": self._heartbeat.now().isoformat(),
            "last_reconnect_attempt": self._heartbeat.now().isoformat(),
            "reconnect_attempt_count": self._reconnect_attempts,
            "next_retry_at_epoch": next_retry,
        }))
        try:
            await asyncio.wait_for(self._shutdown.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def _heartbeat_loop(self) -> None:
        while True:
            if self._ownership is not None:
                try:
                    await asyncio.to_thread(self._ownership.check)
                except Exception as error:
                    await asyncio.to_thread(record_heartbeat_safely, self._logger, "database", lambda: self._heartbeat.record_failure(error))
                    self._fatal_background_error = error
                    self.request_shutdown("database_ownership_lost")
                    await self._transport.disconnect()
                    return
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "poll", self._heartbeat.record_poll)
            await asyncio.to_thread(record_heartbeat_safely, self._logger, "success", lambda: self._heartbeat.record_success(idle=True))
            await asyncio.sleep(self._heartbeat_interval)

    async def _scheduled_engagement_loop(self) -> None:
        while True:
            safety = self._global_safety_service.check_global_safety()
            if safety.get("allowed", False):
                await self._scheduled_engagement_worker.process_one(transport=self._transport)
            await asyncio.sleep(60)

    async def _media_cleanup_loop(self) -> None:
        """Bounded cleanup in the existing worker; failures never stop Telegram."""
        while True:
            try:
                removed=await asyncio.to_thread(self._inbound_media.cleanup_expired)
                if removed:
                    self._logger.info(
                        "event=telegram_media_cleanup status=success removed=%s",removed)
            except Exception as error:
                self._logger.warning(
                    "event=telegram_media_cleanup status=failure error_type=%s",
                    type(error).__name__)
            await asyncio.sleep(self._media_cleanup_interval)

    async def _business_connection_loop(self) -> None:
        """Supervise Business metadata ingestion independently of chat health."""
        while True:
            failed = False
            try:
                await asyncio.to_thread(self._business_connection_worker.poll_once)
            except Exception:
                failed = True
                self._logger.warning("Business ingestion unavailable; inspect business_ingestion heartbeat metadata")
            await asyncio.to_thread(
                record_heartbeat_safely, self._logger, "business_ingestion",
                lambda: self._heartbeat.heartbeat(metadata={
                    "business_ingestion": dict(self._business_connection_worker.health),
                }),
            )
            if failed:
                await asyncio.sleep(5)

    async def _sleep_wake_loop(self) -> None:
        """Release one consolidated deferred inbound per chat after wake."""
        while True:
            now = self._heartbeat.now()
            decision = self._sleep_service.evaluate(now=now)
            if decision.state.value == "AWAKE" and self._transport_connected:
                payloads = await asyncio.to_thread(
                    self._ordinary_replies.due_sleep_payloads, now=now,
                )
                for payload in payloads:
                    await self.handle_payload(payload)
            await asyncio.sleep(60)

    async def _availability_loop(self) -> None:
        """Supervise durable reply scheduling independently from Telegram I/O."""
        while True:
            polled_at = self._heartbeat.now()
            await asyncio.to_thread(
                record_heartbeat_safely, self._logger, "ordinary_reply_scheduler_poll",
                lambda: self._heartbeat.heartbeat(metadata={
                    "ordinary_reply_scheduler_alive": True,
                    "ordinary_reply_scheduler_healthy": self._availability_failure_count == 0,
                    "ordinary_reply_scheduler_last_poll": polled_at.isoformat(),
                }),
            )
            try:
                result = await self._availability_iteration(now=polled_at)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._availability_failure_count += 1
                delay = min(
                    self._availability_failure_backoff_max,
                    self._availability_failure_backoff_initial
                    * (2 ** (self._availability_failure_count - 1)),
                )
                failed_at = self._heartbeat.now()
                self._logger.exception(
                    "event=ordinary_reply_scheduler_iteration_failed stage=poll "
                    "failure_count=%s retry_seconds=%.2f",
                    self._availability_failure_count, delay,
                )
                await asyncio.to_thread(
                    record_heartbeat_safely, self._logger,
                    "ordinary_reply_scheduler_failure",
                    lambda: self._heartbeat.heartbeat(metadata={
                        "ordinary_reply_scheduler_alive": True,
                        "ordinary_reply_scheduler_healthy": False,
                        "ordinary_reply_scheduler_last_failure": failed_at.isoformat(),
                        "ordinary_reply_scheduler_last_error": (
                            f"{type(error).__name__}: {error}"
                        )[:1000],
                        "ordinary_reply_scheduler_consecutive_failures": (
                            self._availability_failure_count
                        ),
                        "ordinary_reply_scheduler_retry_seconds": delay,
                    }),
                )
                await asyncio.sleep(delay)
                continue
            self._availability_failure_count = 0
            succeeded_at = self._heartbeat.now()
            await asyncio.to_thread(
                record_heartbeat_safely, self._logger,
                "ordinary_reply_scheduler_success",
                lambda: self._heartbeat.heartbeat(metadata={
                    "ordinary_reply_scheduler_alive": True,
                    "ordinary_reply_scheduler_healthy": True,
                    "ordinary_reply_scheduler_last_success": succeeded_at.isoformat(),
                    "ordinary_reply_scheduler_last_error": None,
                    "ordinary_reply_scheduler_consecutive_failures": 0,
                    "ordinary_reply_scheduler_retry_seconds": None,
                    "ordinary_reply_scheduler_last_result": result,
                }),
            )
            await asyncio.sleep(1)

    async def _availability_iteration(self, *, now) -> dict[str, int | bool]:
        result = {
            "transportConnected": bool(self._transport_connected),
            "expiredGeneratingFound": 0,
            "expiredGeneratingReclaimed": 0,
            "expiredGeneratingSuperseded": 0,
            "pendingSupersededFinalized": 0,
            "unscheduledRetryableFound": 0,
            "unscheduledRetryableFinalizedOrRescheduled": 0,
            "pendingReclaimed": 0,
            "backlogPending": 0,
            "strandedGeneratedRecovered": 0,
            "availabilityDue": 0,
            "generatedSendDue": 0,
            "resumeTasksActive": 0,
            "resumeTasksCoolingDown": 0,
            "manualPrivateDispatches": 0,
        }
        if not self._transport_connected:
            return result
        if self._transport_certification is not None:
            await self._transport_certification.poll(self._transport)
        if self._operator_messages is not None:
            from app.services.telegram_transport_boundary import RoutedTelegramSender, ManualInvocationRecorder
            await asyncio.to_thread(self._operator_messages.recover_expired_invocations)
            pending = await asyncio.to_thread(
                self._operator_messages.pending_private_dispatches, 10)
            for operation in pending:
                result["manualPrivateDispatches"] += 1
                recorder = ManualInvocationRecorder(self._operator_messages, operation)
                sender = RoutedTelegramSender(self._transport, context={
                    "record_transport_evidence": recorder,
                    "operation_id": str(operation["operation_id"]),
                    "provider_attempt_id": recorder.owner}, metadata={})
                try:
                    sent = await sender.send_text(
                        chat_id=int(operation["telegram_chat_id"]),
                        message_text=operation["message_text"])
                    message_id = getattr(sent, "id", sent)
                    if not isinstance(message_id, int) or isinstance(message_id, bool):
                        raise ConnectionError(
                            "Telegram acceptance lacked a provider message ID.")
                except (ValueError, TelethonProviderRejectedError) as error:
                    await asyncio.to_thread(self._operator_messages.failed,
                        operation["operation_id"], error, owner=recorder.final_owner)
                except Exception as error:
                    await asyncio.to_thread(self._operator_messages.ambiguous,
                        operation["operation_id"], error, owner=recorder.final_owner)
                else:
                    await asyncio.to_thread(self._operator_messages.confirmed,
                        operation["operation_id"], message_id, owner=recorder.final_owner)
        if self._manual_offer_dispatcher is not None:
            result['manualOfferDispatches'] = await self._manual_offer_dispatcher.dispatch_pending()
        self._global_safety_service.refresh()
        raw_config = getattr(self._global_safety_service, "behavior_config", {}) or {}
        automation_allowed = (
            raw_config.get("global_automation_enabled") is True
            and raw_config.get("global_sends_enabled") is True
        )
        if automation_allowed:
            lifecycle_maintenance = getattr(
                self._ordinary_replies, "maintain_stranded_lifecycle", None,
            )
            if callable(lifecycle_maintenance):
                maintenance = await asyncio.to_thread(
                    lifecycle_maintenance, now=now,
                )
                for key in (
                    "expiredGeneratingFound", "expiredGeneratingReclaimed",
                    "expiredGeneratingSuperseded", "pendingSupersededFinalized",
                    "unscheduledRetryableFound",
                    "unscheduledRetryableFinalizedOrRescheduled",
                ):
                    result[key] = int(maintenance.get(key) or 0)
                for payload in maintenance.get("payloads") or ():
                    self._schedule_ordinary_resume(payload, now=now)
            stranded_recovery = getattr(
                self._ordinary_replies, "recover_stranded_generated", None,
            )
            if callable(stranded_recovery):
                recovered = await asyncio.to_thread(stranded_recovery, now=now)
                result["strandedGeneratedRecovered"] = len(recovered)
                for operation in recovered:
                    self._logger.warning(
                        "event=ordinary_reply_stranded_generated_recovered "
                        "operation_id=%s state=%s fresh_generation=%s",
                        operation.operation_id, operation.state.value,
                        operation.response_payload is None,
                    )
            pending_reclaimer = getattr(
                self._ordinary_replies, "reclaim_stranded_pending_payloads", None,
            )
            if callable(pending_reclaimer):
                reclaimed = await asyncio.to_thread(pending_reclaimer, now=now)
                result["pendingReclaimed"] = len(reclaimed)
                for payload in reclaimed:
                    self._schedule_ordinary_resume(payload, now=now)
            pending = await asyncio.to_thread(
                self._ordinary_replies.pending_backlog_payloads,
            )
            result["backlogPending"] = len(pending)
            for payload in pending:
                self._schedule_ordinary_resume(payload, now=now)
        payloads = await asyncio.to_thread(
            self._ordinary_replies.due_availability_payloads, now=now,
        )
        result["availabilityDue"] = len(payloads)
        for payload in payloads:
            self._schedule_ordinary_resume(payload, now=now)
        generated_retries = await asyncio.to_thread(
            self._ordinary_replies.due_generated_send_payloads, now=now,
        )
        result["generatedSendDue"] = len(generated_retries)
        for payload in generated_retries:
            self._schedule_ordinary_resume(payload, now=now)
        result["resumeTasksActive"] = sum(
            not task.done() for task in self._ordinary_resume_tasks.values()
        )
        result["resumeTasksCoolingDown"] = sum(
            item["retry_at"] > now for item in self._ordinary_resume_failures.values()
        )
        return result

    @staticmethod
    def _ordinary_resume_key(payload) -> tuple[int, int]:
        return int(payload.telegram_chat_id), int(payload.message_id)

    def _schedule_ordinary_resume(self, payload, *, now) -> bool:
        """Start at most one supervised resume per durable inbound obligation."""
        key = self._ordinary_resume_key(payload)
        active = self._ordinary_resume_tasks.get(key)
        if active is not None and not active.done():
            return False
        failure = self._ordinary_resume_failures.get(key)
        if failure is not None and failure["retry_at"] > now:
            return False
        task = asyncio.create_task(
            self._resume_available_payload(payload),
            name=f"ordinary-reply-resume-{key[1]}",
        )
        self._ordinary_resume_tasks[key] = task
        task.add_done_callback(
            lambda completed, resume_key=key: self._ordinary_resume_task_completed(
                resume_key, completed
            )
        )
        return True

    def _ordinary_resume_task_completed(self, key, task: asyncio.Task) -> None:
        self._ordinary_resume_tasks.pop(key, None)
        if task.cancelled():
            return
        error = task.exception()
        now = self._heartbeat.now()
        if error is None:
            had_failure = self._ordinary_resume_failures.pop(key, None)
            if had_failure is not None:
                asyncio.create_task(self._record_ordinary_resume_health(
                    healthy=True, at=now, key=key, failure_count=0,
                    retry_seconds=None, error=None,
                ))
            return
        prior = self._ordinary_resume_failures.get(key) or {"count": 0}
        count = int(prior["count"]) + 1
        delay = min(
            self._availability_failure_backoff_max,
            self._availability_failure_backoff_initial * (2 ** (count - 1)),
        )
        from datetime import timedelta
        self._ordinary_resume_failures[key] = {
            "count": count, "retry_at": now + timedelta(seconds=delay),
            "error": f"{type(error).__name__}: {error}"[:1000],
        }
        self._logger.exception(
            "event=ordinary_reply_resume_failed message_id=%s "
            "failure_count=%s retry_seconds=%.2f",
            key[1], count, delay, exc_info=error,
        )
        asyncio.create_task(self._record_ordinary_resume_health(
            healthy=False, at=now, key=key, failure_count=count,
            retry_seconds=delay, error=error,
        ))

    async def _record_ordinary_resume_health(
        self, *, healthy, at, key, failure_count, retry_seconds, error,
    ) -> None:
        # Per-recipient eligibility is not a runtime outage. Keep the same
        # rejection/backoff, but publish it separately from execution failures.
        if getattr(error, "health_scope", None) == "RECIPIENT_REACHABILITY":
            await asyncio.to_thread(
                record_heartbeat_safely, self._logger, "ordinary_reply_peer_unavailable",
                lambda: self._heartbeat.heartbeat(metadata={
                    "ordinary_reply_peer_reachability": {
                        "scope": "RECIPIENT_REACHABILITY", "available": False,
                        "chat_id": key[0], "message_id": key[1],
                        "observed_at": at.isoformat(), "error_code": error.code,
                        "error": f"{type(error).__name__}: {error}",
                        "failure_count": failure_count, "retry_seconds": retry_seconds,
                    },
                }),
            )
            return
        metadata = {
            "ordinary_reply_resume_healthy": healthy,
            "ordinary_reply_resume_last_success": at.isoformat() if healthy else None,
            "ordinary_reply_resume_last_failure": None if healthy else at.isoformat(),
            "ordinary_reply_resume_last_error": (
                None if error is None else f"{type(error).__name__}: {error}"[:1000]
            ),
            "ordinary_reply_resume_consecutive_failures": failure_count,
            "ordinary_reply_resume_retry_seconds": retry_seconds,
            "ordinary_reply_resume_failed_message_id": None if healthy else key[1],
            "ordinary_reply_resume_cooling_down": len(self._ordinary_resume_failures),
        }
        await asyncio.to_thread(
            record_heartbeat_safely, self._logger, "ordinary_reply_resume_health",
            lambda: self._heartbeat.heartbeat(metadata=metadata),
        )

    def _availability_task_completed(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is None:
            error = TelethonRuntimeError(
                "Ordinary reply availability scheduler stopped unexpectedly."
            )
        self._fatal_background_error = error
        self._logger.critical(
            "event=ordinary_reply_scheduler_stopped_unexpectedly error=%s", error
        )
        self.request_shutdown("ordinary_reply_scheduler_stopped")

    async def _resume_available_payload(self, payload):
        """Re-evaluate live authority when a durable availability wait expires."""
        global_result = self._global_safety_service.check_global_safety()
        controlled = self._controlled_autonomy.decide(
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
        )
        if not global_result.get("allowed", False) and not controlled.allowed:
            return None
        if not global_result.get("allowed", False):
            with self._controlled_autonomy.scope(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
            ):
                return await self._handle_authorized_payload(payload, availability_released=True)
        return await self._handle_authorized_payload(payload, availability_released=True)

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
                "[TELEGRAM PAUSED] inbound message observed without automation "
                "chat_id=%s user_id=%s",
                payload.telegram_chat_id,
                payload.telegram_user_id,
            )
            return await asyncio.to_thread(
                self._inbound_adapter.execute, payload, observe_only=True,
            )

        global_result = self._global_safety_service.check_global_safety()
        controlled_result = self._controlled_autonomy.decide(
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
        )
        if not global_result.get("allowed", False) and not controlled_result.allowed:
            self._logger.info(
                "[TELEGRAM AUTONOMY BLOCKED] inbound observed chat_id=%s reason=%s",
                payload.telegram_chat_id, global_result.get("reason"),
            )
            return await asyncio.to_thread(
                self._inbound_adapter.execute, payload, observe_only=True,
            )

        if not global_result.get("allowed", False):
            with self._controlled_autonomy.scope(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
            ):
                return await self._handle_authorized_payload(payload)
        return await self._handle_authorized_payload(payload)

    async def _handle_authorized_payload(
        self, payload: TelegramInboundPayload, *, availability_released: bool = False,
    ) -> TelegramInboundResult | None:

        lock = self._chat_locks.setdefault(payload.telegram_chat_id, asyncio.Lock())
        async with lock:
            ordinary_operation = None
            claimed_operation = None
            claimed_ordinary = None
            try:
                if self._ordinary_replies is None:
                    result = await asyncio.to_thread(
                        self._inbound_adapter.execute, payload,
                    )
                else:
                    ordinary_operation, ordinary_created = await asyncio.to_thread(
                        self._ordinary_replies.begin, payload,
                    )
                    if payload.current_turn_visual_context.get("media_turn_id") and self._visual_turns is not None:
                        await asyncio.to_thread(
                            self._visual_turns.repository.bind_response_owner,
                            media_turn_id=payload.current_turn_visual_context["media_turn_id"],
                            operation_id=ordinary_operation.operation_id,
                            visual_context=payload.current_turn_visual_context)
                        ordinary_operation = await asyncio.to_thread(
                            self._ordinary_replies.repository.get, ordinary_operation.operation_id)
                        payload = self._ordinary_replies.retry_payload(ordinary_operation)
                    backlog_correlator = getattr(
                        self._private_inbound_backlog, "correlate", None)
                    if callable(backlog_correlator):
                        await asyncio.to_thread(
                            backlog_correlator, payload,
                            account_scope=self.ACCOUNT_SCOPE,
                            response_operation_id=ordinary_operation.operation_id)
                    if not ordinary_created:
                        self._logger.info(
                            "event=ordinary_reply_duplicate_inbound operation_id=%s state=%s",
                            ordinary_operation.operation_id,
                            ordinary_operation.state.value,
                        )
                    ignored_reader = getattr(
                        self._ordinary_replies, "relationship_ignored", None)
                    if (callable(ignored_reader) and await asyncio.to_thread(
                            ignored_reader, ordinary_operation)):
                        await asyncio.to_thread(
                            self._ordinary_replies.suppress_ignored, ordinary_operation)
                        self._logger.info(
                            "event=telegram_reply_ignored operation_id=%s reason=RELATIONSHIP_IGNORED ai_generation_count=0",
                            ordinary_operation.operation_id)
                        return None
                    language_disposition = None
                    language_policy = getattr(
                        self._ordinary_replies, "apply_english_only_policy", None)
                    if callable(language_policy):
                        language_disposition = await asyncio.to_thread(
                            language_policy, ordinary_operation)
                        if language_disposition.action.startswith("SUPPRESSED_"):
                            self._logger.info(
                                "event=telegram_non_english_reply_suppressed operation_id=%s reason=%s ai_generation_count=0",
                                ordinary_operation.operation_id,
                                getattr(language_disposition.operation, "last_error", None))
                            return None
                        ordinary_operation = language_disposition.operation
                    if (self._availability is not None
                            and ordinary_operation.state.value == "PENDING_GENERATION"):
                        profile_reader = getattr(
                            self._ordinary_replies, "relationship_scheduling_profile", None)
                        if callable(profile_reader):
                            profile = await asyncio.to_thread(profile_reader,
                                creator_profile_id=int(self._inbound_adapter._creator_profile_id),
                                fanvue_account_id=int(self._inbound_adapter._fanvue_account_id),
                                telegram_user_id=payload.telegram_user_id,
                                telegram_chat_id=payload.telegram_chat_id)
                        else:
                            profile = {"market_tier": "UNCLASSIFIED",
                                       "high_value_prospect": False}
                        peak_context_reader=getattr(
                            self._ordinary_replies,"peak_engagement_context",None)
                        peak_context=(await asyncio.to_thread(
                            peak_context_reader,ordinary_operation)
                            if callable(peak_context_reader) else {})
                        active_exchange=peak_context.get("confirmed_exchange_at")
                        sleep_for_peak=self._sleep_service.evaluate(
                            active_conversation=active_exchange is not None)
                        peak_context.update({
                            "sleeping":sleep_for_peak.state.value=="ASLEEP",
                            "sleep_pending_signoff":sleep_for_peak.state.value=="SLEEP_PENDING_SIGNOFF",
                        })
                        peak_verified=bool(peak_context.pop(
                            "verified_buyer",profile.get("verified_buyer",False)))
                        availability = self._availability.calculate(
                            inbound_text=payload.message_text,
                            received_at=payload.received_at,
                            high_value_prospect=profile["high_value_prospect"],
                            market_tier=profile["market_tier"],
                            verified_buyer=peak_verified,
                            peak_engagement_context=peak_context,
                        )
                        # Availability establishes delivery on the initial pass.
                        # At the preparation boundary, BUSY must not postpone
                        # generation again; the persisted reply stays held until
                        # its scheduled delivery time.
                        if not availability_released:
                            await asyncio.to_thread(
                                self._ordinary_replies.defer_for_availability,
                                ordinary_operation, availability,
                            )
                            self._logger.info(
                                "event=telegram_reply_availability_scheduled operation_id=%s category=%s available_at=%s session_id=%s",
                                ordinary_operation.operation_id, availability.category,
                                availability.available_at.isoformat(), availability.session_id,
                            )
                            return None
                    sleep_context_reader = getattr(
                        self._ordinary_replies, "sleep_context", None,
                    )
                    sleep_decision = (
                        await asyncio.to_thread(
                            sleep_context_reader, ordinary_operation,
                            sleep_service=self._sleep_service,
                        )
                        if callable(sleep_context_reader)
                        else self._sleep_service.evaluate()
                    )
                    if sleep_decision.response_deferred:
                        await asyncio.to_thread(
                            self._ordinary_replies.defer_for_sleep,
                            ordinary_operation, sleep_decision,
                        )
                        self._logger.info(
                            "event=telegram_reply_deferred_for_sleep operation_id=%s wake=%s",
                            ordinary_operation.operation_id, sleep_decision.wake_time.isoformat(),
                        )
                        return None
                    from dataclasses import replace
                    payload = replace(
                        payload, sleep_context=sleep_decision.diagnostics(),
                    )
                    result = self._ordinary_replies.result(ordinary_operation)
                    if result is not None:
                        suppress_if_stale = getattr(
                            self._ordinary_replies, "suppress_if_stale", None,
                        )
                        stale = (
                            await asyncio.to_thread(suppress_if_stale, ordinary_operation)
                            if callable(suppress_if_stale) else None
                        )
                        if stale is not None:
                            self._logger.info(
                                "event=ordinary_reply_stale_blocked operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id,
                            )
                            return result
                    if result is None:
                        if (language_disposition is not None
                                and language_disposition.action == "FIRST_NOTICE"):
                            result = self._ordinary_replies.english_only_notice_result(
                                ordinary_operation, payload)
                            pacing = self._response_pacing.calculate(
                                inbound_text=payload.message_text,
                                reply_text=result.response_text,
                                commercial=False, acknowledgement=False, shadow=False,
                                telegram_user_id=payload.telegram_user_id)
                            result.diagnostic_metadata["response_pacing"] = pacing.diagnostics()
                            ordinary_operation = await asyncio.to_thread(
                                self._ordinary_replies.store_english_only_notice,
                                ordinary_operation, result)
                            if ordinary_operation is None:
                                return None
                        else:
                            readiness_deferrer = getattr(
                                self._ordinary_replies,
                                "defer_if_global_delivery_prohibited", None,
                            )
                            if callable(readiness_deferrer):
                                deferred = await asyncio.to_thread(
                                    readiness_deferrer, ordinary_operation,
                                )
                                if deferred is not None:
                                    self._logger.warning(
                                        "event=ordinary_reply_generation_deferred "
                                        "operation_id=%s reason=GLOBAL_AVA_BOT_ATTENTION "
                                        "provider_generation_count=0",
                                        ordinary_operation.operation_id,
                                    )
                                    return None
                            ordinary_operation = await asyncio.to_thread(
                                self._ordinary_replies.claim_generation, ordinary_operation,
                            )
                            if ordinary_operation is None:
                                return None
                            validator=getattr(self._ordinary_replies,
                                "validate_follow_through_before_generation",None)
                            if callable(validator) and not await asyncio.to_thread(
                                    validator,ordinary_operation):
                                return None
                            try:
                                policy_factory=getattr(self._ordinary_replies,
                                    "post_nudge_policy_result",None)
                                result=(policy_factory(ordinary_operation,payload)
                                    if callable(policy_factory) else None)
                                if result is None:
                                    generator = getattr(self._ordinary_replies, "generate", None)
                                    result = await asyncio.to_thread(
                                        generator, ordinary_operation, payload,
                                        initial=self._inbound_adapter.execute,
                                    ) if callable(generator) else await asyncio.to_thread(
                                        self._inbound_adapter.execute, payload,
                                    )
                            except Exception as error:
                                await asyncio.to_thread(
                                    self._ordinary_replies.generation_failed,
                                    ordinary_operation, error,
                                )
                                self._logger.error(
                                    "event=ordinary_reply_generation_failed_no_send "
                                    "operation_id=%s error_type=%s",
                                    ordinary_operation.operation_id,
                                    type(error).__name__,
                                )
                                return None
                            pacing = self._response_pacing.calculate(
                                inbound_text=payload.message_text,
                                reply_text=result.response_text,
                                commercial=bool(result.delivery_requires_payment),
                                acknowledgement=bool(result.diagnostic_metadata.get(
                                    "purchase_acknowledgement_intent_id")),
                                shadow=False,
                                telegram_user_id=payload.telegram_user_id,
                            )
                            result.diagnostic_metadata["response_pacing"] = pacing.diagnostics()
                            ordinary_operation = await asyncio.to_thread(
                                self._ordinary_replies.generated,
                                ordinary_operation, result,
                            )
                        if ordinary_operation is not None:
                            result.diagnostic_metadata[
                                "authoritativeForegroundInboundId"
                            ] = int(getattr(
                                ordinary_operation,
                                "inbound_telegram_message_id",
                                payload.message_id,
                            ))
                        if (ordinary_operation is not None and callable(ignored_reader)
                                and await asyncio.to_thread(
                                    ignored_reader, ordinary_operation)):
                            await asyncio.to_thread(
                                self._ordinary_replies.suppress_ignored,
                                ordinary_operation)
                            self._logger.info(
                                "event=ordinary_reply_generation_ignored operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id)
                            return result
                        awaiting_delivery = getattr(
                            self._ordinary_replies,
                            "awaiting_scheduled_delivery", None,
                        )
                        if (ordinary_operation is not None
                                and callable(awaiting_delivery)
                                and awaiting_delivery(
                                    ordinary_operation, now=self._heartbeat.now())):
                            self._logger.info(
                                "event=ordinary_reply_prepared operation_id=%s "
                                "delivery_at=%s provider_generation_count=1",
                                ordinary_operation.operation_id,
                                ordinary_operation.scheduled_delivery_at.isoformat(),
                            )
                            return result
                        if (ordinary_operation is not None
                                and ordinary_operation.state.value == "SUPPRESSED"):
                            self._logger.info(
                                "event=ordinary_reply_preparation_invalidated "
                                "operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id,
                            )
                            return result
                if result.error_code in {"RELATIONSHIP_HUMAN_OPERATOR_ACTIVE",
                                          "RELATIONSHIP_IGNORED"}:
                    if ordinary_operation is not None and self._ordinary_replies is not None:
                        suppressor = (self._ordinary_replies.suppress_ignored
                            if result.error_code == "RELATIONSHIP_IGNORED"
                            and hasattr(self._ordinary_replies,"suppress_ignored")
                            else self._ordinary_replies.suppress_relationship_control)
                        await asyncio.to_thread(suppressor, ordinary_operation)
                    self._logger.info("event=telegram_reply_held relationship_control=HUMAN_OPERATOR chat_id=%s",
                                      payload.telegram_chat_id)
                    return result
                operation_commercial_allowed = bool(
                    ordinary_operation is None
                    or self._ordinary_replies is None
                    or not hasattr(self._ordinary_replies, "purchase_intent_allowed")
                    or self._ordinary_replies.purchase_intent_allowed(ordinary_operation)
                )
                if self._engagement_teasers is not None and operation_commercial_allowed:
                    engagement = await self._engagement_teasers.handle_active_inbound(
                        result=result, payload=payload, transport=self._transport)
                    if engagement.get("status") in {"CONFIRMED", "TELEGRAM_ACCEPTED"}:
                        if self._ordinary_replies is not None:
                            await asyncio.to_thread(
                            self._ordinary_replies.suppress_commercial,
                            ordinary_operation,
                            )
                        self._logger.info("event=free_engagement_teaser_sent strategy=%s",
                            getattr(engagement.get("decision"), "strategy", None))
                        return result
                if result.response_text:
                    intent = None
                    operation = (
                        await asyncio.to_thread(
                            self._sales_deliveries.get, result.correlation_id,
                        ) if self._sales_deliveries is not None else None
                    )
                    if operation is not None:
                        state = operation.state.value
                        if state in {"TELEGRAM_ACCEPTED", "CONFIRMED"}:
                            await asyncio.to_thread(
                                self._sales_deliveries.confirm, operation,
                            )
                            return result
                        if state in {"CONFIRMED", "FAILED", "AMBIGUOUS", "SENDING"}:
                            self._logger.info(
                                "event=telegram_sales_delivery_replay_suppressed "
                                "correlation_id=%s state=%s",
                                result.correlation_id, state,
                            )
                            return result
                        intent = await asyncio.to_thread(
                            self._purchase_intents.get, operation.purchase_intent_id,
                        )
                    elif self._purchase_intents is not None and operation_commercial_allowed:
                        intent = await asyncio.to_thread(
                            self._purchase_intents.create_before_delivery,
                            result, payload,
                        )
                        if intent is not None and self._sales_deliveries is not None:
                            operation, _ = await asyncio.to_thread(
                                self._sales_deliveries.prepare,
                                intent=intent, result=result, payload=payload,
                            )
                    if (
                        intent is not None
                        and operation is None
                        and ordinary_operation is not None
                        and self._ordinary_replies is not None
                    ):
                        ordinary_operation = await asyncio.to_thread(
                            self._ordinary_replies.enrich_commercial,
                            ordinary_operation, result, intent,
                        )
                    if operation is not None and self._ordinary_replies is not None:
                        await asyncio.to_thread(
                            self._ordinary_replies.suppress_commercial,
                            ordinary_operation,
                        )
                    # Establish final ordinary-delivery authority before any
                    # customer-visible typing or pacing.  A deterministic
                    # rejection must remain entirely outside the transport UX.
                    if operation is None and ordinary_operation is not None:
                        suppress_if_stale = getattr(
                            self._ordinary_replies, "suppress_if_stale", None,
                        )
                        stale = (
                            await asyncio.to_thread(suppress_if_stale, ordinary_operation)
                            if callable(suppress_if_stale) else None
                        )
                        if stale is not None:
                            self._logger.info(
                                "event=ordinary_reply_stale_blocked operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id,
                            )
                            return result
                        if (callable(ignored_reader) and await asyncio.to_thread(
                                ignored_reader, ordinary_operation)):
                            await asyncio.to_thread(
                                self._ordinary_replies.suppress_ignored,
                                ordinary_operation)
                            self._logger.info(
                                "event=ordinary_reply_send_ignored operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id)
                            return result
                        state = ordinary_operation.state.value
                        if state == "SENT_CONFIRMED":
                            finalize_confirmed = getattr(
                                self._ordinary_replies, "finalize_confirmed", None)
                            if callable(finalize_confirmed):
                                await asyncio.to_thread(
                                    finalize_confirmed, ordinary_operation)
                            self._record_confirmed_ordinary_transcript(
                                ordinary_operation, result,
                            )
                            return result
                        if state in {"SEND_UNCERTAIN", "TERMINAL_FAILED", "SUPPRESSED", "SENDING"}:
                            self._logger.info(
                                "event=ordinary_reply_replay_suppressed correlation_id=%s state=%s",
                                ordinary_operation.correlation_id, state,
                            )
                            return result
                        settlement_guard = getattr(
                            self._ordinary_replies,
                            "suppress_settled_follow_through_before_send", None,
                        )
                        settled = (
                            await asyncio.to_thread(
                                settlement_guard, ordinary_operation)
                            if callable(settlement_guard) else None
                        )
                        if settled is not None:
                            self._logger.info(
                                "event=active_offer_nudge_settlement_blocked "
                                "operation_id=%s disposition=BLOCKED_BEFORE_DELIVERY",
                                ordinary_operation.operation_id,
                            )
                            return result
                        delivery_authorizer = getattr(
                            self._ordinary_replies,
                            "authorize_customer_visible_delivery", None,
                        )
                        if (callable(delivery_authorizer)
                                and not await asyncio.to_thread(
                                    delivery_authorizer, ordinary_operation)):
                            self._logger.error(
                                "event=ordinary_reply_payload_blocked_no_send "
                                "operation_id=%s reason=NOT_AFFIRMATIVELY_AUTHORIZED",
                                ordinary_operation.operation_id,
                            )
                            return result
                    # Apply human pacing before entering either durable send
                    # namespace.  A restart during this bounded wait therefore
                    # leaves the operation GENERATED and safely claimable; it
                    # never creates false provider ambiguity or a duplicate.
                    pacing_data = dict(result.diagnostic_metadata.get("response_pacing") or {})
                    if pacing_data:
                        from app.services.telegram_response_pacing_service import TelegramResponsePacingDecision
                        await self._wait_with_typing(
                            chat_id=payload.telegram_chat_id,
                            telegram_user_id=payload.telegram_user_id,
                            correlation_id=(
                                str(ordinary_operation.operation_id)
                                if ordinary_operation is not None
                                else self._safe_correlation_id(result.correlation_id)
                            ),
                            decision=TelegramResponsePacingDecision(
                            mode=str(pacing_data["mode"]), policy=str(pacing_data["policy"]),
                            calculated_delay_ms=int(pacing_data["calculatedDelayMs"]),
                            applied_delay_ms=int(pacing_data["appliedDelayMs"]),
                            reason=str(pacing_data["reason"]),
                            bypass_reason=pacing_data.get("bypassReason"),
                            controlled_identity=bool(pacing_data.get("controlledIdentity")),
                        ))
                    if operation is not None:
                        claimed_operation = await asyncio.to_thread(
                            self._sales_deliveries.claim, operation,
                        )
                        if claimed_operation is None:
                            return result
                    if operation is None and ordinary_operation is not None:
                        claimed_ordinary = await asyncio.to_thread(
                            self._ordinary_replies.claim_send, ordinary_operation,
                        )
                        if claimed_ordinary is None:
                            return result
                    delivery_payload = (
                        operation.delivery_payload
                        if operation is not None
                        and hasattr(operation, "delivery_payload")
                        else result.delivery_payload
                    )
                    def persist_transport_evidence(evidence):
                        if claimed_ordinary is not None:
                            return self._ordinary_replies.record_provider_evidence(claimed_ordinary, evidence)
                        if claimed_operation is not None:
                            return self._sales_deliveries.record_provider_evidence(claimed_operation, evidence)
                        raise ValueError("A durable operation is required for Telegram invocation.")

                    try:
                        execution = await self._delivery_executor.execute_async(
                            delivery_payload,
                            context={
                                "chat_id": payload.telegram_chat_id,
                                "telegram_user_id": payload.telegram_user_id,
                                "correlation_id": (
                                    claimed_ordinary.correlation_id
                                    if claimed_ordinary is not None
                                    else result.correlation_id
                                ),
                                "engine_user_id": result.engine_user_id,
                                "creator_profile_id": result.diagnostic_metadata.get("creator_profile_id"),
                                "fanvue_account_id": result.diagnostic_metadata.get("fanvue_account_id"),
                                "fanvue_user_id": result.diagnostic_metadata.get("fanvue_user_id"),
                                "relationship_control_version": result.diagnostic_metadata.get(
                                    "relationship_control_version", 0),
                                "fallback_message_text": (
                                    operation.response_text
                                    if operation is not None
                                    and hasattr(operation, "response_text")
                                    else result.response_text
                                ),
                                "raise_on_failure": True,
                                "record_transport_evidence": persist_transport_evidence,
                                "operation_id": str((claimed_ordinary or claimed_operation).operation_id) if (claimed_ordinary or claimed_operation) else None,
                                "transport": self._transport,
                            },
                        )
                    except Exception as error:
                        recoverable_commercial = self._recoverable_commercial_error(error)
                        definitive_rejection = isinstance(
                            error, TelegramOutboundSendError,
                        ) and error.definitive_not_delivered
                        terminal_rejection = bool(
                            definitive_rejection and error.non_retryable
                        )
                        failed_operation = None
                        failed_ordinary = None
                        if claimed_operation is not None:
                            failed_operation = await asyncio.to_thread(
                                self._sales_deliveries.failed,
                                claimed_operation, error,
                            )
                        if claimed_ordinary is not None:
                            failed_ordinary = await asyncio.to_thread(
                                self._ordinary_replies.failed,
                                claimed_ordinary, error,
                                definitive=definitive_rejection,
                                terminal=terminal_rejection,
                                recoverable=recoverable_commercial,
                            )
                        if self._purchase_intents is not None:
                            commercial_state = getattr(
                                getattr(failed_operation, "state", None),
                                "value", None,
                            )
                            ordinary_state = getattr(
                                getattr(failed_ordinary, "state", None),
                                "value", None,
                            )
                            if not recoverable_commercial and (
                                commercial_state == "FAILED"
                                or ordinary_state in {
                                    "RETRYABLE", "TERMINAL_FAILED",
                                }
                                or (
                                    failed_operation is None
                                    and failed_ordinary is None
                                )
                            ):
                                await asyncio.to_thread(
                                    self._fail_or_abandon_delivery,
                                    intent, delivery_payload,
                                )
                        raise
                    commercial_presentation = bool(
                        intent is not None and result.delivery_requires_payment
                    )
                    provider_evidence = self._provider_delivery_evidence(
                        execution.metadata
                    )
                    # Persist what the provider returned before interpreting it.
                    # If verification remains incomplete, SEND_UNCERTAIN retains
                    # the exact message correlation instead of discarding it.
                    if claimed_operation is not None:
                        recorder = getattr(
                            self._sales_deliveries,
                            "record_provider_evidence", None,
                        )
                        if callable(recorder):
                            claimed_operation = await asyncio.to_thread(
                                recorder, claimed_operation, provider_evidence,
                            ) or claimed_operation
                    if claimed_ordinary is not None:
                        recorder = getattr(
                            self._ordinary_replies,
                            "record_provider_evidence", None,
                        )
                        if callable(recorder):
                            claimed_ordinary = await asyncio.to_thread(
                                recorder, claimed_ordinary, provider_evidence,
                            ) or claimed_ordinary
                    commercial_complete, commercial_failure_reason = (
                        self._commercial_presentation_verification(
                            result.diagnostic_metadata, execution.metadata,
                        )
                    )
                    result.diagnostic_metadata.update({
                        "actionable_destination_attached": execution.metadata.get(
                            "actionable_destination_attached", False
                        ),
                        "provider_markup_verified": execution.metadata.get(
                            "provider_markup_verified", False
                        ),
                        "provider_markup_included": execution.metadata.get(
                            "provider_markup_included", False
                        ),
                        "provider_action_verified": execution.metadata.get(
                            "provider_action_verified", False
                        ),
                        "customer_facing_destination_valid": execution.metadata.get(
                            "customer_facing_destination_valid", False
                        ),
                        "customer_facing_destination_failure_reason": execution.metadata.get(
                            "customer_facing_destination_failure_reason"
                        ),
                        "customer_facing_destination_origin": execution.metadata.get(
                            "customer_facing_destination_origin"
                        ),
                        "destination_scope": execution.metadata.get("destination_scope"),
                        "commercial_attachment_mode": execution.metadata.get(
                            "attachment_mode"
                        ),
                        "commercial_presentation_complete": (
                            commercial_complete if commercial_presentation else None
                        ),
                        "commercial_presentation_failure_reason": (
                            None if not commercial_presentation or commercial_complete
                            else commercial_failure_reason
                        ),
                    })
                    if execution.executed and commercial_presentation and not commercial_complete:
                        verification_error = ConnectionError(
                            "Commercial presentation was not verified complete provider-side"
                        )
                        if claimed_operation is not None:
                            await asyncio.to_thread(
                                self._sales_deliveries.failed,
                                claimed_operation,
                                verification_error,
                            )
                        if claimed_ordinary is not None:
                            await asyncio.to_thread(
                                self._ordinary_replies.failed,
                                claimed_ordinary,
                                verification_error,
                            )
                        self._logger.error(
                            "event=commercial_presentation_unverified correlation_id=%s "
                            "telegram_message_id=%s",
                            result.correlation_id,
                            execution.metadata.get("telegram_message_id"),
                        )
                        return result
                    if execution.executed:
                        if claimed_operation is not None:
                            telegram_message_id = execution.metadata.get(
                                "telegram_message_id"
                            )
                            if telegram_message_id is None:
                                await asyncio.to_thread(
                                    self._sales_deliveries.failed,
                                    claimed_operation,
                                    ConnectionError(
                                        "Telegram acceptance lacked a provider message ID"
                                    ),
                                )
                                return result
                            accepted_operation = await asyncio.to_thread(
                                self._sales_deliveries.accepted,
                                claimed_operation,
                                telegram_message_id,
                            )
                            await asyncio.to_thread(
                                self._sales_deliveries.confirm, accepted_operation,
                            )
                        elif claimed_ordinary is not None:
                            telegram_message_id = execution.metadata.get(
                                "telegram_message_id"
                            )
                            confirmed_ordinary = await asyncio.to_thread(
                                self._ordinary_replies.confirmed,
                                claimed_ordinary, telegram_message_id,
                            )
                            if confirmed_ordinary.state.value == "SENT_CONFIRMED":
                                self._record_confirmed_ordinary_transcript(
                                    confirmed_ordinary, result,
                                )
                                if (
                                    intent is not None
                                    and self._purchase_intents is not None
                                    and self._ordinary_send_presents_intent(result)
                                ):
                                    await asyncio.to_thread(
                                        self._purchase_intents.confirm_delivery,
                                        intent,
                                        telegram_message_id=telegram_message_id,
                                    )
                        elif self._purchase_intents is not None:
                            await asyncio.to_thread(
                                self._purchase_intents.confirm_delivery, intent,
                                telegram_message_id=execution.metadata.get(
                                    "telegram_message_id"
                                ),
                            )
                        acknowledgement_id = result.diagnostic_metadata.get(
                            "purchase_acknowledgement_intent_id"
                        )
                        if (
                            self._purchase_intents is not None
                            and acknowledgement_id
                            and result.diagnostic_metadata.get(
                                "customer_sales_decision"
                            ) == "CONGRATULATE_PURCHASE"
                        ):
                            await asyncio.to_thread(
                                self._purchase_intents.acknowledge_purchase,
                                acknowledgement_id,
                            )
                        if (claimed_operation is None and claimed_ordinary is None
                                and self._conversation_message_saver is not None):
                            await asyncio.to_thread(
                                self._record_outbound_transcript, result, execution,
                            )
                    elif not execution.executed:
                        if claimed_operation is not None:
                            await asyncio.to_thread(
                                self._sales_deliveries.failed,
                                claimed_operation,
                                RuntimeError(
                                    f"definitive_delivery_status:{execution.status}"
                                ),
                            )
                        if claimed_ordinary is not None:
                            deterministic_block = (
                                execution.status == "blocked"
                                and bool(execution.blocking_reason)
                            )
                            blocked_recorder = getattr(
                                self._ordinary_replies,
                                "deterministic_delivery_blocked", None,
                            )
                            if deterministic_block and callable(blocked_recorder):
                                await asyncio.to_thread(
                                    blocked_recorder, claimed_ordinary,
                                    reason=execution.blocking_reason,
                                    metadata=execution.metadata,
                                )
                            else:
                                await asyncio.to_thread(
                                    self._ordinary_replies.failed, claimed_ordinary,
                                    RuntimeError(
                                        f"definitive_delivery_status:{execution.status}"
                                    ),
                                    definitive=True,
                                )
                        if self._purchase_intents is not None:
                            await asyncio.to_thread(
                                self._fail_or_abandon_delivery,
                                intent, delivery_payload,
                            )
                    if not execution.executed:
                        self._logger.warning(
                            "Telegram response not sent: "
                            "delivery execution status=%s.",
                            execution.status,
                        )
                    teaser_metadata = dict(
                        (delivery_payload.get("metadata") or {}).get(
                            "free_teaser_delivery"
                        ) or {}
                    )
                    bundle_teaser_metadata = dict(
                        (delivery_payload.get("metadata") or {}).get(
                            "bundle_teaser_delivery"
                        ) or {}
                    )
                    if execution.executed and teaser_metadata:
                        provisional_confirmation = await asyncio.to_thread(
                            self._record_free_teaser_delivery,
                            delivery_payload,
                            execution,
                        )
                        result.diagnostic_metadata.update({
                            "commercial_tease_delivery_pending_confirmation": False,
                            "commercial_tease_delivered": True,
                            "commercial_tease_exposure_recorded": True,
                            "progression_finalized_after_delivery": True,
                        })
                        commercial_projection = dict(dict(
                            result.diagnostic_metadata.get("commercial_summary") or {}
                        ).get("sexualCommercialProgression") or {})
                        commercial_projection.update({
                            "commercialTeaseAuthorized": True,
                            "commercialTeaseDelivered": True,
                            "commercialTeaseExposureRecorded": True,
                            "progressionFinalizedAfterDelivery": True,
                            "adaptiveSwitchEligible": True,
                            "adaptiveSwitchReason": (
                                "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE"
                            ),
                        })
                        result.diagnostic_metadata.setdefault(
                            "commercial_summary", {}
                        )["sexualCommercialProgression"] = commercial_projection
                        if provisional_confirmation is not None and claimed_ordinary is not None:
                            from app.services.sales_brain_full_analysis_service import (
                                SalesBrainFullAnalysisService,
                            )
                            result.diagnostic_metadata["commercial_summary"] = (
                                SalesBrainFullAnalysisService.reconcile_confirmed_session_free_teaser(
                                    result.diagnostic_metadata.get("commercial_summary"),
                                    delivery_payload=delivery_payload,
                                    delivery_operation_id=str(claimed_ordinary.operation_id),
                                    delivery_state="CONFIRMED",
                                    customer_binding_confirmed=bool(
                                        claimed_ordinary.outbound_telegram_message_id
                                        == execution.metadata.get("telegram_message_id")
                                    ),
                                    provisional_session=provisional_confirmation,
                                )
                            )
                    if execution.executed and bundle_teaser_metadata:
                        await asyncio.to_thread(
                            self._record_bundle_teaser_delivery,
                            delivery_payload,
                            execution,
                        )
                return result
            except Exception as error:
                if (
                    ordinary_operation is not None
                    and claimed_operation is None
                    and claimed_ordinary is None
                    and self._ordinary_replies is not None
                ):
                    await asyncio.to_thread(
                        self._ordinary_replies.commercial_bootstrap_failed,
                        ordinary_operation, error,
                    )
                self._logger.error(
                    "[TELETHON ERROR] operation=gateway chat_id=%s "
                    "message_id=%s error_type=%s error=%s",
                    payload.telegram_chat_id,
                    payload.message_id,
                    type(error).__name__,
                    str(error)[:500],
                )
                # Live inbound handling remains isolated as before. Scheduler
                # replays must propagate to their per-operation supervisor so
                # heartbeat health and bounded cooldown reflect the failure.
                if availability_released:
                    raise
                return None

    def _fail_or_abandon_delivery(self, intent, delivery_payload) -> None:
        metadata = dict((delivery_payload or {}).get("metadata") or {})
        if metadata.get("bundle_complete_presentation") is True:
            handler = getattr(self._purchase_intents, "fail_delivery", None)
            if callable(handler):
                handler(intent)
                return
        self._purchase_intents.abandon_delivery(intent)

    @staticmethod
    def _provider_delivery_evidence(metadata):
        keys = (
            "attachment_mode", "actionable_destination_attached",
            "provider_action_verified", "provider_markup_included",
            "provider_markup_verified", "provider_media_included",
            "customer_facing_destination_valid",
            "destination_scope", "business_connection_id",
            "sender_business_bot", "provider_sender", "telegram_message_id",
        )
        return {key: metadata.get(key) for key in keys if key in metadata}

    @staticmethod
    def _commercial_presentation_verification(diagnostics, metadata):
        """Verify a paid presentation according to its provider attachment mode.

        Paid presentations require verified Telegram Business inline markup and
        media. Telethon user-session visible-URL degradation is prohibited.
        """
        if diagnostics.get("paid_presentation_validated") is not True:
            return False, "STRUCTURED_PRESENTATION_NOT_VALIDATED"
        if metadata.get("customer_facing_destination_valid") is not True:
            return False, "DESTINATION_INVALID"
        if metadata.get("telegram_message_id") is None:
            return False, "TELEGRAM_MESSAGE_ID_NOT_CAPTURED"
        if metadata.get("actionable_destination_attached") is not True:
            return False, "PROVIDER_ACTION_MISSING"
        if metadata.get("provider_action_verified") is not True:
            return False, "PROVIDER_ACTION_NOT_VERIFIED"
        mode = str(metadata.get("attachment_mode") or "")
        if mode in {"TELEGRAM_BUSINESS_INLINE_BUTTON",
                    "TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON"}:
            if metadata.get("provider_markup_included") is not True:
                return False, "MARKUP_MISSING"
            if metadata.get("provider_markup_verified") is not True:
                return False, "MARKUP_MISMATCH"
            if mode == "TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON" and metadata.get(
                    "provider_media_included") is not True:
                return False, "MEDIA_MISSING"
            return True, None
        return False, "ATTACHMENT_MODE_UNVERIFIED"

    @staticmethod
    def _ordinary_send_presents_intent(result) -> bool:
        """Only paid ordinary-namespace bootstrap sends present an intent.

        A conversational active-offer nudge can carry an existing intent for
        settlement protection without representing a new paid presentation.
        """
        return bool(getattr(result, "delivery_requires_payment", False))

    @staticmethod
    def _recoverable_commercial_error(error) -> bool:
        code = str(getattr(error, "code", "") or "")
        text = str(error)
        return code in {
            "BUSINESS_CONNECTION_UNAVAILABLE", "BUSINESS_CONNECTION_DISABLED",
            "BUSINESS_REPLY_NOT_ALLOWED", "BUSINESS_PEER_USAGE_MISSING",
            "BUSINESS_INLINE_BUTTON_REQUIRED",
            "PRIVATE_PPV_MEDIA_REQUIRED",
        } or any(marker in text for marker in (
            "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE",
            "INVALID_CUSTOMER_FACING_DESTINATION",
        ))

    def _record_outbound_transcript(self, result, execution) -> None:
        if self._conversation_message_saver is None:
            return
        metadata = dict(result.diagnostic_metadata or {})
        thread_id = metadata.get("conversation_thread_id")
        fanvue_account_id = metadata.get("conversation_fanvue_account_id")
        fanvue_user_id = metadata.get("conversation_fanvue_user_id")
        telegram_message_id = execution.metadata.get("telegram_message_id")
        if not all(value is not None for value in (
            thread_id, fanvue_account_id, fanvue_user_id, telegram_message_id,
        )):
            self._logger.warning(
                "event=telegram_outbound_transcript_skipped reason=canonical_metadata_missing"
            )
            return
        message_uuid = uuid5(
            NAMESPACE_URL,
            f"telegram:{result.telegram_chat_id}:outbound:{telegram_message_id}",
        )
        delivery_payload = dict(result.delivery_payload or {})
        delivery_metadata = dict(delivery_payload.get("metadata") or {})
        free_teaser = dict(delivery_metadata.get("free_teaser_delivery") or {})
        bundle_teaser = dict(delivery_metadata.get("bundle_teaser_delivery") or {})
        lifecycle = dict(metadata.get("offer_lifecycle") or {})
        self._conversation_message_saver(
            fanvue_account_id=int(fanvue_account_id), thread_id=int(thread_id),
            fanvue_user_id=int(fanvue_user_id), direction="outbound",
            sender_type="bot", text=result.response_text,
            fanvue_message_uuid=message_uuid,
            raw_payload={
                "provider": "TELEGRAM", "channel": "PRIVATE_CHAT",
                "telegram_chat_id": result.telegram_chat_id,
                "telegram_message_id": int(telegram_message_id),
                "correlation_id": result.correlation_id,
                "delivery_kind": (
                    "SESSION_FREE_TEASER" if free_teaser
                    else "BUNDLE_PROMOTIONAL_TEASER" if bundle_teaser
                    else delivery_payload.get("delivery_reason")
                ),
                "session_id": (
                    free_teaser.get("photoshoot_session_id")
                    or bundle_teaser.get("photoshoot_session_id")
                ),
                "session_role": free_teaser.get("sales_role"),
                "asset_id": free_teaser.get("asset_id") or bundle_teaser.get("asset_id"),
                "free": bool(free_teaser or bundle_teaser),
                "message_purpose": lifecycle.get("messagePurpose"),
                "purchase_kind": lifecycle.get("purchaseKind"),
                "purchase_intent_id": lifecycle.get("purchaseIntentId"),
                "commercial_offering_id": lifecycle.get("offeringId"),
                "commercial_publication_id": lifecycle.get("publicationId"),
                "session_step": lifecycle.get("sessionStep"),
                "session_role": lifecycle.get("sessionRole"),
            },
        )

    def _record_confirmed_ordinary_transcript(self, operation, result) -> None:
        if operation.outbound_telegram_message_id is None:
            return
        self._record_outbound_transcript(
            result,
            SimpleNamespace(metadata={
                "telegram_message_id": operation.outbound_telegram_message_id,
            }),
        )

    def _record_free_teaser_delivery(self, delivery_payload, execution) -> None:
        metadata = dict((delivery_payload or {}).get("metadata") or {})
        teaser = dict(metadata.get("free_teaser_delivery") or {})
        if not teaser or execution.metadata.get("execution_state") != "asset_sent":
            return
        provider_delivery_id = execution.metadata.get("telegram_message_id")
        if provider_delivery_id is None:
            self._logger.warning(
                "event=free_teaser_delivery_unrecorded reason=provider_identifier_missing "
                "asset_id=%s", teaser.get("asset_id"),
            )
            return
        confirmation = {
            "asset_id": int(teaser["asset_id"]),
            "provider": "TELEGRAM",
            "provider_delivery_id": str(provider_delivery_id),
            "metadata": {
                "photoshoot_session_id": teaser.get("photoshoot_session_id"),
                "sales_role": teaser.get("sales_role"),
                "delivery_method": execution.delivery_method,
            },
        }
        if teaser.get("provisional_session_id"):
            from app.services.telegram_provisional_sales_session_service import (
                TelegramProvisionalSalesSessionService,
            )
            return TelegramProvisionalSalesSessionService().record_free_teaser_delivery(
                provisional_session_id=teaser["provisional_session_id"],
                **confirmation,
            )
        return self._photoshoot_lifecycles.record_free_teaser_delivery(
            lifecycle_id=teaser["lifecycle_id"], **confirmation,
        )

    def _record_bundle_teaser_delivery(self, delivery_payload, execution) -> None:
        metadata = dict((delivery_payload or {}).get("metadata") or {})
        teaser = dict(metadata.get("bundle_teaser_delivery") or {})
        provider_delivery_id = execution.metadata.get("telegram_message_id")
        if (
            not teaser
            or execution.metadata.get("execution_state") != "asset_sent"
            or provider_delivery_id is None
        ):
            return
        self._photoshoot_lifecycles.record_bundle_teaser_delivery(
            lifecycle_id=teaser["lifecycle_id"],
            asset_id=int(teaser["asset_id"]), provider="TELEGRAM",
            provider_delivery_id=str(provider_delivery_id),
            metadata={
                "photoshoot_session_id": teaser.get("photoshoot_session_id"),
                "source_asset_id": teaser.get("source_asset_id"),
                "sales_role": "BUNDLE_PROMOTIONAL_TEASER",
                "delivery_method": execution.delivery_method,
            },
        )


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
    from app.services.telegram_identity_service import TelegramIdentityService
    from app.services.telegram_identity_verification_service import TelegramIdentityVerificationService
    from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
    from app.services.conversational_memory_service import ConversationalMemoryService
    from app.services.unmapped_telegram_prospect_service import (
        UnmappedTelegramProspectService,
    )
    from app.services.customer_abuse_policy_service import CustomerAbusePolicyService
    from app.services.customer_media_multimodal_decision_engine import CustomerMediaMultimodalDecisionEngine
    from app.services.timing_engine import TimingEngine
    from app.services.user_value_service import UserValueService
    from app.services.ava_runtime_scope_service import AvaRuntimeScopeService

    api_id = _required_positive_int("TG_API_ID")
    api_hash = _required_text("TG_API_HASH")
    engine_account_id = _required_positive_int("AVA_FANVUE_ACCOUNT_ID")
    session_path = os.getenv("TG_SESSION_PATH", "tg_sessions/ava").strip()
    if not session_path:
        raise TelethonRuntimeError("TG_SESSION_PATH must not be empty.")
    Path(session_path).expanduser().parent.mkdir(parents=True, exist_ok=True)

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
    gpt_service = GPTService(settings.OPENAI_API_KEY)
    decision_engine = DecisionEngine(
        memory_service=memory_service,
        intent_service=IntentService(),
        user_value_service=UserValueService(),
        mode_engine=ModeEngine(),
        offer_service=OfferService(),
        content_service=ContentService(),
        post_offer_service=PostOfferService(),
        timing_engine=TimingEngine(),
        gpt_service=gpt_service,
        settings=settings,
        logger=logging.getLogger("telegram-decision-engine"),
    )
    global_safety = GlobalAutomationSafetyService()
    from app.services.global_selling_permissions_service import (
        GlobalSellingPermissionsService,
    )
    global_selling_permissions = GlobalSellingPermissionsService()
    from app.services.customer_effective_permissions_service import (
        CustomerEffectivePermissionsService,
    )
    customer_effective_permissions = CustomerEffectivePermissionsService(
        global_selling_permissions=global_selling_permissions)
    telegram_prospects = UnmappedTelegramProspectService()
    creator_profile_id, resolved_account_id = AvaRuntimeScopeService.resolve(
        requested_account_id=engine_account_id)
    if resolved_account_id != engine_account_id:
        raise TelethonRuntimeError("Configured Ava runtime scope is inconsistent.")
    visual_turn_service = __import__(
        "app.services.telegram_visual_turn_service", fromlist=["TelegramVisualTurnService"]
    ).TelegramVisualTurnService()
    turn_reservation_service = __import__(
        "app.services.telegram_turn_reservation_service", fromlist=["TelegramTurnReservationService"]
    ).TelegramTurnReservationService()
    gateway = ConversationGateway(
        MemoryInitializingDecisionEngine(decision_engine),
        allowed_fanvue_hostnames=allowed_hosts,
        chat_commerce_service=ChatCommerceService(
            commerce_mode=ChatCommerceService.AUTHORITATIVE_MODE
        ),
        customer_sales_brain_service=CustomerSalesBrainService(
            unmapped_telegram_prospect_service=telegram_prospects,
            global_selling_permissions_service=global_selling_permissions,
            customer_effective_permissions_service=customer_effective_permissions,
        ),
        creator_profile_id=creator_profile_id or None,
        runtime_control_service=RuntimeControlService(),
        global_automation_safety_service=global_safety,
        global_selling_permissions_service=global_selling_permissions,
        customer_effective_permissions_service=customer_effective_permissions,
        commercial_presentation_copy_generator=lambda **kwargs: (
            gpt_service.generate_paid_presentation_copy(
                **kwargs,
                fanvue_account_id=engine_account_id,
            )
        ),
        purchase_acknowledgement_copy_generator=lambda **kwargs: (
            gpt_service.generate_purchase_acknowledgement_copy(
                **kwargs,
                fanvue_account_id=engine_account_id,
            )
        ),
        ava_persona_runtime_service=gpt_service.persona_runtime_service,
        visual_decision_engine=CustomerMediaMultimodalDecisionEngine(
            visual_turn_service=visual_turn_service),
    )
    purchase_intents = (
        TelegramPurchaseIntentService(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=engine_account_id,
            deferred_continuation_service=telegram_prospects,
        ) if creator_profile_id else None
    )
    from app.repositories.free_engagement_teaser_repository import FreeEngagementTeaserRepository
    from app.repositories.engagement_teaser_policy_repository import EngagementTeaserPolicyRepository
    from app.services.free_engagement_teaser_service import FreeEngagementTeaserService
    from app.services.engagement_teaser_policy_service import EngagementTeaserPolicyService
    from app.services.free_engagement_teaser_caption_service import FreeEngagementTeaserCaptionService
    from app.services.autonomous_engagement_teaser_service import AutonomousEngagementTeaserService
    from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
    from app.services.buyer_memory_priority_service import BuyerMemoryPriorityService
    from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
    relationship_controls = TelegramRelationshipControlService()
    engagement_repository = FreeEngagementTeaserRepository()
    engagement_policy_repository = EngagementTeaserPolicyRepository()
    engagement_teasers = AutonomousEngagementTeaserService(
        policy_service=EngagementTeaserPolicyService(repository=engagement_policy_repository),
        delivery_service=FreeEngagementTeaserService(repository=engagement_repository),
        caption_service=FreeEngagementTeaserCaptionService(gpt_service=gpt_service),
        policy_repository=engagement_policy_repository,
    )
    ordinary_replies = OrdinaryChatReplyService(
        creator_profile_id=creator_profile_id or None,
        fanvue_account_id=engine_account_id,
        effective_permissions=customer_effective_permissions,
    )
    from app.repositories.telegram_operator_message_repository import TelegramOperatorMessageRepository
    from app.services.unmapped_telegram_history_service import UnmappedTelegramHistoryService
    operator_messages = TelegramOperatorMessageRepository()
    unmapped_history = UnmappedTelegramHistoryService(
        ordinary_source=ordinary_replies,
        manual_source=operator_messages,
        final_limit=10,
    )
    recent_telegram_history = unmapped_history.recent_history
    buyer_memory_priority = BuyerMemoryPriorityService()
    private_inbound_backlog = __import__(
        "app.services.telegram_private_inbound_backlog_service",
        fromlist=["TelegramPrivateInboundBacklogService"],
    ).TelegramPrivateInboundBacklogService()
    inbound_adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(
            engine_account_id=engine_account_id,
        ),
        conversation_gateway=gateway,
        creator_profile_id=creator_profile_id or None,
        fanvue_account_id=engine_account_id,
        purchase_intent_service=purchase_intents,
        telegram_identity_service=TelegramIdentityService(
            repository=(purchase_intents.identities if purchase_intents is not None else None)
        ),
        identity_verification_service=TelegramIdentityVerificationService(),
        conversation_thread_resolver=get_or_create_chat_thread,
        conversation_message_saver=save_chat_message,
        conversation_history_loader=get_recent_messages_for_gpt,
        unmapped_conversation_history_loader=recent_telegram_history,
        engagement_outcome_tracker=engagement_repository,
        conversational_memory_service=ConversationalMemoryService(),
        buyer_memory_priority_resolver=buyer_memory_priority.resolve,
        customer_behavior_evidence_repository=ordinary_replies.repository,
        unmapped_telegram_prospect_service=telegram_prospects,
        abuse_policy_service=CustomerAbusePolicyService(
            prospect_service=telegram_prospects,
        ),
        relationship_control_service=relationship_controls,
        private_inbound_backlog_service=private_inbound_backlog,
    )
    client = TelegramClient(session_path, api_id, api_hash)
    transport = TelethonUserTransport(client=client)
    from app.services.telegram_business_commercial_transport import (
        TelegramBusinessCommercialTransport,
    )
    business_transport = TelegramBusinessCommercialTransport()
    delivery_executor = TelegramDeliveryExecutor(
        global_safety_service=global_safety,
        business_commercial_transport=business_transport,
        relationship_control_service=relationship_controls,
        customer_effective_permissions_service=customer_effective_permissions,
    )
    business_connection_worker = None
    if os.getenv(
        "TELEGRAM_BUSINESS_CONNECTION_LIFECYCLE_ENABLED", "false"
    ).strip().lower() == "true":
        from app.services.telegram_business_connection_service import (
            TelegramBusinessConnectionService,
        )
        from app.services.telegram_business_connection_worker import (
            TelegramBusinessConnectionWorker,
        )
        from app.services.telegram_business_peer_observation_service import (
            TelegramBusinessPeerObservationService,
        )
        if not business_transport.bot_id:
            raise TelethonRuntimeError("TELEGRAM_BUSINESS_BOT_ID is required.")
        business_connection_worker = TelegramBusinessConnectionWorker(
            bot_token=settings.TELEGRAM_BOT_TOKEN_AVA,
            lifecycle_service=TelegramBusinessConnectionService(
                bot_telegram_user_id=business_transport.bot_id,
            ),
            peer_observation_service=TelegramBusinessPeerObservationService(),
            business_owner_user_id=business_transport.owner_user_id,
        )
    sales_deliveries = (
        TelegramSalesDeliveryService(
            purchase_intent_service=purchase_intents,
            conversation_message_saver=save_chat_message,
        ) if purchase_intents is not None else None
    )
    from app.services.schema_manager_service import SchemaManagerService
    schema_manager = SchemaManagerService()
    ordinary_reply_schema_preflight = lambda: schema_manager.assert_migration_ready(
        "20260916_139_ordinary_reply_preparation_window.sql",
        table_name="ordinary_chat_reply_operations",
        required_columns=("scheduled_delivery_at", "preparation_eligible_at"),
        required_indexes=("idx_ordinary_reply_preparation_due",),
    )
    return TelethonRuntime(
        transport=transport,
        inbound_adapter=inbound_adapter,
        delivery_executor=delivery_executor,
        heartbeat_service=WorkerHeartbeatService(
            worker_name="Telegram", worker_type="transport_runtime",
            creator_profile_id=creator_profile_id or None,
            account_id=engine_account_id, poll_interval_seconds=30,
        ),
        global_safety_service=global_safety,
        purchase_intent_service=purchase_intents,
        conversation_message_saver=save_chat_message,
        sales_delivery_service=sales_deliveries,
        engagement_teaser_service=engagement_teasers,
        ordinary_reply_service=ordinary_replies,
        availability_service=__import__(
            "app.services.ava_human_availability_service",
            fromlist=["AvaHumanAvailabilityService"],
        ).AvaHumanAvailabilityService(),
        private_inbound_backlog_service=private_inbound_backlog,
        ownership_service=TelegramWorkerOwnershipService(),
        business_connection_worker=business_connection_worker,
        ordinary_reply_schema_preflight=ordinary_reply_schema_preflight,
        operator_message_repository=operator_messages,
        manual_offer_dispatcher=__import__(
            'app.services.relationship_manual_offer_service',
            fromlist=['RelationshipManualOfferService']).RelationshipManualOfferService(runtime_transport=transport),
        transport_certification_service=__import__(
            "app.services.telegram_transport_certification_service",
            fromlist=["TelegramTransportCertificationService"],
        ).TelegramTransportCertificationService(),
        visual_turn_service=visual_turn_service,
        turn_reservation_service=turn_reservation_service,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    runtime = build_default_runtime_from_environment()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is not None:
            try:
                loop.add_signal_handler(sig, runtime.request_shutdown, name)
            except (NotImplementedError, RuntimeError):
                signal.signal(sig, lambda *_args, _name=name: runtime.request_shutdown(_name))
    try:
        loop.run_until_complete(runtime.run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()

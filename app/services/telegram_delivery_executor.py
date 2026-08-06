"""Runtime execution boundary for normalized Telegram delivery payloads.

TelegramDeliveryExecutor owns Telegram runtime execution only. It intentionally
does not decide what to send, why to send it, who should receive it, or whether
commerce delivery is allowed.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from app.models.commerce_execution import (
    RuntimeExecutionIntent,
    RuntimeExecutionPayload,
)
from app.models.telegram_commerce import TelegramDeliveryPayload


@dataclass(frozen=True)
class TelegramDeliveryExecutionResult:
    """Result of handing a normalized payload to the execution boundary."""

    status: str
    executed: bool
    delivery_method: str | None = None
    blocking_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "executed": self.executed,
            "delivery_method": self.delivery_method,
            "blocking_reason": self.blocking_reason,
            "metadata": dict(self.metadata),
        }


class TelegramDeliveryExecutor:
    """Execute normalized Telegram Delivery Payloads.

    Text and canonical local-Asset delivery are executable capabilities.
    Paid link/button behavior remains governed by the existing Commerce path.
    """

    def __init__(self, *, global_safety_service: Any | None = None) -> None:
        if global_safety_service is None:
            from app.services.global_automation_safety_service import GlobalAutomationSafetyService
            global_safety_service = GlobalAutomationSafetyService()
        self._global_safety_service = global_safety_service

    def execute(
        self,
        payload: TelegramDeliveryPayload | RuntimeExecutionIntent | Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> TelegramDeliveryExecutionResult:
        normalized = self._normalize_payload(payload)
        metadata = self._metadata(normalized, context)
        message_text = self._message_text(normalized, context)
        sender = self._sender(context)
        chat_id = self._chat_id(context)

        if normalized.asset_path and sender is not None and chat_id is not None:
            safety = self._global_safety_service.check_global_safety()
            if not safety.get("allowed", False):
                return self._safety_blocked_result(normalized, metadata, safety)
            return self._execute_asset(
                sender, chat_id=chat_id, asset_path=normalized.asset_path,
                message_text=message_text, payload=normalized, metadata=metadata,
                raise_on_failure=self._raise_on_failure(context),
            )
        if message_text and sender is not None and chat_id is not None:
            safety = self._global_safety_service.check_global_safety()
            if not safety.get("allowed", False):
                return self._safety_blocked_result(normalized, metadata, safety)
            return self._execute_text(
                sender,
                chat_id=chat_id,
                message_text=message_text,
                payload=normalized,
                metadata=metadata,
                raise_on_failure=self._raise_on_failure(context),
            )

        return self._deferred_result(normalized, metadata)

    async def execute_async(
        self,
        payload: TelegramDeliveryPayload | RuntimeExecutionIntent | Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> TelegramDeliveryExecutionResult:
        normalized = self._normalize_payload(payload)
        metadata = self._metadata(normalized, context)
        message_text = self._message_text(normalized, context)
        sender = self._sender(context)
        chat_id = self._chat_id(context)

        if normalized.asset_path and sender is not None and chat_id is not None:
            safety = self._global_safety_service.check_global_safety()
            if not safety.get("allowed", False):
                return self._safety_blocked_result(normalized, metadata, safety)
            return await self._execute_asset_async(
                sender, chat_id=chat_id, asset_path=normalized.asset_path,
                message_text=message_text, payload=normalized, metadata=metadata,
                raise_on_failure=self._raise_on_failure(context),
            )
        if message_text and sender is not None and chat_id is not None:
            safety = self._global_safety_service.check_global_safety()
            if not safety.get("allowed", False):
                return self._safety_blocked_result(normalized, metadata, safety)
            return await self._execute_text_async(
                sender,
                chat_id=chat_id,
                message_text=message_text,
                payload=normalized,
                metadata=metadata,
                raise_on_failure=self._raise_on_failure(context),
            )

        return self._deferred_result(normalized, metadata)

    def _execute_text(
        self,
        sender: Any,
        *,
        chat_id: int,
        message_text: str,
        payload: TelegramDeliveryPayload,
        metadata: dict[str, Any],
        raise_on_failure: bool,
    ) -> TelegramDeliveryExecutionResult:
        try:
            sent = sender.send_text(chat_id=chat_id, message_text=message_text)
        except Exception as error:
            if raise_on_failure:
                raise
            return self._failure_result(payload, metadata, error)

        metadata.update(
            {
                "execution_state": "text_sent",
                "text_length": len(message_text),
            }
        )
        message_id = getattr(sent, "id", sent)
        if isinstance(message_id, int) and not isinstance(message_id, bool):
            metadata["telegram_message_id"] = message_id
        return TelegramDeliveryExecutionResult(
            status="success",
            executed=True,
            delivery_method=payload.delivery_method,
            blocking_reason=payload.blocking_reason,
            metadata=metadata,
        )

    async def _execute_text_async(
        self,
        sender: Any,
        *,
        chat_id: int,
        message_text: str,
        payload: TelegramDeliveryPayload,
        metadata: dict[str, Any],
        raise_on_failure: bool,
    ) -> TelegramDeliveryExecutionResult:
        try:
            result = sender.send_text(chat_id=chat_id, message_text=message_text)
            if inspect.isawaitable(result):
                result = await result
        except Exception as error:
            if raise_on_failure:
                raise
            return self._failure_result(payload, metadata, error)

        metadata.update(
            {
                "execution_state": "text_sent",
                "text_length": len(message_text),
            }
        )
        message_id = getattr(result, "id", result)
        if isinstance(message_id, int) and not isinstance(message_id, bool):
            metadata["telegram_message_id"] = message_id
        return TelegramDeliveryExecutionResult(
            status="success",
            executed=True,
            delivery_method=payload.delivery_method,
            blocking_reason=payload.blocking_reason,
            metadata=metadata,
        )

    def _deferred_result(
        self,
        payload: TelegramDeliveryPayload,
        metadata: dict[str, Any],
    ) -> TelegramDeliveryExecutionResult:
        if payload.blocking_reason:
            metadata["execution_state"] = "blocked"
            return TelegramDeliveryExecutionResult(
                status="blocked",
                executed=False,
                delivery_method=payload.delivery_method,
                blocking_reason=payload.blocking_reason,
                metadata=metadata,
            )

        if not payload.delivery_method or payload.delivery_method == "none":
            metadata["execution_state"] = "no_delivery"
            return TelegramDeliveryExecutionResult(
                status="no_delivery",
                executed=False,
                delivery_method=payload.delivery_method,
                metadata=metadata,
            )

        metadata["execution_state"] = "deferred_until_transport_capability_exists"
        return TelegramDeliveryExecutionResult(
            status="deferred",
            executed=False,
            delivery_method=payload.delivery_method,
            metadata=metadata,
        )

    def _execute_asset(
        self, sender: Any, *, chat_id: int, asset_path: str,
        message_text: str, payload: TelegramDeliveryPayload,
        metadata: dict[str, Any], raise_on_failure: bool,
    ) -> TelegramDeliveryExecutionResult:
        method = getattr(sender, "send_asset", None)
        if not callable(method):
            return self._deferred_result(payload, metadata)
        try:
            sent = method(chat_id=chat_id, asset_path=asset_path, message_text=message_text)
        except Exception as error:
            if raise_on_failure:
                raise
            return self._failure_result(payload, metadata, error)
        return self._asset_success(payload, metadata, sent)

    async def _execute_asset_async(
        self, sender: Any, *, chat_id: int, asset_path: str,
        message_text: str, payload: TelegramDeliveryPayload,
        metadata: dict[str, Any], raise_on_failure: bool,
    ) -> TelegramDeliveryExecutionResult:
        method = getattr(sender, "send_asset", None)
        if not callable(method):
            return self._deferred_result(payload, metadata)
        try:
            sent = method(chat_id=chat_id, asset_path=asset_path, message_text=message_text)
            if inspect.isawaitable(sent):
                sent = await sent
        except Exception as error:
            if raise_on_failure:
                raise
            return self._failure_result(payload, metadata, error)
        return self._asset_success(payload, metadata, sent)

    @staticmethod
    def _asset_success(payload, metadata, sent):
        metadata.update({"execution_state": "asset_sent", "asset_path": payload.asset_path})
        message_id = getattr(sent, "id", sent)
        if isinstance(message_id, int) and not isinstance(message_id, bool):
            metadata["telegram_message_id"] = message_id
        return TelegramDeliveryExecutionResult(
            status="success", executed=True, delivery_method=payload.delivery_method,
            blocking_reason=payload.blocking_reason, metadata=metadata,
        )

    @staticmethod
    def _safety_blocked_result(
        payload: TelegramDeliveryPayload,
        metadata: dict[str, Any],
        safety: Mapping[str, Any],
    ) -> TelegramDeliveryExecutionResult:
        reason = str(safety.get("reason") or "global_automation_blocked")
        metadata.update({"execution_state": "blocked", "safety_source": safety.get("source")})
        return TelegramDeliveryExecutionResult(
            status="blocked", executed=False,
            delivery_method=payload.delivery_method,
            blocking_reason=reason, metadata=metadata,
        )

    @staticmethod
    def _failure_result(
        payload: TelegramDeliveryPayload,
        metadata: dict[str, Any],
        error: Exception,
    ) -> TelegramDeliveryExecutionResult:
        metadata.update(
            {
                "execution_state": "failed",
                "error_type": type(error).__name__,
            }
        )
        return TelegramDeliveryExecutionResult(
            status="failed",
            executed=False,
            delivery_method=payload.delivery_method,
            blocking_reason=payload.blocking_reason,
            metadata=metadata,
        )

    @staticmethod
    def _normalize_payload(
        payload: TelegramDeliveryPayload | RuntimeExecutionIntent | Mapping[str, Any],
    ) -> TelegramDeliveryPayload:
        if isinstance(payload, TelegramDeliveryPayload):
            return payload
        if isinstance(payload, RuntimeExecutionIntent):
            if isinstance(payload.payload, TelegramDeliveryPayload):
                return payload.payload
            if isinstance(payload.payload, RuntimeExecutionPayload):
                return TelegramDeliveryExecutor._payload_from_runtime_payload(
                    payload.payload,
                    payload,
                )
            if isinstance(payload.payload, Mapping):
                return TelegramDeliveryExecutor._normalize_payload(payload.payload)
            return TelegramDeliveryPayload(
                delivery_method="none",
                metadata={
                    "runtime_execution_intent": tuple(
                        action.value for action in payload.actions
                    ),
                    "runtime_intent_owner": "CommerceExecutionService",
                },
            )
        return TelegramDeliveryPayload(
            delivery_type=payload.get("delivery_type"),
            message_text=str(payload.get("message_text") or ""),
            asset_path=payload.get("asset_path"),
            media_link=payload.get("media_link"),
            product_reference=payload.get("product_reference"),
            experience_reference=payload.get("experience_reference"),
            delivery_reason=payload.get("delivery_reason"),
            blocking_reason=payload.get("blocking_reason"),
            next_suggested_action=payload.get("next_suggested_action"),
            delivery_method=payload.get("delivery_method"),
            metadata=dict(payload.get("metadata") or {}),
        )

    @staticmethod
    def _payload_from_runtime_payload(
        payload: RuntimeExecutionPayload,
        intent: RuntimeExecutionIntent,
    ) -> TelegramDeliveryPayload:
        metadata = dict(payload.metadata or {})
        metadata["runtime_execution_intent"] = tuple(
            action.value for action in intent.actions
        )
        metadata["runtime_intent_owner"] = "CommerceExecutionService"
        return TelegramDeliveryPayload(
            delivery_type=payload.delivery_type,
            message_text=payload.message_text,
            asset_path=payload.asset_path,
            media_link=payload.media_link,
            product_reference=payload.product_reference,
            experience_reference=payload.experience_reference,
            delivery_reason=payload.delivery_reason,
            blocking_reason=payload.blocking_reason,
            next_suggested_action=payload.next_suggested_action,
            delivery_method=payload.delivery_method,
            metadata=metadata,
        )

    @classmethod
    def _metadata(
        cls,
        payload: TelegramDeliveryPayload,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        metadata = {
            "execution_owner": "TelegramDeliveryExecutor",
            "transport_behavior": "preserved",
            "provider_metadata": dict(payload.metadata),
        }
        if context:
            metadata["context"] = cls._safe_context(context)
        unsupported = []
        if payload.media_link:
            unsupported.append("paid_media_link_send")
        if unsupported:
            metadata["unsupported_capabilities"] = tuple(unsupported)
        return metadata

    @staticmethod
    def _message_text(
        payload: TelegramDeliveryPayload,
        context: Mapping[str, Any] | None,
    ) -> str:
        text = payload.message_text
        if not text and context is not None:
            text = str(context.get("fallback_message_text") or "")
        return text

    @staticmethod
    def _sender(context: Mapping[str, Any] | None) -> Any | None:
        if context is None:
            return None
        return context.get("text_sender") or context.get("transport")

    @staticmethod
    def _chat_id(context: Mapping[str, Any] | None) -> int | None:
        if context is None:
            return None
        value = context.get("chat_id") or context.get("telegram_chat_id")
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _raise_on_failure(context: Mapping[str, Any] | None) -> bool:
        if context is None:
            return False
        return bool(context.get("raise_on_failure", False))

    @staticmethod
    def _safe_context(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            str(key): value
            for key, value in context.items()
            if key in {"correlation_id", "engine_user_id", "chat_id", "telegram_chat_id"}
        }

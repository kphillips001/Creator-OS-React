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


class TelegramCommercialDestinationError(ValueError):
    def __init__(self, provider_reason: str):
        super().__init__(provider_reason)
        self.code = (
            "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE"
            if provider_reason == "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE"
            else "INVALID_CUSTOMER_FACING_DESTINATION"
        )


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

    def __init__(self, *, global_safety_service: Any | None = None,
                 customer_safety_service: Any | None = None,
                 business_commercial_transport: Any | None = None) -> None:
        if global_safety_service is None:
            from app.services.global_automation_safety_service import GlobalAutomationSafetyService
            global_safety_service = GlobalAutomationSafetyService()
        self._global_safety_service = global_safety_service
        if customer_safety_service is None:
            from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
            customer_safety_service = CustomerInteractionSafetyService()
        self._customer_safety_service = customer_safety_service
        if business_commercial_transport is None:
            from app.services.telegram_business_commercial_transport import (
                TelegramBusinessCommercialTransport,
            )
            business_commercial_transport = TelegramBusinessCommercialTransport()
        self._business_commercial_transport = business_commercial_transport

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

        customer_block = self._customer_block(context)
        if customer_block is not None:
            return self._customer_blocked_result(normalized, metadata, customer_block)

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

        customer_block = self._customer_block(context)
        if customer_block is not None:
            return self._customer_blocked_result(normalized, metadata, customer_block)

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
            button = self._private_unlock_button(payload)
            self._validate_commercial_destination(metadata, button)
            if button:
                sender = self._business_commercial_transport
            sent = sender.send_text(
                chat_id=chat_id, message_text=message_text, **button,
            )
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
        self._apply_send_receipt(metadata, sent)
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
            button = self._private_unlock_button(payload)
            self._validate_commercial_destination(metadata, button)
            if button:
                sender = self._business_commercial_transport
            result = sender.send_text(
                chat_id=chat_id, message_text=message_text, **button,
            )
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
        self._apply_send_receipt(metadata, result)
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

    @staticmethod
    def _apply_send_receipt(metadata: dict[str, Any], receipt: Any) -> None:
        """Copy only provider-confirmed commercial attachment facts."""
        if getattr(receipt, "actionable_destination_attached", False) is True:
            metadata["actionable_destination_attached"] = True
        if getattr(receipt, "provider_action_verified", False) is True:
            metadata["provider_action_verified"] = True
        metadata["provider_markup_included"] = bool(
            getattr(receipt, "provider_markup_included", False)
        )
        if getattr(receipt, "provider_markup_verified", False) is True:
            metadata["provider_markup_verified"] = True
        attachment_mode = getattr(receipt, "attachment_mode", None)
        if attachment_mode:
            metadata["attachment_mode"] = str(attachment_mode)
        final_text = getattr(receipt, "final_text", None)
        if isinstance(final_text, str) and final_text.strip():
            metadata["final_customer_facing_text"] = final_text
        business_connection_id = getattr(receipt, "business_connection_id", None)
        if business_connection_id:
            metadata["business_connection_id"] = str(business_connection_id)
        sender_business_bot = getattr(receipt, "sender_business_bot", None)
        if isinstance(sender_business_bot, Mapping):
            metadata["sender_business_bot"] = dict(sender_business_bot)
        provider_sender = getattr(receipt, "sender", None)
        if isinstance(provider_sender, Mapping):
            metadata["provider_sender"] = dict(provider_sender)

    @staticmethod
    def _validate_commercial_destination(metadata, button):
        if not button:
            return
        from app.services.customer_facing_commerce_url_service import (
            validate_customer_facing_commerce_url,
        )
        result = validate_customer_facing_commerce_url(button.get("button_url"))
        metadata.update({
            "customer_facing_destination_valid": result.valid,
            "customer_facing_destination_failure_reason": result.failure_reason,
            "customer_facing_destination_origin": result.origin,
            "destination_scope": result.scope,
        })
        if not result.valid:
            raise TelegramCommercialDestinationError(
                result.failure_reason or "CUSTOMER_FACING_DESTINATION_INVALID"
            )

    @staticmethod
    def _private_unlock_button(payload):
        metadata = dict(payload.metadata or {})
        button = dict(metadata.get("private_chat_unlock_button") or {})
        label = str(button.get("label") or "").strip()
        url = str(button.get("url") or "").strip()
        if not label or not url:
            return {}
        return {"button_label": label, "button_url": url}

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
                "failure_code": str(
                    getattr(error, "code", "BUSINESS_SEND_REJECTED")
                ),
            }
        )
        return TelegramDeliveryExecutionResult(
            status="failed",
            executed=False,
            delivery_method=payload.delivery_method,
            blocking_reason=payload.blocking_reason,
            metadata=metadata,
        )

    def _customer_block(self, context):
        if not context:
            return None
        creator_id = context.get("creator_profile_id")
        account_id = context.get("fanvue_account_id")
        user_id = context.get("fanvue_user_id")
        if not all((creator_id, account_id, user_id)):
            return None
        decision = self._customer_safety_service.decide(
            creator_profile_id=int(creator_id), fanvue_account_id=int(account_id),
            fanvue_user_id=int(user_id))
        return decision if not decision.allowed else None

    @staticmethod
    def _customer_blocked_result(payload, metadata, decision):
        metadata.update({"execution_state": "blocked",
                         "customer_interaction_safety": decision.code})
        return TelegramDeliveryExecutionResult(
            status="blocked", executed=False, delivery_method=payload.delivery_method,
            blocking_reason=decision.code, metadata=metadata)

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
            if key in {"correlation_id", "engine_user_id", "chat_id", "telegram_chat_id",
                       "creator_profile_id", "fanvue_account_id", "fanvue_user_id"}
        }

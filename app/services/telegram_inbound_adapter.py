"""Offline normalization from Telegram-like input to the conversation gateway."""

from typing import Protocol

from app.models.conversation_gateway import (
    ConversationGatewayInput,
    ConversationGatewayOutput,
)
from app.models.telegram_identity import TelegramMvpIdentityInput
from app.models.telegram_inbound import (
    TelegramInboundPayload,
    TelegramInboundResult,
)
from app.services.telegram_identity_adapter import (
    POSTGRES_BIGINT_MAX,
    InvalidTelegramMvpIdentityError,
    TelegramIdentityAdapter,
)


class ConversationGatewayCompatible(Protocol):
    def execute(
        self,
        gateway_input: ConversationGatewayInput,
    ) -> ConversationGatewayOutput:
        ...


class InvalidTelegramInboundError(ValueError):
    """The inbound payload cannot safely enter the conversation gateway."""


class TelegramInboundAdapter:
    """Validate and execute one normalized inbound conversation request."""

    def __init__(
        self,
        *,
        identity_adapter: TelegramIdentityAdapter,
        conversation_gateway: ConversationGatewayCompatible,
    ) -> None:
        if identity_adapter is None:
            raise ValueError("identity_adapter is required")
        if conversation_gateway is None:
            raise ValueError("conversation_gateway is required")
        self._identity_adapter = identity_adapter
        self._conversation_gateway = conversation_gateway

    def execute(
        self,
        payload: TelegramInboundPayload,
    ) -> TelegramInboundResult:
        self._validate_payload(payload)

        try:
            identity = self._identity_adapter.adapt(
                TelegramMvpIdentityInput(
                    telegram_user_id=payload.telegram_user_id,
                    telegram_chat_id=payload.telegram_chat_id,
                )
            )
        except InvalidTelegramMvpIdentityError as error:
            raise InvalidTelegramInboundError(str(error)) from error

        correlation_id = (
            payload.correlation_id
            if payload.correlation_id is not None
            else self._generate_correlation_id(
                payload.telegram_chat_id,
                payload.message_id,
            )
        )

        gateway_output = self._conversation_gateway.execute(
            ConversationGatewayInput(
                engine_user_id=identity.engine_user_id,
                message_text=payload.message_text,
                chat_history=payload.chat_history,
                correlation_id=correlation_id,
            )
        )

        return TelegramInboundResult(
            correlation_id=gateway_output.correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=identity.engine_user_id,
            response_text=gateway_output.response_text,
            offer_authorized=gateway_output.offer_authorized,
            offer_link=gateway_output.offer_link,
            blocked=gateway_output.blocked,
            error_code=gateway_output.error_code,
            delivery_type=gateway_output.delivery_type,
            delivery_mode=gateway_output.delivery_mode,
            delivery_requires_payment=gateway_output.delivery_requires_payment,
            delivery_payload=dict(gateway_output.delivery_payload),
            diagnostic_metadata=dict(gateway_output.diagnostic_metadata),
        )

    @staticmethod
    def _validate_payload(payload: TelegramInboundPayload) -> None:
        if not isinstance(payload, TelegramInboundPayload):
            raise InvalidTelegramInboundError(
                "payload must be a TelegramInboundPayload."
            )
        if (
            not isinstance(payload.message_text, str)
            or not payload.message_text.strip()
        ):
            raise InvalidTelegramInboundError(
                "message_text must be a non-empty string."
            )
        if (
            isinstance(payload.message_id, bool)
            or not isinstance(payload.message_id, int)
            or payload.message_id <= 0
            or payload.message_id > POSTGRES_BIGINT_MAX
        ):
            raise InvalidTelegramInboundError(
                "message_id must be a positive signed 64-bit integer."
            )
        if not isinstance(payload.chat_history, list):
            raise InvalidTelegramInboundError(
                "chat_history must be a list."
            )
        if payload.correlation_id is not None and (
            not isinstance(payload.correlation_id, str)
            or not payload.correlation_id.strip()
        ):
            raise InvalidTelegramInboundError(
                "correlation_id must be a non-empty string when provided."
            )

    @staticmethod
    def _generate_correlation_id(
        telegram_chat_id: int,
        message_id: int,
    ) -> str:
        return f"telegram:{telegram_chat_id}:{message_id}"

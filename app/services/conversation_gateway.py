"""Channel-neutral facade around the existing DecisionEngine entry point."""

import logging
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.models.conversation_gateway import (
    ConversationGatewayInput,
    ConversationGatewayOutput,
)
from app.models.runtime_control import RuntimeMode


logger = logging.getLogger(__name__)


class DecisionEngineCompatible(Protocol):
    """The only brain behavior required by the gateway."""

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        ...


class TelegramCommerceCompatible(Protocol):
    """Commerce orchestration behavior optionally used by the gateway."""

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history: list[Any] | None = None,
    ) -> dict[str, Any] | None:
        ...


class ContentOpportunityIngestionCompatible(Protocol):
    """Read-only customer content request ingestion."""

    def ingest_message(
        self,
        *,
        customer_id: str,
        message_text: str,
        provider: str = "telegram",
        provider_customer_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
        creator_profile_id: int | None = None,
        source_metadata: Mapping[str, Any] | None = None,
        is_vip: bool = False,
    ) -> Any:
        ...


class RuntimeControlCompatible(Protocol):
    def evaluate_runtime(
        self,
        *,
        creator_profile_id: str | int | None = None,
    ) -> Any:
        ...

    def record_live_turn(
        self,
        *,
        creator_profile_id: str | int | None = None,
        has_offer: bool = False,
        has_delivery: bool = False,
    ) -> Any:
        ...

    def record_observation(
        self,
        *,
        creator_profile_id: str | int | None = None,
        customer_id: str | None = None,
        conversation_id: str | None = None,
        message_text: str = "",
        suggested_reply: str | None = None,
        suggested_offer: Mapping[str, Any] | None = None,
        suggested_delivery: Mapping[str, Any] | None = None,
        suggested_follow_up: Mapping[str, Any] | None = None,
        provider: str | None = None,
    ) -> Any:
        ...


class ConversationGateway:
    """Invoke one conversation brain once and normalize its result."""

    _DIAGNOSTIC_FIELDS = (
        "route",
        "relationship_route",
        "effective_route",
        "intent",
        "mode",
        "send_nudge",
        "nudge_type",
        "buyer_session_active",
    )

    def __init__(
        self,
        decision_engine: DecisionEngineCompatible,
        *,
        allowed_fanvue_hostnames: Sequence[str],
        telegram_commerce_service: TelegramCommerceCompatible | None = None,
        content_opportunity_ingestion_service: (
            ContentOpportunityIngestionCompatible | None
        ) = None,
        runtime_control_service: RuntimeControlCompatible | None = None,
        creator_profile_id: str | int | None = None,
    ) -> None:
        if decision_engine is None:
            raise ValueError("decision_engine is required")

        normalized_hosts = {
            str(hostname).strip().lower().rstrip(".")
            for hostname in allowed_fanvue_hostnames
            if str(hostname).strip()
        }
        if not normalized_hosts:
            raise ValueError("At least one Fanvue hostname is required")

        self._decision_engine = telegram_commerce_service or decision_engine
        self._allowed_fanvue_hostnames = frozenset(normalized_hosts)
        self._content_opportunity_ingestion_service = (
            content_opportunity_ingestion_service
        )
        self._runtime_control_service = runtime_control_service
        self._creator_profile_id = creator_profile_id

    def execute(
        self,
        gateway_input: ConversationGatewayInput,
    ) -> ConversationGatewayOutput:
        """Invoke DecisionEngine exactly once for a valid request."""

        validation_error = self._validate_input(gateway_input)
        if validation_error:
            return self._error_output(
                correlation_id=self._correlation_id(gateway_input),
                error_code=validation_error,
                status="invalid_request",
            )

        runtime_decision = self._runtime_decision()
        if runtime_decision is not None and not getattr(
            runtime_decision,
            "allow_decision_engine",
            True,
        ):
            return self._offline_output(
                correlation_id=gateway_input.correlation_id,
                runtime_decision=runtime_decision,
            )

        content_opportunity_ingestion = self._ingest_content_opportunity(gateway_input)

        try:
            engine_result = self._decision_engine.process_message(
                gateway_input.engine_user_id,
                gateway_input.message_text,
                chat_history=gateway_input.chat_history,
            )
        except TimeoutError as error:
            logger.exception(
                "[CONVERSATION GATEWAY ERROR] correlation_id=%s "
                "exception_type=%s exception_message=%s",
                gateway_input.correlation_id,
                type(error).__name__,
                str(error),
            )
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="decision_engine_timeout",
                status="engine_timeout",
            )
        except Exception as error:  # Boundary converts brain failures to data.
            logger.exception(
                "[CONVERSATION GATEWAY ERROR] correlation_id=%s "
                "exception_type=%s exception_message=%s",
                gateway_input.correlation_id,
                type(error).__name__,
                str(error),
            )
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="decision_engine_exception",
                status="engine_exception",
                extra_diagnostics={
                    "exception_type": type(error).__name__,
                },
            )

        if engine_result is None:
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="decision_engine_no_result",
                status="no_result",
            )

        if not isinstance(engine_result, Mapping):
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="decision_engine_malformed_result",
                status="malformed_result",
            )

        response_text = engine_result.get("response")
        if not isinstance(response_text, str):
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="decision_engine_malformed_result",
                status="malformed_result",
                extra_diagnostics=self._diagnostics(engine_result),
            )

        blocked = engine_result.get("blocked") is True
        offer_authorized = (
            not blocked and engine_result.get("send_offer") is True
        )
        offer_link = (
            self._authorized_offer_link(engine_result)
            if offer_authorized
            else None
        )
        delivery_type = (
            self._offer_delivery_type(engine_result)
            if offer_authorized
            else None
        )
        delivery_mode = (
            self._offer_delivery_mode(engine_result)
            if offer_authorized
            else None
        )
        delivery_requires_payment = (
            self._offer_requires_payment(engine_result)
            if offer_authorized
            else None
        )
        delivery_payload = self._delivery_payload(engine_result)

        error_code = None
        if blocked:
            error_code = self._safe_error_code(engine_result.get("error"))
            if error_code is None:
                error_code = "decision_engine_blocked"

        diagnostics = self._diagnostics(engine_result)
        diagnostics["status"] = "blocked" if blocked else "ok"
        diagnostics["offer_link_accepted"] = offer_link is not None
        diagnostics["delivery_type"] = delivery_type
        diagnostics["delivery_mode"] = delivery_mode
        diagnostics["delivery_requires_payment"] = delivery_requires_payment
        if content_opportunity_ingestion:
            diagnostics["content_opportunity_ingestion"] = (
                content_opportunity_ingestion
            )
        if delivery_payload:
            diagnostics["telegram_delivery_payload_ready"] = True

        if runtime_decision is not None:
            diagnostics["runtime_control"] = self._runtime_diagnostics(
                runtime_decision
            )

        if runtime_decision is not None and getattr(
            runtime_decision,
            "observe_only",
            False,
        ):
            self._record_observation(
                gateway_input=gateway_input,
                engine_result=engine_result,
                response_text=response_text,
                offer_authorized=offer_authorized,
                delivery_payload=delivery_payload,
            )
            diagnostics["status"] = "observe"
            diagnostics["runtime_control"]["observed_only"] = True
            return ConversationGatewayOutput(
                correlation_id=gateway_input.correlation_id,
                response_text="",
                offer_authorized=False,
                offer_link=None,
                blocked=True,
                error_code="runtime_observe_mode",
                delivery_type=None,
                delivery_mode=None,
                delivery_requires_payment=None,
                delivery_payload={},
                diagnostic_metadata=diagnostics,
            )

        self._record_live_turn(
            has_offer=offer_authorized,
            has_delivery=bool(delivery_payload),
        )

        return ConversationGatewayOutput(
            correlation_id=gateway_input.correlation_id,
            response_text=response_text,
            offer_authorized=offer_authorized,
            offer_link=offer_link,
            blocked=blocked,
            error_code=error_code,
            delivery_type=delivery_type,
            delivery_mode=delivery_mode,
            delivery_requires_payment=delivery_requires_payment,
            delivery_payload=delivery_payload,
            diagnostic_metadata=diagnostics,
        )

    def _runtime_decision(self) -> Any | None:
        service = self._runtime_control_service
        evaluate = getattr(service, "evaluate_runtime", None)
        if not callable(evaluate):
            return None
        return evaluate(creator_profile_id=self._creator_profile_id)

    def _record_live_turn(
        self,
        *,
        has_offer: bool,
        has_delivery: bool,
    ) -> None:
        service = self._runtime_control_service
        record = getattr(service, "record_live_turn", None)
        if not callable(record):
            return
        try:
            record(
                creator_profile_id=self._creator_profile_id,
                has_offer=has_offer,
                has_delivery=has_delivery,
            )
        except Exception:
            logger.exception("[RUNTIME CONTROL ERROR] live turn recording failed")

    def _record_observation(
        self,
        *,
        gateway_input: ConversationGatewayInput,
        engine_result: Mapping[str, Any],
        response_text: str,
        offer_authorized: bool,
        delivery_payload: Mapping[str, Any],
    ) -> None:
        service = self._runtime_control_service
        record = getattr(service, "record_observation", None)
        if not callable(record):
            return
        try:
            record(
                creator_profile_id=self._creator_profile_id,
                customer_id=gateway_input.engine_user_id,
                conversation_id=gateway_input.correlation_id,
                message_text=gateway_input.message_text,
                suggested_reply=response_text,
                suggested_offer=dict(engine_result.get("offer") or {})
                if offer_authorized
                else {},
                suggested_delivery=dict(delivery_payload or {}),
                suggested_follow_up={
                    "source": "DecisionEngine",
                    "intent": engine_result.get("intent"),
                    "route": self._safe_diagnostic_value(engine_result.get("route")),
                },
                provider="telegram",
            )
        except Exception:
            logger.exception("[RUNTIME CONTROL ERROR] observation recording failed")

    @staticmethod
    def _runtime_diagnostics(runtime_decision: Any) -> dict[str, Any]:
        mode = getattr(runtime_decision, "mode", RuntimeMode.OFFLINE)
        status = getattr(runtime_decision, "status", mode)
        return {
            "mode": getattr(mode, "value", str(mode)),
            "status": getattr(status, "value", str(status)),
            "allow_decision_engine": bool(
                getattr(runtime_decision, "allow_decision_engine", False)
            ),
            "allow_replies": bool(getattr(runtime_decision, "allow_replies", False)),
            "allow_offers": bool(getattr(runtime_decision, "allow_offers", False)),
            "allow_deliveries": bool(
                getattr(runtime_decision, "allow_deliveries", False)
            ),
            "reason": str(getattr(runtime_decision, "reason", "")),
        }

    @classmethod
    def _offline_output(
        cls,
        *,
        correlation_id: str,
        runtime_decision: Any,
    ) -> ConversationGatewayOutput:
        return ConversationGatewayOutput(
            correlation_id=correlation_id,
            response_text="",
            offer_authorized=False,
            offer_link=None,
            blocked=True,
            error_code="runtime_offline",
            diagnostic_metadata={
                "status": "offline",
                "runtime_control": cls._runtime_diagnostics(runtime_decision),
            },
        )

    def _ingest_content_opportunity(
        self,
        gateway_input: ConversationGatewayInput,
    ) -> dict[str, Any]:
        service = self._content_opportunity_ingestion_service
        ingest = getattr(service, "ingest_message", None)
        if not callable(ingest):
            return {}
        try:
            result = ingest(
                customer_id=gateway_input.engine_user_id,
                provider_customer_id=gateway_input.engine_user_id,
                message_text=gateway_input.message_text,
                provider="telegram",
                conversation_id=gateway_input.correlation_id,
                source_metadata={"source": "ConversationGateway"},
            )
        except Exception as error:
            logger.exception(
                "[CONTENT OPPORTUNITY INGESTION ERROR] correlation_id=%s "
                "exception_type=%s",
                gateway_input.correlation_id,
                type(error).__name__,
            )
            return {"recorded": False, "error": type(error).__name__}
        opportunity = getattr(result, "opportunity", None)
        guidance = getattr(result, "safe_response_guidance", {}) or {}
        return {
            "detected": bool(getattr(result, "detected", False)),
            "recorded": bool(getattr(result, "recorded", False)),
            "opportunity_id": getattr(opportunity, "opportunity_id", None),
            "status": str(getattr(getattr(opportunity, "status", None), "value", "")),
            "soft_response_suggestion": guidance.get("soft_response_suggestion"),
            "must_not_promise_future_content": bool(
                guidance.get("must_not_promise_future_content", False)
            ),
            "decision_owner": "DecisionEngine",
            "sends_messages": False,
        }

    @staticmethod
    def _validate_input(
        gateway_input: ConversationGatewayInput,
    ) -> str | None:
        if not isinstance(gateway_input, ConversationGatewayInput):
            return "invalid_gateway_input"
        if not isinstance(gateway_input.engine_user_id, str):
            return "invalid_engine_user_id"
        if not gateway_input.engine_user_id.strip():
            return "invalid_engine_user_id"
        if not isinstance(gateway_input.message_text, str):
            return "invalid_message_text"
        if not gateway_input.message_text.strip():
            return "invalid_message_text"
        if not isinstance(gateway_input.chat_history, list):
            return "invalid_chat_history"
        if not isinstance(gateway_input.correlation_id, str):
            return "invalid_correlation_id"
        if not gateway_input.correlation_id.strip():
            return "invalid_correlation_id"
        return None

    @staticmethod
    def _correlation_id(gateway_input: object) -> str:
        value = getattr(gateway_input, "correlation_id", "")
        return value if isinstance(value, str) else ""

    def _authorized_offer_link(
        self,
        engine_result: Mapping[str, Any],
    ) -> str | None:
        if self._offer_requires_payment(engine_result) is False:
            return None

        offer = engine_result.get("offer")
        if not isinstance(offer, Mapping):
            return None

        content = offer.get("content")
        if not isinstance(content, Mapping):
            return None

        link = content.get("fanvue_link")
        if not isinstance(link, str) or not self._is_allowed_link(link):
            return None
        return link

    def _is_allowed_link(self, link: str) -> bool:
        if not link or any(character.isspace() for character in link):
            return False

        try:
            parsed = urlsplit(link)
            hostname = (parsed.hostname or "").lower().rstrip(".")
            port = parsed.port
        except ValueError:
            return False

        return (
            parsed.scheme.lower() == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
            and port in (None, 443)
            and hostname in self._allowed_fanvue_hostnames
        )

    def _offer_delivery_type(self, engine_result: Mapping[str, Any]) -> str | None:
        return self._offer_value(
            engine_result,
            "delivery_type",
        )

    def _offer_delivery_mode(self, engine_result: Mapping[str, Any]) -> str | None:
        return self._offer_value(
            engine_result,
            "delivery_permission_mode",
            "delivery_mode",
        )

    def _offer_requires_payment(
        self,
        engine_result: Mapping[str, Any],
    ) -> bool | None:
        value = self._offer_value(
            engine_result,
            "delivery_requires_payment",
            "requires_payment",
        )
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "paid"}:
                return True
            if normalized in {"false", "0", "no", "free", "included"}:
                return False
        mode = self._offer_delivery_mode(engine_result)
        if mode:
            return str(mode).lower() == "paid"
        delivery_type = self._offer_delivery_type(engine_result)
        if delivery_type:
            return str(delivery_type).upper() == "PAID"
        return None

    @staticmethod
    def _offer_value(
        engine_result: Mapping[str, Any],
        *names: str,
    ) -> Any:
        offer = engine_result.get("offer")
        if not isinstance(offer, Mapping):
            return None

        sources = [offer]
        content = offer.get("content")
        if isinstance(content, Mapping):
            sources.append(content)

        for source in sources:
            for name in names:
                value = source.get(name)
                if value is not None:
                    return value
        return None

    @classmethod
    def _delivery_payload(
        cls,
        engine_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = engine_result.get("telegram_delivery_payload")
        if not isinstance(payload, Mapping):
            return {}
        return {
            str(key): cls._safe_diagnostic_value(value)
            for key, value in payload.items()
            if cls._is_safe_diagnostic_key(str(key))
        }

    def _diagnostics(
        self,
        engine_result: Mapping[str, Any],
    ) -> dict[str, Any]:
        diagnostics = {
            field: self._safe_diagnostic_value(engine_result[field])
            for field in self._DIAGNOSTIC_FIELDS
            if field in engine_result
        }

        offer = engine_result.get("offer")
        if isinstance(offer, Mapping):
            offer_type = offer.get("offer_type")
            if isinstance(offer_type, (str, int, float, bool)):
                diagnostics["offer_type"] = offer_type

        return diagnostics

    @classmethod
    def _safe_diagnostic_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return {
                str(key): cls._safe_diagnostic_value(item)
                for key, item in value.items()
                if cls._is_safe_diagnostic_key(str(key))
            }
        if isinstance(value, (list, tuple)):
            return [cls._safe_diagnostic_value(item) for item in value]
        return str(type(value).__name__)

    @staticmethod
    def _is_safe_diagnostic_key(key: str) -> bool:
        lowered = key.lower()
        secret_markers = (
            "api_key",
            "authorization",
            "cookie",
            "password",
            "prompt",
            "secret",
            "token",
        )
        return not any(marker in lowered for marker in secret_markers)

    @staticmethod
    def _safe_error_code(value: Any) -> str | None:
        if not isinstance(value, str) or not value or len(value) > 64:
            return None
        if not all(character.isalnum() or character in "._-" for character in value):
            return None
        return value

    @staticmethod
    def _error_output(
        *,
        correlation_id: str,
        error_code: str,
        status: str,
        extra_diagnostics: Mapping[str, Any] | None = None,
    ) -> ConversationGatewayOutput:
        diagnostics = {"status": status}
        if extra_diagnostics:
            diagnostics.update(extra_diagnostics)
        return ConversationGatewayOutput(
            correlation_id=correlation_id,
            response_text="",
            offer_authorized=False,
            offer_link=None,
            blocked=True,
            error_code=error_code,
            diagnostic_metadata=diagnostics,
        )

"""Channel-neutral facade around the existing DecisionEngine entry point."""

import logging
import inspect
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
    ConversationGatewayOutput,
)
from app.models.chat_commerce import ChatCommerceDecision
from app.models.customer_sales_decision import CustomerSalesDecision
from app.services.commerce_execution_policy import (
    CommerceExecutionPolicy,
    derive_commerce_execution_policy,
)
from app.models.runtime_control import RuntimeMode
from app.models.commerce_mode import CommerceMode
from app.services.commerce_mode_service import CommerceModeService
from app.services.relationship_mode_service import RelationshipModeService


logger = logging.getLogger(__name__)


class DecisionEngineCompatible(Protocol):
    """The only brain behavior required by the gateway."""

    def process_message(
        self,
        user_id: str,
        message: str,
        chat_history: list[Any] | None = None,
        runtime_injection: dict[str, Any] | None = None,
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
        "send_offer",
        "should_send_offer_behavior",
        "selected_content",
        "final_offer",
        "buyer_tier",
        "user_value_tier",
        "ownership_blocked",
        "delivery_prepared",
        "delivery_blocking_reason",
        "send_nudge",
        "nudge_type",
        "buyer_session_active",
        "provider",
        "selected_provider",
        "provider_preview",
        "commerce_execution_policy",
        "legacy_offer_requested",
        "commerce_offer_authorized",
        "final_offer_authorized",
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
        chat_commerce_service: Any | None = None,
        customer_sales_brain_service: Any | None = None,
        raise_engine_exceptions: bool = False,
        global_automation_safety_service: Any | None = None,
        commerce_mode_service: Any | None = None,
        relationship_mode_service: Any | None = None,
        sales_session_service: Any | None = None,
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
        self._chat_commerce_service = chat_commerce_service
        self._customer_sales_brain_service = customer_sales_brain_service
        self._raise_engine_exceptions = raise_engine_exceptions
        self._global_automation_safety_service = global_automation_safety_service
        self._commerce_mode_service = commerce_mode_service or CommerceModeService()
        self._relationship_mode_service = (
            relationship_mode_service or RelationshipModeService()
        )
        self._sales_session_service = sales_session_service

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

        if self._global_automation_safety_service is not None:
            global_result = self._global_automation_safety_service.check_global_safety()
            if not global_result.get("allowed", False):
                return self._error_output(
                    correlation_id=gateway_input.correlation_id,
                    error_code="global_automation_blocked",
                    status="autonomous_execution_blocked",
                    extra_diagnostics={"reason": global_result.get("reason")},
                )

        content_opportunity_ingestion = self._ingest_content_opportunity(gateway_input)
        try:
            sales_session = self._resolve_conversation_sales_session(
                gateway_input
            )
        except Exception as error:
            logger.warning(
                "event=conversation_sales_session_unavailable error_type=%s "
                "correlation_id=%s",
                type(error).__name__, gateway_input.correlation_id,
            )
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="canonical_sales_session_unavailable",
                status="commerce_context_unavailable",
            )
        customer_sales_decision = self._evaluate_customer_sales_brain(
            gateway_input, sales_session=sales_session,
        )
        commerce_mode = self._commerce_mode_service.get_mode()
        commerce_runtime_injection = self._commerce_runtime_injection(
            customer_sales_decision
        )
        authoritative_runtime = (
            getattr(self._chat_commerce_service, "commerce_mode", None)
            == "AUTHORITATIVE"
        )
        if authoritative_runtime and not commerce_runtime_injection:
            commerce_runtime_injection = {
                "commerce_execution_policy": (
                    CommerceExecutionPolicy.DISABLED_FOR_TURN.value
                ),
                "authoritative_selection_missing": True,
                "commerce_decision": {
                    "decision": "UNAVAILABLE",
                    "reason_code": "AUTHORITATIVE_CONTEXT_UNAVAILABLE",
                    "buyer_stage": "UNKNOWN",
                    "current_offer_status": None,
                    "conversion_state": "UNKNOWN",
                    "commerce_execution_policy": (
                        CommerceExecutionPolicy.DISABLED_FOR_TURN.value
                    ),
                },
            }
            logger.warning(
                "event=canonical_commerce_context_unavailable "
                "legacy_commerce_disabled=true correlation_id=%s",
                gateway_input.correlation_id,
            )
        engine_runtime_injection = dict(commerce_runtime_injection)
        if commerce_mode is not CommerceMode.LIVE:
            engine_runtime_injection["commerce_execution_policy"] = (
                CommerceExecutionPolicy.DISABLED_FOR_TURN.value
            )
            engine_context = dict(
                engine_runtime_injection.get("commerce_decision") or {}
            )
            engine_context.update({
                "commerce_execution_policy": (
                    CommerceExecutionPolicy.DISABLED_FOR_TURN.value
                ),
                "commerce_mode": commerce_mode.value,
                "decision": (
                    "PRE_LAUNCH"
                    if commerce_mode is CommerceMode.RELATIONSHIP
                    and customer_sales_decision is not None
                    and customer_sales_decision.sell_allowed
                    else engine_context.get("decision")
                ),
            })
            engine_runtime_injection["commerce_decision"] = engine_context
        if (
            customer_sales_decision is not None
            and customer_sales_decision.decision.value == "PRESENT_OFFER"
        ):
            engine_runtime_injection["commerce_execution_policy"] = (
                CommerceExecutionPolicy.DISABLED_FOR_TURN.value
            )
            engine_context = dict(
                engine_runtime_injection.get("commerce_decision") or {}
            )
            engine_context["commerce_execution_policy"] = (
                CommerceExecutionPolicy.DISABLED_FOR_TURN.value
            )
            engine_runtime_injection["commerce_decision"] = engine_context

        try:
            engine_result = self._invoke_decision_engine(
                gateway_input.engine_user_id,
                gateway_input.message_text,
                chat_history=gateway_input.chat_history,
                runtime_injection=engine_runtime_injection,
            )
        except TimeoutError as error:
            if self._raise_engine_exceptions:
                raise
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
            if self._raise_engine_exceptions:
                raise
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
        engine_offer_requested = engine_result.get("send_offer") is True
        legacy_offer_requested = (
            engine_result.get("legacy_offer_requested") is True
            if "legacy_offer_requested" in engine_result
            else engine_offer_requested
        )
        if (
            customer_sales_decision is not None
            and self._customer_sales_brain_service is not None
        ):
            refiner = getattr(
                self._customer_sales_brain_service,
                "refine_for_readiness",
                None,
            )
            if refiner is None:
                from app.services.customer_sales_brain_service import (
                    CustomerSalesBrainService,
                )
                refiner = CustomerSalesBrainService.refine_for_readiness
            customer_sales_decision = (
                refiner(
                    customer_sales_decision,
                    engine_result.get("commerce_readiness"),
                )
            )
            commerce_runtime_injection = self._commerce_runtime_injection(
                customer_sales_decision
            )
        would_have_sold = bool(
            customer_sales_decision is not None
            and customer_sales_decision.sell_allowed
            and customer_sales_decision.recommended_offering_id is not None
        )
        relationship_suppressed = bool(
            commerce_mode is CommerceMode.RELATIONSHIP and would_have_sold
        )
        commerce_offer_allowed = (
            customer_sales_decision.sell_allowed
            and not commerce_runtime_injection.get(
                "authoritative_selection_missing", False
            )
            if customer_sales_decision is not None
            else self._customer_sales_brain_service is None
        )
        if commerce_mode is not CommerceMode.LIVE:
            commerce_offer_allowed = False
        offer_authorized = (
            not blocked and commerce_offer_allowed
            if customer_sales_decision is not None
            else not blocked and engine_offer_requested
        )
        legacy_offer_link = (
            self._authorized_offer_link(engine_result)
            if offer_authorized
            else None
        )
        legacy_delivery_type = (
            self._offer_delivery_type(engine_result)
            if offer_authorized
            else None
        )
        legacy_delivery_mode = (
            self._offer_delivery_mode(engine_result)
            if offer_authorized
            else None
        )
        legacy_delivery_requires_payment = (
            self._offer_requires_payment(engine_result)
            if offer_authorized
            else None
        )
        legacy_delivery_payload = self._delivery_payload(engine_result)

        error_code = None
        if blocked:
            error_code = self._safe_error_code(engine_result.get("error"))
            if error_code is None:
                error_code = "decision_engine_blocked"

        diagnostics = self._diagnostics(engine_result)
        if commerce_runtime_injection.get("commerce_decision"):
            diagnostics["commerce_decision"] = dict(
                commerce_runtime_injection["commerce_decision"]
            )
        if commerce_runtime_injection.get("commerce_execution_policy"):
            diagnostics["commerce_execution_policy"] = (
                commerce_runtime_injection["commerce_execution_policy"]
            )
        diagnostics.update(self._customer_sales_diagnostics(
            customer_sales_decision
        ))
        diagnostics["engine_offer_requested"] = engine_offer_requested
        diagnostics["legacy_offer_requested"] = legacy_offer_requested
        diagnostics["commerce_offer_allowed"] = commerce_offer_allowed
        diagnostics["commerce_offer_authorized"] = commerce_offer_allowed
        diagnostics["offer_authorized"] = offer_authorized
        diagnostics["final_offer_authorized"] = offer_authorized
        diagnostics.update({
            "configured_commerce_mode": commerce_mode.value,
            "relationship_mode_active": (
                commerce_mode is CommerceMode.RELATIONSHIP
            ),
            "would_have_sold": would_have_sold,
            "commerce_suppression_reason": (
                "RELATIONSHIP_MODE" if relationship_suppressed
                else "COMMERCE_OFF" if commerce_mode is CommerceMode.OFF
                else None
            ),
            "purchase_intent_created": False if relationship_suppressed else None,
            "customer_commerce_stage": (
                "PRE_LAUNCH_INTEREST" if relationship_suppressed else None
            ),
        })
        diagnostics.update(self._commerce_authority_diagnostics(
            customer_sales_decision,
            commerce_runtime_injection,
        ))
        logger.info(
            "event=commerce_authorization legacy_offer_requested=%s "
            "commerce_offer_authorized=%s final_offer_authorized=%s "
            "correlation_id=%s",
            legacy_offer_requested,
            commerce_offer_allowed,
            offer_authorized,
            gateway_input.correlation_id,
        )
        diagnostics["status"] = "blocked" if blocked else "ok"
        if content_opportunity_ingestion:
            diagnostics["content_opportunity_ingestion"] = (
                content_opportunity_ingestion
            )
        commerce = (
            self._compose_commerce(
                gateway_input=gateway_input,
                response_text=response_text,
                offer_authorized=offer_authorized,
                diagnostics=diagnostics,
                customer_sales_decision=customer_sales_decision,
            )
            if not blocked
            else {"response_text": response_text, "diagnostics": {}}
        )
        response_text = commerce["response_text"]
        diagnostics.update(commerce["diagnostics"])
        offering = commerce.get("offering")
        if relationship_suppressed:
            try:
                self._relationship_mode_service.record_would_have_sold(
                    customer_sales_decision,
                    correlation_id=gateway_input.correlation_id,
                )
                diagnostics["would_have_sold_recorded"] = True
            except Exception as error:
                diagnostics["would_have_sold_recorded"] = False
                logger.warning(
                    "event=relationship_mode_learning_failed error_type=%s "
                    "correlation_id=%s",
                    type(error).__name__, gateway_input.correlation_id,
                )
            pre_launch = self._relationship_mode_service.response(
                customer_identifier=gateway_input.engine_user_id,
                correlation_id=gateway_input.correlation_id,
            )
            response_text = f"{response_text.rstrip()}\n\n{pre_launch}".strip()
            diagnostics.update({
                "commerce_prompt_mode": "PRE_LAUNCH",
                "delivery_source": "RELATIONSHIP_MODE_SUPPRESSED",
                "no_purchase_intent_created": True,
            })
        if authoritative_runtime and offer_authorized and offering is None:
            offer_authorized = False
            diagnostics["offer_authorized"] = False
            diagnostics["final_offer_authorized"] = False
        if authoritative_runtime:
            (
                offer_link,
                delivery_type,
                delivery_mode,
                delivery_requires_payment,
                delivery_payload,
            ) = self._authoritative_delivery(
                response_text=response_text,
                offering=offering if offer_authorized else None,
            )
            diagnostics.update({
                "commerce_mode": "AUTHORITATIVE",
                "compatibility_mode": False,
                "delivery_source": (
                    "RESOLVED_COMMERCIAL_OFFERING"
                    if offering is not None and offer_authorized
                    else "AUTHORITATIVE_CONVERSATION"
                ),
                "memory_source": "CANONICAL_COMMERCE",
                "eligibility_source": (
                    "COMMERCIAL_OFFERING_SELECTOR_AND_SALES_SAFETY"
                ),
                "recommendation_source": (
                    diagnostics.get("selection_source") or "NONE"
                ),
                "legacy_memory_mutated": False,
                "legacy_delivery_used": False,
            })
            logger.info(
                "event=canonical_commerce_state_used "
                "delivery_source=%s eligibility_source=%s correlation_id=%s",
                diagnostics["delivery_source"],
                diagnostics["eligibility_source"],
                gateway_input.correlation_id,
            )
            if legacy_delivery_payload or legacy_offer_link:
                logger.info(
                    "event=legacy_delivery_metadata_skipped correlation_id=%s",
                    gateway_input.correlation_id,
                )
        else:
            offer_link = legacy_offer_link
            delivery_type = legacy_delivery_type
            delivery_mode = legacy_delivery_mode
            delivery_requires_payment = legacy_delivery_requires_payment
            delivery_payload = legacy_delivery_payload
            diagnostics.update({
                "commerce_mode": "COMPATIBILITY",
                "compatibility_mode": True,
                "delivery_source": "LEGACY_DECISION_ENGINE",
                "memory_source": "LEGACY_CONVERSATION_MEMORY",
                "eligibility_source": "LEGACY_COMMERCE_SALES",
                "recommendation_source": (
                    diagnostics.get("selection_source")
                    or "COMPATIBILITY_RECOMMEND_BEST"
                ),
                "legacy_memory_mutated": True,
                "legacy_delivery_used": bool(
                    legacy_delivery_payload or legacy_offer_link
                ),
            })
            logger.warning(
                "event=compatibility_mode_entered "
                "delivery_source=legacy_decision_engine correlation_id=%s",
                gateway_input.correlation_id,
            )
        diagnostics["offer_link_accepted"] = offer_link is not None
        diagnostics["delivery_type"] = delivery_type
        diagnostics["delivery_mode"] = delivery_mode
        diagnostics["delivery_requires_payment"] = delivery_requires_payment
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

    def _compose_commerce(
        self,
        *,
        gateway_input: ConversationGatewayInput,
        response_text: str,
        offer_authorized: bool,
        diagnostics: dict[str, Any],
        customer_sales_decision: CustomerSalesDecision | None,
    ) -> dict[str, Any]:
        service = self._chat_commerce_service
        if service is None:
            return {"response_text": response_text, "diagnostics": {}}
        context = self._brain_context(gateway_input)
        if not context.creator_profile_id:
            decision = ChatCommerceDecision(
                False,
                service.requested_media_type(gateway_input.message_text),
                (),
                None,
                None,
                "CREATOR_PROFILE_UNAVAILABLE",
            )
        else:
            relationship, reason = self._commerce_relationship(diagnostics)
            commerce_context = service.build_context(
                creator_profile_id=int(context.creator_profile_id),
                purchase_intent=bool(offer_authorized),
                message_text=gateway_input.message_text,
                diagnostics=diagnostics,
                customer_identifier=context.customer_identifier,
                conversation_identifier=context.conversation_identifier,
                relationship_level=relationship,
                recommendation_reason=reason,
            )
            decision = service.recommend(
                commerce_context,
                customer_sales_decision=customer_sales_decision,
            )
        if (
            decision.offering is not None
            and not self._is_allowed_link(decision.offering.delivery_url)
        ):
            logger.warning(
                "event=unsafe_authoritative_delivery_url_rejected "
                "correlation_id=%s",
                gateway_input.correlation_id,
            )
            decision = ChatCommerceDecision(
                decision.lookup_attempted,
                decision.requested_media_type,
                decision.requested_themes,
                None,
                None,
                "UNSAFE_DELIVERY_URL",
                decision.selection_source,
                decision.legacy_recommendation_used,
            )
        composed = service.compose_reply(response_text, decision)
        commerce_diagnostics = dict(decision.diagnostics())
        commerce_diagnostics["commerce_composed"] = decision.offering is not None
        commerce_diagnostics["developer_mode"] = context.developer_mode
        logger.info(
            "event=commercial_offering_selection_source source=%s "
            "legacy_recommendation_used=%s correlation_id=%s",
            commerce_diagnostics.get("selection_source"),
            commerce_diagnostics.get("legacy_recommendation_used"),
            gateway_input.correlation_id,
        )
        if customer_sales_decision is not None:
            logger.info(
                "event=existing_workflow_selected decision=%s workflow=%s "
                "correlation_id=%s",
                customer_sales_decision.decision.value,
                (
                    "offer_presentation"
                    if decision.offering is not None
                    else "normal_conversation"
                ),
                gateway_input.correlation_id,
            )
        return {
            "response_text": composed,
            "diagnostics": commerce_diagnostics,
            "offering": decision.offering,
        }

    @staticmethod
    def _authoritative_delivery(*, response_text: str, offering):
        if offering is None:
            return (
                None,
                "text",
                "conversation",
                False,
                {
                    "delivery_type": "text",
                    "message_text": response_text,
                    "delivery_method": "text",
                    "delivery_reason": "authoritative_conversation",
                    "metadata": {"commerce_mode": "AUTHORITATIVE"},
                },
            )
        return (
            offering.delivery_url,
            offering.offering_type,
            "provider_link",
            True,
            {
                "delivery_type": offering.offering_type,
                "message_text": response_text,
                "media_link": offering.delivery_url,
                "product_reference": str(offering.offering_id),
                "delivery_method": "text",
                "delivery_reason": "authoritative_commercial_offering",
                "metadata": {
                    "commerce_mode": "AUTHORITATIVE",
                    "publication_id": str(offering.publication_id),
                    "provider": offering.provider,
                    "provider_resource_id": offering.provider_resource_id,
                    "price_minor": offering.price_minor,
                    "currency": offering.currency,
                },
            },
        )

    def _brain_context(
        self, gateway_input: ConversationGatewayInput,
    ) -> ConversationBrainContext:
        if gateway_input.brain_context is not None:
            supplied = gateway_input.brain_context
            return ConversationBrainContext(
                creator_profile_id=(
                    supplied.creator_profile_id
                    if supplied.creator_profile_id is not None
                    else (
                        int(self._creator_profile_id)
                        if self._creator_profile_id is not None else None
                    )
                ),
                customer_identifier=supplied.customer_identifier,
                conversation_identifier=supplied.conversation_identifier,
                primary_sales_channel=supplied.primary_sales_channel,
                developer_mode=supplied.developer_mode,
                telegram_user_id=supplied.telegram_user_id,
                fanvue_account_id=supplied.fanvue_account_id,
                external_fanvue_buyer_uuid=(
                    supplied.external_fanvue_buyer_uuid
                ),
                fanvue_user_id=supplied.fanvue_user_id,
                conversation_thread_id=supplied.conversation_thread_id,
                purchase_acknowledgement_pending=(
                    supplied.purchase_acknowledgement_pending
                ),
                purchase_acknowledgement_intent_id=(
                    supplied.purchase_acknowledgement_intent_id
                ),
            )
        return ConversationBrainContext(
            creator_profile_id=(
                int(self._creator_profile_id)
                if self._creator_profile_id is not None
                else None
            ),
            customer_identifier=gateway_input.engine_user_id,
            conversation_identifier=gateway_input.correlation_id,
        )

    def _evaluate_customer_sales_brain(
        self, gateway_input: ConversationGatewayInput, *, sales_session=None,
    ) -> CustomerSalesDecision | None:
        service = self._customer_sales_brain_service
        if service is None:
            return None
        context = self._brain_context(gateway_input)
        if context.creator_profile_id is None:
            logger.warning(
                "event=customer_sales_brain_skipped reason=creator_unavailable "
                "correlation_id=%s",
                gateway_input.correlation_id,
            )
            return None
        decision_context = {
            "purchase_acknowledgement_pending": (
                context.purchase_acknowledgement_pending
            ),
            "latest_message": gateway_input.message_text,
            "conversation_id": context.conversation_identifier,
            "requested_media_type": (
                self._chat_commerce_service.requested_media_type(
                    gateway_input.message_text
                )
                if self._chat_commerce_service is not None
                else None
            ),
            "recent_conversation_requests": tuple(
                str(item.get("content") or "")
                for item in tuple(gateway_input.chat_history or ())[-8:]
                if isinstance(item, Mapping)
                and str(item.get("role") or "").lower() == "user"
                and str(item.get("content") or "").strip()
            )[-3:],
        }
        if sales_session is not None:
            decision_context["sales_session_id"] = str(
                sales_session.sales_session_id
            )
        if context.telegram_user_id is not None:
            decision = service.evaluate_for_telegram_user(
                creator_profile_id=int(context.creator_profile_id),
                telegram_user_id=int(context.telegram_user_id),
                conversation_context=decision_context,
            )
        elif (
            context.fanvue_account_id is not None
            and context.external_fanvue_buyer_uuid
        ):
            decision = service.evaluate_for_buyer(
                creator_profile_id=int(context.creator_profile_id),
                fanvue_account_id=int(context.fanvue_account_id),
                external_fanvue_buyer_uuid=context.external_fanvue_buyer_uuid,
                telegram_user_id=None,
                identity_resolved=False,
                conversation_context=decision_context,
            )
        else:
            logger.warning(
                "event=customer_sales_brain_skipped reason=identity_unavailable "
                "correlation_id=%s",
                gateway_input.correlation_id,
            )
            return None
        logger.info(
            "event=customer_sales_brain_evaluated decision=%s reason_code=%s "
            "correlation_id=%s",
            decision.decision.value, decision.reason_code.value,
            gateway_input.correlation_id,
        )
        return decision

    def _resolve_conversation_sales_session(self, gateway_input):
        context = self._brain_context(gateway_input)
        if (
            context.creator_profile_id is None
            or context.fanvue_account_id is None
            or context.fanvue_user_id is None
            or context.conversation_thread_id is None
        ):
            return None
        service = self._sales_session_service
        if service is None:
            from app.services.sales_session_service import SalesSessionService
            service = SalesSessionService()
            self._sales_session_service = service
        return service.resolve_or_start_conversation(
            creator_profile_id=int(context.creator_profile_id),
            fanvue_account_id=int(context.fanvue_account_id),
            fanvue_user_id=int(context.fanvue_user_id),
            telegram_user_id=context.telegram_user_id,
            conversation_thread_id=int(context.conversation_thread_id),
            objective="Authorized conversational commerce",
            commercial_context={
                "conversationIdentifier": context.conversation_identifier,
                "primarySalesChannel": context.primary_sales_channel,
            },
            actor_type="AI",
            actor_identifier="ConversationGateway",
        )

    @staticmethod
    def _commerce_runtime_injection(
        decision: CustomerSalesDecision | None,
    ) -> dict[str, Any]:
        if decision is None:
            return {}
        policy = derive_commerce_execution_policy(decision)
        selection_missing = (
            policy is CommerceExecutionPolicy.PRESENTATION_ALLOWED
            and (
                decision.recommended_offering_id is None
                or not decision.recommended_offering_title
                or decision.recommended_offering_price_minor is None
                or not decision.recommended_offering_currency
            )
        )
        effective_policy = (
            CommerceExecutionPolicy.DISABLED_FOR_TURN
            if selection_missing else policy
        )
        context = {
            "decision": decision.decision.value,
            "reason_code": decision.reason_code.value,
            "buyer_stage": decision.buyer_stage.value,
            "current_offer_status": decision.active_offer_status,
            "conversion_state": decision.active_offer_conversion_state,
            "commerce_execution_policy": effective_policy.value,
        }
        if (
            effective_policy.value in {
                "COMMERCE_PRESENTATION_ALLOWED",
                "COMMERCE_NUDGE_ALLOWED",
            }
            and decision.recommended_offering_title
        ):
            context["selected_offering"] = {
                "title": decision.recommended_offering_title,
                "short_description": (
                    decision.recommended_offering_short_description
                ),
                "price_minor": decision.recommended_offering_price_minor,
                "currency": decision.recommended_offering_currency,
            }
        logger.info(
            "event=commerce_execution_policy_derived policy=%s decision=%s "
            "reason_code=%s",
            effective_policy.value, decision.decision.value,
            decision.reason_code.value,
        )
        if selection_missing:
            logger.warning(
                "event=missing_authoritative_selection decision=%s "
                "compatibility_fallback_blocked=true",
                decision.decision.value,
            )
        return {
            "commerce_decision": context,
            "commerce_execution_policy": effective_policy.value,
            "authoritative_selection_missing": selection_missing,
        }

    @staticmethod
    def _commerce_authority_diagnostics(
        decision: CustomerSalesDecision | None,
        runtime_injection: Mapping[str, Any],
    ) -> dict[str, Any]:
        if decision is None:
            return {
                "authoritative_offering_selected": False,
                "selection_source": "NONE",
                "commerce_prompt_mode": "COMPATIBILITY",
                "legacy_recommendation_used": False,
            }
        policy = str(
            runtime_injection.get("commerce_execution_policy") or ""
        )
        modes = {
            "COMMERCE_PRESENTATION_ALLOWED": "PRESENT_OFFER",
            "COMMERCE_NUDGE_ALLOWED": "NUDGE_ACTIVE_OFFER",
            "COMMERCE_ACKNOWLEDGEMENT_ALLOWED": "CONGRATULATE_PURCHASE",
            "COMMERCE_PAYMENT_PENDING": "PAYMENT_PENDING",
            "COMMERCE_MANUAL_REVIEW": "MANUAL_REVIEW",
            "COMMERCE_DISABLED_FOR_TURN": "NO_PAID_OFFER",
        }
        selected = bool(
            (runtime_injection.get("commerce_decision") or {}).get(
                "selected_offering"
            )
        )
        return {
            "authoritative_offering_selected": selected,
            "selection_source": (
                "COMMERCIAL_OFFERING_SELECTOR" if selected else "NONE"
            ),
            "commerce_prompt_mode": modes.get(policy, "NO_PAID_OFFER"),
            "legacy_recommendation_used": False,
        }

    @staticmethod
    def _customer_sales_diagnostics(
        decision: CustomerSalesDecision | None,
    ) -> dict[str, Any]:
        if decision is None:
            return {}
        selector = dict(decision.decision_metadata or {}).get(
            "offeringSelector"
        )
        selector_diagnostics = (
            dict(selector) if isinstance(selector, Mapping) else {}
        )
        intelligence = dict(decision.decision_metadata or {}).get(
            "commercialIntelligence"
        )
        return {
            "customer_sales_decision": decision.decision.value,
            "customer_sales_reason_code": decision.reason_code.value,
            "customer_buyer_stage": decision.buyer_stage.value,
            "customer_current_offer_status": decision.active_offer_status,
            "customer_conversion_state": (
                decision.active_offer_conversion_state
            ),
            "customer_sales_brain_evaluated": True,
            "recommendation_trace": (
                selector_diagnostics.get("recommendationTrace") or []
            ),
            "recommendation_diagnostics": selector_diagnostics or None,
            "commercial_intelligence": (
                dict(intelligence)
                if isinstance(intelligence, Mapping) else None
            ),
        }

    def _invoke_decision_engine(
        self, user_id: str, message: str, *, chat_history,
        runtime_injection: dict[str, Any],
    ):
        process = self._decision_engine.process_message
        parameters = inspect.signature(process).parameters
        if "runtime_injection" in parameters:
            return process(
                user_id, message, chat_history=chat_history,
                runtime_injection=runtime_injection,
            )
        return process(user_id, message, chat_history=chat_history)

    @staticmethod
    def _commerce_relationship(
        diagnostics: Mapping[str, Any],
    ) -> tuple[str, str]:
        route = diagnostics.get("route") or {}
        relationship = str(
            diagnostics.get("effective_route")
            or diagnostics.get("relationship_route")
            or (route.get("route") if isinstance(route, Mapping) else route)
            or "unknown"
        )
        reason = (
            str(route.get("reason") or "")
            if isinstance(route, Mapping)
            else ""
        )
        return relationship, reason or "DecisionEngine authorized the turn."

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
        context = gateway_input.brain_context
        if context is not None:
            if not isinstance(context, ConversationBrainContext):
                return "invalid_brain_context"
            if context.primary_sales_channel != "AI_CHAT":
                return "invalid_sales_channel"
            if not context.customer_identifier.strip():
                return "invalid_customer_identifier"
            if not context.conversation_identifier.strip():
                return "invalid_conversation_identifier"
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

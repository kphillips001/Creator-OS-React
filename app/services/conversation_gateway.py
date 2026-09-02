"""Channel-neutral facade around the existing DecisionEngine entry point."""

import logging
import inspect
import re
from difflib import SequenceMatcher
from dataclasses import replace
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlsplit

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
    ConversationGatewayOutput,
)
from app.models.chat_commerce import ChatCommerceDecision
from app.models.customer_sales_decision import (
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
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
        photoshoot_conversation_context_builder: Any | None = None,
        asset_repository: Any | None = None,
        runtime_media_resolver: Any | None = None,
        content_presentation_validator: Any | None = None,
        commercial_presentation_copy_generator: Any | None = None,
        purchase_acknowledgement_copy_generator: Any | None = None,
        ava_persona_runtime_service: Any | None = None,
        conversation_quality_watch_service: Any | None = None,
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
        if content_presentation_validator is None:
            from app.services.customer_content_presentation_validator import (
                CustomerContentPresentationValidator,
            )
            content_presentation_validator = CustomerContentPresentationValidator()
        self._content_presentation_validator = content_presentation_validator
        self._commercial_presentation_copy_generator = (
            commercial_presentation_copy_generator
        )
        self._purchase_acknowledgement_copy_generator = (
            purchase_acknowledgement_copy_generator
        )
        self._ava_persona_runtime_service = ava_persona_runtime_service
        if conversation_quality_watch_service is None:
            from app.services.conversation_quality_watch_service import (
                ConversationQualityWatchService,
            )
            conversation_quality_watch_service = ConversationQualityWatchService()
        self._conversation_quality_watch_service = conversation_quality_watch_service
        if photoshoot_conversation_context_builder is None:
            from app.services.photoshoot_session_conversation_context_builder import (
                PhotoshootSessionConversationContextBuilder,
            )
            photoshoot_conversation_context_builder = PhotoshootSessionConversationContextBuilder()
        self._photoshoot_conversation_context_builder = photoshoot_conversation_context_builder
        if asset_repository is None:
            from app.repositories.asset_repository import AssetRepository
            asset_repository = AssetRepository()
        if runtime_media_resolver is None:
            from app.services.runtime_media_resolver import RuntimeMediaResolver
            runtime_media_resolver = RuntimeMediaResolver()
        self._asset_repository = asset_repository
        self._runtime_media_resolver = runtime_media_resolver

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
        from app.services.controlled_autonomy_test_service import (
            ControlledAutonomyTestService,
        )
        controlled_test_active = (
            ControlledAutonomyTestService().active_decision().allowed
        )
        if runtime_decision is not None and not getattr(
            runtime_decision,
            "allow_decision_engine",
            True,
        ) and not controlled_test_active:
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
            safe_message = self._safe_exception_message(error)
            logger.warning(
                "event=conversation_sales_session_unavailable error_type=%s "
                "error_message=%s boundary=%s correlation_id=%s",
                type(error).__name__, safe_message,
                "ConversationGateway.active_sales_session_lookup",
                gateway_input.correlation_id,
            )
            return self._error_output(
                correlation_id=gateway_input.correlation_id,
                error_code="canonical_sales_session_unavailable",
                status="commerce_context_unavailable",
                extra_diagnostics={
                    "salesSessionError": {
                        "exceptionClass": type(error).__name__,
                        "message": safe_message,
                        "boundary": "ConversationGateway.active_sales_session_lookup",
                        "scenarioIdentity": (
                            gateway_input.brain_context.customer_identifier
                            if gateway_input.brain_context is not None
                            and gateway_input.brain_context.developer_mode
                            else "REDACTED_NON_DEVELOPER_CONTEXT"
                        ),
                    },
                },
            )
        customer_sales_decision = self._evaluate_customer_sales_brain(
            gateway_input, sales_session=sales_session,
        )
        if customer_sales_decision is not None:
            metadata = dict(customer_sales_decision.decision_metadata or {})
            deferred = dict(metadata.get("deferredContinuation") or {})
            invalidator = getattr(
                self._customer_sales_brain_service,
                "invalidate_deferred_continuation", None,
            )
            if (
                callable(invalidator)
                and deferred.get("state") in {
                    "PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"
                }
                and (
                    sales_session is not None
                    or customer_sales_decision.decision
                    is CustomerSalesDecisionType.BACK_OFF
                    or customer_sales_decision.reason_code
                    is CustomerSalesReasonCode.CUSTOMER_INTERACTION_SAFETY_BLOCKED
                )
            ):
                if sales_session is not None:
                    invalidation_reason = "ACTIVE_SESSION_PRECEDENCE"
                elif (
                    customer_sales_decision.reason_code
                    is CustomerSalesReasonCode.CUSTOMER_INTERACTION_SAFETY_BLOCKED
                ):
                    invalidation_reason = "CUSTOMER_INTERACTION_SAFETY_BLOCKED"
                else:
                    invalidation_reason = "BACK_OFF"
                invalidator(
                    customer_sales_decision,
                    reason=invalidation_reason,
                )
        suppression = dict(
            dict(getattr(customer_sales_decision, "decision_metadata", {}) or {}).get(
                "outboundSuppression"
            ) or {}
        )
        if suppression.get("suppressed") is True:
            diagnostics = self._customer_sales_diagnostics(
                customer_sales_decision
            )
            diagnostics.update({
                "status": "suppressed",
                "outbound_decision": "NO_RESPONSE",
                "outbound_suppression": suppression,
                "ai_generation_count": 0,
                "inbound_processed": True,
                "inbound_audit_preserved": True,
            })
            self._record_sales_progression(
                sales_session, customer_sales_decision,
                correlation_id=gateway_input.correlation_id,
            )
            from app.services.sales_brain_full_analysis_service import (
                SalesBrainFullAnalysisService,
            )
            diagnostics["commercial_summary"] = (
                SalesBrainFullAnalysisService.project(
                    customer_sales_decision,
                    runtime_diagnostics=diagnostics,
                    customer_message=gateway_input.message_text,
                )
            )
            self._record_live_turn(has_offer=False, has_delivery=False)
            return ConversationGatewayOutput(
                correlation_id=gateway_input.correlation_id,
                response_text="",
                offer_authorized=False,
                offer_link=None,
                blocked=True,
                error_code=str(
                    suppression.get("reason") or "authoritative_reply_suppression"
                ).lower(),
                delivery_type=None,
                delivery_mode=None,
                delivery_requires_payment=False,
                delivery_payload={},
                diagnostic_metadata=diagnostics,
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
        brain_context = self._brain_context(gateway_input)
        if customer_sales_decision is not None:
            from app.services.customer_sales_brain_service import CustomerSalesBrainService
            engine_runtime_injection["proactive_progression_preflight"] = (
                CustomerSalesBrainService.proactive_progression_preflight(
                    customer_sales_decision,
                    recent_history_turn_count=len(tuple(gateway_input.chat_history or ())[-8:]),
                )
            )
        persona_projection = None
        if (brain_context.fanvue_account_id is not None
                and self._ava_persona_runtime_service is not None):
            persona_projection = self._ava_persona_runtime_service.build(
                fanvue_account_id=brain_context.fanvue_account_id,
                topic=gateway_input.message_text,
            )
            engine_runtime_injection["ava_persona_runtime_projection"] = (
                persona_projection
            )
        if brain_context.conversational_memory:
            engine_runtime_injection["conversational_memory"] = dict(
                brain_context.conversational_memory
            )
        from app.services.ava_temporal_context_service import AvaTemporalContextService
        engine_runtime_injection["time_context"] = AvaTemporalContextService().build(
            customer_timezone=brain_context.conversational_memory.get("timezone"),
        )
        sleep_context = dict(brain_context.sleep_context or {})
        if sleep_context:
            from app.services.ava_sleep_service import AvaSleepService
            override, override_reason = AvaSleepService.commercial_override(
                customer_sales_decision
            )
            sleep_context.update({
                "commercialOverrideActive": override,
                "overrideReason": override_reason,
            })
            if override:
                sleep_context.update({
                    "state": "OVERRIDE_HOT_COMMERCIAL",
                    "signoffRequired": False,
                    "signoffPending": False,
                    "responseDeferredDueToSleep": False,
                    "transitionReason": "STRONG_COMMERCIAL_MOMENTUM",
                })
            engine_runtime_injection["sleep_context"] = sleep_context
        if commerce_mode is not CommerceMode.LIVE and not controlled_test_active:
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
            and customer_sales_decision.decision in {
                CustomerSalesDecisionType.PRESENT_OFFER,
                CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
                CustomerSalesDecisionType.UPSELL,
                CustomerSalesDecisionType.CROSS_SELL,
            }
            and not controlled_test_active
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
        # The Customer Sales Brain decision was finalized before generation.
        # DecisionEngine may still report useful wording/readiness observations,
        # but those observations must never replace the commercial strategy.
        ai_commerce_readiness_observation = dict(
            engine_result.get("commerce_readiness") or {}
        )
        if ai_commerce_readiness_observation:
            ai_commerce_readiness_observation.update({
                "authority": "NON_AUTHORITATIVE_AI_OBSERVATION",
                "observedAfterFinalStrategy": True,
                "alteredFinalCommercialStrategy": False,
            })
        would_have_sold = bool(
            customer_sales_decision is not None
            and customer_sales_decision.sell_allowed
            and customer_sales_decision.recommended_offering_id is not None
        )
        relationship_suppressed = bool(
            commerce_mode is CommerceMode.RELATIONSHIP and would_have_sold
            and not controlled_test_active
        )
        commerce_offer_allowed = (
            (
                customer_sales_decision.sell_allowed
                or customer_sales_decision.nudge_allowed
            )
            and not commerce_runtime_injection.get(
                "authoritative_selection_missing", False
            )
            if customer_sales_decision is not None
            else self._customer_sales_brain_service is None
        )
        if commerce_mode is not CommerceMode.LIVE and not controlled_test_active:
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
        if persona_projection is not None:
            diagnostics["avaPersonaRuntime"] = persona_projection.diagnostics()
        diagnostics["time_context"] = dict(engine_runtime_injection["time_context"])
        if engine_runtime_injection.get("sleep_context"):
            diagnostics["sleep_context"] = dict(
                engine_runtime_injection["sleep_context"]
            )
        conversational = dict(brain_context.conversational_memory or {})
        memory_diagnostics = dict(conversational.get("memoryDiagnostics") or {})
        diagnostics["conversational_memory"] = {
            "retrievalAttempted": memory_diagnostics.get("retrievalAttempted", False),
            "identitySource": memory_diagnostics.get("identitySource"),
            "available": memory_diagnostics.get("available", False),
            "relevantMemoriesFound": bool(
                memory_diagnostics.get("retrievedCount", 0)
            ),
            "retrievedCount": memory_diagnostics.get("retrievedCount", 0),
            "retrievedKeys": list(memory_diagnostics.get("retrievedKeys") or ()),
            "retrievedCategories": list(
                memory_diagnostics.get("retrievedCategories") or ()
            ),
            "semanticClassificationAttempted": memory_diagnostics.get(
                "semanticClassificationAttempted", False
            ),
            "semanticDomains": list(memory_diagnostics.get("semanticDomains") or ()),
            "semanticClassificationConfidence": memory_diagnostics.get(
                "semanticClassificationConfidence", 0.0
            ),
            "semanticClassificationSource": memory_diagnostics.get(
                "semanticClassificationSource"
            ),
            "explicitRecallRequest": memory_diagnostics.get(
                "explicitRecallRequest", False
            ),
            "explicitMemoryReference": memory_diagnostics.get(
                "explicitMemoryReference", False
            ),
            "recallSatisfied": memory_diagnostics.get("recallSatisfied"),
            "extractedThisTurn": memory_diagnostics.get("extractedThisTurn", 0),
            "persistedThisTurn": memory_diagnostics.get("persistedThisTurn", 0),
            "correctionsApplied": memory_diagnostics.get("correctionsApplied", 0),
            "eventsExtractedThisTurn": list(
                memory_diagnostics.get("eventsExtractedThisTurn") or ()
            ),
            "eventPersistence": dict(
                memory_diagnostics.get("eventPersistence") or {}
            ),
            "customerSelfDisclosure": dict(
                memory_diagnostics.get("customerSelfDisclosure") or {}
            ),
            "generationCompliance": dict(
                memory_diagnostics.get("generationCompliance") or {}
            ),
            "temporalEventRecall": dict(
                memory_diagnostics.get("temporalEventRecall") or {}
            ),
            "continuityGuidance": dict(
                memory_diagnostics.get("continuityGuidance") or {}
            ),
            "memoryPriorityOperational": bool(
                memory_diagnostics.get("memoryPriorityOperational")
            ),
            "memoryPriority": memory_diagnostics.get("memoryPriority"),
            "operationalMemoryPolicy": dict(
                memory_diagnostics.get("operationalMemoryPolicy") or {}
            ),
            "memoryCandidates": list(
                memory_diagnostics.get("memoryCandidates") or ()
            ),
            "conversationStyle": dict(
                memory_diagnostics.get("conversationStyle") or {}
            ),
            "locationTimezoneInference": memory_diagnostics.get(
                "locationTimezoneInference"
            ),
            "persistenceSource": memory_diagnostics.get("persistenceSource"),
            "retrievalSource": memory_diagnostics.get("retrievalSource"),
            "injectedIntoGeneration": bool(
                engine_runtime_injection.get("conversational_memory")
            ),
            "commerceMemorySource": diagnostics.get("memory_source"),
            "separateFromCommerceMemory": True,
        }
        diagnostics["conversationStyle"] = dict(
            memory_diagnostics.get("conversationStyle") or {}
        )
        diagnostics["invalid_memory_capture_rejected"] = bool(
            memory_diagnostics.get("invalidMemoryCaptureRejected")
        )
        if commerce_runtime_injection.get("offering_copy_diagnostics"):
            diagnostics["offering_copy_diagnostics"] = dict(
                commerce_runtime_injection["offering_copy_diagnostics"]
            )
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
        diagnostics["commercial_strategy_authority"] = {
            "owner": "CustomerSalesBrainService",
            "finalizedBeforeGeneration": True,
            "aiRole": "WORDING_AND_NON_AUTHORITATIVE_OBSERVATION",
            "aiAlteredFinalCommercialStrategy": False,
            "finalDecision": (
                customer_sales_decision.decision.value
                if customer_sales_decision is not None else None
            ),
            "reasonCode": (
                customer_sales_decision.reason_code.value
                if customer_sales_decision is not None else None
            ),
        }
        diagnostics["ai_commerce_readiness_observation"] = (
            ai_commerce_readiness_observation or {
                "authority": "NON_AUTHORITATIVE_AI_OBSERVATION",
                "status": "NOT_PROVIDED",
                "alteredFinalCommercialStrategy": False,
            }
        )
        diagnostics["engine_offer_requested"] = engine_offer_requested
        diagnostics["legacy_offer_requested"] = legacy_offer_requested
        diagnostics["commerce_offer_allowed"] = commerce_offer_allowed
        diagnostics["commerce_offer_authorized"] = commerce_offer_allowed
        diagnostics["offer_authorized"] = offer_authorized
        diagnostics["final_offer_authorized"] = offer_authorized
        diagnostics.update({
            "configured_commerce_mode": commerce_mode.value,
            "controlled_test_commerce_override": controlled_test_active,
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
        ava_presentation_text = commerce.get(
            "ava_presentation_text", response_text
        )
        diagnostics.update(commerce["diagnostics"])
        offering = commerce.get("offering")
        lifecycle_context = dict(
            (commerce_runtime_injection.get("commerce_decision") or {}).get("offer_lifecycle") or {}
        )
        if (
            not blocked
            and customer_sales_decision is not None
            and customer_sales_decision.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE
        ):
            original_acknowledgement = ava_presentation_text
            lifecycle_validation = self._content_presentation_validator.validate_lifecycle(
                original_acknowledgement, lifecycle=lifecycle_context,
                require_purchase_acknowledgement=True,
            )
            rewrite_attempted = False
            rewrite_outcome = "NOT_REQUIRED"
            if (
                not lifecycle_validation.valid
                and callable(self._purchase_acknowledgement_copy_generator)
            ):
                rewrite_attempted = True
                try:
                    repaired = self._purchase_acknowledgement_copy_generator(
                        user_message=gateway_input.message_text,
                        draft=original_acknowledgement,
                        lifecycle=lifecycle_context,
                    )
                    repaired_validation = self._content_presentation_validator.validate_lifecycle(
                        repaired, lifecycle=lifecycle_context,
                        require_purchase_acknowledgement=True,
                    )
                    if repaired_validation.valid:
                        response_text = ava_presentation_text = repaired
                        lifecycle_validation = repaired_validation
                        rewrite_outcome = "PROVIDER_REPAIR_SUCCEEDED"
                    else:
                        rewrite_outcome = "PROVIDER_REPAIR_REJECTED_SAFE_FALLBACK"
                except Exception:
                    logger.exception(
                        "event=purchase_acknowledgement_repair_failed correlation_id=%s",
                        gateway_input.correlation_id,
                    )
                    rewrite_outcome = "PROVIDER_REPAIR_ERROR_SAFE_FALLBACK"
            if not lifecycle_validation.valid:
                fallback = "I saw you grabbed it — hope you enjoy this one."
                fallback_validation = self._content_presentation_validator.validate_lifecycle(
                    fallback, lifecycle=lifecycle_context,
                    require_purchase_acknowledgement=True,
                )
                if fallback_validation.valid:
                    response_text = ava_presentation_text = fallback
                    lifecycle_validation = fallback_validation
                    if not rewrite_attempted:
                        rewrite_outcome = "SAFE_ACKNOWLEDGEMENT_FALLBACK"
            diagnostics.update({
                "purchaseAcknowledgementRequired": True,
                "purchaseAcknowledgementSatisfied": lifecycle_validation.valid,
                "purchaseAcknowledgementEvidence": (
                    ["FINAL_MESSAGE_ACKNOWLEDGES_COMPLETED_PURCHASE"]
                    if lifecycle_validation.valid else []
                ),
                "purchaseAcknowledgementValidationAttempted": True,
                "purchaseAcknowledgementRewriteAttempted": rewrite_attempted,
                "purchaseAcknowledgementRewriteOutcome": rewrite_outcome,
                "purchaseAcknowledgementOriginalCandidate": original_acknowledgement,
                "purchaseAcknowledgementFinalCandidate": ava_presentation_text,
                "purchase_acknowledgement_validated": lifecycle_validation.valid,
            })
            if not lifecycle_validation.valid:
                blocked = True
                error_code = lifecycle_validation.reason
                response_text = ""
                diagnostics.update({"status": "blocked", "lifecycle_presentation_block_reason": lifecycle_validation.reason})
        if not blocked and offer_authorized and offering is not None:
            presentation = self._content_presentation_validator.validate_paid(
                ava_presentation_text,
                offering=offering,
                presentation_context={
                    "price_neutral": True,
                    "bundle": dict(
                        (commerce_runtime_injection.get("commerce_decision") or {}).get(
                            "bundle_conversation"
                        ) or {}
                    ),
                    "session": dict(
                        (commerce_runtime_injection.get("commerce_decision") or {}).get(
                            "session_conversation"
                        ) or {}
                    ),
                    "lifecycle": dict(
                        (commerce_runtime_injection.get("commerce_decision") or {}).get(
                            "offer_lifecycle"
                        ) or {}
                    ),
                },
            )
            diagnostics["paid_presentation_validated"] = presentation.valid
            diagnostics["presentation_copy_valid"] = presentation.valid
            diagnostics["presentation_copy_failure_reason"] = presentation.reason
            diagnostics["commercial_payload_composed"] = True
            diagnostics["actionable_destination_required"] = True
            diagnostics.update({
                "priceRequestDetected": bool(re.search(
                    r"\b(?:how much|what(?:'s| is) the price|what does it cost|price)\b",
                    gateway_input.message_text,
                    re.I,
                )),
                "authoritativeOffering": str(getattr(offering, "offering_id", "") or ""),
                "canonicalInternalPriceMinor": int(offering.price_minor),
                "canonicalInternalCurrency": str(offering.currency),
                "paidPresentationAuthorized": True,
                "paidPresentationDelivered": False,
                "conversationalPriceSuppressed": True,
                "numericPricePresentInAvaProse": (
                    self._content_presentation_validator.numeric_price_present(
                        ava_presentation_text
                    )
                ),
                "purchaseIntent": diagnostics.get("active_purchase_intent"),
                "ctaLinkTruth": {
                    "required": True,
                    "deliveryPayloadPresent": False,
                    "authoritativeDestinationAvailable": bool(offering.delivery_url),
                    "destinationOwnedBy": "DURABLE_STRUCTURED_COMMERCE",
                },
            })
            if not presentation.valid:
                logger.warning(
                    "event=paid_presentation_blocked reason=%s correlation_id=%s",
                    presentation.reason, gateway_input.correlation_id,
                )
                blocked = True
                error_code = presentation.reason
                offer_authorized = False
                response_text = ""
                offering = None
                diagnostics.update({
                    "status": "blocked",
                    "offer_authorized": False,
                    "final_offer_authorized": False,
                    "paid_presentation_block_reason": presentation.reason,
                })
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
                customer_sales_decision=customer_sales_decision,
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
        if diagnostics.get("paidPresentationAuthorized") is True:
            cta_truth = dict(diagnostics.get("ctaLinkTruth") or {})
            cta_truth["deliveryPayloadPresent"] = bool(delivery_payload)
            cta_truth["providerConfirmed"] = False
            diagnostics["ctaLinkTruth"] = cta_truth
        if delivery_payload:
            diagnostics["telegram_delivery_payload_ready"] = True
        if sales_session is not None:
            session_commercial_context = dict(
                getattr(sales_session, "commercial_context", {}) or {}
            )
            diagnostics["active_sales_session"] = {
                "salesSessionId": str(sales_session.sales_session_id),
                "state": getattr(getattr(sales_session, "state", None), "value", None),
                "currentUnlock": session_commercial_context.get("currentUnlock"),
                "nextUnlock": session_commercial_context.get("nextUnlock"),
            }

        customer_sales_decision, progression_delivery = (
            self._finalize_progression_delivery(
                customer_sales_decision,
                response_text=response_text,
                blocked=blocked,
                offer_authorized=offer_authorized,
                style=diagnostics.get("conversationStyle") or {},
            )
        )
        diagnostics.update(progression_delivery)
        diagnostics.update(self._customer_sales_diagnostics(
            customer_sales_decision
        ))
        strategy_authority = dict(
            diagnostics.get("commercial_strategy_authority") or {}
        )
        strategy_authority.update({
            "finalDecision": (
                customer_sales_decision.decision.value
                if customer_sales_decision is not None else None
            ),
            "reasonCode": (
                customer_sales_decision.reason_code.value
                if customer_sales_decision is not None else None
            ),
        })
        diagnostics["commercial_strategy_authority"] = strategy_authority
        # Contact timing is purpose-aware and separate from commercial strategy.
        # Inbound replies remain reactive even when optional proactive contact is
        # cooling down; acknowledgements and Session continuations retain their
        # explicit higher priority.
        from app.models.customer_contact import ContactPurpose
        from app.services.customer_contact_authority_service import CustomerContactAuthorityService
        contact_purpose = ContactPurpose.REACTIVE_CONVERSATION
        if customer_sales_decision is not None:
            contact_decision = customer_sales_decision.decision.value
            if contact_decision == "CONGRATULATE_PURCHASE":
                contact_purpose = ContactPurpose.PURCHASE_ACKNOWLEDGEMENT
            elif contact_decision == "NUDGE_ACTIVE_OFFER":
                contact_purpose = ContactPurpose.ACTIVE_OFFER_FOLLOWUP
            elif diagnostics.get("active_sales_session") or diagnostics.get("sales_session_id"):
                contact_purpose = ContactPurpose.SESSION_CONTINUATION
            elif contact_decision in {"PRESENT_OFFER", "DELIVER_PURCHASE"}:
                contact_purpose = ContactPurpose.REACTIVE_COMMERCIAL
        contact_policy = CustomerContactAuthorityService().decide(
            purpose=contact_purpose,
            evidence={
                "safety_blocked": blocked,
                "active_offer": bool(diagnostics.get("active_purchase_intent")),
                "active_session": bool(diagnostics.get("active_sales_session") or diagnostics.get("sales_session_id")),
                "followup_due": contact_purpose is ContactPurpose.ACTIVE_OFFER_FOLLOWUP,
            },
        )
        diagnostics["customerContactPolicy"] = dict(contact_policy.to_mapping())
        if progression_delivery.get("commercial_tease_delivery_pending_confirmation"):
            diagnostics["pending_sales_progression_context"] = (
                self._pending_progression_scope(
                    brain_context,
                    sales_session=sales_session,
                    correlation_id=gateway_input.correlation_id,
                )
            )
        session_proposal_pending_confirmation = bool(
            customer_sales_decision is not None
            and customer_sales_decision.decision
                is CustomerSalesDecisionType.PROPOSE_SESSION
            and response_text
            and not blocked
        )
        if session_proposal_pending_confirmation:
            proposal_metadata = dict(
                customer_sales_decision.decision_metadata or {}
            )
            diagnostics.update({
                "session_proposal_delivery_pending_confirmation": True,
                "sessionProposalAuthorized": True,
                "sessionProposalDelivered": False,
                "sessionProposalPending": False,
                "pending_session_proposal": dict(
                    proposal_metadata.get("sessionProposalContext") or {}
                ),
                "pending_session_proposal_context": (
                    self._pending_progression_scope(
                        brain_context,
                        sales_session=sales_session,
                        correlation_id=gateway_input.correlation_id,
                    )
                ),
                "scenarioInfluencedCommercialAuthority": False,
            })
        if (not blocked and not progression_delivery.get(
                "commercial_tease_delivery_pending_confirmation")
                and not session_proposal_pending_confirmation):
            self._record_sales_progression(
                sales_session, customer_sales_decision,
                correlation_id=gateway_input.correlation_id,
            )

        from app.services.sales_brain_full_analysis_service import (
            SalesBrainFullAnalysisService,
        )
        diagnostics["commercial_summary"] = (
            SalesBrainFullAnalysisService.project(
                customer_sales_decision,
                runtime_diagnostics=diagnostics,
                customer_message=gateway_input.message_text,
            )
        )

        if runtime_decision is not None:
            diagnostics["runtime_control"] = self._runtime_diagnostics(
                runtime_decision
            )
            if controlled_test_active:
                diagnostics["runtime_control"]["controlled_test_override"] = True

        if runtime_decision is not None and getattr(
            runtime_decision,
            "observe_only",
            False,
        ) and not controlled_test_active:
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

        if not blocked and response_text:
            try:
                context = self._brain_context(gateway_input)
                diagnostics.update(self._conversation_quality_watch_service.observe(
                    response_text=response_text,
                    customer_message=gateway_input.message_text,
                    diagnostics=diagnostics,
                    creator_profile_id=context.creator_profile_id,
                    fanvue_account_id=context.fanvue_account_id,
                    telegram_user_id=context.telegram_user_id,
                    telegram_chat_id=context.telegram_chat_id,
                    correlation_id=gateway_input.correlation_id,
                    buyer_context=diagnostics.get("customer_value_attention") or {},
                    recent_history=gateway_input.chat_history,
                ))
            except Exception:
                logger.exception("[QUALITY WATCH ERROR] observational alert failed")
                diagnostics.update({
                    "conversationQualityWatchTriggered": True,
                    "conversationQualitySeverity": "HIGH",
                    "conversationQualityReasons": ["QUALITY_WATCH_DELIVERY_FAILURE"],
                    "conversationQualityAlertAuthorized": False,
                    "conversationQualityAlertOperationId": None,
                    "conversationQualityAlertConfirmed": False,
                    "conversationQualityAlertFailed": True,
                })

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
        structured_paid_presentation = decision.offering is not None
        presentation_text = response_text
        paid_presentation_context = self._paid_presentation_wording_context(
            gateway_input=gateway_input,
            customer_sales_decision=customer_sales_decision,
            selected_offering=decision.offering,
        )
        repetition_repair_attempted = False
        repetition_repair_outcome = "NOT_REQUIRED"
        wording_source = "ORIGINAL_ENGINE_RESPONSE"
        repetition_risk = {"risk": False, "reason": None, "similarity": 0.0}
        if (
            decision.offering is not None
            and customer_sales_decision is not None
            and customer_sales_decision.decision in {
                CustomerSalesDecisionType.PRESENT_OFFER,
                CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
                CustomerSalesDecisionType.UPSELL,
                CustomerSalesDecisionType.CROSS_SELL,
                CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
            }
            and callable(self._commercial_presentation_copy_generator)
        ):
            presentation_text = self._commercial_presentation_copy_generator(
                user_message=gateway_input.message_text,
                draft=response_text,
                offering=decision.offering,
                price_neutral=True,
                presentation_purpose=paid_presentation_context["purpose"],
                same_offer_as_previous_presentation=paid_presentation_context[
                    "sameOfferAsPreviousPresentation"
                ],
                continuation_intent_type=paid_presentation_context[
                    "continuationIntentType"
                ],
                recent_paid_presentation_wording=paid_presentation_context[
                    "recentPaidPresentationWording"
                ],
            )
            presentation_text, authority_repair = (
                self._preserve_paid_presentation_authority(
                    presentation_text,
                    offering=decision.offering,
                    price_neutral=True,
                    presentation_purpose=paid_presentation_context["purpose"],
                )
            )
            wording_source = (
                "PURPOSE_AWARE_SAFE_FALLBACK"
                if authority_repair else "PROVIDER_GENERATED"
            )
            repetition_risk = self._paid_presentation_repetition_risk(
                presentation_text,
                paid_presentation_context["recentPaidPresentationWording"],
                paid_presentation_context["purpose"],
            )
            if repetition_risk["risk"]:
                repetition_repair_attempted = True
                try:
                    repaired_text = self._commercial_presentation_copy_generator(
                        user_message=gateway_input.message_text,
                        draft=presentation_text,
                        offering=decision.offering,
                        price_neutral=True,
                        presentation_purpose=paid_presentation_context["purpose"],
                        same_offer_as_previous_presentation=paid_presentation_context[
                            "sameOfferAsPreviousPresentation"
                        ],
                        continuation_intent_type=paid_presentation_context[
                            "continuationIntentType"
                        ],
                        recent_paid_presentation_wording=paid_presentation_context[
                            "recentPaidPresentationWording"
                        ],
                        repetition_repair=True,
                    )
                    repaired_text, repaired_authority = (
                        self._preserve_paid_presentation_authority(
                            repaired_text,
                            offering=decision.offering,
                            price_neutral=True,
                            presentation_purpose=paid_presentation_context["purpose"],
                        )
                    )
                    repaired_risk = self._paid_presentation_repetition_risk(
                        repaired_text,
                        paid_presentation_context["recentPaidPresentationWording"],
                        paid_presentation_context["purpose"],
                    )
                    if repaired_risk["risk"]:
                        presentation_text = self._purpose_aware_paid_fallback(
                            paid_presentation_context["purpose"], decision.offering,
                        )
                        authority_repair = {
                            "applied": True,
                            "reason": "PAID_PRESENTATION_REPETITION",
                            "authority": "STRUCTURED_SELECTED_OFFERING",
                        }
                        wording_source = "PURPOSE_AWARE_SAFE_FALLBACK"
                        repetition_repair_outcome = "SAFE_FALLBACK"
                    else:
                        presentation_text = repaired_text
                        authority_repair = repaired_authority
                        wording_source = (
                            "PURPOSE_AWARE_SAFE_FALLBACK"
                            if repaired_authority else "PROVIDER_REPETITION_REPAIR"
                        )
                        repetition_repair_outcome = "SUCCEEDED"
                except Exception:
                    logger.exception(
                        "event=paid_presentation_repetition_repair_failed correlation_id=%s",
                        gateway_input.correlation_id,
                    )
                    presentation_text = self._purpose_aware_paid_fallback(
                        paid_presentation_context["purpose"], decision.offering,
                    )
                    authority_repair = {
                        "applied": True,
                        "reason": "PAID_PRESENTATION_REPETITION_REPAIR_ERROR",
                        "authority": "STRUCTURED_SELECTED_OFFERING",
                    }
                    wording_source = "PURPOSE_AWARE_SAFE_FALLBACK"
                    repetition_repair_outcome = "SAFE_FALLBACK_AFTER_ERROR"
            else:
                repetition_repair_outcome = "NOT_NEEDED"
        else:
            authority_repair = None
        composed = service.compose_reply(
            presentation_text,
            decision,
            price_neutral=True,
        )
        commerce_diagnostics = dict(decision.diagnostics())
        commerce_diagnostics["commerce_composed"] = decision.offering is not None
        commerce_diagnostics["structured_paid_presentation"] = structured_paid_presentation
        commerce_diagnostics["conversational_price_suppressed"] = structured_paid_presentation
        commerce_diagnostics["developer_mode"] = context.developer_mode
        commerce_diagnostics["presentation_copy_generation"] = (
            "AUTHORITATIVE_PRESENT_OFFER_REGENERATION"
            if presentation_text != response_text else "ORIGINAL_ENGINE_RESPONSE"
        )
        commerce_diagnostics["presentation_authority_repair"] = authority_repair
        commerce_diagnostics.update({
            "paidPresentationPurpose": paid_presentation_context["purpose"],
            "sameOfferAsPreviousPresentation": paid_presentation_context[
                "sameOfferAsPreviousPresentation"
            ],
            "customerInitiatedOfferContinuation": paid_presentation_context[
                "customerInitiatedOfferContinuation"
            ],
            "continuationIntentType": paid_presentation_context[
                "continuationIntentType"
            ],
            "recentPaidPresentationWording": paid_presentation_context[
                "recentPaidPresentationWording"
            ],
            "paidPresentationRepetitionRisk": repetition_risk,
            "paidPresentationWordingSource": wording_source,
            "repetitionRepairAttempted": repetition_repair_attempted,
            "repetitionRepairOutcome": repetition_repair_outcome,
        })
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
            "ava_presentation_text": presentation_text,
            "diagnostics": commerce_diagnostics,
            "offering": decision.offering,
        }

    def _preserve_paid_presentation_authority(
        self, presentation_text: str, *, offering, price_neutral: bool,
        presentation_purpose: str = "INITIAL_OFFER",
    ) -> tuple[str, dict[str, Any] | None]:
        """Repair only missing offer semantics; unsafe claims still fail closed.

        The backend's selected offering remains authoritative. Language generation
        may style the caption, but an empty, vague, deferred, or overlong draft
        cannot demote an authorized PRESENT_OFFER back into another tease.
        """
        validation = self._content_presentation_validator.validate_paid(
            presentation_text,
            offering=offering,
            presentation_context={"price_neutral": price_neutral},
        )
        recoverable = {
            "PAID_PRESENTATION_EMPTY",
            "PAID_PRESENTATION_UNUSABLE",
            "PAID_PRESENTATION_NOT_AN_OFFER",
            "PAID_PRESENTATION_DEFERRED",
            "PAID_PRESENTATION_NOT_CONCISE",
            "PAID_PRESENTATION_CONVERSATIONAL_PRICE",
            "PAID_PRESENTATION_CONTRADICTORY_PRICE",
        }
        if validation.valid or validation.reason not in recoverable:
            return presentation_text, None
        replacement = self._purpose_aware_paid_fallback(
            presentation_purpose, offering,
        )
        return replacement, {
            "applied": True,
            "reason": validation.reason,
            "authority": "STRUCTURED_SELECTED_OFFERING",
        }

    @staticmethod
    def _purpose_aware_paid_fallback(purpose: str, offering) -> str:
        """Return concise price-neutral copy; structured commerce stays authoritative."""
        normalized = str(purpose or "INITIAL_OFFER").upper()
        if normalized == "PRICE_REQUEST_CONTINUATION":
            return "You can check it on the offer right here — unlock it whenever you want."
        if normalized == "SEND_OR_LINK_CONTINUATION":
            return "Here you go — the Unlock button has the link for this one."
        if normalized == "BUYER_INITIATED_NEXT_OFFER":
            return "Here's another one you might like — unlock it whenever you want."
        if normalized == "ALTERNATIVE_OFFER":
            return "Here's another option for you — unlock it whenever you want."
        if normalized == "UPSELL":
            return "Here's an upgraded option for you — unlock it whenever you want."
        if normalized == "CROSS_SELL":
            return "Here's another option that fits — unlock it whenever you want."
        if normalized == "SESSION_PAID_STEP":
            return "Here's the next part for you — unlock it whenever you want."
        offering_type = str(getattr(offering, "offering_type", "") or "").upper()
        if "BUNDLE" in offering_type:
            return "Here's this set for you — unlock it whenever you want."
        return "Here you go — unlock it whenever you want."

    @classmethod
    def _paid_presentation_repetition_risk(
        cls, candidate: str, recent_wording: Sequence[str], purpose: str,
    ) -> dict[str, Any]:
        normalized = cls._normalize_paid_wording(candidate)
        similarities = [
            SequenceMatcher(None, normalized, cls._normalize_paid_wording(prior)).ratio()
            for prior in tuple(recent_wording or ())[-4:]
            if cls._normalize_paid_wording(prior)
        ]
        similarity = max(similarities, default=0.0)
        risk = bool(normalized and similarity >= 0.90)
        return {
            "risk": risk,
            "reason": "EXACT_OR_NEAR_RECENT_PAID_PRESENTATION" if risk else None,
            "similarity": round(similarity, 4),
            "purpose": str(purpose or "INITIAL_OFFER"),
        }

    @staticmethod
    def _normalize_paid_wording(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(value or "").lower()))

    def _paid_presentation_wording_context(
        self, *, gateway_input: ConversationGatewayInput,
        customer_sales_decision: CustomerSalesDecision | None,
        selected_offering,
    ) -> dict[str, Any]:
        decision = customer_sales_decision
        metadata = dict(getattr(decision, "decision_metadata", None) or {})
        continuation = dict(metadata.get("activeOfferContinuation") or {})
        continuation_type = continuation.get("continuationIntentType")
        same_offer = bool(
            selected_offering is not None
            and getattr(decision, "active_offering_id", None) is not None
            and str(getattr(selected_offering, "offering_id", ""))
            == str(decision.active_offering_id)
        )
        purpose = "INITIAL_OFFER"
        if continuation_type == "PRICE_REQUEST":
            purpose = "PRICE_REQUEST_CONTINUATION"
        elif continuation_type == "SEND_OR_LINK_REQUEST":
            purpose = "SEND_OR_LINK_CONTINUATION"
        elif decision is not None and decision.next_sales_action is not None:
            purpose = "SESSION_PAID_STEP"
        elif (
            decision is not None
            and decision.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
        ):
            purpose = "ALTERNATIVE_OFFER"
        elif decision is not None and decision.decision is CustomerSalesDecisionType.UPSELL:
            purpose = "UPSELL"
        elif decision is not None and decision.decision is CustomerSalesDecisionType.CROSS_SELL:
            purpose = "CROSS_SELL"
        elif (
            decision is not None
            and decision.buyer_stage.value != "PROSPECT"
            and decision.active_offer_conversion_state == "PURCHASED"
        ):
            purpose = "BUYER_INITIATED_NEXT_OFFER"
        recent = tuple(
            str(item.get("content") or "").strip()
            for item in tuple(gateway_input.chat_history or ())[-10:]
            if isinstance(item, Mapping)
            and str(item.get("role") or "").lower() == "assistant"
            and str(item.get("content") or "").strip()
        )[-4:]
        return {
            "purpose": purpose,
            "sameOfferAsPreviousPresentation": same_offer,
            "customerInitiatedOfferContinuation": bool(
                continuation.get("customerInitiatedOfferContinuation")
            ),
            "continuationIntentType": continuation_type,
            "recentPaidPresentationWording": list(recent),
        }

    def _authoritative_delivery(
        self, *, response_text: str, offering,
        customer_sales_decision: CustomerSalesDecision | None = None,
    ):
        teaser = self._free_teaser_delivery(customer_sales_decision)
        if teaser is not None:
            metadata_key = (
                "bundle_teaser_delivery"
                if teaser.get("sales_role") == "BUNDLE_PROMOTIONAL_TEASER"
                else "free_teaser_delivery"
            )
            bundle_presentation = (
                teaser.get("sales_role") == "BUNDLE_PROMOTIONAL_TEASER"
                and offering is not None
            )
            offering_metadata = ({
                "publication_id": str(offering.publication_id),
                "provider": offering.provider,
                "provider_resource_id": offering.provider_resource_id,
                "price_minor": offering.price_minor,
                "currency": offering.currency,
            } if bundle_presentation else {})
            return (
                offering.delivery_url if bundle_presentation else None,
                offering.offering_type if bundle_presentation else "FREE",
                "provider_link" if bundle_presentation else "asset",
                bundle_presentation,
                {
                    "delivery_type": (
                        offering.offering_type if bundle_presentation else "FREE"
                    ),
                    "message_text": response_text,
                    "asset_path": teaser["asset_path"],
                    **({
                        "media_link": offering.delivery_url,
                        "product_reference": str(offering.offering_id),
                    } if bundle_presentation else {}),
                    "experience_reference": teaser["photoshoot_session_id"],
                    "delivery_method": "free_asset",
                    "delivery_reason": (
                        "canonical_bundle_complete_presentation"
                        if bundle_presentation
                        else "canonical_photoshoot_free_teaser"
                    ),
                    "next_suggested_action": (
                        "await_purchase_or_continue_conversation"
                        if bundle_presentation else "deliver_free_asset"
                    ),
                    "metadata": {
                        "commerce_mode": "AUTHORITATIVE",
                        metadata_key: teaser,
                        "bundle_complete_presentation": bundle_presentation,
                        **offering_metadata,
                    },
                },
            )
        if offering is None:
            lifecycle = dict(dict(getattr(customer_sales_decision, "decision_metadata", None) or {}).get("offerLifecycle") or {})
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
                    "metadata": {"commerce_mode": "AUTHORITATIVE", "message_purpose": lifecycle.get("messagePurpose"), "purchase_kind": lifecycle.get("purchaseKind"), "purchase_intent_id": lifecycle.get("purchaseIntentId"), "session_id": lifecycle.get("sessionId"), "session_step": lifecycle.get("sessionStep"), "session_role": lifecycle.get("sessionRole")},
                },
            )
        if (
            customer_sales_decision is not None
            and customer_sales_decision.identity_resolved is False
        ):
            # The provider URL and configured base price remain internal until
            # TelegramPurchaseIntentService replaces this pending payload with
            # the durable Creator-OS Unlock gateway URL before delivery.
            return (
                None,
                offering.offering_type,
                "unlock_gateway",
                True,
                {
                    "delivery_type": offering.offering_type,
                    "message_text": response_text,
                    "product_reference": str(offering.offering_id),
                    "delivery_method": "text",
                    "delivery_reason": "unmapped_private_chat_unlock_pending",
                    "metadata": {
                        "commerce_mode": "AUTHORITATIVE",
                        "publication_id": str(offering.publication_id),
                        "provider": offering.provider,
                        "provider_resource_id": offering.provider_resource_id,
                        "price_minor": offering.price_minor,
                        "currency": offering.currency,
                        "customer_facing_price_status": (
                            "ESTABLISHED_BY_UNLOCK_FLOW"
                        ),
                    },
                },
            )
        session_delivery_metadata = {}
        lifecycle = dict(dict(getattr(customer_sales_decision, "decision_metadata", None) or {}).get("offerLifecycle") or {})
        if customer_sales_decision is not None and customer_sales_decision.next_sales_action is not None:
            action_context = customer_sales_decision.next_sales_action.to_context()
            session_runtime = dict(
                (action_context.get("metadata") or {}).get("sessionRuntime") or {}
            )
            session_delivery_metadata = {
                "session_step": action_context.get("current_position"),
                "session_role": session_runtime.get("currentSalesRole"),
                "session_id": action_context.get("sales_session_id"),
                "session_asset_id": action_context.get("selected_asset_id"),
            }
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
                    **session_delivery_metadata,
                    "message_purpose": lifecycle.get("messagePurpose"),
                    "purchase_kind": lifecycle.get("purchaseKind"),
                },
            },
        )

    def _free_teaser_delivery(
        self, decision: CustomerSalesDecision | None,
    ) -> dict[str, Any] | None:
        bundle = dict(getattr(decision, "bundle_sales_context", None) or {})
        if (
            bundle.get("eligible") is True
            and bundle.get("presentationPhase") == "COMPLETE_PRESENTATION"
        ):
            teaser = dict(bundle.get("promotionalTeaser") or {})
            delivery = dict(bundle.get("_delivery") or {})
            if all((bundle.get("lifecycleId"), teaser.get("assetId"),
                    delivery.get("teaserAssetPath"))):
                return {
                    "lifecycle_id": str(bundle["lifecycleId"]),
                    "photoshoot_session_id": str(
                        (bundle.get("photoshoot") or {}).get(
                            "photoshootSessionId"
                        )
                    ),
                    "asset_id": int(teaser["assetId"]),
                    "source_asset_id": int(teaser["sourceAssetId"]),
                    "sales_role": "BUNDLE_PROMOTIONAL_TEASER",
                    "asset_path": str(delivery["teaserAssetPath"]),
                    "asset_path_source": "canonical_bundle_teaser",
                }
        action = getattr(decision, "next_sales_action", None)
        runtime = dict((getattr(action, "metadata", {}) or {}).get("sessionRuntime") or {})
        asset_id = runtime.get("currentAssetId")
        if (
            action is None
            or str(runtime.get("currentSalesRole") or "") != "FREE_TEASER"
            or action.action.value != "CONTINUE_PHOTOSHOOT"
            or asset_id is None
            or int(action.selected_asset_id or 0) != int(asset_id)
            or not runtime.get("lifecycleId")
        ):
            return None
        try:
            asset = self._asset_repository.get_by_id(int(asset_id))
            resolved = self._runtime_media_resolver.resolve_original(
                asset, require_exists=True,
            )
        except Exception as error:
            logger.warning(
                "event=free_teaser_asset_resolution_failed asset_id=%s error_type=%s",
                asset_id, type(error).__name__,
            )
            return None
        if asset is None or resolved.path is None:
            logger.warning(
                "event=free_teaser_asset_unavailable asset_id=%s", asset_id,
            )
            return None
        return {
            "lifecycle_id": str(runtime["lifecycleId"]),
            "photoshoot_session_id": str(runtime.get("photoshootSessionId") or action.current_photoshoot_id),
            "asset_id": int(asset_id),
            "sales_role": "FREE_TEASER",
            "asset_path": str(resolved.path),
            "asset_path_source": resolved.source,
        }

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
                telegram_chat_id=supplied.telegram_chat_id,
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
                conversational_memory=dict(supplied.conversational_memory),
                sleep_context=dict(supplied.sleep_context),
                customer_behavior_evidence=dict(
                    supplied.customer_behavior_evidence
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
            # Durable behavior evidence is advisory.  Current-turn identity and
            # text must be applied after it so a persisted ``latest_message``
            # can never replace the inbound currently being evaluated.
            **dict(context.customer_behavior_evidence or {}),
            "purchase_acknowledgement_pending": (
                context.purchase_acknowledgement_pending
            ),
            "latest_message": gateway_input.message_text,
            "known_memory_domains": tuple(
                context.conversational_memory.get("knownMemoryDomains") or ()
            ),
            "known_memory_keys": tuple(
                context.conversational_memory.get("knownMemoryKeys") or ()
            ),
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
        assistant_turns = tuple(
            str(item.get("content") or "")
            for item in tuple(gateway_input.chat_history or ())[-8:]
            if isinstance(item, Mapping)
            and str(item.get("role") or "").lower() == "assistant"
            and str(item.get("content") or "").strip()
        )
        question_flags = tuple("?" in value for value in assistant_turns[-4:])
        question_streak = 0
        for flag in reversed(question_flags):
            if not flag:
                break
            question_streak += 1
        decision_context["recent_question_count"] = sum(question_flags)
        decision_context["question_streak"] = question_streak
        decision_context["previous_ava_message"] = (
            assistant_turns[-1] if assistant_turns else None
        )
        decision_context["memory_written_this_turn"] = tuple(
            dict(context.conversational_memory.get("memoryDiagnostics") or {}).get(
                "writtenThisTurn"
            ) or ()
        )
        customer_turns = tuple(
            str(item.get("content") or "")
            for item in tuple(gateway_input.chat_history or ())[-16:]
            if isinstance(item, Mapping)
            and str(item.get("role") or "").lower() == "user"
            and str(item.get("content") or "").strip()
        )
        if gateway_input.message_text and (
            not customer_turns
            or customer_turns[-1].strip() != gateway_input.message_text.strip()
        ):
            customer_turns = (*customer_turns, gateway_input.message_text)
        from app.services.conversational_sales_progression_service import (
            ConversationalSalesProgressionService,
        )
        decision_context["relationship_warming_evidence"] = (
            ConversationalSalesProgressionService.relationship_warming_evidence(
                customer_turns
            )
        )
        decision_context["low_conversational_return_count"] = int(
            decision_context["relationship_warming_evidence"].get(
                "lowConversationalReturnCount"
            ) or 0
        )
        memory_values = dict(context.conversational_memory or {})
        canonical_durable_count = memory_values.get("durableRecordCount")
        memory_records = memory_values.get("records")
        if canonical_durable_count is not None:
            durable_fact_count = max(0, int(canonical_durable_count))
        elif isinstance(memory_records, (list, tuple)):
            durable_fact_count = sum(
                1 for record in memory_records
                if isinstance(record, Mapping)
                and record.get("value") not in (None, "")
            )
        else:
            durable_fact_count = sum(
                1 for key, value in memory_values.items()
                if value not in (None, "", (), [], {})
                and str(key) not in {
                    "schemaVersion", "lastExtraction", "memoryDiagnostics",
                    "historyCount", "retrievalDiagnostics", "generationCompliance",
                    "recentAvaResponses", "retrievedMemories", "durableRecordCount",
                }
            )
        decision_context["durable_conversational_fact_count"] = durable_fact_count
        decision_context["recent_history_turn_count"] = len(customer_turns)
        from app.services.contextual_customer_tone_service import (
            ContextualCustomerToneService,
        )
        decision_context["contextual_customer_tone"] = (
            ContextualCustomerToneService().classify(
                message=gateway_input.message_text,
                recent_transcript=tuple(gateway_input.chat_history or ()),
                relationship_context=dict(context.conversational_memory or {}),
                commerce_context=dict(
                    (context.customer_behavior_evidence or {}).get(
                        "customer_commerce_memory"
                    ) or {}
                ),
            )
        )
        if ControlledAutonomyTestService().active_decision().allowed:
            decision_context["controlled_test_commerce"] = True
        if context.fanvue_account_id is not None:
            decision_context["fanvue_account_id"] = int(context.fanvue_account_id)
        if context.telegram_chat_id is not None:
            decision_context["telegram_chat_id"] = int(context.telegram_chat_id)
        if context.conversation_thread_id is not None:
            decision_context["conversation_thread_id"] = int(context.conversation_thread_id)
        if context.fanvue_user_id is not None:
            decision_context["fanvue_user_id"] = int(context.fanvue_user_id)
        if sales_session is not None:
            decision_context["sales_session_id"] = str(
                sales_session.sales_session_id
            )
            progression = dict(
                getattr(sales_session, "commercial_context", {}) or {}
            ).get("salesProgression")
            if isinstance(progression, Mapping):
                decision_context["sales_progression"] = dict(progression)
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
        from app.services.customer_sales_brain_service import CustomerSalesBrainService
        decision = CustomerSalesBrainService.authorize_deterministic_proactive_tease(
            decision, decision_context,
        )
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
        return service.resolve_active_conversation(
            creator_profile_id=int(context.creator_profile_id),
            fanvue_account_id=int(context.fanvue_account_id),
            fanvue_user_id=int(context.fanvue_user_id),
            telegram_user_id=context.telegram_user_id,
            conversation_thread_id=int(context.conversation_thread_id),
        )

    def _record_sales_progression(
        self, sales_session, decision, *, correlation_id=None,
    ):
        if decision is None:
            return
        proposal_recorder = getattr(
            getattr(self, "_customer_sales_brain_service", None),
            "record_session_proposal", None,
        )
        if sales_session is None and callable(proposal_recorder):
            try:
                proposal_recorder(decision, correlation_id=correlation_id)
            except Exception as error:
                logger.warning(
                    "event=session_proposal_persistence_failed error_type=%s",
                    type(error).__name__,
                )
        progression = dict(
            getattr(decision, "decision_metadata", None) or {}
        ).get(
            "salesProgression"
        )
        if not isinstance(progression, Mapping):
            return
        try:
            if sales_session is not None:
                recorder = getattr(
                    self._sales_session_service,
                    "record_conversational_progression", None,
                )
                if not callable(recorder):
                    return
                recorder(
                    session_id=sales_session.sales_session_id,
                    creator_profile_id=sales_session.creator_profile_id,
                    progression=progression,
                )
            else:
                recorder = getattr(
                    self._customer_sales_brain_service,
                    "record_unmapped_progression", None,
                )
                if not callable(recorder):
                    return
                recorder(decision, correlation_id=correlation_id)
        except Exception as error:
            logger.warning(
                "event=sales_progression_persistence_failed error_type=%s",
                type(error).__name__,
            )

    @staticmethod
    def _pending_progression_scope(
        brain_context, *, sales_session, correlation_id,
    ) -> dict:
        """Capture the already-resolved gateway identity for send confirmation."""
        return {
            "creator_profile_id": brain_context.creator_profile_id,
            "fanvue_account_id": brain_context.fanvue_account_id,
            "telegram_user_id": brain_context.telegram_user_id,
            "sales_session_id": (
                str(sales_session.sales_session_id)
                if sales_session is not None else None
            ),
            "correlation_id": correlation_id,
        }

    @staticmethod
    def _finalize_progression_delivery(
        decision, *, response_text, blocked, offer_authorized, style,
    ):
        if decision is None:
            return decision, {
                "proactive_tease_delivered": False,
                "build_interest_exposure": False,
                "offer_exposure": False,
                "customer_commercial_response": False,
            }
        metadata = dict(decision.decision_metadata or {})
        proactive = dict(metadata.get("proactiveProgression") or {})
        progression = dict(metadata.get("salesProgression") or {})
        proactive_expected = bool(
            proactive.get("proactiveProgressionAuthorized")
            and proactive.get("progressionAction") == "TEASE"
        )
        tease_authorized = decision.decision is CustomerSalesDecisionType.TEASE
        tease_type = str(
            metadata.get("teaseType") or progression.get("teaseType")
            or ("PROACTIVE_RELATIONSHIP" if proactive_expected else "OPPORTUNITY_GROUNDED")
        ) if tease_authorized else None
        style_values = dict(style or {})
        satisfied = bool(
            style_values.get("proactiveTeaseSatisfied")
            if tease_type == "PROACTIVE_RELATIONSHIP"
            else response_text
            and not style_values.get("genericFillerRisk")
            and style_values.get("turnObligationsSatisfied", True)
            and style_values.get("meaningfulContribution", True)
        )
        pending_confirmation = bool(
            tease_authorized and satisfied and response_text and not blocked
        )
        delivered = False
        social_flirtation = bool(
            dict(style or {}).get("socialFlirtationPresent")
            or dict(style or {}).get("socialFlirtationDetected")
            or (
                response_text
                and dict(style or {}).get("meaningfulContributionType")
                == "FLIRT_RECIPROCATION"
            )
        )
        response_class = str(
            proactive.get("customerResponseToPreviousTease") or "NONE"
        )
        pending_progression = dict(progression) if pending_confirmation else None
        if tease_authorized:
            proactive.update({
                "proactiveTeaseExpected": proactive_expected,
                "proactiveTeaseSatisfied": satisfied,
                "proactiveTeaseDelivered": False,
                "awaitingCustomerResponse": False,
            })
            progression.update({
                "phase": str(
                    dict(metadata.get("salesProgressionTransition") or {}).get(
                        "priorPhase"
                    ) or "CONVERSATIONAL"
                ),
                "awaitingCustomerResponse": False,
                "proactiveTeaseDelivered": False,
            })
        metadata["proactiveProgression"] = proactive
        metadata["salesProgression"] = progression
        decision = replace(decision, decision_metadata=immutable_mapping(metadata))
        return decision, {
            "social_flirtation_present": social_flirtation,
            "tease_type": tease_type,
            "commercial_tease_authorized": tease_authorized,
            "commercial_tease_wording_satisfied": satisfied if tease_authorized else None,
            "commercial_tease_delivered": delivered,
            "commercial_tease_exposure_recorded": False,
            "progression_finalized_after_delivery": False,
            "commercial_tease_delivery_pending_confirmation": pending_confirmation,
            "pending_sales_progression": pending_progression,
            "tease_offering": (
                str(getattr(decision, "recommended_offering_id", None) or "") or None
            ),
            "commercial_tease_satisfied": False,
            "proactive_tease_expected": proactive_expected,
            "proactive_tease_satisfied": satisfied if proactive_expected else None,
            "proactive_tease_delivered": delivered,
            "build_interest_exposure": bool(
                not blocked and response_text
                and decision.decision is CustomerSalesDecisionType.BUILD_INTEREST
            ),
            "offer_exposure": bool(not blocked and offer_authorized and response_text),
            "customer_commercial_response": response_class != "NONE",
        }

    def _commerce_runtime_injection(
        self, decision: CustomerSalesDecision | None,
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
        value_attention = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "customerValueAttention"
            ) or {}
        )
        if value_attention:
            context["customer_value_attention"] = value_attention
        commercial_receptiveness = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "commercialReceptiveness"
            ) or {}
        )
        if commercial_receptiveness:
            context["commercial_receptiveness"] = commercial_receptiveness
        active_buying_window = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "activeBuyingWindow"
            ) or {}
        )
        if active_buying_window:
            context["active_buying_window"] = active_buying_window
        contextual_tone = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "contextualCustomerTone"
            ) or {}
        )
        if contextual_tone:
            context["contextual_customer_tone"] = contextual_tone
        objection_recovery = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "objectionRecovery"
            ) or {}
        )
        if objection_recovery:
            context["objection_recovery"] = objection_recovery
        offer_lifecycle = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get("offerLifecycle") or {}
        )
        if offer_lifecycle:
            context["offer_lifecycle"] = offer_lifecycle
        progression = dict(
            getattr(decision, "decision_metadata", None) or {}
        ).get(
            "salesProgression"
        )
        if isinstance(progression, Mapping):
            context["sales_progression"] = dict(progression)
        proactive = dict(
            dict(getattr(decision, "decision_metadata", None) or {}).get(
                "proactiveProgression"
            ) or {}
        )
        if proactive:
            context["proactive_progression"] = proactive
        product_context = dict(
            getattr(decision, "recommended_product_context", None) or {}
        )
        if product_context.get("assetIntelligence"):
            context["single_image_conversation"] = {
                "schemaVersion": "single_image_chat_conversation_v1",
                "assetId": product_context.get("heroAssetId"),
                "canonicalIntelligence": product_context["assetIntelligence"],
                "groundingRules": [
                    "Keep every product-specific visual claim grounded in the supplied canonical intelligence.",
                    "Enticing conversational framing is allowed; inventing absent visual details is not.",
                ],
            }
        session_context_required = False
        session_context_available = False
        if decision.next_sales_action is not None:
            session_context_required = bool(
                decision.next_sales_action.selected_offering_id is not None
            )
            context["next_sales_action"] = decision.next_sales_action.to_context()
            try:
                session_conversation = (
                    self._photoshoot_conversation_context_builder.build(decision)
                )
            except Exception as error:
                session_conversation = None
                logger.warning(
                    "event=photoshoot_session_conversation_context_unavailable "
                    "error_type=%s session_id=%s asset_id=%s fallback=fail_closed",
                    type(error).__name__,
                    decision.next_sales_action.current_photoshoot_id,
                    decision.next_sales_action.selected_asset_id,
                )
            if session_conversation:
                context["session_conversation"] = session_conversation
                session_context_available = True
        bundle_context = dict(decision.bundle_sales_context or {})
        if bundle_context.get("eligible") is True:
            context["bundle_conversation"] = {
                key: value for key, value in bundle_context.items()
                if key != "_delivery"
            }
        if session_context_required and not session_context_available:
            effective_policy = CommerceExecutionPolicy.DISABLED_FOR_TURN
            context["commerce_execution_policy"] = effective_policy.value
            context["grounding_failure"] = (
                "SESSION_CURRENT_SHOT_INTELLIGENCE_UNAVAILABLE"
            )
            context.pop("sales_progression", None)
        customer_safe_copy = self._customer_safe_offering_copy(
            decision.recommended_offering_short_description
        )
        offering_copy_diagnostics = {
            "offeringInternalTitle": decision.recommended_offering_title,
            "offeringCustomerSafeCopyAvailable": bool(customer_safe_copy),
            "internalOfferingMetadataExposedToGeneration": False,
        }
        if (
            effective_policy.value in {
                "COMMERCE_PRESENTATION_ALLOWED",
                "COMMERCE_NUDGE_ALLOWED",
            }
            and (decision.recommended_offering_title or customer_safe_copy)
        ):
            experience = decision.recommended_photoshoot_experience
            if experience is not None:
                context["selected_photoshoot_experience"] = {
                    "photoshoot_id": experience.photoshoot_id,
                    "title": experience.title,
                    "theme": experience.theme,
                    "description": experience.description,
                    "recommendation_explanation": (
                        experience.recommendation_explanation
                    ),
                }
            selected_offering = {
                "customer_safe_description": customer_safe_copy,
                "customer_safe_copy_available": bool(customer_safe_copy),
            }
            if effective_policy is CommerceExecutionPolicy.PRESENTATION_ALLOWED:
                context["paid_presentation_contract"] = {
                    "price_neutral": True,
                    "presentation_complete": True,
                    "customer_facing_price_status": "STRUCTURED_PAID_PRESENTATION",
                    "conversational_price_suppressed": True,
                }
            if effective_policy is not CommerceExecutionPolicy.PRESENTATION_ALLOWED:
                selected_offering.update({
                    "price_minor": decision.recommended_offering_price_minor,
                    "currency": decision.recommended_offering_currency,
                })
            context["selected_offering"] = selected_offering
        elif (
            decision.decision in {
                CustomerSalesDecisionType.TEASE,
                CustomerSalesDecisionType.BUILD_INTEREST,
            }
            and (decision.recommended_offering_title or customer_safe_copy)
            and not (session_context_required and not session_context_available)
        ):
            context["selected_opportunity"] = {
                "customer_safe_description": customer_safe_copy,
                "customer_safe_copy_available": bool(customer_safe_copy),
                "offering_type": (
                    dict(decision.recommended_product_context or {}).get(
                        "offeringType"
                    )
                ),
            }
        if decision.decision is CustomerSalesDecisionType.PROPOSE_SESSION:
            proposal_context = dict(
                dict(decision.decision_metadata or {}).get(
                    "sessionProposalContext"
                ) or {}
            )
            context["session_proposal_contract"] = {
                "authorized": True,
                "session_started": False,
                "no_purchase_intent": True,
                "price_neutral": True,
                "customer_safe_description": self._customer_safe_offering_copy(
                    proposal_context.get("description")
                ),
                "instruction": (
                    "Naturally suggest continuing this as an ongoing experience. "
                    "Do not mention software modes, Sales Sessions, internal "
                    "strategy, or a numeric price. Invite the customer to lean in; "
                    "do not imply that a Session has already started."
                ),
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
            "customer_value_attention": value_attention,
            "offering_copy_diagnostics": offering_copy_diagnostics,
            "commerce_execution_policy": effective_policy.value,
            "authoritative_selection_missing": (
                selection_missing
                or (session_context_required and not session_context_available)
            ),
        }

    @staticmethod
    def _customer_safe_offering_copy(value: str | None) -> str | None:
        """Allow descriptive copy into generation, never raw/internal labels."""
        copy = " ".join(str(value or "").split()).strip()
        if not copy:
            return None
        if re.search(
            r"\b(?:certification|fixture|test[- ]?only|internal(?:\s+id)?|uuid)\b",
            copy, re.I,
        ):
            return None
        return copy

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
        opportunity = dict(decision.decision_metadata or {}).get(
            "commercialOpportunity"
        )
        receptiveness = dict(decision.decision_metadata or {}).get(
            "commercialReceptiveness"
        )
        cooldown = dict(decision.decision_metadata or {}).get(
            "purchaseCooldown"
        )
        continuation = dict(decision.decision_metadata or {}).get(
            "continuation"
        )
        objection = dict(decision.decision_metadata or {}).get(
            "commercialObjection"
        )
        objection_recovery = dict(decision.decision_metadata or {}).get(
            "objectionRecovery"
        )
        next_best = dict(decision.decision_metadata or {}).get(
            "nextBestOffer"
        )
        lifecycle = dict(
            dict(decision.decision_metadata or {}).get("offerLifecycle") or {}
        )
        acknowledgement_intent_id = None
        if (
            lifecycle.get("messagePurpose") == "PURCHASE_ACKNOWLEDGEMENT"
            and lifecycle.get("purchaseIntentId")
        ):
            acknowledgement_intent_id = str(lifecycle["purchaseIntentId"])
        value_attention = dict(decision.decision_metadata or {}).get(
            "customerValueAttention"
        )
        contextual_tone = dict(decision.decision_metadata or {}).get(
            "contextualCustomerTone"
        )
        outbound_suppression = dict(decision.decision_metadata or {}).get(
            "outboundSuppression"
        )
        active_buying_window = dict(decision.decision_metadata or {}).get(
            "activeBuyingWindow"
        )
        deferred_continuation = dict(decision.decision_metadata or {}).get(
            "deferredContinuation"
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
            "active_purchase_intent_id": str(decision.active_purchase_intent_id) if decision.active_purchase_intent_id else None,
            "purchase_acknowledgement_intent_id": acknowledgement_intent_id,
            "recommendation_trace": (
                selector_diagnostics.get("recommendationTrace") or []
            ),
            "recommendation_diagnostics": selector_diagnostics or None,
            "commercial_intelligence": (
                dict(intelligence)
                if isinstance(intelligence, Mapping) else None
            ),
            "commercial_opportunity": (
                dict(opportunity)
                if isinstance(opportunity, Mapping) else None
            ),
            "commercial_receptiveness": (
                dict(receptiveness)
                if isinstance(receptiveness, Mapping) else None
            ),
            "purchase_cooldown": (
                dict(cooldown) if isinstance(cooldown, Mapping) else None
            ),
            "active_buying_window": (
                dict(active_buying_window)
                if isinstance(active_buying_window, Mapping) else None
            ),
            "deferred_continuation": (
                dict(deferred_continuation)
                if isinstance(deferred_continuation, Mapping) else None
            ),
            "commercial_continuation": (
                dict(continuation)
                if isinstance(continuation, Mapping) else None
            ),
            "commercial_objection": (
                dict(objection) if isinstance(objection, Mapping) else None
            ),
            "objection_recovery": (
                dict(objection_recovery)
                if isinstance(objection_recovery, Mapping) else None
            ),
            "next_best_offer": (
                dict(next_best) if isinstance(next_best, Mapping) else None
            ),
            "bundle_sales_context": (
                {
                    key: value
                    for key, value in dict(
                        decision.bundle_sales_context or {}
                    ).items()
                    if key != "_delivery"
                } or None
            ),
            "offer_lifecycle": dict(lifecycle) if isinstance(lifecycle, Mapping) else None,
            "customer_value_attention": (
                dict(value_attention) if isinstance(value_attention, Mapping) else None
            ),
            "contextual_customer_tone": (
                dict(contextual_tone) if isinstance(contextual_tone, Mapping) else None
            ),
            "outbound_suppression": (
                dict(outbound_suppression)
                if isinstance(outbound_suppression, Mapping) else None
            ),
            "sales_progression_source": dict(
                decision.decision_metadata or {}
            ).get("salesProgressionSource", "NONE"),
            "sales_progression_transition": dict(
                dict(decision.decision_metadata or {}).get(
                    "salesProgressionTransition"
                ) or {}
            ) or None,
            "recommended_product_context": dict(decision.recommended_product_context or {}),
            "recommended_photoshoot_experience": (
                {
                    "photoshoot_id": decision.recommended_photoshoot_experience.photoshoot_id,
                    "title": decision.recommended_photoshoot_experience.title,
                }
                if decision.recommended_photoshoot_experience is not None else None
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
    def _safe_exception_message(error: Exception) -> str:
        message = " ".join(str(error).split())[:240]
        if not message:
            return "No exception message provided."
        message = re.sub(r"https?://\S+", "[URL_REDACTED]", message)
        message = re.sub(
            r"(?i)(authorization|bearer|api[_ -]?key|password|secret|token)\s*[:=]?\s*\S+",
            r"\1 [REDACTED]",
            message,
        )
        return message

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

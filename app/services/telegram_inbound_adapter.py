"""Offline normalization from Telegram-like input to the conversation gateway."""

from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from app.models.conversation_gateway import (
    ConversationBrainContext,
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
from app.services.telegram_identity_service import TelegramIdentityError


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
        creator_profile_id: int | None = None,
        fanvue_account_id: int | None = None,
        purchase_intent_service=None,
        telegram_identity_service=None,
        conversation_thread_resolver=None,
        conversation_message_saver=None,
        conversation_history_loader=None,
        unmapped_conversation_history_loader=None,
        customer_safety_service=None,
        identity_verification_service=None,
        engagement_outcome_tracker=None,
        unmapped_telegram_prospect_service=None,
        conversation_history_limit: int = 10,
        conversational_memory_service=None,
        buyer_memory_priority_resolver=None,
        customer_behavior_evidence_repository=None,
        abuse_policy_service=None,
        relationship_control_service=None,
        private_inbound_backlog_service=None,
        content_entry_attribution_service=None,
    ) -> None:
        if identity_adapter is None:
            raise ValueError("identity_adapter is required")
        if conversation_gateway is None:
            raise ValueError("conversation_gateway is required")
        self._identity_adapter = identity_adapter
        self._conversation_gateway = conversation_gateway
        self._creator_profile_id = creator_profile_id
        self._fanvue_account_id = fanvue_account_id
        self._purchase_intents = purchase_intent_service
        self._telegram_identities = telegram_identity_service
        self._conversation_thread_resolver = conversation_thread_resolver
        self._conversation_message_saver = conversation_message_saver
        self._conversation_history_loader = conversation_history_loader
        self._unmapped_conversation_history_loader = (
            unmapped_conversation_history_loader
        )
        if customer_safety_service is None:
            from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
            customer_safety_service = CustomerInteractionSafetyService()
        self._customer_safety = customer_safety_service
        self._identity_verification = identity_verification_service
        self._engagement_outcomes = engagement_outcome_tracker
        self._unmapped_prospects = unmapped_telegram_prospect_service
        self._conversation_history_limit = max(1, int(conversation_history_limit))
        self._conversational_memory = conversational_memory_service
        self._buyer_memory_priority_resolver = buyer_memory_priority_resolver
        self._customer_behavior_evidence = customer_behavior_evidence_repository
        self._abuse_policy = abuse_policy_service
        self._relationship_controls = relationship_control_service
        self._private_inbound_backlog = private_inbound_backlog_service
        self._content_entry_attribution = content_entry_attribution_service

    def observe_identity_and_relationship(self, payload: TelegramInboundPayload):
        """Establish Chat visibility without running memory, generation, or sales."""
        self._validate_payload(payload)
        try:
            identity = self._identity_adapter.adapt(TelegramMvpIdentityInput(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id))
        except InvalidTelegramMvpIdentityError as error:
            raise InvalidTelegramInboundError(str(error)) from error
        correlation_id = payload.correlation_id or self._generate_correlation_id(
            payload.telegram_chat_id, payload.message_id)
        canonical_identity = None
        if self._telegram_identities is not None:
            self._telegram_identities.observe(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
                username=payload.telegram_username,
                display_name=payload.telegram_display_name)
            try:
                canonical_identity = self._telegram_identities.resolve_telegram_identity(
                    payload.telegram_user_id)
            except TelegramIdentityError:
                canonical_identity = None
        else:
            identity_repository = getattr(self._purchase_intents, "identities", None)
            if identity_repository is not None:
                reader = (getattr(identity_repository, "get_verified_by_telegram_user_id", None)
                          or identity_repository.get_by_telegram_user_id)
                canonical_identity = reader(payload.telegram_user_id)
        telegram_prospect = None
        if (canonical_identity is None and self._creator_profile_id
                and self._fanvue_account_id):
            if self._unmapped_prospects is None:
                from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
                self._unmapped_prospects = UnmappedTelegramProspectService()
            telegram_prospect = self._unmapped_prospects.observe(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id))
        if self._private_inbound_backlog is not None:
            self._private_inbound_backlog.correlate(
                payload, account_scope="AVA_TELETHON_PRIVATE",
                mapped_customer_id=(getattr(canonical_identity, "local_fanvue_user_id", None)
                    if canonical_identity is not None else None),
                prospect_id=getattr(telegram_prospect, "prospect_id", None))
        return identity, canonical_identity, telegram_prospect, correlation_id

    def observe_content_entry_control(self, payload: TelegramInboundPayload, *,
                                      observed_identity=None):
        """Consume attribution commands before any ordinary-response lifecycle."""
        identity, canonical_identity, _prospect, correlation_id = (
            observed_identity or self.observe_identity_and_relationship(payload))
        if self._content_entry_attribution is None:
            from app.services.creator_content_entry_attribution_service import CreatorContentEntryAttributionService
            self._content_entry_attribution = CreatorContentEntryAttributionService()
        observation = self._content_entry_attribution.observe_message(
            creator_profile_id=int(self._creator_profile_id or 0),
            message_text=payload.message_text,
            telegram_user_id=int(payload.telegram_user_id),
            telegram_chat_id=int(payload.telegram_chat_id),
            inbound_telegram_message_id=int(payload.message_id),
        )
        if observation.get("disposition") == "NONE":
            return None
        return TelegramInboundResult(
            correlation_id=correlation_id, telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id, message_id=payload.message_id,
            engine_user_id=(getattr(canonical_identity, "engine_user_id", None)
                or identity.engine_user_id), response_text="", offer_authorized=False,
            offer_link=None, blocked=True,
            error_code=str(observation.get("disposition") or "ATTRIBUTION_REJECTED"),
            delivery_requires_payment=False, delivery_payload={},
            diagnostic_metadata={"creatorContentEntryAttribution": observation,
                "controlTraffic": True, "ordinaryConversation": False,
                "ai_generation_count": 0, "commercial_execution_count": 0,
                "automatic_send_count": 0, "customerHeatSignalCreated": False,
                "ordinaryReplyOperationCreated": False},
        )
    def execute(
        self,
        payload: TelegramInboundPayload,
        *,
        observe_only: bool = False,
    ) -> TelegramInboundResult:
        observed_identity = self.observe_identity_and_relationship(payload)
        control_result = self.observe_content_entry_control(payload, observed_identity=observed_identity)
        if control_result is not None:
            return control_result
        identity, canonical_identity, telegram_prospect, correlation_id = observed_identity
        canonical_thread = None
        durable_inbound_observed = telegram_prospect is not None
        conversational_memory = {}
        if (payload.message_text and self._conversational_memory is not None and self._creator_profile_id
                and self._fanvue_account_id):
            memory_priority = "STANDARD"
            if (canonical_identity is not None
                    and self._buyer_memory_priority_resolver is not None):
                try:
                    memory_priority = self._buyer_memory_priority_resolver(
                        creator_profile_id=int(self._creator_profile_id),
                        canonical_identity=canonical_identity,
                    )
                except Exception:
                    # Memory enrichment must fail closed to the existing default;
                    # it may never block legitimate reactive conversation.
                    memory_priority = "STANDARD"
            conversational_memory = self._conversational_memory.learn(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id),
                message_text=payload.message_text,
                memory_priority=memory_priority,
                bootstrap_unmapped_prospect=canonical_identity is None,
            )
            conversational_memory.setdefault("memoryDiagnostics", {})[
                "identitySource"
            ] = (
                "MAPPED_CUSTOMER"
                if canonical_identity is not None
                else "TELEGRAM_NUMERIC_PROSPECT"
            )
        acknowledgement = None
        if (
            self._purchase_intents is not None
            and self._creator_profile_id
            and self._fanvue_account_id
        ):
            acknowledgement = self._purchase_intents.get_unacknowledged_purchase(
                creator_profile_id=self._creator_profile_id,
                fanvue_account_id=self._fanvue_account_id,
                telegram_user_id=payload.telegram_user_id,
            )
        explicit_ack_continuation = False
        if acknowledgement is not None:
            from app.services.commercial_receptiveness_service import CommercialReceptivenessService
            explicit_ack_continuation = (
                CommercialReceptivenessService.explicit_continuation_detected(
                    payload.message_text
                )
            )
        if (
            self._creator_profile_id and self._fanvue_account_id
            and explicit_ack_continuation
        ):
            if self._unmapped_prospects is None:
                from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
                self._unmapped_prospects = UnmappedTelegramProspectService()
            telegram_prospect = self._unmapped_prospects.observe(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id),
            )
            durable_inbound_observed = telegram_prospect is not None
            if explicit_ack_continuation:
                from app.services.session_escalation_decision_service import (
                    SessionEscalationDecisionService,
                )
                continuation_type = (
                    SessionEscalationDecisionService.continuation_intent(
                        payload.message_text
                    )
                )
                self._unmapped_prospects.record_deferred_continuation(
                    creator_profile_id=int(self._creator_profile_id),
                    fanvue_account_id=int(self._fanvue_account_id),
                    telegram_user_id=int(payload.telegram_user_id),
                    source_inbound_message_id=int(payload.message_id),
                    source_correlation_id=correlation_id,
                    purchase_intent_id=acknowledgement.purchase_intent_id,
                    continuation_type=(
                        continuation_type
                        if continuation_type != "NONE" else "EXPLICIT_MORE"
                    ),
                )
        if (telegram_prospect is None and self._unmapped_prospects is not None
                and self._creator_profile_id and self._fanvue_account_id
                and hasattr(self._unmapped_prospects, "repository")):
            telegram_prospect = self._unmapped_prospects.repository.get(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
            )
        if telegram_prospect is not None:
            relationship = dict(
                getattr(telegram_prospect, "relationship_state", {}) or {}
            )
            conversational_memory["supporterAttentionBoundary"] = dict(
                relationship.get("supporterAttentionBoundary") or {}
            )
        if (self._abuse_policy is not None and self._creator_profile_id
                and self._fanvue_account_id):
            authority = self._abuse_policy.existing_authority(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                canonical_identity=canonical_identity, prospect=telegram_prospect,
            )
            if authority.suppressed:
                return self._suppressed_result(
                    payload, correlation_id, identity.engine_user_id,
                    authority.code, authority.diagnostics,
                )
        if (
            canonical_identity is not None
            and self._conversation_thread_resolver is not None
        ):
            canonical_thread = self._conversation_thread_resolver(
                fanvue_account_id=canonical_identity.fanvue_account_id,
                fanvue_user_id=canonical_identity.local_fanvue_user_id,
            )

        if canonical_identity is not None and self._creator_profile_id:
            safety = self._customer_safety.decide(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(canonical_identity.fanvue_account_id),
                fanvue_user_id=int(canonical_identity.local_fanvue_user_id),
            )
            if not safety.allowed:
                return TelegramInboundResult(
                    correlation_id=correlation_id,
                    telegram_chat_id=payload.telegram_chat_id,
                    telegram_user_id=payload.telegram_user_id,
                    message_id=payload.message_id,
                    engine_user_id=canonical_identity.engine_user_id,
                    response_text="", offer_authorized=False, offer_link=None,
                    blocked=True, error_code=safety.code,
                    delivery_requires_payment=False, delivery_payload={},
                    diagnostic_metadata={
                        "customer_interaction_safety": safety.code,
                        "ai_generation_count": 0,
                    },
                )

        message_uuid = uuid5(
            NAMESPACE_URL,
            f"telegram:{payload.telegram_chat_id}:inbound:{payload.message_id}",
        )
        chat_history = payload.chat_history
        recent_history_source = "NONE"
        if canonical_thread is not None and self._conversation_history_loader is not None:
            chat_history = list(self._conversation_history_loader(
                fanvue_account_id=canonical_identity.fanvue_account_id,
                thread_id=int(canonical_thread["id"]),
                limit=self._conversation_history_limit,
                exclude_message_uuid=message_uuid,
            ))
            recent_history_source = "CANONICAL_MAPPED_CONVERSATION"
            if (
                not chat_history
                and self._unmapped_conversation_history_loader is not None
                and self._creator_profile_id
                and self._fanvue_account_id
            ):
                chat_history = list(self._unmapped_conversation_history_loader(
                    creator_profile_id=int(self._creator_profile_id),
                    fanvue_account_id=int(self._fanvue_account_id),
                    telegram_user_id=int(payload.telegram_user_id),
                    telegram_chat_id=int(payload.telegram_chat_id),
                    exclude_inbound_message_id=int(payload.message_id),
                ))
                if chat_history:
                    recent_history_source = (
                        "TELEGRAM_DURABLE_PROSPECT_FALLBACK"
                    )
        elif (
            canonical_identity is None
            and self._unmapped_conversation_history_loader is not None
            and self._creator_profile_id
            and self._fanvue_account_id
        ):
            chat_history = list(self._unmapped_conversation_history_loader(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id),
                exclude_inbound_message_id=int(payload.message_id),
            ))
            recent_history_source = "TELEGRAM_DURABLE_PROSPECT"
        if (self._abuse_policy is not None and self._creator_profile_id
                and self._fanvue_account_id):
            abuse = self._abuse_policy.evaluate_current(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id),
                inbound_message_id=int(payload.message_id),
                correlation_id=correlation_id, message=payload.message_text,
                canonical_identity=canonical_identity,
                recent_transcript=chat_history, prospect=telegram_prospect,
                telegram_username=payload.telegram_username,
            )
            if abuse.suppressed:
                return self._suppressed_result(
                    payload, correlation_id,
                    getattr(canonical_identity, "engine_user_id", None)
                    or identity.engine_user_id,
                    abuse.code, abuse.diagnostics,
                )
        if (payload.message_text and canonical_thread is not None
                and self._conversation_message_saver is not None):
            self._conversation_message_saver(
                fanvue_account_id=canonical_identity.fanvue_account_id,
                thread_id=int(canonical_thread["id"]),
                fanvue_user_id=canonical_identity.local_fanvue_user_id,
                direction="inbound", sender_type="user",
                text=payload.message_text,
                fanvue_message_uuid=message_uuid,
                raw_payload={
                    "provider": "TELEGRAM", "channel": "PRIVATE_CHAT",
                    "telegram_chat_id": payload.telegram_chat_id,
                    "telegram_message_id": payload.message_id,
                    "correlation_id": correlation_id,
                    "reply_to_telegram_message_id": payload.reply_to_message_id,
                },
            )
            durable_inbound_observed = True
            if self._engagement_outcomes is not None and self._creator_profile_id:
                self._engagement_outcomes.record_next_inbound(
                    creator_profile_id=int(self._creator_profile_id),
                    fanvue_account_id=int(canonical_identity.fanvue_account_id),
                    fanvue_user_id=int(canonical_identity.local_fanvue_user_id),
                    telegram_message_id=payload.message_id,
                    reply_to_message_id=payload.reply_to_message_id,
                )

        relationship_control = None
        if (self._relationship_controls is not None and self._creator_profile_id
                and self._fanvue_account_id):
            allowed, control = self._relationship_controls.autonomous_allowed(
                creator_profile_id=int(self._creator_profile_id),
                fanvue_account_id=int(self._fanvue_account_id),
                telegram_user_id=int(payload.telegram_user_id),
                telegram_chat_id=int(payload.telegram_chat_id),
            )
            relationship_control = control
            if not allowed:
                hold_reason = (
                    self._relationship_controls.block_reason(control)
                    if hasattr(self._relationship_controls,"block_reason")
                    else self._relationship_controls.HOLD_REASON)
                return TelegramInboundResult(
                    correlation_id=correlation_id,
                    telegram_chat_id=payload.telegram_chat_id,
                    telegram_user_id=payload.telegram_user_id,
                    message_id=payload.message_id,
                    engine_user_id=(getattr(canonical_identity, "engine_user_id", None)
                                    or identity.engine_user_id),
                    response_text="", offer_authorized=False, offer_link=None,
                    blocked=True, error_code=hold_reason,
                    delivery_requires_payment=False, delivery_payload={},
                    diagnostic_metadata={
                        "relationship_control_mode": control.mode.value,
                        "relationship_control_version": control.control_version,
                        "held_reason": hold_reason,
                        "ai_generation_count": 0,
                    },
                )

        # Observation is part of the canonical inbound path and precedes any
        # AI or Sales Brain execution. AVA BOT OFF uses this boundary so the
        # message, identity, relationship and memory evidence remain durable
        # without creating a reply, presentation, or PurchaseIntent.
        if observe_only:
            return TelegramInboundResult(
                correlation_id=correlation_id,
                telegram_chat_id=payload.telegram_chat_id,
                telegram_user_id=payload.telegram_user_id,
                message_id=payload.message_id,
                engine_user_id=(getattr(canonical_identity, "engine_user_id", None)
                                or identity.engine_user_id),
                response_text="", offer_authorized=False, offer_link=None,
                blocked=True, error_code="GLOBAL_AUTOMATION_DISABLED",
                delivery_requires_payment=False, delivery_payload={},
                diagnostic_metadata={
                    "observation_only": True,
                    "durable_inbound_observed": durable_inbound_observed,
                    "ai_generation_count": 0,
                    "commercial_execution_count": 0,
                    "automatic_send_count": 0,
                },
            )

        effective_engine_user_id = (
            getattr(canonical_identity, "engine_user_id", None)
            or (f"{canonical_identity.fanvue_account_id}:"
                f"{canonical_identity.local_fanvue_user_id}"
                if canonical_identity else identity.engine_user_id)
        )
        gateway_output = self._conversation_gateway.execute(
            ConversationGatewayInput(
                engine_user_id=effective_engine_user_id,
                message_text=payload.message_text,
                chat_history=chat_history,
                correlation_id=correlation_id,
                current_turn_visual_context=dict(
                    payload.current_turn_visual_context or {}
                ),
                quality_correction_context=dict(
                    payload.quality_correction_context or {}
                ),
                brain_context=ConversationBrainContext(
                    creator_profile_id=self._creator_profile_id,
                    customer_identifier=effective_engine_user_id,
                    conversation_identifier=correlation_id,
                    telegram_user_id=payload.telegram_user_id,
                    fanvue_account_id=self._fanvue_account_id,
                    fanvue_user_id=(
                        canonical_identity.local_fanvue_user_id
                        if canonical_identity else None
                    ),
                    external_fanvue_buyer_uuid=(
                        str(canonical_identity.external_fanvue_user_uuid)
                        if canonical_identity else None
                    ),
                    conversation_thread_id=(
                        int(canonical_thread["id"])
                        if canonical_thread else None
                    ),
                    purchase_acknowledgement_pending=(
                        acknowledgement is not None
                    ),
                    purchase_acknowledgement_intent_id=(
                        str(acknowledgement.purchase_intent_id)
                        if acknowledgement else None
                    ),
                    conversational_memory=conversational_memory,
                    sleep_context=dict(payload.sleep_context or {}),
                    customer_behavior_evidence=(
                        self._customer_behavior_evidence.customer_behavior_evidence(
                            account_scope="AVA_TELETHON_PRIVATE",
                            chat_id=payload.telegram_chat_id,
                            sender_user_id=payload.telegram_user_id,
                        ) if self._customer_behavior_evidence is not None else {}
                    ),
                ),
            )
        )

        diagnostics = dict(gateway_output.diagnostic_metadata)
        diagnostics.update({
            "recentHistorySource": recent_history_source,
            "recentHistoryTurnCount": len(chat_history) // 2,
        })
        if relationship_control is not None:
            diagnostics.update({
                "relationship_control_mode": relationship_control.mode.value,
                "relationship_control_version": relationship_control.control_version,
            })
        if self._creator_profile_id and self._fanvue_account_id:
            diagnostics.update({"creator_profile_id":int(self._creator_profile_id),
                                "fanvue_account_id":int(self._fanvue_account_id)})
        if self._telegram_identities is not None:
            diagnostics["telegram_identity_eligibility"] = (
                "VERIFIED" if canonical_identity is not None else "UNMAPPED"
            )
        if acknowledgement is not None:
            diagnostics["purchase_acknowledgement_intent_id"] = str(
                acknowledgement.purchase_intent_id
            )
        if canonical_thread is not None:
            diagnostics.update({
                "conversation_thread_id": int(canonical_thread["id"]),
                "conversation_fanvue_account_id": canonical_identity.fanvue_account_id,
                "conversation_fanvue_user_id": canonical_identity.local_fanvue_user_id,
            })
        if canonical_identity is not None and self._creator_profile_id:
            diagnostics.update({
                "creator_profile_id": int(self._creator_profile_id),
                "fanvue_account_id": int(canonical_identity.fanvue_account_id),
                "fanvue_user_id": int(canonical_identity.local_fanvue_user_id),
            })
        response_text = gateway_output.response_text
        value_attention = dict(diagnostics.get("customerValueAttention") or {})
        boundary = dict(conversational_memory.get("supporterAttentionBoundary") or {})
        boundary_appropriate = bool(value_attention.get("lowCostNurtureActive")
                                    and not boundary.get("delivered"))
        boundary_delivered = bool(boundary_appropriate and __import__("re").search(
            r"\b(?:support me|supporters?|people who support)\b",
            str(response_text or ""), __import__("re").I))
        if self._abuse_policy is not None or boundary_appropriate or boundary.get("delivered"):
            diagnostics.update({
                "supporterAttentionBoundaryAppropriate": boundary_appropriate,
                "supporterAttentionBoundaryDelivered": False,
                "supporterAttentionBoundaryPreviouslyDelivered": bool(boundary.get("delivered")),
            })
        if boundary_delivered:
            diagnostics.update({
                "supporter_attention_boundary_pending_confirmation": True,
                "pending_supporter_attention_boundary_context": {
                    "creator_profile_id": self._creator_profile_id,
                    "fanvue_account_id": self._fanvue_account_id,
                    "telegram_user_id": payload.telegram_user_id,
                    "correlation_id": correlation_id,
                },
            })
        offer_authorized = gateway_output.offer_authorized
        offer_link = gateway_output.offer_link
        from app.models.telegram_inbound import canonical_text_delivery_type
        delivery_type = (canonical_text_delivery_type(gateway_output.delivery_type)
                         if not gateway_output.offer_authorized and not gateway_output.delivery_requires_payment
                         else gateway_output.delivery_type)
        delivery_mode = gateway_output.delivery_mode
        delivery_requires_payment = gateway_output.delivery_requires_payment
        delivery_payload = dict(gateway_output.delivery_payload)
        if delivery_type == 'MESSAGE_TEXT':
            for type_key in ('type', 'delivery_type'):
                if type_key in delivery_payload:
                    delivery_payload[type_key] = canonical_text_delivery_type(delivery_payload[type_key])
        if self._telegram_identities is not None and canonical_identity is None and (
            offer_authorized or offer_link or delivery_requires_payment
        ):
            from app.services.private_chat_unlock_gateway_service import fingerprint_bootstrap_enabled
            if fingerprint_bootstrap_enabled():
                diagnostics["telegram_identity_eligibility"] = "UNMAPPED_BOOTSTRAP"
                diagnostics["private_chat_price_copy_policy"] = "PRICE_NEUTRAL"
            else:
                response_text = (
                    "I can keep chatting with you here, but paid offers are unavailable "
                    "until your account connection is verified."
                )
                offer_authorized = False
                offer_link = None
                delivery_type = None
                delivery_mode = None
                delivery_requires_payment = False
                delivery_payload = {"message_text": response_text}
                diagnostics["paid_offer_blocked_reason"] = "TELEGRAM_IDENTITY_UNVERIFIED"

        if (
            canonical_identity is None
            and self._identity_verification is not None
            and self._fanvue_account_id
            and self._identity_verification.should_start(payload.message_text)
        ):
            challenge = self._identity_verification.start(
                telegram_user_id=payload.telegram_user_id,
                telegram_chat_id=payload.telegram_chat_id,
                fanvue_account_id=int(self._fanvue_account_id),
            )
            response_text = challenge.instruction or response_text
            offer_authorized = False
            offer_link = None
            delivery_type = None
            delivery_mode = None
            delivery_requires_payment = False
            delivery_payload = {"message_text": response_text}
            diagnostics.update({
                "identity_verification": "PENDING",
                "identity_verification_challenge_id": str(challenge.challenge_id),
                "identity_verification_already_pending": challenge.already_pending,
            })

        return TelegramInboundResult(
            correlation_id=gateway_output.correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=effective_engine_user_id,
            response_text=response_text,
            offer_authorized=offer_authorized,
            offer_link=offer_link,
            blocked=gateway_output.blocked,
            error_code=gateway_output.error_code,
            delivery_type=delivery_type,
            delivery_mode=delivery_mode,
            delivery_requires_payment=delivery_requires_payment,
            delivery_payload=delivery_payload,
            diagnostic_metadata=diagnostics,
        )

    @staticmethod
    def _suppressed_result(payload, correlation_id, engine_user_id, code,
                           diagnostics):
        return TelegramInboundResult(
            correlation_id=correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id, engine_user_id=engine_user_id,
            response_text="", offer_authorized=False, offer_link=None,
            blocked=True, error_code=code, delivery_requires_payment=False,
            delivery_payload={}, diagnostic_metadata={
                **dict(diagnostics or {}), "ai_generation_count": 0,
                "ordinaryReplySuppressed": True,
                "commerceSuppressed": True, "grokSuppressed": True,
                "sessionSuppressed": True, "nurtureSuppressed": True,
            },
        )

    @staticmethod
    def _validate_payload(payload: TelegramInboundPayload) -> None:
        if not isinstance(payload, TelegramInboundPayload):
            raise InvalidTelegramInboundError(
                "payload must be a TelegramInboundPayload."
            )
        if (
            not isinstance(payload.message_text, str)
            or (not payload.message_text.strip() and not payload.attachments
                and not (payload.media_turn_input is not None
                         and payload.media_turn_input.matches(payload)))
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

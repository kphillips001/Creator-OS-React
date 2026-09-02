"""Deterministic commercial action evaluator; no AI and no side effects."""
from __future__ import annotations
from dataclasses import replace
from collections.abc import Mapping

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.repositories.customer_commerce_repository import CustomerCommerceRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.sales_session_repository import SalesSessionRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.commerce_signal_service import CommerceSignalService
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.services.commercial_intelligence_context_service import (
    CommercialIntelligenceContextService,
)
from app.services.commercial_intelligence_service import (
    CommercialIntelligenceService,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.models.ownership_intelligence import OwnershipIdentity
from app.services.customer_commerce_memory_service import CustomerCommerceMemoryService
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.services.commercial_objection_service import CommercialObjectionService
from app.models.commercial_objection import CommercialObjectionType
from app.models.commercial_intelligence import StrategyConstraints


logger = logging.getLogger("customer-sales-brain")


class CustomerSalesBrainService:
    SUSTAINED_SEXUAL_RECEPTIVENESS_AUTHORITY = (
        "CUSTOMER_SALES_BRAIN_CANONICAL_BEHAVIOR_EVIDENCE"
    )

    def _sustained_sexual_receptiveness_projection(self, context: dict) -> dict:
        """Project this concept once from the complete authoritative context."""
        tone = dict(context.get("contextual_customer_tone") or {})
        progression = dict(context.get("sales_progression") or {})
        suppression_reasons = []
        if int(context.get("rejection_count") or 0) > 0:
            suppression_reasons.append("CUSTOMER_REJECTION")
        if str(progression.get("phase") or "").upper() == "BACK_OFF":
            suppression_reasons.append("BACK_OFF")
        if tone.get("explicitDisengagement") is True:
            suppression_reasons.append("EXPLICIT_DISENGAGEMENT")
        if tone.get("hostilityLevel") in {"HIGH", "SEVERE"}:
            suppression_reasons.append("HIGH_HOSTILITY")
        sexual_detected = bool(
            tone.get("sexualOrProvocative") is True
            or int(context.get("sexual_engagement_count") or 0) > 0
        )
        value = bool(
            context.get("sexual_engagement_only")
            and int(context.get("sexual_engagement_count") or 0)
                >= self.config.sexual_receptiveness_min_engagements
            and int(context.get("inbound_message_count") or 0)
                >= self.config.sexual_receptiveness_min_history_turns
            and tone.get("sexualOrProvocative") is True
            and not suppression_reasons
        )
        return {
            "value": value,
            "authority": self.SUSTAINED_SEXUAL_RECEPTIVENESS_AUTHORITY,
            "sexualEngagementDetected": sexual_detected,
            "sexualEngagementCount": int(context.get("sexual_engagement_count") or 0),
            "inboundMessageCount": int(context.get("inbound_message_count") or 0),
            "suppressionReasons": suppression_reasons,
        }

    def _sustained_sexual_receptiveness(self, context: dict) -> bool:
        return bool(self._sustained_sexual_receptiveness_projection(context)["value"])

    def _commerce_selection_relevant(self, context: dict, *, objection=None) -> tuple[bool, str]:
        """Gate inventory work behind current commercial or persisted offer evidence."""
        message = str(context.get("latest_message") or "")
        if not message:
            return True, "LEGACY_CALLER_WITHOUT_CURRENT_TURN_CLASSIFICATION"
        features = self.conversational_progression.transition_features(message)
        progression = dict(context.get("sales_progression") or {})
        phase = str(progression.get("phase") or "CONVERSATIONAL").upper()
        classifier = dict(context.get("classifier_result") or {})
        receptiveness = dict(context.get("commercial_receptiveness") or {})
        relevant = bool(
            self.conversational_progression.has_direct_purchase_intent(message)
            or receptiveness.get("freshDirectIntentDetected") is True
            or features.get("content_request")
            or features.get("reveal_request")
            or phase in {"TEASE", "BUILD_INTEREST", "PRESENT_OFFER"}
            or classifier.get("buying_intent") is True
            or classifier.get("conversation_ready_for_offer") is True
            or bool(objection is not None and getattr(objection, "consider_alternative", False))
            or self._sustained_sexual_receptiveness(context)
        )
        if relevant:
            return True, (
                "SUSTAINED_POSITIVE_SEXUAL_RECEPTIVENESS"
                if self._sustained_sexual_receptiveness(context)
                else "CURRENT_COMMERCIAL_OR_OFFER_TRAJECTORY_EVIDENCE"
            )
        return False, "NO_CURRENT_COMMERCIAL_EVIDENCE"

    def __init__(
        self, *, customer_repository=None, identity_repository=None,
        intent_repository=None, commerce_signal_service=None,
        offering_selector_service=None, config=None,
        sales_session_repository=None,
        commercial_intelligence_service=None,
        commercial_intelligence_context_service=None,
        photoshoot_lifecycle_service=None,
        autonomous_progression_service=None, progression_repository=None,
        session_runtime_service=None,
        bundle_sales_context_service=None,
        conversational_progression_service=None,
        adaptive_sales_readiness_service=None,
        customer_safety_service=None, telegram_sales_delivery_repository=None,
        customer_commerce_memory_service=None,
        commercial_receptiveness_service=None,
        commercial_objection_service=None,
        customer_value_attention_service=None,
        unmapped_telegram_prospect_service=None,
        clock=lambda: datetime.now(timezone.utc),
    ):
        self.customers = customer_repository or CustomerCommerceRepository()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.intents = intent_repository or PurchaseIntentRepository()
        self.signals = commerce_signal_service or CommerceSignalService()
        self.offering_selector = (
            offering_selector_service or CommercialOfferingSelectorService()
        )
        self.sales_sessions = (
            sales_session_repository or SalesSessionRepository()
        )
        self.commercial_intelligence = (
            commercial_intelligence_service or CommercialIntelligenceService()
        )
        self.commercial_context = (
            commercial_intelligence_context_service
            or CommercialIntelligenceContextService()
        )
        self.config = config or CustomerSalesBrainConfig.from_environment()
        self.photoshoot_lifecycles = photoshoot_lifecycle_service
        self.autonomous_progression = autonomous_progression_service
        self.progression_repository = progression_repository
        self.session_runtime = session_runtime_service
        self.bundle_sales_context = bundle_sales_context_service
        self.customer_commerce_memory = (
            customer_commerce_memory_service or CustomerCommerceMemoryService()
        )
        self.unmapped_prospects = unmapped_telegram_prospect_service
        if telegram_sales_delivery_repository is None:
            from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository
            telegram_sales_delivery_repository = TelegramSalesDeliveryRepository()
        self.telegram_sales_deliveries = telegram_sales_delivery_repository
        self.conversational_progression = (
            conversational_progression_service
            or ConversationalSalesProgressionService()
        )
        self.commercial_receptiveness = (
            commercial_receptiveness_service
            or CommercialReceptivenessService(
                self.conversational_progression.has_direct_purchase_intent
            )
        )
        self.commercial_objections = (
            commercial_objection_service or CommercialObjectionService()
        )
        if customer_value_attention_service is None:
            from app.services.customer_value_attention_service import CustomerValueAttentionService
            customer_value_attention_service = CustomerValueAttentionService()
        self.customer_value_attention = customer_value_attention_service
        if adaptive_sales_readiness_service is None:
            from app.services.adaptive_sales_readiness_service import AdaptiveSalesReadinessService
            adaptive_sales_readiness_service = AdaptiveSalesReadinessService(
                direct_intent_detector=self.conversational_progression.has_direct_purchase_intent)
        self.adaptive_sales_readiness = adaptive_sales_readiness_service
        self.clock = clock
        if customer_safety_service is None:
            from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
            customer_safety_service = CustomerInteractionSafetyService()
        self.customer_safety = customer_safety_service

    def evaluate_for_telegram_user(
        self, *, creator_profile_id: int, telegram_user_id: int,
        conversation_context: dict | None = None,
    ) -> CustomerSalesDecision:
        started = time.perf_counter()
        now = self.clock()
        identity = self.identities.get_by_telegram_user_id(telegram_user_id)
        if identity is None:
            from app.services.private_chat_unlock_gateway_service import fingerprint_bootstrap_enabled
            if fingerprint_bootstrap_enabled():
                return self._evaluate_unmapped_prospect(
                    started=started, now=now,
                    creator_profile_id=creator_profile_id,
                    telegram_user_id=telegram_user_id,
                    conversation_context=conversation_context,
                )
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=0, buyer_uuid=None,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.IDENTITY_UNRESOLVED,
                summary="Telegram identity has no canonical Fanvue buyer mapping.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        local_fanvue_user_id = getattr(identity, "local_fanvue_user_id", None)
        safety = (self.customer_safety.decide(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=identity.fanvue_account_id,
            fanvue_user_id=local_fanvue_user_id)
            if local_fanvue_user_id is not None else None)
        if safety is not None and not safety.allowed:
            proposal = self._session_proposal(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=identity.fanvue_account_id,
                telegram_user_id=telegram_user_id,
            )
            if proposal and proposal.get("state") == "PENDING":
                self.unmapped_prospects.transition_session_proposal(
                    creator_profile_id=creator_profile_id,
                    fanvue_account_id=identity.fanvue_account_id,
                    telegram_user_id=telegram_user_id,
                    target_state="INVALIDATED", reaction="NONE",
                    invalidation_reason=(
                        "CUSTOMER_INTERACTION_SAFETY_BLOCKED"
                    ),
                )
            return self._finish(started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=identity.fanvue_account_id,
                buyer_uuid=identity.external_fanvue_user_uuid,
                telegram_user_id=telegram_user_id, identity_resolved=True,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.CUSTOMER_INTERACTION_SAFETY_BLOCKED,
                summary="Customer autonomous sales interaction is blocked by authoritative safety state.",
                stage=CustomerBuyerStage.UNKNOWN)
        return self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=identity.fanvue_account_id,
            external_fanvue_buyer_uuid=identity.external_fanvue_user_uuid,
            telegram_user_id=identity.telegram_user_id,
            identity_resolved=True,
            conversation_context=conversation_context,
            _started=started,
        )

    def _evaluate_unmapped_prospect(self, *, started, now,
                                    creator_profile_id, telegram_user_id,
                                    conversation_context=None):
        """Evaluate only Telegram-attributable facts before first mapping."""
        context = dict(conversation_context or {})
        account_id = int(context.get("fanvue_account_id") or 0)
        if account_id <= 0:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=0, buyer_uuid=None,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.IDENTITY_UNRESOLVED,
                summary="Creator account context is unavailable for this Telegram prospect.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        if self.unmapped_prospects is None:
            from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
            self.unmapped_prospects = UnmappedTelegramProspectService()
        restricted = self.unmapped_prospects.context(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=context.get("telegram_chat_id"),
        )
        if restricted is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=account_id, buyer_uuid=None,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.NO_COMMERCE_PROFILE,
                summary="Telegram prospect state is not yet durable.",
                stage=CustomerBuyerStage.PROSPECT,
            )
        prior_progression = self.unmapped_prospects.sales_progression(
            restricted.prospect
        )
        if prior_progression is not None:
            context["sales_progression"] = prior_progression
            context["sales_progression_source"] = (
                "TELEGRAM_NUMERIC_PROSPECT"
            )
        else:
            context["sales_progression_source"] = "NONE"
        tone = dict(context.get("contextual_customer_tone") or {})
        active = self.intents.get_active_for_buyer(
            creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id)
        latest = self.intents.get_latest_for_buyer(
            creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id)
        context.update(self._commercial_opportunity_evidence(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id,
            latest=latest,
        ))
        context["_customer_commerce_memory"] = restricted.memory
        context["customer_commerce_memory_summary"] = self._commerce_memory_summary(restricted.memory)
        context["unmapped_telegram_prospect"] = True
        receptiveness = self.commercial_receptiveness.evaluate(
            context=context,
            recent_purchase=False,
            cooldown_active=False,
            active_offer=active is not None,
        )
        active_offer_continuation_type = (
            self.commercial_receptiveness.active_offer_continuation_type(
                str(context.get("latest_message") or "")
            ) if active is not None else None
        )
        context["active_offer_continuation"] = {
            "customerInitiatedOfferContinuation": bool(
                active_offer_continuation_type
            ),
            "continuationIntentType": active_offer_continuation_type,
            "nudgeCooldownApplies": not bool(active_offer_continuation_type),
            "structuredOfferReused": bool(active_offer_continuation_type),
            "structuredOfferRedelivered": False,
            "purchaseIntentReused": bool(active_offer_continuation_type),
            "relationshipDiscoverySuppressed": bool(
                active_offer_continuation_type
            ),
        }
        context["commercial_receptiveness"] = dict(receptiveness.to_mapping())
        deferred = self._deferred_continuation(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
            telegram_user_id=telegram_user_id,
        )
        if deferred:
            context["deferred_continuation"] = deferred
        from app.services.active_buying_window_service import ActiveBuyingWindowService
        explicit_continuation = (
            self.commercial_receptiveness.explicit_continuation_detected(
                str(context.get("latest_message") or "")
            )
        )
        context["active_buying_window"] = ActiveBuyingWindowService.project(
            recent_verified_purchase=bool(int(dict(
                context.get("customer_commerce_memory_summary") or {}
            ).get("recentPurchaseCount") or 0)),
            fresh_direct_intent=receptiveness.fresh_direct_intent,
            explicit_continuation=explicit_continuation,
            active_purchase_intent=active is not None,
            active_offer_context=str(dict(
                context.get("sales_progression") or {}
            ).get("phase") or "").upper() == "PRESENT_OFFER",
            acknowledgement_pending=bool(
                context.get("purchase_acknowledgement_pending")
            ),
            declined=bool(context.get("offer_declined")),
            safety_allowed=True,
            active_session=False,
            cooldown_active=False,
            receptiveness=receptiveness.to_mapping(),
            deferred_continuation=deferred,
        )
        context["explicit_continuation_detected"] = explicit_continuation
        objection = self.commercial_objections.evaluate(
            message=str(context.get("latest_message") or ""), context=context,
        )
        context["commercial_objection"] = self._objection_diagnostics(
            objection, active or latest, context,
        )
        self._apply_objection_ranking_context(context, objection)
        common = dict(
            creator_profile_id=creator_profile_id, fanvue_account_id=account_id,
            buyer_uuid=None, telegram_user_id=telegram_user_id,
            identity_resolved=False, stage=CustomerBuyerStage.PROSPECT,
            signal={"identityState": "UNMAPPED_BOOTSTRAP",
                    "fanvueCommerceHistory": "UNKNOWN"},
            active=active, latest=latest, progression_context=context,
        )
        if tone.get("explicitDisengagement") is True:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="An explicit customer boundary ends the current conversation.",
            )
        if (
            tone.get("rageBaitPattern") is True
            and int(tone.get("priorExplicitDisengagementCount") or 0) > 0
            and not self.conversational_progression.has_direct_purchase_intent(
                str(context.get("latest_message") or "")
            )
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="Repeated abuse cannot reopen a conversation after a customer boundary.",
            )
        if (
            str(dict(context.get("sales_progression") or {}).get("phase") or "").upper()
            == "BACK_OFF"
            and not self.conversational_progression.has_direct_purchase_intent(
                str(context.get("latest_message") or "")
            )
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="Current-conversation BACK_OFF remains authoritative without fresh direct intent.",
            )
        if objection.objection_type is CommercialObjectionType.PAYMENT_TECHNICAL:
            return self._finish(started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.PAYMENT_SUPPORT_REQUIRED,
                summary="A payment or link issue preserves the current offer and routes to support-safe conversation.")
        if objection.objection_type is CommercialObjectionType.GLOBAL_DECLINE:
            return self._objection_stop(started, now, common, context, objection)
        if objection.recovery_strategy == "VALUE_DEFENSE":
            return self._value_defense(started, now, common, context, objection,
                                       active or latest)
        if objection.objection_type is CommercialObjectionType.TEMPORARY_HESITATION:
            return self._objection_stop(started, now, common, context, objection,
                                        decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION)
        proactive_readiness = self._deterministic_proactive_tease_readiness(context)
        if (
            proactive_readiness["authorized"]
            and active is None
            and not bool(dict(context.get("active_buying_window") or {}).get(
                "anotherSaleAppropriateNow"
            ))
        ):
            decision = self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.TEASE,
                reason=CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY,
                summary=(
                    "Sustained voluntary relationship engagement authorizes one "
                    "low-pressure Ava-initiated tease without a paid offer."
                ),
            )
            metadata = dict(decision.decision_metadata or {})
            proactive = {
                "proactiveProgressionAuthorized": True,
                "proactiveProgressionReason": "COMBINED_RELATIONSHIP_EVIDENCE",
                "proactiveProgressionEvidence": tuple(proactive_readiness["evidence"]),
                "proactiveProgressionSuppressions": (),
                "progressionInitiator": "AVA",
                "progressionBefore": "CONVERSATIONAL",
                "progressionAfter": "TEASE",
                "progressionAction": "TEASE",
                "proactiveTeaseCooldown": 0,
                "recentProactiveTease": False,
                "customerResponseToPreviousTease": "NONE",
                "customerBuyingIntentUnchanged": True,
            }
            metadata.update({
                "proactiveProgression": proactive,
                "salesProgression": {
                    "phase": "TEASE", "teaseCount": 1,
                    "reasonCode": CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY.value,
                    "progressionInitiator": "AVA",
                    "awaitingCustomerResponse": True,
                },
                "salesProgressionTransition": {
                    "priorPhase": "CONVERSATIONAL",
                    "transitionSignal": "COMBINED_RELATIONSHIP_EVIDENCE",
                    "nextPhase": "TEASE",
                },
            })
            return replace(
                decision, sell_allowed=False, nudge_allowed=False,
                decision_metadata=immutable_mapping(metadata),
            )
        if (
            active is not None
            and active_offer_continuation_type
            and not objection.consider_alternative
        ):
            selection = self.offering_selector.select(
                creator_profile_id=creator_profile_id,
                telegram_user_id=telegram_user_id,
                customer_profile=restricted.profile,
                commerce_signal=None,
                active_purchase_intent=active,
                conversation_context={
                    **context, "primary_sales_channel": "AI_CHAT",
                },
            )
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
                reason=(CustomerSalesReasonCode
                        .CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION),
                summary=(
                    "The customer explicitly requested the current offer; "
                    "reuse its structured presentation without applying "
                    "the unsolicited-nudge cooldown."
                ),
                nudge_allowed=True,
                recommendation=selection,
                selector_result=selection,
            )
        if active is not None and not objection.consider_alternative:
            return self._finish(
                started, now, **common, decision=CustomerSalesDecisionType.WAIT,
                reason=CustomerSalesReasonCode.ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE,
                summary="One unresolved bootstrap offer is already active.")
        backoff = self.conversational_progression.back_off_reason(context)
        if backoff is not None:
            return self._finish(started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF, reason=backoff,
                summary="Customer response requires backing off the opportunity.")
        if active is not None and objection.consider_alternative:
            abandon = getattr(self.intents, "mark_abandoned", None)
            if callable(abandon):
                abandon(active.purchase_intent_id, at=now)
            active = None
            common["active"] = None
        selector_relevant, selector_reason = self._commerce_selection_relevant(
            context, objection=objection,
        )
        context["selector_invocation_reason"] = selector_reason
        if not selector_relevant:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                summary="Ordinary relationship conversation does not invoke commerce inventory selection.",
            )
        constraints = self._recovery_constraints(objection, latest)
        selection = self.offering_selector.select(
            creator_profile_id=creator_profile_id,
            telegram_user_id=telegram_user_id,
            customer_profile=restricted.profile, commerce_signal=None,
            active_purchase_intent=None,
            conversation_context={**context, "primary_sales_channel": "AI_CHAT"},
            strategy_constraints=constraints,
        )
        if not selection.offering_id:
            return self._finish(started, now, **common,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                summary="No safe live provider-backed offering is available.",
                selector_result=selection)
        recovery = (
            objection.consider_alternative
            and not (
                latest is not None
                and getattr(getattr(latest, "status", None), "value", None)
                == "PURCHASED"
            )
        )
        decision = self._finish(started, now, **common,
            decision=(CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
                      if recovery else CustomerSalesDecisionType.PRESENT_OFFER),
            reason=(self._objection_reason(objection) if recovery
                    else CustomerSalesReasonCode.NO_ACTIVE_OFFER),
            summary="A safe first offering is available for the Telegram prospect.",
            recommendation=selection, selector_result=selection,
            sell_allowed=True)
        if recovery:
            return self._decorate_recovery(decision, objection, selection)
        return self.conversational_progression.refine(decision, context)

    @staticmethod
    def _deterministic_proactive_tease_readiness(context: dict) -> dict:
        """Authorize rapport progression without AI timing or commerce intent."""
        values = dict(context or {})
        warming = dict(values.get("relationship_warming_evidence") or {})
        progression = dict(values.get("sales_progression") or {})
        evidence = []
        inbound = int(values.get("inbound_message_count") or 0)
        meaningful = int(values.get("meaningful_engagement_count") or 0)
        history = int(values.get("recent_history_turn_count") or 0)
        durable_facts = int(values.get("durable_conversational_fact_count") or 0)
        if max(inbound, history) >= 6:
            evidence.append("SUSTAINED_VOLUNTARY_CONVERSATION")
        if meaningful >= 5:
            evidence.append("MEANINGFUL_ENGAGEMENT")
        if durable_facts >= 2:
            evidence.append("VOLUNTARY_SELF_DISCLOSURE")
        if warming.get("reciprocalWarmingObserved") is True:
            evidence.append("RECIPROCAL_RELATIONAL_WARMING")
        if int(values.get("offer_exposure_count") or 0) == 0:
            evidence.append("NO_OFFER_EXPOSURE")

        suppressions = []
        if int(values.get("rejection_count") or 0) > 0 or str(
            progression.get("phase") or ""
        ).upper() == "BACK_OFF":
            suppressions.append("REJECTION_OR_BACK_OFF")
        if int(progression.get("proactiveTeaseCooldownTurns") or 0) > 0:
            suppressions.append("PROACTIVE_TEASE_COOLDOWN")
        if str(progression.get("phase") or "").upper() in {
            "TEASE", "BUILD_INTEREST", "PRESENT_OFFER", "SESSION", "ACTIVE_SESSION",
        }:
            suppressions.append("EXISTING_COMMERCIAL_PROGRESSION")
        required = {
            "SUSTAINED_VOLUNTARY_CONVERSATION", "MEANINGFUL_ENGAGEMENT",
            "VOLUNTARY_SELF_DISCLOSURE", "RECIPROCAL_RELATIONAL_WARMING",
            "NO_OFFER_EXPOSURE",
        }
        return {
            "authorized": required.issubset(evidence) and not suppressions,
            "evidence": tuple(evidence),
            "suppressions": tuple(suppressions),
        }

    @staticmethod
    def authorize_deterministic_proactive_tease(
        decision: CustomerSalesDecision, context: dict,
    ) -> CustomerSalesDecision:
        """Apply the relationship-only tease gate to either identity path."""
        readiness = CustomerSalesBrainService._deterministic_proactive_tease_readiness(
            context
        )
        metadata = dict(decision.decision_metadata or {})
        readiness_diagnostics = {
            "proactiveProgressionAuthorized": bool(readiness["authorized"]),
            "proactiveProgressionReason": (
                "COMBINED_RELATIONSHIP_EVIDENCE"
                if readiness["authorized"]
                else readiness["suppressions"][0]
                if readiness["suppressions"]
                else "INSUFFICIENT_DETERMINISTIC_WARMING_EVIDENCE"
            ),
            "proactiveProgressionEvidence": tuple(readiness["evidence"]),
            "proactiveProgressionSuppressions": tuple(readiness["suppressions"]),
            "progressionAction": "TEASE" if readiness["authorized"] else "NONE",
            "customerBuyingIntentUnchanged": True,
        }
        if (
            decision.decision not in {
                CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesDecisionType.NO_SALE,
            }
            or decision.active_purchase_intent_id is not None
        ):
            return decision
        if not readiness["authorized"]:
            metadata["proactiveProgression"] = readiness_diagnostics
            return replace(decision, decision_metadata=immutable_mapping(metadata))
        metadata.update({
            "proactiveProgression": {
                **readiness_diagnostics,
                "proactiveProgressionAuthorized": True,
                "proactiveProgressionReason": "COMBINED_RELATIONSHIP_EVIDENCE",
                "proactiveProgressionEvidence": tuple(readiness["evidence"]),
                "proactiveProgressionSuppressions": (),
                "progressionInitiator": "AVA",
                "progressionBefore": "CONVERSATIONAL",
                "progressionAfter": "TEASE",
                "progressionAction": "TEASE",
                "proactiveTeaseCooldown": 0,
                "recentProactiveTease": False,
                "customerResponseToPreviousTease": "NONE",
                "customerBuyingIntentUnchanged": True,
            },
            "salesProgression": {
                "phase": "TEASE", "teaseCount": 1,
                "reasonCode": CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY.value,
                "progressionInitiator": "AVA",
                "awaitingCustomerResponse": True,
            },
            "salesProgressionTransition": {
                "priorPhase": "CONVERSATIONAL",
                "transitionSignal": "COMBINED_RELATIONSHIP_EVIDENCE",
                "nextPhase": "TEASE",
            },
        })
        return replace(
            decision,
            decision=CustomerSalesDecisionType.TEASE,
            reason_code=CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY,
            reason_summary=(
                "Sustained voluntary relationship engagement authorizes one "
                "low-pressure Ava-initiated tease without a paid offer."
            ),
            sell_allowed=False,
            nudge_allowed=False,
            decision_metadata=immutable_mapping(metadata),
        )

    def record_unmapped_progression(self, decision, *, correlation_id):
        """Persist an unmapped decision without making prospect state authoritative for identity."""
        if decision is None or decision.identity_resolved:
            return None
        metadata = dict(decision.decision_metadata or {})
        progression = metadata.get("salesProgression")
        if (
            not isinstance(progression, Mapping)
            or decision.telegram_user_id is None
            or int(decision.fanvue_account_id or 0) <= 0
            or not correlation_id
        ):
            return None
        if self.unmapped_prospects is None:
            from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
            self.unmapped_prospects = UnmappedTelegramProspectService()
        return self.unmapped_prospects.record_sales_progression(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            telegram_user_id=decision.telegram_user_id,
            progression=progression,
            correlation_id=correlation_id,
        )

    def _deferred_continuation(self, *, creator_profile_id,
                               fanvue_account_id, telegram_user_id):
        if telegram_user_id is None:
            return None
        if self.unmapped_prospects is None:
            return None
        prospect = self.unmapped_prospects.repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        return self.unmapped_prospects.deferred_continuation(prospect) if prospect else None

    def claim_deferred_continuation(self, decision, *, correlation_id):
        metadata = dict(getattr(decision, "decision_metadata", {}) or {})
        deferred = dict(metadata.get("deferredContinuation") or {})
        if deferred.get("state") != "READY" or decision.telegram_user_id is None:
            return decision
        if decision.decision not in {
            CustomerSalesDecisionType.PRESENT_OFFER,
            CustomerSalesDecisionType.UPSELL,
            CustomerSalesDecisionType.CROSS_SELL,
        }:
            return decision
        claimed = self.unmapped_prospects.claim_deferred_continuation(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            telegram_user_id=decision.telegram_user_id,
            correlation_id=correlation_id,
        )
        if claimed is None:
            return replace(
                decision, decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason_code=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                reason_summary="Deferred continuation was already claimed by another turn.",
                sell_allowed=False, upsell_allowed=False, cross_sell_allowed=False,
            )
        updated = dict(metadata)
        updated["deferredContinuation"] = {
            **deferred, "state": "CLAIMED", "claimCorrelationId": correlation_id,
        }
        return replace(decision, decision_metadata=immutable_mapping(updated))

    def invalidate_deferred_continuation(self, decision, *, reason):
        if decision.telegram_user_id is None or self.unmapped_prospects is None:
            return None
        return self.unmapped_prospects.invalidate_deferred_continuation(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            telegram_user_id=decision.telegram_user_id,
            reason=reason,
        )

    def _session_proposal(self, *, creator_profile_id, fanvue_account_id,
                          telegram_user_id):
        if telegram_user_id is None:
            return None
        if self.unmapped_prospects is None:
            from app.services.unmapped_telegram_prospect_service import (
                UnmappedTelegramProspectService,
            )
            self.unmapped_prospects = UnmappedTelegramProspectService()
        prospect = self.unmapped_prospects.repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        proposal = (
            self.unmapped_prospects.session_proposal(prospect)
            if prospect else None
        )
        if proposal and proposal.get("state") == "PENDING":
            expires_at = proposal.get("expiresAt")
            try:
                expired = bool(
                    expires_at
                    and self.clock() >= datetime.fromisoformat(
                        str(expires_at).replace("Z", "+00:00")
                    )
                )
            except (TypeError, ValueError):
                expired = True
            if expired:
                self.unmapped_prospects.transition_session_proposal(
                    creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,
                    telegram_user_id=telegram_user_id,
                    target_state="EXPIRED", reaction="NONE",
                    invalidation_reason="PROPOSAL_RESPONSE_WINDOW_EXPIRED",
                )
                return None
        return proposal

    def confirm_session_proposal_delivery(
        self, decision, *, correlation_id, provider_message_id=None,
        delivered_at=None,
    ):
        """Make a Session proposal pending only after confirmed delivery."""
        if (
            decision is None
            or decision.decision is not CustomerSalesDecisionType.PROPOSE_SESSION
            or decision.telegram_user_id is None
        ):
            return None
        if self.unmapped_prospects is None:
            from app.services.unmapped_telegram_prospect_service import (
                UnmappedTelegramProspectService,
            )
            self.unmapped_prospects = UnmappedTelegramProspectService()
        metadata = dict(decision.decision_metadata or {})
        proposal_context = dict(metadata.get("sessionProposalContext") or {})
        delivered_at = delivered_at or self.clock()
        return self.unmapped_prospects.record_session_proposal(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            telegram_user_id=decision.telegram_user_id,
            correlation_id=correlation_id,
            source_inbound=correlation_id,
            delivery_correlation_id=correlation_id,
            delivery_provider_message_id=provider_message_id,
            session_offering_id=proposal_context.get("offeringId"),
            delivered_at=delivered_at,
            expires_at=delivered_at + self.config.purchase_cooldown,
        )

    def record_session_proposal(self, decision, *, correlation_id):
        if (
            decision is None
            or decision.telegram_user_id is None
        ):
            return None
        if self.unmapped_prospects is None:
            from app.services.unmapped_telegram_prospect_service import (
                UnmappedTelegramProspectService,
            )
            self.unmapped_prospects = UnmappedTelegramProspectService()
        metadata = dict(decision.decision_metadata or {})
        escalation = dict(metadata.get("sessionEscalation") or {})
        reaction = escalation.get("sessionProposalCustomerReaction")
        # PROPOSE_SESSION is persisted only by confirmed delivery. Merely
        # authorizing or generating proposal wording is not customer truth.
        if decision.decision is CustomerSalesDecisionType.PROPOSE_SESSION:
            return None
        target = {
            "ACCEPT_OR_LEAN_IN": "ACCEPTED",
            "DECLINE_SESSION_BUT_WANTS_MORE": "DECLINED_DISCRETE",
            "DECLINE_AND_STOP": "DECLINED_STOP",
        }.get(reaction)
        invalidation_reason = escalation.get(
            "sessionProposalInvalidationReason"
        )
        if target is None and invalidation_reason:
            target = "INVALIDATED"
        if target:
            return self.unmapped_prospects.transition_session_proposal(
                creator_profile_id=decision.creator_profile_id,
                fanvue_account_id=decision.fanvue_account_id,
                telegram_user_id=decision.telegram_user_id,
                target_state=target, reaction=reaction or "NONE",
                reaction_source_inbound=correlation_id,
                invalidation_reason=invalidation_reason,
            )
        return None

    def evaluate_for_buyer(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_buyer_uuid: UUID,
        telegram_user_id: int | None, identity_resolved: bool,
        conversation_context: dict | None = None, _started=None,
    ) -> CustomerSalesDecision:
        started = _started if _started is not None else time.perf_counter()
        now = self.clock()
        identity_reader = getattr(self.identities, "get_by_external_fanvue_user_uuid", None)
        identity_mapping = identity_reader(
            fanvue_account_id, external_fanvue_buyer_uuid) if identity_reader else None
        deferred_continuation = None
        deferred_continuation_loaded = False
        if identity_mapping is not None:
            deferred_continuation = self._deferred_continuation(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
            )
            deferred_continuation_loaded = True
            safety = self.customer_safety.decide(
                creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
                fanvue_user_id=identity_mapping.local_fanvue_user_id)
            if not safety.allowed:
                if (
                    deferred_continuation
                    and deferred_continuation.get("state") in {
                        "PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"
                    }
                ):
                    self.unmapped_prospects.invalidate_deferred_continuation(
                        creator_profile_id=creator_profile_id,
                        fanvue_account_id=fanvue_account_id,
                        telegram_user_id=telegram_user_id,
                        reason="CUSTOMER_INTERACTION_SAFETY_BLOCKED",
                    )
                return self._finish(started, now, creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id, buyer_uuid=external_fanvue_buyer_uuid,
                    telegram_user_id=telegram_user_id, identity_resolved=identity_resolved,
                    decision=CustomerSalesDecisionType.NO_SALE,
                    reason=CustomerSalesReasonCode.CUSTOMER_INTERACTION_SAFETY_BLOCKED,
                    summary="Customer autonomous sales interaction is blocked by authoritative safety state.",
                    stage=CustomerBuyerStage.UNKNOWN)
        context = dict(conversation_context or {})
        if identity_mapping is not None:
            context.setdefault("fanvue_user_id", identity_mapping.local_fanvue_user_id)
        context.update(self._active_sales_session_context(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=external_fanvue_buyer_uuid,
        ))
        if not identity_resolved or telegram_user_id is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                buyer_uuid=external_fanvue_buyer_uuid,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.IDENTITY_UNRESOLVED,
                summary="Buyer identity is not linked to Telegram.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        if not deferred_continuation_loaded:
            deferred_continuation = self._deferred_continuation(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
            )
        if deferred_continuation:
            created_at = deferred_continuation.get("createdAt")
            try:
                stale = bool(
                    created_at
                    and datetime.fromisoformat(str(created_at))
                    < now - self.config.purchase_cooldown
                )
            except (TypeError, ValueError):
                stale = True
            if (
                stale
                and deferred_continuation.get("state") in {
                    "PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"
                }
            ):
                self.unmapped_prospects.invalidate_deferred_continuation(
                    creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,
                    telegram_user_id=telegram_user_id,
                    reason="PURCHASE_COOLDOWN_WINDOW_EXPIRED",
                )
                deferred_continuation = {
                    **deferred_continuation,
                    "state": "INVALIDATED",
                    "reason": "PURCHASE_COOLDOWN_WINDOW_EXPIRED",
                }
            if (
                deferred_continuation.get("state") == "CLAIMED"
                and str(deferred_continuation.get("claimCorrelationId") or "")
                != str(context.get("conversation_id") or "")
            ):
                deferred_continuation = {}
            context["deferred_continuation"] = deferred_continuation
        session_proposal = self._session_proposal(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        if session_proposal:
            context["session_proposal"] = session_proposal
            from app.services.session_escalation_decision_service import (
                SessionEscalationDecisionService,
            )
            preliminary_reaction = (
                SessionEscalationDecisionService.proposal_reaction(
                    str(context.get("latest_message") or ""),
                    proposal_pending=True,
                )
            )
            if preliminary_reaction == "DECLINE_AND_STOP":
                context["session_escalation"] = {
                    "sessionProposalAuthorized": False,
                    "sessionProposalDelivered": True,
                    "sessionProposalPending": False,
                    "sessionProposalCustomerReaction": preliminary_reaction,
                    "sessionEscalationDecision": "NO_FURTHER_SALE_NOW",
                    "sessionEscalationReason": "SAFETY_OR_CUSTOMER_STOP",
                    "sessionStartAuthorityEligible": False,
                    "sessionStarted": False,
                }
        profile = self.customers.get_by_buyer_uuid(
            creator_profile_id=creator_profile_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
        )
        if profile is None and hasattr(self.customers, "get_or_create"):
            profile = self.customers.get_or_create(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                external_fanvue_user_uuid=external_fanvue_buyer_uuid,
                seen_at=now,
                display_name=None,
                handle=None,
            )
            if hasattr(self.customers, "update_profile"):
                profile = self.customers.update_profile(
                    profile.customer_commerce_profile_id,
                    display_name=profile.display_name,
                    handle=profile.handle,
                    profile_state=profile.profile_state,
                    telegram_identity_mapping_id=(
                        self.identities.get_by_telegram_user_id(
                            telegram_user_id
                        ).id
                    ),
                    telegram_user_id=telegram_user_id,
                )
            logger.info(
                "event=customer_commerce_prospect_onboarded "
                "creator_profile_id=%s telegram_user_id=%s",
                creator_profile_id, telegram_user_id,
            )
        if profile is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                buyer_uuid=external_fanvue_buyer_uuid,
                telegram_user_id=telegram_user_id, identity_resolved=True,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.NO_COMMERCE_PROFILE,
                summary="No Customer Commerce profile exists for this buyer.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        stage = self.buyer_stage(profile.purchase_count)
        signal = self.signals.get_signal(
            creator_profile_id=creator_profile_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
        )
        signal_data = self._signal(signal)
        latest = self.intents.get_latest_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        active = self.intents.get_active_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        context.update(self._commercial_opportunity_evidence(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            latest=latest,
        ))
        memory = self.customer_commerce_memory.build(
            identity=OwnershipIdentity(
                creator_profile_id=int(creator_profile_id),
                fanvue_account_id=int(fanvue_account_id),
                external_fanvue_user_uuid=external_fanvue_buyer_uuid,
                telegram_user_id=telegram_user_id,
                legacy_fanvue_user_id=(
                    str(context["fanvue_user_id"])
                    if context.get("fanvue_user_id") is not None else None
                ),
                core_user_id=context.get("core_user_id"),
            ),
            customer_profile=profile,
            active_purchase_intent=active,
        )
        context["_customer_commerce_memory"] = memory
        context["customer_commerce_memory_summary"] = self._commerce_memory_summary(memory)
        common = dict(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            buyer_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            identity_resolved=True, stage=stage,
            signal=signal_data, active=active, latest=latest,
            progression_context=context,
        )
        tone = dict(context.get("contextual_customer_tone") or {})
        if tone.get("explicitDisengagement") is True:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="An explicit customer boundary overrides relationship value.",
            )
        if (
            tone.get("rageBaitPattern") is True
            and int(tone.get("priorExplicitDisengagementCount") or 0) > 0
            and not self.conversational_progression.has_direct_purchase_intent(
                str(context.get("latest_message") or "")
            )
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="Repeated abuse cannot reopen a conversation after a customer boundary.",
            )
        if (
            str(dict(context.get("sales_progression") or {}).get("phase") or "").upper()
            == "BACK_OFF"
            and not self.conversational_progression.has_direct_purchase_intent(
                str(context.get("latest_message") or "")
            )
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="Current-conversation BACK_OFF remains authoritative without fresh direct intent.",
            )
        cooldown_until = (
            profile.last_purchase_at + self.config.purchase_cooldown
            if profile.last_purchase_at else None
        )
        cooldown_active = bool(cooldown_until and now < cooldown_until)
        receptiveness = self.commercial_receptiveness.evaluate(
            context=context,
            recent_purchase=cooldown_active,
            cooldown_active=cooldown_active,
            active_offer=active is not None,
        )
        active_offer_continuation_type = (
            self.commercial_receptiveness.active_offer_continuation_type(
                str(context.get("latest_message") or "")
            ) if active is not None else None
        )
        context["active_offer_continuation"] = {
            "customerInitiatedOfferContinuation": bool(
                active_offer_continuation_type
            ),
            "continuationIntentType": active_offer_continuation_type,
            "nudgeCooldownApplies": not bool(active_offer_continuation_type),
            "structuredOfferReused": bool(active_offer_continuation_type),
            "structuredOfferRedelivered": False,
            "purchaseIntentReused": bool(active_offer_continuation_type),
            "relationshipDiscoverySuppressed": bool(
                active_offer_continuation_type
            ),
        }
        context["commercial_receptiveness"] = dict(receptiveness.to_mapping())
        context["purchase_cooldown_active"] = cooldown_active
        context["purchase_cooldown_until"] = (
            cooldown_until.isoformat() if cooldown_until else None
        )
        context["purchase_cooldown_blocking"] = bool(
            cooldown_active and not receptiveness.fresh_direct_intent
        )
        context["purchase_cooldown_override"] = bool(
            cooldown_active and receptiveness.fresh_direct_intent
        )
        context["purchase_cooldown_override_reason"] = (
            receptiveness.reason
            if context["purchase_cooldown_override"] else None
        )
        from app.services.active_buying_window_service import ActiveBuyingWindowService
        explicit_continuation = (
            self.commercial_receptiveness.explicit_continuation_detected(
                str(context.get("latest_message") or "")
            )
        )
        deferred_state = dict(
            context.get("deferred_continuation") or {}
        ).get("state")
        context["active_buying_window"] = ActiveBuyingWindowService.project(
            recent_verified_purchase=bool(
                int(dict(context.get(
                    "customer_commerce_memory_summary"
                ) or {}).get("recentPurchaseCount") or 0)
            ),
            fresh_direct_intent=receptiveness.fresh_direct_intent,
            explicit_continuation=explicit_continuation,
            active_purchase_intent=active is not None,
            active_offer_context=str(dict(
                context.get("sales_progression") or {}
            ).get("phase") or "").upper() == "PRESENT_OFFER",
            acknowledgement_pending=bool(
                context.get("purchase_acknowledgement_pending")
            ),
            declined=bool(context.get("offer_declined")),
            safety_allowed=True,
            active_session=bool(context.get("sales_session_id")),
            cooldown_active=cooldown_active,
            receptiveness=receptiveness.to_mapping(),
            deferred_continuation=context.get("deferred_continuation"),
        )
        context["explicit_continuation_detected"] = explicit_continuation
        context["deferred_continuation_pending"] = deferred_state in {
            "PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"
        }
        objection = self.commercial_objections.evaluate(
            message=str(context.get("latest_message") or ""), context=context,
        )
        context["commercial_objection"] = self._objection_diagnostics(
            objection, active or latest, context,
        )
        self._apply_objection_ranking_context(context, objection)
        opportunity = self._apply_photoshoot_opportunity_policy(
            creator_profile_id=creator_profile_id,
            customer_profile=profile,
            context=context,
        )
        if opportunity is not None and opportunity.status.value in {"OBJECTION", "CLOSED", "DECLINED"} and active is not None:
            abandon = getattr(self.intents, "mark_abandoned", None)
            if callable(abandon):
                try:
                    abandon(active.purchase_intent_id, at=now)
                    active = None
                    common["active"] = None
                except Exception as error:
                    logger.warning("event=photoshoot_opportunity_intent_close_failed error_type=%s", type(error).__name__)

        # Priority 2: verified provider payment is still reconciling.
        if signal and signal.reconciliation_state == "PENDING":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.PAYMENT_PENDING,
                reason=CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING,
                summary="A provider payment is awaiting earnings reconciliation.",
            )
        # Priority 3: deterministic payment evidence was ambiguous.
        if (
            (signal and signal.attribution_state == "UNKNOWN")
            or (latest and latest.attribution_result.value == "UNKNOWN")
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN,
                summary="Payment attribution did not produce one hard match.",
            )
        # Priority 4: acknowledgement is explicit deterministic context.
        if latest and latest.status.value == "PURCHASED" and context.get(
            "purchase_acknowledgement_pending"
        ) is True:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
                reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
                summary="A verified purchase is awaiting acknowledgement.",
                congratulate_allowed=True,
            )
        if objection.objection_type is CommercialObjectionType.PAYMENT_TECHNICAL:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.PAYMENT_SUPPORT_REQUIRED,
                summary=("A payment or link issue is not a rejection; the "
                         "authoritative offer remains unchanged."),
            )
        if objection.objection_type in {
            CommercialObjectionType.GLOBAL_DECLINE,
            CommercialObjectionType.TRUST_OR_SUPPORT,
        }:
            return self._objection_stop(started, now, common, context, objection)
        if objection.recovery_strategy == "VALUE_DEFENSE":
            return self._value_defense(started, now, common, context, objection,
                                       active or latest)
        if objection.objection_type is CommercialObjectionType.TEMPORARY_HESITATION:
            return self._objection_stop(
                started, now, common, context, objection,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
            )
        # Priority 5: cooldown controls unsolicited pressure, but fresh direct
        # intent remains authoritative for a new ownership-safe opportunity.
        if (
            cooldown_active
            and not receptiveness.fresh_direct_intent
            and dict(context.get("session_proposal") or {}).get("state") != "PENDING"
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN,
                summary=(
                    "Recent purchase cooldown limits unsolicited sales pressure; "
                    "no fresh direct buying intent overrides it."
                ),
                cooldown_until=cooldown_until,
            )
        # Priority 6/7: active offer wait then nudge.
        if active and objection.consider_alternative:
            abandon = getattr(self.intents, "mark_abandoned", None)
            if callable(abandon):
                abandon(active.purchase_intent_id, at=now)
            active = None
            common["active"] = None
        if active:
            presented = active.presented_at or active.created_at
            nudge_at = presented + self.config.offer_nudge_delay
            if active_offer_continuation_type:
                selection = self.offering_selector.select(
                    creator_profile_id=creator_profile_id,
                    telegram_user_id=telegram_user_id,
                    customer_profile=profile,
                    commerce_signal=signal,
                    active_purchase_intent=active,
                    conversation_context={
                        **context, "primary_sales_channel": "AI_CHAT",
                    },
                )
                return self._finish(
                    started, now, **common,
                    decision=CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
                    reason=(CustomerSalesReasonCode
                            .CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION),
                    summary=(
                        "The customer explicitly requested the current offer; "
                        "reuse its structured presentation without applying "
                        "the unsolicited-nudge cooldown."
                    ),
                    nudge_allowed=True, recommendation=selection,
                    selector_result=selection,
                )
            if receptiveness.fresh_direct_intent:
                selection = self.offering_selector.select(
                    creator_profile_id=creator_profile_id,
                    telegram_user_id=telegram_user_id,
                    customer_profile=profile,
                    commerce_signal=signal,
                    active_purchase_intent=active,
                    conversation_context={
                        **context, "primary_sales_channel": "AI_CHAT",
                    },
                )
                return self._finish(
                    started, now, **common,
                    decision=CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
                    reason=CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
                    summary=(
                        "Fresh direct intent authorizes closing the existing "
                        "authoritative offer without waiting for the timer."
                    ),
                    nudge_allowed=True, recommendation=selection,
                    selector_result=selection,
                )
            if now < nudge_at:
                return self._finish(
                    started, now, **common,
                    decision=CustomerSalesDecisionType.WAIT,
                    reason=(
                        CustomerSalesReasonCode
                        .ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE
                    ),
                    summary="The active offer is still in its waiting period.",
                    cooldown_until=nudge_at,
                )
            selection = self.offering_selector.select(
                creator_profile_id=creator_profile_id,
                telegram_user_id=telegram_user_id,
                customer_profile=profile,
                commerce_signal=signal,
                active_purchase_intent=active,
                conversation_context={
                    **context, "primary_sales_channel": "AI_CHAT",
                },
            )
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
                reason=CustomerSalesReasonCode.ACTIVE_OFFER_NUDGE_ELIGIBLE,
                summary="The active offer is eligible for deterministic follow-up.",
                nudge_allowed=True, recommendation=selection,
                selector_result=selection,
            )
        # Priority 8: explicit expired intent.
        if latest and latest.status.value == "EXPIRED":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED,
                summary="The latest offer expired without a verified purchase.",
            )
        conversational_backoff = (
            None if objection.consider_alternative
            else self.conversational_progression.back_off_reason(context)
        )
        if conversational_backoff is not None:
            base = self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=conversational_backoff,
                summary="Customer response requires backing off the current opportunity.",
            )
            state = dict(context.get("sales_progression") or {})
            return replace(
                base,
                decision_metadata=immutable_mapping({
                    **dict(base.decision_metadata),
                    "salesProgression": {
                        **state, "phase": "BACK_OFF",
                        "reasonCode": conversational_backoff.value,
                    },
                }),
            )
        if not objection.consider_alternative and (
            context.get("offer_declined") is True
            or (
                latest and latest.status.value == "ABANDONED"
                and getattr(latest, "updated_at", now)
                >= now - self.config.purchase_cooldown
            )
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                summary="A recent decline suppresses replacement sales pressure.",
            )
        selector_relevant, selector_reason = self._commerce_selection_relevant(
            context, objection=objection,
        )
        if dict(context.get("session_proposal") or {}).get("state") == "PENDING":
            selector_relevant = True
            selector_reason = "SESSION_PROPOSAL_REACTION_PENDING"
        context["selector_invocation_reason"] = selector_reason
        if not selector_relevant:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                summary="Ordinary relationship conversation does not invoke commerce inventory selection.",
            )
        # Priority 9/10: deterministic selector chooses one offering or none.
        intelligence = self._commercial_intelligence_decision(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            conversation_context=context,
            core_user_id=(
                getattr(profile, "core_user_id", None)
                or context.get("core_user_id")
            ),
        )
        recovery_constraints = self._recovery_constraints(
            objection, latest, base=(
                intelligence.constraints
                if intelligence.strategy is not None else StrategyConstraints()
            ),
        )
        from app.services.session_escalation_decision_service import (
            SessionEscalationDecisionService,
        )
        window = dict(context.get("active_buying_window") or {})
        deferred = dict(context.get("deferred_continuation") or {})
        proposal = dict(context.get("session_proposal") or {})
        memory_summary = dict(
            context.get("customer_commerce_memory_summary") or {}
        )
        session_intent = SessionEscalationDecisionService.continuation_intent(
            str(context.get("latest_message") or "")
        )
        if session_intent == "NONE" and deferred.get("state") in {"READY", "CLAIMED"}:
            session_intent = str(deferred.get("continuationType") or "NONE")
        session_constraints = replace(
            recovery_constraints,
            required_selling_modes=("SESSION",),
            excluded_selling_modes=(),
        )
        session_selection = None
        if (
            int(profile.purchase_count or 0) >= 2
            and (session_intent == "ONGOING_EXPERIENCE" or proposal.get("state") == "PENDING")
        ):
            session_selection = self.offering_selector.select(
                creator_profile_id=creator_profile_id,
                telegram_user_id=telegram_user_id,
                customer_profile=profile,
                commerce_signal=signal,
                active_purchase_intent=None,
                conversation_context={
                    **context, "primary_sales_channel": "AI_CHAT",
                },
                strategy_constraints=session_constraints,
                strategy="SESSION_SELLING",
            )
        ordinary_constraints = replace(
            recovery_constraints,
            required_selling_modes=(),
            excluded_selling_modes=("SESSION",),
        )
        selection = self.offering_selector.select(
            creator_profile_id=creator_profile_id,
            telegram_user_id=telegram_user_id,
            customer_profile=profile,
            commerce_signal=signal,
            active_purchase_intent=active,
            conversation_context={
                **context, "primary_sales_channel": "AI_CHAT",
            },
            strategy_constraints=ordinary_constraints,
            strategy=(
                intelligence.strategy.value
                if intelligence.strategy is not None else "LIBRARY_SELLING"
            ),
        )
        session_escalation = SessionEscalationDecisionService.project(
            active_buying_window=bool(window.get("active")),
            purchase_count=int(profile.purchase_count or 0),
            recent_purchase_count=int(
                memory_summary.get("recentPurchaseCount")
                or profile.purchase_count or 0
            ),
            current_message=str(context.get("latest_message") or ""),
            explicit_continuation_count=int(
                context.get("explicit_continuation_count")
                or (1 if context.get("explicit_continuation_detected") else 0)
            ),
            session_inventory_available=bool(
                session_selection and session_selection.offering_id
            ),
            ordinary_inventory_available=bool(selection.offering_id),
            active_purchase_intent=active is not None,
            active_session=bool(context.get("sales_session_id")),
            rejection_or_back_off=bool(context.get("offer_declined")),
            safety_allowed=True,
            proposal_pending=proposal.get("state") == "PENDING",
            deferred_continuation=deferred,
        )
        if proposal.get("state") == "PENDING" and bool(
            context.get("sales_session_id")
        ):
            session_escalation["sessionProposalInvalidationReason"] = (
                "ACTIVE_SESSION_PRECEDENCE"
            )
        elif proposal.get("state") == "PENDING" and session_selection is None:
            session_escalation.update({
                "sessionProposalPending": False,
                "sessionProposalInvalidationReason": (
                    "SESSION_INVENTORY_NO_LONGER_AVAILABLE"
                ),
            })
        proposal_reaction = session_escalation.get(
            "sessionProposalCustomerReaction"
        )
        proposal_consumed = proposal_reaction in {
            "ACCEPT_OR_LEAN_IN", "DECLINE_SESSION_BUT_WANTS_MORE",
            "DECLINE_AND_STOP",
        }
        session_escalation.update({
            "sessionProposalDelivered": bool(proposal.get("delivered")),
            "sessionProposalId": proposal.get("proposalId"),
            "sessionProposalSourceInbound": proposal.get("sourceInbound"),
            "sessionProposalCreatedAt": proposal.get("createdAt"),
            "sessionProposalExpiresAt": proposal.get("expiresAt"),
            "sessionProposalReactionSourceInbound": (
                str(
                    context.get("conversation_id")
                    or context.get("correlation_id") or ""
                ) or None
                if proposal_consumed else None
            ),
            "sessionProposalConsumed": proposal_consumed,
            "sessionProposalInvalidationReason": (
                session_escalation.get("sessionProposalInvalidationReason")
                or proposal.get("invalidationReason")
            ),
            "purchaseCooldownActive": cooldown_active,
            "purchaseCooldownSuppressedForProposalReaction": bool(
                cooldown_active and proposal_reaction != "NONE"
            ),
            "scenarioInfluencedCommercialAuthority": False,
        })
        context["session_escalation"] = session_escalation
        context["session_proposal_context"] = {
            "offeringId": (
                str(session_selection.offering_id)
                if session_selection and session_selection.offering_id else None
            ),
            "title": session_selection.title if session_selection else None,
            "description": (
                session_selection.short_description if session_selection else None
            ),
            "photoshootExperience": (
                session_selection.photoshoot_experience.to_mapping()
                if session_selection is not None
                and session_selection.photoshoot_experience is not None
                and hasattr(session_selection.photoshoot_experience, "to_mapping")
                else None
            ),
        }
        escalation_decision = session_escalation["sessionEscalationDecision"]
        if escalation_decision == "PROPOSE_SESSION":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.PROPOSE_SESSION,
                reason=(CustomerSalesReasonCode.SESSION_PROPOSAL_PENDING
                        if proposal.get("state") == "PENDING"
                        else CustomerSalesReasonCode.SESSION_PROPOSAL_AUTHORIZED),
                summary=(
                    "Repeated customer-led purchases and ongoing-experience "
                    "intent authorize a natural Session bridge, not a Session start."
                ),
            )
        if escalation_decision == "SESSION_ACCEPTED":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.SESSION_ACCEPTED,
                summary=(
                    "Customer acceptance reached the canonical Session-entry "
                    "boundary; no ordinary PurchaseIntent is authorized."
                ),
            )
        if (
            intelligence.strategy is None
            and escalation_decision != "CONTINUE_DISCRETE_PPVS"
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.NO_SELLING_STRATEGY,
                summary=intelligence.reason_summary,
                commercial_intelligence=intelligence,
            )
        if selection.offering_id:
            recovery = (
                objection.consider_alternative
                and not cooldown_active
                and not (
                    latest is not None
                    and getattr(getattr(latest, "status", None), "value", None)
                    == "PURCHASED"
                )
            )
            next_kind = self._next_offer_kind(
                objection=objection, latest=latest, selection=selection,
                receptiveness=receptiveness,
            )
            selected_decision = self._finish(
                started, now, **common,
                decision=(CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
                          if recovery else next_kind),
                reason=(self._objection_reason(objection) if recovery
                        else CustomerSalesReasonCode.NO_ACTIVE_OFFER),
                summary=(
                    "No offer is active and the deterministic selector "
                    "found one live offering."
                ),
                recommendation=selection, selector_result=selection,
                sell_allowed=True,
                upsell_allowed=next_kind is CustomerSalesDecisionType.UPSELL,
                cross_sell_allowed=next_kind is CustomerSalesDecisionType.CROSS_SELL,
                commercial_intelligence=intelligence,
            )
            if recovery:
                return self._decorate_recovery(
                    selected_decision, objection, selection,
                )
            readiness = None
            fanvue_user_id = context.get("fanvue_user_id")
            thread_id = context.get("conversation_thread_id")
            if fanvue_user_id is not None and thread_id is not None:
                readiness = self.adaptive_sales_readiness.evaluate(
                    creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id,
                    fanvue_user_id=int(fanvue_user_id),
                    conversation_thread_id=int(thread_id),
                    buyer_stage=stage.value, purchase_count=profile.purchase_count,
                    context=context,
                )
            if readiness is None:
                return self.conversational_progression.refine(selected_decision, context)
            reason_map = {
                "DIRECT_PURCHASE_INTENT_BYPASS": CustomerSalesReasonCode.ADAPTIVE_DIRECT_INTENT_BYPASS,
                "ADAPTIVE_READINESS_AUTHORIZED": CustomerSalesReasonCode.ADAPTIVE_READINESS_AUTHORIZED,
                "COLD_BEYOND_BENCHMARK": CustomerSalesReasonCode.ADAPTIVE_COLD_BEYOND_BENCHMARK,
                "ACTIVE_SESSION_PRECEDENCE": CustomerSalesReasonCode.ACTIVE_SESSION_PRECEDENCE,
            }
            if readiness.authorized:
                selected_decision = replace(selected_decision,
                    reason_code=reason_map.get(readiness.reason_code,
                                               CustomerSalesReasonCode.ADAPTIVE_READINESS_AUTHORIZED),
                    decision_metadata=immutable_mapping({**dict(selected_decision.decision_metadata),
                        "adaptiveSalesReadiness": self._readiness_metadata(readiness)}))
                result = self.conversational_progression.refine(selected_decision, context)
            else:
                result = replace(selected_decision,
                    decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                    reason_code=reason_map.get(readiness.reason_code,
                                               CustomerSalesReasonCode.ADAPTIVE_WARMUP_CONTINUE),
                    reason_summary=("Adaptive readiness continues rapport-building; the advisory "
                                    "message benchmark does not independently authorize a sale."),
                    sell_allowed=False,
                    decision_metadata=immutable_mapping({**dict(selected_decision.decision_metadata),
                        "adaptiveSalesReadiness": self._readiness_metadata(readiness)}))
            correlation = context.get("conversation_id")
            if correlation:
                self.adaptive_sales_readiness.persist(readiness,
                    correlation_id=correlation, creator_profile_id=creator_profile_id,
                    fanvue_account_id=fanvue_account_id, fanvue_user_id=int(fanvue_user_id),
                    conversation_thread_id=int(thread_id),
                    selected_offering_id=selection.offering_id,
                    selected_publication_id=selection.publication_id,
                    resulting_sales_action=result.decision.value)
            return result
        return self._finish(
            started, now, **common,
            decision=CustomerSalesDecisionType.NO_SALE,
            reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
            summary="No active, live, deliverable offering is available.",
            selector_result=selection,
            commercial_intelligence=intelligence,
        )

    @staticmethod
    def _readiness_metadata(decision):
        return {
            "policyVersion": decision.policy_version,
            "warmupDepth": decision.warmup_depth,
            "benchmarkPosition": decision.benchmark_position,
            "customerSegment": decision.segment,
            "directIntent": decision.direct_intent,
            "strongReadiness": decision.strong_readiness,
            "decision": "AUTHORIZE_COMMERCIAL_PROGRESSION" if decision.authorized else "CONTINUE_CONVERSATION",
            "reasonCode": decision.reason_code,
            "evidence": decision.evidence,
            "suppressionEvidence": decision.suppression_evidence,
        }

    @staticmethod
    def _commerce_memory_summary(memory):
        return {
            "verifiedPurchaseCount": len(memory.purchase_events),
            "lifetimePurchaseCount": memory.purchase_count,
            "lifetimeGrossMinor": memory.lifetime_gross_minor,
            "lifetimeNetMinor": memory.lifetime_net_minor,
            "averageOrderValueMinor": memory.average_order_value_minor,
            "largestOrderMinor": memory.largest_order_minor,
            "ownedAssetIds": memory.owned_asset_ids,
            "ownedOfferingIds": tuple(str(value) for value in memory.owned_offering_ids),
            "ownedProductIds": tuple(str(value) for value in memory.owned_product_ids),
            "channels": memory.channels_purchased_through,
            "purchaseTypes": memory.purchase_type_history,
            "firstPurchaseAt": memory.first_purchase_at.isoformat() if memory.first_purchase_at else None,
            "lastPurchaseAt": memory.last_purchase_at.isoformat() if memory.last_purchase_at else None,
            "unmatchedTransactionCount": len(memory.unmatched_financial_evidence),
            "activePurchaseState": dict(memory.active_purchase_state),
            "recentVerifiedPurchaseEvidence": tuple({
                "sourceType": event.source_type,
                "sourceRecordId": event.source_record_id,
                "purchasedAt": event.purchased_at.isoformat(),
                "channel": event.channel,
                "saleType": event.sale_type,
                "offeringId": str(event.offering_id) if event.offering_id else None,
                "productId": str(event.product_id) if event.product_id else None,
                "assetIds": event.asset_ids,
                "grossMinor": event.gross_minor,
                "currency": event.currency,
            } for event in memory.purchase_events[-20:]),
            "affinity": {
                "offeringTypes": dict(memory.affinity.offering_type_weights),
                "tags": dict(memory.affinity.tag_weights),
                "channels": dict(memory.affinity.channel_weights),
                "typicalPriceMinMinor": memory.affinity.typical_price_min_minor,
                "typicalPriceMaxMinor": memory.affinity.typical_price_max_minor,
            },
            "insufficiencies": memory.attribution_insufficiencies,
            "conflicts": memory.conflicts,
            "provenance": tuple(dict.fromkeys(
                event.source_type for event in memory.purchase_events
            )),
        }

    def _commercial_intelligence_decision(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_buyer_uuid, telegram_user_id, conversation_context,
        core_user_id=None,
    ):
        identity = self.identities.get_by_telegram_user_id(telegram_user_id)
        local_fanvue_user_id = getattr(
            identity, "local_fanvue_user_id", None
        )
        session = self.sales_sessions.get_active_for_customer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=local_fanvue_user_id,
        ) if local_fanvue_user_id is not None else None
        session_intents = ()
        roles = ()
        historical_session = None
        selector_repository = getattr(self.offering_selector, "repository", None)
        candidates = (
            selector_repository.list_candidates(
                creator_profile_id=creator_profile_id,
                primary_sales_channel="AI_CHAT",
            )
            if selector_repository is not None else ()
        )
        bundle_compositions = tuple(
            {
                "photoshoot_reference": str(
                    candidate["photoshoot_identifiers"][0]
                ),
                "asset_ids": tuple(
                    int(value) for value in candidate.get("asset_ids") or ()
                ),
                "complete_set": (
                    len(candidate.get("asset_ids") or ())
                    == int(candidate.get("photoshoot_asset_count") or 0)
                    and int(candidate.get("photoshoot_asset_count") or 0) > 0
                ),
                "provenance": (
                    "CommercialOfferingAssetMembership",
                    "PhotoshootAssetMembership",
                ),
            }
            for candidate in candidates
            if str(candidate.get("offering_type") or "") == "BUNDLE"
            and len(candidate.get("photoshoot_identifiers") or ()) == 1
        )
        normalized_conversation = dict(conversation_context or {})
        intended_photoshoot = normalized_conversation.get(
            "requested_photoshoot_reference"
        )
        if intended_photoshoot is None:
            references = tuple(dict.fromkeys(
                value["photoshoot_reference"] for value in bundle_compositions
            ))
            intended_photoshoot = references[0] if len(references) == 1 else None
        if (
            session is None
            and intended_photoshoot is not None
            and local_fanvue_user_id is not None
            and hasattr(self.sales_sessions, "list_for_creator")
        ):
            historical_session = self._resolve_historical_session(
                self.sales_sessions.list_for_creator(
                    creator_profile_id=creator_profile_id, limit=100
                ),
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=local_fanvue_user_id,
                intended_photoshoot_reference=intended_photoshoot,
            )
        evidence_session = session or historical_session
        if session is not None and hasattr(
            self.sales_sessions, "list_purchase_intents"
        ):
            session_intents = self.sales_sessions.list_purchase_intents(
                session_id=session.sales_session_id,
                creator_profile_id=creator_profile_id,
            )
        elif historical_session is not None and hasattr(
            self.sales_sessions, "list_purchase_intents"
        ):
            session_intents = self.sales_sessions.list_purchase_intents(
                session_id=historical_session.sales_session_id,
                creator_profile_id=creator_profile_id,
            )
        if evidence_session is not None and hasattr(
            self.sales_sessions, "commercial_guidance"
        ):
            guidance = self.sales_sessions.commercial_guidance(
                session=evidence_session
            )
            roles = tuple(
                role
                for asset in guidance.get("assets") or ()
                for role in asset.get("effective_commercial_roles") or ()
            )
        available_types = tuple(
            str(candidate.get("offering_type") or "")
            for candidate in candidates
        )
        lineage_asset_ids = tuple(dict.fromkeys(
            int(asset_id)
            for candidate in candidates
            for asset_id in candidate.get("asset_ids") or ()
        ))
        if (
            not available_types
            and getattr(self.offering_selector, "offering", None) is not None
        ):
            available_types = ("SINGLE_IMAGE",)
        if "latest_message" not in normalized_conversation:
            normalized_conversation["latest_message"] = (
                "general request for existing content"
            )
        assembled = self.commercial_context.assemble(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            core_user_id=core_user_id,
            legacy_fanvue_user_id=local_fanvue_user_id,
            active_sales_session=session,
            relevant_historical_session=historical_session,
            session_purchase_intents=session_intents,
            available_offering_types=available_types,
            intended_photoshoot_reference=intended_photoshoot,
            bundle_compositions=bundle_compositions,
            approved_commercial_roles=roles,
            conversation_context=normalized_conversation,
            lineage_asset_ids=lineage_asset_ids,
        )
        return self.commercial_intelligence.recommend(assembled)

    @staticmethod
    def _resolve_historical_session(
        sessions, *, fanvue_account_id, fanvue_user_id,
        intended_photoshoot_reference,
    ):
        if intended_photoshoot_reference is None:
            return None
        return next(
            (
                item for item in sessions
                if item.fanvue_account_id == fanvue_account_id
                and item.fanvue_user_id == fanvue_user_id
                and item.commercial_foundation_reference
                == str(intended_photoshoot_reference)
            ),
            None,
        )

    def _active_sales_session_context(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_buyer_uuid,
    ) -> dict:
        try:
            identity = (
                self.identities.get_by_external_fanvue_user_uuid(
                    fanvue_account_id, external_fanvue_buyer_uuid
                )
            )
            if identity is None:
                return {}
            session = self.sales_sessions.get_active_for_customer(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=identity.local_fanvue_user_id,
            )
        except Exception as error:
            logger.warning(
                "event=sales_session_context_unavailable error_type=%s",
                type(error).__name__,
            )
            return {}
        if session is None:
            return {}
        return {
            "sales_session_id": str(session.sales_session_id),
            "sales_session_state": session.state.value,
            "sales_session_progression": session.progression_stage.value,
            "sales_session_foundation_type": getattr(
                session.commercial_foundation_type,
                "value", session.commercial_foundation_type,
            ),
            "sales_session_foundation": (
                session.commercial_foundation_reference
            ),
        }

    @staticmethod
    def refine_for_readiness(
        decision: CustomerSalesDecision,
        readiness: dict | None,
    ) -> CustomerSalesDecision:
        """Refine one immutable evaluation without another database read."""
        flags = dict(readiness or {})
        metadata = dict(decision.decision_metadata or {})
        configuration = dict(metadata.get("configuration") or {})
        projection = dict(metadata.get("sustainedSexualReceptiveness") or {})
        if projection.get("authority") == (
            CustomerSalesBrainService.SUSTAINED_SEXUAL_RECEPTIVENESS_AUTHORITY
        ):
            flags["sustained_sexual_receptiveness"] = bool(projection.get("value"))
        else:
            behavior = dict(dict(metadata.get("customerValueAttention") or {}).get(
                "behaviorEvidenceCounts"
            ) or {})
            flags["sustained_sexual_receptiveness"] = bool(
                behavior.get("sexual_engagement_only")
                and int(behavior.get("sexual_engagement_count") or 0)
                    >= int(configuration.get("sexualReceptivenessMinEngagements") or 4)
                and int(behavior.get("inbound_message_count") or 0)
                    >= int(configuration.get("sexualReceptivenessMinHistoryTurns") or 3)
                and int(behavior.get("rejection_count") or 0) == 0
            )
        if metadata.get("commercialReceptiveness"):
            receptiveness = CommercialReceptivenessService.refine_projection(
                metadata.get("commercialReceptiveness"), flags,
            )
            cooldown = dict(metadata.get("purchaseCooldown") or {})
            if (receptiveness.get("freshDirectIntentDetected")
                    and cooldown.get("active")):
                cooldown.update({
                    "blockingCurrentSale": False,
                    "override": True,
                    "overrideReason": receptiveness.get("reason"),
                })
            continuation = dict(metadata.get("continuation") or {})
            continuation.update({
                "eligible": bool(receptiveness.get("continuationEligible")),
                "anotherSaleAppropriateNow": bool(
                    receptiveness.get("anotherSaleAppropriateNow")
                ),
                "reason": receptiveness.get("reason"),
            })
            decision = replace(decision, decision_metadata=immutable_mapping({
                **metadata,
                "commercialReceptiveness": receptiveness,
                "purchaseCooldown": cooldown,
                "continuation": continuation,
            }))
        else:
            receptiveness = {}
        curiosity_only = bool(
            receptiveness.get("commercialInterestType")
                == "COMMERCIAL_CURIOSITY"
            and receptiveness.get("freshDirectIntentDetected") is not True
        )
        conversational_action = str(
            flags.get("recommended_conversational_action") or ""
        ).upper()
        explicitly_ready = (
            flags.get("conversation_ready_for_offer") is True
            or conversational_action == "PRESENT_OFFER"
        )
        if (
            not metadata.get("commercialReceptiveness")
            and explicitly_ready
            and decision.decision is CustomerSalesDecisionType.PRESENT_OFFER
        ):
            return decision
        progression = dict(decision.decision_metadata or {}).get(
            "salesProgression"
        ) or {}
        current_phase = str(progression.get("phase") or "").upper()
        transition = dict(decision.decision_metadata or {}).get(
            "salesProgressionTransition"
        ) or {}
        prior_phase = str(
            current_phase
            if decision.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
            and current_phase
            else transition.get("priorPhase") or current_phase or "CONVERSATIONAL"
        ).upper()
        opportunity = CustomerSalesBrainService._commercial_opportunity_assessment(
            decision, flags, progression=progression,
            conversational_action=conversational_action,
        )
        proactive = CustomerSalesBrainService._proactive_progression_assessment(
            decision, flags, progression=progression,
            opportunity=opportunity,
            conversational_action=conversational_action,
        )
        opportunity["proactiveProgression"] = proactive
        ready = explicitly_ready or opportunity["presentPreferred"]
        if (
            conversational_action == "BACK_OFF"
            and decision.recommended_offering_id is not None
            and decision.decision not in {
                CustomerSalesDecisionType.BACK_OFF,
                CustomerSalesDecisionType.MANUAL_REVIEW,
            }
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.BACK_OFF,
                reason_code=CustomerSalesReasonCode.CUSTOMER_DECLINED,
                reason_summary="Current conversational semantics require backing off.",
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression), "phase": "BACK_OFF",
                        "reasonCode": CustomerSalesReasonCode.CUSTOMER_DECLINED.value,
                    },
                    "recommendedConversationalAction": conversational_action,
                    "commercialOpportunity": opportunity,
                }),
            )
        classifier_support = bool(
            flags.get("escalation_ready") is True
            or flags.get("recommended_action") in {
                "build_tension", "offer", "close",
            }
            or flags.get("curiosity_level") in {"medium", "high"}
            or flags.get("engagement_level") in {"medium", "high"}
        )
        if (
            proactive["recentProactiveTease"]
            and decision.decision in {
                CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesDecisionType.NO_SALE,
                CustomerSalesDecisionType.TEASE,
            }
            and not opportunity["commercialAnchorPresent"]
        ):
            if conversational_action == "BACK_OFF":
                next_phase = "BACK_OFF"
                action = "BACK_OFF"
                reason = CustomerSalesReasonCode.CUSTOMER_DECLINED
                signal = "CUSTOMER_REJECTED_AVA_TEASE"
                cooldown = 0
            elif flags.get("positive_tease_response") is True and classifier_support:
                next_phase = "BUILD_INTEREST"
                action = "BUILD_INTEREST"
                reason = CustomerSalesReasonCode.BUILD_INTEREST
                signal = "POSITIVE_RESPONSE_TO_AVA_TEASE"
                cooldown = 0
            else:
                next_phase = "CONVERSATIONAL"
                action = "NONE"
                reason = CustomerSalesReasonCode.CURRENT_TURN_NOT_READY
                signal = "CUSTOMER_DID_NOT_LEAN_IN"
                cooldown = 2
            return replace(
                decision,
                decision=(
                    CustomerSalesDecisionType.BUILD_INTEREST
                    if next_phase == "BUILD_INTEREST" else
                    CustomerSalesDecisionType.BACK_OFF
                    if next_phase == "BACK_OFF" else
                    CustomerSalesDecisionType.CONTINUE_CONVERSATION
                ),
                reason_code=reason,
                reason_summary=(
                    "Customer response advances Ava's bounded proactive tease."
                    if next_phase == "BUILD_INTEREST" else
                    "Customer rejection ends Ava's proactive progression."
                    if next_phase == "BACK_OFF" else
                    "Customer did not lean into Ava's tease; return to ordinary conversation."
                ),
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression), "phase": next_phase,
                        "reasonCode": reason.value,
                        "progressionInitiator": "AVA",
                        "proactiveTeaseCooldownTurns": cooldown,
                        "awaitingCustomerResponse": False,
                    },
                    "salesProgressionTransition": {
                        "priorPhase": "TEASE",
                        "transitionSignal": signal,
                        "nextPhase": next_phase,
                    },
                    "proactiveProgression": {
                        **proactive,
                        "progressionAction": action,
                        "customerResponseToPreviousTease": (
                            "LEAN_IN" if next_phase == "BUILD_INTEREST"
                            else "GLOBAL_REJECT" if next_phase == "BACK_OFF"
                            else "IGNORE_OR_CHANGE_TOPIC"
                        ),
                    },
                    "commercialOpportunity": opportunity,
                }),
            )
        if (
            proactive["proactiveProgressionAuthorized"]
            and decision.decision in {
                CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesDecisionType.NO_SALE,
            }
            and not bool(dict(
                dict(decision.decision_metadata or {}).get(
                    "activeBuyingWindow"
                ) or {}
            ).get("anotherSaleAppropriateNow"))
            and not opportunity["commercialAnchorPresent"]
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.TEASE,
                reason_code=CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY,
                reason_summary=(
                    "Combined relationship evidence authorizes one low-pressure "
                    "Ava-initiated tease without asserting customer buying intent."
                ),
                sell_allowed=False,
                nudge_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression), "phase": "TEASE", "teaseCount": 1,
                        "reasonCode": CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY.value,
                        "progressionInitiator": "AVA",
                        "awaitingCustomerResponse": True,
                        "proactiveTeaseCooldownTurns": 0,
                        "teaseType": "PROACTIVE_RELATIONSHIP",
                    },
                    "salesProgressionTransition": {
                        "priorPhase": str(progression.get("phase") or "CONVERSATIONAL").upper(),
                        "transitionSignal": "COMBINED_RELATIONSHIP_EVIDENCE",
                        "nextPhase": "TEASE",
                    },
                    "proactiveProgression": proactive,
                    "teaseType": "PROACTIVE_RELATIONSHIP",
                    "recommendedConversationalAction": conversational_action,
                    "commercialOpportunity": opportunity,
                }),
            )
        if (
            current_phase == "TEASE"
            and flags.get("positive_tease_response") is True
            and classifier_support
            and (not ready or curiosity_only)
            and decision.recommended_offering_id is not None
            and decision.decision is not CustomerSalesDecisionType.BUILD_INTEREST
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.BUILD_INTEREST,
                reason_code=CustomerSalesReasonCode.BUILD_INTEREST,
                reason_summary=(
                    "Bounded classifier evidence supports the positive "
                    "response to an existing tease."
                ),
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression),
                        "phase": "BUILD_INTEREST",
                        "teaseCount": int(
                            progression.get("teaseCount") or 0
                        ) + 1,
                        "reasonCode": (
                            CustomerSalesReasonCode.BUILD_INTEREST.value
                        ),
                    },
                    "salesProgressionTransition": {
                        "priorPhase": "TEASE",
                        "transitionSignal": (
                            "POSITIVE_TEASE_RESPONSE_SUPPORTED"
                        ),
                        "nextPhase": "BUILD_INTEREST",
                    },
                    "commercialOpportunity": opportunity,
                }),
            )
        if (
            curiosity_only
            and current_phase == "BUILD_INTEREST"
            and decision.decision is CustomerSalesDecisionType.BUILD_INTEREST
        ):
            # A model may recommend closing while the customer's canonical
            # semantics still express curiosity only. Preserve the earned
            # BUILD_INTEREST step until a later actionable customer signal.
            return replace(
                decision,
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "recommendedConversationalAction": "BUILD_INTEREST",
                    "commercialOpportunity": opportunity,
                }),
            )
        if (
            decision.decision in {
                CustomerSalesDecisionType.TEASE,
                CustomerSalesDecisionType.BUILD_INTEREST,
                CustomerSalesDecisionType.CONTINUE_CONVERSATION,
            }
            and ready
            and decision.recommended_offering_id is not None
        ):
            progression = dict(decision.decision_metadata or {}).get(
                "salesProgression"
            ) or {}
            direct_intent = bool(
                not curiosity_only
                and (
                    flags.get("current_buying_intent") is True
                    or flags.get("classifier_buying_intent") is True
                    or (
                        flags.get("conversation_ready_for_offer") is True
                        and not conversational_action
                    )
                    or (
                        conversational_action == "PRESENT_OFFER"
                        and flags.get("recommended_action") in {"offer", "close"}
                    )
                )
            )
            presentation_reason = (
                CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT
                if direct_intent
                else CustomerSalesReasonCode.PRESENT_AFTER_POSITIVE_TEASE_RESPONSE
            )
            return replace(
                decision,
                decision=CustomerSalesDecisionType.PRESENT_OFFER,
                reason_code=presentation_reason,
                reason_summary=(
                    "Current commercial opportunity value exceeds the expected "
                    "benefit of another conversational or tease turn."
                ),
                sell_allowed=True,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression),
                        "phase": "PRESENT_OFFER",
                        "reasonCode": presentation_reason.value,
                    },
                    "salesProgressionTransition": {
                        "priorPhase": prior_phase,
                        "transitionSignal": "AI_RECOMMENDED_PRESENTATION",
                        "nextPhase": "PRESENT_OFFER",
                    },
                    "recommendedConversationalAction": (
                        conversational_action or "PRESENT_OFFER"
                    ),
                    "commercialOpportunity": opportunity,
                }),
            )
        if (
            conversational_action in {"CHAT", "FLIRT"}
            and decision.decision is CustomerSalesDecisionType.TEASE
            and prior_phase == "CONVERSATIONAL"
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason_code=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                reason_summary=(
                    "The eligible opportunity remains contextual; this turn "
                    "is ordinary conversation rather than an offer sequence."
                ),
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "salesProgression": {
                        **dict(progression), "phase": "CONVERSATIONAL",
                        "teaseCount": 0,
                        "reasonCode": CustomerSalesReasonCode.CURRENT_TURN_NOT_READY.value,
                    },
                    "salesProgressionTransition": {
                        "priorPhase": "CONVERSATIONAL",
                        "transitionSignal": conversational_action,
                        "nextPhase": "CONVERSATIONAL",
                    },
                    "recommendedConversationalAction": conversational_action,
                    "commercialOpportunity": opportunity,
                }),
            )
        deterministic_intent = decision.reason_code in {
            CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
            CustomerSalesReasonCode.PRICE_REQUEST,
            CustomerSalesReasonCode.SESSION_NEXT_UNLOCK_REQUEST,
            CustomerSalesReasonCode.PRESENT_AFTER_POSITIVE_TEASE_RESPONSE,
        }
        if (
            decision.decision is CustomerSalesDecisionType.PRESENT_OFFER
            and not ready and not deterministic_intent
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason_code=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                reason_summary=(
                    "Current deterministic conversation flags do not "
                    "authorize presenting a paid offer."
                ),
                sell_allowed=False,
                decision_metadata=immutable_mapping({
                    **dict(decision.decision_metadata),
                    "recommendedConversationalAction": (
                        conversational_action or None
                    ),
                    "commercialOpportunity": opportunity,
                }),
            )
        return replace(
            decision,
            decision_metadata=immutable_mapping({
                **dict(decision.decision_metadata),
                "recommendedConversationalAction": (
                    conversational_action or None
                ),
                "commercialOpportunity": opportunity,
            }),
        )

    @staticmethod
    def _commercial_opportunity_assessment(
        decision: CustomerSalesDecision, flags: dict, *, progression: dict,
        conversational_action: str,
    ) -> dict:
        """Compare selling now with the expected value of another chat turn."""
        contributions: dict[str, int] = {}
        suppressions: list[str] = []
        phase = str(progression.get("phase") or "CONVERSATIONAL").upper()
        tease_count = max(0, int(progression.get("teaseCount") or 0))
        anchor_evidence: list[str] = []
        if flags.get("current_buying_intent") is True:
            anchor_evidence.append("CURRENT_BUYING_INTENT")
        if flags.get("customer_requested_content") is True:
            anchor_evidence.append("CONTENT_ACCESS_REQUEST")
        if flags.get("reveal_request") is True:
            anchor_evidence.append("COMMERCIAL_REVEAL_REQUEST")
        if flags.get("sustained_sexual_receptiveness") is True:
            anchor_evidence.append("SUSTAINED_POSITIVE_SEXUAL_RECEPTIVENESS")
        if (
            phase in {"TEASE", "BUILD_INTEREST", "PRESENT_OFFER"}
            and str(progression.get("progressionInitiator") or "CUSTOMER").upper()
            != "AVA"
        ):
            anchor_evidence.append("PERSISTED_COMMERCIAL_PROGRESSION")
        if decision.active_purchase_intent_id is not None:
            anchor_evidence.append("ACTIVE_PURCHASE_INTENT")
        commercial_anchor = bool(anchor_evidence)

        if flags.get("current_buying_intent") is True:
            contributions["currentIntent"] = 45
        if commercial_anchor and flags.get("escalation_ready") is True:
            contributions["escalationReady"] = 24
        if flags.get("customer_requested_content") is True:
            contributions["contentAccessRequest"] = 18
        if flags.get("reveal_request") is True:
            contributions["revealRequest"] = 28
        if flags.get("sustained_sexual_receptiveness") is True:
            contributions["sustainedSexualReceptiveness"] = 46
        if commercial_anchor and flags.get("positive_tease_response") is True:
            contributions["positiveTrajectory"] = 12
        if commercial_anchor and conversational_action == "PRESENT_OFFER":
            contributions["modelTimingRecommendation"] = 30
        elif commercial_anchor and conversational_action == "TEASE_OFFER":
            contributions["modelTimingRecommendation"] = 6

        level_weights = {
            "curiosity_level": {"medium": 8, "high": 14},
            "buyer_likelihood": {"medium": 8, "high": 16},
        }
        for field, weights in level_weights.items():
            weight = weights.get(str(flags.get(field) or "").lower(), 0)
            if weight:
                contributions[field] = weight
        if commercial_anchor:
            weight = {"medium": 8, "high": 14}.get(
                str(flags.get("engagement_level") or "").lower(), 0,
            )
            if weight:
                contributions["engagement_level"] = weight

        if phase == "TEASE":
            contributions["trajectoryPhase"] = 8
        elif phase == "BUILD_INTEREST":
            contributions["trajectoryPhase"] = 18
        if tease_count:
            contributions["accumulatedTeaseContext"] = min(16, tease_count * 8)
        if tease_count and (
            flags.get("positive_tease_response") is True
            or flags.get("escalation_ready") is True
        ):
            contributions["teaseDiminishingReturn"] = min(16, tease_count * 8)

        history_count = max(0, int(flags.get("recent_history_turn_count") or 0))
        if flags.get("sustained_sexual_receptiveness") is True and history_count >= 3:
            contributions["sustainedRelationshipDepth"] = 12
        if history_count >= 3 and phase in {"TEASE", "BUILD_INTEREST"}:
            contributions["recentTrajectory"] = min(10, history_count * 2)

        memory = dict(decision.decision_metadata or {}).get(
            "customerCommerceMemory"
        ) or {}
        purchase_count = int(
            memory.get("verifiedPurchaseCount")
            or memory.get("lifetimePurchaseCount") or 0
        )
        if purchase_count:
            contributions["verifiedBuyerHistory"] = min(12, 6 + purchase_count)
        affinity = dict(memory.get("affinity") or {})
        if affinity.get("offeringTypes") or affinity.get("tags"):
            contributions["knownCommerceAffinity"] = 6

        if conversational_action in {"CHAT", "FLIRT"} and not any((
            flags.get("current_buying_intent") is True,
            flags.get("positive_tease_response") is True,
            flags.get("reveal_request") is True,
            flags.get("sustained_sexual_receptiveness") is True,
        )):
            suppressions.append(
                "CUSTOMER_CHANGED_OR_REMAINED_ON_NONCOMMERCIAL_TOPIC"
            )
        if conversational_action == "BACK_OFF":
            suppressions.append("CURRENT_OBJECTION_OR_BACK_OFF")
        if decision.active_purchase_intent_id is not None:
            suppressions.append("ACTIVE_PURCHASE_INTENT")
        if decision.decision in {
            CustomerSalesDecisionType.BACK_OFF,
            CustomerSalesDecisionType.WAIT,
            CustomerSalesDecisionType.MANUAL_REVIEW,
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
        }:
            suppressions.append(f"AUTHORITATIVE_{decision.decision.value}")
        if decision.recommended_offering_id is None:
            suppressions.append("NO_ELIGIBLE_OFFERING")

        score = sum(contributions.values())
        threshold = 70
        preferred = score >= threshold and not suppressions
        return {
            "policyVersion": "EXPECTED_COMMERCIAL_VALUE_V1",
            "strengthScore": score,
            "presentationThreshold": threshold,
            "presentConsidered": bool(score > 0 and commercial_anchor),
            "presentPreferred": preferred,
            "relationshipTrajectory": (
                "POSITIVE_SOCIAL" if not commercial_anchor and str(
                    flags.get("engagement_level") or ""
                ).lower() in {"medium", "high"} else "NEUTRAL"
            ),
            "commercialTrajectory": phase,
            "commercialAnchorPresent": commercial_anchor,
            "commercialAnchorEvidence": tuple(anchor_evidence),
            "modelTimingRecommendation": conversational_action or None,
            "modelTimingAuthority": (
                "COMMERCIAL_STRENGTH_MODIFIER" if commercial_anchor
                else "SUBORDINATE_NO_COMMERCIAL_ANCHOR"
            ),
            "trajectoryPhase": phase,
            "teaseCount": tease_count,
            "contributions": contributions,
            "suppressions": tuple(dict.fromkeys(suppressions)),
            "finalRationale": (
                "PRESENT_VALUE_EXCEEDS_ADDITIONAL_TEASE_VALUE"
                if preferred else
                "PRESENT_SUPPRESSED" if suppressions else
                "MORE_CONVERSATION_EXPECTED_TO_HAVE_HIGHER_VALUE"
            ),
        }

    @staticmethod
    def _proactive_progression_assessment(
        decision: CustomerSalesDecision, flags: dict, *, progression: dict,
        opportunity: dict, conversational_action: str,
    ) -> dict:
        """Authorize one relationship bridge without manufacturing customer intent."""
        metadata = dict(decision.decision_metadata or {})
        attention = dict(metadata.get("customerValueAttention") or {})
        behavior = dict(attention.get("behaviorEvidenceCounts") or {})
        phase = str(progression.get("phase") or "CONVERSATIONAL").upper()
        initiator = str(progression.get("progressionInitiator") or "").upper()
        recent = bool(
            initiator == "AVA" and phase in {"TEASE", "BUILD_INTEREST"}
            and progression.get("awaitingCustomerResponse") is not False
        )
        cooldown = max(0, int(progression.get("proactiveTeaseCooldownTurns") or 0))
        evidence = []
        if attention.get("valueTier") == "ENGAGED_PROSPECT":
            evidence.append("ENGAGED_PROSPECT")
        if attention.get("buyerStatus") in {
            "FIRST_TIME_BUYER", "ACTIVE_BUYER", "REPEAT_BUYER",
            "HIGH_VALUE_BUYER", "WHALE",
        }:
            evidence.append("VERIFIED_RELATIONSHIP_HISTORY")
        if opportunity.get("relationshipTrajectory") == "POSITIVE_SOCIAL":
            evidence.append("POSITIVE_SOCIAL_TRAJECTORY")
        if int(flags.get("recent_history_turn_count") or 0) >= 5:
            evidence.append("MEANINGFUL_CONVERSATION_DEPTH")
        if str(flags.get("engagement_level") or "").lower() in {"medium", "high"}:
            evidence.append("RECIPROCAL_ENGAGEMENT")
        if conversational_action == "TEASE_OFFER":
            evidence.append("MODEL_TIMING_TEASE")
        if attention.get("conversationContinuationValue") in {"MEDIUM", "HIGH"}:
            evidence.append("CONVERSATION_CONTINUATION_VALUE")
        if int(behavior.get("offer_exposure_count") or 0) == 0:
            evidence.append("NO_OFFER_EXPOSURE")

        suppressions = []
        if attention.get("timeWasterRisk") == "HIGH":
            suppressions.append("HIGH_TIME_WASTER_RISK")
        if int(behavior.get("rejection_count") or 0) > 0 or phase == "BACK_OFF":
            suppressions.append("REJECTION_OR_BACK_OFF")
        if cooldown:
            suppressions.append("PROACTIVE_TEASE_COOLDOWN")
        if recent:
            suppressions.append("AWAITING_CUSTOMER_RESPONSE")
        if decision.active_purchase_intent_id is not None:
            suppressions.append("ACTIVE_PURCHASE_INTENT")
        if getattr(decision, "next_sales_action", None) is not None and \
                phase in {"SESSION", "ACTIVE_SESSION"}:
            suppressions.append("ACTIVE_SESSION_AUTHORITY")
        if opportunity.get("commercialAnchorPresent"):
            suppressions.append("CUSTOMER_COMMERCIAL_PATH_ALREADY_ACTIVE")
        if decision.decision in {
            CustomerSalesDecisionType.BACK_OFF,
            CustomerSalesDecisionType.WAIT,
            CustomerSalesDecisionType.MANUAL_REVIEW,
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
        }:
            suppressions.append(f"AUTHORITATIVE_{decision.decision.value}")

        relationship_depth = (
            "MEANINGFUL_CONVERSATION_DEPTH" in evidence
            or "VERIFIED_RELATIONSHIP_HISTORY" in evidence
        )
        authorized = bool(
            {"ENGAGED_PROSPECT", "VERIFIED_RELATIONSHIP_HISTORY"}.intersection(evidence)
            and relationship_depth
            and {"POSITIVE_SOCIAL_TRAJECTORY", "RECIPROCAL_ENGAGEMENT",
                 "MODEL_TIMING_TEASE", "CONVERSATION_CONTINUATION_VALUE"}.issubset(evidence)
            and not suppressions
        )
        return {
            "proactiveProgressionAuthorized": authorized,
            "proactiveProgressionReason": (
                "COMBINED_RELATIONSHIP_EVIDENCE"
                if authorized else suppressions[0] if suppressions
                else "INSUFFICIENT_COMBINED_RELATIONSHIP_EVIDENCE"
            ),
            "proactiveProgressionEvidence": tuple(evidence),
            "proactiveProgressionSuppressions": tuple(suppressions),
            "progressionInitiator": "AVA" if authorized or recent else None,
            "progressionBefore": phase,
            "progressionAfter": "TEASE" if authorized else phase,
            "progressionAction": "TEASE" if authorized else "NONE",
            "proactiveTeaseCooldown": cooldown,
            "recentProactiveTease": recent,
            "customerResponseToPreviousTease": "AWAITING" if recent else "NONE",
            "customerBuyingIntentUnchanged": True,
        }

    @staticmethod
    def proactive_progression_preflight(
        decision: CustomerSalesDecision, *, recent_history_turn_count: int,
    ) -> dict:
        """Serialize safe relationship evidence for the pre-generation boundary."""
        metadata = dict(decision.decision_metadata or {})
        return {
            "customerValueAttention": dict(metadata.get("customerValueAttention") or {}),
            "salesProgression": dict(metadata.get("salesProgression") or {}),
            "proactiveProgression": dict(metadata.get("proactiveProgression") or {}),
            "recentHistoryTurnCount": max(0, int(recent_history_turn_count or 0)),
            "activePurchaseIntent": decision.active_purchase_intent_id is not None,
            "authoritativeDecision": decision.decision.value,
        }

    @staticmethod
    def activate_pre_generation_proactive_progression(
        preflight: dict, readiness: dict,
    ) -> dict:
        """Compatibility projection; AI readiness cannot authorize progression."""
        values = dict(preflight or {})
        authoritative = dict(values.get("proactiveProgression") or {})
        if (
            authoritative.get("proactiveProgressionAuthorized") is True
            and authoritative.get("progressionAction") == "TEASE"
        ):
            return authoritative
        return {
            "proactiveProgressionAuthorized": False,
            "proactiveProgressionReason": "CUSTOMER_SALES_BRAIN_NOT_AUTHORIZED",
            "proactiveProgressionEvidence": tuple(
                authoritative.get("proactiveProgressionEvidence") or ()
            ),
            "proactiveProgressionSuppressions": tuple(
                authoritative.get("proactiveProgressionSuppressions") or ()
            ),
            "progressionInitiator": None,
            "progressionBefore": str(
                dict(values.get("salesProgression") or {}).get("phase")
                or "CONVERSATIONAL"
            ).upper(),
            "progressionAfter": str(
                dict(values.get("salesProgression") or {}).get("phase")
                or "CONVERSATIONAL"
            ).upper(),
            "progressionAction": "NONE",
            "proactiveTeaseCooldown": 0,
            "recentProactiveTease": False,
            "customerResponseToPreviousTease": "NONE",
            "customerBuyingIntentUnchanged": True,
        }

    @staticmethod
    def buyer_stage(purchase_count: int) -> CustomerBuyerStage:
        if purchase_count <= 0:
            return CustomerBuyerStage.PROSPECT
        if purchase_count == 1:
            return CustomerBuyerStage.FIRST_TIME_BUYER
        return CustomerBuyerStage.REPEAT_BUYER

    def list_decisions(
        self, *, creator_profile_id: int, search: str | None,
        page: int, page_size: int,
    ):
        profiles, total, current_page = self.customers.list_profiles(
            creator_profile_id=creator_profile_id, search=search,
            page=page, page_size=page_size,
        )
        items = tuple(self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=item.fanvue_account_id,
            external_fanvue_buyer_uuid=item.external_fanvue_user_uuid,
            telegram_user_id=item.telegram_user_id,
            identity_resolved=item.telegram_identity_mapping_id is not None,
        ) for item in profiles)
        return items, total, current_page

    def statistics(self, *, creator_profile_id: int):
        profiles, _, _ = self.customers.list_profiles(
            creator_profile_id=creator_profile_id, search=None,
            page=1, page_size=1000,
        )
        decisions = [self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=item.fanvue_account_id,
            external_fanvue_buyer_uuid=item.external_fanvue_user_uuid,
            telegram_user_id=item.telegram_user_id,
            identity_resolved=item.telegram_identity_mapping_id is not None,
        ) for item in profiles]
        distribution = {}
        stages = {}
        for item in decisions:
            distribution[item.decision.value] = distribution.get(
                item.decision.value, 0
            ) + 1
            stages[item.buyer_stage.value] = stages.get(
                item.buyer_stage.value, 0
            ) + 1
        return {
            "total": len(decisions), "decisionDistribution": distribution,
            "buyerStageDistribution": stages,
            "currentActiveOffers": sum(
                item.active_purchase_intent_id is not None for item in decisions
            ),
            "pendingPayments": sum(
                item.decision is CustomerSalesDecisionType.PAYMENT_PENDING
                for item in decisions
            ),
            "unknownAttributions": sum(
                item.reason_code
                is CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN
                for item in decisions
            ),
        }

    @staticmethod
    def _apply_objection_ranking_context(context, objection):
        preference = objection.selector_constraints.get("contentPreference")
        if preference:
            context["requested_themes"] = tuple(dict.fromkeys((
                *tuple(context.get("requested_themes") or ()),
                str(preference).lower().replace("_", " "),
            )))
        if objection.objection_type in {
            CommercialObjectionType.PRICE_RESISTANCE,
            CommercialObjectionType.DISCOUNT_REQUEST,
            CommercialObjectionType.BUDGET_LIMIT,
        }:
            context["price_sensitive"] = True

    @staticmethod
    def _objection_reason(objection):
        return (
            CustomerSalesReasonCode.PRICE_RECOVERY
            if objection.objection_type in {
                CommercialObjectionType.PRICE_RESISTANCE,
                CommercialObjectionType.BUDGET_LIMIT,
            }
            else CustomerSalesReasonCode.CONTENT_ALTERNATIVE
        )

    @staticmethod
    def _objection_diagnostics(objection, current_intent, context):
        result = dict(objection.to_mapping())
        previous = dict(context.get("sales_progression") or {})
        offering_id = (
            getattr(current_intent, "commercial_offering_id", None)
            if current_intent is not None else previous.get("offeringId")
        )
        price = (
            getattr(current_intent, "expected_price_minor", None)
            if current_intent is not None else previous.get("priceMinor")
        )
        maximum = None
        if (objection.objection_type in {
                CommercialObjectionType.PRICE_RESISTANCE,
                CommercialObjectionType.BUDGET_LIMIT,
            } and price is not None):
            explicit = objection.budget_constraint_minor
            maximum = min(int(price) - 100, int(int(price) * 0.90))
            maximum = maximum if maximum >= 300 else 299
            if explicit is not None:
                maximum = min(maximum, int(explicit))
        result.update({
            "priceRecoveryRequested": objection.objection_type in {
                CommercialObjectionType.PRICE_RESISTANCE,
                CommercialObjectionType.BUDGET_LIMIT,
            },
            "previousOfferPriceMinor": int(price) if price is not None else None,
            "targetMaximumAlternativePriceMinor": maximum,
            "contentExclusionApplied": bool(
                offering_id and objection.objection_type in {
                    CommercialObjectionType.CONTENT_MISMATCH,
                    CommercialObjectionType.PRODUCT_REJECTION,
                }
            ),
            "rejectedOfferingId": str(offering_id) if offering_id else None,
            "recoveryAttemptCount": int(previous.get("recoveryAttemptCount") or 0),
        })
        return result

    def _objection_stop(self, started, now, common, context, objection, *,
                        decision=CustomerSalesDecisionType.BACK_OFF):
        base = self._finish(
            started, now, **common, decision=decision,
            reason=(CustomerSalesReasonCode.CUSTOMER_HESITATION
                    if objection.objection_type is CommercialObjectionType.TEMPORARY_HESITATION
                    else CustomerSalesReasonCode.CUSTOMER_DECLINED),
            summary=("Customer hesitation lowers pressure without replacing the offer."
                     if decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
                     else "A global or repeated decline suppresses sales pressure."),
        )
        prior = dict(context.get("sales_progression") or {})
        return replace(base, decision_metadata=immutable_mapping({
            **dict(base.decision_metadata),
            "salesProgression": {
                **prior,
                "phase": ("BACK_OFF" if decision is CustomerSalesDecisionType.BACK_OFF
                          else prior.get("phase", "CONVERSATIONAL")),
                "reasonCode": base.reason_code.value,
            },
        }))

    def _value_defense(self, started, now, common, context, objection,
                       current_intent):
        """Authorize one non-price-changing, current-offer recovery turn."""
        prior = dict(context.get("sales_progression") or {})
        attempts = int(prior.get("recoveryAttemptCount") or 0)
        if attempts >= 1 or not objection.negative_contact_authorized:
            return self._objection_stop(started, now, common, context, objection)
        offering_id = (
            getattr(current_intent, "commercial_offering_id", None)
            if current_intent is not None else prior.get("offeringId")
        )
        price = (
            getattr(current_intent, "expected_price_minor", None)
            if current_intent is not None else prior.get("priceMinor")
        )
        attention = self.customer_value_attention.project(
            commerce_memory=dict(context.get("customer_commerce_memory_summary") or {}),
            behavior={
                "recovery_attempt_count": attempts,
                "sexual_engagement_only": bool(context.get("sexual_engagement_only")),
                "inbound_message_count": context.get("inbound_message_count"),
                "offer_exposure_count": context.get("offer_exposure_count"),
                "active_purchase_intent": current_intent is not None,
            },
            now=now,
        )
        negative_contact_used = attention.time_waster_risk != "HIGH"
        intensity = (
            "OMITTED" if not negative_contact_used
            else "FAMILIAR_LIGHT" if attention.buyer_status in {
                "REPEAT_BUYER", "HIGH_VALUE_BUYER"
            }
            else "LIGHT"
        )
        base = self._finish(
            started, now, **common,
            decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
            reason=CustomerSalesReasonCode.OBJECTION_VALUE_DEFENSE,
            summary=("One bounded value-defense response preserves the original "
                     "offering and its canonical price."),
        )
        metadata = dict(base.decision_metadata or {})
        recovery = {
            "authorized": True,
            "attemptCount": attempts + 1,
            "budgetRemaining": 0,
            "strategy": "VALUE_DEFENSE",
            "negativeContactAuthorized": True,
            "negativeContactUsed": negative_contact_used,
            "negativeContactIntensity": intensity,
            "valueDefenseUsed": True,
            "originalOfferPreserved": True,
            "originalOfferingId": str(offering_id) if offering_id else None,
            "originalPrice": int(price) if price is not None else None,
            "budgetConstraintDetected": False,
            "budgetConstraintAmount": None,
            "alternativeAuthorized": False,
            "alternativeSelected": False,
            "alternativePrice": None,
            "noDynamicDiscount": True,
            "falseScarcityAllowed": False,
            "reason": (
                "TIME_WASTER_MINIMAL_VALUE_DEFENSE"
                if not negative_contact_used
                else "BOUNDED_ORIGINAL_OFFER_VALUE_DEFENSE"
            ),
        }
        metadata["objectionRecovery"] = recovery
        metadata["salesProgression"] = {
            **prior,
            "offeringId": str(offering_id) if offering_id else prior.get("offeringId"),
            "priceMinor": int(price) if price is not None else prior.get("priceMinor"),
            "recoveryAttemptCount": attempts + 1,
            "reasonCode": base.reason_code.value,
        }
        return replace(base, decision_metadata=immutable_mapping(metadata))

    @staticmethod
    def _recovery_constraints(objection, current_intent, *, base=None):
        constraints = base or StrategyConstraints()
        if not objection.consider_alternative:
            return constraints
        rejected = []
        price = None
        if current_intent is not None:
            try:
                rejected.append(UUID(str(current_intent.commercial_offering_id)))
            except (TypeError, ValueError, AttributeError):
                pass
            price = getattr(current_intent, "expected_price_minor", None)
        maximum = None
        if (objection.objection_type in {
                CommercialObjectionType.PRICE_RESISTANCE,
                CommercialObjectionType.BUDGET_LIMIT,
            } and price is not None):
            current = int(price)
            maximum = min(current - 100, int(current * 0.90))
            if maximum < 300:
                maximum = 299
            if objection.budget_constraint_minor is not None:
                maximum = min(maximum, int(objection.budget_constraint_minor))
        return replace(
            constraints,
            excluded_offering_ids=tuple(dict.fromkeys((
                *constraints.excluded_offering_ids, *rejected,
            ))),
            maximum_price_minor=maximum,
        )

    @staticmethod
    def _decorate_recovery(decision, objection, selection):
        metadata = dict(decision.decision_metadata)
        prior = dict(metadata.get("salesProgression") or {})
        previous_attempts = int(prior.get("recoveryAttemptCount") or 0)
        objection_metadata = dict(metadata.get("commercialObjection") or {})
        rejected_id = objection_metadata.get("rejectedOfferingId")
        selector = dict(metadata.get("offeringSelector") or {})
        selector_exclusions = list(selector.get("exclusionReasons") or ())
        metadata["salesProgression"] = {
            **prior,
            "phase": "PRESENT_OFFER",
            "offeringId": str(selection.offering_id),
            "recoveryAttemptCount": previous_attempts + 1,
            "rejectedOfferingId": rejected_id,
            "reasonCode": decision.reason_code.value,
        }
        metadata["nextBestOffer"] = {
            "strategy": "PRICE_RECOVERY" if objection.objection_type is CommercialObjectionType.PRICE_RESISTANCE else "CONTENT_ALTERNATIVE",
            "classification": "ALTERNATIVE",
            "selectedCandidate": str(selection.offering_id),
            "selectorExclusions": selector_exclusions,
        }
        return replace(decision, decision_metadata=immutable_mapping(metadata))

    @staticmethod
    def _next_offer_kind(*, objection, latest, selection, receptiveness):
        if latest is None or getattr(latest, "status", None) is None:
            return CustomerSalesDecisionType.PRESENT_OFFER
        if getattr(latest.status, "value", latest.status) != "PURCHASED":
            return CustomerSalesDecisionType.PRESENT_OFFER
        if not receptiveness.fresh_direct_intent:
            return CustomerSalesDecisionType.PRESENT_OFFER
        prior_price = int(getattr(latest, "expected_price_minor", 0) or 0)
        selected_price = int(selection.price_minor or 0)
        selected_type = str(selection.offering_type or "").upper()
        if objection.objection_type is not CommercialObjectionType.PRICE_RESISTANCE and (
            selected_type in {"BUNDLE", "SESSION"}
            or (prior_price > 0 and selected_price > prior_price)
        ):
            return CustomerSalesDecisionType.UPSELL
        return CustomerSalesDecisionType.CROSS_SELL

    def _commercial_opportunity_evidence(
        self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
        latest=None,
    ) -> dict:
        reader = getattr(
            self.intents, "get_customer_opportunity_evidence", None
        )
        if callable(reader):
            return dict(reader(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
            ) or {})

        # Compatibility for isolated repositories: never count CREATED-only
        # state as a customer-visible opportunity.
        presented = bool(
            latest is not None and getattr(latest, "presented_at", None) is not None
        )
        status = str(
            getattr(getattr(latest, "status", None), "value", "") or ""
        ).upper()
        return {
            "commercial_opportunity_evidence_source": (
                "LATEST_PURCHASE_INTENT_COMPATIBILITY"
            ),
            "presented_opportunity_count": 1 if presented else 0,
            "failed_nonconverted_opportunity_count": (
                1 if presented and status in {
                    "EXPIRED", "ABANDONED", "SUPERSEDED", "ADMIN_CLOSED",
                } else 0
            ),
            "converted_opportunity_count": (
                1 if presented and status == "PURCHASED" else 0
            ),
            "active_unresolved_opportunity": bool(
                presented and status in {"PRESENTED", "CLICKED", "UNKNOWN"}
            ),
        }

    def _finish(
        self, started, now, *, creator_profile_id, fanvue_account_id,
        buyer_uuid, telegram_user_id, identity_resolved, decision, reason,
        summary, stage, signal=None, active=None, latest=None,
        recommendation=None, sell_allowed=False, nudge_allowed=False,
        upsell_allowed=False, cross_sell_allowed=False,
        congratulate_allowed=False, cooldown_until=None,
        selector_result=None,
        commercial_intelligence=None,
        progression_context=None,
    ):
        progression_context = dict(progression_context or {})
        sexual_receptiveness = self._sustained_sexual_receptiveness_projection(
            progression_context
        )
        memory_summary = dict(
            progression_context.get("customer_commerce_memory_summary") or {}
        )
        objection_summary = dict(
            progression_context.get("commercial_objection") or {}
        )
        progression = dict(progression_context.get("sales_progression") or {})
        latest_message = str(progression_context.get("latest_message") or "")
        from app.services.commercial_nonpayment_evidence_service import (
            CommercialNonpaymentEvidenceService,
        )
        current_nonpayment = CommercialNonpaymentEvidenceService.classify(
            latest_message
        )
        behavior_evidence = {
            key: progression_context.get(key)
            for key in (
                "inbound_message_count", "offer_exposure_count",
                "rejection_count", "commercial_movement",
                "commercial_movement_count", "sexual_engagement_only",
                "sexual_engagement_count", "low_information_response_count",
                "idle_browsing_signal_count", "meaningful_engagement_count",
                "low_conversational_return_count",
                "proactive_tease_delivered_count", "build_interest_exposure_count",
                "commercial_tease_exposure_count",
                "commercial_opportunity_exposure_count",
                "presented_opportunity_count",
                "failed_nonconverted_opportunity_count",
                "converted_opportunity_count",
                "active_unresolved_opportunity",
                "post_offer_sexual_engagement_count",
                "latest_message", "known_memory_domains", "known_memory_keys",
                "recent_question_count", "question_streak",
                "purchase_acknowledgement_pending",
                "previous_ava_message", "memory_written_this_turn",
                "nurture_response_count_rolling_day",
                "last_nurture_response_at",
            )
            if progression_context.get(key) is not None
        }
        value_attention = self.customer_value_attention.project(
            commerce_memory=memory_summary,
            behavior={
                **behavior_evidence,
                "active_purchase_intent": active is not None,
                "active_session": bool(progression_context.get("sales_session_id")),
                "sales_progression_phase": progression.get("phase"),
                "direct_buying_intent": self.conversational_progression.has_direct_purchase_intent(latest_message),
                "commercial_interest_type": dict(
                    progression_context.get("commercial_receptiveness") or {}
                ).get("commercialInterestType", "NONE"),
                "current_inbound_activity": bool(latest_message.strip()),
                "recovery_attempt_count": max(
                    int(behavior_evidence.get("rejection_count") or 0),
                    int(objection_summary.get("recoveryAttemptCount") or 0),
                ),
                "back_off": decision is CustomerSalesDecisionType.BACK_OFF,
                "commercial_action": decision.value,
                "content_request": self.conversational_progression.transition_features(latest_message).get("content_request"),
                "explicit_nonpayment_detected": current_nonpayment[
                    "explicitNonpaymentDetected"
                ],
                "browsing_only_detected": current_nonpayment[
                    "browsingOnlyDetected"
                ],
                "hostility_level": dict(progression_context.get(
                    "contextual_customer_tone"
                ) or {}).get("hostilityLevel"),
                "repeated_hostility": dict(progression_context.get(
                    "contextual_customer_tone"
                ) or {}).get("repeatedHostility"),
                "explicit_disengagement": dict(progression_context.get(
                    "contextual_customer_tone"
                ) or {}).get("explicitDisengagement"),
            },
            now=now,
        )
        contextual_tone = dict(
            progression_context.get("contextual_customer_tone") or {}
        )
        prior_backoff = str(progression.get("phase") or "").upper() == "BACK_OFF"
        fresh_direct_intent = self.conversational_progression.has_direct_purchase_intent(
            latest_message
        )
        suppress_repeated_abuse = bool(
            (prior_backoff or int(
                contextual_tone.get("priorExplicitDisengagementCount") or 0
            ) > 0)
            and contextual_tone.get("rageBaitPattern") is True
            and not fresh_direct_intent
            and not contextual_tone.get("commercialCuriosity")
            and not contextual_tone.get("priceObjection")
        )
        suppress_optional_nurture_reply = bool(
            value_attention.optional_ordinary_reply_suppressed
            and decision in {
                CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesDecisionType.NO_SALE,
            }
            and not fresh_direct_intent
        )
        outbound_suppressed = bool(
            suppress_repeated_abuse or suppress_optional_nurture_reply
        )
        outbound_suppression_reason = (
            "REPEATED_HOSTILITY_AFTER_BACK_OFF"
            if suppress_repeated_abuse
            else "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
            if suppress_optional_nurture_reply
            else None
        )
        projected_stage = value_attention.buyer_stage
        if projected_stage in CustomerBuyerStage.__members__:
            stage = CustomerBuyerStage[projected_stage]
        lifecycle = active
        conversion = (
            signal.get("conversionState") if signal else "NO_ACTIVE_OFFER"
        )
        lifecycle_intent = active or latest
        lifecycle_operation = None
        if lifecycle_intent is not None and decision in {CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER, CustomerSalesDecisionType.CONGRATULATE_PURCHASE}:
            try:
                lifecycle_operation = self.telegram_sales_deliveries.get_by_purchase_intent(lifecycle_intent.purchase_intent_id)
            except Exception as error:
                logger.warning("event=offer_lifecycle_presentation_unavailable error_type=%s", type(error).__name__)
        lifecycle_payload = dict(getattr(lifecycle_operation, "delivery_payload", {}) or {})
        lifecycle_metadata = dict(lifecycle_payload.get("metadata") or {})
        original_presentation = str(getattr(lifecycle_operation, "response_text", "") or "").strip()
        original_lines = original_presentation.splitlines()
        if original_lines and ("http://" in original_lines[-1] or "https://" in original_lines[-1]):
            original_presentation = "\n".join(original_lines[:-1]).strip()
        persisted_context = dict(getattr(lifecycle_intent, "created_metadata", {}) or {})
        purchase_kind = ("SESSION_FINALE_PURCHASE" if lifecycle_metadata.get("session_role") == "FINALE" else "SESSION_STEP_PURCHASE" if lifecycle_metadata.get("session_role") else "BUNDLE_PURCHASE" if lifecycle_payload.get("delivery_type") == "BUNDLE" else "SINGLE_PURCHASE")
        offer_lifecycle = ({
            "messagePurpose": (
                "ACTIVE_OFFER_CONTINUATION"
                if decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
                and dict(progression_context.get(
                    "active_offer_continuation"
                ) or {}).get("customerInitiatedOfferContinuation") is True
                else "NUDGE"
                if decision is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
                else "PURCHASE_ACKNOWLEDGEMENT"
            ),
            "purchaseKind": purchase_kind,
            "purchaseIntentId": str(lifecycle_intent.purchase_intent_id),
            "offeringId": str(lifecycle_intent.commercial_offering_id),
            "publicationId": str(getattr(lifecycle_intent, "commercial_publication_id", "") or "") or None,
            "status": lifecycle_intent.status.value,
            "priceMinor": getattr(lifecycle_intent, "expected_price_minor", None),
            "currency": getattr(lifecycle_intent, "expected_currency", None),
            "presentedAt": lifecycle_intent.presented_at.isoformat() if lifecycle_intent.presented_at else None,
            "purchasedAt": getattr(lifecycle_intent, "purchased_at", None).isoformat() if getattr(lifecycle_intent, "purchased_at", None) else None,
            "originalPresentation": original_presentation or None,
            "contentType": lifecycle_payload.get("delivery_type"),
            "sessionId": lifecycle_metadata.get("session_id"), "sessionStep": lifecycle_metadata.get("session_step"),
            "sessionRole": lifecycle_metadata.get("session_role"), "sessionAssetId": lifecycle_metadata.get("session_asset_id"),
            "groundedProductContext": {
                "commercialIntelligence": dict(persisted_context.get("commercial_intelligence") or {}),
                "bundle": dict(persisted_context.get("photoshoot_bundle") or {}),
            },
            "rules": (
                [
                    "The customer explicitly requested the current paid offer.",
                    "Foreground the current structured Unlock presentation now.",
                    "Do not state a numeric price in conversational prose.",
                    "Do not ask an unrelated discovery or curiosity question.",
                    "Do not deny, delay, or claim the existing link is unavailable.",
                    "Never change product, price, link, ownership, or Session state.",
                ]
                if dict(progression_context.get(
                    "active_offer_continuation"
                ) or {}).get("customerInitiatedOfferContinuation") is True
                else [
                    "Complement rather than repeat the original presentation.",
                    "Acknowledge only the verified purchase; do not present another offer.",
                    "Never change product, price, link, ownership, or Session state.",
                ]
            ),
        } if lifecycle_intent is not None and decision in {CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER, CustomerSalesDecisionType.CONGRATULATE_PURCHASE} else None)
        result = CustomerSalesDecision(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=buyer_uuid,
            telegram_user_id=telegram_user_id,
            identity_resolved=identity_resolved,
            decision=decision, reason_code=reason, reason_summary=summary,
            buyer_stage=stage, commerce_signal=immutable_mapping(signal),
            active_purchase_intent_id=(
                lifecycle.purchase_intent_id if lifecycle else None
            ),
            active_offering_id=(
                lifecycle.commercial_offering_id if lifecycle else None
            ),
            active_offer_status=(
                lifecycle.status.value if lifecycle else None
            ),
            active_offer_conversion_state=conversion,
            recommended_offering_id=(
                recommendation.offering_id if recommendation else None
            ),
            recommended_publication_id=(
                recommendation.publication_id if recommendation else None
            ),
            recommended_delivery_url=(
                recommendation.delivery_url if recommendation else None
            ),
            sell_allowed=sell_allowed, nudge_allowed=nudge_allowed,
            upsell_allowed=upsell_allowed, cross_sell_allowed=cross_sell_allowed,
            congratulate_allowed=congratulate_allowed,
            cooldown_until=cooldown_until, evaluated_at=now,
            decision_metadata=immutable_mapping({
                "rulePriority": self._priority(decision, reason),
                "evaluationMs": round((time.perf_counter() - started) * 1000, 3),
                "configuration": {
                    "purchaseCooldownHours": int(
                        self.config.purchase_cooldown.total_seconds() // 3600
                    ),
                    "offerNudgeHours": int(
                        self.config.offer_nudge_delay.total_seconds() // 3600
                    ),
                    "offerExpirationHours": int(
                        self.config.offer_expiration.total_seconds() // 3600
                    ),
                    "sexualReceptivenessMinEngagements": (
                        self.config.sexual_receptiveness_min_engagements
                    ),
                    "sexualReceptivenessMinHistoryTurns": (
                        self.config.sexual_receptiveness_min_history_turns
                    ),
                },
                "sustainedSexualReceptiveness": sexual_receptiveness,
                "sustainedSexualReceptivenessAuthority": sexual_receptiveness["authority"],
                "latestPurchaseIntentId": (
                    str(latest.purchase_intent_id) if latest else None
                ),
                "latestIntentStatus": (
                    latest.status.value if latest else None
                ),
                "latestAttributionResult": (
                    latest.attribution_result.value
                    if latest and getattr(latest, "attribution_result", None)
                    else None
                ),
                "latestPurchaseAcknowledgedAt": (
                    latest.purchase_acknowledged_at.isoformat()
                    if latest and getattr(latest, "purchase_acknowledged_at", None)
                    else None
                ),
                "historicalCommercialContext": {
                    "previousOfferPresented": bool(
                        latest is not None and latest.presented_at is not None
                    ),
                    "previousOfferAdminClosed": bool(
                        latest is not None
                        and latest.status.value == "ADMIN_CLOSED"
                    ),
                    "previousOfferingId": (
                        str(latest.commercial_offering_id) if latest else None
                    ),
                    "executionReusable": False,
                } if latest is not None else {},
                "customerCommerceMemory": dict(
                    memory_summary
                ),
                "commercialOpportunity": {
                    "source": progression_context.get(
                        "commercial_opportunity_evidence_source"
                    ),
                    "presentedOpportunityCount": int(
                        progression_context.get("presented_opportunity_count") or 0
                    ),
                    "convertedOpportunityCount": int(
                        progression_context.get("converted_opportunity_count") or 0
                    ),
                    "failedNonconvertedOpportunityCount": int(
                        progression_context.get(
                            "failed_nonconverted_opportunity_count"
                        ) or 0
                    ),
                    "activeUnresolvedOpportunity": bool(
                        progression_context.get("active_unresolved_opportunity")
                    ),
                },
                "customerValueAttention": {
                    **dict(value_attention.to_mapping()),
                    "source": "CUSTOMER_VALUE_ATTENTION_SERVICE",
                    "behaviorEvidenceLoaded": bool(
                        progression_context.get("behaviorEvidenceLoaded")
                    ),
                    "behaviorEvidenceCounts": {
                        key: behavior_evidence.get(key)
                        for key in (
                            "inbound_message_count", "offer_exposure_count",
                            "rejection_count", "commercial_movement_count",
                            "sexual_engagement_count", "sexual_engagement_only",
                            "proactive_tease_delivered_count",
                            "commercial_tease_exposure_count",
                            "build_interest_exposure_count",
                            "commercial_opportunity_exposure_count",
                            "presented_opportunity_count",
                            "failed_nonconverted_opportunity_count",
                            "converted_opportunity_count",
                            "active_unresolved_opportunity",
                            "post_offer_sexual_engagement_count",
                            "low_information_response_count",
                            "idle_browsing_signal_count",
                            "meaningful_engagement_count",
                        )
                    },
                    "upstreamProjection": "CANONICAL_BEHAVIOR_EVIDENCE",
                    "generationProjection": "CUSTOMER_VALUE_ATTENTION_SERVICE",
                    "projectionConsistent": True,
                },
                "commercialReceptiveness": dict(
                    progression_context.get("commercial_receptiveness") or {}
                ),
                "activeBuyingWindow": dict(
                    progression_context.get("active_buying_window") or {}
                ),
                "sessionEscalation": dict(
                    progression_context.get("session_escalation") or {}
                ),
                "sessionProposalContext": dict(
                    progression_context.get("session_proposal_context") or {}
                ),
                "deferredContinuation": dict(
                    progression_context.get("deferred_continuation") or {}
                ),
                "activeOfferContinuation": dict(
                    progression_context.get("active_offer_continuation") or {}
                ),
                "commercialObjection": dict(
                    progression_context.get("commercial_objection") or {}
                ),
                "contextualCustomerTone": dict(
                    progression_context.get("contextual_customer_tone") or {}
                ),
                "outboundSuppression": {
                    "suppressed": outbound_suppressed,
                    "outcome": "NO_RESPONSE" if outbound_suppressed else "REPLY",
                    "reason": outbound_suppression_reason,
                    "inboundProcessingRequired": True,
                    "futureCommercialReentryAllowed": True,
                    "freshCommercialIntentDetected": fresh_direct_intent,
                    "nurtureBypassedForCommercialIntent": bool(
                        value_attention.nurture_bypassed_for_commercial_intent
                    ),
                },
                "objectionRecovery": {
                    "authorized": bool(objection_summary.get(
                        "negativeContactAuthorized"
                    ) or objection_summary.get("alternativeSelectionAllowed")),
                    "attemptCount": int(objection_summary.get(
                        "recoveryAttemptCount"
                    ) or 0),
                    "budgetRemaining": max(0, 1 - int(objection_summary.get(
                        "recoveryAttemptCount"
                    ) or 0)),
                    "strategy": objection_summary.get("recoveryStrategy", "NONE"),
                    "negativeContactAuthorized": bool(objection_summary.get(
                        "negativeContactAuthorized"
                    )),
                    "negativeContactUsed": False,
                    "valueDefenseUsed": False,
                    "originalOfferPreserved": bool(objection_summary.get(
                        "currentOfferAuthoritative"
                    )),
                    "originalPrice": objection_summary.get(
                        "previousOfferPriceMinor"
                    ),
                    "budgetConstraintDetected": bool(objection_summary.get(
                        "budgetConstraintDetected"
                    )),
                    "budgetConstraintAmount": objection_summary.get(
                        "budgetConstraintAmount"
                    ),
                    "alternativeAuthorized": bool(objection_summary.get(
                        "alternativeSelectionAllowed"
                    )),
                    "alternativeSelected": bool(
                        decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
                    ),
                    "alternativePrice": (
                        int(recommendation.price_minor)
                        if recommendation and recommendation.price_minor is not None
                        and decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
                        else None
                    ),
                    "noDynamicDiscount": True,
                    "falseScarcityAllowed": False,
                    "reason": objection_summary.get("evidence", ()),
                },
                "purchaseCooldown": {
                    "active": bool(progression_context.get(
                        "purchase_cooldown_active"
                    )),
                    "blockingCurrentSale": bool(progression_context.get(
                        "purchase_cooldown_blocking"
                    )),
                    "override": bool(progression_context.get(
                        "purchase_cooldown_override"
                    )),
                    "overrideReason": progression_context.get(
                        "purchase_cooldown_override_reason"
                    ),
                    "until": progression_context.get(
                        "purchase_cooldown_until"
                    ),
                },
                "continuation": {
                    "eligible": bool(dict(progression_context.get(
                        "commercial_receptiveness"
                    ) or {}).get("continuationEligible")),
                    "anotherSaleAppropriateNow": bool(dict(
                        progression_context.get("commercial_receptiveness") or {}
                    ).get("anotherSaleAppropriateNow")),
                    "reason": dict(progression_context.get(
                        "commercial_receptiveness"
                    ) or {}).get("reason"),
                    "selectedOfferingId": (
                        str(recommendation.offering_id)
                        if recommendation and recommendation.offering_id else None
                    ),
                    "ownershipNoveltyExclusions": list(
                        selector_result.exclusion_reasons
                        if selector_result else ()
                    ),
                },
                "salesProgressionSource": progression_context.get(
                    "sales_progression_source",
                    "SALES_SESSION" if progression_context.get(
                        "sales_progression"
                    ) else "NONE",
                ),
                "selectorInvocationReason": progression_context.get(
                    "selector_invocation_reason",
                    "SELECTOR_INVOKED" if selector_result else "NOT_REACHED",
                ),
                "offerLifecycle": offer_lifecycle,
                "offeringSelector": (
                    {
                        "selectionReason": (
                            selector_result.selection_reason.value
                        ),
                        "exclusionReasons": list(
                            selector_result.exclusion_reasons
                        ),
                        **dict(selector_result.selector_metadata),
                    }
                    if selector_result else None
                ),
                "commercialIntelligence": (
                    {
                        "strategy": (
                            commercial_intelligence.strategy.value
                            if commercial_intelligence.strategy else None
                        ),
                        "reason": commercial_intelligence.reason.value,
                        "reasonSummary": commercial_intelligence.reason_summary,
                        "evidence": list(commercial_intelligence.evidence),
                        "evidenceProvenance": dict(
                            commercial_intelligence.evidence_provenance
                        ),
                        "constraints": {
                            "requiredOfferingTypes": list(
                                commercial_intelligence.constraints
                                .required_offering_types
                            ),
                            "excludedOfferingTypes": list(
                                commercial_intelligence.constraints
                                .excluded_offering_types
                            ),
                            "requiredPhotoshootReference": (
                                commercial_intelligence.constraints
                                .required_photoshoot_reference
                            ),
                            "progression": (
                                commercial_intelligence.constraints.progression
                            ),
                            "completeSetRequired": (
                                commercial_intelligence.constraints
                                .complete_set_required
                            ),
                            "continuationRequired": (
                                commercial_intelligence.constraints
                                .continuation_required
                            ),
                        },
                        "bundleEligibility": (
                            commercial_intelligence.bundle_eligibility.value
                        ),
                        "continuationGuidance": (
                            commercial_intelligence.continuation_guidance
                        ),
                        "evidenceSufficient": (
                            commercial_intelligence.evidence_sufficient
                        ),
                        "conflicts": list(commercial_intelligence.conflicts),
                        "ownershipConsiderations": dict(
                            commercial_intelligence.ownership_considerations
                        ),
                        "salesSessionContext": dict(
                            commercial_intelligence.sales_session_context
                        ),
                        "customerRequestContext": dict(
                            commercial_intelligence.customer_request_context
                        ),
                        "diagnosticContext": dict(
                            commercial_intelligence.diagnostic_context
                        ),
                    }
                    if commercial_intelligence else None
                ),
            }),
            recommended_offering_title=(
                recommendation.title if recommendation else None
            ),
            recommended_offering_short_description=(
                recommendation.short_description if recommendation else None
            ),
            recommended_offering_price_minor=(
                recommendation.price_minor if recommendation else None
            ),
            recommended_offering_currency=(
                recommendation.currency if recommendation else None
            ),
            recommended_photoshoot_experience=(
                getattr(recommendation, "photoshoot_experience", None)
                if recommendation else None
            ),
            recommended_product_context=(
                immutable_mapping(getattr(recommendation, "product_context", None))
                if recommendation else None
            ),
        )
        progression_context=dict(progression_context or {})
        experience = getattr(recommendation, "photoshoot_experience", None) if recommendation else None
        resolved_photoshoot_lifecycle = None
        existing_active_lifecycle = None
        profile = None
        if experience is not None and buyer_uuid is not None:
            try:
                profile = self.customers.get_by_buyer_uuid(
                    creator_profile_id=creator_profile_id,
                    external_fanvue_user_uuid=buyer_uuid,
                )
                if profile is not None:
                    service = self.photoshoot_lifecycles
                    if service is None:
                        from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                        service = CustomerPhotoshootLifecycleService()
                    states=service.context_for_customer(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id)
                    existing_active_lifecycle=next((v for v in states.values() if v.status.value in {'ACTIVE','OBJECTION'}),None)
                    resolved_photoshoot_lifecycle = service.resolve_recommendation(
                        creator_profile_id=creator_profile_id,
                        customer_commerce_profile_id=profile.customer_commerce_profile_id,
                        recommendation=experience,
                        reason=experience.recommendation_explanation,
                    )
            except Exception as error:
                logger.warning("event=photoshoot_lifecycle_resolution_unavailable error_type=%s", type(error).__name__)
        dispatch_mode = None
        dispatch_session_id = (
            resolved_photoshoot_lifecycle.photoshoot_id
            if resolved_photoshoot_lifecycle is not None
            else getattr(experience, "photoshoot_id", None)
        )
        if dispatch_session_id:
            try:
                bundle_service = self.bundle_sales_context
                if bundle_service is None:
                    from app.services.photoshoot_bundle_sales_context_service import PhotoshootBundleSalesContextService
                    bundle_service = PhotoshootBundleSalesContextService()
                dispatch_mode = bundle_service.resolve_mode(dispatch_session_id)
                if dispatch_mode == "BUNDLE" and profile is not None:
                    from app.models.ownership_intelligence import OwnershipIdentity
                    lifecycle_service = self.photoshoot_lifecycles
                    if lifecycle_service is None:
                        from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                        lifecycle_service = CustomerPhotoshootLifecycleService()
                    teaser_presented = bool(
                        resolved_photoshoot_lifecycle
                        and lifecycle_service.bundle_teaser_presented(
                            resolved_photoshoot_lifecycle
                        )
                    )
                    offer_presented_reader = getattr(
                        lifecycle_service, "bundle_offer_presented", None
                    )
                    offer_presented = bool(
                        resolved_photoshoot_lifecycle
                        and callable(offer_presented_reader)
                        and offer_presented_reader(resolved_photoshoot_lifecycle)
                    )
                    bundle_context = bundle_service.build(
                        dispatch_session_id,
                        identity=OwnershipIdentity(
                            creator_profile_id=creator_profile_id,
                            fanvue_account_id=fanvue_account_id,
                            external_fanvue_user_uuid=buyer_uuid,
                            telegram_user_id=telegram_user_id,
                        ),
                        lifecycle_id=(
                            resolved_photoshoot_lifecycle.lifecycle_id
                            if resolved_photoshoot_lifecycle else None
                        ),
                        teaser_presented=teaser_presented,
                        offer_presented=offer_presented,
                    )
                    result = replace(result, bundle_sales_context=bundle_context)
                    if not bundle_context["eligible"]:
                        result = replace(
                            result, decision=CustomerSalesDecisionType.NO_SALE,
                            reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                            reason_summary=",".join(
                                bundle_context["ineligibilityReasons"]
                            ), sell_allowed=False, nudge_allowed=False,
                            recommended_offering_id=None,
                            recommended_publication_id=None,
                            recommended_delivery_url=None,
                        )
            except Exception as error:
                dispatch_mode = "BUNDLE" if dispatch_mode == "BUNDLE" else dispatch_mode
                logger.warning(
                    "event=bundle_sales_context_unavailable error_type=%s",
                    type(error).__name__,
                )
                if dispatch_mode == "BUNDLE":
                    result = replace(
                        result, decision=CustomerSalesDecisionType.NO_SALE,
                        reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                        reason_summary="BUNDLE_CONTEXT_NOT_READY",
                        sell_allowed=False, nudge_allowed=False,
                        recommended_offering_id=None,
                        recommended_publication_id=None,
                        recommended_delivery_url=None,
                    )
                elif dispatch_session_id:
                    dispatch_mode = "UNRESOLVED"
                    result = replace(
                        result, decision=CustomerSalesDecisionType.NO_SALE,
                        reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                        reason_summary="PHOTOSHOOT_SELLING_MODE_UNRESOLVED",
                        sell_allowed=False, nudge_allowed=False,
                        recommended_offering_id=None,
                        recommended_publication_id=None,
                        recommended_delivery_url=None,
                    )
        if buyer_uuid is not None:
            try:
                profile = profile or self.customers.get_by_buyer_uuid(creator_profile_id=creator_profile_id,external_fanvue_user_uuid=buyer_uuid)
                lifecycle_service = self.photoshoot_lifecycles
                if lifecycle_service is None:
                    from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                    lifecycle_service = CustomerPhotoshootLifecycleService()
                if profile and resolved_photoshoot_lifecycle is None:
                    states=lifecycle_service.context_for_customer(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id)
                    existing_active_lifecycle=next((v for v in states.values() if v.status.value in {'ACTIVE','OBJECTION'}),None)
                    resolved_photoshoot_lifecycle=existing_active_lifecycle
                current_lifecycle=existing_active_lifecycle or resolved_photoshoot_lifecycle
                target_lifecycle=(resolved_photoshoot_lifecycle if current_lifecycle and resolved_photoshoot_lifecycle and current_lifecycle.photoshoot_id!=resolved_photoshoot_lifecycle.photoshoot_id else None)
                if profile and current_lifecycle and dispatch_mode == "SESSION":
                    repository=self.progression_repository
                    if repository is None:
                        from app.repositories.autonomous_sales_progression_repository import AutonomousSalesProgressionRepository
                        repository=AutonomousSalesProgressionRepository()
                    engine=self.autonomous_progression
                    if engine is None:
                        from app.services.autonomous_sales_progression_service import AutonomousSalesProgressionService
                        engine=AutonomousSalesProgressionService()
                    from app.models.autonomous_sales_progression import BuyingMomentumEvidence
                    assets=repository.ordered_assets(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_id=current_lifecycle.photoshoot_id)
                    session_runtime_state=None
                    try:
                        runtime_service=self.session_runtime
                        if runtime_service is None:
                            from app.services.photoshoot_session_runtime_service import PhotoshootSessionRuntimeService
                            runtime_service=PhotoshootSessionRuntimeService()
                        session_runtime_state=runtime_service.evaluate(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_session_id=current_lifecycle.photoshoot_id)
                        owned=set(session_runtime_state.owned_asset_ids)
                        assets=tuple(replace(asset,owned=asset.asset_id in owned) for asset in assets)
                    except Exception as error:
                        logger.warning("event=photoshoot_session_runtime_unavailable error_type=%s",type(error).__name__)
                    target_assets=(repository.ordered_assets(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_id=target_lifecycle.photoshoot_id) if target_lifecycle else ())
                    action=engine.decide(customer_profile_id=profile.customer_commerce_profile_id,lifecycle=current_lifecycle,assets=assets,target_lifecycle=target_lifecycle,target_assets=target_assets,momentum_evidence=BuyingMomentumEvidence(purchases=int(progression_context.get('current_conversation_purchase_count') or (1 if congratulate_allowed else 0)),rapid_purchases=int(progression_context.get('rapid_purchase_count') or 0),explicit_more=bool(progression_context.get('explicit_request_for_more')),declined=bool(progression_context.get('offer_declined')),expired_intents=int(progression_context.get('expired_intent_count') or (1 if reason is CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED else 0)),consecutive_no_response=int(progression_context.get('consecutive_offer_no_response') or 0),active_intent=active is not None,cooldown=reason is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN,runtime_suppressed=decision in {CustomerSalesDecisionType.MANUAL_REVIEW}),active_purchase_intent_id=(active.purchase_intent_id if active else None),sales_session_id=progression_context.get('sales_session_id'),bridge_recent=bool(progression_context.get('recent_bridge_to_target')),selling_authorized=(sell_allowed or nudge_allowed or decision in {CustomerSalesDecisionType.CONTINUE_CONVERSATION,CustomerSalesDecisionType.NO_SALE}))
                    if session_runtime_state is not None:
                        if (
                            session_runtime_state.status.value == "ACTIVE"
                            and session_runtime_state.current_sales_role == "FREE_TEASER"
                            and session_runtime_state.current_asset_id not in set(session_runtime_state.owned_asset_ids)
                            and active is None
                        ):
                            from app.models.autonomous_sales_progression import NextSalesActionType
                            action=replace(
                                action,action=NextSalesActionType.CONTINUE_PHOTOSHOOT,
                                selected_asset_id=session_runtime_state.current_asset_id,
                                selected_offering_id=None,publication_id=None,delivery_url=None,
                                reason="Execute the persisted Session Sales Strategy free teaser.",
                                decision_trace=("active_lifecycle","session_runtime","free_teaser"),
                            )
                        action=replace(action,metadata={**dict(action.metadata),"sessionRuntime":session_runtime_state.to_context()})
                    result=replace(result,next_sales_action=action)
                    # The opportunity engine is authoritative for fulfillment.
                    # Never leave the generic ranked Offering attached when it
                    # differs from the deterministic current chapter.
                    if action.selected_offering_id is not None and action.selected_offering_id != result.recommended_offering_id:
                        selector_repository=getattr(self.offering_selector,'repository',None)
                        getter=getattr(selector_repository,'get_candidate',None)
                        selected=getter(action.selected_offering_id,creator_profile_id=creator_profile_id) if callable(getter) else None
                        if selected:
                            product_context_builder = getattr(
                                self.offering_selector, "_product_context", None
                            )
                            selected_context = (
                                product_context_builder(selected)
                                if callable(product_context_builder) else {}
                            )
                            result=replace(result,recommended_offering_id=action.selected_offering_id,recommended_publication_id=action.publication_id,recommended_delivery_url=action.delivery_url,recommended_offering_title=str(selected.get('title') or ''),recommended_offering_short_description=selected.get('description'),recommended_offering_price_minor=selected.get('price_minor'),recommended_offering_currency=selected.get('currency'),recommended_product_context=immutable_mapping(selected_context))
                    claim=getattr(repository,'claim_action',None)
                    if callable(claim):
                        claimed=claim(action)
                        if claimed and claimed.get('decision'):
                            from app.models.autonomous_sales_progression import NextSalesAction
                            action=NextSalesAction.from_context(claimed['decision'])
                            result=replace(result,next_sales_action=action)
            except Exception as error:
                logger.warning("event=autonomous_sales_progression_unavailable error_type=%s",type(error).__name__)
        logger.info(
            "event=decision_generated decision=%s reason_code=%s buyer_stage=%s "
            "buyer_uuid=%s current_offer=%s purchase_state=%s timing_ms=%s",
            decision.value, reason.value, stage.value, buyer_uuid,
            result.active_offering_id, conversion,
            result.decision_metadata["evaluationMs"],
        )
        return result

    def _apply_photoshoot_opportunity_policy(self, *, creator_profile_id,
                                             customer_profile, context):
        """Apply explicit bounded-opportunity decisions before Offering selection."""
        profile_id = getattr(customer_profile, "customer_commerce_profile_id", None)
        if profile_id is None:
            return None
        try:
            service = self.photoshoot_lifecycles
            if service is None:
                from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                service = CustomerPhotoshootLifecycleService()
            opportunity = service.active_for_customer(
                creator_profile_id=creator_profile_id,
                customer_commerce_profile_id=profile_id,
            )
            if opportunity is None:
                return None
            requested = context.get("requested_photoshoot_reference")
            close_reason = next((reason for enabled, reason in (
                (context.get("close_photoshoot_opportunity"), "SALES_BRAIN_CLOSE"),
                (context.get("operator_close_photoshoot"), "OPERATOR_CLOSE"),
                (context.get("customer_requests_different_content"), "CUSTOMER_REQUESTED_DIFFERENT_CONTENT"),
                (context.get("stronger_opportunity_available"), "STRONGER_OPPORTUNITY"),
                (requested and str(requested) != opportunity.photoshoot_id, "DIFFERENT_PHOTOSHOOT_REQUESTED"),
                (int(context.get("consecutive_offer_no_response") or 0) >= self.config.photoshoot_objection_recovery_limit, "REPEATED_NON_RESPONSE"),
            ) if enabled), None)
            if close_reason:
                return service.close_opportunity(opportunity, reason=close_reason)
            if context.get("offer_declined") or context.get("photoshoot_objection"):
                opportunity = service.enter_objection(opportunity, reason=str(context.get("objection_type") or "CUSTOMER_OBJECTION"))
            if opportunity.status.value == "OBJECTION":
                if context.get("objection_recovered") or context.get("explicit_request_for_more"):
                    opportunity = service.attempt_recovery(
                        opportunity, recovered=True,
                        recovery_limit=self.config.photoshoot_objection_recovery_limit,
                        reason="CUSTOMER_REENGAGED",
                    )
                elif context.get("objection_recovery_attempted") or context.get("objection_recovery_failed"):
                    opportunity = service.attempt_recovery(
                        opportunity, recovered=False,
                        recovery_limit=self.config.photoshoot_objection_recovery_limit,
                        reason="RECOVERY_DID_NOT_CONVERT",
                    )
            return opportunity
        except Exception as error:
            logger.warning("event=photoshoot_opportunity_policy_unavailable error_type=%s", type(error).__name__)
            return None

    @staticmethod
    def _signal(signal):
        if signal is None:
            return {}
        return {
            "buyerUuid": signal.buyer_uuid,
            "telegramUserId": signal.telegram_user_id,
            "identityResolved": signal.identity_resolved,
            "lifetimeSpendMinor": signal.lifetime_spend_minor,
            "purchaseCount": signal.purchase_count,
            "lastPurchaseAt": (
                signal.last_purchase_at.isoformat()
                if signal.last_purchase_at else None
            ),
            "currentActiveOfferId": signal.current_active_offer_id,
            "currentOfferStatus": signal.current_offer_status,
            "conversionState": signal.conversion_state,
            "latestTransaction": signal.latest_transaction,
            "attributionState": signal.attribution_state,
            "reconciliationState": signal.reconciliation_state,
        }

    @staticmethod
    def _priority(decision, reason):
        priorities = {
            CustomerSalesReasonCode.IDENTITY_UNRESOLVED: 1,
            CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING: 2,
            CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN: 3,
            CustomerSalesReasonCode.PURCHASE_VERIFIED: 4,
            CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN: 5,
            CustomerSalesReasonCode.ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE: 6,
            CustomerSalesReasonCode.CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION: 6,
            CustomerSalesReasonCode.ACTIVE_OFFER_NUDGE_ELIGIBLE: 7,
            CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED: 8,
            CustomerSalesReasonCode.NO_ACTIVE_OFFER: 9,
            CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING: 10,
            CustomerSalesReasonCode.NO_SELLING_STRATEGY: 9,
        }
        return priorities.get(reason, 0)

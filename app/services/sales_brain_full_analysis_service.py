"""Compact Full Analysis projection of canonical Sales Brain outputs."""
from __future__ import annotations

import re
from collections.abc import Mapping

from app.models.customer_sales_decision import (
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)


class SalesBrainFullAnalysisService:
    """Project existing truth; never classify, select, authorize, or mutate."""

    PURCHASE_CLAIM = re.compile(
        r"\b(?:i (?:bought|purchased|paid for|unlocked) (?:it|that)|"
        r"i(?:'|’)ve (?:bought|purchased|paid for|unlocked) (?:it|that))\b",
        re.I,
    )
    PRICE_REQUEST = re.compile(
        r"\b(?:how much|what(?:'s| is) the price|what does it cost|price)\b",
        re.I,
    )
    PRESENTATION_ACTIONS = frozenset({
        CustomerSalesDecisionType.PRESENT_OFFER,
        CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
        CustomerSalesDecisionType.UPSELL,
        CustomerSalesDecisionType.CROSS_SELL,
    })

    @classmethod
    def project(cls, decision: CustomerSalesDecision | None, *,
                runtime_diagnostics: Mapping | None = None,
                customer_message: str = "") -> dict:
        if decision is None:
            return cls._not_evaluated()
        runtime = dict(runtime_diagnostics or {})
        metadata = dict(decision.decision_metadata or {})
        receptiveness = dict(metadata.get("commercialReceptiveness") or {})
        opportunity = dict(metadata.get("commercialOpportunity") or {})
        objection = dict(metadata.get("commercialObjection") or {})
        recovery = dict(metadata.get("objectionRecovery") or {})
        cooldown = dict(metadata.get("purchaseCooldown") or {})
        buying_window = dict(metadata.get("activeBuyingWindow") or {})
        session_escalation = dict(metadata.get("sessionEscalation") or {})
        deferred = dict(metadata.get("deferredContinuation") or {})
        continuation = dict(metadata.get("continuation") or {})
        memory = dict(metadata.get("customerCommerceMemory") or {})
        selector = dict(metadata.get("offeringSelector") or {})
        next_best = dict(metadata.get("nextBestOffer") or {})
        intelligence = dict(metadata.get("commercialIntelligence") or {})
        session_context = dict(intelligence.get("salesSessionContext") or {})
        if not session_context.get("salesSessionId"):
            session_context = dict(runtime.get("active_sales_session") or {})
        progression = dict(metadata.get("salesProgression") or {})
        transition = dict(metadata.get("salesProgressionTransition") or {})
        proactive = dict(metadata.get("proactiveProgression") or {})
        value_attention = dict(
            runtime.get("customer_value_attention")
            or metadata.get("customerValueAttention") or {}
        )
        style = dict(runtime.get("conversationStyle") or {})
        signal = dict(decision.commerce_signal or {})
        classifier = dict(
            dict(runtime.get("intent") or {}).get("classifier_result")
            or dict(runtime.get("route") or {}).get("classifier_result")
            or {}
        )
        disclosure_memory = dict(
            dict(runtime.get("conversational_memory") or {}).get(
                "customerSelfDisclosure"
            ) or {}
        )
        conversational_memory = dict(runtime.get("conversational_memory") or {})
        continuity = dict(conversational_memory.get("continuityGuidance") or {})
        generation_compliance = dict(
            conversational_memory.get("generationCompliance") or {}
        )
        relationship_discovery = dict(
            value_attention.get("relationshipDiscovery") or {}
        )
        memory_policy = dict(
            conversational_memory.get("operationalMemoryPolicy") or {}
        )
        discovery_generation = dict(
            generation_compliance.get("relationshipDiscovery")
            or style.get("relationshipDiscovery")
            or {}
        )
        strategy_authority = dict(
            runtime.get("commercial_strategy_authority") or {}
        )
        ai_readiness_observation = dict(
            runtime.get("ai_commerce_readiness_observation") or {}
        )
        intimacy = dict(runtime.get("intimacy_overrides") or {})
        provider = dict(
            runtime.get("provider_preview")
            or runtime.get("generation_preview") or {}
        )

        positive = cls._positive_evidence(
            receptiveness, opportunity, memory, intelligence,
        )
        resistance = cls._resistance_evidence(receptiveness, objection)
        fresh_direct = bool(receptiveness.get("freshDirectIntentDetected"))
        opportunity_exists = bool(
            fresh_direct
            or objection.get("alternativeSelectionAllowed")
            or opportunity.get("presentConsidered") is True
        )
        verified_count = int(
            memory.get("verifiedPurchaseCount", memory.get(
                "lifetimePurchaseCount", signal.get("purchaseCount", 0)
            )) or 0
        )
        verified_purchase = bool(verified_count > 0)
        conversational_claim = bool(cls.PURCHASE_CLAIM.search(customer_message or ""))
        provider_source = (
            "PROVIDER_VERIFIED_COMMERCE_MEMORY"
            if verified_purchase else "NONE"
        )
        offer_authorized = bool(runtime.get("offer_authorized"))
        presentation_authorized = bool(
            offer_authorized
            and runtime.get("commerce_execution_policy")
            == "COMMERCE_PRESENTATION_ALLOWED"
        )
        controlling_gate = cls._controlling_gate(
            decision, objection=objection, cooldown=cooldown,
            selector=selector, runtime=runtime,
        )
        suppression_reason = cls._suppression_reason(
            controlling_gate, opportunity_exists, presentation_authorized,
            decision,
        )
        selected_trace = next((
            dict(item) for item in tuple(selector.get("recommendationTrace") or ())
            if isinstance(item, Mapping) and item.get("selected") is True
        ), {})
        classification = cls._selection_classification(
            decision, next_best, objection, verified_count,
        )
        recovery_attempts = int(objection.get("recoveryAttemptCount") or 0)
        pressure_reduced = bool(
            objection.get("pressureDecrease")
            or receptiveness.get("state") in {"COOLING", "BACK_OFF"}
            or cooldown.get("blockingCurrentSale")
        )
        active_offer_continuation = dict(
            metadata.get("activeOfferContinuation") or {}
        )
        sexual_projection = dict(
            metadata.get("sustainedSexualReceptiveness") or {}
        )
        commercial_response_interest = str(
            transition.get("transitionSignal") or ""
        ) in {
            "POSITIVE_TEASE_RESPONSE", "POSITIVE_RESPONSE_TO_AVA_TEASE",
            "REVEAL_REQUEST", "SUSTAINED_INTEREST",
        }
        prior_progression_phase = str(
            transition.get("priorPhase")
            or progression.get("priorPhase")
            or runtime.get("progressionBefore")
            or ""
        ).upper()
        current_progression_phase = str(
            progression.get("phase")
            or runtime.get("progressionAfter")
            or ""
        ).upper()
        direct_intent_bypass = bool(
            decision.reason_code in {
                CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
                CustomerSalesReasonCode.PRICE_REQUEST,
                CustomerSalesReasonCode.SESSION_NEXT_UNLOCK_REQUEST,
            }
            and decision.decision in cls.PRESENTATION_ACTIONS
        )
        build_interest_observed = bool(
            decision.decision is CustomerSalesDecisionType.BUILD_INTEREST
            or "BUILD_INTEREST" in {
                prior_progression_phase, current_progression_phase,
            }
        )
        reveal_interest_observed = (
            str(runtime.get("adaptiveCustomerPhase") or "").upper()
            == "REVEAL_INTEREST"
        )
        realized_conversion_path = (
            "DIRECT_INTENT_BYPASS" if direct_intent_bypass
            else "EARNED_PROGRESSION" if (
                decision.decision in cls.PRESENTATION_ACTIONS
                and build_interest_observed
            ) else None
        )
        copy_diagnostics = dict(
            runtime.get("offering_copy_diagnostics") or {}
        )
        opportunity_exposure_count = int(
            value_attention.get("commercialOpportunityExposureCount") or 0
        )
        proactive_tease_count = int(
            value_attention.get("proactiveTeaseDeliveredCount") or 0
        )
        build_exposure_count = int(
            value_attention.get("buildInterestExposureCount") or 0
        )
        offer_exposure_count = int(
            value_attention.get("offerExposureCount") or 0
        )
        opportunity_grounded_tease_count = max(
            0, opportunity_exposure_count
            - proactive_tease_count - build_exposure_count - offer_exposure_count,
        )
        tease_type = runtime.get("tease_type") or metadata.get("teaseType")

        return {
            "schemaVersion": "sales_brain_full_analysis_v1",
            "activeBuyingWindow": bool(buying_window.get("active")),
            "activeBuyingWindowReason": buying_window.get("reason"),
            "activeBuyingWindowSource": (
                buying_window.get("source") or "PRODUCTION_CUSTOMER_STATE"
            ),
            "activeBuyingWindowEvidence": dict(
                buying_window.get("evidence") or {}
            ),
            "activeBuyingWindowAuthoritySatisfied": bool(
                buying_window.get("activeBuyingWindowAuthoritySatisfied")
            ),
            "continuationCommercialContextPresent": bool(
                buying_window.get("continuationCommercialContextPresent")
            ),
            "customerLedContinuation": bool(
                buying_window.get("customerLedContinuation")
            ),
            "currentCommercialMomentum": buying_window.get(
                "currentCommercialMomentum", "INACTIVE"
            ),
            "explicitConversationDetected": bool(
                provider.get("explicit_requested")
            ),
            "intimacyEntitlement": (
                intimacy.get("intimacy_entitlement")
                or provider.get("intimacy_entitlement")
            ),
            "intimacyEntitlementReason": (
                intimacy.get("intimacy_entitlement_reason")
                or provider.get("intimacy_entitlement_reason")
            ),
            "intimacyInvestment": (
                intimacy.get("intimacy_investment")
                or provider.get("intimacy_investment")
            ),
            "intimacyInvestmentInputs": dict(
                intimacy.get("intimacy_investment_inputs")
                or provider.get("intimacy_investment_inputs") or {}
            ),
            "premiumSextingAllowed": bool(
                intimacy.get("premium_sexting_allowed")
            ),
            "explicitAllowed": bool(intimacy.get("explicit_allowed")),
            "canonicalBuyerAuthorityUsed": bool(
                intimacy.get("canonical_buyer_authority_used")
                or provider.get("canonical_buyer_authority_used")
            ),
            "legacyBuyerMemoryAuthorityUsed": bool(
                intimacy.get("legacy_buyer_memory_authority_used")
                or provider.get("legacy_buyer_memory_authority_used")
            ),
            "responseProvider": (
                provider.get("responseProvider")
                or provider.get("selected_provider")
            ),
            "providerRoutingReason": provider.get("reason"),
            "grokEligible": bool(provider.get("grok_eligible")),
            "grokAttempted": bool(provider.get("grokAttempted")),
            "grokSucceeded": bool(provider.get("grokSucceeded")),
            "providerFallbackAttempted": bool(
                provider.get("providerFallbackAttempted")
            ),
            "providerFallbackProvider": provider.get(
                "providerFallbackProvider"
            ),
            "providerFallbackOutcome": provider.get(
                "providerFallbackOutcome"
            ),
            "momentumDecayReason": buying_window.get("momentumDecayReason"),
            "scenarioInfluencedCommercialAuthority": bool(
                buying_window.get("scenarioInfluencedCommercialAuthority", False)
            ),
            "explicitContinuationDetected": bool(
                dict(buying_window.get("evidence") or {}).get(
                    "explicitContinuationIntent"
                )
            ),
            "purchaseCooldownActive": bool(cooldown.get("active")),
            "purchaseCooldownOverridden": bool(cooldown.get("override")),
            "purchaseCooldownOverrideReason": cooldown.get("overrideReason"),
            "deferredContinuationPending": deferred.get("state") in {
                "PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"
            },
            "deferredContinuationSourceInbound": deferred.get(
                "sourceInboundMessageId"
            ),
            "deferredContinuationConsumed": bool(
                runtime.get("deferred_continuation_consumed")
                or deferred.get("state") == "CONSUMED"
            ),
            "purchaseStreakCount": verified_count,
            "recentPurchaseCount": int(
                memory.get("recentPurchaseCount", verified_count) or 0
            ),
            "currentUniqueOpportunityCount": int(
                opportunity.get("presentedOpportunityCount")
                or opportunity.get("presented_opportunity_count") or 0
            ),
            "currentConvertedOpportunityCount": int(
                opportunity.get("convertedOpportunityCount")
                or opportunity.get("converted_opportunity_count") or 0
            ),
            "currentFailedOpportunityCount": int(
                opportunity.get("failedNonconvertedOpportunityCount")
                or opportunity.get("failed_nonconverted_opportunity_count") or 0
            ),
            "nextOfferOwnershipExclusions": list(
                selector.get("exclusionReasons") or ()
            ),
            "anotherSaleAppropriateNow": bool(
                buying_window.get("anotherSaleAppropriateNow")
            ),
            "anotherSaleSuppressionReason": buying_window.get(
                "anotherSaleSuppressionReason"
            ),
            "recentPurchaseVelocity": dict(
                session_escalation.get("recentPurchaseVelocity") or {}
            ),
            "explicitContinuationCount": int(
                session_escalation.get("explicitContinuationCount") or 0
            ),
            "currentContinuationIntent": session_escalation.get(
                "currentContinuationIntent"
            ),
            "sessionCandidate": bool(
                session_escalation.get("sessionCandidate")
            ),
            "sessionCandidateReason": session_escalation.get(
                "sessionCandidateReason"
            ),
            "sessionCompatibleInventoryAvailable": bool(
                session_escalation.get("sessionCompatibleInventoryAvailable")
            ),
            "sessionEscalationDecision": session_escalation.get(
                "sessionEscalationDecision"
            ),
            "sessionEscalationReason": session_escalation.get(
                "sessionEscalationReason"
            ),
            "continueDiscretePpvsAuthorized": bool(
                session_escalation.get("continueDiscretePpvsAuthorized")
            ),
            "sessionProposalAuthorized": bool(
                session_escalation.get("sessionProposalAuthorized")
            ),
            "sessionProposalDelivered": bool(
                runtime.get("sessionProposalDelivered")
                or session_escalation.get("sessionProposalDelivered")
            ),
            "sessionProposalPending": bool(
                runtime.get("sessionProposalPending")
                if "sessionProposalPending" in runtime
                else session_escalation.get("sessionProposalPending")
            ),
            "sessionProposalId": session_escalation.get("sessionProposalId"),
            "sessionProposalSourceInbound": session_escalation.get(
                "sessionProposalSourceInbound"
            ),
            "sessionProposalCreatedAt": session_escalation.get(
                "sessionProposalCreatedAt"
            ),
            "sessionProposalExpiresAt": session_escalation.get(
                "sessionProposalExpiresAt"
            ),
            "sessionProposalCustomerReaction": session_escalation.get(
                "sessionProposalCustomerReaction"
            ),
            "sessionProposalReactionSourceInbound": session_escalation.get(
                "sessionProposalReactionSourceInbound"
            ),
            "sessionProposalConsumed": bool(
                session_escalation.get("sessionProposalConsumed")
            ),
            "sessionProposalInvalidationReason": session_escalation.get(
                "sessionProposalInvalidationReason"
            ),
            "sessionStartAuthorityEligible": bool(
                session_escalation.get("sessionStartAuthorityEligible")
            ),
            "sessionStarted": bool(session_escalation.get("sessionStarted")),
            "purchaseCooldownActive": bool(
                session_escalation.get("purchaseCooldownActive")
                or cooldown.get("active")
            ),
            "purchaseCooldownSuppressedForProposalReaction": bool(
                session_escalation.get(
                    "purchaseCooldownSuppressedForProposalReaction"
                )
            ),
            "scenarioInfluencedCommercialAuthority": False,
            "activeSessionPrecedence": bool(
                session_escalation.get("activeSessionPrecedence")
            ),
            "sessionUnavailableFallback": bool(
                session_escalation.get("sessionUnavailableFallback")
            ),
            "ownershipSafeOrdinaryInventoryAvailable": bool(
                session_escalation.get("ownershipSafeOrdinaryInventoryAvailable")
            ),
            "sexualCommercialProgression": {
                "sustainedSexualReceptiveness": bool(
                    sexual_projection.get("value")
                ),
                "sustainedSexualReceptivenessAuthority": (
                    sexual_projection.get("authority")
                    or metadata.get("sustainedSexualReceptivenessAuthority")
                ),
                "sexualEngagementDetected": bool(
                    sexual_projection.get("sexualEngagementDetected")
                    or style.get("sexualEngagementDetected")
                ),
                "sexualResponseExpected": bool(style.get("sexualResponseExpected")),
                "sexualResponseSatisfied": style.get("sexualResponseSatisfied"),
                "flirtResponseExpected": bool(style.get("flirtResponseExpected")),
                "flirtResponseSatisfied": style.get("flirtResponseSatisfied"),
                "teaseType": tease_type,
                "commercialTeaseAuthorized": bool(
                    runtime.get("commercial_tease_authorized")
                ),
                "commercialTeaseWordingSatisfied": runtime.get(
                    "commercial_tease_wording_satisfied"
                ),
                "commercialTeaseDelivered": bool(
                    runtime.get("commercial_tease_delivered")
                ),
                "commercialTeaseExposureRecorded": bool(
                    runtime.get("commercial_tease_exposure_recorded")
                ),
                "teaseOffering": runtime.get("tease_offering"),
                "progressionFinalizedAfterDelivery": bool(
                    runtime.get("progression_finalized_after_delivery")
                ),
                "adaptiveSwitchEligible": bool(
                    runtime.get("commercial_tease_delivered")
                    and runtime.get("commercial_tease_exposure_recorded")
                    and runtime.get("progression_finalized_after_delivery")
                ),
                "adaptiveSwitchReason": (
                    "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE"
                    if runtime.get("commercial_tease_delivered")
                    and runtime.get("commercial_tease_exposure_recorded")
                    and runtime.get("progression_finalized_after_delivery")
                    else "AWAITING_CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_EXPOSURE"
                ),
                "adaptiveCustomerPhase": runtime.get("adaptiveCustomerPhase"),
                "adaptiveCustomerSource": runtime.get("adaptiveCustomerSource"),
                "adaptiveCustomerService": runtime.get("adaptiveCustomerService"),
                "adaptiveCustomerWordingSource": runtime.get(
                    "adaptiveCustomerWordingSource"
                ),
                "adaptivePhaseReason": runtime.get("adaptivePhaseReason"),
                "progressionBefore": runtime.get("progressionBefore"),
                "progressionAfter": runtime.get("progressionAfter"),
                "recentCustomerRepetitionRisk": bool(
                    runtime.get("recentCustomerRepetitionRisk")
                ),
                "commercialResponseInterest": commercial_response_interest,
                "realizedConversionPath": realized_conversion_path,
                "buildInterestObserved": build_interest_observed,
                "revealInterestObserved": reveal_interest_observed,
                "directIntentBypassUsed": direct_intent_bypass,
                "commercialResponseInterestMeaning": (
                    "POSITIVE_RESPONSE_TO_TEASE_OR_REVEAL_REQUEST; NOT GENERAL_ENGAGEMENT"
                ),
                "opportunityExposure": bool(
                    runtime.get("commercial_tease_exposure_recorded")
                    or runtime.get("build_interest_exposure")
                    or runtime.get("offer_exposure")
                ),
                "repeatedResponseDetected": bool(
                    style.get("repeatedResponseDetected")
                ),
                "repeatedResponseSource": style.get("repeatedResponseSource"),
                "recentPhraseRepetitionRisk": bool(
                    style.get("recentPhraseRepetitionRisk")
                ),
                "repetitionRepairAttempted": bool(
                    style.get("repetitionRepairAttempted")
                ),
                "repetitionRepairOutcome": style.get("repetitionRepairOutcome"),
                "finalResponseRepetitionSatisfied": style.get(
                    "finalResponseRepetitionSatisfied"
                ),
                "trajectorySexualAlignmentRequired": style.get(
                    "trajectorySexualAlignmentRequired"
                ),
                "trajectorySexualAlignmentSatisfied": style.get(
                    "trajectorySexualAlignmentSatisfied"
                ),
                "trajectorySexualAlignmentSource": style.get(
                    "trajectorySexualAlignmentSource"
                ),
            },
            "paidPresentationContract": {
                "priceRequestDetected": bool(
                    runtime.get("priceRequestDetected")
                    or cls.PRICE_REQUEST.search(customer_message or "")
                ),
                "authoritativeOffering": runtime.get("authoritativeOffering"),
                "canonicalInternalPriceMinor": runtime.get("canonicalInternalPriceMinor"),
                "canonicalInternalCurrency": runtime.get("canonicalInternalCurrency"),
                "paidPresentationAuthorized": bool(runtime.get("paidPresentationAuthorized")),
                "paidPresentationDelivered": bool(runtime.get("paidPresentationDelivered")),
                "conversationalPriceSuppressed": bool(runtime.get("conversationalPriceSuppressed")),
                "numericPricePresentInAvaProse": bool(runtime.get("numericPricePresentInAvaProse")),
                "purchaseIntent": runtime.get("purchaseIntent"),
                "ctaLinkTruth": dict(runtime.get("ctaLinkTruth") or {}),
                "priceAuthority": "STRUCTURED_PAID_PRESENTATION",
                "paidPresentationPurpose": runtime.get("paidPresentationPurpose"),
                "sameOfferAsPreviousPresentation": bool(
                    runtime.get("sameOfferAsPreviousPresentation")
                ),
                "customerInitiatedOfferContinuation": bool(
                    runtime.get("customerInitiatedOfferContinuation")
                ),
                "continuationIntentType": runtime.get("continuationIntentType"),
                "recentPaidPresentationWording": list(
                    runtime.get("recentPaidPresentationWording") or ()
                ),
                "paidPresentationRepetitionRisk": dict(
                    runtime.get("paidPresentationRepetitionRisk") or {}
                ),
                "paidPresentationWordingSource": runtime.get(
                    "paidPresentationWordingSource"
                ),
                "repetitionRepairAttempted": bool(
                    runtime.get("repetitionRepairAttempted")
                ),
                "repetitionRepairOutcome": runtime.get(
                    "repetitionRepairOutcome"
                ),
            },
            "authorityArchitecture": {
                "commercialStrategy": {
                    "owner": "CustomerSalesBrainService",
                    "legacyDecisionEngineCommerce": "DISABLED_UNREACHABLE",
                    "gptRole": "WORDING_ONLY",
                },
                "buyerValueAndAttention": {
                    "owner": "CustomerValueAttentionService",
                    "purchaseTruth": "PROVIDER_BACKED_COMMERCE_MEMORY",
                    "legacyBuyerWhaleFlags": "ADVISORY_ONLY",
                },
                "contactTiming": {
                    "owner": "CustomerContactAuthorityService",
                    "decision": dict(runtime.get("customerContactPolicy") or {}),
                },
                "salesSession": {
                    "owner": "SalesSessionService",
                    "scope": "SESSION_SPECIFIC_COMMERCIAL_ENVELOPE",
                    "contentProgression": "PHOTOSHOOT_LIFECYCLE_AND_OWNERSHIP",
                    "ordinarySalesProgression": "ADVISORY_WITHIN_SESSION_CONTEXT",
                },
                "memory": {
                    "conversationalFacts": "ConversationalMemoryService",
                    "purchaseSpendOwnership": "CANONICAL_COMMERCE_MEMORY",
                    "legacyUserMemory": "ADVISORY_COMPATIBILITY_ONLY",
                    "decisionEngineWorkingMemory": "EPHEMERAL_GENERATION_CONTEXT",
                },
                "relationshipAndProgression": {
                    "telegramProspectRelationshipState": "UNMAPPED_PROSPECT_DURABILITY",
                    "salesProgression": "CUSTOMER_SALES_BRAIN_STRATEGY_CONTEXT",
                    "salesSessionProgression": "SESSION_SPECIFIC",
                    "premiumIntimacyState": "ADVISORY_CONVERSATIONAL_STYLE",
                },
            },
            "customerValueAttention": value_attention or {
                "status": "NOT_PROJECTED"
            },
            "relationshipDiscovery": {
                **relationship_discovery,
                "questionActuallyAsked": bool(
                    discovery_generation.get("questionActuallyAsked")
                ),
                "questionReason": discovery_generation.get("questionReason"),
                "questionValue": discovery_generation.get("questionValue"),
                "customerAnsweredDiscovery": discovery_generation.get(
                    "customerAnsweredDiscovery"
                ),
                "memoryLearnedFromAnswer": bool(
                    discovery_generation.get("memoryLearnedFromAnswer")
                ),
            },
            "conversationInvestment": {
                "desiredEffort": value_attention.get("effortMode"),
                "actualResponseEffort": (
                    "SHORT" if int(style.get("responseLengthWords") or 0) <= 12
                    else "MEDIUM" if int(style.get("responseLengthWords") or 0) <= 30
                    else "EXPANDED"
                ) if style else "NOT_OBSERVED",
                "taperApplied": bool(value_attention.get("taperApplied")),
                "taperReason": value_attention.get("taperReason"),
            },
            "attentionEconomics": {
                "presentedOpportunities": value_attention.get(
                    "presentedOpportunityCount", 0
                ),
                "failedNonconvertedOpportunities": value_attention.get(
                    "failedNonconvertedOpportunityCount", 0
                ),
                "convertedOpportunities": value_attention.get(
                    "convertedOpportunityCount", 0
                ),
                "activeUnresolvedOpportunity": bool(value_attention.get(
                    "activeUnresolvedOpportunity"
                )),
                "purchaseCount": value_attention.get("purchaseCount", 0),
                "timeWasterRisk": value_attention.get("timeWasterRisk"),
                "timeWasterEvidence": list(
                    value_attention.get("timeWasterEvidence") or ()
                ),
                "attentionTier": value_attention.get("attentionTier"),
                "effortMode": value_attention.get("effortMode"),
                "taperApplied": bool(value_attention.get("taperApplied")),
                "taperReason": value_attention.get("taperReason"),
                "lowCostNurtureEligible": bool(value_attention.get(
                    "lowCostNurtureEligible"
                )),
                "lowCostNurtureActive": bool(value_attention.get(
                    "lowCostNurtureActive"
                )),
                "lowCostNurtureReason": value_attention.get(
                    "lowCostNurtureReason"
                ),
                "nurtureResponseBudget": value_attention.get(
                    "nurtureResponseBudget", 1
                ),
                "nurtureResponsesUsed": value_attention.get(
                    "nurtureResponsesUsed", 0
                ),
                "nurtureNextOptionalResponseAt": value_attention.get(
                    "nurtureNextOptionalResponseAt"
                ),
                "optionalOrdinaryReplySuppressed": bool(value_attention.get(
                    "optionalOrdinaryReplySuppressed"
                )),
                "suppressionReason": value_attention.get("suppressionReason"),
                "freshCommercialIntentDetected": bool(value_attention.get(
                    "freshCommercialIntentDetected"
                )),
                "nurtureBypassedForCommercialIntent": bool(value_attention.get(
                    "nurtureBypassedForCommercialIntent"
                )),
                "nurtureExitedAfterPurchase": bool(value_attention.get(
                    "nurtureExitedAfterPurchase"
                )),
                "policySource": "CustomerValueAttentionService",
            },
            "buyerRetention": {
                "verifiedBuyerStatus": value_attention.get("buyerStatus"),
                "buyerStage": value_attention.get("buyerStage"),
                "purchaseCount": value_attention.get("purchaseCount", 0),
                "totalSpendMinor": value_attention.get(
                    "lifetimeSpendMinor", 0
                ),
                "lastPurchaseAt": value_attention.get("lastPurchaseAt"),
                "purchaseRecencyDays": value_attention.get(
                    "purchaseRecencyDays"
                ),
                "valueTier": value_attention.get("valueTier"),
                "retentionLifecycle": value_attention.get(
                    "retentionLifecycle"
                ),
                "retentionPriority": value_attention.get(
                    "retentionPriority"
                ),
                "attentionTier": value_attention.get("attentionTier"),
                "effortMode": value_attention.get("effortMode"),
                "reactivationState": value_attention.get(
                    "reactivationState"
                ),
                "relationshipInvestment": value_attention.get(
                    "relationshipInvestment"
                ),
                "memoryPriority": value_attention.get("memoryPriority"),
                "memoryPriorityOperational": bool(
                    conversational_memory.get("memoryPriorityOperational")
                ),
                "operationalMemoryPolicy": memory_policy,
                "salesPressure": value_attention.get("salesPressure"),
                "offerCadence": value_attention.get("offerCadence"),
                "buyerProtection": bool(
                    value_attention.get("buyerProtectionApplied")
                ),
                "relationshipDiscoveryAuthorized": bool(
                    relationship_discovery.get("allowed")
                ),
                "memoryCandidatesRetrieved": list(
                    conversational_memory.get("retrievedKeys") or ()
                ),
                "memoryCandidatesUsed": list(
                    generation_compliance.get("memoriesUsed")
                    or style.get("memoriesUsed") or ()
                ),
                "buyerReactiveConversationAllowed": bool(
                    value_attention.get("buyerStatus") == "VERIFIED_BUYER"
                    and not dict(metadata.get("contextualCustomerTone") or {}).get(
                        "explicitDisengagement"
                    )
                    and not dict(metadata.get("outboundSuppression") or {}).get(
                        "suppressed"
                    )
                ),
                "commercialCooldownActive": bool(
                    cooldown.get("active")
                    or value_attention.get("offerCadence")
                        == "POST_PURCHASE_CAREFUL"
                ),
                "relationshipCooldownActive": bool(
                    value_attention.get("buyerStatus") == "VERIFIED_BUYER"
                    and (
                        dict(metadata.get("contextualCustomerTone") or {}).get(
                            "explicitDisengagement"
                        )
                        or dict(metadata.get("outboundSuppression") or {}).get(
                            "suppressed"
                        )
                    )
                ),
                "upsellAuthorized": bool(decision.upsell_allowed),
                "crossSellAuthorized": bool(decision.cross_sell_allowed),
                "authoritativeSource": value_attention.get("authority"),
                "legacyRelationshipObservationsAuthority": (
                    value_attention.get(
                        "legacyRelationshipObservationsAuthority",
                        "ADVISORY_ONLY",
                    )
                ),
                "canonicalSignalsConsumed": list(
                    value_attention.get("canonicalSignalsConsumed") or ()
                ),
                "legacySignalsConsumed": list(
                    value_attention.get("legacySignalsConsumed") or ()
                ),
                "conflictResolution": list(
                    value_attention.get("conflictResolution") or ()
                ),
            },
            "attentionBehaviorEnforcement": {
                "required": bool(style.get("attentionComplianceRequired")),
                "satisfied": style.get("attentionComplianceSatisfied"),
                "strategyProtected": bool(style.get(
                    "attentionComplianceStrategyProtected"
                )),
                "violations": list(
                    style.get("attentionComplianceViolations") or ()
                ),
                "initialViolations": list(
                    style.get("attentionComplianceInitialViolations") or ()
                ),
                "rewriteAttempted": bool(style.get(
                    "attentionComplianceRewriteAttempted"
                )),
                "rewriteOutcome": style.get(
                    "attentionComplianceRewriteOutcome"
                ),
                "actualEffortMode": style.get("attentionPolicyEffortMode"),
            },
            "conversationStyle": style or {"status": "NOT_OBSERVED"},
            "contextualCustomerTone": dict(
                metadata.get("contextualCustomerTone") or {}
            ),
            "identityAbuse": {
                key: metadata.get(key) for key in (
                    "mappingState", "hostilityLevel", "qualifyingAbuse",
                    "abuseCategory", "abuseSeverity",
                    "unmappedTelegramAutoBlocked", "telegramBlockReason",
                    "abuseReviewIncidentId", "abuseReviewStatus",
                    "interactionReviewHoldActive",
                    "mappedCustomerManualReviewRequired",
                )
            },
            "operatorAlert": {
                key: metadata.get(key) for key in (
                    "operatorAlertAuthorized", "operatorAlertAttempted",
                    "operatorAlertConfirmed", "operatorAlertFailed",
                )
            },
            "nurture": {
                "lowCostNurtureActive": value_attention.get("lowCostNurtureActive"),
                "supporterAttentionBoundaryAppropriate": metadata.get(
                    "supporterAttentionBoundaryAppropriate"
                ),
                "supporterAttentionBoundaryDelivered": metadata.get(
                    "supporterAttentionBoundaryDelivered"
                ),
                "supporterAttentionBoundaryPreviouslyDelivered": metadata.get(
                    "supporterAttentionBoundaryPreviouslyDelivered"
                ),
            },
            "commercialReactivation": {
                "commercialInterestType": dict(
                    metadata.get("commercialReceptiveness") or {}
                ).get("commercialInterestType", "NONE"),
                "nurtureBypassedForCommercialInterest": value_attention.get(
                    "nurtureBypassedForCommercialIntent"
                ),
            },
            "outboundSuppression": dict(
                metadata.get("outboundSuppression") or {}
            ),
            "temporalLanguage": {
                key: style.get(key) for key in (
                    "canonicalAvaTimezone", "canonicalAvaLocalTime",
                    "canonicalAvaDaypart", "customerTimezone",
                    "customerTemporalReferenceDetected",
                    "customerTemporalReference",
                    "customerTemporalReferenceTarget",
                    "customerAssumedAvaDaypart", "customerTemporalRelation",
                    "temporalCompatibility", "temporalMismatchDetected",
                    "responseTemporalClaim",
                    "responseTemporalAlignmentSatisfied",
                    "responseTemporalAlignmentReason",
                    "temporalRewriteAttempted", "temporalRewriteOutcome",
                )
            },
            "newProspectWelcome": {
                key: style.get(key) for key in (
                    "newRelationship", "welcomeRequired", "welcomeSatisfied",
                    "newProspectApproachIntensity",
                    "newProspectWarmthExpected",
                    "newProspectWarmthSatisfied",
                    "newProspectMinimumWarmth", "responseWarmthLevel",
                    "receptivenessSignal",
                )
            },
            "socialFlirtation": {
                "socialFlirtationDetected": bool(style.get("socialFlirtationDetected")),
                "socialFlirtationStrength": style.get("socialFlirtationStrength") or "NONE",
                "flirtationEvidence": list(style.get("flirtationEvidence") or ()),
                "flirtResponseExpected": bool(style.get("flirtResponseExpected")),
                "flirtResponseSatisfied": style.get("flirtResponseSatisfied"),
                "sexualEngagement": bool(classifier.get("sexual_engagement")),
                "buyingIntent": bool(classifier.get("buying_intent")),
                "commercialAnchorPresent": bool(opportunity.get("commercialAnchorPresent")),
            },
            "customerSelfDisclosure": {
                "customerSelfDisclosureDetected": bool(style.get("customerSelfDisclosureDetected")),
                "customerSelfDisclosureDomain": style.get("customerSelfDisclosureDomain"),
                "customerSelfDisclosureEvidence": list(style.get("customerSelfDisclosureEvidence") or ()),
                "customerSelfDisclosureSignificance": style.get("customerSelfDisclosureSignificance"),
                "customerSelfDisclosureResponseExpected": bool(style.get("customerSelfDisclosureResponseExpected")),
                "customerSelfDisclosureResponseSatisfied": style.get("customerSelfDisclosureResponseSatisfied"),
                "memoryCandidateCreated": bool(disclosure_memory.get("memoryCandidateCreated")),
                "memoryCandidateType": list(disclosure_memory.get("memoryCandidateType") or ()),
                "memoryPersistenceDecision": disclosure_memory.get("persistenceDecision"),
                "memoryPersistenceReason": disclosure_memory.get("persistenceReason"),
                "memoryPersisted": bool(disclosure_memory.get("memoryPersisted")),
                "memoryRetrievalEligible": bool(disclosure_memory.get("memoryRetrievalEligible")),
                "sharedInterestDetected": bool(style.get("sharedInterestDetected")),
                "sharedInterestDomain": style.get("sharedInterestDomain"),
                "sharedInterestEvidence": list(style.get("sharedInterestEvidence") or ()),
                "sharedInterestClaimAuthorized": bool(style.get("sharedInterestClaimAuthorized")),
                "sharedInterestSource": style.get("sharedInterestSource"),
                "sharedInterestUsedInResponse": bool(style.get("sharedInterestUsedInResponse")),
            },
            "memoryCallback": {
                "memoriesAvailable": bool(
                    generation_compliance.get("memoriesAvailable")
                    or conversational_memory.get("available")
                ),
                "memoriesRetrieved": list(
                    generation_compliance.get("memoriesRetrieved")
                    or conversational_memory.get("retrievedKeys") or ()
                ),
                "memoriesRelevant": list(
                    generation_compliance.get("memoriesRelevant") or ()
                ),
                "memoryCallbackExpected": bool(generation_compliance.get("callbackExpected")),
                "memoryCallbackUsed": bool(style.get("memoryCallbackUsed")),
                "memoriesUsed": list(
                    generation_compliance.get("memoriesUsed")
                    or style.get("memoriesUsed") or ()
                ),
                "memoryCallbackReason": list(continuity.get("relevanceReasons") or ()),
                "memoryCandidates": list(conversational_memory.get("memoryCandidates") or ()),
                "selectedMemoryCallback": continuity.get("strongestMemory"),
                "selectedMemoryDomain": next((
                    next(iter(item.get("domains") or ()), None)
                    for item in conversational_memory.get("memoryCandidates") or ()
                    if item.get("key") == (continuity.get("strongestMemory") or {}).get("key")
                ), None),
                "memoryCallbackNatural": (
                    True if style.get("memoryCallbackUsed") else None
                ),
                "memoryCallbackRequired": bool(
                    generation_compliance.get("callbackRequired")
                ),
                "memoryCallbackCompliance": generation_compliance.get(
                    "callbackCompliance"
                ) or "NOT_EVALUATED",
                "memoryCallbackSuppressionReason": generation_compliance.get("omissionReason"),
            },
            "proactiveProgression": {
                "proactiveProgressionAuthorized": bool(
                    proactive.get("proactiveProgressionAuthorized")
                ),
                "proactiveProgressionReason": proactive.get("proactiveProgressionReason"),
                "proactiveProgressionEvidence": list(
                    proactive.get("proactiveProgressionEvidence") or ()
                ),
                "progressionInitiator": proactive.get("progressionInitiator"),
                "progressionBefore": (
                    proactive.get("progressionBefore") or transition.get("priorPhase")
                ),
                "progressionAfter": (
                    proactive.get("progressionAfter") or transition.get("nextPhase")
                ),
                "progressionAction": proactive.get("progressionAction") or "NONE",
                "proactiveTeaseCooldown": int(
                    proactive.get("proactiveTeaseCooldown") or 0
                ),
                "recentProactiveTease": bool(proactive.get("recentProactiveTease")),
                "customerResponseToPreviousTease": proactive.get(
                    "customerResponseToPreviousTease"
                ) or "NONE",
                "customerBuyingIntentUnchanged": bool(
                    proactive.get("customerBuyingIntentUnchanged", True)
                ),
                "proactiveTeaseExpected": bool(
                    proactive.get("proactiveTeaseExpected")
                    or style.get("proactiveTeaseExpected")
                ),
                "proactiveTeaseSatisfied": bool(
                    (proactive.get("proactiveTeaseSatisfied")
                     if proactive.get("proactiveTeaseSatisfied") is not None
                     else style.get("proactiveTeaseSatisfied"))
                    and (proactive.get("proactiveTeaseDelivered")
                         or runtime.get("proactive_tease_delivered"))
                ),
                "proactiveTeaseDelivered": bool(
                    proactive.get("proactiveTeaseDelivered")
                    or runtime.get("proactive_tease_delivered")
                ),
                "socialFlirtationPresent": bool(
                    runtime.get("social_flirtation_present")
                    or style.get("socialFlirtationPresent")
                    or style.get("socialFlirtationDetected")
                ),
                "commercialTeaseAuthorized": bool(
                    proactive.get("proactiveProgressionAuthorized")
                    and proactive.get("progressionAction") == "TEASE"
                ),
                "commercialTeaseDelivered": bool(
                    proactive.get("proactiveTeaseDelivered")
                    or runtime.get("commercial_tease_delivered")
                ),
                "commercialTeaseSatisfied": bool(
                    proactive.get("proactiveProgressionAuthorized")
                    and proactive.get("progressionAction") == "TEASE"
                    and (
                        proactive.get("proactiveTeaseDelivered")
                        or runtime.get("commercial_tease_delivered")
                    )
                    and (
                        proactive.get("proactiveTeaseSatisfied")
                        or runtime.get("commercial_tease_satisfied")
                    )
                ),
                "awaitingCustomerResponse": bool(
                    proactive.get("awaitingCustomerResponse")
                    or progression.get("awaitingCustomerResponse")
                ),
            },
            "timeWasterAttribution": {
                "commercialOpportunityExposureCount": opportunity_exposure_count,
                "proactiveTeaseDeliveredCount": proactive_tease_count,
                "proactiveRelationshipTeaseDeliveredCount": proactive_tease_count,
                "opportunityGroundedTeaseDeliveredCount": opportunity_grounded_tease_count,
                "totalCommercialTeaseExposureCount": (
                    proactive_tease_count + opportunity_grounded_tease_count
                ),
                "buildInterestExposureCount": build_exposure_count,
                "offerExposureCount": offer_exposure_count,
                "customerVisibleCommercialExposureCount": opportunity_exposure_count,
                "uniqueCommercialOpportunityCount": value_attention.get(
                    "uniqueCommercialOpportunityCount"
                ),
                "exposureAccountingMeaning": (
                    "Customer-visible exposures are not unique PurchaseIntents."
                ),
                "timeWasterOpportunityBasis": bool(
                    value_attention.get("timeWasterOpportunityBasis")
                ),
                "timeWasterEvidence": list(
                    value_attention.get("timeWasterEvidence") or ()
                ),
            },
            "commercialTeaseAccounting": {
                "commercialTeaseType": tease_type,
                "commercialTeaseDelivered": bool(
                    runtime.get("commercial_tease_delivered")
                ),
                "commercialTeaseExposureRecorded": bool(
                    runtime.get("commercial_tease_exposure_recorded")
                ),
                "proactiveRelationshipTeaseDeliveredCount": proactive_tease_count,
                "opportunityGroundedTeaseDeliveredCount": opportunity_grounded_tease_count,
                "totalCommercialTeaseExposureCount": (
                    proactive_tease_count + opportunity_grounded_tease_count
                ),
                "customerVisibleCommercialExposureCount": opportunity_exposure_count,
                "uniqueCommercialOpportunityCount": value_attention.get(
                    "uniqueCommercialOpportunityCount"
                ),
                "countingContract": (
                    "Delivery events and category projections are reported separately; "
                    "category counts must not be summed as unique opportunities."
                ),
            },
            "offeringCopySafety": {
                "offeringInternalTitle": copy_diagnostics.get(
                    "offeringInternalTitle"
                ),
                "offeringCustomerSafeCopyAvailable": bool(
                    copy_diagnostics.get("offeringCustomerSafeCopyAvailable")
                ),
                "internalOfferingMetadataExposedToGeneration": bool(
                    copy_diagnostics.get(
                        "internalOfferingMetadataExposedToGeneration"
                    )
                ),
            },
            "memoryQuality": {
                "invalidMemoryCaptureRejected": bool(
                    runtime.get("invalid_memory_capture_rejected")
                    or dict(conversational_memory.get("memoryDiagnostics") or {}).get(
                        "invalidMemoryCaptureRejected"
                    )
                ),
            },
            "customerTemperature": {
                "state": receptiveness.get("state") or "UNKNOWN",
                "strength": receptiveness.get("strength"),
                "buyerStage": decision.buyer_stage.value,
                "repeatBuyer": verified_count > 1,
                "purchaseCount": verified_count,
                "lifetimeSpendMinor": (
                    memory.get("lifetimeGrossMinor")
                    if memory.get("lifetimeGrossMinor") is not None
                    else signal.get("lifetimeSpendMinor")
                ),
            },
            "buyingSignals": {
                "commercialOpportunityExists": opportunity_exists,
                "opportunityStrength": opportunity.get("strengthScore") or receptiveness.get("strength"),
                "relationshipTrajectory": opportunity.get("relationshipTrajectory"),
                "commercialTrajectory": opportunity.get("commercialTrajectory"),
                "commercialAnchorPresent": bool(opportunity.get("commercialAnchorPresent")),
                "commercialAnchorEvidence": list(opportunity.get("commercialAnchorEvidence") or ()),
                "modelTimingRecommendation": opportunity.get("modelTimingRecommendation"),
                "modelTimingAuthority": opportunity.get("modelTimingAuthority"),
                "freshDirectIntent": fresh_direct,
                "buyingIntent": (
                    fresh_direct
                    or bool(opportunity.get("contributions", {}).get("currentIntent"))
                    or bool(classifier.get("buying_intent"))
                ),
                "closeReady": bool(opportunity.get("contributions", {}).get("escalationReady")) or bool(classifier.get("close_ready")),
                "buyerLikelihood": classifier.get("buyer_likelihood"),
                "continuationIntent": bool(receptiveness.get("continuationEligible")),
                "anotherSaleAppropriateNow": bool(receptiveness.get("anotherSaleAppropriateNow")),
                "postPurchaseContinuationEligible": bool(receptiveness.get("continuationEligible")),
                "positiveEvidence": positive,
                "opportunityEvidence": dict(opportunity.get("contributions") or {}),
            },
            "resistance": {
                "evidence": resistance,
                "pressureReduced": pressure_reduced,
                "pressureReductionReason": cls._pressure_reason(
                    objection, receptiveness, cooldown,
                ),
            },
            "purchaseCommerceState": {
                "conversationalPurchaseClaim": conversational_claim,
                "verifiedPurchase": verified_purchase,
                "verificationSource": provider_source,
                "latestVerifiedPurchaseAt": memory.get("lastPurchaseAt") or signal.get("lastPurchaseAt"),
                "latestVerifiedPurchaseEvidence": (
                    tuple(memory.get("recentVerifiedPurchaseEvidence") or ())[-1]
                    if memory.get("recentVerifiedPurchaseEvidence") else None
                ),
                "purchaseCount": verified_count,
                "lifetimeSpendMinor": memory.get("lifetimeGrossMinor") or signal.get("lifetimeSpendMinor"),
                "purchaseAcknowledgementPending": decision.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
                "purchaseAcknowledgementCompleted": bool(metadata.get("latestPurchaseAcknowledgedAt")),
                "activePurchaseIntentId": str(decision.active_purchase_intent_id) if decision.active_purchase_intent_id else None,
                "purchaseIntentStatus": decision.active_offer_status or metadata.get("latestIntentStatus"),
                "attributionResult": signal.get("attributionState") or metadata.get("latestAttributionResult"),
                "ownedOfferingIds": list(memory.get("ownedOfferingIds") or ()),
                "ownedAssetIds": list(memory.get("ownedAssetIds") or ()),
            },
            "cooldownPressure": {
                "purchaseCooldownActive": bool(cooldown.get("active")),
                "cooldownStartedAt": memory.get("lastPurchaseAt") or signal.get("lastPurchaseAt"),
                "cooldownUntil": cooldown.get("until"),
                "cooldownBlockingCurrentSale": bool(cooldown.get("blockingCurrentSale")),
                "cooldownOverride": bool(cooldown.get("override")),
                "overrideReason": cooldown.get("overrideReason"),
                "recentOfferPressure": list(opportunity.get("suppressions") or ()),
                "recoveryAttemptCount": recovery_attempts,
                "pressureReduced": pressure_reduced,
            },
            "currentOffer": {
                "activePurchaseIntentId": str(decision.active_purchase_intent_id) if decision.active_purchase_intent_id else None,
                "activeOfferingId": str(decision.active_offering_id) if decision.active_offering_id else None,
                "status": decision.active_offer_status,
                "conversionState": decision.active_offer_conversion_state,
                "customerInitiatedOfferContinuation": bool(
                    active_offer_continuation.get(
                        "customerInitiatedOfferContinuation"
                    )
                ),
                "continuationIntentType": active_offer_continuation.get(
                    "continuationIntentType"
                ),
                "nudgeCooldownApplies": active_offer_continuation.get(
                    "nudgeCooldownApplies"
                ),
                "structuredOfferReused": bool(
                    active_offer_continuation.get("structuredOfferReused")
                ),
                "structuredOfferRedelivered": bool(
                    runtime.get("paidPresentationDelivered")
                    and active_offer_continuation.get(
                        "customerInitiatedOfferContinuation"
                    )
                ),
                "purchaseIntentReused": bool(
                    active_offer_continuation.get("purchaseIntentReused")
                ),
                "relationshipDiscoverySuppressed": bool(
                    active_offer_continuation.get(
                        "relationshipDiscoverySuppressed"
                    )
                ),
                "failedOpportunityReason": (
                    dict(value_attention.get("behaviorEvidenceCounts") or {}).get(
                        "failed_nonconverted_opportunity_reason"
                    )
                ),
            },
            "objectionRecovery": {
                "type": objection.get("type") or "NONE",
                "scope": objection.get("scope") or "NONE",
                "strength": objection.get("strength") or "NONE",
                "currentOfferRejected": bool(objection.get("rejectedOfferingId")),
                "globalRejection": objection.get("scope") == "GLOBAL",
                "customerStillCommerciallyReceptive": bool(objection.get("customerStillCommerciallyReceptive", True)),
                "alternativeSelectionAllowed": bool(objection.get("alternativeSelectionAllowed")),
                "priceRecoveryRequested": bool(objection.get("priceRecoveryRequested")),
                "rejectedPriceMinor": objection.get("previousOfferPriceMinor"),
                "maximumAlternativePriceMinor": objection.get("targetMaximumAlternativePriceMinor"),
                "rejectedOfferingId": objection.get("rejectedOfferingId"),
                "contentExclusionApplied": bool(objection.get("contentExclusionApplied")),
                "replacementPreference": dict(objection.get("selectorConstraints") or {}).get("contentPreference"),
                "recoveryAttemptCount": recovery_attempts,
                "recoveryStillAllowed": bool(objection.get("alternativeSelectionAllowed")),
                "recoverySuppressionReason": (
                    "RECOVERY_LIMIT_REACHED"
                    if recovery_attempts >= 1 and not objection.get("alternativeSelectionAllowed")
                    else None
                ),
                "authorized": bool(recovery.get("authorized")),
                "attemptCount": int(recovery.get("attemptCount") or recovery_attempts),
                "budgetRemaining": recovery.get("budgetRemaining"),
                "strategy": recovery.get("strategy") or objection.get("recoveryStrategy", "NONE"),
                "negativeContactAuthorized": bool(recovery.get(
                    "negativeContactAuthorized", objection.get("negativeContactAuthorized")
                )),
                "negativeContactUsed": bool(recovery.get("negativeContactUsed")),
                "valueDefenseUsed": bool(recovery.get("valueDefenseUsed")),
                "originalOfferPreserved": bool(recovery.get(
                    "originalOfferPreserved", objection.get("currentOfferAuthoritative")
                )),
                "originalPrice": recovery.get(
                    "originalPrice", objection.get("previousOfferPriceMinor")
                ),
                "budgetConstraintDetected": bool(recovery.get(
                    "budgetConstraintDetected", objection.get("budgetConstraintDetected")
                )),
                "budgetConstraintAmount": recovery.get(
                    "budgetConstraintAmount", objection.get("budgetConstraintAmount")
                ),
                "alternativeAuthorized": bool(recovery.get(
                    "alternativeAuthorized", objection.get("alternativeSelectionAllowed")
                )),
                "alternativeSelected": bool(recovery.get("alternativeSelected")),
                "alternativePrice": recovery.get("alternativePrice"),
                "noDynamicDiscount": True,
                "falseScarcityAllowed": False,
                "reason": (
                    recovery.get("reason")
                    or list(objection.get("evidence") or ())
                ),
            },
            "inventorySelection": {
                "selectorInvoked": bool(selector),
                "selectorInvocationReason": metadata.get(
                    "selectorInvocationReason",
                    "SELECTOR_INVOKED" if selector else "NOT_REACHED",
                ),
                "strategy": selector.get("strategy"),
                "requestedInventoryType": runtime.get("requested_media_type"),
                "requestedThemes": list(runtime.get("requested_themes") or ()),
                "candidateCount": selector.get("candidateCount"),
                "eligibleCount": selector.get("eligibleCount"),
                "selectedOfferingId": str(decision.recommended_offering_id) if decision.recommended_offering_id else None,
                "selectedOfferingType": dict(decision.recommended_product_context or {}).get("offeringType"),
                "selectedPriceMinor": decision.recommended_offering_price_minor,
                "classification": classification,
                "selectedBecause": selected_trace.get("reason") or selector.get("recommendationSummary"),
                "rankingEvidence": selected_trace.get("components") or [],
                "excludedCandidateReasons": list(selector.get("exclusionReasons") or ()),
                "rejectedCandidateCountsByReason": dict(
                    selector.get("rejectedCandidateCountsByReason") or {}
                ),
                "candidateEvaluations": list(
                    selector.get("candidateEvaluations") or ()
                ),
                "recoveryConstraints": dict(selector.get("recoveryConstraints") or {}),
                "activeSessionAuthority": bool(dict(
                    intelligence.get("salesSessionContext") or {}
                ).get("salesSessionId")),
            },
            "activeSession": {
                "active": bool(session_context.get("salesSessionId")),
                "sessionId": session_context.get("salesSessionId"),
                "state": session_context.get("state"),
                "currentUnlock": session_context.get("currentUnlock"),
                "nextUnlock": session_context.get("nextUnlock"),
                "authority": (
                    "SALES_SESSION" if session_context.get("salesSessionId")
                    else "NONE"
                ),
                "genericSelectorOverride": False,
            },
            "policyGate": {
                "controllingGate": controlling_gate,
                "opportunityBeforePolicyGate": opportunity_exists,
                "finalActionAfterPolicyGate": decision.decision.value,
                "suppressionOccurred": bool(suppression_reason),
                "suppressionReason": suppression_reason,
                "rulePriority": metadata.get("rulePriority"),
            },
            "finalSalesDecision": {
                "decision": decision.decision.value,
                "reasonCode": decision.reason_code.value,
                "reasonSummary": decision.reason_summary,
                "progressionBefore": transition.get("priorPhase"),
                "progressionAfter": transition.get("nextPhase") or progression.get("phase"),
                "selectedOfferingId": str(decision.recommended_offering_id) if decision.recommended_offering_id else None,
                "offerAuthorized": offer_authorized,
                "commercePresentationAuthorized": presentation_authorized,
                "acknowledgementAction": decision.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
                "sessionAction": intelligence.get("continuationGuidance"),
                "selectionClassification": classification,
                "anotherSaleAppropriateNow": bool(receptiveness.get("anotherSaleAppropriateNow")),
                "rationale": decision.reason_summary,
            },
            "commercialStrategyAuthority": strategy_authority or {
                "owner": "CustomerSalesBrainService",
                "finalizedBeforeGeneration": True,
                "aiRole": "WORDING_AND_NON_AUTHORITATIVE_OBSERVATION",
                "aiAlteredFinalCommercialStrategy": False,
            },
            "aiCommerceReadinessObservation": (
                ai_readiness_observation or {
                    "authority": "NON_AUTHORITATIVE_AI_OBSERVATION",
                    "status": "NOT_PROVIDED",
                    "alteredFinalCommercialStrategy": False,
                }
            ),
        }

    @staticmethod
    def _positive_evidence(receptiveness, opportunity, memory, intelligence):
        values = list(receptiveness.get("positiveEvidence") or ())
        values.extend(str(key) for key, value in dict(
            opportunity.get("contributions") or {}
        ).items() if value)
        if memory.get("verifiedPurchaseCount"):
            values.append("VERIFIED_PURCHASE_HISTORY")
        affinity = dict(memory.get("affinity") or {})
        if affinity.get("offeringTypes") or affinity.get("tags"):
            values.append("RELEVANT_COMMERCE_AFFINITY")
        if dict(intelligence.get("salesSessionContext") or {}).get("salesSessionId"):
            values.append("ACTIVE_SESSION_MOMENTUM")
        return list(dict.fromkeys(values))

    @staticmethod
    def _resistance_evidence(receptiveness, objection):
        values = list(receptiveness.get("resistanceEvidence") or ())
        if objection.get("type") and objection.get("type") != "NONE":
            values.append(str(objection["type"]))
        values.extend(str(item) for item in objection.get("evidence") or ())
        return list(dict.fromkeys(values))

    @classmethod
    def _controlling_gate(cls, decision, *, objection, cooldown, selector, runtime):
        reason = decision.reason_code
        if reason is CustomerSalesReasonCode.CUSTOMER_INTERACTION_SAFETY_BLOCKED:
            return "SAFETY"
        if decision.decision is CustomerSalesDecisionType.PAYMENT_PENDING:
            return "PAYMENT_PENDING"
        if decision.decision is CustomerSalesDecisionType.MANUAL_REVIEW:
            return "MANUAL_REVIEW"
        if decision.decision is CustomerSalesDecisionType.CONGRATULATE_PURCHASE:
            return "PURCHASE_ACKNOWLEDGEMENT"
        if objection.get("type") == "PAYMENT_TECHNICAL":
            return "PAYMENT_TECHNICAL"
        if objection.get("type") == "TRUST_OR_SUPPORT":
            return "TRUST_OR_SUPPORT"
        if objection.get("scope") == "GLOBAL":
            return "GLOBAL_BACK_OFF"
        if int(objection.get("recoveryAttemptCount") or 0) >= 1 and not objection.get("alternativeSelectionAllowed"):
            return "RECOVERY_LIMIT"
        if cooldown.get("blockingCurrentSale"):
            return "PURCHASE_COOLDOWN"
        if decision.active_purchase_intent_id:
            return "ACTIVE_PURCHASE_INTENT"
        intelligence = dict(dict(decision.decision_metadata or {}).get(
            "commercialIntelligence"
        ) or {})
        if (reason is CustomerSalesReasonCode.ACTIVE_SESSION_PRECEDENCE
                or dict(intelligence.get("salesSessionContext") or {}).get(
                    "salesSessionId"
                )):
            return "SESSION_AUTHORITY"
        if decision.recommended_offering_id is None and selector:
            return "NO_ELIGIBLE_INVENTORY"
        if runtime.get("authoritative_selection_missing") or runtime.get("paid_presentation_block_reason"):
            return "FULFILLMENT"
        if reason in {CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
                      CustomerSalesReasonCode.ADAPTIVE_DIRECT_INTENT_BYPASS}:
            return "DIRECT_INTENT"
        if decision.decision in cls.PRESENTATION_ACTIONS:
            return "COMMERCIAL_RECEPTIVENESS"
        return "NONE"

    @staticmethod
    def _suppression_reason(gate, opportunity, presentation, decision):
        if not opportunity or presentation:
            return None
        if gate != "NONE":
            return gate
        if not decision.sell_allowed:
            return decision.reason_code.value
        return None

    @staticmethod
    def _pressure_reason(objection, receptiveness, cooldown):
        if cooldown.get("blockingCurrentSale"):
            return "PURCHASE_COOLDOWN"
        if objection.get("type") and objection.get("type") != "NONE":
            return objection.get("type")
        if receptiveness.get("state") in {"COOLING", "BACK_OFF"}:
            return receptiveness.get("reason")
        return None

    @staticmethod
    def _selection_classification(decision, next_best, objection, purchase_count):
        if next_best.get("classification"):
            return next_best["classification"]
        if decision.decision is CustomerSalesDecisionType.UPSELL:
            return "UPSELL"
        if decision.decision is CustomerSalesDecisionType.CROSS_SELL:
            return "CROSS_SELL"
        if decision.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER:
            return ("LOWER_PRICE_RECOVERY" if objection.get("priceRecoveryRequested")
                    else "ALTERNATIVE")
        if decision.recommended_offering_id:
            return "CONTINUATION" if purchase_count else "FIRST_OFFER"
        return "NONE"

    @staticmethod
    def _not_evaluated():
        return {
            "schemaVersion": "sales_brain_full_analysis_v1",
            "status": "NOT_EVALUATED",
        }

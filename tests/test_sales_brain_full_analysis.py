from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.services.sales_brain_full_analysis_service import (
    SalesBrainFullAnalysisService,
)


NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def _confirmed_session_teaser_inputs():
    payload = {"metadata": {
        "teaser_domain": "SESSION_FREE_TEASER",
        "free_teaser_delivery": {
            "provisional_session_id": "provisional-1",
            "photoshoot_session_id": "foundation-1",
            "asset_id": 41,
            "position": 1,
            "sales_role": "FREE_TEASER",
        },
    }}
    provisional = SimpleNamespace(
        provisional_session_id="provisional-1",
        photoshoot_reference="foundation-1",
        progression_stage="PROGRESSION",
        current_position=2,
        commercial_context={"freeTeaserDelivery": {
            "assetId": 41, "providerDeliveryId": "provider-message-1",
        }},
    )
    return payload, provisional


def test_full_analysis_reconciles_exact_confirmed_session_teaser():
    payload, provisional = _confirmed_session_teaser_inputs()
    result = SalesBrainFullAnalysisService.reconcile_confirmed_session_free_teaser(
        {"commercialTeaseAccounting": {
            "commercialTeaseType": "FREE_TEASER_ASSET",
            "commercialTeaseDelivered": False,
            "commercialTeaseExposureRecorded": False,
        }},
        delivery_payload=payload,
        delivery_operation_id="operation-1",
        delivery_state="CONFIRMED",
        customer_binding_confirmed=True,
        provisional_session=provisional,
    )
    accounting = result["commercialTeaseAccounting"]
    assert accounting["commercialTeaseAuthorized"] is True
    assert accounting["commercialTeaseDelivered"] is True
    assert accounting["commercialTeaseExposureRecorded"] is True
    assert accounting["deliveryOperationId"] == "operation-1"
    assert accounting["deliveryState"] == "CONFIRMED"
    assert accounting["teaserDomain"] == "SESSION_FREE_TEASER"
    assert accounting["assetId"] == 41
    assert accounting["foundation"] == "foundation-1"
    assert accounting["position"] == 1
    assert accounting["nextPosition"] == 2


def test_full_analysis_does_not_reconcile_unconfirmed_or_wrongly_bound_teaser():
    payload, provisional = _confirmed_session_teaser_inputs()
    original = {"commercialTeaseAccounting": {
        "commercialTeaseDelivered": False,
        "commercialTeaseExposureRecorded": False,
    }}
    controls = (
        {"delivery_state": "FAILED"},
        {"customer_binding_confirmed": False},
        {"delivery_operation_id": None},
    )
    for override in controls:
        kwargs = {
            "delivery_payload": payload,
            "delivery_operation_id": "operation-1",
            "delivery_state": "CONFIRMED",
            "customer_binding_confirmed": True,
            "provisional_session": provisional,
            **override,
        }
        result = SalesBrainFullAnalysisService.reconcile_confirmed_session_free_teaser(
            original, **kwargs,
        )
        assert result["commercialTeaseAccounting"]["commercialTeaseDelivered"] is False
    payload["metadata"]["free_teaser_delivery"]["asset_id"] = 99
    mismatched = SalesBrainFullAnalysisService.reconcile_confirmed_session_free_teaser(
        original, delivery_payload=payload, delivery_operation_id="operation-1",
        delivery_state="CONFIRMED", customer_binding_confirmed=True,
        provisional_session=provisional,
    )
    assert mismatched["commercialTeaseAccounting"]["commercialTeaseDelivered"] is False


def test_full_analysis_rejects_ordinary_and_engagement_teaser_confirmations():
    payload, provisional = _confirmed_session_teaser_inputs()
    controls = ({}, {"metadata": {
        "teaser_domain": "GENERAL_ENGAGEMENT_TEASER",
        "free_teaser_delivery": payload["metadata"]["free_teaser_delivery"],
    }})
    for candidate in controls:
        result = SalesBrainFullAnalysisService.reconcile_confirmed_session_free_teaser(
            {"commercialTeaseAccounting": {"commercialTeaseDelivered": False}},
            delivery_payload=candidate,
            delivery_operation_id="operation-1", delivery_state="CONFIRMED",
            customer_binding_confirmed=True, provisional_session=provisional,
        )
        assert result["commercialTeaseAccounting"]["commercialTeaseDelivered"] is False


def test_active_session_context_is_distinct_from_null_session_action():
    item = decision()
    metadata = dict(item.decision_metadata)
    metadata["activeSessionContext"] = {
        "available": True,
        "salesSessionId": "session-c19",
        "foundationType": "PHOTOSHOOT",
        "foundationReference": "certification-C19",
        "state": "CONTINUING",
        "progressionStage": "PROGRESSION",
        "currentConsumedPosition": 1,
        "nextEligiblePosition": 2,
        "orderedAssets": [{
            "position": 1, "assetId": 2705, "owned": True,
        }, {
            "position": 2, "assetId": 2706, "owned": False,
            "priceMinor": 900, "currency": "USD",
        }],
    }
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
        next_sales_action=None,
    )

    result = SalesBrainFullAnalysisService.project(item)

    assert result["activeSessionContext"]["available"] is True
    assert result["activeSessionContext"]["currentConsumedPosition"] == 1
    assert result["activeSessionContext"]["nextEligiblePosition"] == 2
    assert result["finalSalesDecision"]["sessionAction"] is None


def test_active_session_candidate_is_distinct_from_presented_offering():
    candidate_id = str(uuid4())
    item = decision()
    metadata = dict(item.decision_metadata)
    metadata["sessionEscalation"] = {
        "sessionCandidate": False,
        "sessionCandidateReason": (
            "EXISTING_ACTIVE_SESSION_NOT_SESSION_START_CANDIDATE"
        ),
        "canonicalSessionCandidate": True,
        "canonicalSessionCandidateOfferingId": candidate_id,
        "canonicalSessionCandidateReason": (
            "ACTIVE_SESSION_ORDERED_CANDIDATE_SELECTED"
        ),
        "sessionCompatibleInventoryAvailable": True,
    }
    metadata["offeringSelector"] = {
        "strategy": "SESSION_SELLING",
        "selectedOfferingId": candidate_id,
        "candidateCount": 2,
        "eligibleCount": 2,
    }
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
        recommended_offering_id=None,
    )

    result = SalesBrainFullAnalysisService.project(item)

    assert result["canonicalSessionCandidate"] is True
    assert result["canonicalSessionCandidateOfferingId"] == candidate_id
    assert result["inventorySelection"][
        "canonicalCandidateOfferingId"
    ] == candidate_id
    assert result["inventorySelection"]["selectedOfferingId"] is None
    assert result["inventorySelection"]["presentedOfferingId"] is None
    assert result["finalSalesDecision"]["commercePresentationAuthorized"] is False


def test_incomplete_active_session_context_is_truthfully_unavailable():
    item = decision()
    metadata = dict(item.decision_metadata)
    metadata["activeSessionContext"] = {
        "available": False,
        "completeness": "POSITIONAL_CONTEXT_UNAVAILABLE",
        "runtimeStatus": "UNAVAILABLE",
        "unavailableReason": "PhotoshootSessionRuntimeUnavailable",
        "salesSessionId": "session-c19",
        "foundationReference": "certification-C19",
        "orderedAssets": [],
        "ownedPositions": [],
        "currentConsumedPosition": None,
        "nextEligiblePosition": None,
    }
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
        next_sales_action=None,
    )

    result = SalesBrainFullAnalysisService.project(item)

    assert result["activeSessionContext"]["available"] is False
    assert result["activeSessionContext"]["completeness"] == (
        "POSITIONAL_CONTEXT_UNAVAILABLE"
    )
    assert result["finalSalesDecision"]["sessionAction"] is None


def test_full_analysis_projects_commercial_question_authorization_truthfully():
    result = SalesBrainFullAnalysisService.project(
        decision(), runtime_diagnostics={
            "conversationStyle": {
                "questionAsked": True,
                "questionReason": "PROTECTED_TRANSACTIONAL_QUESTION",
                "commercialDiscoveryAuthorized": False,
            },
        },
    )
    assert result["relationshipDiscovery"]["commercialDiscoveryAuthorized"] is False
    assert result["relationshipDiscovery"]["questionReason"] == (
        "PROTECTED_TRANSACTIONAL_QUESTION"
    )


def test_full_analysis_exposes_operational_buyer_relationship_contract():
    item = decision(purchase_count=1)
    metadata = dict(item.decision_metadata)
    metadata.update({
        "customerValueAttention": {
            "authority": "COMMERCE_BACKED_AUTHORITATIVE_VALUE",
            "buyerStatus": "VERIFIED_BUYER",
            "buyerStage": "FIRST_TIME_BUYER",
            "valueTier": "BUYER",
            "retentionLifecycle": "ACTIVE_BUYER",
            "relationshipInvestment": "WARM",
            "memoryPriority": "ELEVATED",
            "buyerProtectionApplied": True,
            "salesPressure": "LOW",
            "offerCadence": "POST_PURCHASE_CAREFUL",
            "relationshipDiscovery": {"allowed": True},
        },
        "purchaseCooldown": {"active": True},
    })
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
    )
    result = SalesBrainFullAnalysisService.project(item, runtime_diagnostics={
        "conversational_memory": {
            "memoryPriorityOperational": True,
            "retrievedKeys": ["charlie", "hiking"],
            "operationalMemoryPolicy": {
                "policy": "RELEVANCE_PRESERVING_CANDIDATE_DEPTH",
                "retrievalCandidateLimit": 8,
            },
            "generationCompliance": {"memoriesUsed": ["hiking"]},
        },
    })
    retention = result["buyerRetention"]
    assert retention["memoryPriorityOperational"] is True
    assert retention["operationalMemoryPolicy"]["retrievalCandidateLimit"] == 8
    assert retention["buyerProtection"] is True
    assert retention["buyerReactiveConversationAllowed"] is True
    assert retention["commercialCooldownActive"] is True
    assert retention["relationshipCooldownActive"] is False
    assert retention["memoryCandidatesRetrieved"] == ["charlie", "hiking"]
    assert retention["memoryCandidatesUsed"] == ["hiking"]


def test_full_analysis_exposes_intimacy_and_provider_fallback_truth():
    result = SalesBrainFullAnalysisService.project(
        decision(purchase_count=3),
        runtime_diagnostics={
            "intimacy_overrides": {
                "intimacy_entitlement": "PREMIUM",
                "intimacy_entitlement_reason": "CANONICAL_HIGH_VALUE_BUYER",
                "intimacy_investment": "STRONG_PREMIUM_INTIMACY",
                "intimacy_investment_inputs": {"purchaseCount": 3},
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
                "canonical_buyer_authority_used": True,
                "legacy_buyer_memory_authority_used": False,
            },
            "provider_preview": {
                "explicit_requested": True,
                "selected_provider": "GROK",
                "responseProvider": "OPENAI",
                "reason": "premium explicit route",
                "grok_eligible": True,
                "grokAttempted": True,
                "grokSucceeded": False,
                "providerFallbackAttempted": True,
                "providerFallbackProvider": "OPENAI",
                "providerFallbackOutcome": "SUCCEEDED",
            },
        },
    )
    assert result["explicitConversationDetected"] is True
    assert result["intimacyEntitlement"] == "PREMIUM"
    assert result["canonicalBuyerAuthorityUsed"] is True
    assert result["legacyBuyerMemoryAuthorityUsed"] is False
    assert result["responseProvider"] == "OPENAI"
    assert result["grokEligible"] is True
    assert result["grokAttempted"] is True
    assert result["grokSucceeded"] is False
    assert result["providerFallbackOutcome"] == "SUCCEEDED"


def test_full_analysis_recovers_effective_intimacy_permissions_from_provider_preview():
    result = SalesBrainFullAnalysisService.project(
        decision(purchase_count=3),
        runtime_diagnostics={
            "provider_preview": {
                "premium_sexting_allowed": True,
                "explicit_allowed": True,
                "legacy_premium_sexting_allowed": False,
                "legacy_explicit_allowed": False,
                "legacy_permission_flags_authoritative": False,
            },
        },
    )

    assert result["premiumSextingAllowed"] is True
    assert result["explicitAllowed"] is True
    assert result["effectivePremiumSextingAllowed"] is True
    assert result["effectiveExplicitAllowed"] is True
    assert result["legacyPremiumSextingAllowed"] is False
    assert result["legacyExplicitAllowed"] is False
    assert result["legacyPermissionFlagsAuthoritative"] is False


def test_full_analysis_exposes_canonical_sexual_and_tease_delivery_truth():
    item = decision(selected=True)
    metadata = dict(item.decision_metadata)
    metadata.update({
        "sustainedSexualReceptiveness": {
            "value": True,
            "authority": "CUSTOMER_SALES_BRAIN_CANONICAL_BEHAVIOR_EVIDENCE",
            "sexualEngagementDetected": True,
        },
        "teaseType": "OPPORTUNITY_GROUNDED",
    })
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
    )
    result = SalesBrainFullAnalysisService.project(item, runtime_diagnostics={
        "tease_type": "OPPORTUNITY_GROUNDED",
        "commercial_tease_authorized": True,
        "commercial_tease_wording_satisfied": True,
        "commercial_tease_delivered": False,
        "commercial_tease_exposure_recorded": False,
        "progression_finalized_after_delivery": False,
        "conversationStyle": {
            "sexualResponseExpected": True,
            "sexualResponseSatisfied": True,
            "repeatedResponseDetected": False,
        },
    })
    projection = result["sexualCommercialProgression"]
    assert projection["sustainedSexualReceptiveness"] is True
    assert projection["teaseType"] == "OPPORTUNITY_GROUNDED"
    assert projection["commercialTeaseAuthorized"] is True
    assert projection["commercialTeaseDelivered"] is False
    assert projection["progressionFinalizedAfterDelivery"] is False
    assert projection["adaptiveSwitchEligible"] is False
    assert projection["adaptiveSwitchReason"] == (
        "AWAITING_CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_EXPOSURE"
    )

    confirmed = SalesBrainFullAnalysisService.project(item, runtime_diagnostics={
        "commercial_tease_delivered": True,
        "commercial_tease_exposure_recorded": True,
        "progression_finalized_after_delivery": True,
    })["sexualCommercialProgression"]
    assert confirmed["adaptiveSwitchEligible"] is True
    assert confirmed["adaptiveSwitchReason"] == (
        "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE"
    )


def test_full_analysis_projects_active_window_and_deferred_continuation():
    item = decision(purchase_count=1)
    metadata = dict(item.decision_metadata)
    metadata.update({
        "activeBuyingWindow": {
            "active": True,
            "reason": "ACKNOWLEDGEMENT_FIRST_CONTINUATION_DEFERRED",
            "source": "PRODUCTION_CUSTOMER_STATE",
            "currentCommercialMomentum": "EXPLICIT_CUSTOMER_CONTINUATION",
            "momentumDecayReason": None,
            "scenarioInfluencedCommercialAuthority": False,
            "evidence": {
                "explicitContinuationIntent": True,
                "continuationCommercialContextPresent": True,
                "activeBuyingWindowAuthoritySatisfied": True,
            },
            "customerLedContinuation": True,
            "continuationCommercialContextPresent": True,
            "activeBuyingWindowAuthoritySatisfied": True,
            "anotherSaleAppropriateNow": False,
            "anotherSaleSuppressionReason": "ACKNOWLEDGEMENT_FIRST_CONTINUATION_DEFERRED",
        },
        "deferredContinuation": {
            "state": "PENDING_ACKNOWLEDGEMENT",
            "sourceInboundMessageId": 42,
        },
        "purchaseCooldown": {
            "active": True, "override": True,
            "overrideReason": "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN",
        },
        "sessionEscalation": {
            "sessionCandidate": True,
            "sessionCandidateReason": "REPEATED_PURCHASES_AND_ONGOING_EXPERIENCE_INTENT",
            "sessionCompatibleInventoryAvailable": True,
            "sessionEscalationDecision": "PROPOSE_SESSION",
            "sessionEscalationReason": "SESSION_CANDIDATE_AND_INVENTORY_READY",
            "continueDiscretePpvsAuthorized": False,
            "sessionProposalAuthorized": True,
            "sessionProposalDelivered": True,
            "sessionProposalPending": True,
            "sessionProposalId": "proposal:42",
            "sessionProposalSourceInbound": "inbound:42",
            "sessionProposalCreatedAt": "2026-08-27T12:00:00+00:00",
            "sessionProposalExpiresAt": "2026-08-28T12:00:00+00:00",
            "sessionProposalCustomerReaction": "NONE",
            "sessionProposalConsumed": False,
            "sessionStartAuthorityEligible": False,
            "sessionStarted": False,
            "purchaseCooldownActive": True,
            "purchaseCooldownSuppressedForProposalReaction": False,
            "activeSessionPrecedence": False,
            "sessionUnavailableFallback": False,
            "ownershipSafeOrdinaryInventoryAvailable": True,
            "recentPurchaseVelocity": {"recentPurchaseCount": 2},
            "explicitContinuationCount": 2,
            "currentContinuationIntent": "ONGOING_EXPERIENCE",
        },
    })
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
    )
    result = project(item)
    assert result["activeBuyingWindow"] is True
    assert result["activeBuyingWindowSource"] == "PRODUCTION_CUSTOMER_STATE"
    assert result["currentCommercialMomentum"] == (
        "EXPLICIT_CUSTOMER_CONTINUATION"
    )
    assert result["scenarioInfluencedCommercialAuthority"] is False
    assert result["explicitContinuationDetected"] is True
    assert result["customerLedContinuation"] is True
    assert result["continuationCommercialContextPresent"] is True
    assert result["activeBuyingWindowAuthoritySatisfied"] is True
    assert result["deferredContinuationPending"] is True
    assert result["deferredContinuationSourceInbound"] == 42
    assert result["purchaseCooldownOverridden"] is True
    assert result["sessionCandidate"] is True
    assert result["sessionEscalationDecision"] == "PROPOSE_SESSION"
    assert result["sessionProposalAuthorized"] is True
    assert result["sessionProposalDelivered"] is True
    assert result["sessionProposalId"] == "proposal:42"
    assert result["sessionProposalSourceInbound"] == "inbound:42"
    assert result["sessionProposalPending"] is True
    assert result["purchaseCooldownActive"] is True
    assert result["purchaseCooldownSuppressedForProposalReaction"] is False
    assert result["currentContinuationIntent"] == "ONGOING_EXPERIENCE"


def decision(*, action=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
             reason=CustomerSalesReasonCode.CONVERSATION_ONLY,
             state="COLD", strength=0, positive=(), resistance=(),
             direct=False, continuation=False, another=False,
             purchase_count=0, spend=0, objection=None, cooldown=None,
             selector=None, opportunity=None, latest_status=None,
             active_intent=False, selected=False, selected_type="SINGLE_IMAGE",
             price=900, intelligence=None):
    offering_id = uuid4() if selected else None
    metadata = {
        "commercialReceptiveness": {
            "state": state, "strength": strength,
            "positiveEvidence": list(positive),
            "resistanceEvidence": list(resistance),
            "freshDirectIntentDetected": direct,
            "continuationEligible": continuation,
            "anotherSaleAppropriateNow": another,
        },
        "commercialOpportunity": opportunity or {},
        "commercialObjection": objection or {"type": "NONE", "scope": "NONE"},
        "purchaseCooldown": cooldown or {},
        "continuation": {},
        "customerCommerceMemory": {
            "verifiedPurchaseCount": purchase_count,
            "lifetimePurchaseCount": purchase_count,
            "lifetimeGrossMinor": spend,
            "lastPurchaseAt": NOW.isoformat() if purchase_count else None,
            "recentVerifiedPurchaseEvidence": ([{
                "sourceType": "PURCHASE_INTENT",
                "sourceRecordId": "verified-1",
                "purchasedAt": NOW.isoformat(),
                "offeringId": "offering-verified",
            }] if purchase_count else []),
            "ownedOfferingIds": (["offering-verified"] if purchase_count else []),
            "ownedAssetIds": ([42] if purchase_count else []),
            "affinity": {},
        },
        "offeringSelector": selector,
        "nextBestOffer": {},
        "commercialIntelligence": intelligence,
        "salesProgression": {"phase": action.value},
        "salesProgressionTransition": {
            "priorPhase": "CONVERSATIONAL", "nextPhase": action.value,
        },
        "latestIntentStatus": latest_status,
        "rulePriority": 9,
    }
    return CustomerSalesDecision(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_buyer_uuid=uuid4(), telegram_user_id=3,
        identity_resolved=True, decision=action, reason_code=reason,
        reason_summary=reason.value, buyer_stage=(
            CustomerBuyerStage.REPEAT_BUYER if purchase_count > 1
            else CustomerBuyerStage.FIRST_TIME_BUYER if purchase_count
            else CustomerBuyerStage.PROSPECT
        ),
        commerce_signal=MappingProxyType({
            "attributionState": "ATTRIBUTED" if purchase_count else "PENDING"
        }),
        active_purchase_intent_id=uuid4() if active_intent else None,
        active_offering_id=uuid4() if active_intent else None,
        active_offer_status=latest_status if active_intent else None,
        active_offer_conversion_state="NO_ACTIVE_OFFER",
        recommended_offering_id=offering_id,
        recommended_publication_id=uuid4() if selected else None,
        recommended_delivery_url="https://example.invalid" if selected else None,
        sell_allowed=selected, nudge_allowed=False,
        upsell_allowed=action is CustomerSalesDecisionType.UPSELL,
        cross_sell_allowed=action is CustomerSalesDecisionType.CROSS_SELL,
        congratulate_allowed=action is CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        cooldown_until=None, evaluated_at=NOW,
        decision_metadata=MappingProxyType(metadata),
        recommended_offering_title="Selected" if selected else None,
        recommended_offering_price_minor=price if selected else None,
        recommended_offering_currency="USD" if selected else None,
        recommended_product_context=MappingProxyType(
            {"offeringType": selected_type} if selected else {}
        ),
    )


def project(value, message="", authorized=False, runtime_extra=None):
    runtime = {
        "offer_authorized": authorized,
        "commerce_execution_policy": (
            "COMMERCE_PRESENTATION_ALLOWED" if authorized
            else "COMMERCE_DISABLED_FOR_TURN"
        ),
    }
    runtime.update(runtime_extra or {})
    return SalesBrainFullAnalysisService.project(
        value, customer_message=message,
        runtime_diagnostics=runtime,
    )


def test_full_analysis_projects_global_structured_price_contract():
    result = project(
        decision(action=CustomerSalesDecisionType.PRESENT_OFFER, selected=True),
        message="how much is it?", authorized=True,
        runtime_extra={
            "authoritativeOffering": "offering-1",
            "canonicalInternalPriceMinor": 2900,
            "canonicalInternalCurrency": "USD",
            "paidPresentationAuthorized": True,
            "paidPresentationDelivered": True,
            "conversationalPriceSuppressed": True,
            "numericPricePresentInAvaProse": False,
            "purchaseIntent": "intent-1",
            "ctaLinkTruth": {"required": True, "deliveryPayloadPresent": True},
            "paidPresentationPurpose": "PRICE_REQUEST_CONTINUATION",
            "sameOfferAsPreviousPresentation": True,
            "customerInitiatedOfferContinuation": True,
            "continuationIntentType": "PRICE_REQUEST",
            "recentPaidPresentationWording": ["Here you go — unlock this one."],
            "paidPresentationRepetitionRisk": {
                "risk": False, "similarity": 0.42,
            },
            "paidPresentationWordingSource": "PROVIDER_GENERATED",
            "repetitionRepairAttempted": False,
            "repetitionRepairOutcome": "NOT_NEEDED",
        },
    )
    contract = result["paidPresentationContract"]
    assert contract == {
        "priceRequestDetected": True,
        "authoritativeOffering": "offering-1",
        "canonicalInternalPriceMinor": 2900,
        "canonicalInternalCurrency": "USD",
        "paidPresentationAuthorized": True,
        "paidPresentationDelivered": True,
        "conversationalPriceSuppressed": True,
        "numericPricePresentInAvaProse": False,
        "purchaseIntent": "intent-1",
        "ctaLinkTruth": {"required": True, "deliveryPayloadPresent": True},
        "priceAuthority": "STRUCTURED_PAID_PRESENTATION",
        "paidPresentationPurpose": "PRICE_REQUEST_CONTINUATION",
        "sameOfferAsPreviousPresentation": True,
        "customerInitiatedOfferContinuation": True,
        "continuationIntentType": "PRICE_REQUEST",
        "recentPaidPresentationWording": ["Here you go — unlock this one."],
        "paidPresentationRepetitionRisk": {
            "risk": False, "similarity": 0.42,
        },
        "paidPresentationWordingSource": "PROVIDER_GENERATED",
        "repetitionRepairAttempted": False,
        "repetitionRepairOutcome": "NOT_NEEDED",
    }


def test_active_offer_reuse_diagnostics_require_committed_redelivery():
    item = decision(
        action=CustomerSalesDecisionType.NO_SALE,
        reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
    )
    metadata = dict(item.decision_metadata)
    metadata["activeOfferContinuation"] = {
        "customerInitiatedOfferContinuation": True,
        "continuationIntentType": "SEND_OR_LINK_REQUEST",
        "reuseRequested": True,
        "redeliveryAuthorized": True,
        "purchaseIntentReuseEligible": True,
        # Decision-stage intent must not become committed-behavior truth.
        "structuredOfferReused": True,
        "structuredOfferRedelivered": True,
        "purchaseIntentReused": True,
    }
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
    )

    failed = project(item, runtime_extra={"paidPresentationDelivered": False})
    current = failed["currentOffer"]
    assert current["reuseRequested"] is True
    assert current["redeliveryAuthorized"] is True
    assert current["purchaseIntentReuseEligible"] is True
    assert current["structuredOfferReused"] is False
    assert current["structuredOfferRedelivered"] is False
    assert current["purchaseIntentReused"] is False


def test_full_analysis_separates_adaptive_service_from_wording_source():
    result = project(decision(), runtime_extra={
        "adaptiveCustomerService": "AdaptiveSyntheticCustomerService",
        "adaptiveCustomerPhase": "REVEAL_INTEREST",
        "adaptiveCustomerWordingSource": "DETERMINISTIC_PHASE_SAFE_FALLBACK",
        "adaptivePhaseReason": "AVA_BUILD_INTEREST_CONFIRMED",
        "progressionBefore": "BUILD_INTEREST",
        "progressionAfter": "PRESENT_OFFER",
        "recentCustomerRepetitionRisk": False,
    })
    projection = result["sexualCommercialProgression"]
    assert projection["adaptiveCustomerService"] == "AdaptiveSyntheticCustomerService"
    assert projection["adaptiveCustomerPhase"] == "REVEAL_INTEREST"
    assert projection["adaptiveCustomerWordingSource"] == (
        "DETERMINISTIC_PHASE_SAFE_FALLBACK"
    )
    assert projection["adaptivePhaseReason"] == "AVA_BUILD_INTEREST_CONFIRMED"
    assert projection["progressionBefore"] == "BUILD_INTEREST"
    assert projection["progressionAfter"] == "PRESENT_OFFER"
    assert projection["recentCustomerRepetitionRisk"] is False


def selector(*, exclusions=(), selected=True):
    return {
        "strategy": "LIBRARY_SELLING", "candidateCount": 3,
        "eligibleCount": 1 if selected else 0,
        "exclusionReasons": list(exclusions),
        "recommendationTrace": ([{
            "selected": True, "reason": "semantic request match",
            "components": [{"key": "semantic_match"}],
        }] if selected else []),
    }


def test_cold_prospect_has_no_opportunity_or_offer():
    summary = project(decision())
    assert summary["customerTemperature"]["state"] == "COLD"
    assert summary["buyingSignals"]["commercialOpportunityExists"] is False
    assert summary["finalSalesDecision"]["offerAuthorized"] is False


def test_proactive_tease_satisfaction_requires_actual_delivery():
    value = decision(action=CustomerSalesDecisionType.TEASE)
    metadata = dict(value.decision_metadata)
    metadata["proactiveProgression"] = {
        "proactiveProgressionAuthorized": True,
        "proactiveTeaseExpected": True,
        "proactiveTeaseSatisfied": True,
        "proactiveTeaseDelivered": False,
        "progressionAction": "TEASE",
    }
    value = CustomerSalesDecision(**{
        **value.__dict__, "decision_metadata": MappingProxyType(metadata),
    })
    summary = project(value, runtime_extra={
        "conversationStyle": {
            "proactiveTeaseExpected": True,
            "proactiveTeaseSatisfied": True,
        },
        "proactive_tease_delivered": False,
    })
    proactive = summary["proactiveProgression"]
    assert proactive["proactiveTeaseDelivered"] is False
    assert proactive["proactiveTeaseSatisfied"] is False
    assert proactive["commercialTeaseAuthorized"] is True
    assert proactive["commercialTeaseDelivered"] is False
    assert proactive["commercialTeaseSatisfied"] is False


def test_social_flirtation_does_not_masquerade_as_commercial_tease():
    summary = project(decision(), runtime_extra={
        "conversationStyle": {
            "socialFlirtationDetected": True,
            "proactiveTeaseExpected": False,
            "proactiveTeaseSatisfied": True,
        },
        "social_flirtation_present": True,
        "commercial_tease_delivered": False,
    })
    proactive = summary["proactiveProgression"]
    assert proactive["socialFlirtationPresent"] is True
    assert proactive["commercialTeaseAuthorized"] is False
    assert proactive["commercialTeaseDelivered"] is False
    assert proactive["commercialTeaseSatisfied"] is False


def test_full_analysis_separates_retrieved_memory_from_final_usage():
    summary = project(decision(), runtime_extra={
        "conversationStyle": {
            "memoryCallbackUsed": False,
            "memoriesUsed": [],
        },
        "conversational_memory": {
            "available": True,
            "retrievedKeys": ["social_style", "outdoors", "hiking", "camping"],
            "memoryCandidates": [{"key": "social_style", "selected": True}],
            "continuityGuidance": {
                "strongestMemory": {"key": "social_style"},
                "relevanceReasons": ["EXPLICIT_MEMORY_REFERENCE"],
            },
            "generationCompliance": {
                "memoriesAvailable": True,
                "memoriesRetrieved": [
                    "social_style", "outdoors", "hiking", "camping",
                ],
                "memoriesRelevant": ["social_style"],
                "memoriesUsed": [],
                "callbackExpected": True,
                "callbackRequired": True,
                "callbackActuallyUsed": False,
                "callbackCompliance": "REQUIRED_NOT_USED",
                "omissionReason": "FINAL_RESPONSE_OMITTED_REQUIRED_CALLBACK",
            },
        },
    })

    callback = summary["memoryCallback"]
    assert callback["memoriesAvailable"] is True
    assert callback["memoriesRetrieved"] == [
        "social_style", "outdoors", "hiking", "camping",
    ]
    assert callback["memoriesRelevant"] == ["social_style"]
    assert callback["memoryCallbackUsed"] is False
    assert callback["memoriesUsed"] == []
    assert callback["memoryCallbackNatural"] is None
    assert callback["memoryCallbackRequired"] is True
    assert callback["memoryCallbackCompliance"] == "REQUIRED_NOT_USED"


def test_full_analysis_names_canonical_and_legacy_authorities():
    summary = project(decision(), runtime_extra={
        "customerContactPolicy": {"decision": "ALLOW"},
    })
    authority = summary["authorityArchitecture"]
    assert authority["commercialStrategy"] == {
        "owner": "CustomerSalesBrainService",
        "legacyDecisionEngineCommerce": "DISABLED_UNREACHABLE",
        "gptRole": "WORDING_ONLY",
    }
    assert authority["buyerValueAndAttention"]["owner"] == (
        "CustomerValueAttentionService"
    )
    assert authority["buyerValueAndAttention"]["legacyBuyerWhaleFlags"] == (
        "ADVISORY_ONLY"
    )
    assert authority["contactTiming"]["owner"] == (
        "CustomerContactAuthorityService"
    )
    assert authority["salesSession"]["scope"] == (
        "SESSION_SPECIFIC_COMMERCIAL_ENVELOPE"
    )
    assert authority["memory"]["legacyUserMemory"] == (
        "ADVISORY_COMPATIBILITY_ONLY"
    )


def test_attention_policy_and_actual_enforcement_are_separate():
    summary = project(decision(), runtime_extra={
        "customer_value_attention": {
            "presentedOpportunityCount": 2,
            "failedNonconvertedOpportunityCount": 2,
            "convertedOpportunityCount": 0,
            "activeUnresolvedOpportunity": False,
            "purchaseCount": 0,
            "lastPurchaseAt": None,
            "purchaseRecencyDays": None,
            "buyerStatus": "NONBUYER",
            "buyerStage": "PROSPECT",
            "valueTier": "LOW_VALUE_PROSPECT",
            "retentionLifecycle": "NOT_A_BUYER",
            "retentionPriority": "NONE",
            "reactivationState": "NOT_APPLICABLE",
            "relationshipInvestment": "STANDARD",
            "memoryPriority": "STANDARD",
            "salesPressure": "NORMAL",
            "offerCadence": "PROSPECT",
            "authority": "COMMERCE_BACKED_AUTHORITATIVE_VALUE",
            "timeWasterRisk": "HIGH",
            "timeWasterEvidence": ["MULTIPLE_OFFERS_NO_CONVERSION"],
            "attentionTier": "LOW",
            "effortMode": "MINIMAL",
            "taperApplied": True,
            "taperReason": "PERSISTENT_NONCONVERSION_REDUCED_INVESTMENT",
            "lowCostNurtureEligible": True,
            "lowCostNurtureActive": True,
            "lowCostNurtureReason": "REPEATED_PROVEN_NONCONVERSION",
            "nurtureResponseBudget": 1,
            "nurtureResponsesUsed": 1,
            "nurtureNextOptionalResponseAt": "2026-09-02T18:00:00+00:00",
            "optionalOrdinaryReplySuppressed": True,
            "suppressionReason": "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED",
            "freshCommercialIntentDetected": False,
            "nurtureBypassedForCommercialIntent": False,
            "nurtureExitedAfterPurchase": False,
        },
        "conversationStyle": {
            "attentionPolicyEffortMode": "MINIMAL",
            "attentionComplianceRequired": True,
            "attentionComplianceSatisfied": True,
            "attentionComplianceStrategyProtected": False,
            "attentionComplianceInitialViolations": [
                "MINIMAL_UNNECESSARY_OPEN_ENDED_HOOK"
            ],
            "attentionComplianceViolations": [],
            "attentionComplianceRewriteAttempted": True,
            "attentionComplianceRewriteOutcome": "SUCCEEDED",
        },
    })
    assert summary["attentionEconomics"]["presentedOpportunities"] == 2
    assert summary["attentionEconomics"][
        "failedNonconvertedOpportunities"
    ] == 2
    assert summary["attentionEconomics"]["lowCostNurtureActive"] is True
    assert summary["attentionEconomics"]["nurtureResponseBudget"] == 1
    assert summary["attentionEconomics"]["nurtureResponsesUsed"] == 1
    assert summary["attentionEconomics"][
        "optionalOrdinaryReplySuppressed"
    ] is True
    assert summary["attentionBehaviorEnforcement"] == {
        "required": True,
        "satisfied": True,
        "strategyProtected": False,
        "violations": [],
        "initialViolations": ["MINIMAL_UNNECESSARY_OPEN_ENDED_HOOK"],
        "rewriteAttempted": True,
        "rewriteOutcome": "SUCCEEDED",
        "actualEffortMode": "MINIMAL",
    }
    assert summary["buyerRetention"]["authoritativeSource"] == (
        "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
    )
    assert summary["buyerRetention"]["buyerStage"] == "PROSPECT"


def test_warm_prospect_exposes_evidence_without_false_direct_intent():
    summary = project(decision(state="WARM", strength=45,
                               positive=("SUSTAINED_ENGAGEMENT",)))
    assert summary["buyingSignals"]["commercialOpportunityExists"] is False
    assert summary["buyingSignals"]["freshDirectIntent"] is False
    assert "SUSTAINED_ENGAGEMENT" in summary["buyingSignals"]["positiveEvidence"]


def test_direct_intent_is_hot_selected_and_authorized():
    summary = project(decision(
        action=CustomerSalesDecisionType.PRESENT_OFFER,
        reason=CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
        state="HOT", strength=90, direct=True, another=True,
        selector=selector(), selected=True,
    ), authorized=True)
    assert summary["buyingSignals"]["freshDirectIntent"] is True
    assert summary["inventorySelection"]["selectorInvoked"] is True
    assert summary["finalSalesDecision"]["commercePresentationAuthorized"] is True


def test_provider_verified_purchase_and_acknowledgement_are_visible():
    summary = project(decision(
        action=CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        state="HOT", purchase_count=1, spend=900,
        latest_status="PURCHASED", active_intent=True,
    ))
    assert summary["purchaseCommerceState"]["verifiedPurchase"] is True
    assert summary["purchaseCommerceState"]["verificationSource"] == "PROVIDER_VERIFIED_COMMERCE_MEMORY"
    assert summary["finalSalesDecision"]["acknowledgementAction"] is True
    assert summary["purchaseCommerceState"]["purchaseOwnershipVerified"] is True


def test_provider_verified_purchase_requires_exact_ownership_evidence():
    item = decision(
        action=CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        purchase_count=2, spend=2900, latest_status="PURCHASED",
        active_intent=True,
    )
    metadata = dict(item.decision_metadata)
    memory = dict(metadata["customerCommerceMemory"])
    memory["ownedOfferingIds"] = ["unrelated-offering"]
    memory["ownedAssetIds"] = [999]
    metadata["customerCommerceMemory"] = memory
    item = __import__("dataclasses").replace(
        item, decision_metadata=MappingProxyType(metadata),
    )

    state = project(item, message="I bought it")["purchaseCommerceState"]

    assert state["providerPurchaseVerified"] is True
    assert state["purchaseOwnershipVerified"] is False


def test_false_purchase_claim_remains_non_authoritative():
    summary = project(decision(), message="I bought it")
    state = summary["purchaseCommerceState"]
    assert state["conversationalPurchaseClaim"] is True
    assert state["customerPurchaseClaimDetected"] is True
    assert state["verifiedPurchase"] is False
    assert state["providerPurchaseVerified"] is False
    assert state["purchaseOwnershipVerified"] is False
    assert state["firstPurchaseSemanticsAuthorized"] is False
    assert state["purchaseAcknowledgementAuthorized"] is False
    assert state["purchaseAcknowledgementReason"] == (
        "CUSTOMER_CLAIM_AWAITING_PROVIDER_SETTLEMENT"
    )
    assert state["ownedOfferingIds"] == []


def test_hot_continuation_shows_cooldown_override_and_novel_selection():
    summary = project(decision(
        action=CustomerSalesDecisionType.CROSS_SELL,
        state="HOT", strength=100, direct=True, continuation=True,
        another=True, purchase_count=1, spend=900,
        cooldown={"active": True, "blockingCurrentSale": False,
                  "override": True, "overrideReason": "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN"},
        selector=selector(exclusions=("OFFERING_ALREADY_PURCHASED",)),
        selected=True,
    ), authorized=True)
    assert summary["cooldownPressure"]["cooldownOverride"] is True
    assert summary["buyingSignals"]["anotherSaleAppropriateNow"] is True
    assert summary["inventorySelection"]["classification"] == "CROSS_SELL"


def test_positive_purchase_response_does_not_force_second_offer():
    summary = project(decision(
        state="HOT", strength=70, positive=("POSITIVE_POST_PURCHASE_RESPONSE",),
        purchase_count=1, cooldown={"active": True, "blockingCurrentSale": True},
    ))
    assert summary["buyingSignals"]["freshDirectIntent"] is False
    assert summary["finalSalesDecision"]["offerAuthorized"] is False


def test_cooling_purchase_blocks_second_sale():
    summary = project(decision(
        state="COOLING", strength=20, purchase_count=1,
        cooldown={"active": True, "blockingCurrentSale": True},
        reason=CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN,
    ))
    assert summary["policyGate"]["controllingGate"] == "PURCHASE_COOLDOWN"
    assert summary["buyingSignals"]["anotherSaleAppropriateNow"] is False


def test_price_recovery_projects_lower_price_constraint():
    objection = {"type": "PRICE_RESISTANCE", "scope": "CURRENT_PRODUCT",
        "strength": "MODERATE", "customerStillCommerciallyReceptive": True,
        "alternativeSelectionAllowed": True, "priceRecoveryRequested": True,
        "previousOfferPriceMinor": 1200, "targetMaximumAlternativePriceMinor": 1080,
        "rejectedOfferingId": "rejected", "recoveryAttemptCount": 0}
    summary = project(decision(
        action=CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
        reason=CustomerSalesReasonCode.PRICE_RECOVERY,
        state="HOT", objection=objection, selector=selector(), selected=True,
        price=900,
    ), authorized=True)
    assert summary["objectionRecovery"]["type"] == "PRICE_RESISTANCE"
    assert summary["objectionRecovery"]["maximumAlternativePriceMinor"] == 1080
    assert summary["inventorySelection"]["classification"] == "LOWER_PRICE_RECOVERY"


def test_content_recovery_projects_scoped_exclusion():
    objection = {"type": "CONTENT_MISMATCH", "scope": "CURRENT_PRODUCT",
        "strength": "MODERATE", "customerStillCommerciallyReceptive": True,
        "alternativeSelectionAllowed": True, "rejectedOfferingId": "rejected",
        "contentExclusionApplied": True,
        "selectorConstraints": {"contentPreference": "HOTTER"}}
    summary = project(decision(
        action=CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
        reason=CustomerSalesReasonCode.CONTENT_ALTERNATIVE,
        state="HOT", objection=objection,
        selector=selector(exclusions=("OFFERING_REJECTED_CURRENT_SEQUENCE",)),
        selected=True,
    ), authorized=True)
    assert summary["objectionRecovery"]["contentExclusionApplied"] is True
    assert summary["objectionRecovery"]["replacementPreference"] == "HOTTER"


def test_hesitation_reduces_pressure_without_alternative():
    summary = project(decision(objection={
        "type": "TEMPORARY_HESITATION", "scope": "CURRENT_PRODUCT",
        "pressureDecrease": True, "alternativeSelectionAllowed": False,
    }))
    assert summary["resistance"]["pressureReduced"] is True
    assert summary["objectionRecovery"]["alternativeSelectionAllowed"] is False


def test_historical_purchased_intent_cannot_be_current_offer_rejection():
    summary = project(decision(
        purchase_count=1, latest_status="PURCHASED", active_intent=False,
        objection={
            "type": "NONE", "scope": "NONE",
            "rejectedOfferingId": "historical-purchased-offering",
        },
    ))
    assert summary["objectionRecovery"]["currentOfferRejected"] is False


def test_presented_active_offer_with_explicit_rejection_is_current_rejection():
    summary = project(decision(
        latest_status="PRESENTED", active_intent=True,
        objection={
            "type": "GLOBAL_DECLINE", "scope": "GLOBAL",
            "rejectedOfferingId": "current-presented-offering",
        },
    ))
    assert summary["objectionRecovery"]["currentOfferRejected"] is True


def test_presented_active_offer_without_rejection_is_not_current_rejection():
    summary = project(decision(
        latest_status="PRESENTED", active_intent=True,
        objection={
            "type": "NONE", "scope": "NONE",
            "rejectedOfferingId": "current-presented-offering",
        },
    ))
    assert summary["objectionRecovery"]["currentOfferRejected"] is False


def test_global_decline_has_backoff_controlling_gate():
    summary = project(decision(
        action=CustomerSalesDecisionType.BACK_OFF,
        reason=CustomerSalesReasonCode.CUSTOMER_DECLINED,
        state="BACK_OFF", objection={"type": "GLOBAL_DECLINE", "scope": "GLOBAL"},
    ))
    assert summary["policyGate"]["controllingGate"] == "GLOBAL_BACK_OFF"
    assert summary["finalSalesDecision"]["decision"] == "BACK_OFF"


def test_payment_technical_preserves_support_gate_without_offer():
    summary = project(decision(
        reason=CustomerSalesReasonCode.PAYMENT_SUPPORT_REQUIRED,
        objection={"type": "PAYMENT_TECHNICAL", "scope": "CURRENT_PRODUCT"},
        active_intent=True, latest_status="PRESENTED",
    ))
    assert summary["policyGate"]["controllingGate"] == "PAYMENT_TECHNICAL"
    assert summary["inventorySelection"]["selectorInvoked"] is False


def test_qualified_upsell_is_visible():
    summary = project(decision(action=CustomerSalesDecisionType.UPSELL,
        state="HOT", direct=True, purchase_count=1, selector=selector(),
        selected=True, selected_type="BUNDLE", price=1500), authorized=True)
    assert summary["inventorySelection"]["classification"] == "UPSELL"


def test_qualified_cross_sell_is_visible():
    summary = project(decision(action=CustomerSalesDecisionType.CROSS_SELL,
        state="HOT", direct=True, purchase_count=1, selector=selector(),
        selected=True, selected_type="SINGLE_IMAGE", price=700), authorized=True)
    assert summary["inventorySelection"]["classification"] == "CROSS_SELL"


def test_second_failed_recovery_exposes_limit_and_suppression():
    summary = project(decision(state="BACK_OFF", objection={
        "type": "PRICE_RESISTANCE", "scope": "CURRENT_PRODUCT",
        "alternativeSelectionAllowed": False, "recoveryAttemptCount": 1,
    }))
    assert summary["objectionRecovery"]["recoverySuppressionReason"] == "RECOVERY_LIMIT_REACHED"
    assert summary["policyGate"]["controllingGate"] == "RECOVERY_LIMIT"


def test_hot_no_inventory_distinguishes_opportunity_from_gate():
    summary = project(decision(
        action=CustomerSalesDecisionType.NO_SALE,
        reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
        state="HOT", strength=90, direct=True,
        selector=selector(exclusions=("PUBLICATION_NOT_LIVE",), selected=False),
    ))
    assert summary["buyingSignals"]["commercialOpportunityExists"] is True
    assert summary["policyGate"]["controllingGate"] == "NO_ELIGIBLE_INVENTORY"
    assert summary["policyGate"]["suppressionOccurred"] is True


def test_owned_candidate_exclusion_is_visible():
    summary = project(decision(state="HOT", selector=selector(
        exclusions=("OFFERING_ALREADY_PURCHASED",), selected=False)))
    assert "OFFERING_ALREADY_PURCHASED" in summary["inventorySelection"]["excludedCandidateReasons"]


def test_active_session_authority_is_visible():
    summary = project(decision(
        state="HOT", intelligence={"salesSessionContext": {
            "salesSessionId": "session-1", "state": "ACTIVE"},
            "continuationGuidance": "Continue active Session"},
    ))
    assert summary["inventorySelection"]["activeSessionAuthority"] is True
    assert summary["policyGate"]["controllingGate"] == "SESSION_AUTHORITY"


def test_attribution_ambiguity_fails_closed_with_manual_review():
    value = decision(
        action=CustomerSalesDecisionType.MANUAL_REVIEW,
        reason=CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN,
        state="HOT", strength=90,
    )
    summary = project(value)
    assert summary["buyingSignals"]["commercialOpportunityExists"] is False
    assert summary["policyGate"]["controllingGate"] == "MANUAL_REVIEW"
    assert summary["finalSalesDecision"]["offerAuthorized"] is False


def test_full_analysis_reports_direct_bypass_copy_memory_and_exposure_clarity():
    summary = project(
        decision(
            action=CustomerSalesDecisionType.PRESENT_OFFER,
            reason=CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
            selected=True,
        ),
        authorized=True,
        runtime_extra={
            "tease_type": "OPPORTUNITY_GROUNDED",
            "customer_value_attention": {
                "commercialOpportunityExposureCount": 3,
                "proactiveTeaseDeliveredCount": 0,
                "buildInterestExposureCount": 0,
                "offerExposureCount": 2,
            },
            "offering_copy_diagnostics": {
                "offeringInternalTitle": "Certification available 3",
                "offeringCustomerSafeCopyAvailable": True,
                "internalOfferingMetadataExposedToGeneration": False,
            },
            "invalid_memory_capture_rejected": True,
        },
    )
    progression = summary["sexualCommercialProgression"]
    assert progression["realizedConversionPath"] == "DIRECT_INTENT_BYPASS"
    assert progression["directIntentBypassUsed"] is True
    counts = summary["timeWasterAttribution"]
    assert counts["opportunityGroundedTeaseDeliveredCount"] == 1
    assert counts["proactiveRelationshipTeaseDeliveredCount"] == 0
    assert counts["totalCommercialTeaseExposureCount"] == 1
    assert counts["customerVisibleCommercialExposureCount"] == 3
    accounting = summary["commercialTeaseAccounting"]
    assert accounting["commercialTeaseType"] == "OPPORTUNITY_GROUNDED"
    assert accounting["proactiveRelationshipTeaseDeliveredCount"] == 0
    assert accounting["opportunityGroundedTeaseDeliveredCount"] == 1
    assert accounting["totalCommercialTeaseExposureCount"] == 1
    assert accounting["customerVisibleCommercialExposureCount"] == 3
    assert summary["offeringCopySafety"] == {
        "offeringInternalTitle": "Certification available 3",
        "offeringCustomerSafeCopyAvailable": True,
        "internalOfferingMetadataExposedToGeneration": False,
    }
    assert summary["memoryQuality"]["invalidMemoryCaptureRejected"] is True


def test_full_analysis_projects_buyer_relationship_nurture_as_noncommercial_success():
    summary = project(decision(purchase_count=5, spend=50_000), runtime_extra={
        "customer_value_attention": {
            "buyerStatus": "VERIFIED_BUYER", "valueTier": "WHALE",
            "relationshipNurtureActive": True,
            "relationshipNurtureReason": (
                "WHALE_NO_CURRENT_ACTIONABLE_COMMERCIAL_OPPORTUNITY"
            ),
            "relationshipNurtureOutcome": "ACTIVE_RELATIONSHIP_RETENTION",
            "relationshipNurtureCommercialReentryAllowed": True,
            "lowCostNurtureActive": False,
        },
    })
    nurture = summary["relationshipNurture"]
    assert nurture["active"] is True
    assert nurture["objective"] == "BUYER_RELATIONSHIP_NURTURE"
    assert nurture["commercialOpportunityExists"] is False
    assert nurture["distinctFromLowCostNurture"] is True
    assert nurture["commercialReentryAllowed"] is True


def test_full_analysis_actionable_signal_prevents_relationship_nurture():
    summary = project(decision(
        action=CustomerSalesDecisionType.PRESENT_OFFER,
        reason=CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT,
        direct=True, selected=True,
    ), authorized=True, runtime_extra={
        "customer_value_attention": {"relationshipNurtureActive": True},
    })
    assert summary["relationshipNurture"]["active"] is False
    assert summary["buyingSignals"]["commercialOpportunityExists"] is True


def test_full_analysis_distinguishes_dormancy_reactivation_and_rewarming():
    summary = project(decision(purchase_count=1), runtime_extra={
        "customer_value_attention": {
            "buyerStatus": "VERIFIED_BUYER",
            "retentionLifecycle": "DORMANT_BUYER",
            "reactivationState": "REACTIVATED_BUYER",
            "relationshipRewarmingActive": True,
            "relationshipRewarmingObjective": "BUYER_REWARMING",
            "relationshipRewarmingReason": (
                "VERIFIED_DORMANT_BUYER_RETURNED_WITHOUT_CURRENT_COMMERCIAL_OPPORTUNITY"
            ),
            "relationshipRewarmingCommercialReentryAllowed": True,
            "currentCommercialInterest": False,
        },
    })
    rewarming = summary["relationshipRewarming"]
    assert rewarming["active"] is True
    assert rewarming["objective"] == "BUYER_REWARMING"
    assert rewarming["retentionLifecycle"] == "DORMANT_BUYER"
    assert rewarming["reactivationState"] == "REACTIVATED_BUYER"
    assert rewarming["currentCommercialInterest"] is False
    assert rewarming["commercialReentryAllowed"] is True
    assert rewarming["interpretation"] == (
        "This verified buyer has returned and Ava is rebuilding the relationship, "
        "but the customer is not currently shopping."
    )

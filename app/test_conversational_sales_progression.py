from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import UUID

import pytest

from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.active_buying_window_service import ActiveBuyingWindowService
from app.services.conversation_gateway import ConversationGateway
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.gpt_service import GPTService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.engine.decision_engine import DecisionEngine


OFFER = UUID("00000000-0000-0000-0000-000000000195")
NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)


def decision(*, selected=True, product_context=None):
    return CustomerSalesDecision(
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_buyer_uuid=None, telegram_user_id=22,
        identity_resolved=True,
        decision=(CustomerSalesDecisionType.PRESENT_OFFER if selected
                  else CustomerSalesDecisionType.NO_SALE),
        reason_code=CustomerSalesReasonCode.NO_ACTIVE_OFFER,
        reason_summary="selected", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=MappingProxyType({}), active_purchase_intent_id=None,
        active_offering_id=None, active_offer_status=None,
        active_offer_conversion_state="NO_ACTIVE_OFFER",
        recommended_offering_id=OFFER if selected else None,
        recommended_publication_id=None,
        recommended_delivery_url="https://share.fanvue.com/canonical" if selected else None,
        sell_allowed=selected, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=NOW,
        decision_metadata=MappingProxyType({}),
        recommended_offering_title="Canonical product" if selected else None,
        recommended_offering_short_description="Verified content",
        recommended_offering_price_minor=1799 if selected else None,
        recommended_offering_currency="USD" if selected else None,
        recommended_product_context=MappingProxyType(product_context or {}),
    )


def state(phase="TEASE", count=1):
    return {"phase": phase, "offeringId": str(OFFER), "teaseCount": count}


@pytest.mark.parametrize("message", (
    "send me that", "show me a photo", "I want it", "I'll take it",
    "where do I buy it?", "I want the whole set", "give me the next one",
    "show me", "okay show me", "let me see it", "send it",
    "what do I get?", "show me the private one", "give me the good stuff",
    "Okay Ava 😏 show me what you've got.",
    "Okay Ava 😏 show me what you’ve got.",
))
def test_strong_purchase_intent_bypasses_teasing(message):
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": message},
    )
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True


@pytest.mark.parametrize("message", (
    "reveal what you're teasing",
    "show me what you're teasing",
    "tell me what you're teasing",
    "tell me a little more",
    "tell me a bit more",
    "give me a little more",
    "what exactly were you teasing about",
    "what are you hinting at",
))
def test_natural_non_direct_tease_responses_advance_to_build_interest(message):
    service = ConversationalSalesProgressionService()
    features = service.transition_features(message)
    assert features["commercial_response_interest"] is True
    assert service.has_direct_purchase_intent(message) is False
    result = service.refine(
        decision(), {"latest_message": message, "sales_progression": state()},
    )
    assert result.decision is CustomerSalesDecisionType.BUILD_INTEREST


def test_curiosity_build_interest_survives_overeager_provider_readiness():
    service = ConversationalSalesProgressionService()
    message = "okay I'm curious, tell me a little more"
    receptiveness = __import__(
        "app.services.commercial_receptiveness_service",
        fromlist=["CommercialReceptivenessService"],
    ).CommercialReceptivenessService(
        service.has_direct_purchase_intent
    ).evaluate(
        context={"latest_message": message},
        recent_purchase=False,
        cooldown_active=False,
    ).to_mapping()
    base = service.refine(
        decision(), {"latest_message": message, "sales_progression": state()},
    )
    base = CustomerSalesDecision(**{
        **base.__dict__,
        "decision_metadata": immutable_mapping({
            **dict(base.decision_metadata),
            "commercialReceptiveness": dict(receptiveness),
        }),
    })

    refined = CustomerSalesBrainService.refine_for_readiness(base, {
        "positive_tease_response": True,
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "classifier_close_ready": True,
        "conversation_ready_for_offer": True,
        "recommended_conversational_action": "PRESENT_OFFER",
        "recommended_action": "offer",
        "curiosity_level": "high",
    })

    assert refined.decision is CustomerSalesDecisionType.BUILD_INTEREST
    assert refined.sell_allowed is False
    projection = dict(refined.decision_metadata)["commercialReceptiveness"]
    assert projection["commercialInterestType"] == "COMMERCIAL_CURIOSITY"
    assert projection["freshDirectIntentDetected"] is False


def test_direct_actionable_request_retains_precedence_after_tease():
    service = ConversationalSalesProgressionService()
    features = service.transition_features("let me see what you mean")
    assert features["reveal_request"] is True
    assert service.has_direct_purchase_intent("let me see what you mean") is True
    result = service.refine(decision(), {
        "latest_message": "let me see what you mean",
        "sales_progression": state(),
    })
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.reason_code is CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT


def test_admin_closed_history_plus_renewed_content_request_presents_fresh_offer():
    historical = decision()
    historical = CustomerSalesDecision(**{
        **historical.__dict__,
        "decision_metadata": immutable_mapping({
            "latestPurchaseIntentId": "8bb9270a-f682-4953-992b-95ec05a1bbf3",
            "latestIntentStatus": "ADMIN_CLOSED",
            "historicalCommercialContext": {
                "previousOfferPresented": True,
                "previousOfferAdminClosed": True,
                "previousOfferingId": str(OFFER),
                "executionReusable": False,
            },
        }),
    })
    result = ConversationalSalesProgressionService().refine(
        historical,
        {
            "latest_message": "Okay Ava 😏 show me what you’ve got.",
            "sales_progression": state(phase="PRESENT_OFFER", count=2),
        },
    )
    metadata = dict(result.decision_metadata)
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.reason_code is CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT
    assert result.active_purchase_intent_id is None
    assert metadata["latestIntentStatus"] == "ADMIN_CLOSED"
    assert metadata["historicalCommercialContext"]["executionReusable"] is False
    assert metadata["salesProgressionTransition"] == {
        "priorPhase": "PRESENT_OFFER",
        "transitionSignal": "DIRECT_PURCHASE_INTENT",
        "nextPhase": "PRESENT_OFFER",
    }


@pytest.mark.parametrize("message", (
    "you're hot 😏", "maybe", "lol prove it", "you think you can handle me?",
    "what are you doing?",
))
def test_generic_flirting_does_not_become_direct_content_request(message):
    service = ConversationalSalesProgressionService()
    assert service.has_direct_purchase_intent(message) is False
    result = service.refine(decision(), {"latest_message": message})
    assert result.decision is not CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is False


def test_price_request_presents_canonical_offer_now():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "How much is that photo?"},
    )
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.reason_code is CustomerSalesReasonCode.PRICE_REQUEST
    assert result.recommended_offering_price_minor == 1799
    assert result.recommended_delivery_url.endswith("/canonical")


def test_relevant_opportunity_teases_without_price_or_link_authorization():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "you look hot in that photo"},
    )
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert result.sell_allowed is False
    assert result.reason_code is CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY


def test_positive_tease_response_builds_interest_then_presents():
    service = ConversationalSalesProgressionService()
    built = service.refine(
        decision(), {"latest_message": "tell me more", "sales_progression": state()},
    )
    assert built.decision is CustomerSalesDecisionType.BUILD_INTEREST
    progressed = dict(built.decision_metadata)["salesProgression"]
    offered = service.refine(
        decision(), {"latest_message": "yes definitely", "sales_progression": progressed},
    )
    assert offered.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert offered.reason_code is CustomerSalesReasonCode.PRESENT_AFTER_POSITIVE_TEASE_RESPONSE


def test_turn_26_semantics_advance_persisted_tease_to_build_interest():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": (
                "Okay now you definitely have my attention 😂 "
                "give me a little hint at least"
            ),
            "sales_progression": state(),
        },
    )
    progression = dict(result.decision_metadata)["salesProgression"]
    transition = dict(result.decision_metadata)["salesProgressionTransition"]
    assert result.decision is CustomerSalesDecisionType.BUILD_INTEREST
    assert progression["teaseCount"] == 2
    assert transition == {
        "priorPhase": "TEASE",
        "transitionSignal": "POSITIVE_TEASE_RESPONSE",
        "nextPhase": "BUILD_INTEREST",
    }


def test_turn_27_semantics_advance_build_interest_to_present_offer():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "Alright you’ve teased me enough 😂 what is it?",
            "sales_progression": state(phase="BUILD_INTEREST", count=2),
        },
    )
    transition = dict(result.decision_metadata)["salesProgressionTransition"]
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.reason_code is CustomerSalesReasonCode.PRESENT_AFTER_POSITIVE_TEASE_RESPONSE
    assert transition["transitionSignal"] == "REVEAL_REQUEST"


@pytest.mark.parametrize("message", (
    "How was your weekend?", "Charlie sounds adorable 😂",
    "What music do you like?", "Is it evening there?",
    "Where is your hometown?", "really? 👀",
))
def test_friendly_or_weak_generic_chat_does_not_advance_existing_tease(message):
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": message, "sales_progression": state()},
    )
    progression = dict(result.decision_metadata)["salesProgression"]
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert progression["phase"] == "TEASE"
    assert progression["teaseCount"] == 1


def test_reveal_request_without_prior_momentum_does_not_jump_to_offer():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "what is it?"},
    )
    assert result.decision is CustomerSalesDecisionType.TEASE


def test_escalation_ready_requires_positive_response_and_prior_tease():
    teased = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "tell me about that photo"},
    )
    unsupported = CustomerSalesBrainService.refine_for_readiness(
        teased, {
            "escalation_ready": True, "recommended_action": "build_tension",
            "positive_tease_response": False,
            "conversation_ready_for_offer": False,
        },
    )
    assert unsupported.decision is CustomerSalesDecisionType.TEASE

    continued = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "okay", "sales_progression": state()},
    )
    supported = CustomerSalesBrainService.refine_for_readiness(
        continued, {
            "escalation_ready": True, "recommended_action": "build_tension",
            "positive_tease_response": True,
            "conversation_ready_for_offer": False,
        },
    )
    assert supported.decision is CustomerSalesDecisionType.BUILD_INTEREST
    assert dict(supported.decision_metadata)["salesProgressionTransition"][
        "transitionSignal"
    ] == "POSITIVE_TEASE_RESPONSE_SUPPORTED"


def test_escalation_ready_from_conversational_state_cannot_authorize_offer():
    result = CustomerSalesBrainService.refine_for_readiness(
        decision(), {
            "escalation_ready": True, "recommended_action": "build_tension",
            "positive_tease_response": True,
            "conversation_ready_for_offer": False,
        },
    )
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.sell_allowed is False


def test_weak_response_does_not_present_offer():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "hmm", "sales_progression": state()},
    )
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.sell_allowed is False


@pytest.mark.parametrize("message,reason", (
    ("nah, not right now", CustomerSalesReasonCode.CUSTOMER_DECLINED),
    ("maybe later", CustomerSalesReasonCode.CUSTOMER_DECLINED),
    ("that's too expensive", CustomerSalesReasonCode.CUSTOMER_HESITATION),
))
def test_negative_or_hesitant_response_backs_off(message, reason):
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": message, "sales_progression": state()},
    )
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.reason_code is reason
    assert result.sell_allowed is False


def test_prior_tease_decline_is_detected_before_product_reselection():
    service = ConversationalSalesProgressionService()
    assert service.back_off_reason({
        "latest_message": "nah not right now",
        "sales_progression": state(),
    }) is CustomerSalesReasonCode.CUSTOMER_DECLINED


def test_backoff_suppresses_immediate_reoffer_for_same_opportunity():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "okay",
            "sales_progression": state(phase="BACK_OFF"),
        },
    )
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.BACK_OFF


def test_teasing_is_bounded_and_cannot_loop_indefinitely():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "okay",
            "sales_progression": state(count=2),
        },
    )
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.reason_code is CustomerSalesReasonCode.TEASE_LIMIT_REACHED


def test_insufficient_grounding_fails_closed():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "show me",
            "critical_grounding_available": False,
        },
    )
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.reason_code is CustomerSalesReasonCode.INSUFFICIENT_GROUNDING
    assert result.sell_allowed is False


def test_no_selected_opportunity_remains_no_sale():
    original = decision(selected=False)
    assert ConversationalSalesProgressionService().refine(
        original, {"latest_message": "hello"},
    ) is original


def test_different_opportunity_does_not_inherit_old_tease_count():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "okay", "sales_progression": {
            "phase": "BUILD_INTEREST", "offeringId": "different", "teaseCount": 9,
        }},
    )
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert dict(result.decision_metadata)["salesProgression"]["teaseCount"] == 1


def test_tease_runtime_receives_grounding_but_not_price_or_delivery():
    teased = ConversationalSalesProgressionService().refine(
        decision(product_context={
            "offeringType": "SINGLE_IMAGE", "heroAssetId": 195,
            "assetIntelligence": {"sceneEnvironment": "sunlit bedroom"},
        }),
        {"latest_message": "you look gorgeous in that photo"},
    )
    gateway = ConversationGateway.__new__(ConversationGateway)
    runtime = gateway._commerce_runtime_injection(teased)
    commerce = runtime["commerce_decision"]
    assert commerce["sales_progression"]["phase"] == "TEASE"
    assert commerce["selected_opportunity"]["customer_safe_description"] == "Verified content"
    assert "title" not in commerce["selected_opportunity"]
    assert "price_minor" not in commerce["selected_opportunity"]
    assert "selected_offering" not in commerce
    assert commerce["single_image_conversation"]["canonicalIntelligence"] == {
        "sceneEnvironment": "sunlit bedroom",
    }


def test_tease_without_intelligence_is_explicitly_generic():
    teased = ConversationalSalesProgressionService().refine(
        decision(product_context={
            "offeringType": "SINGLE_IMAGE", "heroAssetId": 398,
            "assetIntelligence": {},
        }),
        {"latest_message": "you look gorgeous in that photo"},
    )
    gateway = ConversationGateway.__new__(ConversationGateway)
    commerce = gateway._commerce_runtime_injection(teased)["commerce_decision"]
    assert "single_image_conversation" not in commerce


def test_generation_receives_canonical_curiosity_truth_context():
    base = decision()
    projected = CustomerSalesDecision(**{
        **base.__dict__,
        "decision_metadata": immutable_mapping({
            "customerValueAttention": {
                "commercialInterestType": "COMMERCIAL_CURIOSITY",
            },
            "commercialReceptiveness": {
                "commercialInterestType": "COMMERCIAL_CURIOSITY",
                "freshDirectIntentDetected": False,
            },
            "activeBuyingWindow": {"active": False},
            "contextualCustomerTone": {"buyingIntent": False},
        }),
    })
    commerce = ConversationGateway.__new__(
        ConversationGateway
    )._commerce_runtime_injection(projected)["commerce_decision"]

    assert commerce["customer_value_attention"][
        "commercialInterestType"
    ] == "COMMERCIAL_CURIOSITY"
    assert commerce["commercial_receptiveness"][
        "freshDirectIntentDetected"
    ] is False
    assert commerce["active_buying_window"]["active"] is False
    assert commerce["contextual_customer_tone"]["buyingIntent"] is False


def test_internal_offering_title_is_operator_diagnostic_only():
    gateway = ConversationGateway.__new__(ConversationGateway)
    runtime = gateway._commerce_runtime_injection(decision())
    selected = runtime["commerce_decision"]["selected_offering"]
    assert "Canonical product" not in str(selected)
    assert selected["customer_safe_description"] == "Verified content"
    assert runtime["offering_copy_diagnostics"] == {
        "offeringInternalTitle": "Canonical product",
        "offeringCustomerSafeCopyAvailable": True,
        "internalOfferingMetadataExposedToGeneration": False,
    }


@pytest.mark.parametrize("message", (
    "you know what I like now",
    "that's what I like",
))
def test_relative_preference_language_does_not_create_bogus_memory(message):
    records = ConversationalMemoryService.extract_records(message)
    assert not [item for item in records if item["category"] == "preference"]


@pytest.mark.parametrize("message,expected", (
    ("I like hiking", "hiking"),
    ("I like rock music", "rock music"),
    ("I love camping", "camping"),
    ("I prefer dogs", "dogs"),
    ("I'm into Foo Fighters", "foo fighters"),
    ("I like hiking now", "hiking"),
))
def test_valid_preference_language_remains_durable(message, expected):
    values = [
        item["value"] for item in ConversationalMemoryService.extract_records(message)
        if item["category"] == "preference"
    ]
    assert expected in values


def test_unmapped_price_request_keeps_base_internal_and_provider_context_price_neutral():
    unresolved = decision()
    unresolved = CustomerSalesDecision(
        **{**unresolved.__dict__, "identity_resolved": False,
           "reason_code": CustomerSalesReasonCode.PRICE_REQUEST}
    )
    gateway = ConversationGateway.__new__(ConversationGateway)

    runtime = gateway._commerce_runtime_injection(unresolved)
    commerce = runtime["commerce_decision"]

    assert unresolved.recommended_offering_price_minor == 1799
    assert commerce["paid_presentation_contract"] == {
        "price_neutral": True,
        "presentation_complete": True,
        "customer_facing_price_status": "STRUCTURED_PAID_PRESENTATION",
        "conversational_price_suppressed": True,
    }
    assert commerce["selected_offering"] == {
        "customer_safe_description": "Verified content",
        "customer_safe_copy_available": True,
    }


def test_mapped_price_request_also_withholds_price_from_generation_context():
    mapped = decision()
    gateway = ConversationGateway.__new__(ConversationGateway)
    commerce = gateway._commerce_runtime_injection(mapped)["commerce_decision"]
    assert commerce["paid_presentation_contract"]["price_neutral"] is True
    assert commerce["paid_presentation_contract"]["conversational_price_suppressed"] is True
    assert "price_minor" not in commerce["selected_offering"]
    assert mapped.recommended_offering_price_minor == 1799


def test_existing_semantic_readiness_can_promote_tease_to_offer():
    teased = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "tell me about that photo"},
    )
    promoted = CustomerSalesBrainService.refine_for_readiness(
        teased, {"conversation_ready_for_offer": True},
    )
    assert promoted.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert promoted.sell_allowed is True
    assert promoted.reason_code is CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT


def test_ordinary_chat_keeps_eligible_opportunity_contextual_not_mandatory():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "How was your day?"},
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "CHAT",
        "conversation_ready_for_offer": False,
    })
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.sell_allowed is False
    progression = dict(result.decision_metadata)["salesProgression"]
    assert progression["phase"] == "CONVERSATIONAL"
    assert progression["offeringId"] == str(OFFER)


def proactive_candidate(*, time_waster="NONE", rejection_count=0, phase=None):
    base = decision(selected=False)
    metadata = {
        "customerValueAttention": {
            "valueTier": "ENGAGED_PROSPECT",
            "timeWasterRisk": time_waster,
            "conversationContinuationValue": "MEDIUM",
            "behaviorEvidenceCounts": {
                "inbound_message_count": 7,
                "offer_exposure_count": 0,
                "rejection_count": rejection_count,
            },
        },
    }
    if phase:
        metadata["salesProgression"] = phase
    return CustomerSalesDecision(**{
        **base.__dict__,
        "decision": CustomerSalesDecisionType.CONTINUE_CONVERSATION,
        "reason_code": CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
        "decision_metadata": immutable_mapping(metadata),
    })


def proactive_flags(**updates):
    return {
        "recommended_conversational_action": "TEASE_OFFER",
        "engagement_level": "medium",
        "recent_history_turn_count": 6,
        **updates,
    }


def test_engaged_relationship_can_authorize_ava_tease_without_customer_intent_or_inventory():
    result = CustomerSalesBrainService.refine_for_readiness(
        proactive_candidate(), proactive_flags(),
    )
    metadata = dict(result.decision_metadata)
    proactive = metadata["proactiveProgression"]
    opportunity = metadata["commercialOpportunity"]
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    assert proactive["proactiveProgressionAuthorized"] is True
    assert proactive["progressionInitiator"] == "AVA"
    assert proactive["progressionAction"] == "TEASE"
    assert opportunity["commercialAnchorPresent"] is False


def test_generalized_relationship_warming_evidence_is_not_scenario_or_exact_message_bound():
    evidence = ConversationalSalesProgressionService.relationship_warming_evidence([
        "You seem really cute.",
        "I usually take a while to open up.",
        "I really enjoy talking with you.",
        "This has been unexpectedly comfortable.",
    ])
    assert evidence["voluntaryCustomerTurnCount"] == 4
    assert evidence["relationalWarmthTurnCount"] >= 2
    assert evidence["reciprocalWarmingObserved"] is True


def test_generalized_low_return_evidence_separates_quiet_from_warmed_or_buying_turns():
    quiet = ConversationalSalesProgressionService.relationship_warming_evidence([
        "hey, how's it going?", "not too bad", "yeah pretty much",
        "work was okay", "mostly relaxing", "still here, just quiet",
    ])
    warmed = ConversationalSalesProgressionService.relationship_warming_evidence([
        "I really enjoy talking with you", "this is comfortable with you",
    ])
    buying = ConversationalSalesProgressionService.relationship_warming_evidence([
        "show me what you have", "how much is it?",
    ])
    assert quiet["lowConversationalReturnCount"] >= 4
    assert warmed["lowConversationalReturnCount"] == 0
    assert buying["lowConversationalReturnCount"] == 0


def test_minimal_or_merely_friendly_conversation_does_not_authorize_proactive_tease():
    minimal = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 2,
        "meaningful_engagement_count": 2,
        "recent_history_turn_count": 2,
        "durable_conversational_fact_count": 0,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": False},
        "offer_exposure_count": 0,
    })
    friendly_only = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 8,
        "meaningful_engagement_count": 8,
        "recent_history_turn_count": 8,
        "durable_conversational_fact_count": 0,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": False},
        "offer_exposure_count": 0,
    })
    assert minimal["authorized"] is False
    assert friendly_only["authorized"] is False


def test_sustained_self_disclosing_reciprocal_warming_authorizes_tease_only():
    readiness = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 7,
        "meaningful_engagement_count": 7,
        "recent_history_turn_count": 7,
        "durable_conversational_fact_count": 4,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
        "offer_exposure_count": 0,
    })
    assert readiness["authorized"] is True
    assert "RECIPROCAL_RELATIONAL_WARMING" in readiness["evidence"]
    # Readiness is conversational only; it carries no product or execution data.
    assert "offeringId" not in readiness
    assert "purchaseIntentId" not in readiness

    result = CustomerSalesBrainService.authorize_deterministic_proactive_tease(
        proactive_candidate(), {
            "inbound_message_count": 7,
            "meaningful_engagement_count": 7,
            "recent_history_turn_count": 7,
            "durable_conversational_fact_count": 4,
            "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
            "offer_exposure_count": 0,
        },
    )
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    assert result.active_purchase_intent_id is None


def test_attempt_55_evidence_is_authoritative_before_generation():
    messages = [
        "Hey - you seem really sweet. How's your day been?",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl.",
        "Haha maybe a little. I'm usually pretty quiet at first though. Takes me a minute to warm up to somebody.",
        "I'm kinda an outdoors person once I actually get off the couch - hiking, camping, stuff like that.",
        "See - told you I warm up eventually. I could talk about hiking forever.",
    ]
    context = {
        "inbound_message_count": 6,
        "meaningful_engagement_count": 6,
        "recent_history_turn_count": 6,
        "durable_conversational_fact_count": 4,
        "relationship_warming_evidence": (
            ConversationalSalesProgressionService.relationship_warming_evidence(messages)
        ),
        "offer_exposure_count": 0,
    }
    result = CustomerSalesBrainService.authorize_deterministic_proactive_tease(
        proactive_candidate(), context,
    )
    proactive = dict(result.decision_metadata)["proactiveProgression"]
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert proactive["proactiveProgressionAuthorized"] is True
    assert set(proactive["proactiveProgressionEvidence"]) == {
        "SUSTAINED_VOLUNTARY_CONVERSATION", "MEANINGFUL_ENGAGEMENT",
        "VOLUNTARY_SELF_DISCLOSURE", "RECIPROCAL_RELATIONAL_WARMING",
        "NO_OFFER_EXPOSURE",
    }
    assert result.sell_allowed is False
    assert result.active_purchase_intent_id is None


def test_memory_projection_exposes_canonical_durable_record_count():
    state = ConversationalMemoryService._normalize_state({})
    for message in (
        "I'm usually pretty quiet at first. Takes me a minute to warm up.",
        "I'm into hiking, camping, and the outdoors.",
    ):
        ConversationalMemoryService._merge_records(
            state, ConversationalMemoryService.extract_records(message),
        )
    projection = ConversationalMemoryService.retrieve(
        state, "I could talk about hiking forever.",
    )
    assert projection["durableRecordCount"] == len([
        record for record in state["records"]
        if record.get("status") == "current" and record.get("value") not in (None, "")
    ])


def test_ai_readiness_cannot_create_canonical_tease_progression():
    preflight = CustomerSalesBrainService.proactive_progression_preflight(
        proactive_candidate(), recent_history_turn_count=8,
    )
    result = CustomerSalesBrainService.activate_pre_generation_proactive_progression(
        preflight, {
            "recommended_conversational_action": "TEASE_OFFER",
            "engagement_level": "high",
        },
    )
    assert result["proactiveProgressionAuthorized"] is False
    assert result["progressionAction"] == "NONE"


def test_playful_reciprocation_semantically_acknowledges_compliment():
    style = GPTService._style_analysis(
        "careful, you haven't seen trouble yet",
        "Yeah - you're pretty easy to talk to honestly.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert "ACKNOWLEDGE_COMPLIMENT" in style["turnObligations"]
    assert "ACKNOWLEDGE_COMPLIMENT" in style["satisfiedTurnObligations"]
    assert style["turnObligationsSatisfied"] is True


def test_social_flirt_during_continue_does_not_persist_commercial_tease():
    original = proactive_candidate()
    result, runtime = ConversationGateway._finalize_progression_delivery(
        original,
        response_text="careful, you haven't seen trouble yet",
        blocked=False, offer_authorized=False,
        style={
            "proactiveTeaseSatisfied": True,
            "meaningfulContributionType": "FLIRT_RECIPROCATION",
        },
    )
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert dict(result.decision_metadata).get("salesProgression", {}).get("phase") in {
        None, "CONVERSATIONAL",
    }
    assert runtime["social_flirtation_present"] is True
    assert runtime["commercial_tease_authorized"] is False
    assert runtime["commercial_tease_delivered"] is False
    assert runtime["commercial_tease_satisfied"] is False


def test_authorized_tease_waits_for_confirmed_delivery_before_progression():
    authorized = CustomerSalesBrainService.authorize_deterministic_proactive_tease(
        proactive_candidate(), {
            "inbound_message_count": 6, "meaningful_engagement_count": 6,
            "recent_history_turn_count": 6,
            "durable_conversational_fact_count": 4,
            "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
            "offer_exposure_count": 0,
        },
    )
    result, runtime = ConversationGateway._finalize_progression_delivery(
        authorized,
        response_text="careful, you haven't seen trouble yet",
        blocked=False, offer_authorized=False,
        style={"proactiveTeaseSatisfied": True},
    )
    progression = dict(result.decision_metadata)["salesProgression"]
    assert progression["phase"] == "CONVERSATIONAL"
    assert progression["proactiveTeaseDelivered"] is False
    assert runtime["commercial_tease_authorized"] is True
    assert runtime["tease_type"] == "PROACTIVE_RELATIONSHIP"
    assert runtime["commercial_tease_wording_satisfied"] is True
    assert runtime["commercial_tease_delivery_pending_confirmation"] is True
    assert runtime["commercial_tease_delivered"] is False
    assert runtime["progression_finalized_after_delivery"] is False
    assert runtime["pending_sales_progression"]["phase"] == "TEASE"
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    assert result.active_purchase_intent_id is None


@pytest.mark.parametrize("external_buyer_uuid", (None, "fanvue-buyer-22"))
def test_pending_tease_scope_uses_resolved_gateway_brain_context(external_buyer_uuid):
    brain_context = SimpleNamespace(
        creator_profile_id=2,
        fanvue_account_id=7,
        telegram_user_id=9_100_000_005,
        external_fanvue_buyer_uuid=external_buyer_uuid,
    )
    scope = ConversationGateway._pending_progression_scope(
        brain_context, sales_session=None, correlation_id="c05:attempt:turn",
    )
    assert scope == {
        "creator_profile_id": 2,
        "fanvue_account_id": 7,
        "telegram_user_id": 9_100_000_005,
        "sales_session_id": None,
        "correlation_id": "c05:attempt:turn",
    }


def test_confirmed_send_finalizes_pending_unmapped_tease_once():
    progression = {
        "phase": "TEASE", "teaseType": "OPPORTUNITY_GROUNDED",
        "offeringId": str(OFFER), "teaseCount": 1,
    }
    confirmed = SimpleNamespace(
        response_payload={"diagnostic_metadata": {
            "progression_finalized_after_delivery": True,
            "pending_sales_progression": progression,
            "pending_sales_progression_context": {
                "creator_profile_id": 2, "fanvue_account_id": 7,
                "telegram_user_id": 22, "sales_session_id": None,
                "correlation_id": "turn:22:1",
            },
        }},
        correlation_id="turn:22:1",
    )

    class Repository:
        def confirm_sent(self, *_args, **_kwargs):
            return confirmed

    class Prospects:
        def __init__(self): self.calls = []
        def record_sales_progression(self, **values): self.calls.append(values)

    prospects = Prospects()
    service = OrdinaryChatReplyService(
        repository=Repository(), worker_id="worker",
        prospect_service=prospects,
    )
    operation = SimpleNamespace(operation_id=OFFER)
    assert service.confirmed(operation, 9001) is confirmed
    assert len(prospects.calls) == 1
    assert prospects.calls[0]["progression"] == progression


def test_failed_tease_send_never_finalizes_pending_progression():
    class Repository:
        def fail_send(self, *_args, **_kwargs):
            return SimpleNamespace(state="FAILED")

    class Prospects:
        def __init__(self): self.calls = []
        def record_sales_progression(self, **values): self.calls.append(values)

    prospects = Prospects()
    service = OrdinaryChatReplyService(
        repository=Repository(), worker_id="worker",
        prospect_service=prospects,
    )
    operation = SimpleNamespace(operation_id=OFFER)
    failed = service.failed(operation, ConnectionError("delivery failed"), definitive=True)
    assert failed.state == "FAILED"
    assert prospects.calls == []


def test_confirmed_send_persists_session_proposal_delivery_truth_once():
    confirmed = SimpleNamespace(
        response_payload={"diagnostic_metadata": {
            "session_proposal_delivery_pending_confirmation": True,
            "pending_session_proposal": {"offeringId": str(OFFER)},
            "pending_session_proposal_context": {
                "creator_profile_id": 2, "fanvue_account_id": 7,
                "telegram_user_id": 22, "sales_session_id": None,
                "correlation_id": "turn:22:session-proposal",
            },
        }},
        correlation_id="ordinary:22:session-proposal",
    )

    class Repository:
        def confirm_sent(self, *_args, **_kwargs):
            return confirmed

    class Prospects:
        def __init__(self): self.calls = []
        def record_session_proposal(self, **values): self.calls.append(values)

    prospects = Prospects()
    service = OrdinaryChatReplyService(
        repository=Repository(), worker_id="worker",
        prospect_service=prospects,
    )
    operation = SimpleNamespace(operation_id=OFFER)
    assert service.confirmed(operation, 9102) is confirmed
    assert prospects.calls == [{
        "creator_profile_id": 2,
        "fanvue_account_id": 7,
        "telegram_user_id": 22,
        "correlation_id": "turn:22:session-proposal",
        "source_inbound": "turn:22:session-proposal",
        "delivery_correlation_id": "ordinary:22:session-proposal",
        "delivery_provider_message_id": 9102,
        "session_offering_id": str(OFFER),
    }]


def test_generated_but_unconfirmed_session_proposal_is_not_persisted():
    class Repository:
        def fail_send(self, *_args, **_kwargs):
            return SimpleNamespace(state="FAILED")

    class Prospects:
        def __init__(self): self.calls = []
        def record_session_proposal(self, **values): self.calls.append(values)

    prospects = Prospects()
    service = OrdinaryChatReplyService(
        repository=Repository(), worker_id="worker",
        prospect_service=prospects,
    )
    operation = SimpleNamespace(operation_id=OFFER)
    service.failed(operation, ConnectionError("not delivered"), definitive=True)
    assert prospects.calls == []


def test_opportunity_grounded_tease_is_explicit_and_not_a_paid_offer():
    result = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "you are so hot", "sales_progression": {}},
    )
    metadata = dict(result.decision_metadata)
    assert result.decision is CustomerSalesDecisionType.TEASE
    assert metadata["teaseType"] == "OPPORTUNITY_GROUNDED"
    assert metadata["salesProgression"]["teaseType"] == "OPPORTUNITY_GROUNDED"
    assert result.sell_allowed is False
    assert result.active_purchase_intent_id is None


def test_proactive_readiness_remains_fail_closed_for_backoff_or_existing_progression():
    base = {
        "inbound_message_count": 7, "meaningful_engagement_count": 7,
        "recent_history_turn_count": 7, "durable_conversational_fact_count": 4,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
        "offer_exposure_count": 0,
    }
    assert CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        **base, "rejection_count": 1,
    })["authorized"] is False
    assert CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        **base, "sales_progression": {"phase": "TEASE"},
    })["authorized"] is False


@pytest.mark.parametrize(("candidate", "flags", "reason"), (
    (proactive_candidate(), proactive_flags(recent_history_turn_count=0),
     "INSUFFICIENT_COMBINED_RELATIONSHIP_EVIDENCE"),
    (proactive_candidate(time_waster="HIGH"), proactive_flags(), "HIGH_TIME_WASTER_RISK"),
    (proactive_candidate(rejection_count=1), proactive_flags(), "REJECTION_OR_BACK_OFF"),
    (proactive_candidate(phase={"phase": "CONVERSATIONAL", "proactiveTeaseCooldownTurns": 2}),
     proactive_flags(), "PROACTIVE_TEASE_COOLDOWN"),
))
def test_proactive_tease_is_suppressed_without_combined_safe_evidence(candidate, flags, reason):
    result = CustomerSalesBrainService.refine_for_readiness(candidate, flags)
    proactive = dict(result.decision_metadata)["commercialOpportunity"]["proactiveProgression"]
    assert result.decision is not CustomerSalesDecisionType.TEASE
    assert proactive["proactiveProgressionAuthorized"] is False
    assert proactive["proactiveProgressionReason"] == reason


def test_customer_response_to_ava_tease_advances_once_or_returns_to_chat():
    phase = {
        "phase": "TEASE", "teaseCount": 1, "progressionInitiator": "AVA",
        "awaitingCustomerResponse": True,
    }
    lean = CustomerSalesBrainService.refine_for_readiness(
        proactive_candidate(phase=phase),
        proactive_flags(positive_tease_response=True, curiosity_level="medium"),
    )
    assert lean.decision is CustomerSalesDecisionType.BUILD_INTEREST
    assert dict(lean.decision_metadata)["salesProgression"]["phase"] == "BUILD_INTEREST"
    ignore = CustomerSalesBrainService.refine_for_readiness(
        proactive_candidate(phase=phase),
        proactive_flags(recommended_conversational_action="CHAT"),
    )
    ignored = dict(ignore.decision_metadata)
    assert ignore.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert ignored["salesProgression"]["phase"] == "CONVERSATIONAL"
    assert ignored["salesProgression"]["proactiveTeaseCooldownTurns"] == 2
    rejected = CustomerSalesBrainService.refine_for_readiness(
        proactive_candidate(phase=phase),
        proactive_flags(recommended_conversational_action="BACK_OFF"),
    )
    assert rejected.decision is CustomerSalesDecisionType.BACK_OFF
    assert dict(rejected.decision_metadata)["proactiveProgression"][
        "customerResponseToPreviousTease"
    ] == "GLOBAL_REJECT"


def test_model_timing_can_present_directly_without_progression_prerequisites():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "Got anything cute from tonight?"},
    )
    assert candidate.decision is CustomerSalesDecisionType.TEASE
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "PRESENT_OFFER",
        "conversation_ready_for_offer": True,
    })
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True
    transition = dict(result.decision_metadata)["salesProgressionTransition"]
    assert transition == {
        "priorPhase": "CONVERSATIONAL",
        "transitionSignal": "AI_RECOMMENDED_PRESENTATION",
        "nextPhase": "PRESENT_OFFER",
    }


def test_model_timing_can_present_from_tease_without_build_interest_gate():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "okay", "sales_progression": state(),
        },
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "PRESENT_OFFER",
        "conversation_ready_for_offer": True,
        "positive_tease_response": True,
        "recommended_action": "offer",
    })
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert dict(result.decision_metadata)["salesProgressionTransition"][
        "priorPhase"
    ] == "TEASE"


def test_model_backoff_cannot_be_promoted_to_offer():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "you look cute"},
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "BACK_OFF",
        "conversation_ready_for_offer": True,
    })
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.sell_allowed is False


def test_bounded_action_contract_never_accepts_model_offering_or_price():
    flags = {
        "recommended_conversational_action": "PRESENT_OFFER",
        "recommended_offering_id": "invented-by-model",
        "recommended_price_minor": 1,
    }
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "show me something"},
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, flags)
    assert result.recommended_offering_id == OFFER
    assert result.recommended_offering_price_minor == 1799


def test_action_normalization_distinguishes_chat_tease_present_and_backoff():
    service = ConversationalSalesProgressionService
    assert service.recommended_conversational_action(
        "How was your day?", {"recommended_action": "chat"}, {},
    ) == "CHAT"
    assert service.recommended_conversational_action(
        "You have me curious", {"recommended_action": "build_tension"}, {},
    ) == "TEASE_OFFER"
    assert service.recommended_conversational_action(
        "Show me that", {"recommended_action": "chat"}, {},
    ) == "PRESENT_OFFER"
    assert service.recommended_conversational_action(
        "No, stop", {"recommended_action": "offer"}, {},
    ) == "BACK_OFF"


def test_engine_readiness_exports_bounded_action_without_model_commerce_values():
    readiness = DecisionEngine._commerce_readiness(
        "Got anything cute from tonight?",
        {"recommended_action": "offer", "recommended_offering_id": "fake"},
        {},
    )
    assert readiness["recommended_conversational_action"] == "PRESENT_OFFER"
    assert readiness["conversation_ready_for_offer"] is True
    assert readiness["recommended_offering_id"] is None
    assert readiness["offering_authority"] == "DETERMINISTIC_SELECTOR_ONLY"


def test_turn_10_content_request_overrides_model_flirt_misclassification():
    readiness = DecisionEngine._commerce_readiness(
        "Okay Ava 😏 show me what you’ve got.",
        {
            "route": "chat", "buying_intent": False, "close_ready": False,
            "sexual_engagement": True, "recommended_action": "build_tension",
        },
        {},
    )
    assert readiness["current_buying_intent"] is True
    assert readiness["customer_requested_content"] is True
    assert readiness["recommended_conversational_action"] == "PRESENT_OFFER"
    assert readiness["conversation_ready_for_offer"] is True


def test_playful_maybe_is_not_customer_hesitation():
    service = ConversationalSalesProgressionService()
    context = {
        "latest_message": (
            "Maybe, but you're the one teasing. What do I get if I prove you wrong?"
        ),
        "sales_progression": state(),
    }
    assert service.back_off_reason(context) is None
    assert service.refine(decision(), context).decision is not (
        CustomerSalesDecisionType.BACK_OFF
    )


def test_genuine_maybe_later_remains_backoff():
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "Maybe later, I'm not sure I want to pay.",
            "sales_progression": state(),
        },
    )
    assert result.decision is CustomerSalesDecisionType.BACK_OFF
    assert result.sell_allowed is False


def test_live_trajectory_prefers_offer_when_another_tease_has_lower_value():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": (
                "Alright, you've got me curious. Show me what you've been teasing me about."
            ),
            "sales_progression": state(),
        },
    )
    assert candidate.decision is CustomerSalesDecisionType.BUILD_INTEREST
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "TEASE_OFFER",
        "recommended_action": "build_tension",
        "conversation_ready_for_offer": False,
        "escalation_ready": True,
        "positive_tease_response": True,
        "curiosity_level": "medium",
        "engagement_level": "medium",
        "buyer_likelihood": "medium",
        "recent_history_turn_count": 5,
    })
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True
    opportunity = dict(result.decision_metadata)["commercialOpportunity"]
    assert opportunity["presentPreferred"] is True
    assert opportunity["contributions"]["escalationReady"] == 24
    assert opportunity["contributions"]["teaseDiminishingReturn"] > 0
    assert opportunity["finalRationale"] == (
        "PRESENT_VALUE_EXCEEDS_ADDITIONAL_TEASE_VALUE"
    )
    diagnostics = ConversationGateway._customer_sales_diagnostics(result)
    assert diagnostics["commercial_opportunity"]["strengthScore"] == (
        opportunity["strengthScore"]
    )
    assert diagnostics["commercial_opportunity"]["suppressions"] == ()


def test_first_light_curiosity_does_not_cross_presentation_threshold():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "Okay, now I'm a little curious."},
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "TEASE_OFFER",
        "recommended_action": "build_tension",
        "positive_tease_response": True,
        "curiosity_level": "medium",
        "engagement_level": "medium",
        "buyer_likelihood": "medium",
        "recent_history_turn_count": 1,
    })
    assert result.decision in {
        CustomerSalesDecisionType.TEASE,
        CustomerSalesDecisionType.BUILD_INTEREST,
    }
    assert result.sell_allowed is False
    assert dict(result.decision_metadata)["commercialOpportunity"][
        "presentPreferred"
    ] is False


def test_fresh_curiosity_cannot_gain_direct_intent_through_buying_window():
    window = ActiveBuyingWindowService.project(
        recent_verified_purchase=False,
        fresh_direct_intent=False,
        explicit_continuation=True,
        active_purchase_intent=False,
        active_offer_context=False,
        acknowledgement_pending=False,
        declined=False,
        safety_allowed=True,
        active_session=False,
        cooldown_active=False,
        receptiveness={
            "state": "WARM",
            "commercialInterestType": "COMMERCIAL_CURIOSITY",
            "freshDirectIntentDetected": False,
        },
        deferred_continuation={},
    )
    result = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "okay, I'm curious... tell me a little more",
            "sales_progression": state(phase="TEASE", count=1),
            "active_buying_window": window,
        },
    )

    assert window["active"] is False
    assert window["activeBuyingWindowAuthoritySatisfied"] is False
    assert result.decision is CustomerSalesDecisionType.BUILD_INTEREST
    assert result.reason_code is not CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT

    actionable_window = ActiveBuyingWindowService.project(
        recent_verified_purchase=False,
        fresh_direct_intent=True,
        explicit_continuation=False,
        active_purchase_intent=False,
        active_offer_context=False,
        acknowledgement_pending=False,
        declined=False,
        safety_allowed=True,
        active_session=False,
        cooldown_active=False,
        receptiveness={
            "state": "HOT",
            "commercialInterestType": "SEND_OR_LINK_REQUEST",
            "freshDirectIntentDetected": True,
        },
        deferred_continuation={},
    )
    presented = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "send it",
            "sales_progression": dict(result.decision_metadata)[
                "salesProgression"
            ],
            "active_buying_window": actionable_window,
        },
    )
    assert presented.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert presented.reason_code is CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT


def test_subject_change_suppresses_offer_despite_prior_trajectory():
    candidate = ConversationalSalesProgressionService().refine(
        decision(), {
            "latest_message": "How was your day?",
            "sales_progression": state(phase="BUILD_INTEREST", count=2),
        },
    )
    result = CustomerSalesBrainService.refine_for_readiness(candidate, {
        "recommended_conversational_action": "CHAT",
        "recent_history_turn_count": 6,
    })
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    opportunity = dict(result.decision_metadata)["commercialOpportunity"]
    assert "CUSTOMER_CHANGED_OR_REMAINED_ON_NONCOMMERCIAL_TOPIC" in (
        opportunity["suppressions"]
    )


def test_active_intent_is_an_authoritative_opportunity_suppression():
    active = CustomerSalesDecision(**{
        **decision().__dict__,
        "active_purchase_intent_id": UUID(
            "00000000-0000-0000-0000-000000000999"
        ),
    })
    opportunity = CustomerSalesBrainService._commercial_opportunity_assessment(
        active,
        {"escalation_ready": True, "positive_tease_response": True},
        progression=state(phase="BUILD_INTEREST", count=2),
        conversational_action="TEASE_OFFER",
    )
    assert opportunity["presentPreferred"] is False
    assert "ACTIVE_PURCHASE_INTENT" in opportunity["suppressions"]


def test_verified_repeat_buyer_memory_increases_commercial_opportunity_value():
    baseline = decision()
    repeat_buyer = CustomerSalesDecision(**{
        **baseline.__dict__,
        "decision_metadata": immutable_mapping({
            **dict(baseline.decision_metadata),
            "customerCommerceMemory": {
                "verifiedPurchaseCount": 3,
                "affinity": {"offeringTypes": {"SINGLE": 2}},
            },
        }),
    })
    flags = {
        "escalation_ready": True,
        "positive_tease_response": True,
        "curiosity_level": "medium",
    }
    progression = state(phase="TEASE", count=1)
    ordinary = CustomerSalesBrainService._commercial_opportunity_assessment(
        baseline,
        flags,
        progression=progression,
        conversational_action="TEASE_OFFER",
    )
    experienced = CustomerSalesBrainService._commercial_opportunity_assessment(
        repeat_buyer,
        flags,
        progression=progression,
        conversational_action="TEASE_OFFER",
    )
    assert experienced["strengthScore"] > ordinary["strengthScore"]
    assert experienced["contributions"]["verifiedBuyerHistory"] == 9
    assert experienced["contributions"]["knownCommerceAffinity"] == 6


def sexual_receptiveness_decision(count):
    base = decision()
    return CustomerSalesDecision(**{
        **base.__dict__,
        "decision": CustomerSalesDecisionType.CONTINUE_CONVERSATION,
        "sell_allowed": False,
        "decision_metadata": immutable_mapping({
            "configuration": {
                "sexualReceptivenessMinEngagements": 4,
                "sexualReceptivenessMinHistoryTurns": 3,
            },
            "customerValueAttention": {"behaviorEvidenceCounts": {
                "inbound_message_count": count,
                "sexual_engagement_count": count,
                "sexual_engagement_only": True,
                "rejection_count": 0,
            }},
        }),
    })


def test_one_sexual_turn_does_not_authorize_an_offer():
    result = CustomerSalesBrainService.refine_for_readiness(
        sexual_receptiveness_decision(1), {
            "recommended_conversational_action": "FLIRT",
            "engagement_level": "high", "recent_history_turn_count": 1,
        },
    )
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    opportunity = dict(result.decision_metadata)["commercialOpportunity"]
    assert opportunity["commercialAnchorPresent"] is False


def test_sustained_sexual_receptiveness_authorizes_offer_without_buying_intent():
    result = CustomerSalesBrainService.refine_for_readiness(
        sexual_receptiveness_decision(4), {
            "recommended_conversational_action": "FLIRT",
            "engagement_level": "high", "recent_history_turn_count": 4,
            "current_buying_intent": False,
            "conversation_ready_for_offer": False,
        },
    )
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True
    assert result.buyer_stage is CustomerBuyerStage.PROSPECT
    opportunity = dict(result.decision_metadata)["commercialOpportunity"]
    assert opportunity["presentPreferred"] is True
    assert "SUSTAINED_POSITIVE_SEXUAL_RECEPTIVENESS" in opportunity[
        "commercialAnchorEvidence"
    ]
    assert dict(result.decision_metadata)["salesProgressionTransition"][
        "transitionSignal"
    ] == "AI_RECOMMENDED_PRESENTATION"


def test_progression_persistence_uses_existing_sales_session_context():
    calls = []
    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._sales_session_service = type("Sessions", (), {
        "record_conversational_progression": staticmethod(
            lambda **values: calls.append(values)
        )
    })()
    session = type("Session", (), {
        "sales_session_id": UUID("00000000-0000-0000-0000-000000000010"),
        "creator_profile_id": 2,
    })()
    teased = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "tell me about that photo"},
    )
    gateway._record_sales_progression(session, teased)
    assert calls[0]["progression"]["phase"] == "TEASE"
    assert calls[0]["progression"]["offeringId"] == str(OFFER)


def test_progression_persistence_uses_unmapped_brain_with_operation_boundary():
    calls = []
    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._customer_sales_brain_service = type("Brain", (), {
        "record_unmapped_progression": staticmethod(
            lambda decision, **values: calls.append((decision, values))
        )
    })()
    teased = ConversationalSalesProgressionService().refine(
        decision(), {"latest_message": "tell me about that photo"},
    )

    gateway._record_sales_progression(
        None, teased, correlation_id="ordinary-reply-operation-28",
    )

    assert calls == [(teased, {
        "correlation_id": "ordinary-reply-operation-28",
    })]

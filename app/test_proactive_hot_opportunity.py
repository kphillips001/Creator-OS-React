from types import SimpleNamespace

import pytest

from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.contextual_customer_tone_service import ContextualCustomerToneService


def service():
    value = object.__new__(CustomerSalesBrainService)
    value.config = CustomerSalesBrainConfig.from_environment()
    return value


def hot_context(**overrides):
    values = {
        "inbound_message_count": 15,
        "sexual_engagement_count": 7,
        "sexual_engagement_only": True,
        "offer_exposure_count": 0,
        "rejection_count": 0,
        "contextual_customer_tone": {
            "sexualOrProvocative": True,
            "explicitDisengagement": False,
            "hostilityLevel": "NONE",
        },
        "sales_progression": {"phase": "CONVERSATIONAL"},
        "relationship_control_mode": "AVA_AUTO",
        "communication_disposition": "ACTIVE",
        "relationship_ignored": False,
        "effective_content_selling_allowed": True,
    }
    values.update(overrides)
    return values


def assess(context=None, *, active_intent=False, active_session=False):
    return service()._proactive_hot_opportunity_assessment(
        context or hot_context(),
        active_purchase_intent=active_intent,
        active_sales_session=active_session,
    )


def test_joseph_equivalent_authorizes_evaluation_only():
    result = assess()
    assert result["proactiveHotOpportunityDetected"] is True
    assert result["proactiveHotOpportunityAuthorized"] is True
    assert result["commercialEvaluationReason"] == "SUSTAINED_HOT_CONVERSATION"
    assert result["evaluationOnly"] is True
    assert result["offerAuthorized"] is False
    assert result["purchaseIntentCreated"] is False


def test_joseph_sustained_sequence_preserves_bounded_hot_continuity():
    classifier = ContextualCustomerToneService()
    transcript = []
    customer_turns = (
        "my fingers will play with your clit then one finger goes in and up",
        "How many fingers do you like",
        "kiss and lick your inner thighs up to between your sexy legs",
        "I know you will love it 😀",
        "To pleasure a beautiful sexy woman like you would be my pleasure",
    )
    ava_turns = (
        "That is a tempting question.",
        "You are making that sound dangerous.",
        "You sound very confident.",
        "That is quite an image.",
    )
    for index, message in enumerate(customer_turns):
        tone = classifier.classify(
            message=message, recent_transcript=tuple(transcript[-12:]),
        )
        assert tone["sexualOrProvocative"] is True
        result = assess(hot_context(contextual_customer_tone=tone))
        assert result["currentHotToneQualified"] is True
        assert result["sustainedSexualReceptiveness"] is True
        assert result["proactiveHotOpportunityAuthorized"] is True
        transcript.append({"role": "customer", "content": message})
        if index < len(ava_turns):
            transcript.append({"role": "assistant", "content": ava_turns[index]})


@pytest.mark.parametrize("context,blocker", [
    (hot_context(inbound_message_count=1, sexual_engagement_count=1),
     "SUSTAINED_CONVERSATION_REQUIRED"),
    (hot_context(sexual_engagement_count=0, sexual_engagement_only=False),
     "SUSTAINED_SEXUAL_RECEPTIVENESS_REQUIRED"),
    (hot_context(contextual_customer_tone={"sexualOrProvocative": False}),
     "CURRENT_HOT_TONE_REQUIRED"),
    (hot_context(offer_exposure_count=1), "PRIOR_PAID_OFFER_EXPOSURE"),
    (hot_context(rejection_count=1), "CUSTOMER_REJECTION"),
    (hot_context(sales_progression={"phase": "BACK_OFF"}), "BACK_OFF"),
    (hot_context(sales_progression={"phase": "CONVERSATIONAL",
                                    "proactiveTeaseCooldownTurns": 2}),
     "COMMERCIAL_OR_PROACTIVE_COOLDOWN"),
    (hot_context(purchase_cooldown_active=True),
     "COMMERCIAL_OR_PROACTIVE_COOLDOWN"),
    (hot_context(relationship_ignored=True), "RELATIONSHIP_IGNORED"),
    (hot_context(relationship_control_mode="HUMAN_OPERATOR"), "HUMAN_OPERATOR"),
    (hot_context(effective_content_selling_allowed=False),
     "CONTENT_SELLING_NOT_ALLOWED"),
])
def test_hot_path_hard_blockers(context, blocker):
    result = assess(context)
    assert result["proactiveHotOpportunityAuthorized"] is False
    assert blocker in result["hotOpportunityBlockers"]


def test_active_purchase_intent_and_session_block_without_duplicate_progression():
    assert "ACTIVE_PURCHASE_INTENT" in assess(
        active_intent=True
    )["hotOpportunityBlockers"]
    assert "ACTIVE_SALES_SESSION" in assess(
        active_session=True
    )["hotOpportunityBlockers"]


def test_one_sided_sexual_count_without_complete_authority_is_blocked():
    result = assess(hot_context(
        contextual_customer_tone={
            "sexualOrProvocative": True,
            "hostilityLevel": "HIGH",
        },
    ))
    assert result["proactiveHotOpportunityAuthorized"] is False
    assert result["sustainedSexualReceptiveness"] is False


def test_market_tier_and_hvp_are_not_hot_path_inputs():
    cold = hot_context(
        inbound_message_count=1,
        sexual_engagement_count=0,
        sexual_engagement_only=False,
        contextual_customer_tone={"sexualOrProvocative": False},
        market_tier="HIGH",
        high_value_prospect=True,
    )
    result = assess(cold)
    assert result["proactiveHotOpportunityAuthorized"] is False
    assert "market_tier" not in result
    assert "high_value_prospect" not in result


def test_hot_authority_enters_existing_inventory_evaluation_boundary():
    value = service()
    value.conversational_progression = SimpleNamespace(
        transition_features=lambda _: {},
        has_direct_purchase_intent=lambda _: False,
    )
    context = hot_context(
        latest_message="current hot turn",
        proactive_hot_opportunity=assess(),
        commercial_receptiveness={},
        classifier_result={},
    )
    assert value._commerce_selection_relevant(context) == (
        True, "SUSTAINED_POSITIVE_SEXUAL_RECEPTIVENESS"
    )


def test_hot_signal_does_not_authorize_inventory_when_safeguards_fail():
    value = service()
    value.conversational_progression = SimpleNamespace(
        transition_features=lambda _: {},
        has_direct_purchase_intent=lambda _: False,
    )
    blocked = assess(hot_context(offer_exposure_count=1))
    relevant, reason = value._commerce_selection_relevant(hot_context(
        latest_message="current hot turn",
        proactive_hot_opportunity=blocked,
        commercial_receptiveness={},
        classifier_result={},
    ))
    assert relevant is False
    assert reason == "NO_CURRENT_COMMERCIAL_EVIDENCE"


@pytest.mark.parametrize("message", [
    "how much is it?",
    "show me what you've got",
    "what can I unlock?",
])
def test_direct_commercial_path_remains_independent(message):
    assert ConversationalSalesProgressionService().has_direct_purchase_intent(
        message
    ) is True


def test_full_relational_warmup_still_requires_all_existing_evidence():
    result = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 8,
        "meaningful_engagement_count": 5,
        "recent_history_turn_count": 8,
        "durable_conversational_fact_count": 2,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
        "offer_exposure_count": 0,
    })
    assert result["authorized"] is True
    missing_meaningful = CustomerSalesBrainService._deterministic_proactive_tease_readiness({
        "inbound_message_count": 8,
        "meaningful_engagement_count": None,
        "recent_history_turn_count": 8,
        "durable_conversational_fact_count": 2,
        "relationship_warming_evidence": {"reciprocalWarmingObserved": True},
        "offer_exposure_count": 0,
    })
    assert missing_meaningful["authorized"] is False

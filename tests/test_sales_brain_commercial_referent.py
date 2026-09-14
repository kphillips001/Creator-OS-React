import pytest

from app.services.commercial_receptiveness_service import CommercialReceptivenessService
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService
from app.services.ava_attention_investment_service import AvaAttentionInvestmentService
from app.services.ava_human_availability_service import (
    AvaAvailabilityState, AvaHumanAvailabilityService,
)
from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
from app.services.conversation_quality_watch_service import ConversationQualityWatchService
from datetime import datetime, timezone
from app.models.customer_sales_decision import CustomerSalesDecisionType
from app.test_customer_sales_brain import brain, evaluate as evaluate_brain, offering, profile, signal


def evaluate(message, *, active_offer=False, context=None, readiness=None):
    service = CommercialReceptivenessService(
        ConversationalSalesProgressionService().has_direct_purchase_intent
    )
    return service.evaluate(
        context={"latest_message": message, **dict(context or {})},
        recent_purchase=False, cooldown_active=False,
        active_offer=active_offer, readiness=readiness,
    )


@pytest.mark.parametrize("message", [
    "Do I get a special photo babe 😘",
    "Can I see something special?",
    "Do you have private content?",
    "What do you have available?",
    "Can you send me a pic?",
    "Can I see more?",
    "Show me something",
    "How much for a photo?",
    "What can I unlock?",
])
def test_direct_content_requests_are_fresh_commercial_opportunities(message):
    result = evaluate(message)
    assert result.fresh_direct_intent is True
    assert result.state.value == "HOT"
    assert result.commercial_referent_present is True
    assert result.commercial_referent_type in {
        "DIRECT_CONTENT_INTENT", "OFFERING_AVAILABILITY_INQUIRY",
        "PRICE_REQUEST", "SEND_OR_LINK_REQUEST",
    }
    assert result.nurture_bypassed is True


@pytest.mark.parametrize("message", [
    "I love you", "You're mine", "I want you", "You want to fuck me?",
    "Make love to me", "Mmmmmm", "😘🔥", "You're sexy",
    "I'll take you", "Haha 😄 I'll take that babe x",
])
def test_affection_and_sex_are_not_buying_intent_without_referent(message):
    result = evaluate(message, readiness={
        "classifier_buying_intent": True, "classifier_close_ready": True,
        "recommended_conversational_action": "PRESENT_OFFER",
    })
    assert result.fresh_direct_intent is False
    assert result.state.value != "HOT"
    assert result.commercial_interest_type == "NONE"
    assert result.acceptance_grounded is False


def test_purchase_acceptance_requires_active_commercial_referent():
    ungrounded = evaluate("Haha 😄 I'll take that babe x")
    grounded = evaluate("I'll take it", active_offer=True)
    assert ungrounded.commercial_interest_type == "NONE"
    assert ungrounded.acceptance_grounded is False
    assert grounded.commercial_interest_type == "PURCHASE_ACCEPTANCE"
    assert grounded.acceptance_grounded is True
    assert grounded.commercial_referent_type == "ACTIVE_OFFER"


def test_expired_offer_does_not_resurrect_referential_acceptance():
    assert evaluate("I'll take it", active_offer=True).acceptance_grounded is True
    expired = evaluate("I'll take it", active_offer=False)
    assert expired.fresh_direct_intent is False
    assert expired.commercial_referent_present is False


def test_content_request_recovers_attention_but_not_availability():
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    availability = AvaHumanAvailabilityService(
        uniform=lambda low, high: 900,
        now=lambda: now,
        state_selector=lambda _: AvaAvailabilityState.BUSY,
    )
    before = availability.calculate(inbound_text="😘")
    after = availability.calculate(inbound_text="Do you have a special photo I can get?")
    assert before.available_at == after.available_at
    low = ["😘", "hello", "❤️", "babe", "🔥", "love you"]
    attention = AvaAttentionInvestmentService().evaluate(
        low + ["Do you have a special photo I can get?"]
    )
    assert attention.investment.value == "NORMAL"
    assert attention.commercial_referent is True
    assert attention.outcome == "RESPOND"


def test_ordinary_chat_cannot_invent_commercial_tease():
    policy = AvaNaturalConversationPolicy()
    blocked = policy.evaluate(
        customer_text="you're sexy", candidate="I've got something special to show you.",
    )
    authorized = policy.evaluate(
        customer_text="what do you have?", candidate="I've got something special to show you.",
        diagnostics={"customerSalesDecision": "PRESENT_OFFER"},
    )
    assert blocked.repaired is True
    assert "UNAUTHORIZED_COMMERCIAL_TEASE" in blocked.reasons
    assert authorized.repaired is False


def test_missed_commercial_opportunity_monitor_is_bounded_and_observational():
    reasons = ConversationQualityWatchService.material_reasons("You're sweet", {
        "commercial_receptiveness": {"freshDirectIntentDetected": True},
        "recommendation_diagnostics": {
            "inventoryEligible": True, "selectedOfferingId": "fixture-single",
        },
        "customer_sales_decision": "BUILD_INTEREST",
    })
    assert reasons == ["MISSED_COMMERCIAL_OPPORTUNITY"]


def test_special_photo_request_selects_existing_single_and_offer_wins():
    selected = offering()
    result = evaluate_brain(
        brain(customer=profile(), commerce_signal=signal(), eligible=selected),
        {"latest_message": "Do I get a special photo babe 😘"},
    )
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id == selected.offering_id
    receptiveness = result.decision_metadata["commercialReceptiveness"]
    assert receptiveness["freshDirectIntentDetected"] is True
    assert receptiveness["commercialReferentPresent"] is True
    assert receptiveness["nurtureBypassed"] is True


def test_special_photo_request_without_inventory_has_explicit_no_offer_reason():
    result = evaluate_brain(
        brain(customer=profile(), commerce_signal=signal(), eligible=None),
        {"latest_message": "Do I get a special photo babe 😘"},
    )
    assert result.decision is not CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id is None
    selector = result.decision_metadata.get("offeringSelector") or {}
    assert selector.get("selectionReason") == "NO_ELIGIBLE_OFFERING"


@pytest.mark.parametrize("message", [
    "Haha 😄 I'll take that babe x", "You want to fuck me?",
    "Or make love to me!", "Mmmmmm...", "😘🔥",
])
def test_sales_brain_does_not_present_inventory_for_ungrounded_flirt(message):
    result = evaluate_brain(
        brain(customer=profile(), commerce_signal=signal(), eligible=offering()),
        {"latest_message": message},
    )
    assert result.decision is not CustomerSalesDecisionType.PRESENT_OFFER
    assert result.recommended_offering_id is None
    receptiveness = result.decision_metadata["commercialReceptiveness"]
    assert receptiveness["freshDirectIntentDetected"] is False
    assert receptiveness["acceptanceGrounded"] is False

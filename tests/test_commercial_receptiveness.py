from app.models.commercial_receptiveness import CommercialReceptivenessState
from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)


def evaluate(message, *, recent=False, cooldown=False, readiness=None,
             active_offer=False):
    service = CommercialReceptivenessService(
        ConversationalSalesProgressionService().has_direct_purchase_intent
    )
    return service.evaluate(
        context={"latest_message": message}, recent_purchase=recent,
        cooldown_active=cooldown, readiness=readiness,
        active_offer=active_offer,
    )


def test_cold_turn_has_no_continuation_authority():
    result = evaluate("How was your day?")
    assert result.state is CommercialReceptivenessState.COLD
    assert result.another_sale_appropriate_now is False


def test_recent_purchase_plus_another_is_hot_and_overrides_default_cooldown():
    result = evaluate("send me another", recent=True, cooldown=True)
    assert result.state is CommercialReceptivenessState.HOT
    assert result.fresh_direct_intent is True
    assert result.recent_purchase is True
    assert result.another_sale_appropriate_now is True
    assert result.reason == "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN"


def test_recent_purchase_plus_positive_reaction_is_hot_but_not_forced_offer():
    result = evaluate("damn that was so hot", recent=True, cooldown=True)
    assert result.state is CommercialReceptivenessState.HOT
    assert result.continuation_eligible is True
    assert result.another_sale_appropriate_now is False


def test_recent_purchase_plus_subject_change_is_cooling():
    result = evaluate("thanks, anyway I'm heading to work", recent=True,
                      cooldown=True)
    assert result.state is CommercialReceptivenessState.COOLING
    assert result.another_sale_appropriate_now is False


def test_rejection_takes_precedence_over_purchase():
    result = evaluate("no thanks, maybe later", recent=True, cooldown=True)
    assert result.state is CommercialReceptivenessState.BACK_OFF
    assert result.continuation_eligible is False


def test_classifier_evidence_uses_same_canonical_projection():
    result = evaluate("okay", recent=True, cooldown=True, readiness={
        "engagement_level": "high", "escalation_ready": True,
    })
    assert result.state is CommercialReceptivenessState.HOT
    assert "STRONG_POSITIVE_ENGAGEMENT" in result.positive_evidence


def test_price_request_is_direct_only_as_active_offer_continuation():
    result = evaluate("how much is it?", active_offer=True)
    assert result.fresh_direct_intent is True
    assert CommercialReceptivenessService.active_offer_continuation_type(
        "how much is it?"
    ) == "PRICE_REQUEST"


def test_send_link_request_is_active_offer_continuation():
    result = evaluate("yeah, send me the link", active_offer=True)
    assert result.fresh_direct_intent is True
    assert CommercialReceptivenessService.active_offer_continuation_type(
        "yeah, send me the link"
    ) == "SEND_OR_LINK_REQUEST"


def test_durable_deferred_continuation_reopens_direct_intent_once_ready():
    service = CommercialReceptivenessService(
        ConversationalSalesProgressionService().has_direct_purchase_intent
    )
    result = service.evaluate(
        context={
            "latest_message": "okay",
            "deferred_continuation": {"state": "READY"},
        },
        recent_purchase=True, cooldown_active=True,
    )
    assert result.state is CommercialReceptivenessState.HOT
    assert result.fresh_direct_intent is True
    assert result.another_sale_appropriate_now is True


def test_explicit_continuation_detector_does_not_promote_praise():
    assert CommercialReceptivenessService.explicit_continuation_detected(
        "send another"
    ) is True
    assert CommercialReceptivenessService.explicit_continuation_detected(
        "that was so hot"
    ) is False


def test_pre_purchase_commercial_curiosity_is_not_direct_buying_intent():
    result = evaluate("okay I'm curious, tell me a little more")

    assert result.commercial_interest_type == "COMMERCIAL_CURIOSITY"
    assert result.fresh_direct_intent is False
    assert result.another_sale_appropriate_now is False
    assert result.state is CommercialReceptivenessState.WARM


def test_model_readiness_cannot_promote_canonical_curiosity_to_direct_intent():
    initial = evaluate("what were you teasing?").to_mapping()
    refined = CommercialReceptivenessService.refine_projection(initial, {
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "classifier_close_ready": True,
        "recommended_conversational_action": "PRESENT_OFFER",
    })

    assert refined["commercialInterestType"] == "COMMERCIAL_CURIOSITY"
    assert refined["freshDirectIntentDetected"] is False
    assert refined["anotherSaleAppropriateNow"] is False


def test_post_purchase_explicit_continuation_keeps_hot_buyer_authority():
    result = evaluate("tell me a little more", recent=True, cooldown=True)

    assert result.commercial_interest_type == "COMMERCIAL_CURIOSITY"
    assert result.fresh_direct_intent is True
    assert result.another_sale_appropriate_now is True

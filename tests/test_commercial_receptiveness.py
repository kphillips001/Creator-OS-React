import pytest

from app.models.commercial_receptiveness import CommercialReceptivenessState
from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)


def test_active_session_continuation_phrase_is_detected_semantically():
    assert CommercialReceptivenessService.explicit_continuation_detected(
        "yeah, keep the session going"
    ) is True


def evaluate(message, *, recent=False, cooldown=False, readiness=None,
             active_offer=False, classifier=None):
    service = CommercialReceptivenessService(
        ConversationalSalesProgressionService().has_direct_purchase_intent
    )
    return service.evaluate(
        context={"latest_message": message, "classifier_result": classifier or {}}, recent_purchase=recent,
        cooldown_active=cooldown, readiness=readiness,
        active_offer=active_offer,
    )


def test_primary_classifier_blocks_sexual_desire_from_becoming_buying_intent():
    result = evaluate(
        "I want to squeeze you because you're so hot",
        classifier={"buying_intent": False, "monetization_intent": False,
                    "purchase_language_present": False,
                    "sexual_engagement": True,
                    "explicit_without_buying_intent": True},
    )
    assert result.fresh_direct_intent is False
    assert result.commercial_referent_type == "NONE"
    assert "FRESH_DIRECT_BUYING_INTENT" not in result.positive_evidence
    assert result.state is not CommercialReceptivenessState.HOT


@pytest.mark.parametrize("message", [
    "what private content do you have?", "how much is that set?",
    "how do I unlock it?", "I want to buy that set",
])
def test_authoritative_commercial_language_survives_classifier_negative(message):
    result = evaluate(message, classifier={
        "buying_intent": False, "monetization_intent": False,
        "purchase_language_present": False,
    })
    assert result.fresh_direct_intent is True
    assert result.commercial_referent_type != "NONE"


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


@pytest.mark.parametrize("message,expected_type", [
    ("send the link", "SEND_OR_LINK_REQUEST"),
    ("I'm looking to buy something", "DIRECT_CONTENT_INTENT"),
    ("show me another one", "SEND_OR_LINK_REQUEST"),
])
def test_positive_commercial_predicates_remain_actionable(message, expected_type):
    result = evaluate(message, active_offer=True)
    assert result.commercial_interest_type == expected_type
    assert result.fresh_direct_intent is True


@pytest.mark.parametrize("message,boundary_type", [
    ("don't send the link", "NO_LINK_BOUNDARY"),
    ("no, don't send another link", "NO_LINK_BOUNDARY"),
    ("I'm not looking to buy anything tonight", "CURRENT_NO_BUY_BOUNDARY"),
    ("don't show me another one", "CURRENT_NO_BUY_BOUNDARY"),
    ("I'll reach out if I'm interested again", "DEFERRED_SELF_REACTIVATION"),
])
def test_negative_commercial_polarity_precedes_positive_predicates(
        message, boundary_type):
    result = evaluate(message, active_offer=True, readiness={
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "recommended_conversational_action": "BACK_OFF",
    })
    assert CommercialReceptivenessService.commercial_boundary_type(
        message
    ) == boundary_type
    assert result.commercial_interest_type == "NONE"
    assert result.fresh_direct_intent is False
    assert result.state is CommercialReceptivenessState.BACK_OFF
    assert result.another_sale_appropriate_now is False
    assert ConversationalSalesProgressionService.transition_features(message)[
        "content_request"
    ] is False


def test_negative_boundary_survives_provider_projection_without_positive_evidence():
    initial = evaluate("no, don't send another link", active_offer=True).to_mapping()
    refined = CommercialReceptivenessService.refine_projection(initial, {
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "recommended_conversational_action": "BACK_OFF",
    })
    assert refined["commercialInterestType"] == "NONE"
    assert refined["freshDirectIntentDetected"] is False
    assert refined["state"] == "BACK_OFF"
    assert "FRESH_DIRECT_BUYING_INTENT" not in refined["positiveEvidence"]


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


@pytest.mark.parametrize("message", [
    "okay, what private content do you actually have available?",
    "what private content do you have?",
    "what content do you have available?",
    "what do you have for sale?",
    "what can I buy?",
    "what are you selling?",
    "what paid content do you have?",
    "what bundles do you have?",
    "what can I unlock?",
    "what do you have available right now?",
])
def test_current_offering_availability_inquiries_are_direct_commercial_interest(message):
    result = evaluate(message)

    assert result.commercial_interest_type == "OFFERING_AVAILABILITY_INQUIRY"
    assert result.fresh_direct_intent is True
    assert result.state is CommercialReceptivenessState.HOT
    assert result.another_sale_appropriate_now is True


@pytest.mark.parametrize("message", [
    "you probably sell content to everyone",
    "I don't buy content",
    "your content is probably expensive",
    "maybe someday I'll buy something",
    "I saw you talking about private content",
    "last month I asked what content you have available, but I'm not buying",
])
def test_noncurrent_content_mentions_do_not_become_availability_inquiries(message):
    result = evaluate(message)

    assert result.commercial_interest_type != "OFFERING_AVAILABILITY_INQUIRY"
    assert result.fresh_direct_intent is False


@pytest.mark.parametrize("message,qualifier", [
    ("maybe show me something another time", "ANOTHER_TIME"),
    ("show me something later", "LATER"),
    ("send the link tomorrow", "FUTURE_DAY"),
    ("maybe I'll buy later", "LATER"),
    ("not tonight, maybe show me another time", "ANOTHER_TIME"),
    ("I'll ask you later", "LATER"),
    ("maybe when I'm less tired", "FUTURE_DAY"),
    ("next time", "FUTURE_DAY"),
])
def test_temporal_deferment_precedes_positive_commercial_predicates(
    message, qualifier,
):
    result = evaluate(message, recent=True, cooldown=True, readiness={
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "classifier_close_ready": True,
        "recommended_conversational_action": "PRESENT_OFFER",
    }, active_offer=True)
    mapping = dict(result.to_mapping())

    assert result.state is CommercialReceptivenessState.COOLING
    assert result.fresh_direct_intent is False
    assert result.another_sale_appropriate_now is False
    assert mapping["deferredCommercialInterest"] is True
    assert mapping["deferredInterestReason"] == "CUSTOMER_SPECIFIED_FUTURE_TIMING"
    assert mapping["currentCommercialInterest"] is False
    assert mapping["futureCommercialReentryAllowed"] is True
    assert mapping["temporalCommercialQualifier"] == qualifier
    assert ConversationalSalesProgressionService().has_direct_purchase_intent(message) is False
    assert ConversationalSalesProgressionService.transition_features(message)[
        "content_request"
    ] is False
    assert CommercialReceptivenessService.active_offer_continuation_type(message) is None


@pytest.mark.parametrize("message", (
    "show me something",
    "send the link",
    "show me another one",
))
def test_current_actionable_commercial_language_remains_current(message):
    result = evaluate(message, active_offer=True)
    assert result.fresh_direct_intent is True
    assert result.state is CommercialReceptivenessState.HOT
    assert result.deferred_commercial_interest is False


def test_provider_readiness_cannot_repromote_deferred_interest():
    initial = dict(evaluate(
        "maybe show me something another time", recent=True, cooldown=True,
    ).to_mapping())
    refined = CommercialReceptivenessService.refine_projection(initial, {
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "classifier_close_ready": True,
        "recommended_conversational_action": "PRESENT_OFFER",
    })

    assert refined["state"] == "COOLING"
    assert refined["freshDirectIntentDetected"] is False
    assert refined["anotherSaleAppropriateNow"] is False
    assert refined["futureCommercialReentryAllowed"] is True


@pytest.mark.parametrize("message,qualifier", [
    ("maybe I'll see what you've made when I'm ready", "FUTURE_DAY"),
    ("I'll see what you've made when I'm ready", "FUTURE_DAY"),
    ("maybe I'll look when I feel ready", "FUTURE_DAY"),
    ("I'll check out your new stuff once I'm ready", "FUTURE_DAY"),
    ("when I'm in the mood to buy, I'll ask", "FUTURE_DAY"),
    ("I'll buy again when I'm actually in the mood", "FUTURE_DAY"),
    ("show me something another time", "ANOTHER_TIME"),
    ("maybe tomorrow", "FUTURE_DAY"),
])
def test_customer_controlled_readiness_is_deferred_not_current(message, qualifier):
    result = evaluate(message, recent=True, cooldown=True, readiness={
        "current_buying_intent": True,
        "classifier_buying_intent": True,
        "classifier_close_ready": True,
        "recommended_conversational_action": "PRESENT_OFFER",
    }, active_offer=True)
    mapping = result.to_mapping()

    assert result.state is CommercialReceptivenessState.COOLING
    assert mapping["deferredCommercialInterest"] is True
    assert mapping["temporalCommercialQualifier"] == qualifier
    assert mapping["deferredInterestReason"] == "CUSTOMER_SPECIFIED_FUTURE_TIMING"
    assert mapping["currentCommercialInterest"] is False
    assert mapping["freshDirectIntentDetected"] is False
    assert mapping["anotherSaleAppropriateNow"] is False
    assert CommercialReceptivenessService.active_offer_continuation_type(message) is None
    assert ConversationalSalesProgressionService().has_direct_purchase_intent(message) is False


@pytest.mark.parametrize("message", [
    "show me something",
    "show me something new",
])
def test_unqualified_show_request_remains_current_after_readiness_repair(message):
    result = evaluate(message, active_offer=True)
    assert result.deferred_commercial_interest is False
    assert result.fresh_direct_intent is True
    assert result.state is CommercialReceptivenessState.HOT

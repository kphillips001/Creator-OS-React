from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_intelligence import StrategyConstraints
from app.models.commercial_objection import CommercialObjectionType
from app.models.customer_sales_decision import CustomerSalesDecisionType
from app.services.commercial_objection_service import CommercialObjectionService
from app.services.customer_sales_brain_service import CustomerSalesBrainService


@pytest.mark.parametrize("message", (
    "too expensive", "that's too much", "I can't spend that much",
    "That's more than I wanted to spend.",
    "$19 is more than I expected.",
    "$19 is a little more than I expected.",
))
def test_soft_price_resistance_authorizes_value_defense_not_downsell(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.PRICE_RESISTANCE
    assert result.current_product_scoped is True
    assert result.current_offer_authoritative is True
    assert result.consider_alternative is False
    assert result.continue_selling is True
    assert result.recovery_strategy == "VALUE_DEFENSE"
    assert result.negative_contact_authorized is True
    assert result.to_mapping()["noDynamicDiscount"] is True


@pytest.mark.parametrize("message", (
    "anything cheaper?", "do you have something for less?", "cheaper one",
))
def test_explicit_cheaper_product_request_authorizes_alternative(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.PRICE_RESISTANCE
    assert result.consider_alternative is True
    assert result.recovery_strategy == "ALTERNATIVE_PRODUCT"


@pytest.mark.parametrize("message", (
    "send me the cheaper one",
    "give me the cheaper option",
    "I'll take the smaller one",
    "send me the $9 one",
))
def test_known_active_offer_reference_precedes_cheaper_objection(message):
    result = CommercialObjectionService().evaluate(
        message=message,
        context={"active_offer_continuation": {
            "customerInitiatedOfferContinuation": True,
            "continuationIntentType": "SEND_OR_LINK_REQUEST",
        }},
    )
    assert result.objection_type is CommercialObjectionType.NONE
    assert result.consider_alternative is False
    assert result.selector_constraints.get("maximumPriceMinor") is None


@pytest.mark.parametrize("message", (
    "anything cheaper than that?",
    "something even cheaper?",
    "anything under $9?",
    "that's still too expensive",
))
def test_fresh_comparative_request_is_not_treated_as_known_offer_reference(message):
    from app.services.commercial_receptiveness_service import (
        CommercialReceptivenessService,
    )

    assert CommercialReceptivenessService.active_offer_continuation_type(
        message
    ) is None
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type in {
        CommercialObjectionType.PRICE_RESISTANCE,
        CommercialObjectionType.BUDGET_LIMIT,
    }
    if "still too expensive" not in message:
        assert result.consider_alternative is True


@pytest.mark.parametrize("message", (
    "give me a discount", "Come on, give it to me for $5", "what's your best price?",
))
def test_discount_fishing_holds_original_price(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.DISCOUNT_REQUEST
    assert result.current_offer_authoritative is True
    assert result.consider_alternative is False
    assert result.recovery_strategy == "VALUE_DEFENSE"


@pytest.mark.parametrize("message,minor", (
    ("I only have $5", 500),
    ("I can't spend more than $5 tonight", 500),
    ("Do you have anything around $4.50?", 450),
    ("I'm trying to stay under ten dollars", 1000),
    ("I only have about $8 to spend", 800),
    ("my budget is $10", 1000),
    ("anything under $10?", 1000),
    ("I need something cheaper, like under ten", 1000),
))
def test_explicit_budget_is_authoritative_for_different_product(message, minor):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.BUDGET_LIMIT
    assert result.budget_constraint_minor == minor
    assert result.consider_alternative is True


@pytest.mark.parametrize("message", (
    "not really into that", "got something else?", "anything different?",
    "I don't like that kind", "not that one", "anything hotter?",
    "do you have something more teasing?",
))
def test_content_mismatch_preserves_receptiveness(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.CONTENT_MISMATCH
    assert result.current_offer_authoritative is False
    assert result.consider_alternative is True


def test_temporary_hesitation_retains_offer_without_replacement():
    result = CommercialObjectionService().evaluate(
        message="let me think about buying it"
    )
    assert result.objection_type is CommercialObjectionType.TEMPORARY_HESITATION
    assert result.current_offer_authoritative is True
    assert result.consider_alternative is False


@pytest.mark.parametrize("message", (
    "maybe later on that offer",
    "not right now, maybe I'll unlock it later",
))
def test_future_timing_is_deferred_interest_not_an_objection(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.NONE
    assert result.continue_selling is False
    assert result.consider_alternative is False
    assert result.evidence == ("DEFERRED_FUTURE_COMMERCIAL_INTEREST",)


@pytest.mark.parametrize("message", ("maybe later", "let me think", "not right now"))
def test_noncommercial_hesitation_does_not_invent_a_sales_objection(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.NONE


@pytest.mark.parametrize("message", ("no", "stop asking", "I'm not buying anything", "not interested"))
def test_global_decline_suppresses_selling(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.GLOBAL_DECLINE
    assert result.continue_selling is False
    assert result.consider_alternative is False


@pytest.mark.parametrize("message", ("the link doesn't work", "payment failed", "checkout is broken"))
def test_payment_issue_preserves_offer_authority(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is CommercialObjectionType.PAYMENT_TECHNICAL
    assert result.current_offer_authoritative is True
    assert result.consider_alternative is False


def test_repeated_unchanged_objection_after_recovery_is_bounded():
    context = {"sales_progression": {"recoveryAttemptCount": 1}}
    result = CommercialObjectionService().evaluate(
        message="still too much", context=context,
    )
    assert result.consider_alternative is False
    assert result.continue_selling is False


def test_new_cheaper_product_request_after_value_defense_is_still_processed():
    context = {"sales_progression": {
        "recoveryAttemptCount": 1,
        "reasonCode": "OBJECTION_VALUE_DEFENSE",
    }}
    result = CommercialObjectionService().evaluate(
        message="anything cheaper?", context=context,
    )
    assert result.consider_alternative is True
    assert result.recovery_strategy == "ALTERNATIVE_PRODUCT"


@pytest.mark.parametrize("message", (
    "I spent under $10 last time",
    "maybe someday I'll only spend ten dollars",
    "I'm not saying my budget is $10",
    "We were talking about a $10 price yesterday",
))
def test_noncurrent_money_references_are_not_budget_constraints(message):
    result = CommercialObjectionService().evaluate(message=message)
    assert result.objection_type is not CommercialObjectionType.BUDGET_LIMIT
    assert result.budget_constraint_minor is None


def test_explicit_cheaper_request_excludes_current_and_requires_material_reduction():
    current = uuid4()
    objection = CommercialObjectionService().evaluate(message="anything cheaper?")
    constraints = CustomerSalesBrainService._recovery_constraints(
        objection,
        SimpleNamespace(commercial_offering_id=current, expected_price_minor=1000),
        base=StrategyConstraints(),
    )
    assert constraints.excluded_offering_ids == (current,)
    assert constraints.maximum_price_minor == 900


def test_minimum_price_offer_has_no_fake_lower_recovery():
    objection = CommercialObjectionService().evaluate(message="anything cheaper?")
    constraints = CustomerSalesBrainService._recovery_constraints(
        objection,
        SimpleNamespace(commercial_offering_id=uuid4(), expected_price_minor=300),
    )
    assert constraints.maximum_price_minor == 299


def test_post_purchase_bundle_can_be_canonical_upsell():
    result = CustomerSalesBrainService._next_offer_kind(
        objection=CommercialObjectionService().evaluate(message="what else?"),
        latest=SimpleNamespace(status=SimpleNamespace(value="PURCHASED"),
                               expected_price_minor=500),
        selection=SimpleNamespace(price_minor=1200, offering_type="BUNDLE"),
        receptiveness=SimpleNamespace(fresh_direct_intent=True),
    )
    assert result is CustomerSalesDecisionType.UPSELL


def test_price_sensitive_post_purchase_never_upsells():
    result = CustomerSalesBrainService._next_offer_kind(
        objection=CommercialObjectionService().evaluate(message="anything cheaper?"),
        latest=SimpleNamespace(status=SimpleNamespace(value="PURCHASED"),
                               expected_price_minor=500),
        selection=SimpleNamespace(price_minor=1200, offering_type="BUNDLE"),
        receptiveness=SimpleNamespace(fresh_direct_intent=True),
    )
    assert result is CustomerSalesDecisionType.CROSS_SELL


def test_post_purchase_different_relevant_offer_can_cross_sell():
    result = CustomerSalesBrainService._next_offer_kind(
        objection=CommercialObjectionService().evaluate(message="what else?"),
        latest=SimpleNamespace(status=SimpleNamespace(value="PURCHASED"),
                               expected_price_minor=900),
        selection=SimpleNamespace(price_minor=700, offering_type="SINGLE_IMAGE"),
        receptiveness=SimpleNamespace(fresh_direct_intent=True),
    )
    assert result is CustomerSalesDecisionType.CROSS_SELL

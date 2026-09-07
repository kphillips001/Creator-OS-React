import pytest

from app.testing.session5_scenario_runner import Session5ScenarioRunner


def presented(intent="pi-9", offering="offer-9"):
    return {
        "customer": "I'm trying to stay under ten dollars",
        "syntheticPpvPresentation": {
            "offeringId": offering,
            "purchaseIntent": {"id": intent, "state": "PRESENTED"},
        },
        "salesBrainFullAnalysis": {},
    }


def c10_acceptance(
    intent="pi-9", offering="offer-9", *, confirmed=True,
    resolved=True, continuation_type="SEND_OR_LINK_REQUEST",
):
    active_intent = intent if resolved else None
    active_offering = offering if resolved else None
    return {
        "customer": "send me the cheaper one",
        "syntheticPpvPresentation": {
            "offeringId": offering,
            "purchaseIntent": {"id": intent, "state": "PRESENTED"},
        },
        "salesBrainFullAnalysis": {
            "currentOffer": {
                "customerInitiatedOfferContinuation": resolved,
                "continuationIntentType": continuation_type,
                "reuseRequested": resolved,
                "redeliveryAuthorized": resolved,
                "purchaseIntentReuseEligible": resolved,
                "structuredOfferReused": confirmed and resolved,
                "structuredOfferRedelivered": confirmed and resolved,
                "purchaseIntentReused": confirmed and resolved,
                "activePurchaseIntentId": active_intent,
                "activeOfferingId": active_offering,
            },
            "purchaseCommerceState": {
                "activePurchaseIntentId": active_intent,
                "purchaseIntentStatus": "PRESENTED",
            },
            "commerceLifecycleConfirmation": {
                "structuredPresentationConfirmed": confirmed,
                "deliveryState": "CONFIRMED" if confirmed else None,
            },
        },
    }


def eligibility(turns, intent="pi-9", state="PRESENTED"):
    return Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C10",
        turns=turns,
        purchase_intent_id=intent,
        purchase_intent_state=state,
    )


def test_c10_exact_known_offer_redelivery_qualifies_for_synthetic_settlement():
    result = eligibility([presented(), c10_acceptance()])
    assert result["simulatePurchaseEligible"] is True
    assert result["scenarioPurchaseAcceptanceObserved"] is True
    assert result["purchaseEmulatorTargetIntent"] == "pi-9"
    assert result["authoritativePresentedPurchaseIntent"] == "pi-9"
    assert result["scenarioPurchaseAcceptanceSource"] == (
        "C10_CANONICAL_EXACT_OFFER_CONTINUATION"
    )


def test_c10_acceptance_cannot_settle_a_different_presented_intent():
    result = eligibility(
        [presented("pi-29", "offer-29"), c10_acceptance()],
        intent="pi-29",
    )
    assert result["simulatePurchaseEligible"] is False


@pytest.mark.parametrize("turn", (
    c10_acceptance(confirmed=False),
    c10_acceptance(resolved=False),
    c10_acceptance(continuation_type="PRICE_REQUEST"),
))
def test_c10_unconfirmed_ambiguous_or_generic_reference_is_rejected(turn):
    result = eligibility([presented(), turn])
    assert result["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligibilityReason"] == (
        "CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"
    )


@pytest.mark.parametrize("state", (
    "ABANDONED", "EXPIRED", "SUPERSEDED", "ADMIN_CLOSED", "PURCHASED",
))
def test_c10_terminal_intent_is_never_eligible(state):
    result = eligibility([presented(), c10_acceptance()], state=state)
    assert result["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligibilityReason"] == (
        "TARGET_PURCHASE_INTENT_NOT_PRESENTED"
    )


def test_adaptive_offer_reaction_acceptance_remains_supported():
    acceptance = {
        "customer": "yes",
        "adaptiveCustomer": {
            "behavioral_phase": "OFFER_REACTION",
            "authoritative_offer_context": {"purchaseIntentId": "pi-9"},
            "validation_result": {"derivedSignals": {"offerAcceptance": True}},
        },
        "salesBrainFullAnalysis": {},
    }
    result = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06",
        turns=[presented(), acceptance],
        purchase_intent_id="pi-9",
        purchase_intent_state="PRESENTED",
    )
    assert result["simulatePurchaseEligible"] is True
    assert result["scenarioPurchaseAcceptanceSource"] == (
        "ADAPTIVE_OFFER_REACTION_ACCEPT"
    )

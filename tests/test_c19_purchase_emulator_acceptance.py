from copy import deepcopy

import pytest

from app.testing.session5_scenario_harness import CanonicalScenarioEvent
from app.testing.session5_scenario_runner import Session5ScenarioRunner


INTENT = "00000000-0000-0000-0000-000000000019"
OFFERING = "00000000-0000-0000-0000-000000000119"
SESSION = "00000000-0000-0000-0000-000000000219"


def event():
    return CanonicalScenarioEvent(
        "C19_SESSION_STEP_SETTLEMENT",
        "SYNTHETIC_PROVIDER_SETTLEMENT",
        6,
        presentation_authority_types=("SEND_OR_LINK_REQUEST",),
        expected_session_position=2,
        expected_foundation_reference="certification-C19",
    )


def authoritative_turn():
    return {
        "logicalTurn": 6,
        "turnNumber": None,
        "turnAttempt": 1,
        "status": "CURRENT",
        "customer": "send that one",
        "customerValue": {"commercialInterestType": "SEND_OR_LINK_REQUEST"},
        "syntheticPpvPresentation": {
            "offeringId": OFFERING,
            "priceMinor": 900,
            "currency": "USD",
            "purchaseIntent": {"id": INTENT, "state": "PRESENTED"},
        },
        "fullAnalysis": {
            "activeSession": {"active": True, "sessionId": SESSION},
            "inventorySelection": {
                "selectedOfferingId": OFFERING,
                "selectedPriceMinor": 900,
                "activeSessionAuthority": True,
            },
            "commerceLifecycleConfirmation": {
                "purchaseIntentId": INTENT,
                "purchaseIntentState": "PRESENTED",
                "structuredPresentationConfirmed": True,
                "deliveryState": "CONFIRMED",
                "provider": "SYNTHETIC_TEST_TRANSPORT",
            },
            "activeSessionContext": {
                "available": True,
                "completeness": "POSITIONAL_CONTEXT_COMPLETE",
                "salesSessionId": SESSION,
                "foundationReference": "certification-C19",
                "orderedAssets": [{
                    "position": 2,
                    "assetId": 2726,
                    "offeringId": OFFERING,
                    "priceMinor": 900,
                    "currency": "USD",
                    "owned": False,
                }],
            },
        },
    }


def eligibility(*, turns=None, canonical_event=None, **overrides):
    values = {
        "scenario_id": "C19",
        "turns": turns if turns is not None else [authoritative_turn()],
        "purchase_intent_id": INTENT,
        "purchase_intent_state": "PRESENTED",
        "purchase_intent_offering_id": OFFERING,
        "expected_price_minor": 900,
        "expected_currency": "USD",
        "presented_intent_count": 1,
        "target_already_owned": False,
        "prior_provider_settlement": False,
        "canonical_event": canonical_event,
    }
    values.update(overrides)
    return Session5ScenarioRunner.purchase_emulator_eligibility(**values)


def test_declared_c19_event_accepts_exact_confirmed_send_request_presentation():
    result = eligibility(canonical_event=event())
    assert result["simulatePurchaseEligible"] is True
    assert result["scenarioPurchaseAcceptanceObserved"] is True
    assert result["scenarioPurchaseAcceptanceSource"] == (
        "DECLARED_EVENT_WITH_EXACT_PRESENTATION_AUTHORITY"
    )
    assert all(result["canonicalEventChecks"].values())
    assert result["customerPresentationAuthority"] == (
        "CUSTOMER_AUTHORIZED_STRUCTURED_PRESENTATION"
    )
    assert result["providerSettlementAuthority"] == (
        "SCENARIO_LAB_EMULATED_PROVIDER_EVENT"
    )


def test_retried_current_logical_turn_satisfies_sequence_after_failed_precommit():
    failed = deepcopy(authoritative_turn())
    failed.update(status="FAILED_PRE_COMMIT", turnAttempt=1)
    committed = deepcopy(authoritative_turn())
    committed["turnAttempt"] = 2
    result = eligibility(
        turns=[failed, committed], canonical_event=event(),
    )
    assert result["simulatePurchaseEligible"] is True
    assert result["canonicalEventChecks"][
        "sequencedAfterAuthorizingTurn"
    ] is True


@pytest.mark.parametrize("turn", [
    {**authoritative_turn(), "logicalTurn": 5},
    {**authoritative_turn(), "status": "FAILED_PRE_COMMIT"},
])
def test_uncommitted_or_partial_turn_six_does_not_satisfy_sequence(turn):
    result = eligibility(turns=[turn], canonical_event=event())
    assert result["simulatePurchaseEligible"] is False
    assert result["canonicalEventChecks"][
        "sequencedAfterAuthorizingTurn"
    ] is False


def test_later_turn_cannot_substitute_for_missing_authorizing_turn():
    turn = deepcopy(authoritative_turn())
    turn["logicalTurn"] = 7
    result = eligibility(turns=[turn], canonical_event=event())
    assert result["simulatePurchaseEligible"] is False
    assert result["canonicalEventChecks"][
        "sequencedAfterAuthorizingTurn"
    ] is False


def test_attempt_number_never_replaces_logical_turn_identity():
    turn = authoritative_turn()
    turn.update(scenarioAttempt=2, turnAttempt=7)
    assert Session5ScenarioRunner._committed_logical_turn(turn) == 6


def test_legacy_turn_number_remains_a_compatibility_fallback():
    turn = authoritative_turn()
    turn.pop("logicalTurn")
    turn["turnNumber"] = 6
    assert Session5ScenarioRunner._committed_logical_turn(turn) == 6


def test_zero_or_missing_turn_identity_is_not_a_committed_script_turn():
    assert Session5ScenarioRunner._committed_logical_turn({
        "logicalTurn": 0, "status": "CURRENT",
    }) is None
    assert Session5ScenarioRunner._committed_logical_turn({
        "status": "CURRENT",
    }) is None


@pytest.mark.parametrize(("scenario_id", "after_turn"), [
    ("C10", 7),
    ("C13", 6),
    ("C16", 6),
])
def test_existing_non_session_settlement_event_sequence_remains_valid(
        scenario_id, after_turn):
    turn = deepcopy(authoritative_turn())
    turn["logicalTurn"] = after_turn
    turn["fullAnalysis"].pop("activeSession", None)
    turn["fullAnalysis"].pop("activeSessionContext", None)
    declared = CanonicalScenarioEvent(
        f"{scenario_id}_SETTLEMENT",
        "SYNTHETIC_PROVIDER_SETTLEMENT",
        after_turn,
    )
    result = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id=scenario_id,
        turns=[turn],
        purchase_intent_id=INTENT,
        purchase_intent_state="PRESENTED",
        purchase_intent_offering_id=OFFERING,
        expected_price_minor=900,
        expected_currency="USD",
        presented_intent_count=1,
        canonical_event=declared,
    )
    assert result["simulatePurchaseEligible"] is True
    assert result["canonicalEventChecks"][
        "sequencedAfterAuthorizingTurn"
    ] is True


def test_full_analysis_progress_and_event_sequence_use_same_committed_identity():
    turns = [
        {"logicalTurn": number, "turnAttempt": 1, "status": "CURRENT"}
        for number in range(1, 7)
    ]
    assert Session5ScenarioRunner._last_completed_logical_turn(turns) == 6
    assert Session5ScenarioRunner._committed_logical_turn(turns[-1]) == 6


def test_send_request_without_declared_event_does_not_create_purchase_authority():
    result = eligibility()
    assert result["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligibilityReason"] == (
        "CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"
    )


def test_declared_event_without_presentation_is_blocked():
    result = eligibility(turns=[{
        "turnNumber": 6,
        "customer": "send that one",
        "customerValue": {"commercialInterestType": "SEND_OR_LINK_REQUEST"},
    }], canonical_event=event())
    assert result["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligibilityReason"] == (
        "AUTHORITATIVE_STRUCTURED_PRESENTATION_MISSING"
    )


@pytest.mark.parametrize(("mutation", "expected_check"), [
    (lambda turn: turn["customerValue"].update(
        commercialInterestType="NONE"), "acceptedPresentationAuthority"),
    (lambda turn: turn["fullAnalysis"]["commerceLifecycleConfirmation"].update(
        deliveryState=None), "confirmedCustomerVisibleDelivery"),
    (lambda turn: turn["syntheticPpvPresentation"]["purchaseIntent"].update(
        id="wrong-intent"), None),
    (lambda turn: turn["fullAnalysis"]["inventorySelection"].update(
        selectedOfferingId="wrong-offering"), "exactOffering"),
    (lambda turn: turn["fullAnalysis"]["activeSessionContext"].update(
        salesSessionId=None), "activeSessionBound"),
    (lambda turn: turn["fullAnalysis"]["activeSessionContext"].update(
        foundationReference="wrong-foundation"), "exactFoundation"),
    (lambda turn: turn["syntheticPpvPresentation"].update(
        priceMinor=901), "exactAmount"),
    (lambda turn: turn["syntheticPpvPresentation"].update(
        currency="EUR"), "exactCurrency"),
])
def test_declared_event_fails_closed_on_broken_binding(mutation, expected_check):
    turn = deepcopy(authoritative_turn())
    mutation(turn)
    result = eligibility(turns=[turn], canonical_event=event())
    assert result["simulatePurchaseEligible"] is False
    if expected_check is not None:
        assert result["canonicalEventChecks"][expected_check] is False


@pytest.mark.parametrize("override", [
    {"presented_intent_count": 2},
    {"target_already_owned": True},
    {"prior_provider_settlement": True},
    {"purchase_intent_state": "CREATED"},
])
def test_declared_event_rejects_ambiguous_or_nonsettleable_intent(override):
    assert eligibility(canonical_event=event(), **override)[
        "simulatePurchaseEligible"
    ] is False


def test_boolean_event_flag_alone_cannot_fabricate_settlement_authority():
    result = eligibility(canonical_event_authorized=True)
    assert result["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligibilityReason"] == (
        "CANONICAL_EVENT_DECLARATION_REQUIRED"
    )

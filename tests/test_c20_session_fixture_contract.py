import inspect
from copy import deepcopy

import pytest

from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    HistoricalPurchaseFixtureBuilder,
)
from app.testing.session5_scenario_runner import Session5ScenarioRunner


INTENT = "00000000-0000-0000-0000-000000000020"
OFFERING = "00000000-0000-0000-0000-000000000120"


def test_regression_old_session_position_cannot_index_three_paid_items():
    paid = ("paid-0", "paid-1", "paid-2")
    session_position_for_second_paid_step = 3
    with pytest.raises(IndexError, match="tuple index out of range"):
        _ = paid[session_position_for_second_paid_step]


def _turn(*, logical_turn=5, position=2, price=900,
          authority="SEND_OR_LINK_REQUEST"):
    return {
        "logicalTurn": logical_turn,
        "status": "CURRENT",
        "customerValue": {"commercialInterestType": authority},
        "syntheticPpvPresentation": {
            "offeringId": OFFERING,
            "priceMinor": price,
            "currency": "USD",
            "sessionFoundationReference": "certification-C20",
            "sessionPosition": position,
            "purchaseIntent": {"id": INTENT, "state": "PRESENTED"},
        },
        "fullAnalysis": {
            "inventorySelection": {"selectedOfferingId": OFFERING},
            "commerceLifecycleConfirmation": {
                "purchaseIntentId": INTENT,
                "structuredPresentationConfirmed": True,
                "deliveryState": "CONFIRMED",
            },
            "activeSession": {
                "active": position == 4,
                "sessionId": "session-C20" if position == 4 else None,
            },
            "activeSessionContext": ({
                "available": True,
                "completeness": "POSITIONAL_CONTEXT_COMPLETE",
                "salesSessionId": "session-C20",
                "foundationReference": "certification-C20",
                "sessionRuntime": {
                    "currentPosition": 4,
                    "currentSalesRole": "FINALE",
                    "lifecycleId": "lifecycle-C20",
                },
            } if position == 4 else {"available": False}),
        },
    }


def _eligibility(event, turn, *, prior=False, owned=False, **overrides):
    values = {
        "scenario_id": "C20",
        "turns": [turn],
        "purchase_intent_id": INTENT,
        "purchase_intent_state": "PRESENTED",
        "purchase_intent_offering_id": OFFERING,
        "expected_price_minor": turn["syntheticPpvPresentation"]["priceMinor"],
        "expected_currency": "USD",
        "presented_intent_count": 1,
        "target_already_owned": owned,
        "prior_provider_settlement": prior,
        "canonical_event": event,
    }
    values.update(overrides)
    return Session5ScenarioRunner.purchase_emulator_eligibility(
        **values,
    )


def test_c20_prepare_builds_graph_without_precreating_customer_session():
    prepare = inspect.getsource(Session5ScenarioRunner._prepare_with_slot)
    fixture = inspect.getsource(
        HistoricalPurchaseFixtureBuilder.prepare_c20_session_compatible_inventory
    )
    shared = inspect.getsource(
        HistoricalPurchaseFixtureBuilder.prepare_session_compatible_inventory
    )
    planner = inspect.getsource(
        HistoricalPurchaseFixtureBuilder._session_fixture_step_plan
    )

    assert 'scenario_id == "C20"' in prepare
    assert "prepare_c20_session_compatible_inventory" in prepare
    assert 'session_reference="certification-C20"' in fixture
    assert "include_free_teaser=True" in fixture
    assert "SalesSession" not in fixture
    assert '"FREE_TEASER"' in planner
    assert '"FIRST_UNLOCK"' in planner
    assert '"ESCALATION"' in planner
    assert '"FINALE"' in planner
    assert "VALUES (%s,'TEASER')" in shared


def test_explicit_step_plan_separates_session_positions_from_paid_indexes():
    paid = (
        {"assetId": 20, "offeringId": "offer-1", "priceMinor": 900},
        {"assetId": 30, "offeringId": "offer-2", "priceMinor": 1900},
        {"assetId": 40, "offeringId": "offer-3", "priceMinor": 2900},
    )
    plan = HistoricalPurchaseFixtureBuilder._session_fixture_step_plan(
        paid, teaser_asset_id=10,
    )
    assert [row["position"] for row in plan] == [1, 2, 3, 4]
    assert [row["asset_id"] for row in plan] == [10, 20, 30, 40]
    assert [row["offering_id"] for row in plan] == [
        None, "offer-1", "offer-2", "offer-3",
    ]
    assert [row["price_minor"] for row in plan] == [None, 900, 1900, 2900]
    assert [row["role"] for row in plan] == [
        "FREE_TEASER", "FIRST_UNLOCK", "ESCALATION", "FINALE",
    ]
    assert [row["strategy"]["suggested_next_asset_id"] for row in plan] == [
        20, 30, 40, None,
    ]
    assert plan[-1]["strategy"]["recommended_progression"] == "COMPLETE"


def test_default_session_step_plan_preserves_existing_no_teaser_coordinates():
    paid = (
        {"assetId": 20, "offeringId": "offer-1", "priceMinor": 900},
        {"assetId": 30, "offeringId": "offer-2", "priceMinor": 1900},
        {"assetId": 40, "offeringId": "offer-3", "priceMinor": 2900},
    )
    plan = HistoricalPurchaseFixtureBuilder._session_fixture_step_plan(paid)
    assert [row["position"] for row in plan] == [1, 2, 3]
    assert [row["asset_id"] for row in plan] == [20, 30, 40]
    assert [row["strategy"]["suggested_next_asset_id"] for row in plan] == [
        30, 40, None,
    ]
    assert [row["role"] for row in plan] == [
        "PAID_PROGRESSION", "PAID_PROGRESSION", "FINALE",
    ]


def test_c20_start_validation_is_fail_closed_for_exact_graph():
    validation = inspect.getsource(CustomerScenarioHarness.validate_starting_state)
    for required in (
        "certification-C20", "FREE_TEASER", "FIRST_UNLOCK", "ESCALATION",
        "FINALE", "[None, 900, 1900, 2900]",
        "c20.activePurchaseIntent must be null",
        "c20.activeSession must be null",
        "c20.activeUnresolvedOpportunity must be false",
        "c20.suggestedNextChain",
        "c20.FINALE must terminate Session progression",
    ):
        assert required in validation


def test_c20_fixture_teaser_is_registered_for_dependency_ordered_reset():
    fixture = inspect.getsource(
        HistoricalPurchaseFixtureBuilder.prepare_session_compatible_inventory
    )
    reset = inspect.getsource(CustomerScenarioHarness.reset)
    assert 'scenario_id, "content_items", teaser_asset_id' in fixture
    assert "recorded_assets" in reset
    assert "related_session_rows" in reset
    assert "photoshoot_session_sales_strategies" in reset
    assert reset.index('delete("photoshoot_asset_memberships"') < reset.index(
        'delete("content_items"'
    )
    assert reset.index('delete("commercial_offerings"') < reset.index(
        'delete("content_items"'
    )


def test_unallocated_ready_reset_is_generic_and_attempt_evidence_guarded():
    reset = inspect.getsource(CustomerScenarioHarness.reset)
    runner_reset = inspect.getsource(Session5ScenarioRunner.reset)
    assert 'row["state"] == "READY"' in reset
    for authority in (
        "certification_scenario_attempt_allocations",
        "certification_scenario_attempts",
        "certification_scenario_turn_attempts",
        "certification_scenario_assessments",
        "certification_scenario_defects",
        "certification_scenario_snapshots",
        "certification_scenario_turn_evidence",
    ):
        assert authority in reset
    assert "UNALLOCATED_PREPARE_RESIDUE" in reset
    assert '("SNAPSHOTTED", "READY", "VERIFIED_CLEAN")' in runner_reset


def test_first_settlement_can_bind_to_photoshoot_before_sales_session_exists():
    event = CustomerScenarioHarness.definition("C20").canonical_events[0]
    result = _eligibility(event, _turn())
    assert result["simulatePurchaseEligible"] is True
    assert all(result["canonicalEventChecks"].values())


def test_c20_event_contract_fails_closed_on_position_foundation_or_replay():
    event = CustomerScenarioHarness.definition("C20").canonical_events[0]
    wrong_position = _turn(position=3)
    assert _eligibility(event, wrong_position)["canonicalEventChecks"][
        "exactOrderedStep"
    ] is False
    wrong_foundation = deepcopy(_turn())
    wrong_foundation["syntheticPpvPresentation"][
        "sessionFoundationReference"
    ] = "wrong"
    assert _eligibility(event, wrong_foundation)["canonicalEventChecks"][
        "exactFoundation"
    ] is False
    assert _eligibility(event, _turn(), prior=True)[
        "simulatePurchaseEligible"
    ] is False
    assert _eligibility(event, _turn(), owned=True)[
        "simulatePurchaseEligible"
    ] is False


def test_all_three_c20_events_bind_exact_order_price_and_authority():
    events = CustomerScenarioHarness.definition("C20").canonical_events
    rows = (
        (events[0], _turn(logical_turn=5, position=2, price=900)),
        (events[1], _turn(logical_turn=9, position=3, price=1900)),
        (events[2], _turn(
            logical_turn=12, position=4, price=2900,
            authority="SEND_OR_LINK_REQUEST",
        )),
    )
    for event, turn in rows:
        assert _eligibility(event, turn)["simulatePurchaseEligible"] is True


def test_canonical_finale_request_uses_actual_send_or_link_authority():
    assert CommercialReceptivenessService.commercial_interest_type(
        "show me the next one"
    ) == "SEND_OR_LINK_REQUEST"


def test_c20_finale_event_rejects_wrong_role_or_authority():
    event = CustomerScenarioHarness.definition("C20").canonical_events[2]
    wrong_role = _turn(logical_turn=12, position=4, price=2900)
    wrong_role["fullAnalysis"]["activeSessionContext"]["sessionRuntime"][
        "currentSalesRole"
    ] = "ESCALATION"
    result = _eligibility(event, wrong_role)
    assert result["simulatePurchaseEligible"] is False
    assert result["canonicalEventChecks"]["exactSessionRole"] is False

    wrong_authority = _turn(
        logical_turn=12, position=4, price=2900,
        authority="DIRECT_CONTENT_INTENT",
    )
    result = _eligibility(event, wrong_authority)
    assert result["simulatePurchaseEligible"] is False
    assert result["canonicalEventChecks"][
        "acceptedPresentationAuthority"
    ] is False


@pytest.mark.parametrize(("mutation", "check"), (
    (lambda turn: turn["syntheticPpvPresentation"]["purchaseIntent"].update(
        id="wrong-intent"), None),
    (lambda turn: turn["fullAnalysis"]["inventorySelection"].update(
        selectedOfferingId="wrong-offering"), "exactOffering"),
    (lambda turn: turn["fullAnalysis"]["activeSession"].update(
        sessionId="wrong-session"), "activeSessionBound"),
    (lambda turn: turn["fullAnalysis"]["activeSessionContext"].update(
        foundationReference="wrong-foundation"), "exactFoundation"),
    (lambda turn: turn["fullAnalysis"]["activeSessionContext"][
        "sessionRuntime"].update(lifecycleId=None), "lifecycleBound"),
    (lambda turn: turn["syntheticPpvPresentation"].update(
        sessionPosition=3), "exactOrderedStep"),
    (lambda turn: turn["syntheticPpvPresentation"].update(
        priceMinor=2800), "exactAmount"),
    (lambda turn: turn["syntheticPpvPresentation"].update(
        currency="EUR"), "exactCurrency"),
    (lambda turn: turn["fullAnalysis"][
        "commerceLifecycleConfirmation"].update(
            deliveryState=None), "confirmedCustomerVisibleDelivery"),
))
def test_c20_finale_event_fails_closed_on_wrong_exact_binding(mutation, check):
    event = CustomerScenarioHarness.definition("C20").canonical_events[2]
    turn = _turn(logical_turn=12, position=4, price=2900)
    mutation(turn)
    result = _eligibility(event, turn, expected_price_minor=2900)
    assert result["simulatePurchaseEligible"] is False
    if check is not None:
        assert result["canonicalEventChecks"][check] is False


@pytest.mark.parametrize("override", (
    {"turns": []},
    {"presented_intent_count": 2},
    {"target_already_owned": True},
    {"prior_provider_settlement": True},
    {"purchase_intent_state": "CREATED"},
))
def test_c20_finale_event_rejects_missing_ambiguous_or_replayed_authority(
        override):
    event = CustomerScenarioHarness.definition("C20").canonical_events[2]
    turn = _turn(logical_turn=12, position=4, price=2900)
    result = _eligibility(event, turn, **override)
    assert result["simulatePurchaseEligible"] is False

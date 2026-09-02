"""Static certification of the complete C04-C20 Scenario Lab manifest."""
from dataclasses import asdict
import inspect

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    SCENARIO_MANIFEST,
)
from app.testing.session5_scenario_runner import PURCHASE_PLANS, Session5ScenarioRunner


REMAINING = tuple(item for item in SCENARIO_MANIFEST if "C04" <= item.scenario_id <= "C20")
PURCHASE_CLAIM_SCENARIOS = {"C04", "C06", "C10", "C13", "C16", "C19", "C20"}
HISTORICAL_BUYERS = {f"C{number:02d}" for number in range(11, 20)}


def test_c04_c20_definitions_are_structurally_complete():
    assert [item.scenario_id for item in REMAINING] == [f"C{i:02d}" for i in range(4, 21)]
    for item in REMAINING:
        assert item.canonical_turn_count == len(item.canonical_customer_turns)
        if item.scenario_id == "C06":
            assert item.canonical_turn_count == 3
            assert item.maximum_turn_count == 18
        elif item.scenario_id == "C07":
            assert item.canonical_turn_count == 8
            assert item.maximum_turn_count == 14
        elif item.scenario_id == "C08":
            assert item.canonical_turn_count == 3
            assert item.maximum_turn_count == 18
        else:
            assert 6 <= item.canonical_turn_count <= 15
        assert item.completion_condition
        assert item.pre_turn_condition
        assert item.certification_objectives
        assert item.branch_checkpoints
        assert item.facts_ava_must_discover
        assert all(message.strip() == message and message for message in item.canonical_customer_turns)


def test_scenario_metadata_is_not_supplied_to_ava_runtime():
    source = inspect.getsource(CustomerScenarioHarness.execute_turn)
    forbidden_runtime_inputs = (
        "behavior_profile", "commercial_trajectory", "seeded_history",
        "certification_objectives", "branch_checkpoints", "completion_condition",
    )
    assert all(value not in source for value in forbidden_runtime_inputs)
    for item in REMAINING:
        label = item.name.lower().replace("_", " ")
        assert all(label not in message.lower() for message in item.canonical_customer_turns)


def test_purchase_claims_require_provider_emulation_and_seeded_buyers_use_truth():
    for item in REMAINING:
        if item.scenario_id in PURCHASE_CLAIM_SCENARIOS:
            assert item.purchase_emulation_requirements
            assert all("PurchaseIntent" in rule for rule in item.purchase_emulation_requirements)
    assert HISTORICAL_BUYERS == set(PURCHASE_PLANS)
    assert PURCHASE_PLANS["C11"] == [1400]
    assert PURCHASE_PLANS["C13"] == [1200, 1800]
    assert sum(PURCHASE_PLANS["C15"]) >= 15000
    assert sum(PURCHASE_PLANS["C16"]) >= 50000
    assert sum(PURCHASE_PLANS["C17"]) >= 50000


def test_time_waster_definitions_require_paid_opportunity_truth():
    for scenario_id in ("C08", "C09"):
        item = CustomerScenarioHarness.definition(scenario_id)
        completion = item.completion_condition.lower()
        assert "at least two" in completion or "two distinct" in completion
        assert "paid opportunit" in completion or "presented purchaseintent" in completion
        assert not item.seeded_history
    assert "chat volume" not in CustomerScenarioHarness.definition("C08").completion_condition.lower()
    assert "sexual language alone" in CustomerScenarioHarness.definition("C09").completion_condition.lower()


@pytest.mark.parametrize("scenario_id", sorted(HISTORICAL_BUYERS))
def test_every_verified_buyer_definition_has_retention_or_relationship_protection(scenario_id):
    item = CustomerScenarioHarness.definition(scenario_id)
    language = " ".join((*item.certification_objectives, item.completion_condition)).upper()
    assert "RETENTION" in language or "RELATIONSHIP" in language


def test_c20_preserves_session_scope_and_declares_three_provider_settlements():
    item = CustomerScenarioHarness.definition("C20")
    assert item.name == "END_TO_END_SESSION_SELLING"
    assert len(item.purchase_emulation_requirements) == 3
    assert {"SESSION_OPPORTUNITY", "TEASER", "FIRST_PAID_ITEM", "FINALE", "COMPLETION"} <= set(item.certification_objectives)
    assert {"HESITATION", "DECLINE_ONE_STEP", "SESSION_STATE_CONTINUITY", "OWNERSHIP_EXCLUSION"} <= set(item.branch_checkpoints)


@pytest.mark.parametrize("scenario_id", ("C04", "C06", "C10", "C13", "C16", "C19", "C20"))
def test_paid_scenarios_expect_structured_price_without_verbal_price(scenario_id):
    item = CustomerScenarioHarness.definition(scenario_id)
    assert "STRUCTURED_PRICE_NO_VERBAL_PRICE" in item.certification_objectives


def test_shared_execution_guards_cover_every_completed_definition():
    turn_source = inspect.getsource(Session5ScenarioRunner.turn)
    canonical_source = inspect.getsource(Session5ScenarioRunner.execute_canonical)
    assert "CANONICAL_SCENARIO_COMPLETE" in turn_source
    assert "claim_execution" in turn_source
    assert "claim_execution" in canonical_source
    assert "requested_end_turn=canonical_turn_count" in canonical_source


def test_c01_c03_manifest_values_remain_the_certified_inputs():
    c02 = CustomerScenarioHarness.definition("C02")
    c03 = CustomerScenarioHarness.definition("C03")
    assert c02.canonical_turn_count == 7
    assert c02.canonical_customer_turns[0] == "hey, how's it going?"
    assert c02.canonical_customer_turns[-1] == "yeah, I don't have much else going on"
    assert c03.canonical_turn_count == 7
    assert c03.canonical_customer_turns[0] == "hey, what's up?"
    assert c03.canonical_customer_turns[-1] == "whatever, this is getting boring"
    assert asdict(CustomerScenarioHarness.definition("C01"))["name"] == "FRESH_SWEET_PROSPECT"

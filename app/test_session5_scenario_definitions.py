"""Static certification of the complete C04-C20 Scenario Lab manifest."""
from dataclasses import asdict
import inspect

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness,
    HistoricalPurchaseFixtureBuilder,
    SCENARIO_MANIFEST,
)
from app.testing.session5_scenario_runner import PURCHASE_PLANS, Session5ScenarioRunner


REMAINING = tuple(item for item in SCENARIO_MANIFEST if "C04" <= item.scenario_id <= "C20")
PURCHASE_CLAIM_SCENARIOS = {"C04", "C06", "C10", "C13", "C16", "C19", "C20"}
HISTORICAL_BUYERS = {f"C{number:02d}" for number in range(11, 20)}


def test_only_c13_defines_purchased_asset_intelligence_fixture():
    values = HistoricalPurchaseFixtureBuilder.C13_PURCHASED_ASSET_INTELLIGENCE

    assert values[1]["indoor_outdoor"] == "indoor"
    assert values[2]["indoor_outdoor"] == "outdoor"
    assert "portrait" in values[1]["tags"]
    assert "portrait" in values[2]["tags"]
    # The fixture is applied behind an explicit scenario_id == "C13" guard;
    # C11 and C12 retain their existing unadorned historical purchase seeds.
    source = inspect.getsource(HistoricalPurchaseFixtureBuilder._create_intent)
    assert 'scenario_id == "C13"' in source


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


def test_c13_materiality_preserves_primary_purchase_semantics_without_requiring_secondary_emphasis():
    definition = next(item for item in SCENARIO_MANIFEST if item.scenario_id == "C13")

    assert "PURCHASE_REFERENT_PRIMARY_SEMANTICS_PRESERVED" in (
        definition.certification_objectives
    )
    assert "correct referent, primary sentiment, and completed timing" in (
        definition.completion_condition
    )
    assert "secondary comparative emphasis remains visible quality debt" in (
        definition.completion_condition
    )
    assert sum(PURCHASE_PLANS["C15"]) >= 15000
    assert sum(PURCHASE_PLANS["C16"]) >= 50000
    assert sum(PURCHASE_PLANS["C17"]) >= 50000


def test_c14_definition_certifies_passive_cooling_without_scripted_rejection():
    definition = CustomerScenarioHarness.definition("C14")
    script = " ".join(definition.canonical_customer_turns).lower()

    assert "PASSIVE_NONCONVERSION_COOLING" in definition.certification_objectives
    assert "FUTURE_REACTIVATION_ALLOWED" in definition.certification_objectives
    assert "passive nonconversion" in definition.completion_condition.lower()
    assert all(phrase not in script for phrase in (
        "don't send", "do not send", "not looking to buy", "not interested",
        "too expensive", "no thanks",
    ))
    assert len(definition.canonical_customer_turns) == 7


def test_c17_definition_certifies_noncommercial_whale_relationship_nurture():
    definition = CustomerScenarioHarness.definition("C17")
    assert definition.canonical_customer_turns == (
        "hey, just checking in",
        "work's been crazy lately",
        "I'm finally getting away to the lake this weekend",
        "yeah I usually fish when I'm out there",
        "honestly that's probably my favorite way to unwind",
        "anyway I just wanted to come say hi for a bit",
        "I'll talk to you later",
    )
    script = " ".join(definition.canonical_customer_turns).lower()
    assert all(value not in script for value in (
        "not shopping", "no links", "show me", "send it", "how much",
    ))
    assert definition.canonical_events == ()
    assert definition.purchase_emulation_requirements == ()
    assert "buyer relationship nurture" in definition.completion_condition
    assert "creates no offer or failed opportunity" in definition.completion_condition


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
    assert {
        "CUSTOMER_FACING_SESSION_TERMINOLOGY_NOT_REQUIRED",
        "FREE_TEASER_NO_PAID_COMMERCE", "SESSION_STATE_CONTINUITY",
        "OWNERSHIP_EXCLUSION", "POST_COMPLETION_NO_AUTOMATIC_REOPEN",
    } <= set(item.branch_checkpoints)
    assert [event.after_turn for event in item.canonical_events] == [5, 9, 12]


def test_purchase_claim_scenarios_declare_inter_turn_settlement_events():
    expected = {"C04": 4, "C10": 7, "C13": 6, "C16": 6, "C19": 6}
    for scenario_id, after_turn in expected.items():
        events = CustomerScenarioHarness.definition(scenario_id).canonical_events
        assert len(events) == 1
        assert events[0].event_type == "SYNTHETIC_PROVIDER_SETTLEMENT"
        assert events[0].after_turn == after_turn


@pytest.mark.parametrize("scenario_id", ("C04", "C06", "C10", "C13", "C16", "C19", "C20"))
def test_paid_scenarios_expect_structured_price_without_verbal_price(scenario_id):
    item = CustomerScenarioHarness.definition(scenario_id)
    assert "STRUCTURED_PRICE_NO_VERBAL_PRICE" in item.certification_objectives


def test_c19_prepare_binds_owned_first_step_and_unowned_continuation_inventory():
    prepare = inspect.getsource(Session5ScenarioRunner._prepare_with_slot)
    fixture = inspect.getsource(
        HistoricalPurchaseFixtureBuilder.prepare_c19_session_compatible_inventory
    )

    assert 'scenario_id == "C19"' in prepare
    assert "prepare_c19_session_compatible_inventory" in prepare
    assert 'session_reference="certification-C19"' in fixture
    assert 'photoshoot_id="certification-C19"' in fixture
    assert "synchronize_purchase" in fixture
    assert '"consumedStep"' in fixture
    assert '"nextStep"' in fixture


def test_c19_validation_fails_closed_on_session_progression_parity():
    validation = inspect.getsource(CustomerScenarioHarness.validate_starting_state)

    assert 'scenario_id == "C19"' in validation
    for required in (
        "c19.activeSessions", "commercial_foundation_type",
        "commercial_foundation_reference", "c19.step1",
        "c19.step2", "c19.activePurchaseIntent",
        "c19.activeUnresolvedOpportunity", "c19.normalSessionSelectorNextStep",
        "sessionProgression",
    ):
        assert required in validation


def test_reset_orders_photoshoot_dependencies_before_commerce_profile_and_preserves_evidence():
    source = inspect.getsource(CustomerScenarioHarness.reset)
    ordered_fragments = (
        'optional_delete("autonomous_sales_actions"',
        'optional_delete("customer_photoshoot_lifecycle_sessions"',
        'optional_delete("customer_photoshoot_lifecycle_events"',
        'optional_delete("customer_photoshoot_lifecycles"',
        'delete("sales_sessions"',
        'delete("customer_commerce_transactions"',
        'delete("customer_commerce_profiles"',
    )
    offsets = [source.index(fragment) for fragment in ordered_fragments]
    assert offsets == sorted(offsets)
    assert 'DELETE FROM certification_scenario_defects' not in source
    assert 'DELETE FROM certification_scenario_assessments' not in source
    assert 'row["state"] == "VERIFIED_CLEAN"' in source


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

from types import SimpleNamespace

import pytest

from app.testing.session5_scenario_harness import CustomerScenarioHarness
from app.testing.session5_scenario_runner import Session5ScenarioRunner


def test_c09_keeps_ten_scripted_turns_and_allows_two_certification_turns():
    definition = CustomerScenarioHarness.definition("C09")

    assert definition.canonical_turn_count == 10
    assert len(definition.canonical_customer_turns) == 10
    assert definition.maximum_turn_count == 12


@pytest.mark.parametrize("next_turn", [11, 12])
def test_c09_runner_permits_post_threshold_and_reactivation_turns(next_turn):
    runner = object.__new__(Session5ScenarioRunner)
    runner._active = lambda **_kwargs: {"scenario_id": "C09"}
    runner.harness = SimpleNamespace(
        definition=lambda _scenario: CustomerScenarioHarness.definition("C09")
    )
    runner.recovery = SimpleNamespace(
        scenario_attempt=lambda _scenario: 2,
        next_logical_turn=lambda _scenario, _attempt: next_turn,
        claim_execution=lambda *_args, **_kwargs: "owner",
        release_execution=lambda *_args, **_kwargs: None,
    )
    runner._turn_owned = lambda message, **_kwargs: {
        "logicalTurn": next_turn,
        "message": message,
    }

    result = runner.turn("certification extension")

    assert result["logicalTurn"] == next_turn


def test_c09_runner_retains_a_finite_boundary_after_turn_twelve():
    runner = object.__new__(Session5ScenarioRunner)
    runner._active = lambda **_kwargs: {"scenario_id": "C09"}
    runner.harness = SimpleNamespace(
        definition=lambda _scenario: CustomerScenarioHarness.definition("C09")
    )
    runner.recovery = SimpleNamespace(
        scenario_attempt=lambda _scenario: 2,
        next_logical_turn=lambda _scenario, _attempt: 13,
    )

    with pytest.raises(
        RuntimeError,
        match=r"CANONICAL_SCENARIO_COMPLETE: scenario=C09 attempt=2 canonicalTurns=12",
    ):
        runner.turn("must not execute")


def test_other_extended_scenario_limits_are_unchanged():
    assert CustomerScenarioHarness.definition("C05").maximum_turn_count == 16
    assert CustomerScenarioHarness.definition("C06").maximum_turn_count == 18
    assert CustomerScenarioHarness.definition("C07").maximum_turn_count == 14
    assert CustomerScenarioHarness.definition("C08").maximum_turn_count == 18

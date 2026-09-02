import re
from dataclasses import asdict

from app.api.test_chat import ScenarioPrepareRequest
from app.testing.session5_scenario_harness import (
    BehaviorProfile,
    CommercialTrajectory,
    SCENARIO_MANIFEST,
)
from app.testing.adaptive_synthetic_customer import CustomerBehaviorPhase


def _definition(scenario_id):
    return next(item for item in SCENARIO_MANIFEST if item.scenario_id == scenario_id)


def test_c02_has_a_complete_deterministic_quiet_no_interest_trajectory():
    c02 = _definition("C02")

    assert c02.behavior_profile is BehaviorProfile.QUIET
    assert c02.trajectory is CommercialTrajectory.NO_INTEREST
    assert c02.canonical_turn_count == 7
    assert len(c02.canonical_customer_turns) == c02.canonical_turn_count
    assert len(c02.adaptive_phase_sequence) == c02.canonical_turn_count
    assert tuple(CustomerBehaviorPhase(phase) for phase in c02.adaptive_phase_sequence) == (
        CustomerBehaviorPhase.QUIET_LOW_RETURN,
    ) * c02.canonical_turn_count
    assert all(message.strip() for message in c02.canonical_customer_turns)
    assert c02.completion_condition


def test_c02_customer_messages_do_not_inject_other_scenario_signals():
    transcript = " ".join(_definition("C02").canonical_customer_turns).lower()

    assert not re.search(r"\b(?:buy|price|cost|unlock|purchase|pay|offer)\b", transcript)
    assert not re.search(r"\b(?:sexy|horny|naked|nudes?|fuck|turn me on)\b", transcript)
    assert not re.search(r"\b(?:hate|idiot|stupid|shut up|leave me alone|fuck off)\b", transcript)


def test_c02_defines_required_objectives_checkpoints_and_prepare_contract():
    c02 = _definition("C02")

    assert c02.certification_objectives == (
        "QUIET_PROSPECT_RECOGNIZED",
        "NO_PREMATURE_SELLING",
        "NO_MANUFACTURED_ENGAGEMENT_LOOP",
        "NO_FALSE_TIME_WASTER_ESCALATION",
        "APPROPRIATE_ATTENTION_ALLOCATION",
        "NATURAL_CONVERSATIONAL_TAPER",
    )
    assert c02.branch_checkpoints == (
        "EARLY_NORMAL_INVESTMENT",
        "REPEATED_LOW_ENGAGEMENT",
        "LATER_REDUCED_EXPANSION_TAPER",
        "NO_COMMERCIAL_PROGRESSION",
        "NO_PURCHASE_INTENT",
    )
    assert ScenarioPrepareRequest(scenario_id="C02").scenario_id == "C02"


def test_c02_definition_and_legacy_stub_definitions_remain_unchanged():
    c01 = _definition("C01")
    assert c01.name == "FRESH_SWEET_PROSPECT"
    assert c01.economic_state.value == "FRESH_PROSPECT"
    assert c01.behavior_profile.value == "SWEET"
    assert c01.trajectory.value == "WARMING"

    added_fields = {
        "canonical_customer_turns",
        "canonical_turn_count",
        "adaptive_phase_sequence",
        "completion_condition",
    }
    for definition in SCENARIO_MANIFEST:
        assert added_fields <= asdict(definition).keys()

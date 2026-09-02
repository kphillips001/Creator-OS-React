import re

from app.api.test_chat import ScenarioPrepareRequest
from app.testing.session5_scenario_harness import (
    BehaviorProfile,
    CommercialTrajectory,
    EconomicState,
    SCENARIO_MANIFEST,
)


def _definition(scenario_id):
    return next(item for item in SCENARIO_MANIFEST if item.scenario_id == scenario_id)


def test_c03_has_complete_progressive_rude_no_interest_trajectory():
    c03 = _definition("C03")

    assert c03.economic_state is EconomicState.FRESH_PROSPECT
    assert c03.behavior_profile is BehaviorProfile.RUDE
    assert c03.trajectory is CommercialTrajectory.NO_INTEREST
    assert c03.canonical_turn_count == 7
    assert len(c03.canonical_customer_turns) == c03.canonical_turn_count
    assert len(c03.adaptive_phase_sequence) == c03.canonical_turn_count
    assert c03.adaptive_phase_sequence[0] == "UNKNOWN_NEW_PROSPECT"
    assert c03.adaptive_phase_sequence[-1] == "FINAL_DISENGAGEMENT"
    assert all(message.strip() for message in c03.canonical_customer_turns)
    assert c03.completion_condition


def test_c03_rudeness_emerges_from_messages_without_hidden_turn_one_label():
    c03 = _definition("C03")
    first = c03.canonical_customer_turns[0].lower()
    later = " ".join(c03.canonical_customer_turns[1:]).lower()

    assert not re.search(r"\b(?:rude|boring|trying too hard|don't care|didn't ask)\b", first)
    assert re.search(r"\b(?:chatty|trying a little too hard|didn't ask|like i care|entertained|boring)\b", later)
    assert c03.facts_ava_must_discover == (
        "progressive dismissiveness and disrespect from actual messages",
    )


def test_c03_messages_exclude_commerce_sexual_severe_abuse_and_purchase_history():
    transcript = " ".join(_definition("C03").canonical_customer_turns).lower()

    assert not re.search(r"\b(?:buy|price|cost|unlock|purchase|pay|offer|bought|buyer)\b", transcript)
    assert not re.search(r"\b(?:sexy|horny|naked|nudes?|turn me on|sexual)\b", transcript)
    assert not re.search(r"\b(?:kill|threat|hurt you|fuck you|idiot|stupid|hate you)\b", transcript)


def test_c03_defines_required_objectives_checkpoints_and_prepare_contract():
    c03 = _definition("C03")

    assert c03.certification_objectives == (
        "RUDE_BEHAVIOR_DISCOVERED_FROM_EVIDENCE",
        "NO_HIDDEN_BEHAVIOR_CLASSIFICATION",
        "NO_OVERINVESTMENT_IN_DISRESPECT",
        "APPROPRIATE_BOUNDARY_OR_ATTENTION_REDUCTION",
        "NO_PREMATURE_COMMERCIAL_PROGRESSION",
        "NO_FALSE_COMMERCIAL_TIME_WASTER_EVIDENCE",
        "NATURAL_CONFIDENT_RESPONSE",
    )
    assert c03.branch_checkpoints == (
        "INITIAL_UNKNOWN_PROSPECT_TREATMENT",
        "FIRST_OBSERVED_DISRESPECT",
        "SUSTAINED_DISRESPECT",
        "ATTENTION_EFFORT_RESPONSE",
        "NO_COMMERCIAL_PROGRESSION",
        "FINAL_TAPER_OR_BOUNDARY",
    )
    assert ScenarioPrepareRequest(scenario_id="C03").scenario_id == "C03"


def test_c03_definition_does_not_change_c01_c02_or_c04_through_c20_identity():
    assert _definition("C01").name == "FRESH_SWEET_PROSPECT"
    assert _definition("C02").canonical_customer_turns == (
        "hey, how's it going?",
        "not too bad, just taking it easy",
        "yeah, pretty much",
        "work was okay, nothing exciting really",
        "mostly just relaxing tonight",
        "I'm still here, just kinda quiet",
        "yeah, I don't have much else going on",
    )
    assert [item.scenario_id for item in SCENARIO_MANIFEST[3:]] == [
        f"C{number:02d}" for number in range(4, 21)
    ]

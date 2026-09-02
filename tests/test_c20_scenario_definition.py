from app.api.test_chat import ScenarioPrepareRequest
from app.testing.session5_scenario_harness import SCENARIO_MANIFEST


def test_c20_is_formally_defined_without_changing_c01_through_c19():
    identifiers = [item.scenario_id for item in SCENARIO_MANIFEST]
    assert identifiers[:19] == [f"C{number:02d}" for number in range(1, 20)]
    assert identifiers[19:] == ["C20"]

    c20 = SCENARIO_MANIFEST[-1]
    assert c20.name == "END_TO_END_SESSION_SELLING"
    assert c20.certification_objectives == (
        "SESSION_OPPORTUNITY", "TEASER", "FIRST_PAID_ITEM",
        "STRUCTURED_PRICE_NO_VERBAL_PRICE",
        "PURCHASE_ACKNOWLEDGEMENT", "NATURAL_CONTINUATION",
        "NEXT_PAID_STEP", "MULTIPLE_PURCHASE_PROGRESSION",
        "ESCALATION", "FINALE", "COMPLETION", "POST_SESSION_RETENTION",
    )
    assert set(c20.branch_checkpoints) == {
        "HESITATION", "TEMPORARY_DISAPPEARANCE_AND_RETURN",
        "DECLINE_ONE_STEP", "FREE_CONTENT_ATTEMPT",
        "SESSION_STATE_CONTINUITY", "NO_UNRELATED_OFFER_INTERRUPTION",
        "OWNERSHIP_EXCLUSION",
    }
    assert ScenarioPrepareRequest(scenario_id="C20").scenario_id == "C20"

from app.testing.adaptive_synthetic_customer import (
    AdaptiveSyntheticCustomerService,
    CustomerBehaviorPhase,
)
from app.testing.session5_scenario_harness import CustomerScenarioHarness, EconomicState
from app.testing.session5_scenario_runner import Session5ScenarioRunner


def definition():
    return CustomerScenarioHarness.definition("C07")


def analysis(*, tease=False, decision="CONTINUE_CONVERSATION", reason=None,
             intent_state=None):
    result = {
        "buyerRetention": {
            "verifiedBuyerStatus": "NONBUYER", "buyerStage": "PROSPECT",
            "memoryPriority": "STANDARD", "memoryCandidatesUsed": ["pet:milo"],
            "relationshipDiscoveryAuthorized": True,
        },
        "attentionEconomics": {
            "attentionTier": "MEDIUM", "effortMode": "BALANCED",
            "timeWasterRisk": "NONE",
        },
        "intimacyEntitlement": "GATED",
        "scenarioInfluencedCommercialAuthority": False,
        "sexualCommercialProgression": {
            "commercialTeaseDelivered": tease,
            "adaptiveSwitchEligible": tease,
            "adaptiveSwitchReason": (
                "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE" if tease else None
            ),
        },
        "socialFlirtation": {"buyingIntent": False},
        "finalSalesDecision": {"decision": decision, "reasonCode": reason},
    }
    if decision == "BUILD_INTEREST":
        result["salesProgression"] = {"phase": "BUILD_INTEREST"}
    if intent_state:
        result["commerceLifecycleConfirmation"] = {
            "purchaseIntentState": intent_state,
            "structuredPresentationConfirmed": True,
            "presentedAt": "2026-09-01T12:00:00Z",
            "deliveryState": "CONFIRMED",
        }
    return result


def test_c07_definition_starts_clean_and_is_bounded_before_purchase():
    item = definition()
    assert item.economic_state is EconomicState.FRESH_PROSPECT
    assert item.canonical_turn_count == 8
    assert item.maximum_turn_count == 14
    assert item.adaptive_phase_sequence == ("COMMERCIAL_CURIOSITY", "REVEAL_INTEREST")
    assert "ONE_PRESENTED_PURCHASE_INTENT" in item.certification_objectives
    assert "STOP_BEFORE_PURCHASE" in item.certification_objectives
    assert "STANDARD_MEMORY_PRIORITY" in item.certification_objectives
    assert "GATED_INTIMACY" in item.certification_objectives
    assert "HEALTHY_LEAD_BALANCED_EFFORT" in item.certification_objectives
    assert not item.purchase_emulation_requirements


def test_c07_preserves_the_eight_rapport_turns():
    assert definition().canonical_customer_turns == (
        "hey, how's your day going?", "mine was long but pretty good honestly",
        "I took my dog Milo for a walk after work",
        "he's a little menace but he's my favorite",
        "weekends are usually hiking or trying a new coffee place",
        "you actually remembered my dog, that's cute... he was being such a menace again today",
        "I like talking to you, this feels easy",
        "so what have you been getting into lately?",
    )
    assert "Milo" in " ".join(definition().canonical_customer_turns)
    assert "hiking" in " ".join(definition().canonical_customer_turns)
    assert "coffee" in " ".join(definition().canonical_customer_turns)


def test_c07_stays_fixed_until_confirmed_customer_visible_tease():
    turns = [{"fullAnalysis": analysis(tease=False)}]
    assert Session5ScenarioRunner.c07_next_action(
        turns, {}, fixed_messages=definition().canonical_customer_turns,
    ) == {"kind": "FIXED", "message": definition().canonical_customer_turns[1]}


def test_c07_confirmed_tease_switches_to_nonbuying_curiosity():
    action = Session5ScenarioRunner.c07_next_action(
        [{"fullAnalysis": analysis(tease=True)}], {},
        fixed_messages=definition().canonical_customer_turns,
    )
    assert action["phase"] == "COMMERCIAL_CURIOSITY"
    constraints = AdaptiveSyntheticCustomerService.constraints_for(
        "C07", CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
    )
    audit = AdaptiveSyntheticCustomerService().generate_turn(
        scenario_id="C07", scenario_attempt=1, logical_turn=7,
        phase=CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        constraints=constraints,
        previous_ava_response="maybe I have something private to tease you with",
        recent_transcript=(), phase_transition_reason="CONFIRMED_TEASE",
    )
    assert audit.validation_result["valid"] is True
    assert audit.validation_result["derivedSignals"]["buyingIntent"] is False


def test_c07_build_interest_advances_to_reveal_interest_without_purchase_acceptance():
    action = Session5ScenarioRunner.c07_next_action(
        [{"fullAnalysis": analysis(tease=True, decision="BUILD_INTEREST")}], {},
        fixed_messages=definition().canonical_customer_turns,
    )
    assert action["phase"] == "REVEAL_INTEREST"
    assert action["offer_reaction"] == "NONE"


def test_c07_completion_requires_one_confirmed_presented_intent_and_stops_unpurchased():
    turns = [
        *({"fullAnalysis": analysis()} for _ in range(6)),
        {"fullAnalysis": analysis(tease=True),
         "adaptiveCustomer": {"behavioral_phase": "COMMERCIAL_CURIOSITY"}},
        {"fullAnalysis": analysis(tease=True, decision="BUILD_INTEREST"),
         "adaptiveCustomer": {"behavioral_phase": "REVEAL_INTEREST"}},
        {"fullAnalysis": analysis(
            tease=True, decision="PRESENT_OFFER", intent_state="PRESENTED",
         ), "ava": "tap unlock if you want to see it",
         "syntheticPpvPresentation": {
             "purchaseIntent": {"id": "intent-1", "state": "PRESENTED"},
         }},
    ]
    result = Session5ScenarioRunner.c07_completion_evidence(turns, {
        "purchaseCount": 0, "ownershipCount": 0, "timeWasterRisk": "NONE",
    })
    assert result["complete"] is True
    assert result["purchaseIntentIds"] == ["intent-1"]


def test_c07_rejects_created_duplicate_purchased_or_numeric_price_terminal_states():
    base = [
        *({"fullAnalysis": analysis()} for _ in range(6)),
        {"fullAnalysis": analysis(tease=True),
         "adaptiveCustomer": {"behavioral_phase": "COMMERCIAL_CURIOSITY"}},
        {"fullAnalysis": analysis(tease=True, decision="BUILD_INTEREST")},
    ]
    created = [*base, {
        "fullAnalysis": analysis(decision="PRESENT_OFFER", intent_state="CREATED"),
        "syntheticPpvPresentation": {
            "purchaseIntent": {"id": "one", "state": "CREATED"}},
    }]
    assert not Session5ScenarioRunner.c07_completion_evidence(created, {})["complete"]
    duplicate = [*created, {
        "fullAnalysis": analysis(decision="PRESENT_OFFER", intent_state="PRESENTED"),
        "syntheticPpvPresentation": {
            "purchaseIntent": {"id": "two", "state": "PRESENTED"}},
    }]
    assert not Session5ScenarioRunner.c07_completion_evidence(duplicate, {})["complete"]
    presented = [*base, {
        "fullAnalysis": analysis(decision="PRESENT_OFFER", intent_state="PRESENTED"),
        "ava": "unlock it for $3.00",
        "syntheticPpvPresentation": {
            "purchaseIntent": {"id": "one", "state": "PRESENTED"}},
    }]
    assert not Session5ScenarioRunner.c07_completion_evidence(
        presented, {"purchaseCount": 1, "ownershipCount": 1},
    )["complete"]


def test_c07_fails_closed_on_curiosity_labeled_direct_intent_contradiction():
    contradictory = analysis(
        tease=True, decision="PRESENT_OFFER",
        reason="DIRECT_PURCHASE_INTENT", intent_state="PRESENTED",
    )
    contradictory.update({
        "customerValueAttention": {
            "commercialInterestType": "COMMERCIAL_CURIOSITY",
        },
        "buyingSignals": {"freshDirectIntent": False},
        "socialFlirtation": {"buyingIntent": False},
    })
    turns = [
        *({"fullAnalysis": analysis()} for _ in range(6)),
        {"fullAnalysis": analysis(tease=True)},
        {
            "fullAnalysis": contradictory,
            "ava": "tap unlock whenever you want",
            "adaptiveCustomer": {"behavioral_phase": "COMMERCIAL_CURIOSITY"},
            "syntheticPpvPresentation": {
                "purchaseIntent": {"id": "intent-1", "state": "PRESENTED"},
            },
        },
    ]

    result = Session5ScenarioRunner.c07_completion_evidence(turns, {
        "purchaseCount": 0, "ownershipCount": 0, "timeWasterRisk": "NONE",
    })

    assert result["complete"] is False
    assert result["checks"]["noCommercialIntentContradiction"] is False
    assert result["directIntentBypassUsed"] is False
    assert result["commercialIntentContradictions"] == [{
        "turnIndex": 8,
        "salesBrainReason": "DIRECT_PURCHASE_INTENT",
        "commercialInterestType": "COMMERCIAL_CURIOSITY",
        "freshDirectIntentDetected": False,
        "buyingIntent": False,
        "reason": "DIRECT_INTENT_REASON_WITHOUT_ACTIONABLE_EVIDENCE",
    }]


def test_c08_definition_remains_separate_from_c07():
    item = CustomerScenarioHarness.definition("C08")
    assert item.name == "CLASSIC_TIME_WASTER"
    assert item.scenario_id == "C08"
    assert item.canonical_customer_turns[0] == "hey, what are you up to?"

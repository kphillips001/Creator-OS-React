from types import SimpleNamespace

from app.testing.adaptive_synthetic_customer import (
    AdaptiveSyntheticCustomerService,
    CustomerBehaviorPhase,
)
from app.testing.session5_scenario_harness import SCENARIO_MANIFEST
from app.testing.session5_scenario_runner import Session5ScenarioRunner


def definition():
    return next(item for item in SCENARIO_MANIFEST if item.scenario_id == "C05")


def analysis(*, tease=False, decision="CONTINUE_CONVERSATION",
             reason=None, acknowledged=False):
    return {
        "sexualCommercialProgression": {
            "sustainedSexualReceptiveness": True,
            "commercialTeaseDelivered": tease,
            "commercialTeaseExposureRecorded": tease,
            "progressionFinalizedAfterDelivery": tease,
            "adaptiveSwitchEligible": tease,
            "adaptiveSwitchReason": (
                "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE" if tease else None
            ),
        },
        "socialFlirtation": {"buyingIntent": False},
        "finalSalesDecision": {"decision": decision, "reasonCode": reason},
        "purchaseAcknowledgementCompleted": acknowledged,
        "purchaseAcknowledgementAuthorized": acknowledged,
        "acknowledgementProviderConfirmed": acknowledged,
    }


def test_c05_definition_is_bounded_adaptive_and_preserves_fixed_precommerce():
    item = definition()
    assert item.name == "HORNY_NEW_PROSPECT"
    assert len(item.canonical_customer_turns) == 10
    assert item.maximum_turn_count == 16
    assert item.canonical_turn_count == 10
    assert "LEAN_IN_CONVERT" in item.adaptive_branches
    assert "SEXUAL_BUT_COMMERCIALLY_NONRESPONSIVE" in item.adaptive_branches
    assert "REJECT_BACK_OFF" in item.adaptive_branches
    assert "DECLINE_OFFER" in item.adaptive_branches


def test_adaptive_validator_uses_production_direct_intent_authority():
    service = AdaptiveSyntheticCustomerService()
    reveal = service.constraints_for("C05", CustomerBehaviorPhase.REVEAL_INTEREST)
    result = service.validate(
        "my thoughts are getting naughty... let me see what you mean",
        phase=CustomerBehaviorPhase.REVEAL_INTEREST,
        constraints=reveal,
        previous_ava_response="maybe I have something private",
        offer_context={},
    )
    assert result["derivedSignals"]["buyingIntent"] is True
    assert "WORDING_INTRODUCED_BUYING_INTENT" in result["reasons"]


def test_adaptive_curiosity_and_reveal_fallbacks_match_production_semantics():
    service = AdaptiveSyntheticCustomerService()
    for phase in (
        CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        CustomerBehaviorPhase.REVEAL_INTEREST,
    ):
        constraints = service.constraints_for("C05", phase)
        turn = service.generate_turn(
            scenario_id="C05", scenario_attempt=999, logical_turn=5,
            phase=phase, constraints=constraints,
            previous_ava_response="maybe I have something private to tease you with",
            recent_transcript=(), phase_transition_reason="ISOLATED_TEST",
        )
        assert turn.validation_result["valid"] is True
        from app.services.conversational_sales_progression_service import (
            ConversationalSalesProgressionService,
        )
        features = ConversationalSalesProgressionService.transition_features(
            turn.final_customer_message
        )
        assert features["commercial_response_interest"] is True
        assert ConversationalSalesProgressionService().has_direct_purchase_intent(
            turn.final_customer_message
        ) is False


def test_c05_stays_fixed_until_customer_visible_commercial_exposure():
    item = definition()
    action = Session5ScenarioRunner.c05_next_action(
        [{"fullAnalysis": analysis(tease=False)}], {},
        fixed_messages=item.canonical_customer_turns,
    )
    assert action == {"kind": "FIXED", "message": item.canonical_customer_turns[1]}


def test_failed_or_pending_tease_cannot_trigger_adaptive_switch():
    item = definition()
    pending = analysis(tease=False, decision="TEASE")
    pending["sexualCommercialProgression"].update({
        "commercialTeaseAuthorized": True,
        "commercialTeaseWordingSatisfied": True,
        "commercialTeaseDelivered": False,
        "commercialTeaseExposureRecorded": False,
        "progressionFinalizedAfterDelivery": False,
        "adaptiveSwitchEligible": False,
    })
    action = Session5ScenarioRunner.c05_next_action(
        [{"fullAnalysis": pending}], {},
        fixed_messages=item.canonical_customer_turns,
    )
    assert action == {"kind": "FIXED", "message": item.canonical_customer_turns[1]}


def test_confirmed_tease_switches_primary_branch_to_adaptive_lean_in():
    action = Session5ScenarioRunner.c05_next_action(
        [{"fullAnalysis": analysis(tease=True)}], {}, fixed_messages=definition().canonical_customer_turns,
    )
    assert action["kind"] == "ADAPTIVE"
    assert action["phase"] == "COMMERCIAL_CURIOSITY"
    assert action["adaptive_switch_reason"] == (
        "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE"
    )
    constraints = AdaptiveSyntheticCustomerService.constraints_for(
        "C05", CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
    )
    audit = AdaptiveSyntheticCustomerService().generate_turn(
        scenario_id="C05", scenario_attempt=1, logical_turn=2,
        phase=CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        constraints=constraints, previous_ava_response="maybe I have a little surprise",
        recent_transcript=(), phase_transition_reason="CONFIRMED_TEASE",
    )
    assert audit.validation_result["valid"] is True
    assert audit.validation_result["derivedSignals"]["buyingIntent"] is False


def test_actual_build_interest_advances_customer_to_reveal_interest_without_forcing_offer():
    projection = analysis(tease=True, decision="BUILD_INTEREST")
    projection["salesProgression"] = {"phase": "BUILD_INTEREST"}
    action = Session5ScenarioRunner.c05_next_action(
        [{"fullAnalysis": projection}], {},
        fixed_messages=definition().canonical_customer_turns,
    )
    assert action == {
        "kind": "ADAPTIVE", "phase": "REVEAL_INTEREST",
        "offer_reaction": "NONE", "progression": "BUILD_INTEREST",
        "adaptive_switch_reason": "AVA_BUILD_INTEREST_CONFIRMED",
    }
    constraints = AdaptiveSyntheticCustomerService.constraints_for(
        "C05", CustomerBehaviorPhase.REVEAL_INTEREST,
    )
    audit = AdaptiveSyntheticCustomerService().generate_turn(
        scenario_id="C05", scenario_attempt=99, logical_turn=6,
        phase=CustomerBehaviorPhase.REVEAL_INTEREST,
        constraints=constraints,
        previous_ava_response="maybe I should show you what I mean",
        recent_transcript=(), phase_transition_reason="AVA_BUILD_INTEREST_CONFIRMED",
    )
    assert audit.validation_result["valid"] is True
    assert audit.validation_result["derivedSignals"]["buyingIntent"] is False
    from app.services.conversational_sales_progression_service import (
        ConversationalSalesProgressionService,
    )
    assert ConversationalSalesProgressionService.transition_features(
        audit.final_customer_message
    )["reveal_request"] is True


def test_repeated_adaptive_phase_uses_recent_context_without_cycling():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.COMMERCIAL_CURIOSITY
    constraints = service.constraints_for("C05", phase)
    transcript = []
    outputs = []
    for logical_turn in range(2, 8):
        audit = service.generate_turn(
            scenario_id="C05", scenario_attempt=99, logical_turn=logical_turn,
            phase=phase, constraints=constraints,
            previous_ava_response=f"Ava reply {logical_turn}?",
            recent_transcript=transcript,
            phase_transition_reason="REPEATED_PHASE_TEST",
        )
        assert audit.final_customer_message is not None
        assert audit.validation_result["valid"] is True
        assert audit.validation_result["recentCustomerRepetitionRisk"] is False
        outputs.append(audit.final_customer_message)
        transcript.extend((
            {"role": "customer", "content": audit.final_customer_message},
            {"role": "ava", "content": f"Ava reply {logical_turn}?"},
        ))
    assert len(set(outputs)) == len(outputs)


def test_adaptive_switch_requires_complete_post_delivery_truth():
    item = definition()
    for missing in (
        "commercialTeaseDelivered",
        "commercialTeaseExposureRecorded",
        "progressionFinalizedAfterDelivery",
    ):
        projection = analysis(tease=True)
        projection["sexualCommercialProgression"][missing] = False
        projection["sexualCommercialProgression"]["adaptiveSwitchEligible"] = False
        action = Session5ScenarioRunner.c05_next_action(
            [{"fullAnalysis": projection}], {},
            fixed_messages=item.canonical_customer_turns,
        )
        assert action["kind"] == "FIXED"


def test_presented_offer_can_be_accepted_but_acceptance_is_not_purchase_truth():
    turn = {
        "fullAnalysis": analysis(decision="PRESENT_OFFER"),
        "syntheticPpvPresentation": {"purchaseIntent": {"id": "intent-1"}},
    }
    action = Session5ScenarioRunner.c05_next_action(
        [turn], {"purchaseCount": 0}, fixed_messages=definition().canonical_customer_turns,
    )
    assert action == {"kind": "ADAPTIVE", "phase": "OFFER_REACTION",
                      "offer_reaction": "ACCEPT"}
    accepted = {**turn, "adaptiveCustomer": {
        "behavioral_phase": "OFFER_REACTION",
        "validation_result": {"derivedSignals": {"offerAcceptance": True}},
    }}
    next_action = Session5ScenarioRunner.c05_next_action(
        [accepted], {"purchaseCount": 0}, fixed_messages=definition().canonical_customer_turns,
    )
    assert next_action == {"kind": "SIMULATE_PURCHASE"}


def test_primary_completion_requires_purchase_ack_and_postpurchase_continuity():
    turns = [
        {"fullAnalysis": analysis(tease=True)},
        {"fullAnalysis": analysis(
            decision="PRESENT_OFFER", reason="DIRECT_PURCHASE_INTENT",
        ), "adaptiveCustomer": {
            "behavioral_phase": "COMMERCIAL_CURIOSITY"},
         "syntheticPpvPresentation": {"purchaseIntent": {"id": "one"}}},
        {"fullAnalysis": analysis(acknowledged=True), "adaptiveCustomer": {
            "behavioral_phase": "POST_PURCHASE_ACKNOWLEDGEMENT"}},
        {"fullAnalysis": analysis(), "adaptiveCustomer": {
            "behavioral_phase": "POST_PURCHASE_CONTINUITY"}},
    ]
    result = Session5ScenarioRunner.c05_completion_evidence(turns, {
        "purchaseCount": 1, "ownershipCount": 1,
        "buyerStage": "FIRST_TIME_BUYER",
    })
    assert result["complete"] is True
    assert result["realizedConversionPath"] == "DIRECT_INTENT_BYPASS"
    assert result["directIntentBypassUsed"] is True


def test_c05_completion_accepts_earned_progression_path():
    turns = [
        {"fullAnalysis": analysis(tease=True)},
        {"fullAnalysis": analysis(decision="BUILD_INTEREST"),
         "adaptiveCustomer": {"behavioral_phase": "COMMERCIAL_CURIOSITY"}},
        {"fullAnalysis": analysis(decision="PRESENT_OFFER"),
         "adaptiveCustomer": {"behavioral_phase": "REVEAL_INTEREST"},
         "syntheticPpvPresentation": {"purchaseIntent": {"id": "one"}}},
        {"fullAnalysis": analysis(acknowledged=True), "adaptiveCustomer": {
            "behavioral_phase": "POST_PURCHASE_ACKNOWLEDGEMENT"}},
        {"fullAnalysis": analysis(), "adaptiveCustomer": {
            "behavioral_phase": "POST_PURCHASE_CONTINUITY"}},
    ]
    result = Session5ScenarioRunner.c05_completion_evidence(turns, {
        "purchaseCount": 1, "ownershipCount": 1,
        "buyerStage": "FIRST_TIME_BUYER",
    })
    assert result["complete"] is True
    assert result["realizedConversionPath"] == "EARNED_PROGRESSION"
    assert result["buildInterestObserved"] is True
    assert result["revealInterestObserved"] is True


def test_secondary_branches_follow_confirmed_exposure_without_execution():
    turns = [{"fullAnalysis": analysis(tease=True)}]
    fixed = definition().canonical_customer_turns
    assert Session5ScenarioRunner.c05_next_action(
        turns, {}, branch="SEXUAL_BUT_COMMERCIALLY_NONRESPONSIVE",
        fixed_messages=fixed,
    )["phase"] == "ATTRACTION"
    assert Session5ScenarioRunner.c05_next_action(
        turns, {}, branch="REJECT_BACK_OFF", fixed_messages=fixed,
    )["phase"] == "COMMERCIAL_REJECTION"


def test_target_resolver_never_uses_latest_terminal_row():
    class Result:
        def fetchone(self):
            return {"scenario_id": "C05", "state": "COMPLETED"}

    class Connection:
        def execute(self, query, params):
            assert "WHERE scenario_id=%s" in query
            assert params == ("C05",)
            return Result()

    class Context:
        def __enter__(self): return Connection()
        def __exit__(self, *_): return False

    runner = object.__new__(Session5ScenarioRunner)
    runner.harness = SimpleNamespace(connection=lambda: Context())
    assert runner._target_scenario("C05", required_state="COMPLETED") == "C05"


def test_snapshot_and_reset_mutate_only_explicit_target():
    history = {f"C0{index}": f"immutable-{index}" for index in range(1, 6)}
    calls = []

    class AssessmentResult:
        def fetchone(self): return {"grade": "PASS", "completed_at": "now"}
    class Connection:
        def execute(self, _query, params):
            assert params == ("C05",)
            return AssessmentResult()
    class Context:
        def __enter__(self): return Connection()
        def __exit__(self, *_): return False

    runner = object.__new__(Session5ScenarioRunner)
    runner._target_scenario = lambda scenario_id, required_state: scenario_id
    runner._turns = lambda _scenario_id: []
    runner._defects = lambda _scenario_id: []
    runner.builder = SimpleNamespace(derived_state=lambda _scenario_id: {})
    runner.harness = SimpleNamespace(
        connection=lambda: Context(),
        definition=lambda _scenario_id: SimpleNamespace(name="HORNY_NEW_PROSPECT"),
        snapshot=lambda scenario_id, _evidence: calls.append(("snapshot", scenario_id)) or "snap",
        reset=lambda scenario_id: calls.append(("reset", scenario_id)) or {"scenarioId": scenario_id},
    )
    before = dict(history)
    runner.snapshot("C05")
    runner.reset("C05")
    assert calls == [("snapshot", "C05"), ("reset", "C05")]
    assert history == before


def test_prepare_targets_requested_scenario_and_active_owner_still_blocks():
    calls = []
    runner = object.__new__(Session5ScenarioRunner)
    runner._active = lambda optional=False: None
    runner._run = lambda scenario_id: {
        "scenario_id": scenario_id, "state": "SNAPSHOTTED",
    }
    runner.verify_clean = lambda _scenario_id: {"result": "VERIFIED_CLEAN"}
    runner.harness = SimpleNamespace(
        reset=lambda scenario_id: calls.append(("reset", scenario_id)),
        prepare=lambda scenario_id: calls.append(("prepare", scenario_id)),
        validate_starting_state=lambda scenario_id, expected_purchase_count: {
            "scenario": scenario_id, "result": "VALIDATED",
        },
        transition=lambda scenario_id, state: calls.append(
            ("transition", scenario_id, state.value)
        ),
    )
    runner.builder = SimpleNamespace(
        add_eligible_inventory=lambda scenario_id, prices: calls.append(
            ("inventory", scenario_id)
        ),
        derived_state=lambda scenario_id: {"scenario": scenario_id},
    )
    runner.recovery = SimpleNamespace(start_attempt=lambda scenario_id: 2)
    result = runner._prepare_with_slot("C05")
    assert result["scenario"] == "C05"
    assert all(call[1] == "C05" for call in calls)

    runner._active = lambda optional=False: {"scenario_id": "C01"}
    calls_before = list(calls)
    try:
        runner._prepare_with_slot("C06")
        raise AssertionError("Expected active execution owner to block preparation")
    except RuntimeError as error:
        assert "Active scenario C01" in str(error)
    assert calls == calls_before


def test_latest_terminal_fallback_is_select_only():
    class Result:
        def fetchone(self): return {"scenario_id": "C04", "state": "COMPLETED"}
    class Connection:
        def execute(self, query, params):
            assert query.lstrip().upper().startswith("SELECT")
            assert params
            return Result()
    class Context:
        def __enter__(self): return Connection()
        def __exit__(self, *_): return False
    runner = object.__new__(Session5ScenarioRunner)
    runner.harness = SimpleNamespace(connection=lambda: Context())
    assert runner._latest_terminal()["scenario_id"] == "C04"

from app.services.session_escalation_decision_service import (
    SessionEscalationDecisionService,
)
from app.testing.adaptive_synthetic_customer import (
    AdaptiveSyntheticCustomerService,
    CustomerBehaviorPhase,
)
from app.testing.session5_scenario_harness import CustomerScenarioHarness
from app.testing.session5_scenario_runner import Session5ScenarioRunner
import inspect


def definition():
    return CustomerScenarioHarness.definition("C06")


def escalation(decision, **overrides):
    value = {
        "sessionCandidate": decision in {"PROPOSE_SESSION", "SESSION_ACCEPTED"},
        "sessionEscalationDecision": decision,
        "sessionProposalAuthorized": decision == "PROPOSE_SESSION",
        "sessionStartAuthorityEligible": decision == "SESSION_ACCEPTED",
        "sessionStarted": False,
        "purchaseStreakCount": 2,
        "recentPurchaseVelocity": {"recentPurchaseCount": 2},
    }
    value.update(overrides)
    return value


def turn(*, phase=None, decision="CONTINUE_CONVERSATION", reason=None,
         intent=None, offering=None, acknowledged=False, escalation_row=None,
         buying_intent=False, ava="natural reply", customer="ordinary message",
         accepted_intent=None):
    result = {
        "customer": customer,
        "ava": ava,
        "fullAnalysis": {
            "socialFlirtation": {"buyingIntent": buying_intent},
            "finalSalesDecision": {"decision": decision, "reasonCode": reason},
            "purchaseAcknowledgementCompleted": acknowledged,
            "sessionEscalation": escalation_row or {},
        },
    }
    if phase:
        result["adaptiveCustomer"] = {"behavioral_phase": phase}
    if accepted_intent:
        result["adaptiveCustomer"] = {
            "behavioral_phase": "OFFER_REACTION",
            "authoritative_offer_context": {"purchaseIntentId": accepted_intent},
            "validation_result": {"derivedSignals": {"offerAcceptance": True}},
        }
    if intent and offering:
        result["syntheticPpvPresentation"] = {
            "offeringId": offering,
            "purchaseIntent": {"id": intent, "state": "PRESENTED"},
        }
    return result


def test_c06_definition_is_fresh_bounded_adaptive_and_two_purchase():
    item = definition()
    assert item.name == "HOT_BUYER_MULTI_PPV_SESSION_DECISION"
    assert item.economic_state.value == "FRESH_PROSPECT"
    assert not item.seeded_history
    assert item.maximum_turn_count == 18
    assert item.maximum_turn_count > item.canonical_turn_count
    assert len(item.purchase_emulation_requirements) == 2
    assert item.trajectory.value == "SEXUAL_ONLY"
    assert "FLIRTATIOUS_OR_SEXUAL_INTEREST_NOT_BUYING_INTENT" in item.certification_objectives
    assert "SESSION_START_ELIGIBLE_NOT_STARTED" in item.certification_objectives
    assert "SESSION_ACCEPTED_BOUNDARY" in item.branch_checkpoints
    assert {
        "ONGOING_EXPERIENCE_CONTINUATION", "DISCRETE_CONTINUATION",
        "ONGOING_EXPERIENCE_NO_SESSION_INVENTORY", "HOT_PRAISE_NO_MORE_REQUEST",
        "DECLINE_SESSION_WANTS_PPVS",
    } <= set(item.adaptive_branches)


def test_c06_prepare_uses_two_ordinary_and_three_session_compatible_steps():
    source = inspect.getsource(Session5ScenarioRunner._prepare_with_slot)
    assert "(900, 1900, 2900, 3900, 4900)" in source
    assert "prepare_session_compatible_inventory" in source
    fixture_source = inspect.getsource(
        __import__(
            "app.testing.session5_scenario_harness", fromlist=["HistoricalPurchaseFixtureBuilder"]
        ).HistoricalPurchaseFixtureBuilder.prepare_session_compatible_inventory
    )
    assert "'SESSION'" in fixture_source
    assert "'IN_ASSET_LIBRARY'" in fixture_source
    assert "source_photoshoot_deliverable_id" in fixture_source


def test_c06_customer_phases_delegate_continuation_semantics_to_production():
    service = AdaptiveSyntheticCustomerService()
    cases = (
        (CustomerBehaviorPhase.DISCRETE_CONTINUATION, "got another one?", "DISCRETE_ITEM"),
        (CustomerBehaviorPhase.ONGOING_EXPERIENCE_CONTINUATION,
         "don't stop, I want to keep this going", "ONGOING_EXPERIENCE"),
    )
    for phase, message, expected in cases:
        constraints = service.constraints_for("C06", phase)
        result = service.validate(
            message, phase=phase, constraints=constraints,
            previous_ava_response="okay", offer_context={},
        )
        assert result["valid"] is True
        assert SessionEscalationDecisionService.continuation_intent(message) == expected


def test_post_purchase_acknowledgement_varies_across_two_purchases():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT
    constraints = service.constraints_for("C06", phase)
    first = service.generate_turn(
        scenario_id="C06", scenario_attempt=99, logical_turn=5, phase=phase,
        constraints=constraints, previous_ava_response="hope you like it",
        recent_transcript=(), phase_transition_reason="FIRST_PURCHASE",
        purchase_ordinal=1,
    )
    second = service.generate_turn(
        scenario_id="C06", scenario_attempt=99, logical_turn=8, phase=phase,
        constraints=constraints, previous_ava_response="this one is even better",
        recent_transcript=({"role": "customer", "content": first.final_customer_message},),
        phase_transition_reason="SECOND_PURCHASE", purchase_ordinal=2,
    )
    assert first.validation_result["valid"] is True
    assert second.validation_result["valid"] is True
    assert service._normalize(first.final_customer_message) != service._normalize(
        second.final_customer_message
    )
    assert first.provider_metadata["purchaseOrdinal"] == 1
    assert second.provider_metadata["purchaseOrdinal"] == 2
    assert second.validation_result["recentCustomerRepetitionRisk"] is False


def test_post_purchase_acknowledgement_bounded_pool_does_not_cycle_immediately():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT
    constraints = service.constraints_for("C06", phase)
    recent = []
    values = []
    for ordinal in range(1, 7):
        audit = service.generate_turn(
            scenario_id="C06", scenario_attempt=99, logical_turn=ordinal,
            phase=phase, constraints=constraints,
            previous_ava_response="glad you unlocked it",
            recent_transcript=tuple(recent),
            phase_transition_reason="REPEATED_PURCHASE", purchase_ordinal=ordinal,
        )
        assert audit.validation_result["valid"] is True
        values.append(audit.final_customer_message)
        recent.append({"role": "customer", "content": audit.final_customer_message})
    assert len({service._normalize(value) for value in values}) == len(values)


def test_post_purchase_acknowledgement_pool_exhaustion_fails_closed():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT
    prior = (
        "okay I unlocked it, that was hot",
        "yeah I got it, I like that one",
        "got it, that one was good",
        "unlocked it, definitely into that",
        "yep got it, nice choice",
        "okay, that one hit",
    )
    audit = service.generate_turn(
        scenario_id="C06", scenario_attempt=99, logical_turn=12, phase=phase,
        constraints=service.constraints_for("C06", phase),
        previous_ava_response="glad you unlocked it",
        recent_transcript=tuple(
            {"role": "customer", "content": value} for value in prior
        ), phase_transition_reason="BOUNDED_POOL_EXHAUSTED", purchase_ordinal=6,
    )
    assert audit.final_customer_message is None
    assert "REPEATED_RECENT_CUSTOMER_WORDING" in audit.blocked_reason


def test_post_purchase_acknowledgement_rejects_provider_repeat_then_uses_fallback():
    service = AdaptiveSyntheticCustomerService(
        generator=lambda _: "okay I unlocked it, that was hot"
    )
    phase = CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT
    audit = service.generate_turn(
        scenario_id="C06", scenario_attempt=99, logical_turn=8, phase=phase,
        constraints=service.constraints_for("C06", phase),
        previous_ava_response="this one is even better",
        recent_transcript=({
            "role": "customer", "content": "okay I unlocked it, that was hot",
        },), phase_transition_reason="SECOND_PURCHASE", purchase_ordinal=2,
    )
    assert audit.wording_source == "DETERMINISTIC_PHASE_SAFE_FALLBACK_AFTER_REJECTION"
    assert audit.generated_customer_candidate == "okay I unlocked it, that was hot"
    assert audit.final_customer_message == "yeah I got it, I like that one"
    assert audit.validation_result["valid"] is True


def test_c06_post_second_purchase_acknowledgement_reaches_ongoing_phase():
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT
    prior = "okay I unlocked it, that was hot"
    audit = service.generate_turn(
        scenario_id="C06", scenario_attempt=99, logical_turn=8, phase=phase,
        constraints=service.constraints_for("C06", phase),
        previous_ava_response="hope the second one hits",
        recent_transcript=({"role": "customer", "content": prior},),
        phase_transition_reason="SECOND_PURCHASE", purchase_ordinal=2,
    )
    assert audit.final_customer_message is not None
    action = Session5ScenarioRunner.c06_next_action([
        turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
        turn(
            phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True,
            customer=audit.final_customer_message,
        ),
    ], {"purchaseCount": 2})
    assert action == {
        "kind": "ADAPTIVE", "phase": "ONGOING_EXPERIENCE_CONTINUATION",
    }


def test_c06_turn_projection_exposes_early_interest_without_scenario_authority():
    runner = object.__new__(Session5ScenarioRunner)
    projection = runner._turn_projection({
        "scenarioId": "C06", "turnNumber": 1,
        "inboundText": "you look ridiculously hot tonight",
        "finalResponseText": "you are trouble",
        "SalesBrainFullAnalysis": {},
    }, [])
    assert projection["earlyInterestType"] == "FLIRTATION"


def test_c06_secondary_decision_branches_use_canonical_authority():
    base = dict(active_buying_window=True, purchase_count=2,
                recent_purchase_count=2, explicit_continuation_count=1,
                ordinary_inventory_available=True)
    discrete = SessionEscalationDecisionService.project(
        **base, current_message="show me another one",
        session_inventory_available=True,
    )
    unavailable = SessionEscalationDecisionService.project(
        **base, current_message="don't stop, keep this going",
        session_inventory_available=False,
    )
    praise = SessionEscalationDecisionService.project(
        **base, current_message="damn that was hot",
        session_inventory_available=True,
    )
    declined = SessionEscalationDecisionService.project(
        **base, current_message="I'd rather just see another one instead",
        session_inventory_available=True, proposal_pending=True,
    )
    assert discrete["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"
    assert unavailable["sessionUnavailableFallback"] is True
    assert unavailable["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"
    assert praise["sessionEscalationDecision"] == "NO_FURTHER_SALE_NOW"
    assert declined["sessionEscalationDecision"] == "CONTINUE_DISCRETE_PPVS"
    assert declined["sessionProposalCustomerReaction"] == "DECLINE_SESSION_BUT_WANTS_MORE"


def test_c06_primary_trajectory_completion_stops_before_session_execution():
    turns = [
        turn(buying_intent=False, customer="you look ridiculously hot tonight"),
        turn(buying_intent=False, customer="you're making it hard to behave"),
        turn(decision="PRESENT_OFFER", reason="DIRECT_PURCHASE_INTENT",
             intent="pi-1", offering="offering-1", buying_intent=True),
        turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
        turn(phase="DISCRETE_CONTINUATION", decision="PRESENT_OFFER",
             intent="pi-2", offering="offering-2", buying_intent=True),
        turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
        turn(phase="ONGOING_EXPERIENCE_CONTINUATION",
             escalation_row=escalation("PROPOSE_SESSION")),
        turn(phase="SESSION_PROPOSAL_REACTION",
             escalation_row=escalation(
                 "SESSION_ACCEPTED",
                 sessionProposalCustomerReaction="ACCEPT_OR_LEAN_IN",
             )),
    ]
    state = {
        "startingPurchaseCount": 0, "purchaseCount": 2, "ownershipCount": 2,
        "buyerStage": "REPEAT_BUYER", "activeBuyingWindow": {"active": True},
        "activeSession": None, "timeWasterRisk": "NONE",
        "failedOpportunityCount": 0,
    }
    result = Session5ScenarioRunner.c06_completion_evidence(turns, state)
    assert result["complete"] is True
    assert result["purchaseIntentIds"] == ["pi-1", "pi-2"]
    assert result["offeringIds"] == ["offering-1", "offering-2"]
    assert result["checks"]["sessionStartEligible"] is True
    assert result["checks"]["sessionNotStarted"] is True
    assert result["opportunityAccounting"]["failedOpportunities"] == 0
    assert result["earlyInterestTypes"] == ["FLIRTATION", "FLIRTATION"]


def test_c06_cannot_complete_with_one_purchase_or_started_session():
    incomplete = Session5ScenarioRunner.c06_completion_evidence([], {
        "purchaseCount": 1, "ownershipCount": 1, "buyerStage": "FIRST_TIME_BUYER",
        "activeBuyingWindow": {"active": True},
    })
    assert incomplete["complete"] is False
    assert incomplete["checks"]["twoProviderPurchases"] is False
    accepted = turn(
        phase="SESSION_PROPOSAL_REACTION",
        escalation_row=escalation("SESSION_ACCEPTED", sessionStarted=True),
    )
    started = Session5ScenarioRunner.c06_completion_evidence([accepted], {
        "purchaseCount": 2, "ownershipCount": 2, "buyerStage": "REPEAT_BUYER",
        "activeBuyingWindow": {"active": True}, "activeSession": {"id": "session"},
    })
    assert started["checks"]["sessionNotStarted"] is False


def test_acknowledgement_continuation_race_preserves_semantic_intent():
    projected = SessionEscalationDecisionService.project(
        active_buying_window=True, purchase_count=2, recent_purchase_count=2,
        current_message="", explicit_continuation_count=1,
        session_inventory_available=True, ordinary_inventory_available=True,
        deferred_continuation={
            "state": "READY", "continuationType": "ONGOING_EXPERIENCE",
        },
    )
    assert projected["currentContinuationIntent"] == "ONGOING_EXPERIENCE"
    assert projected["sessionEscalationDecision"] == "PROPOSE_SESSION"


def test_c06_next_action_is_evidence_driven_after_each_purchase():
    first_ack = Session5ScenarioRunner.c06_next_action([], {"purchaseCount": 1})
    assert first_ack["phase"] == "POST_PURCHASE_ACKNOWLEDGEMENT"
    more = Session5ScenarioRunner.c06_next_action(
        [turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True)],
        {"purchaseCount": 1},
    )
    assert more["phase"] == "DISCRETE_CONTINUATION"
    ongoing = Session5ScenarioRunner.c06_next_action(
        [turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
         turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True)],
        {"purchaseCount": 2},
    )
    assert ongoing["phase"] == "ONGOING_EXPERIENCE_CONTINUATION"
    acceptance = Session5ScenarioRunner.c06_next_action(
        [turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
         turn(phase="POST_PURCHASE_ACKNOWLEDGEMENT", acknowledged=True),
         turn(escalation_row=escalation("PROPOSE_SESSION"))],
        {"purchaseCount": 2},
    )
    assert acceptance["phase"] == "SESSION_PROPOSAL_REACTION"


def test_c06_presented_offer_requires_acceptance_before_simulation():
    presented = turn(
        decision="PRESENT_OFFER", reason="DIRECT_PURCHASE_INTENT",
        intent="pi-1", offering="offering-1", buying_intent=True,
    )
    action = Session5ScenarioRunner.c06_next_action(
        [presented], {"purchaseCount": 0},
    )
    assert action == {
        "kind": "ADAPTIVE", "phase": "OFFER_REACTION",
        "offer_reaction": "ACCEPT",
    }
    accepted = turn(accepted_intent="pi-1")
    action = Session5ScenarioRunner.c06_next_action(
        [presented, accepted], {"purchaseCount": 0},
    )
    assert action == {"kind": "SIMULATE_PURCHASE"}


def test_purchase_emulator_authority_is_exact_and_trajectory_independent():
    presented = turn(intent="pi-1", offering="offering-1")
    no_acceptance = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06", turns=[presented], purchase_intent_id="pi-1",
        purchase_intent_state="PRESENTED",
    )
    assert no_acceptance["simulatePurchaseEligible"] is False
    assert no_acceptance["simulatePurchaseEligibilityReason"] == (
        "CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"
    )

    accepted = turn(accepted_intent="pi-1")
    eligible = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06", turns=[presented, accepted],
        purchase_intent_id="pi-1", purchase_intent_state="PRESENTED",
    )
    assert eligible["simulatePurchaseEligible"] is True
    assert eligible["scenarioPurchaseAcceptanceSource"] == (
        "ADAPTIVE_OFFER_REACTION_ACCEPT"
    )

    wrong = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06", turns=[presented, accepted],
        purchase_intent_id="pi-2", purchase_intent_state="PRESENTED",
    )
    assert wrong["simulatePurchaseEligible"] is False
    assert wrong["authoritativePresentedPurchaseIntent"] is None

    created = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06", turns=[presented, accepted],
        purchase_intent_id="pi-1", purchase_intent_state="CREATED",
    )
    assert created["simulatePurchaseEligible"] is False
    assert created["simulatePurchaseEligibilityReason"] == (
        "TARGET_PURCHASE_INTENT_NOT_PRESENTED"
    )

    purchased = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C06", turns=[presented, accepted],
        purchase_intent_id="pi-1", purchase_intent_state="PURCHASED",
    )
    assert purchased["simulatePurchaseEligible"] is False


def test_c05_definition_is_not_ready_to_buy_from_the_start():
    c05 = CustomerScenarioHarness.definition("C05")
    c04 = CustomerScenarioHarness.definition("C04")
    c20 = CustomerScenarioHarness.definition("C20")
    assert c04.trajectory.value == "READY_TO_BUY"
    assert c05.trajectory.value == "SEXUAL_ONLY"
    assert definition().trajectory.value == "SEXUAL_ONLY"
    assert c20.trajectory.value == "CONTENT_CURIOUS"

    presented = turn(intent="pi-5", offering="offering-5")
    accepted = turn(accepted_intent="pi-5")
    authority = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C05", turns=[presented, accepted],
        purchase_intent_id="pi-5", purchase_intent_state="PRESENTED",
    )
    assert authority["simulatePurchaseEligible"] is True
    assert authority["scenarioPurchaseAcceptanceSource"] == (
        "ADAPTIVE_OFFER_REACTION_ACCEPT"
    )


def test_c04_direct_buyer_acceptance_remains_supported_without_trajectory_gate():
    presented = turn(intent="pi-4", offering="offering-4")
    acceptance = turn(customer="yeah, send it so I can unlock it")
    result = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C04", turns=[presented, acceptance],
        purchase_intent_id="pi-4", purchase_intent_state="PRESENTED",
    )
    assert result["simulatePurchaseEligible"] is True
    assert result["scenarioPurchaseAcceptanceSource"] == (
        "C04_CANONICAL_DIRECT_BUYER_ACCEPTANCE"
    )


def test_c20_non_telegram_session_settlement_contract_is_unchanged():
    result = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C20", turns=[], purchase_intent_id="session-pi",
        purchase_intent_state="PRESENTED", telegram_commerce=False,
    )
    assert result["simulatePurchaseEligible"] is True
    assert result["simulatePurchaseEligibilityReason"] == (
        "NON_TELEGRAM_COMMERCE_EXISTING_CONTRACT"
    )

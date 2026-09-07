from datetime import datetime, timezone
from threading import Event, Thread

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness, HistoricalPurchaseFixtureBuilder,
)
from app.testing.session5_scenario_runner import Session5ScenarioRunner
from app.testing.postgres_safety import Session5DatabasePurpose
from app.testing.adaptive_synthetic_customer import (
    AdaptiveSyntheticCustomerService, CustomerBehaviorPhase,
)
from app.services.customer_content_presentation_validator import (
    CustomerContentPresentationValidator,
)
from app.repositories.customer_abuse_review_repository import (
    CustomerAbuseReviewRepository,
)


pytestmark = pytest.mark.skipif(
    not __import__("os").getenv("SESSION5_RECOVERY_DATABASE_URL"),
    reason="SESSION5_RECOVERY_DATABASE_URL required",
)


@pytest.fixture
def runner():
    harness = CustomerScenarioHarness(
        certification_mode=True,
        database_purpose=Session5DatabasePurpose.AUTOMATED_RECOVERY,
    )
    instance = Session5ScenarioRunner(harness)
    for item in instance.list():
        if item["lifecycle"] in {"READY", "RUNNING", "COMPLETED", "FAILED", "SNAPSHOTTED"}:
            scenario = item["scenario"]
            with harness.connection() as connection:
                connection.execute(
                    "UPDATE certification_scenario_runs SET state='SNAPSHOTTED' WHERE scenario_id=%s",
                    (scenario,),
                )
            harness.reset(scenario)
    yield instance
    for item in instance.list():
        if item["lifecycle"] in {"READY", "RUNNING", "COMPLETED", "FAILED", "SNAPSHOTTED"}:
            with harness.connection() as connection:
                connection.execute(
                    "UPDATE certification_scenario_runs SET state='SNAPSHOTTED' "
                    "WHERE scenario_id=%s", (item["scenario"],),
                )
            harness.reset(item["scenario"])


def test_operator_workflow_preserves_turns_and_resets_cleanly(runner):
    listed = runner.list()
    assert len(listed) == 20 and listed[0]["name"] == "FRESH_SWEET_PROSPECT"
    prepared = runner.prepare("C01")
    assert prepared["startingState"]["purchaseCount"] == 0
    assert runner.status()["turnCount"] == 0

    with runner.harness.connection() as connection:
        scoped = connection.execute("""SELECT COUNT(*) AS total,
            COUNT(*) FILTER (WHERE status='READY' AND primary_sales_channel='AI_CHAT') AS ready
            FROM commercial_offerings
            WHERE creator_profile_id=(SELECT creator_profile_id
                FROM telegram_sales_prospects WHERE telegram_user_id=%s
                ORDER BY created_at DESC LIMIT 1)""", (
            runner.harness.customer_for(runner.harness.definition("C01")).telegram_user_id,
        )).fetchone()
    assert scoped["total"] >= 3
    assert scoped["ready"] >= 3

    first = runner.turn("Hey, how's your day going?")
    second = runner.turn("I spent the morning hiking with Charlie.")
    assert first["customer"] == "Hey, how's your day going?"
    assert first["testTransport"] == "TEST_TRANSPORT_NO_WAIT"
    assert first["telegramSent"] is False
    assert second["turnNumber"] > first["turnNumber"]
    assert runner.status()["turnCount"] == 2
    assert runner.analysis() == second["fullAnalysis"]

    defect = runner.defect("QUALITY", "Ava sounded overly polished.")
    assert defect["turn"] == 2
    complete = runner.complete("PASS_WITH_NOTES")
    assert complete["next"] == "SNAPSHOT"
    snap = runner.snapshot("C01")
    assert snap["lifecycle"] == "SNAPSHOTTED"
    reset = runner.reset("C01")
    assert reset["state"] == "VERIFIED_CLEAN"
    assert runner.verify_clean("C01")["result"] == "VERIFIED_CLEAN"

    next_scenario = runner.prepare("C02")
    assert next_scenario["startingState"]["purchaseCount"] == 0
    assert runner.status()["turnCount"] == 0


def test_initialization_reconciles_abuse_review_runtime_schema(runner):
    with runner.harness.connection() as connection:
        objects = connection.execute("""SELECT
            to_regclass('public.customer_abuse_review_incidents') AS incidents,
            to_regclass('public.operator_notification_operations') AS notifications
        """).fetchone()
        indexes = {
            row["indexname"] for row in connection.execute("""SELECT indexname
                FROM pg_indexes WHERE schemaname='public' AND indexname IN (
                    'customer_abuse_review_one_open_idx',
                    'customer_abuse_review_telegram_idx',
                    'operator_notification_recovery_idx',
                    'operator_notification_customer_review_idx'
                )""").fetchall()
        }

    assert objects["incidents"] == "customer_abuse_review_incidents"
    assert objects["notifications"] == "operator_notification_operations"
    assert indexes == {
        "customer_abuse_review_one_open_idx",
        "customer_abuse_review_telegram_idx",
        "operator_notification_recovery_idx",
        "operator_notification_customer_review_idx",
    }
    assert CustomerAbuseReviewRepository(
        connection_factory=runner.harness.connection,
    ).active_for_customer(
        creator_profile_id=0, fanvue_account_id=0, fanvue_user_id=0,
    ) is None


def test_false_claim_never_simulates_purchase_and_command_requires_intent(runner):
    runner.prepare("C04")
    turn = runner.turn("I bought it")
    assert turn["systemLogic"]["verifiedPurchase"] is False
    with pytest.raises(RuntimeError, match="exactly one scenario-owned PRESENTED"):
        runner.simulate_purchase()


def test_valid_simulated_purchase_uses_existing_provider_emulator(runner):
    runner.prepare("C04")
    offer = runner.turn("okay, how much is it?")
    assert offer["systemLogic"]["decision"] == "PRESENT_OFFER"
    assert offer["syntheticPpvPresentation"]["purchaseIntent"]["state"] == "PRESENTED"
    result = runner.simulate_purchase()
    assert result["provenance"] == "CERTIFICATION_SIMULATED_PROVIDER_EVENT"
    assert result["fanvueCalled"] is False
    assert result["before"]["purchaseCount"] == 0
    assert result["after"]["purchaseCount"] == 1
    assert result["after"]["ownershipCount"] == 1


def test_canonical_gateway_reaches_customer_initiated_active_offer_continuation(
        runner):
    """Exercise the same Gateway + persisted behavior composition as Scenario Lab."""
    runner.prepare("C04")
    first = runner.turn(
        "hey, do you have anything I can unlock?",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    intent_id = first["syntheticPpvPresentation"]["purchaseIntent"]["id"]

    price = runner.turn(
        "how much is it?", language_mode="DETERMINISTIC_CERTIFICATION",
    )
    link = runner.turn(
        "yeah, send me the link", language_mode="DETERMINISTIC_CERTIFICATION",
    )

    for turn, continuation_type in (
        (price, "PRICE_REQUEST"),
        (link, "SEND_OR_LINK_REQUEST"),
    ):
        analysis = turn["fullAnalysis"]
        current = analysis["currentOffer"]
        assert turn["systemLogic"]["decision"] == "NUDGE_ACTIVE_OFFER"
        assert turn["systemLogic"]["reason"] == (
            "CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION"
        )
        assert current["customerInitiatedOfferContinuation"] is True
        assert current["continuationIntentType"] == continuation_type
        assert current["nudgeCooldownApplies"] is False
        assert current["purchaseIntentReused"] is True
        assert current["structuredOfferReused"] is True
        assert current["structuredOfferRedelivered"] is True
        assert turn["syntheticPpvPresentation"]["purchaseIntent"]["id"] == intent_id
        assert CustomerContentPresentationValidator.numeric_price_present(
            turn["ava"]
        ) is False

    customer = runner.harness.customer_for(runner.harness.definition("C04"))
    with runner.harness.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) AS count FROM purchase_intents "
            "WHERE telegram_user_id=%s",
            (customer.telegram_user_id,),
        ).fetchone()["count"]
    assert count == 1


def test_canonical_synthetic_delivery_confirms_ack_and_unsticks_later_turns(
        runner):
    runner.prepare("C04")
    offer = runner.turn(
        "hey, do you have anything I can unlock?",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    intent_id = offer["syntheticPpvPresentation"]["purchaseIntent"]["id"]
    runner.simulate_purchase()

    acknowledgement = runner.turn(
        "okay, I just paid for it",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    analysis = acknowledgement["fullAnalysis"]
    assert acknowledgement["systemLogic"]["decision"] == "CONGRATULATE_PURCHASE"
    assert analysis["purchaseAcknowledgementAuthorized"] is True
    assert analysis["acknowledgementDeliveryOperation"]
    assert analysis["acknowledgementProviderConfirmed"] is True
    assert analysis["purchaseAcknowledgedAt"]
    assert analysis["purchaseAcknowledgementCompleted"] is True

    with runner.harness.connection() as connection:
        persisted = connection.execute(
            "SELECT purchase_acknowledged_at FROM purchase_intents "
            "WHERE purchase_intent_id=%s", (intent_id,),
        ).fetchone()
    assert persisted["purchase_acknowledged_at"] is not None

    feedback = runner.turn(
        "that was worth it", language_mode="DETERMINISTIC_CERTIFICATION",
    )
    next_offer = runner.turn(
        "what else have you got?", language_mode="DETERMINISTIC_CERTIFICATION",
    )
    assert feedback["systemLogic"]["decision"] != "CONGRATULATE_PURCHASE"
    assert next_offer["systemLogic"]["decision"] != "CONGRATULATE_PURCHASE"
    assert next_offer["systemLogic"]["decision"] in {
        "PRESENT_OFFER", "CROSS_SELL", "UPSELL",
    }, next_offer["systemLogic"]
    assert next_offer["syntheticPpvPresentation"] is not None, next_offer
    assert (
        next_offer["syntheticPpvPresentation"]["purchaseIntent"]["id"]
        != intent_id
    )


def test_fresh_attempt_replaces_runtime_but_preserves_prior_attempt_evidence(runner):
    first = runner.prepare("C04")
    inbound = "hey, how's your day going?"
    offer = runner.turn(inbound)
    builder = HistoricalPurchaseFixtureBuilder(runner.harness)
    base = builder._ensure_customer("C04")
    intent = builder._create_intent(
        "C04", base, index=1, amount_minor=900,
        purchased_at=datetime.now(timezone.utc), session=False,
    )
    purchase = builder.emulator.confirm(
        scenario_id="C04", purchase_intent_id=intent["purchase_intent_id"],
        amount_minor=900, currency="USD",
    )
    assert purchase["settlement"] is not None
    assert builder.derived_state("C04")["purchaseCount"] == 1
    assert builder.derived_state("C04")["ownershipCount"] == 1
    runner.complete("PASS")
    snapshot = runner.snapshot("C04")

    second = runner.prepare("C04")
    assert second["scenarioAttempt"] == first["scenarioAttempt"] + 1
    assert second["startingStateValidation"]["result"] == "VALIDATED"
    state = second["startingState"]
    assert state["buyerStatus"] == "NONBUYER"
    assert state["buyerStage"] == "PROSPECT"
    assert state["purchaseCount"] == 0
    assert state["lifetimeSpendMinor"] == 0
    assert state["ownershipCount"] == 0
    assert state["presentedOpportunityCount"] == 0
    assert state["convertedOpportunityCount"] == 0
    assert state["failedNonconvertedOpportunityCount"] == 0
    inventory = second["startingStateValidation"]["inventory"]["counts"]
    assert inventory["purchaseIntents"] == 0
    assert inventory["providerTransactions"] == 0
    assert inventory["ownership"] == 0
    assert inventory["identityMappings"] == 0
    assert inventory["behaviorEvents"] == 0
    assert inventory["ordinaryOperations"] == 0
    assert inventory["visibleMessages"] == 0
    historical = runner.recovery.historical_attempt_history(
        "C04", exclude_attempt=second["scenarioAttempt"],
    )
    assert any(
        row["scenario_attempt"] == first["scenarioAttempt"]
        and row["inbound"] == inbound
        and row["outbound"] == offer["ava"]
        for row in historical["turnAttempts"]
    )
    with runner.harness.connection() as connection:
        saved = connection.execute(
            "SELECT evidence FROM certification_scenario_snapshots WHERE snapshot_id=%s",
            (snapshot["snapshotId"],),
        ).fetchone()
    assert saved is not None
    assert saved["evidence"]["turns"][0]["inboundText"] == inbound


def test_zero_turn_failed_attempt_remains_allocated_after_snapshot_and_reset(runner):
    first = runner.prepare("C18")
    completed = runner.complete("FAIL")
    assert completed["certificationOutcome"] == "FAIL"
    assert completed["lifecycle"] == "FAILED"
    snapshot = runner.snapshot("C18")

    second = runner.prepare("C18")

    assert second["scenarioAttempt"] == first["scenarioAttempt"] + 1
    with runner.harness.connection() as connection:
        allocation = connection.execute("""SELECT status,snapshot_id
            FROM certification_scenario_attempt_allocations
            WHERE scenario_id='C18' AND scenario_attempt=%s""", (
                first["scenarioAttempt"],
            )).fetchone()
    assert allocation["status"] == "ARCHIVED"
    assert str(allocation["snapshot_id"]) == snapshot["snapshotId"]


def test_partial_certification_failure_is_terminal_and_snapshot_eligible(runner):
    prepared = runner.prepare("C02")
    runner.turn("hey")
    defect = runner.defect("MAJOR", "material failure on first turn", turn_number=1)
    completed = runner.complete("FAIL")

    assert defect["turn"] == 1
    assert completed["lifecycle"] == "FAILED"
    snapshot = runner.snapshot("C02")
    assert snapshot["lifecycle"] == "SNAPSHOTTED"
    assert prepared["scenarioAttempt"] > 0


def test_snapshot_rejects_genuinely_running_attempt(runner):
    runner.prepare("C03")
    with pytest.raises(RuntimeError, match="must be one of"):
        runner.snapshot("C03")


def test_c14_completed_batch_can_fail_at_turn_four_without_truncation(runner):
    first = runner.prepare("C14")
    for message in runner.harness.definition("C14").canonical_customer_turns:
        runner.turn(message)

    defect = runner.defect(
        "MAJOR", "foreground response defect discovered after batch",
        turn_number=4,
    )
    completed = runner.complete("FAIL")
    assert defect["turn"] == 4
    assert completed["lifecycle"] == "FAILED"
    assert len(runner._turns("C14")) == 7
    snapshot = runner.snapshot("C14")
    with runner.harness.connection() as connection:
        saved = connection.execute(
            "SELECT evidence FROM certification_scenario_snapshots WHERE snapshot_id=%s",
            (snapshot["snapshotId"],),
        ).fetchone()["evidence"]
    assert len(saved["turns"]) == 7
    assert saved["assessment"]["grade"] == "FAIL"
    assert saved["defects"][0]["turn_number"] == 4

    second = runner.prepare("C14")
    assert second["scenarioAttempt"] == first["scenarioAttempt"] + 1


def test_c13_pass_keeps_successful_terminal_lifecycle(runner):
    runner.prepare("C13")
    completed = runner.complete("PASS")
    assert completed["certificationOutcome"] == "PASS"
    assert completed["lifecycle"] == "COMPLETED"
    assert runner.snapshot("C13")["lifecycle"] == "SNAPSHOTTED"


def test_archived_attempt_nine_allocates_ten_without_turn_evidence(runner):
    with runner.harness.connection() as connection:
        connection.execute(
            "DELETE FROM certification_scenario_attempt_allocations WHERE scenario_id='C20'"
        )
        connection.execute(
            "DELETE FROM certification_scenario_attempts WHERE scenario_id='C20'"
        )
        connection.execute(
            "DELETE FROM certification_scenario_execution_leases WHERE scenario_id='C20'"
        )
        connection.execute(
            "DELETE FROM certification_scenario_turn_attempts WHERE scenario_id='C20'"
        )
        connection.execute(
            "UPDATE certification_scenario_runs SET scenario_attempt=1 WHERE scenario_id='C20'"
        )
        connection.execute("""INSERT INTO certification_scenario_attempt_allocations(
            scenario_id,scenario_attempt,status)
            VALUES ('C20',9,'ARCHIVED')
            ON CONFLICT(scenario_id,scenario_attempt) DO UPDATE
            SET status='ARCHIVED'""")

    prepared = runner.prepare("C20")

    assert prepared["scenarioAttempt"] == 10
    assert runner.status()["turnCount"] == 0


def test_attempt_allocation_is_monotonic_and_scenario_scoped(runner):
    with runner.harness.connection() as connection:
        c16_prior = connection.execute("""SELECT COALESCE(MAX(scenario_attempt),0) value
            FROM certification_scenario_attempt_allocations WHERE scenario_id='C16'""").fetchone()["value"]
        c17_prior = connection.execute("""SELECT COALESCE(MAX(scenario_attempt),0) value
            FROM certification_scenario_attempt_allocations WHERE scenario_id='C17'""").fetchone()["value"]
        c16_marker = int(c16_prior) + 40
        c17_marker = int(c17_prior) + 7
        connection.execute("""INSERT INTO certification_scenario_attempt_allocations(
            scenario_id,scenario_attempt,status) VALUES ('C16',%s,'ARCHIVED')""",
            (c16_marker,))
        connection.execute("""INSERT INTO certification_scenario_attempt_allocations(
            scenario_id,scenario_attempt,status) VALUES ('C17',%s,'ARCHIVED')""",
            (c17_marker,))

    c16 = runner.prepare("C16")
    assert c16["scenarioAttempt"] == c16_marker + 1
    runner.complete("FAIL")
    runner.snapshot("C16")
    c17 = runner.prepare("C17")
    assert c17["scenarioAttempt"] == c17_marker + 1


def test_empty_current_run_is_durable_allocation_and_cannot_be_reused(runner):
    prepared = runner.prepare("C15")
    first_attempt = prepared["scenarioAttempt"]

    runner.complete("FAIL")
    runner.snapshot("C15")
    replacement = runner.prepare("C15")

    assert replacement["scenarioAttempt"] == first_attempt + 1
    with runner.harness.connection() as connection:
        identities = connection.execute("""SELECT scenario_attempt,COUNT(*) total
            FROM certification_scenario_attempt_allocations WHERE scenario_id='C15'
            GROUP BY scenario_attempt HAVING COUNT(*) > 1""").fetchall()
    assert identities == []


@pytest.mark.parametrize("defects,turns,event", [
    ([{"severity": "MAJOR", "turn_number": 7, "note": "semantic defect"}], [7], None),
    ([{"materiality": "material", "logicalTurn": 3, "note": "semantic defect"}], [3], None),
    ([{"material": True, "turnNumber": 7, "note": "semantic defect"}], [7], None),
    ([{"severity": "CRITICAL", "turn_number": 0,
       "note": "FULL_SCENARIO_ANALYSIS failed"}], [], "FULL_SCENARIO_ANALYSIS"),
    ([{"severity": "QUALITY", "turn_number": 4, "note": "cosmetic"}], [], None),
])
def test_material_defect_projection_accepts_canonical_persisted_shapes(
        defects, turns, event):
    assert Session5ScenarioRunner._material_defect_projection(defects) == (
        turns, event,
    )


def test_fresh_customer_state_does_not_cross_scenario_identity(runner):
    runner.prepare("C04")
    builder = HistoricalPurchaseFixtureBuilder(runner.harness)
    base = builder._ensure_customer("C04")
    intent = builder._create_intent(
        "C04", base, index=1, amount_minor=900,
        purchased_at=datetime.now(timezone.utc), session=False,
    )
    assert builder.emulator.confirm(
        scenario_id="C04", purchase_intent_id=intent["purchase_intent_id"],
        amount_minor=900, currency="USD",
    )["settlement"] is not None
    runner.complete("PASS")
    runner.snapshot("C04")

    fresh = runner.prepare("C01")
    assert fresh["startingStateValidation"]["result"] == "VALIDATED"
    assert fresh["startingState"]["buyerStatus"] == "NONBUYER"
    assert fresh["startingState"]["purchaseCount"] == 0
    assert fresh["startingState"]["ownershipCount"] == 0
    assert fresh["startingStateValidation"]["inventory"]["counts"]["behaviorEvents"] == 0


def test_seeded_buyer_starting_state_is_exactly_rebuilt(runner):
    seeded = runner.prepare("C11")
    assert seeded["startingStateValidation"]["result"] == "VALIDATED"
    state = seeded["startingState"]
    assert state["buyerStatus"] == "VERIFIED_BUYER"
    assert state["purchaseCount"] == 1
    assert state["ownershipCount"] == 1
    inventory = seeded["startingStateValidation"]["inventory"]["counts"]
    assert inventory["purchaseIntents"] == 1
    assert inventory["providerTransactions"] == 1
    assert inventory["ownership"] == 1
    assert inventory["simulatedProviderEvents"] == 1


def test_c14_prepare_reproduces_authoritative_cooling_fixture(runner):
    prepared = runner.prepare("C14")
    state = prepared["startingState"]
    behavior = runner.harness.behavior_summary("C14")
    assert prepared["startingStateValidation"]["result"] == "VALIDATED"
    assert state["purchaseCount"] == state["ownershipCount"] == 1
    assert state["lifetimeSpendMinor"] == 1400
    assert 44.9 <= float(state["purchaseRecencyDays"]) <= 45.1
    assert (state["buyerStatus"], state["buyerStage"]) == (
        "VERIFIED_BUYER", "FIRST_TIME_BUYER",
    )
    assert state["retentionLifecycle"] == "COOLING_BUYER"
    assert state["retentionPriority"] == "NORMAL"
    assert state["attentionTier"] == "MEDIUM"
    assert state["effortMode"] == "COMPRESSED"
    assert state["relationshipInvestment"] == "WARM"
    assert state["memoryPriority"] == "ELEVATED"
    assert state["salesPressure"] == "LOW"
    assert state["offerCadence"] == "POST_PURCHASE_CAREFUL"
    assert state["timeWasterRisk"] == "NONE"
    assert state["activePurchaseIntent"] is None
    assert state["activeSession"] is None
    assert state["activeUnresolvedOpportunity"] is False
    assert behavior["inbound_message_count"] == 18
    assert behavior["offer_exposure_count"] == 4
    assert behavior["rejection_count"] == 0
    customer = runner.harness.customer_for(runner.harness.definition("C14"))
    with runner.harness.connection() as connection:
        intents = connection.execute(
            """SELECT status,expected_price_minor,purchased_at,
                      purchase_acknowledged_at
               FROM purchase_intents WHERE telegram_user_id=%s
               ORDER BY purchased_at NULLS LAST""",
            (customer.telegram_user_id,),
        ).fetchall()
        opportunity = connection.execute(
            """SELECT COUNT(*) FILTER (WHERE status='EXPIRED') AS failed,
                      BOOL_OR(status IN ('CREATED','PRESENTED','CLICKED')) AS active
               FROM purchase_intents WHERE telegram_user_id=%s""",
            (customer.telegram_user_id,),
        ).fetchone()
    intent = next(item for item in intents if item["status"] == "PURCHASED")
    assert intent["status"] == "PURCHASED"
    assert intent["expected_price_minor"] == 1400
    assert intent["purchase_acknowledged_at"] == intent["purchased_at"]
    assert opportunity["failed"] == 4
    assert opportunity["active"] is False

    assert tuple(runner.harness.definition("C14").canonical_customer_turns) == (
        "hey", "I've been busy and less online lately", "the last set was fine",
        "work has been taking most of my attention",
        "I'm mostly just catching up tonight",
        "I still like checking in with you",
        "I'll stop by again when things settle down",
    )


def test_c14_validation_rejects_fresh_purchase_fixture(runner):
    now = datetime.now(timezone.utc)
    builder = HistoricalPurchaseFixtureBuilder(runner.harness)
    builder.build("C14", [{"amount_minor": 1400, "purchased_at": now}])
    builder.add_eligible_inventory("C14", prices=(900, 1900, 2900))
    with pytest.raises(RuntimeError, match="SCENARIO_STARTING_STATE_VALIDATION_FAILED"):
        runner.harness.validate_starting_state(
            "C14", expected_purchase_count=1, now=now,
        )


def test_c14_validation_rejects_missing_commercial_history(runner):
    prepared = runner.prepare("C14")
    assert prepared["startingStateValidation"]["result"] == "VALIDATED"
    with runner.harness.connection() as connection:
        connection.execute(
            """DELETE FROM certification_scenario_behavior_events
               WHERE scenario_id='C14' AND event_type IN
                     ('OFFER_EXPOSURE','REJECTION')"""
        )
    with pytest.raises(RuntimeError, match="behavior.offer_exposure_count"):
        runner.harness.validate_starting_state(
            "C14", expected_purchase_count=1,
            now=datetime.now(timezone.utc),
        )


def test_c13_prepare_fixture_remains_unchanged(runner):
    prepared = runner.prepare("C13")
    state = prepared["startingState"]
    assert state["purchaseCount"] == state["ownershipCount"] == 2
    assert state["lifetimeSpendMinor"] == 3000
    assert state["buyerStage"] == "REPEAT_BUYER"
    assert runner.harness.behavior_summary("C13")["inbound_message_count"] == 0


@pytest.mark.parametrize("scenario,purchase_count", [
    ("C11", 1), ("C12", 1), ("C13", 2), ("C14", 1), ("C15", 3),
    ("C16", 5), ("C17", 5), ("C18", 1), ("C19", 1),
])
def test_every_seeded_scenario_validates_only_its_canonical_history(
        runner, scenario, purchase_count):
    seeded = runner.prepare(scenario)
    assert seeded["startingStateValidation"]["result"] == "VALIDATED"
    assert seeded["startingState"]["purchaseCount"] == purchase_count
    assert seeded["startingState"]["ownershipCount"] == purchase_count
    counts = seeded["startingStateValidation"]["inventory"]["counts"]
    assert counts["purchaseIntents"] == (5 if scenario == "C14" else purchase_count)
    assert counts["providerTransactions"] == purchase_count
    assert counts["simulatedProviderEvents"] == purchase_count


def test_simulated_purchase_rejects_intent_without_presented_ppv(runner):
    runner.prepare("C04")
    base = HistoricalPurchaseFixtureBuilder(runner.harness)._ensure_customer("C04")
    HistoricalPurchaseFixtureBuilder(runner.harness)._create_intent(
        "C04", base, index=1, amount_minor=900,
        purchased_at=datetime.now(timezone.utc), session=False,
    )
    with pytest.raises(RuntimeError, match="canonically presented structured PPV"):
        runner.simulate_purchase()


def test_adaptive_offer_reaction_uses_structured_ppv_and_gates_purchase(runner):
    runner.prepare("C02")
    offer = runner.turn("okay, how much is it?")
    assert offer["syntheticPpvPresentation"]["price"] in {"$9.00", "$19.00", "$29.00"}
    with pytest.raises(RuntimeError, match="CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"):
        runner.simulate_purchase()
    service = AdaptiveSyntheticCustomerService()
    phase = CustomerBehaviorPhase.OFFER_REACTION
    with pytest.raises(RuntimeError, match="ACCEPT_REQUIRES_VALID_OBJECTION_RESPONSE"):
        runner.adaptive_turn(
            phase=phase,
            constraints=service.constraints_for("C02", phase, offer_reaction="ACCEPT"),
            phase_transition_reason="INVALID_PREMATURE_ACCEPTANCE",
        )
    hesitation = runner.adaptive_turn(
        phase=phase,
        constraints=service.constraints_for("C02", phase, offer_reaction="HESITATE"),
        phase_transition_reason="TEST_HESITATION",
    )
    assert hesitation["adaptiveCustomer"]["validation_result"]["derivedSignals"][
        "offerAcceptance"
    ] is False
    acceptance = runner.adaptive_turn(
        phase=phase,
        constraints=service.constraints_for("C02", phase, offer_reaction="ACCEPT"),
        phase_transition_reason="TEST_ACCEPTANCE",
    )
    assert acceptance["adaptiveCustomer"]["validation_result"]["derivedSignals"][
        "offerAcceptance"
    ] is True
    assert acceptance["scenarioPurchaseEmulator"][
        "simulatePurchaseEligible"
    ] is True
    assert acceptance["scenarioPurchaseEmulator"][
        "purchaseEmulatorTargetIntent"
    ] == offer["syntheticPpvPresentation"]["purchaseIntent"]["id"]
    result = runner.simulate_purchase()
    assert result["after"]["purchaseCount"] == 1
    analysis = runner.full_attempt_analysis("C02")
    assert analysis["turns"][0]["customer"] == "okay, how much is it?"
    assert analysis["turns"][0]["syntheticPpvPresentation"]["purchaseIntent"]["id"]


def _c13_purchase_claim_eligibility(**overrides):
    intent_id = "00000000-0000-0000-0000-000000000013"
    offering_id = "00000000-0000-0000-0000-000000000113"
    turn = {
        "customer": "I bought it",
        "syntheticPpvPresentation": {
            "offeringId": offering_id,
            "priceMinor": 900,
            "currency": "USD",
            "purchaseIntent": {"id": intent_id, "state": "PRESENTED"},
        },
        "fullAnalysis": {
            "currentOffer": {
                "activePurchaseIntentId": intent_id,
                "activeOfferingId": offering_id,
            },
            "purchaseCommerceState": {
                "customerPurchaseClaimDetected": True,
                "conversationalPurchaseClaim": True,
                "providerPurchaseVerified": False,
                "purchaseOwnershipVerified": False,
                "activePurchaseIntentId": intent_id,
                "activePurchaseIntentState": "PRESENTED",
                "purchaseIntentStatus": "PRESENTED",
            },
            "conversationStyle": {"purchaseOwnershipGrounding": {
                "customerPurchaseClaimDetected": True,
                "providerPurchaseVerified": False,
            }},
            "commerceLifecycleConfirmation": {
                "structuredPresentationConfirmed": True,
            },
        },
    }
    values = {
        "scenario_id": "C13", "turns": [turn],
        "purchase_intent_id": intent_id,
        "purchase_intent_state": "PRESENTED",
        "telegram_commerce": True,
        "purchase_intent_offering_id": offering_id,
        "expected_price_minor": 900, "expected_currency": "USD",
        "presented_intent_count": 1,
        "target_already_owned": False,
        "prior_provider_settlement": False,
    }
    values.update(overrides)
    return Session5ScenarioRunner.purchase_emulator_eligibility(**values)


def test_c13_exact_purchase_claim_authorizes_only_synthetic_provider_emulation():
    authority = _c13_purchase_claim_eligibility()
    assert authority["simulatePurchaseEligible"] is True
    assert authority["scenarioPurchaseAcceptanceSource"] == (
        "C13_CANONICAL_EXACT_PURCHASE_CLAIM"
    )
    assert authority["purchaseEmulatorTargetIntent"] == (
        "00000000-0000-0000-0000-000000000013"
    )


@pytest.mark.parametrize("override", [
    {"purchase_intent_id": "00000000-0000-0000-0000-000000000099"},
    {"purchase_intent_offering_id": "00000000-0000-0000-0000-000000000099"},
    {"purchase_intent_state": "PURCHASED"},
    {"presented_intent_count": 2},
    {"target_already_owned": True},
    {"prior_provider_settlement": True},
    {"expected_price_minor": 901},
])
def test_c13_purchase_claim_rejects_broken_authoritative_binding(override):
    assert _c13_purchase_claim_eligibility(
        **override
    )["simulatePurchaseEligible"] is False


@pytest.mark.parametrize("message", [
    "I might buy it", "I bought something", "I paid for another thing",
])
def test_c13_purchase_claim_rejects_noncanonical_or_ambiguous_wording(message):
    intent_id = "00000000-0000-0000-0000-000000000013"
    offering_id = "00000000-0000-0000-0000-000000000113"
    result = _c13_purchase_claim_eligibility(turns=[{
        "customer": message,
        "syntheticPpvPresentation": {
            "offeringId": offering_id, "priceMinor": 900, "currency": "USD",
            "purchaseIntent": {"id": intent_id, "state": "PRESENTED"},
        },
        "fullAnalysis": {
            "currentOffer": {"activePurchaseIntentId": intent_id,
                             "activeOfferingId": offering_id},
            "purchaseCommerceState": {
                "customerPurchaseClaimDetected": True,
                "conversationalPurchaseClaim": True,
                "providerPurchaseVerified": False,
                "purchaseOwnershipVerified": False,
                "activePurchaseIntentId": intent_id,
                "activePurchaseIntentState": "PRESENTED",
                "purchaseIntentStatus": "PRESENTED",
            },
            "conversationStyle": {"purchaseOwnershipGrounding": {
                "customerPurchaseClaimDetected": True,
                "providerPurchaseVerified": False,
            }},
            "commerceLifecycleConfirmation": {
                "structuredPresentationConfirmed": True,
            },
        },
    }])
    assert result["simulatePurchaseEligible"] is False


def test_c13_purchase_claim_rejects_unconfirmed_structured_presentation():
    result = _c13_purchase_claim_eligibility()
    # Rebuild through the public helper with the confirmed diagnostic absent.
    assert _c13_purchase_claim_eligibility(turns=[{
        **{
            "customer": "I bought it",
            "syntheticPpvPresentation": {
                "offeringId": "00000000-0000-0000-0000-000000000113",
                "priceMinor": 900, "currency": "USD",
                "purchaseIntent": {
                    "id": "00000000-0000-0000-0000-000000000013",
                    "state": "PRESENTED",
                },
            },
        },
        "fullAnalysis": {},
    }])["simulatePurchaseEligible"] is False
    assert result["simulatePurchaseEligible"] is True


def test_c10_exact_offer_continuation_emulator_authority_is_unchanged():
    intent_id = "00000000-0000-0000-0000-000000000010"
    offering_id = "00000000-0000-0000-0000-000000000110"
    authority = Session5ScenarioRunner.purchase_emulator_eligibility(
        scenario_id="C10",
        purchase_intent_id=intent_id,
        purchase_intent_state="PRESENTED",
        turns=[{
            "customer": "send the link",
            "syntheticPpvPresentation": {
                "offeringId": offering_id,
                "purchaseIntent": {"id": intent_id, "state": "PRESENTED"},
            },
            "salesBrainFullAnalysis": {
                "currentOffer": {
                    "customerInitiatedOfferContinuation": True,
                    "continuationIntentType": "SEND_OR_LINK_REQUEST",
                    "reuseRequested": True,
                    "redeliveryAuthorized": True,
                    "purchaseIntentReuseEligible": True,
                    "structuredOfferReused": True,
                    "structuredOfferRedelivered": True,
                    "purchaseIntentReused": True,
                    "activePurchaseIntentId": intent_id,
                    "activeOfferingId": offering_id,
                },
                "purchaseCommerceState": {
                    "activePurchaseIntentId": intent_id,
                    "purchaseIntentStatus": "PRESENTED",
                },
                "commerceLifecycleConfirmation": {
                    "structuredPresentationConfirmed": True,
                    "deliveryState": "CONFIRMED",
                },
            },
        }],
    )
    assert authority["simulatePurchaseEligible"] is True
    assert authority["scenarioPurchaseAcceptanceSource"] == (
        "C10_CANONICAL_EXACT_OFFER_CONTINUATION"
    )


def test_c13_canonical_claim_settles_exact_third_offer_and_acknowledges_it(runner):
    runner.prepare("C13")
    definition = runner.harness.definition("C13")
    turns = [runner.turn(
        message, language_mode="DETERMINISTIC_CERTIFICATION",
    ) for message in definition.canonical_customer_turns[:7]]
    presentations = [
        turn["syntheticPpvPresentation"] for turn in turns
        if turn.get("syntheticPpvPresentation")
    ]
    assert presentations
    presented = presentations[-1]
    claim = turns[-1]
    assert claim["customer"] == "I bought it"
    commerce = claim["fullAnalysis"]["purchaseCommerceState"]
    assert commerce["customerPurchaseClaimDetected"] is True
    assert commerce["conversationalPurchaseClaim"] is True
    assert commerce["providerPurchaseVerified"] is False
    assert commerce["purchaseOwnershipVerified"] is False

    result = runner.simulate_purchase()
    assert result["purchaseIntentId"] == presented["purchaseIntent"]["id"]
    assert result["purchaseEmulatorAuthority"][
        "scenarioPurchaseAcceptanceSource"
    ] == "C13_CANONICAL_EXACT_PURCHASE_CLAIM"
    assert result["before"]["purchaseCount"] == 2
    assert result["before"]["ownershipCount"] == 2
    assert result["after"]["purchaseCount"] == 3
    assert result["after"]["ownershipCount"] == 3
    assert result["after"]["lifetimeSpendMinor"] == 3900

    acknowledgement = runner.turn(
        definition.canonical_customer_turns[7],
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    analysis = acknowledgement["fullAnalysis"]
    settled_commerce = analysis["purchaseCommerceState"]
    assert settled_commerce["providerPurchaseVerified"] is True
    assert settled_commerce["firstPurchaseSemanticsAuthorized"] is False
    assert analysis["purchaseAcknowledgementAuthorized"] is True
    assert analysis["purchaseAcknowledgementCompleted"] is True
    assert analysis["purchaseAcknowledgedAt"]


def test_c06_exact_presented_intent_acceptance_settles_once(runner):
    runner.prepare("C06")
    runner.turn(
        "you look ridiculously hot tonight",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    runner.turn(
        "you're making it hard to behave",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    offer = runner.turn(
        "okay, I want to see something private I can unlock",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    intent_id = offer["syntheticPpvPresentation"]["purchaseIntent"]["id"]
    with pytest.raises(RuntimeError, match="CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"):
        runner.simulate_purchase()

    service = AdaptiveSyntheticCustomerService()
    accepted = runner.adaptive_turn(
        phase=CustomerBehaviorPhase.OFFER_REACTION,
        constraints=service.constraints_for(
            "C06", CustomerBehaviorPhase.OFFER_REACTION,
            offer_reaction="ACCEPT",
        ),
        phase_transition_reason="C06_EXACT_PRESENTED_INTENT_ACCEPTANCE",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    authority = accepted["scenarioPurchaseEmulator"]
    assert authority["simulatePurchaseEligible"] is True
    assert authority["purchaseEmulatorTargetIntent"] == intent_id
    assert authority["scenarioPurchaseAcceptanceSource"] == (
        "ADAPTIVE_OFFER_REACTION_ACCEPT"
    )

    purchased = runner.simulate_purchase()
    assert purchased["purchaseIntentId"] == intent_id
    assert purchased["before"]["purchaseCount"] == 0
    assert purchased["after"]["purchaseCount"] == 1
    assert purchased["after"]["ownershipCount"] == 1
    assert purchased["purchaseEmulatorAuthority"] == authority
    with pytest.raises(RuntimeError, match="exactly one scenario-owned PRESENTED"):
        runner.simulate_purchase()

    customer = runner.harness.customer_for(runner.harness.definition("C06"))
    with runner.harness.connection() as connection:
        rows = connection.execute(
            "SELECT purchase_intent_id,status FROM purchase_intents "
            "WHERE telegram_user_id=%s", (customer.telegram_user_id,),
        ).fetchall()
    assert [(str(row["purchase_intent_id"]), row["status"]) for row in rows] == [
        (intent_id, "PURCHASED")
    ]


def test_c06_second_presented_intent_requires_its_own_acceptance(runner):
    runner.prepare("C06")
    runner.turn(
        "you look ridiculously hot tonight",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    runner.turn(
        "you're making it hard to behave",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    first_offer = runner.turn(
        "okay, I want to see something private I can unlock",
        language_mode="DETERMINISTIC_CERTIFICATION",
    )
    service = AdaptiveSyntheticCustomerService()
    runner.adaptive_turn(
        phase=CustomerBehaviorPhase.OFFER_REACTION,
        constraints=service.constraints_for(
            "C06", CustomerBehaviorPhase.OFFER_REACTION,
            offer_reaction="ACCEPT",
        ),
        phase_transition_reason="C06_FIRST_ACCEPTANCE",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    first = runner.simulate_purchase()
    assert first["purchaseIntentId"] == first_offer[
        "syntheticPpvPresentation"
    ]["purchaseIntent"]["id"]

    runner.adaptive_turn(
        phase=CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT,
        constraints=service.constraints_for(
            "C06", CustomerBehaviorPhase.POST_PURCHASE_ACKNOWLEDGEMENT,
        ),
        phase_transition_reason="C06_FIRST_PURCHASE_CONFIRMED",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    second_offer = runner.adaptive_turn(
        phase=CustomerBehaviorPhase.DISCRETE_CONTINUATION,
        constraints=service.constraints_for(
            "C06", CustomerBehaviorPhase.DISCRETE_CONTINUATION,
        ),
        phase_transition_reason="C06_REQUEST_SECOND_DISCRETE_PPV",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    second_intent_id = second_offer[
        "syntheticPpvPresentation"
    ]["purchaseIntent"]["id"]
    assert second_intent_id != first["purchaseIntentId"]
    with pytest.raises(RuntimeError, match="CANONICAL_CUSTOMER_ACCEPTANCE_REQUIRED"):
        runner.simulate_purchase()

    accepted = runner.adaptive_turn(
        phase=CustomerBehaviorPhase.OFFER_REACTION,
        constraints=service.constraints_for(
            "C06", CustomerBehaviorPhase.OFFER_REACTION,
            offer_reaction="ACCEPT",
        ),
        phase_transition_reason="C06_SECOND_ACCEPTANCE",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    assert accepted["scenarioPurchaseEmulator"][
        "purchaseEmulatorTargetIntent"
    ] == second_intent_id
    second = runner.simulate_purchase()
    assert second["purchaseIntentId"] == second_intent_id
    assert second["after"]["purchaseCount"] == 2
    assert second["after"]["ownershipCount"] == 2

    customer = runner.harness.customer_for(runner.harness.definition("C06"))
    with runner.harness.connection() as connection:
        rows = connection.execute(
            "SELECT purchase_intent_id,status FROM purchase_intents "
            "WHERE telegram_user_id=%s ORDER BY created_at",
            (customer.telegram_user_id,),
        ).fetchall()
    assert [row["status"] for row in rows] == ["PURCHASED", "PURCHASED"]
    assert {str(row["purchase_intent_id"]) for row in rows} == {
        first["purchaseIntentId"], second_intent_id,
    }


def test_adaptive_customer_audit_persists_in_canonical_attempt_analysis(runner):
    runner.prepare("C07")
    service = AdaptiveSyntheticCustomerService()
    constraints = service.constraints_for("C07", CustomerBehaviorPhase.QUIET_LOW_RETURN)
    turn = runner.adaptive_turn(
        phase=CustomerBehaviorPhase.QUIET_LOW_RETURN,
        constraints=constraints,
        phase_transition_reason="SCENARIO_OPENING",
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    full = runner.full_attempt_analysis("C07")
    audit = full["turns"][0]["adaptiveCustomer"]
    assert turn["telegramSent"] is False
    assert audit["behavioral_phase"] == "QUIET_LOW_RETURN"
    assert audit["customer_constraints"]["engagement"] == "LOW"
    assert audit["previous_ava_response"] == ""
    assert audit["validation_result"]["structuredTruthUnchanged"] is True
    assert audit["provider_metadata"]["hiddenReasoningPersisted"] is False


def test_c03_terminal_backoff_prevents_adaptive_resurrection(runner):
    runner.prepare("C03")
    turn = runner.turn("Nothing. Just leave me alone.")
    assert turn["systemLogic"]["decision"] == "BACK_OFF"
    tone = turn["fullAnalysis"]["contextualCustomerTone"]
    assert tone["explicitDisengagement"] is True
    assert tone["hostilityLevel"] in {"HIGH", "SEVERE"}
    service = AdaptiveSyntheticCustomerService()
    with pytest.raises(RuntimeError, match="SCENARIO_TERMINAL_BACKOFF"):
        runner.adaptive_turn(
            phase=CustomerBehaviorPhase.QUIET_LOW_RETURN,
            constraints=service.constraints_for(
                "C03", CustomerBehaviorPhase.QUIET_LOW_RETURN,
            ),
            phase_transition_reason="MUST_NOT_CONTINUE",
        )


def test_full_canonical_execution_owns_attempt_and_rejects_second_request(
        runner, monkeypatch):
    runner.prepare("C03")
    entered = Event()
    release = Event()
    calls = []

    def blocked_owned(message, **kwargs):
        calls.append(message)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        return {"turnNumber": len(calls), "customer": message}

    monkeypatch.setattr(runner, "_turn_owned", blocked_owned)
    result = {}
    thread = Thread(target=lambda: result.setdefault("value", runner.execute_canonical()))
    thread.start()
    assert entered.wait(5)

    status = runner.status()["execution"]
    assert status["state"] == "RUNNING_AND_OWNED"
    assert status["requestedStartTurn"] == 1
    assert status["requestedEndTurn"] == 7
    assert status["continuationPermitted"] is False
    with pytest.raises(RuntimeError, match="EXECUTION_ALREADY_IN_PROGRESS"):
        runner.turn("must not advance")
    with pytest.raises(RuntimeError, match="EXECUTION_ALREADY_IN_PROGRESS"):
        runner.retry_previous_turn("must not overlap canonical execution")

    release.set()
    thread.join(10)
    assert not thread.is_alive()
    assert result["value"]["completedTurns"] == 7
    assert calls == list(runner.harness.definition("C03").canonical_customer_turns)


def test_canonical_turn_limit_blocks_n_plus_one_without_mutation(runner, monkeypatch):
    runner.prepare("C03")
    monkeypatch.setattr(runner.recovery, "next_logical_turn", lambda *_: 8)
    with pytest.raises(RuntimeError, match="CANONICAL_SCENARIO_COMPLETE"):
        runner.turn("must not become turn eight")
    with pytest.raises(RuntimeError, match="CANONICAL_SCENARIO_COMPLETE"):
        runner.execute_canonical()
    assert runner.harness.behavior_summary("C03")["inbound_message_count"] == 0


def test_stale_execution_is_explicitly_recoverable(runner):
    prepared = runner.prepare("C03")
    attempt = prepared["scenarioAttempt"]
    owner = runner.recovery.claim_execution(
        "C03", attempt, requested_start_turn=1, requested_end_turn=7,
        lease_seconds=-1,
    )
    status = runner.status()["execution"]
    assert status["state"] == "FAILED_STALE_OWNER"
    assert status["continuationPermitted"] is False
    with pytest.raises(RuntimeError, match="STALE_EXECUTION_REQUIRES_RECOVERY"):
        runner.recovery.claim_execution(
            "C03", attempt, requested_start_turn=1, requested_end_turn=7,
        )
    recovered = runner.recover_stale_execution()
    assert recovered == {
        "state": "STALE_OWNER_RECOVERED",
        "restoredPreTurn": None,
        "continuationPermitted": True,
    }
    replacement = runner.recovery.claim_execution(
        "C03", attempt, requested_start_turn=1, requested_end_turn=7,
    )
    assert replacement != owner
    runner.recovery.release_execution("C03", attempt, replacement, failed=True)


def test_failed_owned_execution_creates_no_phantom_turn(runner, monkeypatch):
    runner.prepare("C03")
    monkeypatch.setattr(
        runner, "_turn_owned",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("synthetic crash")),
    )
    with pytest.raises(RuntimeError, match="synthetic crash"):
        runner.turn("not persisted")
    assert runner.status()["turnCount"] == 0
    assert runner.harness.behavior_summary("C03")["inbound_message_count"] == 0
    assert runner.status()["execution"]["state"] == "FAILED"


def test_zero_turn_provider_failure_retains_safe_pre_turn_retry_boundary(
        runner, monkeypatch):
    prepared = runner.prepare("C03")
    attempt = prepared["scenarioAttempt"]
    original_execute = runner.harness.execute_turn
    calls = []

    def fail_then_succeed(scenario_id, message, **kwargs):
        calls.append(dict(kwargs))
        if len(calls) == 1:
            raise RuntimeError("synthetic provider connection failure")
        # Exercise the deterministic runtime while proving that the retry
        # preserved the operator-requested language mode at its boundary.
        assert kwargs["language_mode"] == "REAL_AVA_LANGUAGE"
        evidence = original_execute(
            scenario_id, message,
            **{**kwargs, "language_mode": "DETERMINISTIC_CERTIFICATION"},
        )
        evidence["syntheticProvider"].update({
            "syntheticProviderMode": "REAL_AVA_LANGUAGE",
            "liveProviderCalled": True,
        })
        return evidence

    monkeypatch.setattr(runner.harness, "execute_turn", fail_then_succeed)
    with pytest.raises(RuntimeError, match="synthetic provider connection failure"):
        runner.turn(
            "hey", language_mode="REAL_AVA_LANGUAGE",
            require_language_mode=True,
        )

    failed = runner.recovery.latest_failed_precommit_turn("C03", attempt)
    assert failed is not None
    assert failed["logical_turn"] == 1
    assert failed["inbound"] == "hey"
    assert runner.status()["execution"]["lastCompletedLogicalTurn"] == 0

    recovered = runner.turn(
        "hey", language_mode="REAL_AVA_LANGUAGE",
        require_language_mode=True,
    )
    assert recovered["turnNumber"] == 1
    assert recovered["customer"] == "hey"
    assert recovered["telegramSent"] is False
    assert len(calls) == 2

    rows = runner.recovery.turn_attempt_rows("C03", attempt)
    assert [(row["turn_attempt"], row["status"]) for row in rows] == [
        (1, "SUPERSEDED_BY_RETRY"),
        (2, "CURRENT"),
    ]
    summary = runner.harness.behavior_summary("C03")
    assert summary["inbound_message_count"] == 1
    assert runner.status()["execution"]["lastCompletedLogicalTurn"] == 1


def test_c15_run_canonical_provider_failure_stops_at_turn_one(
        runner, monkeypatch):
    prepared = runner.prepare("C15")
    attempt = prepared["scenarioAttempt"]
    calls = []

    def provider_failure(scenario_id, message, **kwargs):
        calls.append((scenario_id, message, kwargs))
        raise RuntimeError("mocked C15 provider failure")

    monkeypatch.setattr(runner.harness, "execute_turn", provider_failure)
    with pytest.raises(RuntimeError, match="mocked C15 provider failure"):
        runner.execute_canonical()

    assert [(scenario, message) for scenario, message, _ in calls] == [
        ("C15", "hey Ava"),
    ]
    assert calls[0][2]["language_mode"] == "REAL_AVA_LANGUAGE"
    rows = runner.recovery.turn_attempt_rows("C15", attempt)
    assert [
        (row["logical_turn"], row["turn_attempt"], row["status"],
         row["inbound"], row["outbound"])
        for row in rows
    ] == [(1, 1, "FAILED_PRE_COMMIT", "hey Ava", "")]
    assert runner.recovery.next_logical_turn("C15", attempt) == 1
    analysis = runner.full_attempt_analysis("C15")
    assert analysis["scenario"]["canonicalTurnCount"] == 0
    assert analysis["scenario"]["lastCompletedLogicalTurn"] == 0
    assert analysis["turns"] == []
    assert analysis["attemptAudit"]["failedExecutionAttempts"][0]["status"] == (
        "FAILED_PRE_COMMIT"
    )
    state = analysis["finalAccumulatedState"]
    assert state["inboundMessageCount"] == 0
    assert state["derivedState"]["purchaseCount"] == 3
    assert state["derivedState"]["ownershipCount"] == 3
    assert state["derivedState"]["lifetimeSpendMinor"] == 15003
    assert state["derivedState"]["activePurchaseIntent"] is None


def test_two_precommit_failures_allocate_third_attempt_once(runner, monkeypatch):
    prepared = runner.prepare("C03")
    attempt = prepared["scenarioAttempt"]
    original_execute = runner.harness.execute_turn
    calls = 0

    def fail_twice(scenario_id, message, **kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError(f"provider failure {calls}")
        evidence = original_execute(
            scenario_id, message,
            **{**kwargs, "language_mode": "DETERMINISTIC_CERTIFICATION"},
        )
        evidence["syntheticProvider"].update({
            "syntheticProviderMode": "REAL_AVA_LANGUAGE",
            "liveProviderCalled": True,
        })
        return evidence

    monkeypatch.setattr(runner.harness, "execute_turn", fail_twice)
    for expected in ("provider failure 1", "provider failure 2"):
        with pytest.raises(RuntimeError, match=expected):
            runner.turn(
                "hey", language_mode="REAL_AVA_LANGUAGE",
                require_language_mode=True,
            )
    result = runner.turn(
        "hey", language_mode="REAL_AVA_LANGUAGE", require_language_mode=True,
    )

    rows = runner.recovery.turn_attempt_rows("C03", attempt)
    assert [(row["turn_attempt"], row["status"]) for row in rows] == [
        (1, "SUPERSEDED_BY_RETRY"),
        (2, "SUPERSEDED_BY_RETRY"),
        (3, "CURRENT"),
    ]
    assert result["turnNumber"] == 1
    assert result["turnAttempt"] == 3
    assert runner.harness.behavior_summary("C03")["inbound_message_count"] == 1
    assert len(runner.recovery.current_outbound_transcript("C03", attempt)) == 1
    assert runner.harness.starting_state_inventory("C03")["counts"][
        "ordinaryOperations"
    ] == 1

    with pytest.raises(RuntimeError, match="LOGICAL TURN ALREADY COMMITTED"):
        runner.retry_previous_turn("must not duplicate committed turn")


def test_concurrent_turn_attempt_allocation_is_unique(runner):
    prepared = runner.prepare("C03")
    attempt = prepared["scenarioAttempt"]
    allocated = []
    failures = []

    def allocate():
        try:
            allocated.append(
                runner.recovery.allocate_turn_attempt("C03", attempt, 1)
            )
        except Exception as error:
            failures.append(error)

    workers = [Thread(target=allocate), Thread(target=allocate)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(10)

    assert not failures
    assert sorted(allocated) == [1, 2]


def test_repeated_post_backoff_abuse_is_audited_without_fake_outbound(runner):
    # C07 is only an isolated synthetic identity here; this is not a C03 rerun.
    runner.prepare("C07")
    boundary = runner.turn("I'm not interested. Stop wasting my time.")
    assert boundary["systemLogic"]["decision"] == "BACK_OFF"
    assert boundary["fullAnalysis"]["contextualCustomerTone"][
        "explicitDisengagement"
    ] is True

    suppressed = runner.turn("Answer me. Your nonsense is disgusting.")
    assert suppressed["ava"] == ""
    suppression = suppressed["fullAnalysis"]["outboundSuppression"]
    assert suppression["outcome"] == "NO_RESPONSE"
    assert suppression["inboundProcessingRequired"] is True
    assert suppressed["systemLogic"]["decision"] == "BACK_OFF"
    assert suppressed["customerValue"]["attentionTier"] == "LOW"
    assert suppressed["customerValue"]["effortMode"] == "MINIMAL"
    assert suppressed["syntheticProvider"]["liveProviderCalled"] is False

    another = runner.turn("What, scared? Keep answering me.")
    assert another["ava"] == ""
    assert another["systemLogic"]["decision"] == "BACK_OFF"
    assert another["customerValue"]["attentionTier"] == "LOW"
    assert another["customerValue"]["effortMode"] == "MINIMAL"
    full = runner.full_attempt_analysis("C07")
    assert [turn["customer"] for turn in full["turns"]] == [
        "I'm not interested. Stop wasting my time.",
        "Answer me. Your nonsense is disgusting.",
        "What, scared? Keep answering me.",
    ]
    assert [turn["ava"] for turn in full["turns"]][1:] == ["", ""]
    assert runner.status()["state"]["purchaseCount"] == 0


def test_sexual_runtime_evidence_accumulates_once_and_stays_noncommercial(runner):
    runner.prepare("C05")
    first = runner.turn("you look hot and you're making my thoughts dirty")
    second = runner.turn("honestly, my thoughts about you are getting naughty")
    summary = runner.harness.behavior_summary("C05")
    assert first["fullAnalysis"]["contextualCustomerTone"]["sexualOrProvocative"] is True
    assert second["fullAnalysis"]["contextualCustomerTone"]["sexualOrProvocative"] is True
    assert summary["sexual_engagement_count"] == 2
    assert summary["sexual_engagement_only"] is True
    assert summary["commercial_movement"] is False
    state = runner.status()["state"]
    assert state["buyerStatus"] == "NONBUYER"
    assert state["purchaseCount"] == 0
    assert state["activePurchaseIntent"] is None


def test_c05_post_delivery_projection_drives_next_adaptive_customer(runner):
    prepared = runner.prepare("C05")
    fixed = runner.harness.definition("C05").canonical_customer_turns
    turns = []
    for message in fixed:
        turn = runner.turn(
            message, language_mode="DETERMINISTIC_CERTIFICATION",
        )
        turns.append(turn)
        sexual = turn["fullAnalysis"]["sexualCommercialProgression"]
        if sexual.get("adaptiveSwitchEligible") is True:
            break

    assert prepared["scenarioAttempt"] >= 1
    assert turns[-1]["fullAnalysis"]["sexualCommercialProgression"] == {
        **turns[-1]["fullAnalysis"]["sexualCommercialProgression"],
        "commercialTeaseDelivered": True,
        "commercialTeaseExposureRecorded": True,
        "progressionFinalizedAfterDelivery": True,
        "adaptiveSwitchEligible": True,
        "adaptiveSwitchReason": "CONFIRMED_CUSTOMER_VISIBLE_COMMERCIAL_TEASE",
    }
    projections = runner._current_attempt_turn_projections(
        "C05", prepared["scenarioAttempt"],
    )
    action = runner.c05_next_action(
        projections, runner.builder.derived_state("C05"), fixed_messages=fixed,
    )
    assert action["kind"] == "ADAPTIVE"
    assert action["phase"] == "COMMERCIAL_CURIOSITY"

    service = AdaptiveSyntheticCustomerService()
    adaptive = runner.adaptive_turn(
        phase=CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        constraints=service.constraints_for(
            "C05", CustomerBehaviorPhase.COMMERCIAL_CURIOSITY,
        ),
        phase_transition_reason=action["adaptive_switch_reason"],
        language_mode="DETERMINISTIC_CERTIFICATION",
        customer_service=service,
    )
    assert adaptive["adaptiveCustomer"]["behavioral_phase"] == (
        "COMMERCIAL_CURIOSITY"
    )
    assert adaptive["adaptiveCustomer"]["wording_source"].startswith(
        "DETERMINISTIC_PHASE_SAFE_FALLBACK"
    )
    assert adaptive["adaptiveCustomer"]["validation_result"]["valid"] is True
    assert adaptive["adaptiveCustomer"]["validation_result"][
        "derivedSignals"
    ]["buyingIntent"] is False


def test_behavior_event_idempotency_key_prevents_sexual_double_count(runner):
    runner.prepare("C05")
    event = {
        "type": "INBOUND",
        "message": "a noncommercial provocative test message",
        "idempotency_key": "inbound:certified-one",
        "evidence": {
            "sexual_engagement": True,
            "commercial_movement": False,
        },
    }
    runner.harness.record_behavior_history("C05", [event])
    runner.harness.record_behavior_history("C05", [event])
    summary = runner.harness.behavior_summary("C05")
    assert summary["inbound_message_count"] == 1
    assert summary["sexual_engagement_count"] == 1

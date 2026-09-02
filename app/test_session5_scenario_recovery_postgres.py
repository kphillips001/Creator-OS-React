import json

import pytest

from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness, HistoricalPurchaseFixtureBuilder,
    DETERMINISTIC_CERTIFICATION,
)
from app.testing.session5_scenario_runner import Session5ScenarioRunner
from app.testing.postgres_safety import Session5DatabasePurpose


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
    value = Session5ScenarioRunner(harness)
    for item in value.list():
        if item["lifecycle"] in {"READY", "RUNNING", "COMPLETED", "SNAPSHOTTED"}:
            with harness.connection() as c:
                c.execute("UPDATE certification_scenario_runs SET state='SNAPSHOTTED' WHERE scenario_id=%s", (item["scenario"],))
            harness.reset(item["scenario"])
    yield value


def test_retry_restores_exact_pre_turn_state_and_preserves_attempts(runner):
    runner.prepare("C01")
    first = runner.turn("First exact message")
    state_after_first = runner.builder.derived_state("C01")
    runner.turn("Second exact message")
    retried = runner.retry_previous_turn("response repair")
    history = runner.recovery.attempt_history("C01")["turnAttempts"]
    assert first["customer"] == "First exact message"
    assert retried["customer"] == "Second exact message"
    assert retried["turnNumber"] == 2 and retried["turnAttempt"] == 2
    assert [(row["logical_turn"], row["turn_attempt"], row["status"]) for row in history] == [
        (1, 1, "CURRENT"), (2, 1, "SUPERSEDED_BY_RETRY"), (2, 2, "CURRENT")]
    assert len(runner._turns("C01")) == 2
    assert runner.harness.behavior_summary("C01")["inbound_message_count"] == 2
    assert state_after_first["purchaseCount"] == runner.builder.derived_state("C01")["purchaseCount"]


def test_repeated_retry_keeps_one_current_attempt(runner):
    runner.prepare("C02")
    runner.turn("Same punctuation! 😊")
    runner.retry_previous_turn()
    runner.retry_previous_turn()
    rows = runner.recovery.attempt_history("C02")["turnAttempts"]
    assert [(row["turn_attempt"], row["status"], row["inbound"]) for row in rows] == [
        (1, "SUPERSEDED_BY_RETRY", "Same punctuation! 😊"),
        (2, "SUPERSEDED_BY_RETRY", "Same punctuation! 😊"),
        (3, "CURRENT", "Same punctuation! 😊")]
    assert runner.harness.behavior_summary("C02")["inbound_message_count"] == 1


def test_duplicate_recovery_operation_identity_is_idempotent(runner):
    runner.prepare("C01")
    runner.turn("First")
    runner.turn("Second")
    first = runner.retry_previous_turn(
        "response repair", recovery_operation_id="recovery-operation-0001",
    )
    duplicate = runner.retry_previous_turn(
        "network replay", recovery_operation_id="recovery-operation-0001",
    )
    rows = runner.recovery.attempt_history("C01")["turnAttempts"]
    assert first["turnNumber"] == duplicate["turnNumber"] == 2
    assert duplicate["idempotentRecoveryReplay"] is True
    assert [(row["logical_turn"], row["turn_attempt"], row["status"]) for row in rows] == [
        (1, 1, "CURRENT"), (2, 1, "SUPERSEDED_BY_RETRY"), (2, 2, "CURRENT")]
    assert runner.harness.behavior_summary("C01")["inbound_message_count"] == 2


def test_certified_duplicate_advance_recovery_preserves_evidence_and_restores_turn_two(runner):
    runner.prepare("C01")
    runner.turn("First")
    duplicate_text = "Second exact message"
    runner.turn(duplicate_text)
    runner.retry_previous_turn("response repair", recovery_operation_id="recovery-operation-0002")
    runner.turn(duplicate_text)
    assert runner.harness.behavior_summary("C01")["inbound_message_count"] == 3
    result = runner.recover_duplicate_retry_advance()
    history = runner.recovery.attempt_history("C01")["turnAttempts"]
    assert result["restoredLogicalTurn"] == 2
    assert result["archivedDuplicateLogicalTurn"] == 3
    assert result["inboundMessageCount"] == 2
    assert [(row["logical_turn"], row["turn_attempt"], row["status"]) for row in history] == [
        (1, 1, "CURRENT"),
        (2, 1, "SUPERSEDED_BY_RETRY"),
        (2, 2, "CURRENT"),
        (3, 1, "ABORTED_DUPLICATE_RETRY_ADVANCE"),
    ]
    assert len(runner._turns("C01")) == 2
    snapshot = runner.operator_snapshot()
    assert len(snapshot["turns"]) == 2
    assert len(snapshot["transcript"]) == 4
    assert snapshot["turns"][-1]["turnNumber"] == 2
    assert snapshot["turns"][-1]["turnAttempt"] == 2
    full = runner.full_attempt_analysis()
    assert [(turn["logicalTurn"], turn["turnAttempt"], turn["status"])
            for turn in full["turns"]] == [(1, 1, "CURRENT"), (2, 2, "CURRENT")]
    assert all(turn["evidenceStatus"] == "MATCHED" for turn in full["turns"])
    assert all(turn["salesBrainFullAnalysis"] for turn in full["turns"])
    assert not any(turn["logicalTurn"] == 3 for turn in full["turns"])
    audit = full["attemptAudit"]["currentAttempt"]["turnAttempts"]
    assert any(row["status"] == "SUPERSEDED_BY_RETRY" for row in audit)
    assert any(row["status"] == "ABORTED_DUPLICATE_RETRY_ADVANCE" for row in audit)


def test_full_attempt_analysis_is_read_only_and_attempt_scoped(runner):
    runner.prepare("C01")
    runner.turn("Old attempt turn")
    runner.restart_scenario("C01", "new attempt")
    runner.turn("Current turn one")
    runner.turn("Current turn two")
    with runner.harness.connection() as connection:
        before = connection.execute("""SELECT md5(COALESCE(string_agg(value,'|' ORDER BY value),'')) AS state_hash
            FROM (SELECT 'run:'||row_to_json(t)::text value FROM certification_scenario_runs t
            UNION ALL SELECT 'turn:'||row_to_json(t)::text FROM certification_scenario_turn_attempts t
            UNION ALL SELECT 'evidence:'||row_to_json(t)::text FROM certification_scenario_turn_evidence t
            UNION ALL SELECT 'checkpoint:'||row_to_json(t)::text FROM certification_scenario_checkpoints t) x""").fetchone()["state_hash"]
    full = runner.full_attempt_analysis()
    with runner.harness.connection() as connection:
        after = connection.execute("""SELECT md5(COALESCE(string_agg(value,'|' ORDER BY value),'')) AS state_hash
            FROM (SELECT 'run:'||row_to_json(t)::text value FROM certification_scenario_runs t
            UNION ALL SELECT 'turn:'||row_to_json(t)::text FROM certification_scenario_turn_attempts t
            UNION ALL SELECT 'evidence:'||row_to_json(t)::text FROM certification_scenario_turn_evidence t
            UNION ALL SELECT 'checkpoint:'||row_to_json(t)::text FROM certification_scenario_checkpoints t) x""").fetchone()["state_hash"]
    assert before == after
    assert [turn["customer"] for turn in full["turns"]] == ["Current turn one", "Current turn two"]
    assert "Old attempt turn" not in str(full["turns"])
    assert full["scenario"]["canonicalTurnCount"] == 2
    assert full["databaseEnvironment"]["purpose"] == "AUTOMATED_RECOVERY"


def test_completed_automated_attempt_remains_readable_without_mutation(runner):
    runner.prepare("C02")
    runner.turn("hey")
    runner.complete("FAIL")
    with runner.harness.connection() as connection:
        before = connection.execute(
            "SELECT state FROM certification_scenario_runs WHERE scenario_id='C02'"
        ).fetchone()["state"]
    full = runner.full_attempt_analysis()
    with runner.harness.connection() as connection:
        after = connection.execute(
            "SELECT state FROM certification_scenario_runs WHERE scenario_id='C02'"
        ).fetchone()["state"]
    assert before == after == "COMPLETED"
    assert full["scenario"]["lifecycle"] == "COMPLETED"
    assert full["scenario"]["canonicalTurnCount"] == 1
    assert full["turns"][0]["customer"] == "hey"


def test_full_attempt_analysis_withholds_missing_or_ambiguous_evidence(runner):
    runner.prepare("C01")
    result = runner.turn("Exact canonical inbound")
    with runner.harness.connection() as connection:
        original = connection.execute("""SELECT * FROM certification_scenario_turn_evidence
            WHERE scenario_id='C01'""").fetchone()
        connection.execute("DELETE FROM certification_scenario_turn_evidence WHERE correlation_id=%s",
                           (original["correlation_id"],))
    missing = runner.full_attempt_analysis()["turns"][0]
    assert missing["evidenceStatus"] == "UNAVAILABLE"
    assert missing["gatewayDiagnostics"] is None
    with runner.harness.connection() as connection:
        connection.execute("""INSERT INTO certification_scenario_turn_evidence(
            correlation_id,scenario_id,telegram_user_id,inbound,outbound,full_analysis,created_at)
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s),(%s,%s,%s,%s,%s,%s::jsonb,%s)""", (
                "ambiguous-one", original["scenario_id"], original["telegram_user_id"],
                original["inbound"], original["outbound"], json.dumps(original["full_analysis"]), original["created_at"],
                "ambiguous-two", original["scenario_id"], original["telegram_user_id"],
                original["inbound"], original["outbound"], json.dumps(original["full_analysis"]), original["created_at"],
            ))
    ambiguous = runner.full_attempt_analysis()["turns"][0]
    assert ambiguous["evidenceStatus"] == "AMBIGUOUS"
    assert ambiguous["gatewayDiagnostics"] is None
    assert ambiguous["customer"] == result["customer"]


def test_retry_restores_and_recreates_customer_disclosure_memory_once(runner):
    runner.prepare("C01")
    message = (
        "Haha maybe a little 😂 I'm usually pretty quiet at first though. "
        "Takes me a minute to warm up to somebody."
    )
    runner.turn(message)
    retried = runner.retry_previous_turn("customer-memory repair")
    telegram_id = runner.harness.customer_for(
        runner.harness.definition("C01")
    ).telegram_user_id
    with runner.harness.connection() as connection:
        row = connection.execute(
            "SELECT preference_state FROM telegram_sales_prospects "
            "WHERE telegram_user_id=%s ORDER BY telegram_sales_prospect_id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()
    records = [record for record in dict(row["preference_state"] or {}).get("records", [])
               if record.get("status") == "current" and record.get("key") == "social_style"]
    assert retried["customer"] == message
    assert retried["turnAttempt"] == 2
    assert len(records) == 1
    assert records[0]["value"] == "quiet at first and takes time to warm up"


def test_retry_preserves_prior_trait_and_recreates_turn_five_interests_once(runner):
    runner.prepare("C01")
    runner.turn("I'm usually pretty quiet at first. Takes me a minute to warm up to somebody.")
    turn_five = "I'm kinda an outdoors person 😂 hiking, camping, stuff like that."
    runner.turn(turn_five)
    retried = runner.retry_previous_turn("interest-memory repair")
    telegram_id = runner.harness.customer_for(runner.harness.definition("C01")).telegram_user_id
    with runner.harness.connection() as connection:
        row = connection.execute(
            "SELECT preference_state FROM telegram_sales_prospects "
            "WHERE telegram_user_id=%s ORDER BY telegram_sales_prospect_id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()
    records = [record for record in dict(row["preference_state"] or {}).get("records", [])
               if record.get("status") == "current"]
    keys = [record["key"] for record in records]
    assert retried["customer"] == turn_five and retried["turnAttempt"] == 2
    assert keys.count("social_style") == 1
    assert keys.count("outdoors") == 1
    assert keys.count("hiking") == 1
    assert keys.count("camping") == 1


def test_retry_exact_turn_six_restores_memories_and_replays_once(runner):
    runner.prepare("C01")
    runner.turn("I'm usually pretty quiet at first. Takes me a minute to warm up to somebody.")
    runner.turn("I'm kinda an outdoors person - hiking, camping, stuff like that.")
    turn_six = "See - told you I warm up eventually. I could talk about hiking forever."
    runner.turn(turn_six)
    retried = runner.retry_previous_turn("memory callback repair")
    telegram_id = runner.harness.customer_for(runner.harness.definition("C01")).telegram_user_id
    with runner.harness.connection() as connection:
        row = connection.execute(
            "SELECT preference_state FROM telegram_sales_prospects "
            "WHERE telegram_user_id=%s ORDER BY telegram_sales_prospect_id DESC LIMIT 1",
            (telegram_id,),
        ).fetchone()
    keys = [item["key"] for item in dict(row["preference_state"] or {}).get("records", [])
            if item.get("status") == "current"]
    assert retried["customer"] == turn_six
    assert retried["turnAttempt"] == 2
    assert retried["fullAnalysis"]["memoryCallback"]["memoryCallbackUsed"] is True
    assert keys.count("social_style") == 1
    assert keys.count("outdoors") == 1
    assert keys.count("hiking") == 1
    assert keys.count("camping") == 1


def test_restart_archives_attempt_and_returns_same_scenario_to_turn_zero(runner):
    prepared = runner.prepare("C03")
    original = prepared["startingState"]
    expected_attempt = prepared["scenarioAttempt"] + 1
    runner.turn("One")
    runner.turn("Two")
    result = runner.restart_scenario("C03", "contaminated trajectory")
    snapshot = runner.operator_snapshot()
    assert result["scenarioAttempt"] == expected_attempt
    assert snapshot["activeScenario"]["scenario"] == "C03"
    assert snapshot["activeScenario"]["scenarioAttempt"] == expected_attempt
    assert snapshot["turns"] == [] and snapshot["transcript"] == []
    assert snapshot["activeScenario"]["state"] == original
    archived = snapshot["recovery"]["historicalScenarioAttempts"]["scenarioAttempts"]
    assert any(
        row["scenario_attempt"] == prepared["scenarioAttempt"]
        and row["status"] == "ABORTED_FOR_REPAIR"
        for row in archived
    )


def test_failed_c05_restart_is_targeted_preserves_attempt_and_rebuilds_clean(runner):
    prepared = runner.prepare("C05")
    failed_attempt = prepared["scenarioAttempt"]
    for message in ("sexual turn one", "sexual turn two", "sexual turn three"):
        runner.turn(message, language_mode=DETERMINISTIC_CERTIFICATION)
    owner = runner.recovery.claim_execution(
        "C05", failed_attempt, requested_start_turn=4, requested_end_turn=4,
    )
    runner.recovery.release_execution(
        "C05", failed_attempt, owner,
        failed=True, reason="NameError: preserved synthetic failure",
    )
    with runner.harness.connection() as connection:
        other_before = [dict(row) for row in connection.execute("""SELECT scenario_id,state,
            scenario_attempt,updated_at FROM certification_scenario_runs
            WHERE scenario_id=ANY(%s) ORDER BY scenario_id""", (
                ["C01", "C02", "C03", "C04"],
            )).fetchall()]

    restarted = runner.restart_scenario("C05", "failed attempt certification")
    assert restarted["scenarioAttempt"] == failed_attempt + 1
    assert restarted["startingStateValidation"]["result"] == "VALIDATED"
    assert restarted["startingStateValidation"]["inventory"]["counts"]["visibleMessages"] == 0
    assert restarted["startingStateValidation"]["inventory"]["counts"]["behaviorEvents"] == 0
    assert restarted["startingState"]["buyerStatus"] == "NONBUYER"
    assert restarted["startingState"]["purchaseCount"] == 0
    assert restarted["startingState"]["ownershipCount"] == 0
    assert restarted["startingState"]["timeWasterRisk"] == "NONE"
    assert runner._current_attempt_turn_projections(
        "C05", restarted["scenarioAttempt"],
    ) == []

    with runner.harness.connection() as connection:
        archived = connection.execute("""SELECT evidence,status FROM certification_scenario_attempts
            WHERE scenario_id='C05' AND scenario_attempt=%s""", (failed_attempt,)).fetchone()
        other_after = [dict(row) for row in connection.execute("""SELECT scenario_id,state,
            scenario_attempt,updated_at FROM certification_scenario_runs
            WHERE scenario_id=ANY(%s) ORDER BY scenario_id""", (
                ["C01", "C02", "C03", "C04"],
            )).fetchall()]
    assert archived["status"] == "ABORTED_FOR_REPAIR"
    archived_evidence = dict(archived["evidence"] or {})
    assert len(archived_evidence.get("turns") or ()) == 3
    assert archived_evidence["execution"]["executionState"] == "FAILED"
    assert archived_evidence["execution"]["lastCompletedLogicalTurn"] == 3
    assert "preserved synthetic failure" in archived_evidence["execution"]["failureReason"]
    assert archived_evidence["execution"]["ownerId"]
    assert other_after == other_before


def test_restart_prepare_failure_leaves_retryable_clean_boundary(runner, monkeypatch):
    prepared = runner.prepare("C05")
    failed_attempt = prepared["scenarioAttempt"]
    runner.turn("one", language_mode=DETERMINISTIC_CERTIFICATION)
    original_prepare = runner.prepare
    monkeypatch.setattr(
        runner, "prepare",
        lambda _scenario_id: (_ for _ in ()).throw(RuntimeError("injected prepare failure")),
    )
    with pytest.raises(RuntimeError, match="during prepare"):
        runner.restart_scenario("C05", "failure injection")
    assert runner._run("C05")["state"] == "VERIFIED_CLEAN"
    with runner.harness.connection() as connection:
        count = connection.execute("""SELECT COUNT(*) AS value
            FROM certification_scenario_attempts WHERE scenario_id='C05'
              AND scenario_attempt=%s AND status='ABORTED_FOR_REPAIR'""", (
                failed_attempt,
            )).fetchone()["value"]
    assert count == 1

    monkeypatch.setattr(runner, "prepare", original_prepare)
    retried = runner.restart_scenario("C05", "retry same durable boundary")
    assert retried["scenarioAttempt"] == failed_attempt + 1
    with runner.harness.connection() as connection:
        count_after = connection.execute("""SELECT COUNT(*) AS value
            FROM certification_scenario_attempts WHERE scenario_id='C05'
              AND scenario_attempt=%s AND status='ABORTED_FOR_REPAIR'""", (
                failed_attempt,
            )).fetchone()["value"]
    assert count_after == 1


def test_restart_is_blocked_when_another_scenario_owns_execution_slot(runner):
    runner.prepare("C06")
    with pytest.raises(RuntimeError, match="Active scenario C06 blocks restart of C05"):
        runner.restart_scenario("C05")
    assert runner._run("C06")["state"] == "RUNNING"


def test_restart_does_not_prepare_after_clean_verification_failure(runner, monkeypatch):
    runner.prepare("C04")
    runner.turn("One")
    monkeypatch.setattr(runner, "verify_clean", lambda *_: {"result": "RESET_INCOMPLETE"})
    with pytest.raises(RuntimeError, match="SCENARIO RESTART FAILED"):
        runner.restart_scenario("C04")
    assert runner._active(optional=True) is None


def test_retry_is_blocked_after_simulated_purchase(runner):
    runner.prepare("C05")
    runner.turn("Show me")
    base = HistoricalPurchaseFixtureBuilder(runner.harness)._ensure_customer("C05")
    HistoricalPurchaseFixtureBuilder(runner.harness)._create_intent(
        "C05", base, index=1, amount_minor=900, purchased_at=None, session=False)
    runner.simulate_purchase()
    with pytest.raises(RuntimeError, match="SYNTHETIC PURCHASE BOUNDARY"):
        runner.retry_previous_turn()

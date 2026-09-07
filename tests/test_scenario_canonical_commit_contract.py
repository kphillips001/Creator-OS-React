from types import SimpleNamespace

import pytest

from app.testing.session5_scenario_harness import (
    REAL_AVA_LANGUAGE, CanonicalScenarioEvent,
)
from app.testing.session5_scenario_runner import Session5ScenarioRunner


def _evidence(*, response="hello", called=True, delivered=True,
              suppressed=False):
    reason = "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED" if suppressed else None
    return {
        "finalResponseText": response,
        "syntheticProvider": {
            "syntheticProviderMode": REAL_AVA_LANGUAGE,
            "liveProviderCalled": called,
        },
        "testTransportCustomerVisibleConfirmed": delivered,
        "SalesBrainFullAnalysis": {
            "authoritativeIntentionalSuppression": suppressed,
            "outboundSuppression": {"reason": reason} if reason else {},
        },
    }


def test_real_ava_provider_failure_cannot_commit_empty_turn():
    with pytest.raises(RuntimeError, match="REAL_AVA_LANGUAGE_NOT_HONORED"):
        Session5ScenarioRunner._require_canonical_turn_commit(
            _evidence(response="", called=False, delivered=False),
            language_mode=REAL_AVA_LANGUAGE,
            require_language_mode=True,
        )


def test_unblocked_empty_output_cannot_commit():
    with pytest.raises(RuntimeError, match="empty response"):
        Session5ScenarioRunner._require_canonical_turn_commit(
            _evidence(response="", called=True, delivered=False),
            language_mode=REAL_AVA_LANGUAGE,
            require_language_mode=True,
        )


def test_generated_response_requires_synthetic_delivery_confirmation():
    with pytest.raises(RuntimeError, match="delivery confirmation"):
        Session5ScenarioRunner._require_canonical_turn_commit(
            _evidence(delivered=False),
            language_mode=REAL_AVA_LANGUAGE,
            require_language_mode=True,
        )


def test_authoritative_intentional_suppression_is_a_valid_silent_turn():
    Session5ScenarioRunner._require_canonical_turn_commit(
        _evidence(
            response="", called=False, delivered=False, suppressed=True,
        ),
        language_mode=REAL_AVA_LANGUAGE,
        require_language_mode=True,
    )


def _batch_runner(fail_at):
    runner = Session5ScenarioRunner.__new__(Session5ScenarioRunner)
    messages = tuple(f"message {number}" for number in range(1, 8))
    runner._active = lambda **_kwargs: {"scenario_id": "C15"}
    runner.harness = SimpleNamespace(
        definition=lambda _scenario: SimpleNamespace(
            canonical_customer_turns=messages,
            canonical_turn_count=7,
        ),
    )
    releases = []
    runner.recovery = SimpleNamespace(
        scenario_attempt=lambda _scenario: 3,
        next_logical_turn=lambda *_args: 1,
        claim_execution=lambda *_args, **_kwargs: "owner",
        release_execution=lambda *_args, **kwargs: releases.append(kwargs),
    )
    calls = []

    def execute(message, **kwargs):
        calls.append((message, kwargs))
        if len(calls) == fail_at:
            raise RuntimeError("provider failed pre-commit")
        return {"turnNumber": len(calls)}

    runner._turn_owned = execute
    return runner, calls, releases


@pytest.mark.parametrize("fail_at,completed", ((1, 0), (3, 2)))
def test_canonical_batch_stops_at_first_failed_turn(fail_at, completed):
    runner, calls, releases = _batch_runner(fail_at)

    with pytest.raises(RuntimeError, match="provider failed pre-commit"):
        runner.execute_canonical()

    assert len(calls) == completed + 1
    assert all(
        call[1]["require_language_mode"] is True for call in calls
    )
    assert releases == [{
        "failed": True,
        "reason": "RuntimeError: provider failed pre-commit",
    }]


def test_canonical_turn_event_turn_executes_in_order():
    runner = Session5ScenarioRunner.__new__(Session5ScenarioRunner)
    event = CanonicalScenarioEvent("settle", "SYNTHETIC_PROVIDER_SETTLEMENT", 1)
    runner._active = lambda **_kwargs: {"scenario_id": "C16"}
    runner.harness = SimpleNamespace(definition=lambda _scenario: SimpleNamespace(
        canonical_customer_turns=("one", "two"), canonical_turn_count=2,
        canonical_events=(event,),
    ))
    runner.recovery = SimpleNamespace(
        scenario_attempt=lambda _scenario: 2,
        next_logical_turn=lambda *_args: 1,
        claim_execution=lambda *_args, **_kwargs: "owner",
        release_execution=lambda *_args, **_kwargs: None,
    )
    order = []
    runner._turn_owned = lambda message, **_kwargs: (
        order.append(f"TURN:{message}") or {"customer": message}
    )
    runner._dispatch_canonical_event = lambda value: (
        order.append(f"EVENT:{value.event_id}") or {"status": "COMMITTED"}
    )

    runner.execute_canonical()

    assert order == ["TURN:one", "EVENT:settle", "TURN:two"]


def test_required_canonical_event_failure_prevents_next_turn():
    runner, calls, _releases = _batch_runner(fail_at=99)
    event = CanonicalScenarioEvent("settle", "SYNTHETIC_PROVIDER_SETTLEMENT", 1)
    runner.harness.definition = lambda _scenario: SimpleNamespace(
        canonical_customer_turns=("one", "two"), canonical_turn_count=2,
        canonical_events=(event,),
    )
    runner._dispatch_canonical_event = lambda _event: (_ for _ in ()).throw(
        RuntimeError("event failed")
    )

    with pytest.raises(RuntimeError, match="event failed"):
        runner.execute_canonical()

    assert [call[0] for call in calls] == ["one"]


def test_settlement_event_commit_validates_durable_aggregate_deltas():
    runner = Session5ScenarioRunner.__new__(Session5ScenarioRunner)
    event = CanonicalScenarioEvent("settle", "SYNTHETIC_PROVIDER_SETTLEMENT", 6)
    runner._committed_canonical_settlement = lambda _event: None
    runner._simulate_purchase = lambda **_kwargs: {
        "purchaseIntentId": "intent-1",
        "commercialOfferingId": "offering-1",
        "providerEventId": "event-1",
        "transactionRecorded": True,
        "provenance": "CERTIFICATION_SIMULATED_PROVIDER_EVENT",
        "committedIntent": {"status": "PURCHASED", "purchasedAt": "now",
                            "commercialOfferingId": "offering-1",
                            "expectedPriceMinor": 2900,
                            "expectedCurrency": "USD"},
        "before": {"purchaseCount": 5, "ownershipCount": 5,
                   "lifetimeSpendMinor": 50010},
        "after": {"purchaseCount": 6, "ownershipCount": 6,
                  "lifetimeSpendMinor": 52910,
                  "activePurchaseIntent": None},
        "purchaseEmulatorAuthority": {"expectedPriceMinor": 2900,
                                      "expectedCurrency": "USD",
                                      "purchaseEmulatorTargetIntent": "intent-1"},
    }

    result = runner._dispatch_canonical_event(event)

    assert result["status"] == "COMMITTED"
    assert all(result["checks"].values())


def test_settlement_event_replay_is_idempotent():
    runner = Session5ScenarioRunner.__new__(Session5ScenarioRunner)
    event = CanonicalScenarioEvent("settle", "SYNTHETIC_PROVIDER_SETTLEMENT", 6)
    runner._committed_canonical_settlement = lambda _event: {
        "purchaseIntentId": "intent-1",
    }
    runner._simulate_purchase = lambda **_kwargs: pytest.fail(
        "settlement must not run twice"
    )

    result = runner._dispatch_canonical_event(event)

    assert result["status"] == "ALREADY_COMMITTED"


def test_last_completed_logical_turn_is_independent_of_certification_outcome():
    projections = [
        {"logicalTurn": number, "status": "CURRENT"}
        for number in range(1, 9)
    ]
    assert Session5ScenarioRunner._last_completed_logical_turn(projections) == 8
    assert Session5ScenarioRunner._last_completed_logical_turn(
        projections[:4]
    ) == 4
    assert Session5ScenarioRunner._last_completed_logical_turn([]) == 0


class _AnalysisResult:
    def __init__(self, *, one=None, many=()):
        self.one = one
        self.many = list(many)

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class _AnalysisConnection:
    def __init__(self, assessment):
        self.assessment = assessment
        self.statements = []

    def execute(self, statement, _params):
        normalized = " ".join(statement.split()).lower()
        self.statements.append(normalized)
        assert normalized.startswith("select ")
        if "from telegram_sales_prospects" in normalized:
            return _AnalysisResult(one={
                "relationship_state": {}, "preference_state": {},
                "inbound_message_count": 8, "first_observed_at": None,
                "last_observed_at": None,
            })
        if "from purchase_intents" in normalized:
            return _AnalysisResult(many=())
        if "from sales_sessions" in normalized:
            return _AnalysisResult(many=())
        if "from certification_simulated_provider_events" in normalized:
            return _AnalysisResult(many=())
        if "from certification_scenario_assessments" in normalized:
            return _AnalysisResult(
                one={"grade": self.assessment} if self.assessment else None
            )
        raise AssertionError(f"unexpected analysis query: {normalized}")


class _ConnectionScope:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_args):
        return False


def _full_analysis_runner(*, assessment, turns=8, lifecycle="SNAPSHOTTED",
                          defects=()):
    runner = Session5ScenarioRunner.__new__(Session5ScenarioRunner)
    connection = _AnalysisConnection(assessment)
    runner._inspectable = lambda _scenario: {
        "scenario_id": "C16", "state": lifecycle,
        "economic_state": "TEST_ONLY", "telegram_user_id": -16000016,
    }
    runner.recovery = SimpleNamespace(
        scenario_attempt=lambda _scenario: 3,
        attempt_history=lambda *_args, **_kwargs: {
            "scenarioAttempts": [], "turnAttempts": [],
        },
        historical_attempt_history=lambda *_args, **_kwargs: {
            "scenarioAttempts": [], "turnAttempts": [],
        },
    )
    runner.harness = SimpleNamespace(
        database_name="creator_os_scenario_lab",
        database_purpose=SimpleNamespace(value="SCENARIO_LAB"),
        definition=lambda _scenario: SimpleNamespace(name="WHALE BUYER"),
        customer_for=lambda _definition: SimpleNamespace(
            telegram_user_id=-16000016, synthetic_buyer_uuid="buyer-c16",
        ),
        connection=lambda: _ConnectionScope(connection),
        behavior_summary=lambda _scenario: {},
    )
    runner.builder = SimpleNamespace(
        derived_state=lambda _scenario: {
            "customerValueTier": "WHALE", "purchaseCount": 6,
            "ownershipCount": 6, "lifetimeSpendMinor": 52910,
        },
    )
    runner._current_attempt_turn_projections = lambda *_args: [
        {"logicalTurn": number, "status": "CURRENT"}
        for number in range(1, turns + 1)
    ]
    runner._defects = lambda *_args: list(defects)
    return runner, connection


@pytest.mark.parametrize("assessment", ("PASS", "FAIL", None))
def test_full_attempt_analysis_projects_attempt_scoped_assessment(assessment):
    runner, connection = _full_analysis_runner(assessment=assessment)

    result = runner.full_attempt_analysis("C16")

    assert result["scenario"]["certificationOutcome"] == assessment
    assert result["scenario"]["canonicalTurnCount"] == 8
    assert result["scenario"]["lastCompletedLogicalTurn"] == 8
    assessment_queries = [
        query for query in connection.statements
        if "certification_scenario_assessments" in query
    ]
    assert len(assessment_queries) == 1
    assert "scenario_attempt=%s" in assessment_queries[0]


@pytest.mark.parametrize("turns", (8, 4, 0))
def test_full_attempt_analysis_progress_survives_failed_assessment(turns):
    runner, _connection = _full_analysis_runner(
        assessment="FAIL", turns=turns,
    )

    result = runner.full_attempt_analysis("C16")

    assert result["scenario"]["certificationOutcome"] == "FAIL"
    assert result["scenario"]["lastCompletedLogicalTurn"] == turns


def test_snapshotted_post_run_analysis_defect_has_no_fabricated_turn():
    runner, _connection = _full_analysis_runner(
        assessment="FAIL",
        defects=({
            "severity": "MAJOR", "turn_number": 8,
            "note": "FULL_SCENARIO_ANALYSIS NameError after canonical execution",
        },),
    )

    result = runner.full_attempt_analysis("C16")

    assert result["scenario"]["firstMaterialDefectTurn"] is None
    assert result["scenario"]["failureEvent"] == "FULL_SCENARIO_ANALYSIS"
    assert all(query.startswith("select ") for query in _connection.statements)

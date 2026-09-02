import threading

import app.database as database
import app.testing.session5_scenario_harness as harness_module
from app.testing.session5_scenario_harness import (
    CustomerScenarioHarness, ScenarioTurnExecutionIdentity,
)


def test_turn_identity_is_stable_and_attempt_scoped():
    first = ScenarioTurnExecutionIdentity("C02", 8, 1)
    same = ScenarioTurnExecutionIdentity("C02", 8, 1)
    next_turn = ScenarioTurnExecutionIdentity("C02", 8, 2)
    next_attempt = ScenarioTurnExecutionIdentity("C02", 9, 1)

    assert first.correlation_id == same.correlation_id
    assert len({
        first.correlation_id,
        next_turn.correlation_id,
        next_attempt.correlation_id,
    }) == 3


def test_application_database_scope_serializes_global_url_restoration(monkeypatch):
    monkeypatch.setattr(harness_module, "require_session5_database_purpose", lambda value, *_: value)
    monkeypatch.setattr(database, "close_database_pool", lambda: None)
    monkeypatch.setattr(database, "DATABASE_URL", "production")

    first = object.__new__(CustomerScenarioHarness)
    first.test_database_url = "isolated-one"
    first.database_purpose = "SCENARIO_LAB_OPERATOR"
    second = object.__new__(CustomerScenarioHarness)
    second.test_database_url = "isolated-two"
    second.database_purpose = "SCENARIO_LAB_OPERATOR"

    first_entered = threading.Event()
    release_first = threading.Event()
    observations = []

    def run_first():
        with first.application_test_database_scope():
            observations.append(("first", database.DATABASE_URL))
            first_entered.set()
            assert release_first.wait(timeout=2)

    def run_second():
        assert first_entered.wait(timeout=2)
        with second.application_test_database_scope():
            observations.append(("second", database.DATABASE_URL))

    thread_one = threading.Thread(target=run_first)
    thread_two = threading.Thread(target=run_second)
    thread_one.start()
    thread_two.start()
    assert first_entered.wait(timeout=2)
    assert observations == [("first", "isolated-one")]
    release_first.set()
    thread_one.join(timeout=2)
    thread_two.join(timeout=2)

    assert observations == [
        ("first", "isolated-one"),
        ("second", "isolated-two"),
    ]
    assert database.DATABASE_URL == "production"

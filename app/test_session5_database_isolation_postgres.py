"""Structural proof that automated Session 5 databases cannot cross-write operator state."""
import os

import pytest
from psycopg import connect

from app.testing.postgres_safety import (
    Session5DatabasePurpose,
    require_session5_database_purpose,
)
from app.testing.session5_scenario_harness import CustomerScenarioHarness


REQUIRED = (
    "SESSION5_SCENARIO_LAB_DATABASE_URL",
    "SESSION5_INTEGRATION_DATABASE_URL",
    "SESSION5_RECOVERY_DATABASE_URL",
)
pytestmark = pytest.mark.skipif(
    any(not os.getenv(name) for name in REQUIRED),
    reason="All three explicit Session 5 database URLs are required",
)


def _operator_state_hash(url):
    query = """SELECT md5(COALESCE(string_agg(value, '|' ORDER BY value), ''))
        FROM (
          SELECT 'run:' || row_to_json(t)::text value
            FROM certification_scenario_runs t
          UNION ALL
          SELECT 'turn:' || row_to_json(t)::text
            FROM certification_scenario_turn_attempts t
          UNION ALL
          SELECT 'evidence:' || row_to_json(t)::text
            FROM certification_scenario_turn_evidence t
          UNION ALL
          SELECT 'checkpoint:' || row_to_json(t)::text
            FROM certification_scenario_checkpoints t
        ) state"""
    with connect(url) as connection:
        return connection.execute(query).fetchone()[0]


def test_database_purposes_and_automated_writes_are_isolated():
    production = os.environ["DATABASE_URL"]
    operator = require_session5_database_purpose(
        os.environ["SESSION5_SCENARIO_LAB_DATABASE_URL"], production,
        Session5DatabasePurpose.SCENARIO_LAB_OPERATOR,
    )
    integration = require_session5_database_purpose(
        os.environ["SESSION5_INTEGRATION_DATABASE_URL"], production,
        Session5DatabasePurpose.AUTOMATED_INTEGRATION,
    )
    recovery = require_session5_database_purpose(
        os.environ["SESSION5_RECOVERY_DATABASE_URL"], production,
        Session5DatabasePurpose.AUTOMATED_RECOVERY,
    )
    assert len({operator, integration, recovery, production}) == 4
    before = _operator_state_hash(operator)

    for url, purpose, scenario in (
        (integration, Session5DatabasePurpose.AUTOMATED_INTEGRATION, "C18"),
        (recovery, Session5DatabasePurpose.AUTOMATED_RECOVERY, "C19"),
    ):
        harness = CustomerScenarioHarness(
            test_database_url=url,
            production_database_url=production,
            certification_mode=True,
            database_purpose=purpose,
        )
        with harness.connection() as connection:
            connection.execute(
                "UPDATE certification_scenario_runs SET state='SNAPSHOTTED'"
            )
            scenario_ids = [row["scenario_id"] for row in connection.execute(
                "SELECT scenario_id FROM certification_scenario_runs"
            ).fetchall()]
        for scenario_id in scenario_ids:
            harness.reset(scenario_id)
        harness.prepare(scenario)
        with harness.connection() as connection:
            connection.execute(
                "UPDATE certification_scenario_runs SET state='SNAPSHOTTED' "
                "WHERE scenario_id=%s", (scenario,),
            )
        harness.reset(scenario)

    assert _operator_state_hash(operator) == before


@pytest.mark.parametrize("expected,wrong_env", (
    (Session5DatabasePurpose.AUTOMATED_INTEGRATION,
     "SESSION5_SCENARIO_LAB_DATABASE_URL"),
    (Session5DatabasePurpose.SCENARIO_LAB_OPERATOR,
     "SESSION5_RECOVERY_DATABASE_URL"),
))
def test_database_purpose_mismatch_fails_before_harness_bootstrap(
    expected, wrong_env,
):
    with pytest.raises(ValueError, match="purpose mismatch"):
        CustomerScenarioHarness(
            test_database_url=os.environ[wrong_env],
            production_database_url=os.environ["DATABASE_URL"],
            certification_mode=True,
            database_purpose=expected,
        )

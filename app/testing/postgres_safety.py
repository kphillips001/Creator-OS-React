"""Fail-closed validation for destructive PostgreSQL integration fixtures."""
from __future__ import annotations

from enum import Enum

from psycopg import connect
from psycopg.conninfo import conninfo_to_dict


class Session5DatabasePurpose(str, Enum):
    SCENARIO_LAB_OPERATOR = "SCENARIO_LAB_OPERATOR"
    AUTOMATED_INTEGRATION = "AUTOMATED_INTEGRATION"
    AUTOMATED_RECOVERY = "AUTOMATED_RECOVERY"


def require_isolated_test_database_url(
    test_database_url: str | None, production_database_url: str | None,
) -> str:
    test_value = str(test_database_url or "").strip()
    production_value = str(production_database_url or "").strip()
    if not test_value:
        raise ValueError("TEST_DATABASE_URL is required")
    test = conninfo_to_dict(test_value)
    production = conninfo_to_dict(production_value) if production_value else None
    test_database = str(test.get("dbname") or "")
    if not test.get("host") or not test_database:
        raise ValueError("TEST_DATABASE_URL must identify a PostgreSQL database")
    if "test" not in test_database.lower():
        raise ValueError("TEST_DATABASE_URL database name must be explicitly test-scoped")
    if production is not None and (
        test.get("host"), str(test.get("port") or "5432"),
        test.get("user"), test_database,
    ) == (
        production.get("host"), str(production.get("port") or "5432"),
        production.get("user"), production.get("dbname"),
    ):
        raise ValueError("TEST_DATABASE_URL must not equal DATABASE_URL")
    if production_value and test_value == production_value:
        raise ValueError("TEST_DATABASE_URL must not equal DATABASE_URL")
    return test_value


def require_session5_database_purpose(
    database_url: str | None,
    production_database_url: str | None,
    expected_purpose: Session5DatabasePurpose | str,
) -> str:
    """Verify both test isolation and the database's durable purpose marker."""
    value = require_isolated_test_database_url(
        database_url, production_database_url,
    )
    expected = Session5DatabasePurpose(expected_purpose).value
    with connect(value) as connection:
        marker_exists = connection.execute(
            "SELECT to_regclass('public.session5_database_purpose')"
        ).fetchone()[0]
        if marker_exists is None:
            raise ValueError(
                "Session 5 database purpose marker is required before use"
            )
        rows = connection.execute(
            "SELECT purpose FROM public.session5_database_purpose"
        ).fetchall()
    purposes = [str(row[0]) for row in rows]
    if purposes != [expected]:
        actual = purposes[0] if len(purposes) == 1 else "INVALID_OR_AMBIGUOUS"
        raise ValueError(
            f"Session 5 database purpose mismatch: expected {expected}, got {actual}"
        )
    return value

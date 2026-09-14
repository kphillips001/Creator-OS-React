"""Fail-closed validation for destructive PostgreSQL integration fixtures."""
from __future__ import annotations

from enum import Enum
from contextlib import contextmanager
from functools import lru_cache

from psycopg import connect
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


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


@lru_cache(maxsize=8)
def require_current_telegram_test_schema(
    test_database_url: str | None, production_database_url: str | None,
) -> str:
    """Guard an integration database and reconcile canonical Telegram schema."""
    value = require_isolated_test_database_url(
        test_database_url, production_database_url,
    )

    @contextmanager
    def connection_factory():
        with connect(value, row_factory=dict_row) as connection:
            yield connection

    # Import lazily so the safety primitive remains usable by schema tooling.
    from app.services.schema_manager_service import SchemaManagerService

    manager = SchemaManagerService(connection_factory=connection_factory)
    required = (
        "20260912_116_telegram_observation_sources.sql",
        "20260912_117_telegram_inbound_media.sql",
    )
    for migration_name in required:
        manager.reconcile_one(migration_name)

    with connection_factory() as connection:
        rows = connection.execute(
            "SELECT migration_name FROM public.schema_migrations "
            "WHERE migration_name = ANY(%s) ORDER BY migration_name",
            (list(required),),
        ).fetchall()
        if tuple(row["migration_name"] for row in rows) != required:
            raise RuntimeError("Canonical Telegram test migrations are incomplete")
        columns = connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND "
            "table_name='telegram_identity_observations'",
        ).fetchall()
        names = {row["column_name"] for row in columns}
        expected = {
            "observation_sources", "source_channel_id", "private_chat_id",
            "private_chat_observed_at", "participant_status",
        }
        if not expected.issubset(names):
            raise RuntimeError("Migration 116 test schema is incomplete")
        for table_name in (
            "telegram_inbound_media_operations",
            "telegram_inbound_media_attachments",
        ):
            exists = connection.execute(
                "SELECT to_regclass(%s) AS relation",
                (f"public.{table_name}",),
            ).fetchone()["relation"]
            if exists is None:
                raise RuntimeError("Migration 117 test schema is incomplete")
    return value


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

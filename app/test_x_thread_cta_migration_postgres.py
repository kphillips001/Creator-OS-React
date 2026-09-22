from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import (
    isolated_test_connection,
    require_isolated_test_database_url,
)


MIGRATION = "20260916_138_x_thread_cta_deliveries.sql"
LATER_MIGRATION = "20260916_139_ordinary_reply_preparation_window.sql"


def _urls() -> tuple[str, str]:
    production = os.environ.get("PRODUCTION_DATABASE_URL", "")
    test = require_isolated_test_database_url(
        os.environ.get("SESSION5_SCENARIO_LAB_DATABASE_URL"), production,
    )
    return test, production


def _manager(test_url: str) -> SchemaManagerService:
    @contextmanager
    def factory():
        with connect(test_url, row_factory=dict_row) as connection:
            yield connection

    return SchemaManagerService(connection_factory=factory)


def _relation(connection):
    return connection.execute(
        "SELECT to_regclass('public.x_thread_cta_deliveries') AS value"
    ).fetchone()["value"]


def _verify_schema(connection, checksum: str) -> None:
    history = connection.execute(
        "SELECT checksum, COUNT(*) OVER () AS count FROM public.schema_migrations "
        "WHERE migration_name=%s", (MIGRATION,),
    ).fetchall()
    assert len(history) == 1
    assert history[0]["count"] == 1
    assert history[0]["checksum"] == checksum
    assert _relation(connection) == "x_thread_cta_deliveries"
    columns = connection.execute(
        "SELECT column_name,data_type,is_nullable,column_default "
        "FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name='x_thread_cta_deliveries' ORDER BY ordinal_position"
    ).fetchall()
    assert [(row["column_name"], row["data_type"], row["is_nullable"])
            for row in columns] == [
        ("delivery_id", "uuid", "NO"),
        ("creator_profile_id", "bigint", "NO"),
        ("fanvue_account_id", "bigint", "NO"),
        ("publish_operation_id", "text", "NO"),
        ("x_account_name", "text", "NO"),
        ("primary_x_post_id", "text", "NO"),
        ("x_link_attribution_id", "uuid", "NO"),
        ("timing", "text", "NO"),
        ("cta_text", "text", "NO"),
        ("cta_url", "text", "NO"),
        ("state", "text", "NO"),
        ("resulting_x_reply_id", "text", "YES"),
        ("provider_output_url", "text", "YES"),
        ("failure_reason", "text", "YES"),
        ("sent_at", "timestamp with time zone", "YES"),
        ("created_at", "timestamp with time zone", "NO"),
        ("updated_at", "timestamp with time zone", "NO"),
    ]
    defaults = {row["column_name"]: row["column_default"] for row in columns}
    assert defaults["cta_text"] == "''::text"
    assert defaults["created_at"] == "now()"
    assert defaults["updated_at"] == "now()"
    constraints = {
        row["conname"]: row["definition"] for row in connection.execute(
            "SELECT conname,pg_get_constraintdef(oid) AS definition "
            "FROM pg_constraint WHERE conrelid="
            "'public.x_thread_cta_deliveries'::regclass"
        ).fetchall()
    }
    assert set(constraints) == {
        "x_thread_cta_deliveries_pkey",
        "x_thread_cta_deliveries_x_link_attribution_id_fkey",
        "x_thread_cta_deliveries_resulting_x_reply_id_key",
        "uq_x_thread_cta_delivery_operation",
        "uq_x_thread_cta_delivery_parent",
        "ck_x_thread_cta_delivery_parent",
        "ck_x_thread_cta_delivery_timing",
        "ck_x_thread_cta_delivery_state",
    }
    assert "ON DELETE RESTRICT" in constraints[
        "x_thread_cta_deliveries_x_link_attribution_id_fkey"
    ]
    indexes = {row["indexname"] for row in connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname='public' "
        "AND tablename='x_thread_cta_deliveries'"
    ).fetchall()}
    assert indexes == {
        "x_thread_cta_deliveries_pkey",
        "x_thread_cta_deliveries_resulting_x_reply_id_key",
        "uq_x_thread_cta_delivery_operation",
        "uq_x_thread_cta_delivery_parent",
        "idx_x_thread_cta_deliveries_scope",
    }


def test_migration_138_forward_rollback_reforward_certification():
    test_url, production_url = _urls()
    manager = _manager(test_url)
    migration = next(item for item in manager.load_forward_migrations()
                     if item.name == MIGRATION)
    rollback = Path("migrations/rollback") / MIGRATION

    baseline = manager.certify()
    allowed_baseline_prefixes = (
        "Missing table: x_thread_cta_deliveries",
        "Missing required index: x_thread_cta_deliveries.",
        "Missing critical foreign key: x_thread_cta_deliveries.",
    )
    unrelated_drift = tuple(item for item in baseline.drift if not (
        MIGRATION in item or item.startswith(allowed_baseline_prefixes)
    ))
    if unrelated_drift:
        pytest.skip(
            "Scenario-lab baseline cannot certify migration 138 in isolation: "
            + "; ".join(unrelated_drift)
        )

    with isolated_test_connection(test_url, production_url) as connection:
        database = connection.execute(
            "SELECT current_database() AS value"
        ).fetchone()["value"]
        assert database == "creator_os_scenario_lab_test"
        later_before = connection.execute(
            "SELECT checksum,applied_at FROM public.schema_migrations "
            "WHERE migration_name=%s", (LATER_MIGRATION,),
        ).fetchone()
        assert later_before is not None
        if _relation(connection) is not None:
            assert connection.execute(
                "SELECT COUNT(*) AS count FROM public.x_thread_cta_deliveries"
            ).fetchone()["count"] == 0
        connection.execute(rollback.read_text(encoding="utf-8"))
        connection.execute(
            "DELETE FROM public.schema_migrations WHERE migration_name=%s",
            (MIGRATION,),
        )

    first = manager.reconcile_one(MIGRATION)
    assert first.status == "PASS", first.drift
    assert first.migrations_applied == (MIGRATION,)
    assert not first.drift
    with isolated_test_connection(test_url, production_url) as connection:
        _verify_schema(connection, migration.checksum)

    with isolated_test_connection(test_url, production_url) as connection:
        connection.execute(rollback.read_text(encoding="utf-8"))
        connection.execute(
            "DELETE FROM public.schema_migrations WHERE migration_name=%s",
            (MIGRATION,),
        )
        assert _relation(connection) is None
        assert connection.execute(
            "SELECT COUNT(*) AS count FROM public.schema_migrations "
            "WHERE migration_name=%s", (MIGRATION,),
        ).fetchone()["count"] == 0
        later_after = connection.execute(
            "SELECT checksum,applied_at FROM public.schema_migrations "
            "WHERE migration_name=%s", (LATER_MIGRATION,),
        ).fetchone()
        assert later_after == later_before

    second = manager.reconcile_one(MIGRATION)
    assert second.status == "PASS", second.drift
    assert second.migrations_applied == (MIGRATION,)
    assert not second.drift
    with isolated_test_connection(test_url, production_url) as connection:
        _verify_schema(connection, migration.checksum)
    final = manager.certify()
    assert final.status == "PASS"
    assert not final.missing_migrations
    assert not final.drift

"""Fail-closed lifecycle certification for migration 138 on a disposable database."""
from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row

from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import (
    require_isolated_test_database_url,
    verify_isolated_test_connection,
)


M138 = "20260916_138_x_thread_cta_deliveries.sql"
M139 = "20260916_139_ordinary_reply_preparation_window.sql"
TABLE = "x_thread_cta_deliveries"


def factory(url):
    @contextmanager
    def value():
        with connect(url, row_factory=dict_row) as connection:
            yield connection
    return value


def manager(url):
    return SchemaManagerService(connection_factory=factory(url))


def historical_manager(url, excluded):
    value = manager(url)
    migrations = value.load_forward_migrations()
    value.load_forward_migrations = lambda: tuple(
        item for item in migrations if item.name not in excluded
    )
    if M138 in excluded:
        value.REQUIRED_TABLES = {
            key: item for key, item in value.REQUIRED_TABLES.items() if key != TABLE
        }
        value.TABLE_OWNERSHIP = {
            key: item for key, item in value.TABLE_OWNERSHIP.items() if key != TABLE
        }
        value.MIGRATION_SCHEMA_REQUIREMENTS = {
            key: item for key, item in value.MIGRATION_SCHEMA_REQUIREMENTS.items()
            if key != M138
        }
        value.REQUIRED_INDEXES = {
            key: item for key, item in value.REQUIRED_INDEXES.items() if key != TABLE
        }
        value.CRITICAL_FOREIGN_KEYS = {
            key: item for key, item in value.CRITICAL_FOREIGN_KEYS.items()
            if key != TABLE
        }
    return value


def assert_pass(report, phase):
    if report.status != "PASS" or report.missing_migrations or report.drift:
        raise AssertionError(
            f"{phase} failed: missing={report.missing_migrations}, drift={report.drift}"
        )


def history(connection, name):
    return connection.execute(
        "SELECT migration_name,checksum,applied_at FROM public.schema_migrations "
        "WHERE migration_name=%s", (name,),
    ).fetchall()


def remove(connection, name, rollback_name):
    if connection.execute(
        "SELECT current_database() AS value"
    ).fetchone()["value"] == "fanvue_chatbot":
        raise RuntimeError("Production database is forbidden")
    connection.execute(
        (Path("migrations/rollback") / rollback_name).read_text(encoding="utf-8")
    )
    connection.execute(
        "DELETE FROM public.schema_migrations WHERE migration_name=%s", (name,)
    )


def verify_138(connection, checksum):
    rows = history(connection, M138)
    assert len(rows) == 1 and rows[0]["checksum"] == checksum
    assert connection.execute(
        "SELECT to_regclass('public.x_thread_cta_deliveries') AS value"
    ).fetchone()["value"] == TABLE
    columns = connection.execute(
        "SELECT column_name,data_type,is_nullable,column_default "
        "FROM information_schema.columns WHERE table_schema='public' "
        "AND table_name=%s ORDER BY ordinal_position", (TABLE,),
    ).fetchall()
    assert len(columns) == 17
    assert [(row["column_name"], row["data_type"], row["is_nullable"])
            for row in columns] == [
        ("delivery_id","uuid","NO"),
        ("creator_profile_id","bigint","NO"),
        ("fanvue_account_id","bigint","NO"),
        ("publish_operation_id","text","NO"),
        ("x_account_name","text","NO"),
        ("primary_x_post_id","text","NO"),
        ("x_link_attribution_id","uuid","NO"),
        ("timing","text","NO"), ("cta_text","text","NO"),
        ("cta_url","text","NO"), ("state","text","NO"),
        ("resulting_x_reply_id","text","YES"),
        ("provider_output_url","text","YES"),
        ("failure_reason","text","YES"),
        ("sent_at","timestamp with time zone","YES"),
        ("created_at","timestamp with time zone","NO"),
        ("updated_at","timestamp with time zone","NO"),
    ]
    defaults = {row["column_name"]: row["column_default"] for row in columns}
    assert defaults["cta_text"] == "''::text"
    assert defaults["created_at"] == defaults["updated_at"] == "now()"
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
        "AND tablename=%s", (TABLE,),
    ).fetchall()}
    assert indexes == {
        "x_thread_cta_deliveries_pkey",
        "x_thread_cta_deliveries_resulting_x_reply_id_key",
        "uq_x_thread_cta_delivery_operation",
        "uq_x_thread_cta_delivery_parent",
        "idx_x_thread_cta_deliveries_scope",
    }
    return {"columns": len(columns), "constraints": sorted(constraints),
            "indexes": sorted(indexes)}


def main():
    url = require_isolated_test_database_url(
        os.environ.get("CERTIFICATION_DATABASE_URL"),
        os.environ.get("PRODUCTION_DATABASE_URL"),
    )
    evidence = {}
    current = manager(url)
    migration = next(item for item in current.load_forward_migrations()
                     if item.name == M138)
    with connect(url, row_factory=dict_row) as connection:
        evidence["identity"] = verify_isolated_test_connection(
            connection, url, os.environ.get("PRODUCTION_DATABASE_URL")
        )
        ordering = current.certify()
        expected = {
            "Missing table: x_thread_cta_deliveries",
            "Missing required index: x_thread_cta_deliveries.idx_x_thread_cta_deliveries_scope",
            "Missing critical foreign key: x_thread_cta_deliveries.x_thread_cta_deliveries_x_link_attribution_id_fkey",
            f"Migration history is incomplete: {M138}",
        }
        assert ordering.status == "FAIL"
        assert ordering.missing_migrations == (M138,)
        assert set(ordering.drift) == expected
        evidence["ordering_before"] = {"status": ordering.status,
            "missing": list(ordering.missing_migrations), "drift": list(ordering.drift)}
        row139 = history(connection, M139)
        assert len(row139) == 1
        evidence["migration_139"] = {
            "checksum": row139[0]["checksum"],
            "applied_at": str(row139[0]["applied_at"]),
        }
        remove(connection, M139, M139)

    pre = historical_manager(url, {M138, M139}).certify()
    assert_pass(pre, "pre-138 baseline")
    evidence["pre_138"] = "PASS"

    first = current.reconcile_one(M138)
    assert M138 in first.migrations_applied
    position = historical_manager(url, {M139}).certify()
    assert_pass(position, "migration 138 intended position")
    with connect(url, row_factory=dict_row) as connection:
        evidence["forward"] = verify_138(connection, migration.checksum)

    with connect(url, row_factory=dict_row) as connection:
        remove(connection, M138, M138)
    restored = historical_manager(url, {M138, M139}).certify()
    assert_pass(restored, "post-rollback baseline")
    evidence["rollback"] = "PASS"

    second = current.reconcile_one(M138)
    assert M138 in second.migrations_applied
    reforward = historical_manager(url, {M139}).certify()
    assert_pass(reforward, "migration 138 re-forward")
    with connect(url, row_factory=dict_row) as connection:
        evidence["reforward"] = verify_138(connection, migration.checksum)
        remove(connection, M138, M138)

    applied139 = current.reconcile_one(M139)
    assert M139 in applied139.migrations_applied
    ordering_again = current.certify()
    assert ordering_again.missing_migrations == (M138,)
    assert set(ordering_again.drift) == expected
    with connect(url, row_factory=dict_row) as connection:
        row139_before = history(connection, M139)
    final_apply = current.reconcile_one(M138)
    assert final_apply.status == "PASS", final_apply.drift
    with connect(url, row_factory=dict_row) as connection:
        evidence["ordering_forward"] = verify_138(connection, migration.checksum)
        assert history(connection, M139) == row139_before
    final = current.certify()
    assert_pass(final, "final production ordering")
    evidence["final"] = "PASS"
    evidence["checksum_138"] = migration.checksum
    print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    main()

import os
from pathlib import Path

import pytest
from psycopg import connect


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
ROOT = Path(__file__).resolve().parents[1]
FORWARD = ROOT / "migrations/forward/20260911_114_verified_external_customer_identities.sql"
ROLLBACK = ROOT / "migrations/rollback/20260911_114_verified_external_customer_identities.sql"
TABLES = (
    "external_customer_identity_observations",
    "canonical_customer_materialization_audit",
    "verified_external_customer_identities",
    "verified_external_customer_identity_audit",
)


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is required")
def test_customer_identity_forward_and_rollback_in_isolated_postgres():
    forward = FORWARD.read_text(encoding="utf-8")
    rollback = ROLLBACK.read_text(encoding="utf-8")
    with connect(TEST_DATABASE_URL, autocommit=True) as connection:
        for table in TABLES:
            assert connection.execute("SELECT to_regclass(%s)",(f"public.{table}",)).fetchone()[0] is None
        try:
            connection.execute(forward)
            for table in TABLES:
                assert connection.execute("SELECT to_regclass(%s)",(f"public.{table}",)).fetchone()[0] is not None
            constraint = connection.execute("""SELECT COUNT(*) FROM pg_indexes
                WHERE schemaname='public' AND indexname='verified_external_customer_identity_active_customer_idx'""").fetchone()[0]
            assert constraint == 1
            connection.execute(rollback)
            for table in TABLES:
                assert connection.execute("SELECT to_regclass(%s)",(f"public.{table}",)).fetchone()[0] is None
        finally:
            if connection.execute("SELECT to_regclass('public.verified_external_customer_identities')").fetchone()[0]:
                connection.execute(rollback)

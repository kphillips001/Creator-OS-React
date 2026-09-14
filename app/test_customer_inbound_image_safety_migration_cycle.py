import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema

ROOT=Path(__file__).resolve().parents[1]
ROLLBACK=ROOT/'migrations/rollback/20260912_118_customer_inbound_image_safety.sql'
NAME='20260912_118_customer_inbound_image_safety.sql'


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_customer_image_safety_forward_and_rollback():
    url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as c:yield c
    with connect(url,autocommit=True) as c:
        if c.execute("SELECT to_regclass('public.telegram_inbound_media_safety_results')").fetchone()[0] is not None:
            c.execute(ROLLBACK.read_text());c.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))
    try:
        result=SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        assert NAME in result.migrations_applied
        with connect(url) as c:
            assert c.execute("SELECT count(*) FROM schema_migrations WHERE migration_name=%s",(NAME,)).fetchone()[0]==1
            assert c.execute("SELECT to_regclass('public.telegram_explicit_boundary_events')").fetchone()[0] is not None
            assert c.execute("SELECT to_regclass('public.telegram_inbound_media_safety_results')").fetchone()[0] is not None
    finally:
        with connect(url,autocommit=True) as c:
            if c.execute("SELECT to_regclass('public.telegram_inbound_media_safety_results')").fetchone()[0] is not None:c.execute(ROLLBACK.read_text())
            c.execute("DELETE FROM schema_migrations WHERE migration_name=%s",(NAME,))

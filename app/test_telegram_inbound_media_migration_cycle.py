import os
import pytest
from psycopg import connect
from app.testing.postgres_safety import require_current_telegram_test_schema

@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_media_foundation_canonical_schema_is_current():
    url=require_current_telegram_test_schema(
        os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
    with connect(url) as c:
        assert c.execute("SELECT count(*) FROM schema_migrations WHERE migration_name='20260912_117_telegram_inbound_media.sql'").fetchone()[0]==1
        constraints=c.execute("SELECT contype FROM pg_constraint WHERE conrelid='public.telegram_inbound_media_attachments'::regclass").fetchall()
        assert {'p','u','f','c'}.issubset({row[0] for row in constraints})
        indexes={row[0] for row in c.execute("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename LIKE 'telegram_inbound_media_%'").fetchall()}
        assert 'telegram_inbound_media_recovery_idx' in indexes
        assert 'telegram_inbound_media_retention_idx' in indexes
        assert 'telegram_inbound_media_attachment_operation_idx' in indexes

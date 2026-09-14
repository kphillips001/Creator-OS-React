import os
import pytest
from psycopg import connect
from app.testing.postgres_safety import require_current_telegram_test_schema

TEST_DATABASE_URL=os.getenv('TEST_DATABASE_URL')

@pytest.mark.skipif(not TEST_DATABASE_URL,reason='TEST_DATABASE_URL is required')
def test_observation_sources_canonical_schema_and_semantics():
    user_id=9223372036854775001
    url=require_current_telegram_test_schema(TEST_DATABASE_URL,os.getenv('DATABASE_URL'))
    with connect(url) as c:
        try:
            assert c.execute("SELECT count(*) FROM schema_migrations WHERE migration_name='20260912_116_telegram_observation_sources.sql'").fetchone()[0]==1
            nullable=c.execute("SELECT is_nullable FROM information_schema.columns WHERE table_schema='public' AND table_name='telegram_identity_observations' AND column_name='telegram_chat_id'").fetchone()[0]
            assert nullable=='YES'
            c.execute("INSERT INTO telegram_identity_observations(telegram_user_id,observation_sources,source_channel_id,display_name) VALUES(%s,ARRAY['BROADCAST_MEMBER'],%s,'Test Member')",(user_id,-1001))
            chat_id=c.execute("SELECT telegram_chat_id FROM telegram_identity_observations WHERE telegram_user_id=%s",(user_id,)).fetchone()[0]
            assert chat_id is None
            c.execute("UPDATE telegram_identity_observations SET telegram_chat_id=%s,private_chat_id=%s,private_chat_observed_at=NOW(),observation_sources=ARRAY['BROADCAST_MEMBER','PRIVATE_CHAT'] WHERE telegram_user_id=%s",(user_id,user_id,user_id))
            assert c.execute("SELECT cardinality(observation_sources) FROM telegram_identity_observations WHERE telegram_user_id=%s",(user_id,)).fetchone()[0]==2
        finally:
            c.rollback()

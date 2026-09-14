import os
import uuid

import pytest
from psycopg import connect

from app import database
from app.testing.postgres_safety import require_isolated_test_database_url

from app.repositories.fanvue_account_repository import get_or_create_account
from app.repositories.user_repository import get_or_create_user_with_memory
from app.repositories.memory_repository import (
    increment_message_count,
    update_conversation_mode,
    update_intent_fields,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required")


@pytest.fixture
def isolated_memory_database(monkeypatch):
    test_url = require_isolated_test_database_url(
        os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
    database.close_database_pool()
    monkeypatch.setattr(database, "DATABASE_URL", test_url)
    fixture_uuids = []
    try:
        yield test_url, fixture_uuids
    finally:
        database.close_database_pool()
        with connect(test_url) as connection:
            for fixture_uuid in fixture_uuids:
                user = connection.execute(
                    "SELECT id FROM fanvue_users WHERE fanvue_user_uuid = %s",
                    (fixture_uuid,),
                ).fetchone()
                if user:
                    connection.execute(
                        "DELETE FROM user_memory WHERE fanvue_user_id::text = %s",
                        (str(user[0]),),
                    )
                    connection.execute(
                        "DELETE FROM fanvue_users WHERE id = %s AND source = 'test'",
                        (user[0],),
                    )


def test_memory_repository(isolated_memory_database):
    _, fixture_uuids = isolated_memory_database
    account = get_or_create_account(
        username="ava.blackthorne",
        display_name="Ava Blackthorne",
    )

    fixture_uuid = str(uuid.uuid4())
    fixture_uuids.append(fixture_uuid)
    context = get_or_create_user_with_memory(
        fanvue_account_id=account["id"],
        fanvue_user_uuid=fixture_uuid,
        username="memory_test_user",
        display_name="Memory Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="test",
    )

    user = context["user"]

    memory = increment_message_count(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
    )
    print("After increment_message_count:")
    print(memory)

    memory = update_conversation_mode(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
        conversation_mode="flirty",
    )
    print("After update_conversation_mode:")
    print(memory)

    memory = update_intent_fields(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
        intent_score=25.5,
        buyer_tier="medium",
    )
    print("After update_intent_fields:")
    print(memory)

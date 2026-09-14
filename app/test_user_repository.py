import os
import uuid

import pytest
from psycopg import connect

from app import database
from app.repositories.fanvue_account_repository import get_or_create_account
from app.repositories.user_repository import get_or_create_user_with_memory
from app.testing.postgres_safety import require_isolated_test_database_url


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required"
)


@pytest.fixture
def isolated_user_database(monkeypatch):
    test_url = require_isolated_test_database_url(
        os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL")
    )
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


def test_user_repository(isolated_user_database):
    _, fixture_uuids = isolated_user_database
    account = get_or_create_account(
        username="repository.test",
        display_name="Repository Test",
    )
    fanvue_user_uuid = str(uuid.uuid4())
    fixture_uuids.append(fanvue_user_uuid)

    result = get_or_create_user_with_memory(
        fanvue_account_id=account["id"],
        fanvue_user_uuid=fanvue_user_uuid,
        username="test_user_01",
        display_name="Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="test",
    )

    print("User created/loaded successfully!")
    print(result["user"])
    print(result["memory"])


if __name__ == "__main__":
    test_user_repository()

import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.canonical_customer_identity_repository import (
    CanonicalCustomerIdentityRepository, CustomerIdentityConflictError,
)

URL=os.getenv("TEST_DATABASE_URL")
ROOT=Path(__file__).resolve().parents[1]
FORWARD=(ROOT/"migrations/forward/20260911_114_verified_external_customer_identities.sql").read_text()
ROLLBACK=(ROOT/"migrations/rollback/20260911_114_verified_external_customer_identities.sql").read_text()


@pytest.mark.skipif(not URL,reason="TEST_DATABASE_URL is required")
def test_x_identity_verification_conflicts_deactivation_and_mutable_metadata():
    @contextmanager
    def connections():
        with connect(URL,row_factory=dict_row) as connection:
            yield connection
    with connect(URL,autocommit=True,row_factory=dict_row) as setup:
        setup.execute(FORWARD)
        users=setup.execute("""SELECT cp.id creator_profile_id,u.fanvue_account_id,u.id
            FROM fanvue_users u JOIN creator_profiles cp
            ON cp.fanvue_account_id::text=u.fanvue_account_id::text
            WHERE u.fanvue_account_id=(SELECT fanvue_account_id FROM fanvue_users
                GROUP BY fanvue_account_id HAVING COUNT(*)>=2 ORDER BY fanvue_account_id LIMIT 1)
            ORDER BY u.id LIMIT 2""").fetchall()
    if len(users)<2 or users[0]["fanvue_account_id"] != users[1]["fanvue_account_id"]:
        with connect(URL,autocommit=True) as cleanup: cleanup.execute(ROLLBACK)
        pytest.skip("Two canonical users in one account are required")
    repo=CanonicalCustomerIdentityRepository(connections)
    first,second=users
    try:
        repo.observe_external(creator_profile_id=first["creator_profile_id"],platform="X",
            external_numeric_id="991001",username="old_handle",source="TEST_FIXTURE")
        link,replay=repo.verify_external(creator_profile_id=first["creator_profile_id"],
            fanvue_account_id=first["fanvue_account_id"],local_fanvue_user_id=first["id"],
            platform="X",external_numeric_id="991001",evidence={"fixture":True},
            operator_source="TEST_SUITE")
        assert not replay
        _,replay=repo.verify_external(creator_profile_id=first["creator_profile_id"],
            fanvue_account_id=first["fanvue_account_id"],local_fanvue_user_id=first["id"],
            platform="X",external_numeric_id="991001",evidence={"fixture":True},
            operator_source="TEST_SUITE")
        assert replay
        with pytest.raises(CustomerIdentityConflictError):
            repo.verify_external(creator_profile_id=first["creator_profile_id"],
                fanvue_account_id=first["fanvue_account_id"],local_fanvue_user_id=second["id"],
                platform="X",external_numeric_id="991001",evidence={"fixture":True},
                operator_source="TEST_SUITE")
        repo.observe_external(creator_profile_id=first["creator_profile_id"],platform="X",
            external_numeric_id="991002",username="second",source="TEST_FIXTURE")
        with pytest.raises(CustomerIdentityConflictError):
            repo.verify_external(creator_profile_id=first["creator_profile_id"],
                fanvue_account_id=first["fanvue_account_id"],local_fanvue_user_id=first["id"],
                platform="X",external_numeric_id="991002",evidence={"fixture":True},
                operator_source="TEST_SUITE")
        repo.observe_external(creator_profile_id=first["creator_profile_id"],platform="X",
            external_numeric_id="991001",username="new_handle",source="TEST_FIXTURE_REFRESH")
        assert repo.active_for_customer(fanvue_account_id=first["fanvue_account_id"],
            local_fanvue_user_id=first["id"])[0]["observed_username"] == "new_handle"
        repo.deactivate(link_id=link["external_identity_link_id"],reason="fixture correction",
                        operator_source="TEST_SUITE")
        corrected,replay=repo.verify_external(creator_profile_id=first["creator_profile_id"],
            fanvue_account_id=first["fanvue_account_id"],local_fanvue_user_id=second["id"],
            platform="X",external_numeric_id="991001",evidence={"fixture":"correction"},
            operator_source="TEST_SUITE")
        assert not replay and corrected["local_fanvue_user_id"] == second["id"]
        with connect(URL,row_factory=dict_row) as check:
            actions=check.execute("SELECT action,COUNT(*) n FROM verified_external_customer_identity_audit GROUP BY action").fetchall()
            assert {row["action"]:row["n"] for row in actions} == {"VERIFIED":2,"DEACTIVATED":1}
    finally:
        with connect(URL,autocommit=True) as cleanup: cleanup.execute(ROLLBACK)

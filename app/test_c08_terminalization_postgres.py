from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.purchase_intent_repository import PurchaseIntentRepository


pytestmark = pytest.mark.skipif(
    not os.getenv("SESSION5_INTEGRATION_DATABASE_URL"),
    reason="SESSION5_INTEGRATION_DATABASE_URL required",
)


def test_c08_canonical_close_is_atomic_idempotent_and_exact_intent():
    connection = connect(
        os.environ["SESSION5_INTEGRATION_DATABASE_URL"], row_factory=dict_row,
    )

    @contextmanager
    def shared_connection():
        yield connection

    try:
        fixture = connection.execute(
            """SELECT offering.offering_id,offering.creator_profile_id,
                      profile.fanvue_account_id,publication.publication_id
               FROM commercial_offerings offering
               JOIN commercial_publications publication
                 ON publication.commercial_offering_id=offering.offering_id
               JOIN creator_profiles profile ON profile.id=offering.creator_profile_id
               LIMIT 1"""
        ).fetchone()
        assert fixture is not None
        now = datetime.now(timezone.utc)
        first, second = uuid4(), uuid4()
        first_user, second_user = 9_199_000_001, 9_199_000_002
        for intent_id, user_id in ((first, first_user), (second, second_user)):
            connection.execute(
                """INSERT INTO purchase_intents(
                       purchase_intent_id,creator_profile_id,fanvue_account_id,
                       telegram_user_id,telegram_chat_id,commercial_offering_id,
                       commercial_publication_id,provider,provider_resource_id,
                       delivery_url,correlation_id,expected_price_minor,
                       expected_currency,status,presented_at,telegram_message_id,
                       expires_at,configured_base_price_minor,identity_bootstrap_mode)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'FANVUE',%s,%s,%s,900,'USD',
                           'PRESENTED',%s,12345,%s,900,'PRIVATE_CHAT_FINGERPRINT')""",
                (intent_id, fixture["creator_profile_id"],
                 fixture["fanvue_account_id"], user_id, user_id,
                 fixture["offering_id"], fixture["publication_id"],
                 f"c08-postgres-{intent_id}", "https://example.invalid/unlock",
                 uuid4(), now, now + timedelta(days=1)),
            )
            connection.execute(
                """INSERT INTO telegram_unlock_grants(
                       unlock_grant_id,token_hash,purchase_intent_id,
                       telegram_user_id,telegram_chat_id,commercial_offering_id,
                       commercial_publication_id,fanvue_account_id,currency)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'USD')""",
                (uuid4(), uuid4().hex + uuid4().hex, intent_id, user_id, user_id,
                 fixture["offering_id"], fixture["publication_id"],
                 fixture["fanvue_account_id"]),
            )

        repository = PurchaseIntentRepository(connection_factory=shared_connection)
        reason = "SCENARIO_LAB_C08_CANONICAL_NONCONVERSION"
        first_close = repository.close_administratively(
            first, reason_code=reason,
            expected_telegram_user_id=first_user,
            expected_telegram_chat_id=first_user, at=now,
        )
        repeated_close = repository.close_administratively(
            first, reason_code=reason,
            expected_telegram_user_id=first_user,
            expected_telegram_chat_id=first_user, at=now,
        )
        first_evidence = repository.get_customer_opportunity_evidence(
            creator_profile_id=fixture["creator_profile_id"],
            fanvue_account_id=fixture["fanvue_account_id"],
            telegram_user_id=first_user,
        )
        assert first_evidence["presented_opportunity_count"] == 1
        assert first_evidence["failed_nonconverted_opportunity_count"] == 1
        # A is terminal, so B can now become the same customer's next active
        # opportunity without violating the one-active-intent invariant.
        connection.execute(
            """UPDATE purchase_intents
               SET telegram_user_id=%s,telegram_chat_id=%s
               WHERE purchase_intent_id=%s""",
            (first_user, first_user, second),
        )
        connection.execute(
            """UPDATE telegram_unlock_grants
               SET telegram_user_id=%s,telegram_chat_id=%s
               WHERE purchase_intent_id=%s""",
            (first_user, first_user, second),
        )
        mixed_evidence = repository.get_customer_opportunity_evidence(
            creator_profile_id=fixture["creator_profile_id"],
            fanvue_account_id=fixture["fanvue_account_id"],
            telegram_user_id=first_user,
        )
        assert mixed_evidence["presented_opportunity_count"] == 2
        assert mixed_evidence["failed_nonconverted_opportunity_count"] == 1
        rows = connection.execute(
            """SELECT intent.purchase_intent_id,intent.status,unlock.state,
                      unlock.revoked_at,unlock.use_count
               FROM purchase_intents intent
               JOIN telegram_unlock_grants unlock USING(purchase_intent_id)
               WHERE intent.purchase_intent_id=ANY(%s)
               ORDER BY intent.purchase_intent_id""",
            ([first, second],),
        ).fetchall()
        by_id = {row["purchase_intent_id"]: row for row in rows}
        assert first_close == repeated_close
        assert by_id[first]["status"] == "ADMIN_CLOSED"
        assert by_id[first]["state"] == "REVOKED"
        assert by_id[first]["revoked_at"] is not None
        assert by_id[first]["use_count"] == 0
        assert by_id[second]["status"] == "PRESENTED"
        assert by_id[second]["state"] == "ACTIVE"
        assert by_id[second]["revoked_at"] is None
        assert by_id[second]["use_count"] == 0
        repository.close_administratively(
            second, reason_code=reason,
            expected_telegram_user_id=first_user,
            expected_telegram_chat_id=first_user, at=now,
        )
        second_evidence = repository.get_customer_opportunity_evidence(
            creator_profile_id=fixture["creator_profile_id"],
            fanvue_account_id=fixture["fanvue_account_id"],
            telegram_user_id=first_user,
        )
        assert second_evidence["presented_opportunity_count"] == 2
        assert second_evidence["failed_nonconverted_opportunity_count"] == 2
        assert connection.execute(
            "SELECT COUNT(*) AS n FROM provider_purchase_asset_ownership "
            "WHERE provider_transaction_id=ANY(%s)",
            ([f"c08-postgres-{first}", f"c08-postgres-{second}"],),
        ).fetchone()["n"] == 0
    finally:
        connection.rollback()
        connection.close()

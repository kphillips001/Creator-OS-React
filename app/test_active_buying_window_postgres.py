"""Isolated PostgreSQL durability proof for deferred customer continuation."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.repositories.telegram_sales_prospect_repository import (
    TelegramSalesProspectRepository,
)
from app.testing.postgres_safety import Session5DatabasePurpose
from app.testing.session5_scenario_harness import CustomerScenarioHarness
from app.services.private_chat_purchase_settlement_service import (
    PrivateChatPurchaseSettlementService,
)
from app.test_private_chat_settlement_postgres import (
    connection_factory as settlement_connection_factory,
    fixture as settlement_fixture,
    settle as settle_first,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("SESSION5_INTEGRATION_DATABASE_URL"),
    reason="SESSION5_INTEGRATION_DATABASE_URL required",
)


def test_deferred_continuation_is_restart_safe_idempotent_and_single_use():
    harness = CustomerScenarioHarness(
        certification_mode=True,
        database_purpose=Session5DatabasePurpose.AUTOMATED_INTEGRATION,
    )
    telegram_user_id = 8_900_000_000_000_000_000 + (uuid4().int % 10_000_000)
    correlation = f"postgres-deferred:{uuid4()}"
    intent_id = uuid4()
    with harness.connection() as connection:
        scope = connection.execute(
            """SELECT profile.id creator_profile_id, account.id fanvue_account_id
               FROM creator_profiles profile
               JOIN fanvue_accounts account
                 ON account.id::text=profile.fanvue_account_id::text
               ORDER BY profile.id LIMIT 1"""
        ).fetchone()
    assert scope is not None
    values = {
        "creator_profile_id": int(scope["creator_profile_id"]),
        "fanvue_account_id": int(scope["fanvue_account_id"]),
        "telegram_user_id": telegram_user_id,
    }
    repository = TelegramSalesProspectRepository(
        connection_factory=harness.connection
    )
    try:
        repository.observe(
            **values, telegram_chat_id=telegram_user_id,
        )
        first = repository.record_deferred_continuation(
            **values, source_inbound_message_id=6001,
            source_correlation_id=correlation,
            purchase_intent_id=intent_id,
        )
        duplicate = repository.record_deferred_continuation(
            **values, source_inbound_message_id=6001,
            source_correlation_id=correlation,
            purchase_intent_id=intent_id,
        )
        assert first.relationship_state["deferredContinuation"]["state"] == (
            "PENDING_ACKNOWLEDGEMENT"
        )
        assert duplicate.relationship_state == first.relationship_state

        ready = repository.transition_deferred_continuation(
            **values, from_states=("PENDING_ACKNOWLEDGEMENT",),
            target_state="READY",
        )
        assert ready.relationship_state["deferredContinuation"]["state"] == "READY"
        claimed = repository.transition_deferred_continuation(
            **values, from_states=("READY",), target_state="CLAIMED",
            correlation_id=correlation,
        )
        assert claimed is not None
        assert repository.transition_deferred_continuation(
            **values, from_states=("READY",), target_state="CLAIMED",
            correlation_id=f"different:{uuid4()}",
        ) is None
        consumed = repository.transition_deferred_continuation(
            **values, from_states=("CLAIMED",), target_state="CONSUMED",
            correlation_id=correlation,
        )
        assert consumed.relationship_state["deferredContinuation"]["state"] == (
            "CONSUMED"
        )
        assert repository.transition_deferred_continuation(
            **values, from_states=("CLAIMED",), target_state="CONSUMED",
            correlation_id=correlation,
        ) is None

        restarted = TelegramSalesProspectRepository(
            connection_factory=harness.connection
        ).get(**values)
        assert restarted.relationship_state["deferredContinuation"]["state"] == (
            "CONSUMED"
        )

        proposal = repository.record_session_proposal(
            **values, correlation_id=f"proposal:{uuid4()}",
            session_offering_id=uuid4(),
        )
        assert proposal.relationship_state["sessionProposal"]["state"] == "PENDING"
        assert proposal.relationship_state["sessionProposal"]["delivered"] is True
        assert proposal.relationship_state["sessionProposal"]["expiresAt"]
        assert proposal.relationship_state["sessionProposal"]["proposalId"]
        accepted = repository.transition_session_proposal(
            **values, target_state="ACCEPTED", reaction="ACCEPT_OR_LEAN_IN",
        )
        assert accepted.relationship_state["sessionProposal"]["state"] == "ACCEPTED"
        assert repository.transition_session_proposal(
            **values, target_state="DECLINED_STOP", reaction="DECLINE_AND_STOP",
        ) is None
        restarted = TelegramSalesProspectRepository(
            connection_factory=harness.connection
        ).get(**values)
        assert restarted.relationship_state["sessionProposal"]["state"] == "ACCEPTED"
    finally:
        with harness.connection() as connection:
            connection.execute(
                "DELETE FROM telegram_sales_prospects WHERE telegram_user_id=%s",
                (telegram_user_id,),
            )


def _next_ppv(base, *, exact_price_minor):
    offering_id, publication_id, intent_id = uuid4(), uuid4(), uuid4()
    reservation_id, runtime_id, asset_id = uuid4(), uuid4(), None
    with settlement_connection_factory() as connection:
        asset_id = connection.execute(
            "INSERT INTO content_items(file_path,classification) "
            "VALUES (%s,'SAFE') RETURNING id",
            (f"synthetic/{uuid4()}.jpg",),
        ).fetchone()["id"]
        connection.execute(
            """INSERT INTO commercial_offerings(
               offering_id,creator_profile_id,offering_type,title,hero_asset_id,
               primary_sales_channel,status,price_minor,currency)
               VALUES (%s,%s,'SINGLE_IMAGE','Synthetic next',%s,
               'AI_CHAT','READY',1499,'USD')""",
            (offering_id, base["creator"], asset_id),
        )
        connection.execute(
            """INSERT INTO commercial_publications(
               publication_id,commercial_offering_id,provider,status,
               external_product_id,provider_resource_status,publication_metadata)
               VALUES (%s,%s,'FANVUE','LIVE','canonical','PRESENT',
               '{"media_link":{"url":"https://example.invalid/canonical",
               "media_uuids":["synthetic-media"]}}')""",
            (publication_id, offering_id),
        )
        connection.execute(
            "INSERT INTO commercial_offering_assets(offering_id,asset_id,position) "
            "VALUES (%s,%s,1)", (offering_id, asset_id),
        )
        connection.execute(
            """INSERT INTO purchase_intents(
               purchase_intent_id,creator_profile_id,fanvue_account_id,
               telegram_user_id,telegram_chat_id,commercial_offering_id,
               commercial_publication_id,provider,provider_resource_id,
               delivery_url,correlation_id,expected_price_minor,
               configured_base_price_minor,expected_currency,expires_at,
               identity_bootstrap_mode)
               VALUES (%s,%s,%s,%s,%s,%s,%s,'FANVUE','runtime',
               'https://example.invalid/runtime',%s,1499,1499,'USD',%s,
               'PRIVATE_CHAT_FINGERPRINT')""",
            (intent_id, base["creator"], base["account"], base["telegram"],
             base["telegram"], offering_id, publication_id, uuid4(),
             datetime.now(timezone.utc) + timedelta(days=1)),
        )
        connection.execute(
            """INSERT INTO fanvue_fingerprint_reservations(
               fingerprint_reservation_id,fanvue_account_id,currency,
               exact_price_minor,configured_base_price_minor,purchase_intent_id,
               telegram_user_id,state)
               VALUES (%s,%s,'USD',%s,1499,%s,%s,'ACTIVE')""",
            (reservation_id, base["account"], exact_price_minor, intent_id,
             base["telegram"]),
        )
        connection.execute(
            """INSERT INTO fanvue_runtime_media_links(
               runtime_media_link_id,purchase_intent_id,
               fingerprint_reservation_id,provider_media_link_uuid,provider_url,
               state,creation_operation_key,expires_at)
               VALUES (%s,%s,%s,%s,'https://example.invalid/runtime','ACTIVE',
               %s,%s)""",
            (runtime_id, intent_id, reservation_id, str(uuid4()), uuid4(),
             datetime.now(timezone.utc) + timedelta(days=1)),
        )
    return intent_id, offering_id, asset_id


def test_three_customer_led_ppv_settlements_remain_distinct_and_idempotent():
    base = settlement_fixture()
    service = PrivateChatPurchaseSettlementService(
        connection_factory=settlement_connection_factory
    )
    settle_first(base, transaction_id="streak-tx-1")
    intent_ids = [base["intent_id"]]
    offering_ids = [base["offering_id"]]
    asset_ids = [base["asset"]]
    for sequence, exact_price in ((2, 1496), (3, 1495)):
        intent_id, offering_id, asset_id = _next_ppv(
            base, exact_price_minor=exact_price,
        )
        evidence = dict(
            fanvue_account_id=base["account"], currency="USD",
            gross_minor=exact_price, source="media_link",
            buyer_uuid=base["buyer_uuid"], local_fanvue_user_id=base["user"],
            transaction_id=f"streak-tx-{sequence}",
            payment_id=f"streak-pay-{sequence}",
            event_id=f"streak-event-{sequence}",
            purchased_at=datetime.now(timezone.utc),
        )
        assert service.settle(**evidence) is not None
        assert service.settle(**evidence) is not None
        intent_ids.append(intent_id)
        offering_ids.append(offering_id)
        asset_ids.append(asset_id)

    with settlement_connection_factory() as connection:
        intents = connection.execute(
            """SELECT purchase_intent_id,commercial_offering_id,status
               FROM purchase_intents WHERE purchase_intent_id=ANY(%s)""",
            (intent_ids,),
        ).fetchall()
        ownership = connection.execute(
            """SELECT content_item_id,COUNT(*) n
               FROM provider_purchase_asset_ownership
               WHERE fanvue_account_id=%s AND content_item_id=ANY(%s)
               GROUP BY content_item_id""",
            (base["account"], asset_ids),
        ).fetchall()
        mappings = connection.execute(
            "SELECT COUNT(*) n FROM telegram_identity_map "
            "WHERE telegram_user_id=%s", (base["telegram"],),
        ).fetchone()["n"]
    assert len(intents) == 3
    assert {row["status"] for row in intents} == {"PURCHASED"}
    assert {row["commercial_offering_id"] for row in intents} == set(offering_ids)
    assert len(ownership) == 3 and all(row["n"] == 1 for row in ownership)
    assert mappings == 1

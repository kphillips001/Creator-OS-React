"""Real PostgreSQL certification for atomic fingerprint settlement."""
import os
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.services.private_chat_purchase_settlement_service import PrivateChatPurchaseSettlementService
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    guarded_url = require_isolated_test_database_url(
        TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL")
        or os.getenv("DATABASE_URL"),
    )
    with connect(guarded_url, row_factory=dict_row) as connection:
        yield connection


def fixture(*, session=False, offering_type="SINGLE_IMAGE"):
    telegram = 800_000_000 + (uuid4().int % 90_000_000)
    buyer_uuid, offering_id, publication_id, intent_id = uuid4(), uuid4(), uuid4(), uuid4()
    reservation_id, runtime_id, prospect_id = uuid4(), uuid4(), uuid4()
    with connection_factory() as c:
        account = c.execute("INSERT INTO fanvue_accounts(account_name) VALUES (%s) RETURNING id",
                            (f"Synthetic {uuid4()}",)).fetchone()["id"]
        user = c.execute("""INSERT INTO fanvue_users(fanvue_user_uuid,fanvue_account_id,
            username,display_name) VALUES (%s,%s,'synthetic','Synthetic') RETURNING id""",
            (buyer_uuid, account)).fetchone()["id"]
        creator = c.execute("""INSERT INTO creator_profiles(fanvue_account_id,persona_name,
            display_name,age,gender,location) VALUES (%s,'Synthetic','Synthetic',25,'female','test') RETURNING id""",
            (str(account),)).fetchone()["id"]
        asset = c.execute("INSERT INTO content_items(file_path,classification) VALUES (%s,'SAFE') RETURNING id",
                          (f"synthetic/{uuid4()}.jpg",)).fetchone()["id"]
        c.execute("""INSERT INTO commercial_offerings(offering_id,creator_profile_id,
            offering_type,title,hero_asset_id,primary_sales_channel,status,price_minor,currency)
            VALUES (%s,%s,%s,'Synthetic',%s,'AI_CHAT','READY',1499,'USD')""",
            (offering_id, creator, offering_type, asset))
        c.execute("""INSERT INTO commercial_publications(publication_id,commercial_offering_id,
            provider,status,external_product_id,provider_resource_status,publication_metadata)
            VALUES (%s,%s,'FANVUE','LIVE','canonical','PRESENT',
            '{"media_link":{"url":"https://example.invalid/canonical","media_uuids":["synthetic-media"]}}')""",
            (publication_id, offering_id))
        c.execute("""INSERT INTO commercial_offering_assets(offering_id,asset_id,position)
            VALUES (%s,%s,1)""", (offering_id, asset))
        c.execute("INSERT INTO telegram_identity_observations(telegram_user_id,telegram_chat_id) VALUES (%s,%s)",
                  (telegram, telegram))
        c.execute("""INSERT INTO telegram_sales_prospects(telegram_sales_prospect_id,
            creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
            relationship_state,preference_state) VALUES (%s,%s,%s,%s,%s,
            '{"stage":"warm"}','{"theme":"portrait"}')""",
            (prospect_id, creator, account, telegram, telegram))
        c.execute("""INSERT INTO purchase_intents(purchase_intent_id,creator_profile_id,
            fanvue_account_id,telegram_user_id,telegram_chat_id,commercial_offering_id,
            commercial_publication_id,provider,provider_resource_id,delivery_url,
            correlation_id,expected_price_minor,configured_base_price_minor,
            expected_currency,expires_at,identity_bootstrap_mode)
            VALUES (%s,%s,%s,%s,%s,%s,%s,'FANVUE','runtime','https://example.invalid/runtime',
            %s,1499,1499,'USD',%s,'PRIVATE_CHAT_FINGERPRINT')""",
            (intent_id, creator, account, telegram, telegram, offering_id,
             publication_id, uuid4(), datetime.now(timezone.utc)+timedelta(days=1)))
        c.execute("""INSERT INTO fanvue_fingerprint_reservations(
            fingerprint_reservation_id,fanvue_account_id,currency,exact_price_minor,
            configured_base_price_minor,purchase_intent_id,telegram_user_id,state)
            VALUES (%s,%s,'USD',1497,1499,%s,%s,'ACTIVE')""",
            (reservation_id, account, intent_id, telegram))
        c.execute("""INSERT INTO fanvue_runtime_media_links(runtime_media_link_id,
            purchase_intent_id,fingerprint_reservation_id,provider_media_link_uuid,
            provider_url,state,creation_operation_key,expires_at)
            VALUES (%s,%s,%s,%s,'https://example.invalid/runtime','ACTIVE',%s,%s)""",
            (runtime_id, intent_id, reservation_id, str(uuid4()), uuid4(),
             datetime.now(timezone.utc)+timedelta(days=1)))
        provisional_id = None
        if session:
            provisional_id = uuid4()
            c.execute("""INSERT INTO telegram_provisional_sales_sessions(
                provisional_session_id,telegram_sales_prospect_id,creator_profile_id,
                fanvue_account_id,telegram_user_id,telegram_chat_id,photoshoot_reference,
                session_strategy,state,configured_base_price_minor,first_purchase_intent_id)
                VALUES (%s,%s,%s,%s,%s,%s,'synthetic-shoot','ESCALATING',
                'AWAITING_PAYMENT',1499,%s)""", (provisional_id, prospect_id, creator,
                account, telegram, telegram, intent_id))
    return locals()


def settle(values, *, fail_after=None, transaction_id="tx-1"):
    return PrivateChatPurchaseSettlementService(
        connection_factory=connection_factory, fail_after=fail_after).settle(
        fanvue_account_id=values["account"], currency="USD", gross_minor=1497,
        source="media_link", buyer_uuid=values["buyer_uuid"],
        local_fanvue_user_id=values["user"], transaction_id=transaction_id,
        payment_id="pay-1", event_id="event-1", purchased_at=datetime.now(timezone.utc))


def state(values):
    with connection_factory() as c:
        return {
            "mappings": c.execute("SELECT COUNT(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",(values["telegram"],)).fetchone()["n"],
            "audits": c.execute("SELECT COUNT(*) n FROM telegram_identity_verification_audit WHERE telegram_user_id=%s",(values["telegram"],)).fetchone()["n"],
            "intent": c.execute("SELECT status,purchased_at,actual_charged_price_minor,purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone(),
            "reservation": c.execute("SELECT state FROM fanvue_fingerprint_reservations WHERE fingerprint_reservation_id=%s",(values["reservation_id"],)).fetchone()["state"],
            "runtime": c.execute("SELECT state FROM fanvue_runtime_media_links WHERE runtime_media_link_id=%s",(values["runtime_id"],)).fetchone()["state"],
            "prospect": c.execute("SELECT graduated_mapping_id FROM telegram_sales_prospects WHERE telegram_sales_prospect_id=%s",(values["prospect_id"],)).fetchone()["graduated_mapping_id"],
            "sessions": c.execute("SELECT COUNT(*) n FROM sales_sessions WHERE fanvue_account_id=%s AND fanvue_user_id=%s",(values["account"],values["user"])).fetchone()["n"],
        }


@pytest.mark.parametrize("checkpoint", ["mapping","intent","fingerprint","prospect","before_commit"])
def test_atomic_rollback_non_session(checkpoint):
    values = fixture()
    with pytest.raises(RuntimeError): settle(values, fail_after=checkpoint)
    result = state(values)
    assert result == {"mappings":0,"audits":0,"intent":{"status":"CREATED","purchased_at":None,"actual_charged_price_minor":None,"purchase_acknowledged_at":None},
                      "reservation":"ACTIVE","runtime":"ACTIVE","prospect":None,"sessions":0}
    assert settle(values) is not None
    assert state(values)["mappings"] == 1


@pytest.mark.parametrize("checkpoint", ["canonical_session","provisional_session","session_advancement"])
def test_atomic_rollback_session(checkpoint):
    values = fixture(session=True)
    with pytest.raises(RuntimeError): settle(values, fail_after=checkpoint)
    result = state(values)
    assert result["mappings"] == 0 and result["sessions"] == 0
    assert result["intent"]["status"] == "CREATED"
    assert result["reservation"] == result["runtime"] == "ACTIVE"
    settle(values)
    with connection_factory() as c:
        provisional = c.execute("SELECT * FROM telegram_provisional_sales_sessions WHERE provisional_session_id=%s",(values["provisional_id"],)).fetchone()
        assert provisional["state"] == "GRADUATED" and provisional["current_position"] == 2
        assert provisional["configured_base_price_minor"] == 1499
        assert provisional["actual_fingerprint_price_minor"] == 1497


@pytest.mark.parametrize("offering_type", ["SINGLE_IMAGE","BUNDLE"])
def test_real_single_and_bundle_settlement_replay(offering_type):
    values=fixture(offering_type=offering_type)
    first=settle(values); second=settle(values)
    assert first["mapping"].id == second["mapping"].id
    result=state(values)
    assert result["mappings"] == result["audits"] == 1
    assert result["intent"]["status"] == "PURCHASED"
    first_purchased_at = result["intent"]["purchased_at"]
    assert first_purchased_at is not None
    assert result["intent"]["actual_charged_price_minor"] == 1497
    assert result["intent"]["purchase_acknowledged_at"] is None
    assert result["reservation"] == result["runtime"] == "PURCHASED"
    assert result["prospect"] == first["mapping"].id
    assert state(values)["intent"]["purchased_at"] == first_purchased_at


def test_real_session_replay_advances_once():
    values=fixture(session=True, offering_type="PHOTOSET")
    settle(values); settle(values)
    with connection_factory() as c:
        assert c.execute("SELECT COUNT(*) n FROM sales_sessions WHERE fanvue_user_id=%s",(values["user"],)).fetchone()["n"] == 1
        assert c.execute("SELECT COUNT(*) n FROM sales_session_purchase_intents WHERE purchase_intent_id=%s",(values["intent_id"],)).fetchone()["n"] == 1
        row=c.execute("SELECT current_position FROM telegram_provisional_sales_sessions WHERE provisional_session_id=%s",(values["provisional_id"],)).fetchone()
        assert row["current_position"] == 2


def test_settlement_atomically_retires_unlock_and_projects_exact_ownership():
    values = fixture(session=True)
    with connection_factory() as c:
        c.execute("""INSERT INTO telegram_unlock_grants(
            unlock_grant_id,token_hash,purchase_intent_id,telegram_user_id,
            telegram_chat_id,commercial_offering_id,commercial_publication_id,
            fanvue_account_id,currency) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'USD')""",
            (uuid4(), uuid4().hex + uuid4().hex, values["intent_id"], values["telegram"],
             values["telegram"], values["offering_id"], values["publication_id"],
             values["account"]))
    settle(values); settle(values)
    with connection_factory() as c:
        grant = c.execute("SELECT state,revoked_at FROM telegram_unlock_grants WHERE purchase_intent_id=%s",
                          (values["intent_id"],)).fetchone()
        ownership = c.execute("""SELECT count(*) n FROM provider_purchase_asset_ownership
            WHERE fanvue_account_id=%s AND provider_transaction_id='tx-1'
              AND content_item_id=%s""", (values["account"], values["asset"])).fetchone()["n"]
    assert grant["state"] == "REVOKED" and grant["revoked_at"] is not None
    assert ownership == 1


def test_concurrent_settlement_converges():
    values=fixture(session=True, offering_type="PHOTOSET")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: settle(values), range(2)))
    assert results[0]["mapping"].id == results[1]["mapping"].id
    result=state(values)
    assert result["mappings"] == result["audits"] == result["sessions"] == 1


def test_wrong_evidence_fails_closed():
    values=fixture()
    service=PrivateChatPurchaseSettlementService(connection_factory=connection_factory)
    assert service.settle(fanvue_account_id=values["account"],currency="EUR",gross_minor=1497,
        source="media_link",buyer_uuid=values["buyer_uuid"],local_fanvue_user_id=values["user"],
        transaction_id="bad",payment_id="bad",event_id="bad",purchased_at=datetime.now(timezone.utc)) is None
    assert service.settle(fanvue_account_id=values["account"],currency="USD",gross_minor=999,
        source="media_link",buyer_uuid=values["buyer_uuid"],local_fanvue_user_id=values["user"],
        transaction_id="bad",payment_id="bad",event_id="bad",purchased_at=datetime.now(timezone.utc)) is None
    assert settle(values) is not None


def test_pre_purchase_actual_charge_reconciliation_is_guarded_and_idempotent():
    values = fixture(session=True)
    with connection_factory() as c:
        c.execute("""UPDATE purchase_intents SET status='CLICKED',
            presented_at=NOW(),clicked_at=NOW(),actual_charged_price_minor=1497
            WHERE purchase_intent_id=%s""", (values["intent_id"],))
    repository = PurchaseIntentRepository(connection_factory=connection_factory)
    first = repository.clear_unsettled_actual_charged_price(
        values["intent_id"], expected_telegram_user_id=values["telegram"],
    )
    second = repository.clear_unsettled_actual_charged_price(
        values["intent_id"], expected_telegram_user_id=values["telegram"],
    )
    assert first.actual_charged_price_minor is None
    assert second.actual_charged_price_minor is None
    with connection_factory() as c:
        row = c.execute("""SELECT status,actual_charged_price_minor,purchased_at,
            provider_transaction_order_id FROM purchase_intents
            WHERE purchase_intent_id=%s""", (values["intent_id"],)).fetchone()
    assert row == {"status": "CLICKED", "actual_charged_price_minor": None,
                   "purchased_at": None, "provider_transaction_order_id": None}


def test_pre_purchase_reconciliation_rejects_provider_evidence():
    values = fixture(session=True)
    with connection_factory() as c:
        c.execute("""UPDATE purchase_intents SET status='CLICKED',presented_at=NOW(),
            clicked_at=NOW(),actual_charged_price_minor=1497,
            provider_transaction_order_id='provider-evidence'
            WHERE purchase_intent_id=%s""", (values["intent_id"],))
    with pytest.raises(ValueError, match="not eligible"):
        PurchaseIntentRepository(
            connection_factory=connection_factory,
        ).clear_unsettled_actual_charged_price(
            values["intent_id"], expected_telegram_user_id=values["telegram"],
        )


def test_telegram_mapping_conflict_rolls_back():
    values=fixture(); settle(values)
    with connection_factory() as c:
        other_uuid=uuid4()
        other=c.execute("INSERT INTO fanvue_users(fanvue_user_uuid,fanvue_account_id) VALUES (%s,%s) RETURNING id",
                        (other_uuid,values["account"])).fetchone()["id"]
    with pytest.raises(ValueError):
        PrivateChatPurchaseSettlementService(connection_factory=connection_factory).settle(
            fanvue_account_id=values["account"],currency="USD",gross_minor=1497,
            source="media_link",buyer_uuid=other_uuid,local_fanvue_user_id=other,
            transaction_id="conflict",payment_id="conflict",event_id="conflict",
            purchased_at=datetime.now(timezone.utc))
    assert state(values)["mappings"] == 1


def test_fanvue_mapping_conflict_rolls_back():
    first=fixture(); settle(first)
    second=fixture()
    # Rebind the second synthetic purchase evidence to the first account and
    # purchaser while keeping its distinct Telegram identity.
    with connection_factory() as c:
        c.execute("UPDATE purchase_intents SET fanvue_account_id=%s WHERE purchase_intent_id=%s",
                  (first["account"],second["intent_id"]))
        c.execute("UPDATE fanvue_fingerprint_reservations SET fanvue_account_id=%s,exact_price_minor=1496 WHERE fingerprint_reservation_id=%s",
                  (first["account"],second["reservation_id"]))
    with pytest.raises(ValueError):
        PrivateChatPurchaseSettlementService(connection_factory=connection_factory).settle(
            fanvue_account_id=first["account"],currency="USD",gross_minor=1496,
            source="media_link",buyer_uuid=first["buyer_uuid"],
            local_fanvue_user_id=first["user"],transaction_id="fanvue-conflict",
            payment_id="fanvue-conflict",event_id="fanvue-conflict",
            purchased_at=datetime.now(timezone.utc))
    assert state(second)["mappings"] == 0

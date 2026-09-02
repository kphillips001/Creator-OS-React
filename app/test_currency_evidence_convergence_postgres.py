"""Real PostgreSQL coverage for signed transaction-family currency authority."""
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

import app.services.commerce_signal_service as signal_module
from app.repositories.commerce_signal_repository import CommerceSignalRepository
from app.services.commerce_signal_service import CommerceSignalService
from app.test_private_chat_settlement_postgres import fixture
from app.testing.postgres_safety import require_isolated_test_database_url


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def connection_factory():
    guarded = require_isolated_test_database_url(
        TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(guarded, row_factory=dict_row) as connection:
        yield connection


def family(monkeypatch):
    buyer, creator_uuid = uuid4(), uuid4()
    transaction = f"FVE-SYNTHETIC-{uuid4()}"
    with connection_factory() as connection:
        account = connection.execute(
            "INSERT INTO fanvue_accounts(account_name) VALUES (%s) RETURNING id",
            (f"Currency evidence {uuid4()}",),
        ).fetchone()["id"]
        creator = connection.execute(
            """INSERT INTO creator_profiles(fanvue_account_id,persona_name,
               display_name,age,gender,location) VALUES (%s,'Synthetic','Synthetic',
               25,'female','test') RETURNING id""",
            (str(account),),
        ).fetchone()["id"]
    monkeypatch.setattr(
        signal_module, "get_account_by_creator_uuid",
        lambda value: {"id": account} if str(value) == str(creator_uuid) else None,
    )
    repo = CommerceSignalRepository(connection_factory=connection_factory)
    row, _ = repo.get_or_create_reconciliation(
        fanvue_account_id=account, creator_profile_id=creator,
        provider_event_id=str(uuid4()), source_event_type="purchase_new",
        observed_transaction_id=transaction, external_fanvue_user_uuid=buyer,
        purchase_type="media", expected_amount_minor=302,
    )
    service = object.__new__(CommerceSignalService)
    service.repository = repo
    return {"buyer": buyer, "creator_uuid": creator_uuid, "transaction": transaction,
            "account": account, "creator": creator, "repo": repo,
            "service": service, "reconciliation_id": row["reconciliation_id"]}


def add_event(values, *, event_type="creator_payment_succeeded", currency="USD",
              signed=True, transaction=None, event_id=None):
    event_id = event_id or str(uuid4())
    transaction = transaction or values["transaction"]
    if event_type == "creator_payment_succeeded":
        payload = {"data": {"id": transaction, "gross": 302,
            "currency": currency, "creator": {"uuid": str(values["creator_uuid"])},
            "purchaser": {"uuid": str(values["buyer"])}},
            "type": "creator.payment.succeeded"}
    else:
        payload = {"transactionOrderId": transaction, "price": 302,
            "currency": currency, "recipientUuid": str(values["creator_uuid"]),
            "sender": {"uuid": str(values["buyer"])} }
    headers = {"x-fanvue-signature": "persisted-valid-signature"} if signed else {}
    with connection_factory() as connection:
        row = connection.execute(
            "SELECT id FROM webhook_events WHERE external_event_id=%s", (event_id,)
        ).fetchone()
        if row is None:
            row = connection.execute("""INSERT INTO webhook_events(
                internal_event_id,external_event_id,event_type,fanvue_account_id,
                fanvue_user_id,status,payload,headers,received_at)
                VALUES (%s,%s,%s,%s,%s,'processed',%s::jsonb,%s::jsonb,NOW())
                RETURNING id""",
                (uuid4(), event_id, event_type, str(values["creator_uuid"]),
                 str(values["buyer"]), __import__('json').dumps(payload),
                 __import__('json').dumps(headers))).fetchone()
    values["repo"].get_or_create_reconciliation(
        fanvue_account_id=values["account"], creator_profile_id=values["creator"],
        provider_event_id=event_id, source_event_type=event_type,
        observed_transaction_id=values["transaction"],
        external_fanvue_user_uuid=values["buyer"], purchase_type="media",
        expected_amount_minor=302, webhook_event_id=row["id"],
    )


def resolve(values, *, earnings_currency=None):
    reconciliation = values["repo"].get_reconciliation(values["reconciliation_id"])
    earning = {"transactionOrderId": values["transaction"], "gross": 302}
    if earnings_currency is not None:
        earning["currency"] = earnings_currency
    return values["service"]._resolve_transaction_currency(
        reconciliation=reconciliation, earning=earning,
        buyer_uuid=values["buyer"], gross_minor=302,
    )


def test_earnings_currency_and_matching_signed_webhook_converge(monkeypatch):
    values = family(monkeypatch); add_event(values)
    assert resolve(values, earnings_currency="USD")["currency"] == "USD"


def test_missing_earnings_currency_uses_signed_same_family_webhook(monkeypatch):
    values = family(monkeypatch); add_event(values)
    result = resolve(values)
    assert result == {"state": "RESOLVED", "currency": "USD",
                      "source": "SIGNED_TRANSACTION_FAMILY_WEBHOOK"}


@pytest.mark.parametrize("reverse", [False, True])
def test_complementary_events_are_arrival_order_independent_and_duplicates_converge(monkeypatch, reverse):
    values = family(monkeypatch)
    events = [("purchase_new", None), ("creator_payment_succeeded", "USD")]
    if reverse:
        events.reverse()
    for event_type, currency in events:
        add_event(values, event_type=event_type, currency=currency)
    duplicate_id = str(uuid4())
    add_event(values, event_type="purchase_new", currency=None, event_id=duplicate_id)
    add_event(values, event_type="purchase_new", currency=None, event_id=duplicate_id)
    assert resolve(values)["currency"] == "USD"
    with connection_factory() as connection:
        count = connection.execute(
                """SELECT count(*) n FROM commerce_signal_reconciliation_evidence
                   WHERE reconciliation_id=%s AND webhook_event_id IS NOT NULL""",
            (values["reconciliation_id"],),
        ).fetchone()["n"]
    assert count == 3


def test_earnings_and_webhook_currency_conflict_fails_closed(monkeypatch):
    values = family(monkeypatch); add_event(values, currency="EUR")
    assert resolve(values, earnings_currency="USD")["reason"] == "CURRENCY_EVIDENCE_CONFLICT"


def test_two_signed_webhook_currencies_conflict(monkeypatch):
    values = family(monkeypatch); add_event(values, currency="USD"); add_event(values, currency="EUR")
    assert resolve(values)["reason"] == "CURRENCY_EVIDENCE_CONFLICT"


def test_unsigned_and_wrong_family_currency_cannot_establish_authority(monkeypatch):
    values = family(monkeypatch)
    add_event(values, signed=False)
    add_event(values, transaction="FVE-WRONG-FAMILY")
    assert resolve(values) == {"state": "MISSING", "reason": "MISSING_AUTHORITATIVE_CURRENCY"}


def test_missing_currency_is_retryable_and_complementary_event_reactivates(monkeypatch):
    values = family(monkeypatch)
    values["repo"].mark_evidence_pending(
        values["reconciliation_id"], transaction_order_id=values["transaction"],
        external_fanvue_user_uuid=values["buyer"],
        earnings_record={"gross": 302}, reason="MISSING_AUTHORITATIVE_CURRENCY",
    )
    before = values["repo"].get_reconciliation(values["reconciliation_id"])
    assert before["state"] == "PENDING" and before["next_attempt_at"] is not None
    add_event(values, currency="USD")
    after = values["repo"].get_reconciliation(values["reconciliation_id"])
    assert after["state"] == "PENDING" and after["next_attempt_at"] is not None
    assert resolve(values)["currency"] == "USD"


def test_explicit_currency_conflict_is_quarantined_not_retried(monkeypatch):
    values = family(monkeypatch)
    row = values["repo"].mark_evidence_conflict(
        values["reconciliation_id"], transaction_order_id=values["transaction"],
        external_fanvue_user_uuid=values["buyer"],
        earnings_record={"gross": 302}, reason="CURRENCY_EVIDENCE_CONFLICT",
    )
    assert row["state"] == "FAILED" and row["next_attempt_at"] is None
    assert row["quarantined_at"] is not None


def test_durable_recovery_uses_signed_family_currency_and_settles_once(monkeypatch):
    values = fixture(session=True, offering_type="PHOTOSET")
    creator_uuid = uuid4()
    transaction = f"FVE-SIGNED-CURRENCY-{uuid4()}"
    purchased_at = datetime.now(timezone.utc)
    with connection_factory() as connection:
        connection.execute(
            "UPDATE fanvue_accounts SET fanvue_creator_uuid=%s WHERE id=%s",
            (creator_uuid, values["account"]),
        )
        connection.execute("DELETE FROM fanvue_users WHERE id=%s", (values["user"],))
        webhook = connection.execute(
            """INSERT INTO webhook_events(
                internal_event_id,external_event_id,event_type,fanvue_account_id,
                fanvue_user_id,status,payload,headers,received_at)
                VALUES (%s,%s,'creator_payment_succeeded',%s,%s,'processed',
                %s::jsonb,%s::jsonb,NOW()) RETURNING id""",
            (
                uuid4(), str(uuid4()), str(creator_uuid), str(values["buyer_uuid"]),
                __import__('json').dumps({"data": {
                    "id": transaction, "gross": 1497, "net": 1200,
                    "currency": "USD", "creator": {"uuid": str(creator_uuid)},
                    "purchaser": {"uuid": str(values["buyer_uuid"])}},
                    "type": "creator.payment.succeeded"}),
                __import__('json').dumps({"x-fanvue-signature": "persisted-valid-signature"}),
            ),
        ).fetchone()
    repo = CommerceSignalRepository(connection_factory=connection_factory)
    reconciliation, _ = repo.get_or_create_reconciliation(
        fanvue_account_id=values["account"], creator_profile_id=values["creator"],
        provider_event_id=str(uuid4()), source_event_type="creator_payment_succeeded",
        observed_transaction_id=transaction,
        external_fanvue_user_uuid=values["buyer_uuid"], purchase_type="media",
        expected_amount_minor=1497, webhook_event_id=webhook["id"],
    )

    class Provider:
        def get_earnings_by_transaction(self, requested):
            assert requested == transaction
            return {"data": [{
                "transactionOrderId": transaction, "gross": 1497, "net": 1200,
                "date": purchased_at.isoformat(), "source": "media_link",
                "status": "paid", "mediaLinkUuid": "canonical",
            }]}

    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    service = CommerceSignalService(client_factory=lambda _account: Provider())
    first = service.recover_reconciliation(reconciliation["reconciliation_id"])
    second = service.recover_reconciliation(reconciliation["reconciliation_id"])
    assert first["success"] is True and first["attribution"]["state"] == "ATTRIBUTED"
    assert second["success"] is True and second["attribution"]["state"] == "ATTRIBUTED"
    with connection_factory() as connection:
        counts = {
            "mappings": connection.execute(
                "SELECT count(*) n FROM telegram_identity_map WHERE telegram_user_id=%s",
                (values["telegram"],),
            ).fetchone()["n"],
            "transactions": connection.execute(
                "SELECT count(*) n FROM customer_commerce_transactions WHERE transaction_order_id=%s",
                (transaction,),
            ).fetchone()["n"],
            "ownership": connection.execute(
                "SELECT count(*) n FROM provider_purchase_asset_ownership WHERE provider_transaction_id=%s",
                (transaction,),
            ).fetchone()["n"],
        }
        intent = connection.execute(
            "SELECT status,actual_charged_price_minor,purchase_acknowledged_at "
            "FROM purchase_intents WHERE purchase_intent_id=%s",
            (values["intent_id"],),
        ).fetchone()
        grant = connection.execute(
            "SELECT state FROM telegram_unlock_grants WHERE purchase_intent_id=%s",
            (values["intent_id"],),
        ).fetchone()
    assert counts == {"mappings": 1, "transactions": 1, "ownership": 1}
    assert intent == {"status": "PURCHASED", "actual_charged_price_minor": 1497,
                      "purchase_acknowledged_at": None}
    assert grant is None or grant["state"] == "REVOKED"

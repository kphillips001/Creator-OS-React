"""Real PostgreSQL safety certification for Commerce Reconciliation Stage 2."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import json

from app.repositories.commerce_signal_repository import CommerceSignalRepository
from app.services.commerce_backlog_recovery_service import CommerceBacklogRecoveryService
from app.services.fingerprint_purchase_attribution_service import FingerprintPurchaseAttributionService
from app.test_private_chat_settlement_postgres import connection_factory, fixture


pytestmark = pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required")


def test_frozen_batch_is_exact_restartable_and_dry_run_has_zero_side_effects():
    marker = str(uuid4())
    with connection_factory() as c:
        c.execute("""INSERT INTO webhook_events(internal_event_id,external_event_id,event_type,
            fanvue_account_id,fanvue_user_id,status,payload,headers,received_at)
            VALUES (%s,%s,'message_received','1','2','received','{}','{}',NOW())""",
            (uuid4(), marker))
    service = CommerceBacklogRecoveryService(connection_factory=connection_factory)
    batch = service.freeze(batch_name=f"test-{uuid4()}")
    results = service.dry_run(batch.recovery_batch_id)
    assert batch.row_count == len(results)
    assert all(item["mappingChanges"] == item["sessionChanges"] == 0 for item in results)
    assert all(item["acknowledgementChanges"] == item["customerMessages"] == 0 for item in results)
    with connection_factory() as c:
        row = c.execute("SELECT status FROM webhook_events WHERE external_event_id=%s", (marker,)).fetchone()
    assert row["status"] == "received"


def test_two_reconciliation_workers_claim_disjoint_rows_and_stale_lease_recovers():
    values = fixture(); repo = CommerceSignalRepository(connection_factory=connection_factory)
    with connection_factory() as c:
        c.execute("UPDATE commerce_signal_reconciliations SET quarantined_at=NOW() WHERE quarantined_at IS NULL")
        ids = []
        for index in range(4):
            rid = uuid4(); ids.append(rid)
            c.execute("""INSERT INTO commerce_signal_reconciliations(
                reconciliation_id,fanvue_account_id,creator_profile_id,provider_event_id,
                source_event_type,observed_transaction_id,transaction_family_key,next_attempt_at)
                VALUES (%s,%s,%s,%s,'purchase_new',%s,%s,NOW())""",
                (rid, values["account"], values["creator"], str(uuid4()),
                 f"tx-{uuid4()}", str(uuid4()).replace('-','') + str(uuid4()).replace('-','')))
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda name: repo.claim_due(worker_instance_id=name, limit=2), ("a", "b")))
    left = {str(row["reconciliation_id"]) for row in claims[0]}
    right = {str(row["reconciliation_id"]) for row in claims[1]}
    assert len(left) == len(right) == 2 and left.isdisjoint(right)
    with connection_factory() as c:
        c.execute("UPDATE commerce_signal_reconciliations SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE reconciliation_id=%s", (ids[0],))
    reclaimed = repo.claim_due(worker_instance_id="restart", limit=100)
    assert str(ids[0]) in {str(row["reconciliation_id"]) for row in reclaimed}


def test_brand_new_purchaser_is_synchronized_without_creating_mapping():
    values = fixture(); buyer = uuid4(); captured = {}
    class Settlement:
        def settle(self, **kwargs): captured.update(kwargs); return {"ok": True}
    service = FingerprintPurchaseAttributionService(
        fanvue_user_resolver=lambda *_: None, settlement_service=Settlement(),
        connection_factory=connection_factory,
    )
    assert service.attribute(
        fanvue_account_id=values["account"], currency="USD", gross_minor=1497,
        source="media_link", buyer_uuid=buyer, transaction_id="new-buyer",
        payment_id="payment", event_id="event", purchased_at=datetime.now(timezone.utc),
    ) == {"ok": True}
    with connection_factory() as c:
        user = c.execute("SELECT id FROM fanvue_users WHERE fanvue_account_id=%s AND fanvue_user_uuid=%s", (values["account"], buyer)).fetchone()
        mappings = c.execute("SELECT count(*) n FROM telegram_identity_map WHERE fanvue_account_id=%s AND external_fanvue_user_uuid=%s", (values["account"], buyer)).fetchone()["n"]
    assert captured["local_fanvue_user_id"] == user["id"] and mappings == 0


def test_transaction_family_convergence_attaches_two_events_to_one_reconciliation():
    values = fixture(); repo = CommerceSignalRepository(connection_factory=connection_factory)
    common = dict(fanvue_account_id=values["account"], creator_profile_id=values["creator"],
                  observed_transaction_id=f"tx-{uuid4()}", external_fanvue_user_uuid=values["buyer_uuid"],
                  purchase_type="media", expected_amount_minor=1497)
    first, created = repo.get_or_create_reconciliation(provider_event_id=str(uuid4()), source_event_type="purchase_new", **common)
    second, created_second = repo.get_or_create_reconciliation(provider_event_id=str(uuid4()), source_event_type="creator_payment_succeeded", **common)
    assert created is True and created_second is False
    assert first["reconciliation_id"] == second["reconciliation_id"]
    with connection_factory() as c:
        count = c.execute("SELECT count(*) n FROM commerce_signal_reconciliation_evidence WHERE reconciliation_id=%s", (first["reconciliation_id"],)).fetchone()["n"]
    assert count == 2


def test_historical_recovery_records_finance_without_mapping_session_or_acknowledgement():
    values = fixture(session=True, offering_type="PHOTOSET")
    creator_uuid, buyer, transaction = uuid4(), uuid4(), f"historical-{uuid4()}"
    event_id = uuid4()
    payload = {"id": str(event_id), "type": "creator.payment.succeeded", "data": {
        "id": transaction, "creator": {"uuid": str(creator_uuid)},
        "purchaser": {"uuid": str(buyer)}, "source": "subscription",
    }}
    with connection_factory() as c:
        c.execute("UPDATE webhook_events SET status='quarantined' WHERE status IN ('received','failed')")
        c.execute("UPDATE fanvue_accounts SET fanvue_user_uuid=%s WHERE id=%s", (creator_uuid, values["account"]))
        c.execute("""INSERT INTO webhook_events(internal_event_id,external_event_id,event_type,
            fanvue_account_id,fanvue_user_id,status,payload,headers,received_at)
            VALUES (%s,%s,'creator_payment_succeeded',%s,%s,'received',%s::jsonb,'{}',NOW())""",
            (uuid4(), str(event_id), str(creator_uuid), str(buyer), json.dumps(payload)))
    class Provider:
        def get_earnings_by_transaction(self, tx):
            assert tx == transaction
            return {"data": [{"transactionOrderId": tx, "gross": 1200, "net": 900,
                "date": datetime.now(timezone.utc).isoformat(), "source": "subscription",
                "status": "paid"}]}
    service = CommerceBacklogRecoveryService(
        connection_factory=connection_factory, client_factory=lambda _: Provider())
    batch = service.freeze(batch_name=f"historical-{uuid4()}")
    service.dry_run(batch.recovery_batch_id)
    results = []
    while True:
        chunk = service.recover_supported(batch.recovery_batch_id, limit=20)
        if not chunk: break
        results.extend(chunk)
    recovered = next(item for item in results if item["financialRecorded"])
    assert recovered["mappingChanges"] == recovered["sessionChanges"] == 0
    assert recovered["acknowledgementChanges"] == recovered["customerMessages"] == 0
    with connection_factory() as c:
        assert c.execute("SELECT count(*) n FROM customer_commerce_transactions WHERE transaction_order_id=%s", (transaction,)).fetchone()["n"] == 1
        assert c.execute("SELECT count(*) n FROM telegram_identity_map WHERE external_fanvue_user_uuid=%s", (buyer,)).fetchone()["n"] == 0
        assert c.execute("SELECT purchase_acknowledged_at FROM purchase_intents WHERE purchase_intent_id=%s", (values["intent_id"],)).fetchone()["purchase_acknowledged_at"] is None
        assert c.execute("SELECT current_position FROM telegram_provisional_sales_sessions WHERE provisional_session_id=%s", (values["provisional_id"],)).fetchone()["current_position"] == 1
        reconciliation = c.execute("""SELECT state,reconciliation_mode,attribution_state
            FROM commerce_signal_reconciliations WHERE canonical_transaction_order_id=%s""",
            (transaction,)).fetchone()
        assert reconciliation == {"state": "VERIFIED", "reconciliation_mode": "HISTORICAL_RECOVERY",
                                  "attribution_state": "UNKNOWN"}


@pytest.mark.parametrize("checkpoint", (
    "after_customer_transaction", "after_ownership_projection",
    "before_reconciliation_completion",
))
def test_historical_recovery_rolls_back_authoritative_writes_on_crash(checkpoint):
    values = fixture(); creator_uuid, buyer = uuid4(), uuid4()
    transaction, event_id = f"rollback-{uuid4()}", uuid4()
    payload = {"data": {"id": transaction, "creator": {"uuid": str(creator_uuid)},
                        "purchaser": {"uuid": str(buyer)}, "source": "subscription"}}
    with connection_factory() as c:
        c.execute("UPDATE webhook_events SET status='quarantined' WHERE status IN ('received','failed')")
        c.execute("UPDATE fanvue_accounts SET fanvue_user_uuid=%s WHERE id=%s", (creator_uuid, values["account"]))
        c.execute("""INSERT INTO webhook_events(internal_event_id,external_event_id,event_type,
            fanvue_account_id,fanvue_user_id,status,payload,headers,received_at)
            VALUES (%s,%s,'creator_payment_succeeded',%s,%s,'received',%s::jsonb,'{}',NOW())""",
            (uuid4(), str(event_id), str(creator_uuid), str(buyer), json.dumps(payload)))
    class Provider:
        def get_earnings_by_transaction(self, _):
            return {"data": [{"transactionOrderId": transaction, "gross": 1200, "net": 900,
                "date": datetime.now(timezone.utc).isoformat(), "source": "subscription",
                "status": "paid"}]}
    def fail(name):
        if name == checkpoint:
            raise RuntimeError(f"injected:{name}")
    service = CommerceBacklogRecoveryService(connection_factory=connection_factory,
        client_factory=lambda _: Provider(), failure_injector=fail)
    batch = service.freeze(batch_name=f"rollback-{uuid4()}")
    service.dry_run(batch.recovery_batch_id)
    with pytest.raises(RuntimeError, match="injected"):
        service.recover_supported(batch.recovery_batch_id, limit=1)
    with connection_factory() as c:
        assert c.execute("SELECT count(*) n FROM customer_commerce_transactions WHERE transaction_order_id=%s", (transaction,)).fetchone()["n"] == 0
        assert c.execute("SELECT count(*) n FROM commerce_signal_reconciliations WHERE canonical_transaction_order_id=%s", (transaction,)).fetchone()["n"] == 0
        assert c.execute("SELECT status FROM webhook_events WHERE external_event_id=%s", (str(event_id),)).fetchone()["status"] == "received"

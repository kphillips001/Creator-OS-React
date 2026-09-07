from uuid import uuid4

from app.services.private_chat_purchase_settlement_service import (
    PrivateChatPurchaseSettlementService,
)


class Cursor:
    def __init__(self, results):
        self.results = list(results)
        self.current = None
        self.sql = []

    def execute(self, statement, arguments=()):
        self.sql.append((" ".join(statement.split()), arguments))
        self.current = self.results.pop(0) if self.results else []
        return self

    def fetchone(self):
        if isinstance(self.current, list):
            return self.current[0] if self.current else None
        return self.current

    def fetchall(self):
        if isinstance(self.current, list):
            return self.current
        return [] if self.current is None else [self.current]


def values(*, final=False, exact_ownership=True, state="AWAITING_PAYMENT"):
    session_id, intent_id, offering_id = uuid4(), uuid4(), uuid4()
    buyer_uuid, mapping_id = uuid4(), 17
    session = {
        "sales_session_id": session_id,
        "creator_profile_id": 3,
        "fanvue_account_id": 4,
        "fanvue_user_id": 5,
        "external_fanvue_user_uuid": buyer_uuid,
        "commercial_foundation_type": "PHOTOSHOOT",
        "commercial_foundation_reference": "shoot-1",
        "state": state,
        "progression_stage": "PROGRESSION",
    }
    intent = {
        "purchase_intent_id": intent_id,
        "commercial_offering_id": offering_id,
        "creator_profile_id": 3,
        "fanvue_account_id": 4,
    }
    mapping = {"id": mapping_id, "local_fanvue_user_id": 5}
    shots = [
        {"asset_id": 10, "access_recommendation": "PAID"},
        {"asset_id": 20, "access_recommendation": "PAID"},
    ]
    owned = [{"content_item_id": 10}, {"content_item_id": 20}]
    if not final:
        shots.append({"asset_id": 30, "access_recommendation": "PAID"})
    updated = {
        **session,
        "state": "COMPLETED" if final else "CONTINUING",
        "progression_stage": "FINALE" if final else "PROGRESSION",
    }
    results = [
        session,
        [{"asset_id": 20}],
        [{"asset_id": 20}],
        ([{"content_item_id": 20}] if exact_ownership else []),
    ]
    if exact_ownership:
        results.extend([
            {"strategy_data": {"shots": shots}},
            owned,
            updated,
            [],
        ])
    return Cursor(results), intent, mapping, buyer_uuid, updated


def reconcile(cursor, intent, mapping, buyer_uuid):
    return PrivateChatPurchaseSettlementService()._reconcile_sales_session(
        cursor,
        intent=intent,
        mapping=mapping,
        buyer_uuid=buyer_uuid,
        transaction_id="tx-exact",
    )


def test_exact_nonterminal_settlement_releases_payment_wait_on_same_session():
    cursor, intent, mapping, buyer_uuid, expected = values()
    result = reconcile(cursor, intent, mapping, buyer_uuid)
    assert result["sales_session_id"] == expected["sales_session_id"]
    assert result["state"] == "CONTINUING"
    update = next(sql for sql, _ in cursor.sql if sql.startswith("UPDATE public.sales_sessions"))
    assert "state=%s" in update and "state='AWAITING_PAYMENT'" in update
    assert cursor.sql[-1][1][7] == "Provider-settled Session step released payment wait for continuation."


def test_final_settlement_uses_existing_completed_with_purchase_semantics():
    cursor, intent, mapping, buyer_uuid, _ = values(final=True)
    result = reconcile(cursor, intent, mapping, buyer_uuid)
    assert result["state"] == "COMPLETED"
    assert result["progression_stage"] == "FINALE"
    update_args = next(args for sql, args in cursor.sql if sql.startswith("UPDATE public.sales_sessions"))
    assert update_args[:5] == (
        "COMPLETED", "FINALE", "COMPLETED_WITH_PURCHASE",
        "Final provider-settled Session step completed the ordered experience.", True,
    )


def test_missing_exact_ownership_does_not_advance_session():
    cursor, intent, mapping, buyer_uuid, expected = values(exact_ownership=False)
    result = reconcile(cursor, intent, mapping, buyer_uuid)
    assert result["state"] == "AWAITING_PAYMENT"
    assert not any(sql.startswith("UPDATE public.sales_sessions") for sql, _ in cursor.sql)


def test_unlinked_or_already_reconciled_session_is_idempotent():
    cursor = Cursor([None])
    assert reconcile(cursor, {"purchase_intent_id": uuid4()}, {}, uuid4()) is None

    cursor, intent, mapping, buyer_uuid, _ = values(state="CONTINUING")
    result = reconcile(cursor, intent, mapping, buyer_uuid)
    assert result["state"] == "CONTINUING"
    assert len(cursor.sql) == 1


def test_wrong_customer_or_session_binding_fails_closed():
    cursor, intent, mapping, buyer_uuid, _ = values()
    mapping["local_fanvue_user_id"] = 999
    result = reconcile(cursor, intent, mapping, buyer_uuid)
    assert result["state"] == "AWAITING_PAYMENT"
    assert len(cursor.sql) == 1

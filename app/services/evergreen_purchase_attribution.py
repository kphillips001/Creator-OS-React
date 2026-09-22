"""Resolve canonical purchase targets without rewriting expired predecessors."""

from datetime import datetime, timedelta, timezone
from uuid import uuid5, NAMESPACE_URL
from app.repositories.purchase_intent_repository import (
    purchase_intent_advisory_lock_key,
    PurchaseIntentRepository,
)

NAMESPACE = "creator-os-private-unlock"


def family_target(connection, intent_id, *, create_receipt_intent=False):
    if not connection.execute(
        "SELECT to_regclass('public.evergreen_offer_authorities') AS name"
    ).fetchone()["name"]:
        return intent_id
    family = connection.execute(
        """SELECT f.* FROM evergreen_offer_authorities f WHERE f.original_intent_id=%s
        OR EXISTS(SELECT 1 FROM evergreen_checkout_lineage l WHERE l.namespace=%s
            AND l.original_transaction_id=f.original_intent_id AND l.successor_id=%s)""",
        (intent_id, NAMESPACE, intent_id),
    ).fetchone()
    if not family:
        return intent_id
    b = family["binding"]
    connection.execute(
        "SELECT pg_advisory_xact_lock(%s::bigint)",
        (
            purchase_intent_advisory_lock_key(
                fanvue_account_id=int(b["fanvue_account_id"]),
                telegram_user_id=int(b["telegram_user_id"]),
            ),
        ),
    )
    latest = connection.execute(
        "SELECT * FROM evergreen_checkout_lineage WHERE namespace=%s AND original_transaction_id=%s ORDER BY generation DESC LIMIT 1",
        (NAMESPACE, family["original_intent_id"]),
    ).fetchone()
    target = latest["successor_id"] if latest else family["original_intent_id"]
    row = connection.execute(
        "SELECT * FROM purchase_intents WHERE purchase_intent_id=%s FOR UPDATE",
        (target,),
    ).fetchone()
    if create_receipt_intent and row["status"] == "EXPIRED":
        # Record late payment on a fresh canonical intent. Never revive the old
        # row; this child is settled in the same transaction, never presented.
        now = datetime.now(timezone.utc)
        target = uuid5(
            NAMESPACE_URL,
            "evergreen-checkout:"
            + NAMESPACE
            + ":successor:"
            + str(row["purchase_intent_id"]),
        )
        values = dict(
            row,
            purchase_intent_id=target,
            correlation_id=target,
            expires_at=now + timedelta(hours=72),
            created_metadata={
                **row["created_metadata"],
                "evergreen_original_intent_id": str(family["original_intent_id"]),
                "late_payment_receipt": True,
            },
        )
        with connection.cursor() as cursor:
            PurchaseIntentRepository()._insert(cursor, values)
        connection.execute(
            """INSERT INTO evergreen_checkout_lineage(namespace,alias_id,original_transaction_id,
            generation,predecessor_id,successor_id,refresh_reason,refreshed_at,predecessor_price_minor,
            successor_price_minor,currency,eligibility_result,runtime_state,runtime_reason)
            VALUES(%s,%s,%s,%s,%s,%s,'TRANSACTION_EXPIRED',%s,%s,%s,%s,'ELIGIBLE','READY','LATE_PAYMENT_RECEIPT')""",
            (
                NAMESPACE,
                family["unlock_grant_id"],
                family["original_intent_id"],
                latest["generation"] + 1 if latest else 1,
                row["purchase_intent_id"],
                target,
                now,
                family["final_price_minor"],
                family["final_price_minor"],
                family["currency"],
            ),
        )
    return target

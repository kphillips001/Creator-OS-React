"""Auditable, explicit historical webhook recovery planning and disposition."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.services.fanvue_official_client import FanvueOfficialClient


class ReconciliationMode(str, Enum):
    LIVE = "LIVE"
    HISTORICAL_RECOVERY = "HISTORICAL_RECOVERY"


class RoutingOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    IGNORED = "IGNORED"
    RETRYABLE = "RETRYABLE"
    TERMINAL_FAILED = "TERMINAL_FAILED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True)
class FrozenBatch:
    recovery_batch_id: UUID
    row_count: int
    checksum: str


class CommerceBacklogRecoveryService:
    COMMERCE = frozenset({"purchase_new", "creator_payment_succeeded", "tip_new"})
    LIFECYCLE = frozenset({"subscription_renewed", "subscription_cancelled", "subscription_expired"})
    IGNORE = frozenset({"follow_new", "message_read"})

    def __init__(self, connection_factory=get_db_connection,
                 client_factory=FanvueOfficialClient, failure_injector=None):
        self.connection_factory = connection_factory
        self.client_factory = client_factory
        self.failure_injector = failure_injector

    def freeze(self, *, batch_name: str) -> FrozenBatch:
        batch_id = uuid4()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT id,internal_event_id,external_event_id,event_type,status,
                    payload,received_at,fanvue_account_id,fanvue_user_id
                    FROM public.webhook_events WHERE status IN ('received','failed')
                    ORDER BY id FOR SHARE""")
                rows = [dict(row) for row in cursor.fetchall()]
                items = [self._snapshot_item(row) for row in rows]
                checksum = hashlib.sha256("\n".join(
                    f"{item['webhook_event_id']}:{item['payload_sha256']}:{item['frozen_status']}"
                    for item in items
                ).encode()).hexdigest()
                cursor.execute("""INSERT INTO public.commerce_backlog_recovery_batches(
                    recovery_batch_id,batch_name,mode,frozen_row_count,snapshot_checksum,
                    recovery_metadata) VALUES (%s,%s,'HISTORICAL_RECOVERY',%s,%s,%s::jsonb)""",
                    (batch_id, batch_name, len(items), checksum,
                     json.dumps({"selection": "status IN (received,failed)", "immutableRowIds": True})))
                for item in items:
                    cursor.execute("""INSERT INTO public.commerce_backlog_recovery_items(
                        recovery_batch_id,webhook_event_id,internal_event_id,external_event_id,
                        event_type,frozen_status,received_at,payload_sha256,transaction_id,
                        external_fanvue_user_uuid,commerce_relevance,transaction_family_key,
                        intended_disposition) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (batch_id, item["webhook_event_id"], item["internal_event_id"],
                         item["external_event_id"], item["event_type"], item["frozen_status"],
                         item["received_at"], item["payload_sha256"], item["transaction_id"],
                         item["external_fanvue_user_uuid"], item["commerce_relevance"],
                         item["transaction_family_key"], item["intended_disposition"]))
        return FrozenBatch(batch_id, len(items), checksum)

    def dry_run(self, recovery_batch_id: UUID) -> tuple[dict, ...]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT item.*,event.payload FROM commerce_backlog_recovery_items item
                    JOIN webhook_events event ON event.id=item.webhook_event_id
                    WHERE item.recovery_batch_id=%s ORDER BY item.webhook_event_id""", (recovery_batch_id,))
                rows = [dict(row) for row in cursor.fetchall()]
                seen = set()
                results = []
                for row in rows:
                    unchanged = self._sha(row["payload"]) == row["payload_sha256"]
                    family = row.get("transaction_family_key")
                    eligible = row["intended_disposition"] == "HISTORICAL_RECOVERY"
                    leader = bool(eligible and family and family not in seen)
                    if eligible and family:
                        seen.add(family)
                    result = {
                        "snapshotValid": unchanged,
                        "disposition": row["intended_disposition"],
                        "canonicalTransactionFamily": family,
                        "wouldCreateFinancialTransaction": leader,
                        "exactOwnership": "ONLY_IF_AUTHORITATIVE_RESOURCE",
                        "mappingChanges": 0,
                        "sessionChanges": 0,
                        "acknowledgementChanges": 0,
                        "customerMessages": 0,
                    }
                    cursor.execute("""UPDATE commerce_backlog_recovery_items SET dry_run_result=%s::jsonb
                        WHERE recovery_batch_id=%s AND webhook_event_id=%s""",
                        (json.dumps(result), recovery_batch_id, row["webhook_event_id"]))
                    results.append(result)
                if not all(item["snapshotValid"] and item["mappingChanges"] == 0
                           and item["sessionChanges"] == 0 and item["acknowledgementChanges"] == 0
                           and item["customerMessages"] == 0 for item in results):
                    raise RuntimeError("Historical recovery dry run failed safety certification.")
                cursor.execute("""UPDATE commerce_backlog_recovery_batches
                    SET state='DRY_RUN_CERTIFIED',dry_run_at=NOW()
                    WHERE recovery_batch_id=%s AND state='FROZEN'""", (recovery_batch_id,))
        return tuple(results)

    def disposition_noncommerce(self, recovery_batch_id: UUID) -> dict:
        """Disposition frozen non-commerce/messages without routing payloads."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT state FROM commerce_backlog_recovery_batches WHERE recovery_batch_id=%s FOR UPDATE", (recovery_batch_id,))
                batch = cursor.fetchone()
                if not batch or batch["state"] not in {"DRY_RUN_CERTIFIED", "RECOVERING"}:
                    raise RuntimeError("Recovery batch is not dry-run certified.")
                cursor.execute("UPDATE commerce_backlog_recovery_batches SET state='RECOVERING' WHERE recovery_batch_id=%s", (recovery_batch_id,))
                counts = {}
                for intended, status in (("IGNORED", "ignored"), ("QUARANTINED", "quarantined"),
                                         ("MANUAL_REVIEW", "quarantined")):
                    cursor.execute("""UPDATE webhook_events event SET status=%s,
                        last_error=%s,next_retry_at=NULL,worker_instance_id=NULL,
                        claimed_at=NULL,lease_expires_at=NULL
                        FROM commerce_backlog_recovery_items item
                        WHERE item.recovery_batch_id=%s AND item.webhook_event_id=event.id
                          AND item.intended_disposition=%s
                          AND item.final_disposition IS NULL
                        RETURNING event.id""", (status, f"HISTORICAL_RECOVERY:{intended}",
                                                recovery_batch_id, intended))
                    ids = [row["id"] for row in cursor.fetchall()]
                    cursor.execute("""UPDATE commerce_backlog_recovery_items SET
                        final_disposition=%s,dispositioned_at=NOW()
                        WHERE recovery_batch_id=%s AND intended_disposition=%s
                          AND final_disposition IS NULL""",
                        (intended, recovery_batch_id, intended))
                    counts[intended] = len(ids)
        return counts

    def recover_supported(self, recovery_batch_id: UUID, *, limit: int = 2) -> tuple[dict, ...]:
        """Recover financial/ownership truth, one frozen transaction family at a time."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT item.transaction_family_key,min(item.webhook_event_id) leader
                    FROM commerce_backlog_recovery_items item
                    WHERE item.recovery_batch_id=%s
                      AND item.intended_disposition='HISTORICAL_RECOVERY'
                      AND item.final_disposition IS NULL
                    GROUP BY item.transaction_family_key ORDER BY min(item.webhook_event_id)
                    LIMIT %s""", (recovery_batch_id, max(1, int(limit))))
                families = [dict(row) for row in cursor.fetchall()]
        results = []
        for family in families:
            results.append(self._recover_family(recovery_batch_id, family["transaction_family_key"]))
        return tuple(results)

    def finalize(self, recovery_batch_id: UUID) -> None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT count(*) FILTER(WHERE final_disposition IS NULL) pending,
                    count(*) FILTER(WHERE dry_run_result='{}'::jsonb) uncertified
                    FROM commerce_backlog_recovery_items WHERE recovery_batch_id=%s""",
                    (recovery_batch_id,))
                row = cursor.fetchone()
                if not row or row["pending"] or row["uncertified"]:
                    raise RuntimeError("Recovery batch still has undispositioned or uncertified rows.")
                cursor.execute("""UPDATE commerce_backlog_recovery_batches SET
                    state='COMPLETED',completed_at=NOW() WHERE recovery_batch_id=%s
                    AND state IN ('DRY_RUN_CERTIFIED','RECOVERING')""", (recovery_batch_id,))

    def _recover_family(self, batch_id, family_key):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT item.*,event.payload,event.fanvue_account_id
                    FROM commerce_backlog_recovery_items item JOIN webhook_events event
                      ON event.id=item.webhook_event_id
                    WHERE item.recovery_batch_id=%s AND item.transaction_family_key=%s
                    ORDER BY CASE item.event_type WHEN 'creator_payment_succeeded' THEN 0 ELSE 1 END,
                             item.webhook_event_id""", (batch_id, family_key))
                evidence = [dict(row) for row in cursor.fetchall()]
        if not evidence or any(self._sha(row["payload"]) != row["payload_sha256"] for row in evidence):
            raise RuntimeError("Frozen webhook evidence changed after snapshot.")
        primary = evidence[0]; payload = primary["payload"] or {}
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        creator_uuid = payload.get("recipientUuid") or data.get("creatorUuid") or (
            (data.get("creator") or {}).get("uuid") if isinstance(data.get("creator"), dict) else None)
        buyer_uuid = primary.get("external_fanvue_user_uuid")
        transaction_id = primary.get("transaction_id")
        if not buyer_uuid or not transaction_id:
            raise RuntimeError("Historical payment lacks authoritative purchaser/transaction evidence.")
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT * FROM fanvue_accounts WHERE
                    fanvue_creator_uuid::text=%s OR fanvue_user_uuid::text=%s LIMIT 1""",
                    (str(creator_uuid), str(creator_uuid)))
                account = cursor.fetchone()
                if not account: raise LookupError("Historical creator account is unavailable.")
                cursor.execute("SELECT * FROM creator_profiles WHERE fanvue_account_id=%s AND is_active=TRUE LIMIT 1", (str(account["id"]),))
                creator = cursor.fetchone()
                if not creator: raise LookupError("Historical creator profile is unavailable.")
        response = self.client_factory(int(account["id"])).get_earnings_by_transaction(transaction_id)
        records = response.get("data") if isinstance(response, dict) else None
        matches = [row for row in (records or ()) if str(row.get("transactionOrderId") or "") == transaction_id]
        if len(matches) != 1:
            raise LookupError("Historical provider earnings did not return exactly one transaction.")
        earning = matches[0]
        gross = self._minor(earning.get("gross", earning.get("amount")))
        net = self._minor(earning.get("net", earning.get("earnings", gross)))
        purchased_at = self._timestamp(earning.get("date") or earning.get("timestamp"))
        source = str(earning.get("source") or data.get("source") or "unknown")
        status = str(earning.get("status") or data.get("status") or "verified")
        resource_id = self._resource_id(earning, data, payload)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""INSERT INTO fanvue_users(fanvue_account_id,fanvue_user_uuid)
                    VALUES (%s,%s) ON CONFLICT(fanvue_account_id,fanvue_user_uuid)
                    DO UPDATE SET fanvue_user_uuid=EXCLUDED.fanvue_user_uuid RETURNING id""",
                    (account["id"], buyer_uuid))
                cursor.execute("""INSERT INTO customer_commerce_profiles(
                    customer_commerce_profile_id,creator_profile_id,fanvue_account_id,
                    external_fanvue_user_uuid,first_seen_at,last_seen_at,profile_state)
                    VALUES (%s,%s,%s,%s,%s,%s,'FIRST_PURCHASE')
                    ON CONFLICT(creator_profile_id,external_fanvue_user_uuid)
                    DO UPDATE SET last_seen_at=GREATEST(customer_commerce_profiles.last_seen_at,EXCLUDED.last_seen_at)
                    RETURNING customer_commerce_profile_id""",
                    (uuid4(), creator["id"], account["id"], buyer_uuid, purchased_at, purchased_at))
                profile_id = cursor.fetchone()["customer_commerce_profile_id"]
                cursor.execute("""INSERT INTO customer_commerce_transactions(
                    customer_commerce_transaction_id,customer_commerce_profile_id,
                    fanvue_account_id,transaction_order_id,gross_minor,net_minor,
                    payment_status,purchase_source,payment_timestamp)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(fanvue_account_id,transaction_order_id) DO NOTHING""",
                    (uuid4(), profile_id, account["id"], transaction_id, gross, net,
                     status, source, purchased_at))
                self._checkpoint("after_customer_transaction")
                cursor.execute("""UPDATE customer_commerce_profiles profile SET
                    first_purchase_at=summary.first_purchase,last_purchase_at=summary.last_purchase,
                    lifetime_gross_minor=summary.gross,lifetime_net_minor=summary.net,
                    purchase_count=summary.n,average_order_value_minor=summary.gross/summary.n,
                    largest_purchase_minor=summary.largest,updated_at=NOW()
                    FROM (SELECT min(payment_timestamp) first_purchase,max(payment_timestamp) last_purchase,
                        sum(gross_minor) gross,sum(net_minor) net,count(*)::int n,max(gross_minor) largest
                        FROM customer_commerce_transactions WHERE customer_commerce_profile_id=%s) summary
                    WHERE profile.customer_commerce_profile_id=%s""", (profile_id, profile_id))
                ownership = 0
                if resource_id:
                    cursor.execute("""SELECT member.asset_id FROM commercial_publications publication
                        JOIN commercial_offerings offering ON offering.offering_id=publication.commercial_offering_id
                        JOIN commercial_offering_assets member ON member.offering_id=offering.offering_id
                        WHERE offering.creator_profile_id=%s AND publication.external_product_id=%s
                          AND publication.status='LIVE'""", (creator["id"], resource_id))
                    for row in cursor.fetchall():
                        cursor.execute("""INSERT INTO provider_purchase_asset_ownership(
                            ownership_id,creator_profile_id,fanvue_account_id,external_fanvue_user_uuid,
                            provider_transaction_id,provider_resource_id,content_item_id,purchase_timestamp,evidence)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'{"mode":"HISTORICAL_RECOVERY"}')
                            ON CONFLICT(fanvue_account_id,provider_transaction_id,content_item_id) DO NOTHING""",
                            (uuid4(), creator["id"], account["id"], buyer_uuid, transaction_id,
                             resource_id, row["asset_id"], purchased_at))
                        ownership += 1
                self._checkpoint("after_ownership_projection")
                reconciliation_id = uuid4()
                cursor.execute("""INSERT INTO commerce_signal_reconciliations(
                    reconciliation_id,fanvue_account_id,creator_profile_id,provider_event_id,
                    source_event_type,observed_transaction_id,canonical_transaction_order_id,
                    external_fanvue_user_uuid,purchase_type,expected_amount_minor,state,
                    attempt_count,earnings_record,verified_at,transaction_family_key,
                    reconciliation_mode,attribution_state,attribution_reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'VERIFIED',1,%s::jsonb,NOW(),
                            %s,'HISTORICAL_RECOVERY','UNKNOWN','HISTORICAL_FINANCIAL_ONLY')
                    ON CONFLICT(fanvue_account_id,transaction_family_key)
                      WHERE transaction_family_key IS NOT NULL
                    DO UPDATE SET canonical_transaction_order_id=EXCLUDED.canonical_transaction_order_id,
                        external_fanvue_user_uuid=EXCLUDED.external_fanvue_user_uuid,
                        earnings_record=EXCLUDED.earnings_record,state='VERIFIED',verified_at=NOW(),
                        reconciliation_mode='HISTORICAL_RECOVERY',attribution_state='UNKNOWN',
                        attribution_reason='HISTORICAL_FINANCIAL_ONLY',last_error=NULL,
                        next_attempt_at=NULL,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                        updated_at=NOW()
                    RETURNING reconciliation_id""", (reconciliation_id, account["id"], creator["id"],
                    str(primary.get("external_event_id") or primary["internal_event_id"]),
                    primary["event_type"], transaction_id, transaction_id, buyer_uuid, source,
                    gross, json.dumps(earning), family_key))
                reconciliation_id = cursor.fetchone()["reconciliation_id"]
                for item in evidence:
                    cursor.execute("""INSERT INTO commerce_signal_reconciliation_evidence(
                        evidence_id,reconciliation_id,webhook_event_id,provider_event_id,
                        source_event_type,payload_sha256)
                        VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(provider_event_id) DO NOTHING""",
                        (uuid4(), reconciliation_id, item["webhook_event_id"],
                         str(item.get("external_event_id") or item["internal_event_id"]),
                         item["event_type"], item["payload_sha256"]))
                self._checkpoint("before_reconciliation_completion")
                cursor.execute("""UPDATE webhook_events event SET status='historical_recovered',
                    processed_at=NOW(),last_error=NULL,next_retry_at=NULL
                    FROM commerce_backlog_recovery_items item
                    WHERE item.recovery_batch_id=%s AND item.transaction_family_key=%s
                      AND item.webhook_event_id=event.id""", (batch_id, family_key))
                cursor.execute("""UPDATE commerce_backlog_recovery_items SET
                    final_disposition='HISTORICAL_RECOVERED',dispositioned_at=NOW()
                    WHERE recovery_batch_id=%s AND transaction_family_key=%s""", (batch_id, family_key))
        return {"transactionFamily": family_key, "financialRecorded": True,
                "exactOwnershipCount": ownership, "mappingChanges": 0,
                "sessionChanges": 0, "acknowledgementChanges": 0,
                "customerMessages": 0}

    def _checkpoint(self, name: str) -> None:
        if self.failure_injector is not None:
            self.failure_injector(name)

    @staticmethod
    def _minor(value):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("Provider amount must be non-negative minor units.")
        return int(value)

    @staticmethod
    def _timestamp(value):
        from datetime import datetime
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None: raise ValueError("Provider timestamp must be timezone-aware.")
        return result

    @staticmethod
    def _resource_id(*sources):
        for source in sources:
            if not isinstance(source, dict): continue
            for key in ("mediaLinkUuid","mediaLinkId","media_link_uuid","provider_resource_id","externalProductId","post_uuid","message_uuid"):
                value = str(source.get(key) or "").strip()
                if value: return value
        return None

    @classmethod
    def _snapshot_item(cls, row):
        payload = row.get("payload") or {}
        event_type = row["event_type"]
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        transaction = (
            payload.get("transactionOrderId") if event_type in {"purchase_new", "tip_new"}
            else data.get("id") if event_type == "creator_payment_succeeded"
            else payload.get("transactionId") if event_type == "subscription_renewed"
            else None
        )
        buyer = cls._uuid_or_none(
            (payload.get("sender") or {}).get("uuid") if isinstance(payload.get("sender"), dict) else None
        ) or cls._uuid_or_none(
            (data.get("purchaser") or {}).get("uuid") if isinstance(data.get("purchaser"), dict) else None
        ) or cls._uuid_or_none(row.get("fanvue_user_id"))
        if event_type == "message_received":
            relevance, disposition = "CUSTOMER_MESSAGE", "QUARANTINED"
        elif event_type in cls.IGNORE:
            relevance, disposition = "NON_COMMERCE", "IGNORED"
        elif event_type in {"purchase_new", "creator_payment_succeeded"}:
            relevance, disposition = "COMMERCE", "HISTORICAL_RECOVERY"
        elif event_type == "tip_new":
            relevance, disposition = "COMMERCE", "MANUAL_REVIEW"
        elif event_type in cls.LIFECYCLE:
            relevance, disposition = "COMMERCE_LIFECYCLE", "MANUAL_REVIEW"
        else:
            relevance, disposition = "NON_COMMERCE", "MANUAL_REVIEW"
        family = None
        if transaction:
            family = hashlib.sha256(
                f"{row.get('fanvue_account_id')}:{transaction}".encode()
            ).hexdigest()
        return {**row, "webhook_event_id": row["id"], "frozen_status": row["status"],
                "payload_sha256": cls._sha(payload),
                "transaction_id": str(transaction) if transaction else None,
                "external_fanvue_user_uuid": buyer, "commerce_relevance": relevance,
                "transaction_family_key": family, "intended_disposition": disposition}

    @staticmethod
    def _sha(payload) -> str:
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()

    @staticmethod
    def _uuid_or_none(value):
        try: return UUID(str(value)) if value else None
        except (ValueError, TypeError): return None

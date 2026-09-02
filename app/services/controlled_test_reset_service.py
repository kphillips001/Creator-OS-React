"""Fail-closed reset of the one configured pre-purchase Telegram smoke-test identity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from app.database import get_db_connection
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService


class ControlledTestResetBlocked(RuntimeError):
    def __init__(self, preview):
        super().__init__("; ".join(preview["blockers"]))
        self.preview = preview


@dataclass(frozen=True)
class ControlledTestResetService:
    connection_factory: object = get_db_connection
    boundary: object = None

    CATEGORIES = (
        "controlled conversation", "ordinary reply operations", "decision history",
        "prospect relationship/preferences", "controlled identity observation",
        "disposable unsettled controlled PurchaseIntents",
    )
    DISPOSABLE_INTENT_STATES = frozenset({"CREATED"})
    BLOCKING_DELIVERY_STATES = frozenset({
        "SENDING", "TELEGRAM_ACCEPTED", "CONFIRMED", "AMBIGUOUS",
    })
    BLOCKING_RUNTIME_STATES = frozenset({
        "ACTIVE", "PURCHASED", "UNCERTAIN", "DELETE_REQUESTED",
        "DELETE_FAILED", "ORPHANED",
    })

    def __post_init__(self):
        if self.boundary is None:
            object.__setattr__(self, "boundary", ControlledAutonomyTestService())

    def preview(self):
        user_id, chat_id = self._identity()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            checks = self._checks(cursor, user_id, chat_id, lock=False)
            counts = self._counts(
                cursor, user_id, chat_id,
                checks.get("controlled_creator_profile_id"),
                checks.get("controlled_fanvue_account_id"),
            )
        return self._preview(user_id, checks, counts)

    def execute(self):
        user_id, chat_id = self._identity()
        reset_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s),%s)",
                           ("controlled_telegram_test_reset", int(user_id) % 2147483647))
            # Resolve configuration again inside the serialized reset boundary.
            if self.boundary.configured_identity() != (user_id, chat_id):
                raise ControlledTestResetBlocked(self._preview(user_id,
                    {"configured_identity_match": False}, {}))
            checks = self._checks(cursor, user_id, chat_id, lock=True)
            before = self._counts(
                cursor, user_id, chat_id,
                checks.get("controlled_creator_profile_id"),
                checks.get("controlled_fanvue_account_id"),
            )
            preview = self._preview(user_id, checks, before)
            if not preview["allowed"]:
                self._audit(cursor, reset_id, user_id, checks, {}, True,
                            "BLOCKED", "; ".join(preview["blockers"]))
                return {**preview, "executed": False, "resetId": str(reset_id)}

            removed = {}
            disposal = self._delete_disposable_intents(
                cursor, checks.get("disposable_purchase_intents", ()),
            )
            removed.update(disposal)
            cursor.execute("""DELETE FROM chat_messages
                WHERE raw_payload->>'provider'='TELEGRAM'
                  AND raw_payload->>'telegram_chat_id'=%s""", (str(chat_id),))
            removed["controlledConversationMessages"] = cursor.rowcount
            cursor.execute("""DELETE FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s""",
                (chat_id, user_id))
            removed["ordinaryReplyOperations"] = cursor.rowcount
            removed["decisionSnapshots"] = removed["ordinaryReplyOperations"]
            cursor.execute("""DELETE FROM telegram_sales_prospects
                WHERE telegram_user_id=%s AND telegram_chat_id=%s
                  AND creator_profile_id=%s AND fanvue_account_id=%s""",
                (user_id, chat_id, checks.get("controlled_creator_profile_id"),
                 checks.get("controlled_fanvue_account_id")))
            removed["controlledProspectRows"] = cursor.rowcount
            cursor.execute("DELETE FROM telegram_identity_observations WHERE telegram_user_id=%s", (user_id,))
            removed["identityObservations"] = cursor.rowcount
            self._audit(cursor, reset_id, user_id, checks, removed, True, "SUCCEEDED", None)
        return {"allowed": True, "executed": True, "alreadyClean": not any(removed.values()),
                "resetId": str(reset_id), "removedCounts": removed,
                "commercePreserved": True, "identity": self._masked(user_id)}

    def _identity(self):
        configured = self.boundary.configured_identity()
        if configured is None:
            raise ValueError("No controlled Telegram test customer configured")
        return tuple(map(int, configured))

    def _checks(self, cursor, user_id, chat_id, *, lock):
        suffix = " FOR UPDATE" if lock else ""
        cursor.execute("""SELECT creator_profile_id,fanvue_account_id
            FROM telegram_sales_prospects
            WHERE telegram_user_id=%s AND telegram_chat_id=%s""" + suffix,
            (user_id, chat_id))
        prospect_scopes = {
            (int(row["creator_profile_id"]), int(row["fanvue_account_id"]))
            for row in cursor.fetchall()
        }
        controlled_account_scope = (
            next(iter(prospect_scopes)) if len(prospect_scopes) == 1 else None
        )
        cursor.execute("SELECT id FROM telegram_identity_map WHERE telegram_user_id=%s" + suffix, (user_id,))
        mappings = len(cursor.fetchall())
        cursor.execute("SELECT * FROM purchase_intents WHERE telegram_user_id=%s OR telegram_chat_id=%s" + suffix,
                       (user_id, chat_id)); intents = [dict(row) for row in cursor.fetchall()]
        intent_ids = [row["purchase_intent_id"] for row in intents]
        order_ids = [row["provider_transaction_order_id"] for row in intents if row.get("provider_transaction_order_id")]
        settled = sum(1 for row in intents if row.get("purchased_at") is not None or row.get("status") in {"PURCHASED","SETTLED","FULFILLED"})
        cursor.execute("""SELECT * FROM fanvue_fingerprint_reservations
            WHERE telegram_user_id=%s""" + suffix, (user_id,)); reservations = [dict(row) for row in cursor.fetchall()]
        purchased_fp = sum(1 for row in reservations if row.get("purchased_at") is not None or row.get("provider_transaction_reference") or row.get("state") == "PURCHASED")
        active_runtime = 0
        if intent_ids:
            cursor.execute("""SELECT * FROM fanvue_runtime_media_links
                WHERE purchase_intent_id=ANY(%s) AND state IN ('ACTIVE','PURCHASED','UNCERTAIN')""" + suffix,
                (intent_ids,)); active_runtime = len(cursor.fetchall())
        transactions = 0
        if order_ids:
            cursor.execute("SELECT count(*) n FROM customer_commerce_transactions WHERE transaction_order_id=ANY(%s)", (order_ids,))
            transactions = int(cursor.fetchone()["n"])
        cursor.execute("""SELECT count(*) n FROM telegram_provisional_sales_sessions
            WHERE telegram_user_id=%s AND (first_purchase_recorded_at IS NOT NULL
              OR state IN ('PURCHASED','COMPLETED'))""", (user_id,))
        session_purchases = int(cursor.fetchone()["n"])
        if intent_ids:
            cursor.execute("""SELECT count(*) n FROM sales_session_purchase_intents spi
                JOIN sales_sessions s ON s.sales_session_id=spi.sales_session_id
                WHERE spi.purchase_intent_id=ANY(%s) AND s.state IN ('PURCHASED','COMPLETED')""", (intent_ids,))
            session_purchases += int(cursor.fetchone()["n"])
        disposable = []
        intent_blockers = []
        for intent in intents:
            evidence = self._intent_evidence(
                cursor, intent, user_id, chat_id,
                controlled_account_scope=controlled_account_scope, lock=lock,
            )
            eligibility = self._disposal_eligibility(intent, evidence, user_id, chat_id)
            if eligibility["eligible"]:
                disposable.append({
                    "purchase_intent_id": str(intent["purchase_intent_id"]),
                    "state": str(intent.get("status") or ""),
                    "reason": eligibility["reason"],
                })
            else:
                intent_blockers.append({
                    "purchase_intent_id": str(intent["purchase_intent_id"]),
                    "reasons": eligibility["reasons"],
                })
        return {"configured_identity_match": self.boundary.configured_identity() == (user_id, chat_id),
                "controlled_account_scope_ambiguous": len(prospect_scopes) > 1,
                "controlled_creator_profile_id": controlled_account_scope[0] if controlled_account_scope else None,
                "controlled_fanvue_account_id": controlled_account_scope[1] if controlled_account_scope else None,
                "mapping_count": mappings, "purchase_intent_count": len(intents),
                "settled_purchase_intent_count": settled, "customer_transaction_count": transactions,
                "purchased_fingerprint_count": purchased_fp, "active_runtime_media_link_count": active_runtime,
                "session_purchase_count": session_purchases,
                "disposable_purchase_intents": disposable,
                "purchase_intent_disposal_blockers": intent_blockers}

    def _intent_evidence(
        self, cursor, intent, user_id, chat_id, *, controlled_account_scope, lock,
    ):
        intent_id = intent["purchase_intent_id"]
        suffix = " FOR UPDATE" if lock else ""
        evidence = {}

        cursor.execute("""SELECT offering.creator_profile_id,publication.publication_metadata
            FROM commercial_offerings offering
            JOIN commercial_publications publication
              ON publication.publication_id=%s
             AND publication.commercial_offering_id=offering.offering_id
            WHERE offering.offering_id=%s""" + suffix,
            (intent["commercial_publication_id"], intent["commercial_offering_id"]))
        scope = cursor.fetchone()
        metadata = dict(scope["publication_metadata"] or {}) if scope else {}
        evidence["controlled_scope"] = bool(
            scope
            and int(scope["creator_profile_id"]) == int(intent["creator_profile_id"])
            and metadata.get("test_specific") is True
            and str(metadata.get("purpose") or "").startswith("controlled_smoke_test")
            and int(metadata.get("fanvue_account_id") or 0) == int(intent["fanvue_account_id"])
            and controlled_account_scope == (
                int(intent["creator_profile_id"]), int(intent["fanvue_account_id"])
            )
            and int(intent.get("telegram_user_id") or 0) == int(user_id)
            and int(intent.get("telegram_chat_id") or 0) == int(chat_id)
        )

        cursor.execute("SELECT * FROM telegram_sales_delivery_operations WHERE purchase_intent_id=%s" + suffix,
                       (intent_id,))
        deliveries = [dict(row) for row in cursor.fetchall()]
        evidence["delivery_count"] = len(deliveries)
        evidence["successful_delivery"] = any(
            row.get("state") in self.BLOCKING_DELIVERY_STATES
            or row.get("outbound_telegram_message_id") is not None
            or row.get("telegram_accepted_at") is not None
            or row.get("confirmed_at") is not None
            for row in deliveries
        )

        cursor.execute("SELECT * FROM telegram_unlock_grants WHERE purchase_intent_id=%s" + suffix,
                       (intent_id,))
        grants = [dict(row) for row in cursor.fetchall()]
        evidence["unlock_count"] = len(grants)
        evidence["consumed_unlock"] = any(
            int(row.get("use_count") or 0) > 0 or row.get("last_used_at") is not None
            for row in grants
        )

        cursor.execute("SELECT * FROM fanvue_fingerprint_reservations WHERE purchase_intent_id=%s" + suffix,
                       (intent_id,))
        fingerprints = [dict(row) for row in cursor.fetchall()]
        evidence["fingerprint_count"] = len(fingerprints)
        evidence["purchased_fingerprint"] = any(
            row.get("state") in {"PURCHASED", "UNCERTAIN"}
            or row.get("purchased_at") is not None
            or bool(row.get("provider_transaction_reference"))
            for row in fingerprints
        )

        cursor.execute("SELECT * FROM fanvue_runtime_media_links WHERE purchase_intent_id=%s" + suffix,
                       (intent_id,))
        runtime_links = [dict(row) for row in cursor.fetchall()]
        evidence["runtime_link_count"] = len(runtime_links)
        evidence["provider_runtime_evidence"] = any(
            row.get("state") in self.BLOCKING_RUNTIME_STATES
            or bool(row.get("provider_media_link_uuid"))
            or bool(row.get("provider_url"))
            for row in runtime_links
        )
        cursor.execute("""SELECT operation.* FROM fanvue_runtime_media_link_operations operation
            JOIN fanvue_runtime_media_links runtime
              ON runtime.runtime_media_link_id=operation.runtime_media_link_id
            WHERE runtime.purchase_intent_id=%s""" + suffix, (intent_id,))
        runtime_operations = [dict(row) for row in cursor.fetchall()]
        evidence["provider_runtime_operation_evidence"] = any(
            row.get("state") in {"CLAIMED", "SUCCEEDED", "UNCERTAIN"}
            or bool(row.get("provider_response"))
            for row in runtime_operations
        )

        scalar_queries = {
            "attribution_audit_count": "SELECT count(*) n FROM purchase_attribution_resolution_audit WHERE purchase_intent_id=%s",
            "attributed_reconciliation_count": "SELECT count(*) n FROM commerce_signal_reconciliations WHERE attributed_purchase_intent_id=%s",
            "session_association_count": "SELECT count(*) n FROM sales_session_purchase_intents WHERE purchase_intent_id=%s",
            "session_history_count": "SELECT count(*) n FROM sales_session_history WHERE purchase_intent_id=%s",
            "photoshoot_lifecycle_count": "SELECT count(*) n FROM customer_photoshoot_lifecycles WHERE last_purchase_intent_id=%s",
            "photoshoot_lifecycle_event_count": "SELECT count(*) n FROM customer_photoshoot_lifecycle_events WHERE purchase_intent_id=%s",
        }
        for name, sql in scalar_queries.items():
            cursor.execute(sql, (intent_id,))
            evidence[name] = int(cursor.fetchone()["n"])

        cursor.execute("""SELECT count(*) n FROM telegram_provisional_sales_sessions
            WHERE first_purchase_intent_id=%s AND telegram_user_id=%s AND telegram_chat_id=%s
              AND first_purchase_recorded_at IS NULL
              AND mapped_sales_session_id IS NULL
              AND state NOT IN ('PURCHASED','COMPLETED','GRADUATED')""",
            (intent_id, user_id, chat_id))
        evidence["disposable_provisional_session_count"] = int(cursor.fetchone()["n"])
        cursor.execute("SELECT count(*) n FROM telegram_provisional_sales_sessions WHERE first_purchase_intent_id=%s",
                       (intent_id,))
        evidence["provisional_session_count"] = int(cursor.fetchone()["n"])

        transaction_ids = tuple(filter(None, (
            intent.get("provider_transaction_order_id"), intent.get("provider_payment_id"),
        )))
        evidence["provider_ownership_count"] = 0
        evidence["entitlement_count"] = 0
        if transaction_ids:
            cursor.execute("SELECT count(*) n FROM provider_purchase_asset_ownership WHERE provider_transaction_id=ANY(%s)",
                           (list(transaction_ids),))
            evidence["provider_ownership_count"] = int(cursor.fetchone()["n"])
            cursor.execute("SELECT count(*) n FROM customer_entitlements WHERE provider_transaction_id=ANY(%s)",
                           (list(transaction_ids),))
            evidence["entitlement_count"] = int(cursor.fetchone()["n"])
        return evidence

    @classmethod
    def _disposal_eligibility(cls, intent, evidence, user_id, chat_id):
        reasons = []
        if not evidence.get("controlled_scope"):
            reasons.append("PurchaseIntent is outside the test-specific controlled account scope")
        if str(intent.get("status") or "") not in cls.DISPOSABLE_INTENT_STATES:
            reasons.append("PurchaseIntent lifecycle is not explicitly disposable")
        settlement_fields = (
            "purchased_at", "purchase_acknowledged_at", "provider_transaction_order_id",
            "provider_payment_id", "provider_event_id", "actual_charged_price_minor",
        )
        if any(intent.get(field) is not None for field in settlement_fields):
            reasons.append("PurchaseIntent contains settlement or acknowledgement evidence")
        if intent.get("presented_at") is not None or intent.get("clicked_at") is not None:
            reasons.append("PurchaseIntent contains customer-facing presentation/click evidence")
        if str(intent.get("attribution_result") or "") in {"ATTRIBUTED", "UNKNOWN"}:
            reasons.append("PurchaseIntent contains attributed or ambiguous purchase evidence")
        blockers = {
            "successful_delivery": "paid delivery may have reached Telegram",
            "consumed_unlock": "Unlock grant was consumed",
            "purchased_fingerprint": "fingerprint contains purchase/uncertain evidence",
            "provider_runtime_evidence": "runtime Media Link contains provider/active evidence",
            "provider_runtime_operation_evidence": "runtime Media Link operation contains provider/in-flight evidence",
            "attribution_audit_count": "manual attribution audit exists",
            "attributed_reconciliation_count": "commerce reconciliation attribution exists",
            "session_association_count": "mapped Sales Session association exists",
            "session_history_count": "Sales Session history references PurchaseIntent",
            "photoshoot_lifecycle_count": "customer photoshoot lifecycle references PurchaseIntent",
            "photoshoot_lifecycle_event_count": "customer photoshoot lifecycle history references PurchaseIntent",
            "provider_ownership_count": "provider ownership evidence exists",
            "entitlement_count": "customer entitlement evidence exists",
        }
        reasons.extend(label for key, label in blockers.items() if evidence.get(key))
        if evidence.get("provisional_session_count", 0) != evidence.get(
            "disposable_provisional_session_count", 0
        ):
            reasons.append("non-disposable provisional Session references PurchaseIntent")
        return {
            "eligible": not reasons,
            "reasons": reasons,
            "reason": (
                "CREATED controlled-test PurchaseIntent has no delivery, settlement, "
                "ownership, mapping, acknowledgement, or provider-runtime evidence"
            ) if not reasons else None,
        }

    @staticmethod
    def _delete_disposable_intents(cursor, disposable):
        ids = [item["purchase_intent_id"] for item in disposable]
        removed = {
            "disposablePurchaseIntents": 0,
            "disposablePurchaseIntentIds": ids,
            "disposablePurchaseIntentStates": {
                item["purchase_intent_id"]: item["state"] for item in disposable
            },
            "disposablePurchaseIntentReasons": {
                item["purchase_intent_id"]: item["reason"] for item in disposable
            },
            "dependentUnlockGrants": 0,
            "dependentFingerprintReservations": 0,
            "dependentRuntimeMediaLinks": 0,
            "dependentRuntimeMediaLinkOperations": 0,
            "dependentPaidDeliveryOperations": 0,
            "dependentRecommendationOutcomes": 0,
            "dependentProvisionalSessions": 0,
        }
        if not ids:
            return removed
        cursor.execute("""DELETE FROM fanvue_runtime_media_link_operations
            WHERE runtime_media_link_id IN (
              SELECT runtime_media_link_id FROM fanvue_runtime_media_links
              WHERE purchase_intent_id=ANY(%s::uuid[]))""", (ids,))
        removed["dependentRuntimeMediaLinkOperations"] = cursor.rowcount
        tables = (
            ("fanvue_runtime_media_links", "dependentRuntimeMediaLinks"),
            ("telegram_unlock_grants", "dependentUnlockGrants"),
            ("fanvue_fingerprint_reservations", "dependentFingerprintReservations"),
            ("telegram_sales_delivery_operations", "dependentPaidDeliveryOperations"),
            ("commerce_recommendation_outcomes", "dependentRecommendationOutcomes"),
        )
        for table, key in tables:
            cursor.execute(f"DELETE FROM {table} WHERE purchase_intent_id=ANY(%s::uuid[])", (ids,))
            removed[key] = cursor.rowcount
        cursor.execute("DELETE FROM telegram_provisional_sales_sessions WHERE first_purchase_intent_id=ANY(%s::uuid[])",
                       (ids,))
        removed["dependentProvisionalSessions"] = cursor.rowcount
        cursor.execute("DELETE FROM purchase_intents WHERE purchase_intent_id=ANY(%s::uuid[])", (ids,))
        removed["disposablePurchaseIntents"] = cursor.rowcount
        return removed

    @staticmethod
    def _counts(cursor, user_id, chat_id, creator_profile_id=None, fanvue_account_id=None):
        result = {}
        queries = {
            "ordinaryReplyOperations": ("SELECT count(*) n FROM ordinary_chat_reply_operations WHERE telegram_account_scope='AVA_TELETHON_PRIVATE' AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s", (chat_id,user_id)),
            "decisionSnapshots": ("SELECT count(*) n FROM ordinary_chat_reply_operations WHERE telegram_account_scope='AVA_TELETHON_PRIVATE' AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s AND response_payload IS NOT NULL", (chat_id,user_id)),
            "controlledProspectRows": ("SELECT count(*) n FROM telegram_sales_prospects WHERE telegram_user_id=%s AND telegram_chat_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s", (user_id,chat_id,creator_profile_id,fanvue_account_id)),
            "identityObservations": ("SELECT count(*) n FROM telegram_identity_observations WHERE telegram_user_id=%s", (user_id,)),
            "controlledConversationMessages": ("SELECT count(*) n FROM chat_messages WHERE raw_payload->>'provider'='TELEGRAM' AND raw_payload->>'telegram_chat_id'=%s", (str(chat_id),)),
        }
        for name,(sql,params) in queries.items(): cursor.execute(sql,params); result[name]=int(cursor.fetchone()["n"])
        return result

    def _preview(self, user_id, checks, counts):
        blockers=[]
        if not checks.get("configured_identity_match", False): blockers.append("configured controlled identity changed")
        if checks.get("controlled_account_scope_ambiguous"):
            blockers.append("controlled Telegram identity spans multiple commerce account scopes")
        labels = (("mapping_count","controlled customer is mapped"),
                  ("settled_purchase_intent_count","a settled PurchaseIntent exists"),
                  ("customer_transaction_count","a customer transaction exists"),
                  ("purchased_fingerprint_count","a purchased fingerprint exists"),
                  ("active_runtime_media_link_count","an active/purchased runtime Media Link exists"),
                  ("session_purchase_count","a Session purchase exists"))
        blockers.extend(label for key,label in labels if checks.get(key,0))
        if checks.get("purchase_intent_disposal_blockers"):
            blockers.append("a non-disposable controlled PurchaseIntent exists")
        if checks.get("purchase_intent_count", 0) != len(
            checks.get("disposable_purchase_intents", ())
        ):
            blockers.append("not every controlled PurchaseIntent is proven disposable")
        would_clear = dict(counts)
        disposable = checks.get("disposable_purchase_intents", ())
        would_clear["disposablePurchaseIntents"] = len(disposable)
        would_clear["disposablePurchaseIntentIds"] = [
            item["purchase_intent_id"] for item in disposable
        ]
        return {"allowed":not blockers,"executed":False,"blockers":blockers,
                "preconditions":checks,"wouldClear":would_clear,"identity":self._masked(user_id),
                "wouldPreserve":["controlled-autonomy configuration","controlled Telegram allowlist",
                    "Fanvue controlled buyer evidence","worker and supervisor state",
                    "controlled offering, publication, provider resource and base price",
                    "unrelated commerce records",
                    "Content Vault","CONTROLLED SMOKE TEST — $3 SINGLE and canonical publication",
                    "historical webhook recovery batch","unrelated customers"]}

    def _audit(self, cursor, reset_id, user_id, checks, removed, preserved, result, reason):
        cursor.execute("""INSERT INTO controlled_test_reset_audit(
            reset_id,scope,identity_fingerprint,categories,removed_counts,
            safety_preconditions,commerce_preserved,result,failure_reason)
            VALUES(%s,'CONTROLLED_TELEGRAM_TEST',%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s)""",
            (reset_id,self._fingerprint(user_id),json.dumps(self.CATEGORIES),json.dumps(removed),
             json.dumps(checks),preserved,result,reason))

    @staticmethod
    def _fingerprint(user_id): return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]
    @staticmethod
    def _masked(user_id):
        text=str(user_id); return text[:2]+"*"*max(4,len(text)-4)+text[-2:]

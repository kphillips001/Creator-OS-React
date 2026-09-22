"""Bounded reconciliation for orphaned ordinary-chat burst survivors."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.database import get_db_connection


class HistoricalSurvivorReconciliationService:
    ELIGIBLE_ERRORS = frozenset({
        "SUPERSEDED_PENDING_GENERATION",
        "stale_response_suppressed_before_send",
    })

    def __init__(self, *, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def inspect(self, operation_id) -> dict:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s", (operation_id,))
            row = cursor.fetchone()
            if not row:
                return {"disposition": "AMBIGUOUS_OPERATOR_REVIEW", "reason": "OPERATION_NOT_FOUND"}
            operation = dict(row)
            error = str(operation.get("last_error") or "")
            if error not in self.ELIGIBLE_ERRORS or operation.get("state") != "SUPPRESSED":
                return {"disposition": "AMBIGUOUS_OPERATOR_REVIEW", "reason": "SOURCE_NOT_ELIGIBLE"}
            if (operation.get("outbound_telegram_message_id") is not None
                    or int(operation.get("send_attempt_count") or 0) != 0
                    or operation.get("claim_owner") or operation.get("lease_expires_at")):
                return {"disposition": "AMBIGUOUS_OPERATOR_REVIEW", "reason": "SOURCE_NOT_DEFINITIVELY_UNSENT"}
            cursor.execute("""SELECT telegram_message_id,customer_text,received_at
                FROM telegram_private_inbound_messages WHERE telegram_account_scope=%s
                  AND telegram_chat_id=%s AND telegram_message_id>=%s
                  AND (BTRIM(COALESCE(customer_text,''))<>'' OR has_media=TRUE)
                ORDER BY telegram_message_id""", (
                operation["telegram_account_scope"], operation["telegram_chat_id"],
                operation["inbound_telegram_message_id"],
            ))
            inbounds = [dict(item) for item in cursor.fetchall()]
            cursor.execute("""SELECT 1 FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND state='SENT_CONFIRMED' AND sent_confirmed_at>%s LIMIT 1""", (
                operation["telegram_account_scope"], operation["telegram_chat_id"],
                operation["inbound_received_at"],
            ))
            later_answer = cursor.fetchone() is not None
            cursor.execute("""SELECT 1 FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND operation_id<>%s AND inbound_telegram_message_id>=%s
                  AND state IN ('PENDING_GENERATION','GENERATING','GENERATED','RETRYABLE','SENDING') LIMIT 1""", (
                operation["telegram_account_scope"], operation["telegram_chat_id"],
                operation["operation_id"], operation["inbound_telegram_message_id"],
            ))
            replacement = cursor.fetchone() is not None
        payload = dict(operation.get("delivery_payload") or {})
        obligations = list(operation.get("burst_obligations") or
                           dict(payload.get("conversationBurst") or {}).get("obligations") or ())
        meaningful = bool(obligations) or dict(payload.get("attentionInvestment") or {}).get(
            "meaningfulObligation") is True
        if later_answer:
            return {"disposition": "OBLIGATION_OBSOLETE", "reason": "LATER_CONFIRMED_RESPONSE"}
        if replacement:
            return {"disposition": "OBLIGATION_OBSOLETE", "reason": "ACTIONABLE_REPLACEMENT_EXISTS"}
        if not meaningful:
            return {"disposition": "OBLIGATION_OBSOLETE", "reason": "NO_MEANINGFUL_OBLIGATION"}
        if not inbounds:
            return {"disposition": "AMBIGUOUS_OPERATOR_REVIEW", "reason": "ARCHIVE_EVIDENCE_MISSING"}
        newest = inbounds[-1]
        return {
            "disposition": "CURRENT_OBLIGATION_SURVIVES",
            "reason": "CURRENT_ARCHIVED_TURN_RETAINS_MEANINGFUL_OBLIGATION",
            "operationId": str(operation["operation_id"]),
            "freshnessMessageId": int(newest["telegram_message_id"]),
            "obligations": obligations,
            "sourceError": error,
        }

    def reconcile(self, operation_id) -> dict:
        decision = self.inspect(operation_id)
        if decision["disposition"] != "CURRENT_OBLIGATION_SURVIVES":
            return {**decision, "mutated": False}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT response_text FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE", (operation_id,))
            source = cursor.fetchone()
            rejected = str((source or {}).get("response_text") or "").strip()
            evidence = {
                **decision,
                "authority": "HistoricalSurvivorReconciliationService",
                "reconciledAt": datetime.now(timezone.utc).isoformat(),
                "staleGeneratedTextDiscarded": bool(rejected),
                "rejectedCandidateSha256": hashlib.sha256(rejected.encode()).hexdigest() if rejected else None,
                "excludedExactResponses": [rejected] if rejected else [],
            }
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='RETRYABLE',response_payload=NULL,response_text=NULL,
                response_content_sha256=NULL,generated_at=NULL,failed_at=NULL,
                generation_attempt_count=0,next_retry_at=NOW(),
                last_error='historical_survivor_reconciliation_scheduled',
                burst_freshness_telegram_message_id=GREATEST(
                  COALESCE(burst_freshness_telegram_message_id,%s),%s),
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||
                  jsonb_build_object('historicalSurvivorReconciliation',%s::jsonb),
                updated_at=NOW()
                WHERE operation_id=%s AND state='SUPPRESSED'
                  AND last_error=ANY(%s) AND send_attempt_count=0
                  AND outbound_telegram_message_id IS NULL
                  AND claim_owner IS NULL
                RETURNING operation_id""", (
                decision["freshnessMessageId"], decision["freshnessMessageId"],
                json.dumps(evidence), operation_id,
                list(self.ELIGIBLE_ERRORS),
            ))
            updated = cursor.fetchone()
            connection.commit()
        return {**decision, "mutated": updated is not None,
                "evidence": evidence if updated else None}

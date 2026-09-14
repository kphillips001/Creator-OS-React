"""Server-owned, customer-scoped evidence for Inspect & Resolve."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.relationships_repository import RelationshipsRepository
from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
from app.services.relationships_service import RelationshipsService
from app.services.telegram_worker_readiness_service import TelegramWorkerReadinessService


class ConversationAttentionEvidenceService:
    POLICY_VERSION = "ORDINARY_REPLY_CORRECTIVE_REGENERATION_V1"
    FIXED_FAILURES = frozenset({"REQUIRED_RESPONSE_QUALITY_FAILURE"})

    def __init__(self, *, relationships=None, relationship_repository=None,
                 ordinary_repository=None, permissions=None, readiness=None):
        self.relationships = relationships or RelationshipsService()
        self.relationship_repository = relationship_repository or RelationshipsRepository()
        self.ordinary = ordinary_repository or OrdinaryChatReplyRepository()
        self.permissions = permissions or CustomerEffectivePermissionsService()
        self.readiness = readiness or TelegramWorkerReadinessService()

    def build(self, *, creator_profile_id: int, fanvue_account_id: int,
              telegram_user_id: int, relationship_key: str,
              occurrence_id: str) -> dict[str, Any]:
        expected = f"telegram:{creator_profile_id}:{fanvue_account_id}:{telegram_user_id}"
        if relationship_key != expected:
            raise PermissionError("Relationship scope does not match the requested account.")
        inboxes = self.relationship_repository.inbox_state(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
        inbox = inboxes.get(int(telegram_user_id))
        if not inbox:
            raise LookupError("Relationship not found.")
        projection = self.relationships._operational_projection(inbox)
        if (projection["operationalStatus"] != "NEEDS_ATTENTION"
                or projection["attentionOccurrenceId"] != occurrence_id):
            raise ValueError("Attention occurrence is no longer current.")
        causal = self.ordinary.get(inbox["operation_id"]) if inbox.get("operation_id") else None
        target = self._latest_operation(
            account_scope="AVA_TELETHON_PRIVATE", chat_id=int(inbox["telegram_chat_id"]),
            sender_user_id=int(telegram_user_id))
        messages = self.relationships.messages(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id, limit=12)["items"]
        last_outbound = next((item for item in reversed(messages)
                              if item["direction"] == "AVA"), None)
        history = [item for item in messages if (
            last_outbound is None or item["timestamp"] >= last_outbound["timestamp"]
        )][-12:]
        permissions = self.permissions.read(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id, telegram_chat_id=inbox["telegram_chat_id"])
        failure = self._failure_signature(inbox)
        similar = self._similar_cases(
            inboxes=inboxes, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, current_user_id=telegram_user_id,
            failure_signature=failure)
        runtime = self.readiness.read(creator_profile_id=creator_profile_id)
        opaque_key = "relationship:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
        material = {
            "predicateVersion": self.relationships.OPERATIONAL_PREDICATE_VERSION,
            "relationshipKey": opaque_key,
            "attentionOccurrenceId": occurrence_id,
            "latestInbound": [inbox.get("last_inbound_message_id"), inbox.get("last_customer_inbound_at")],
            "latestConfirmedOutboundAt": inbox.get("last_visible_outbound_at"),
            "causalOperation": self._operation_state(causal),
            "targetOperation": self._operation_state(target),
            "operational": projection,
            "mode": inbox.get("control_mode"),
            "effectivePermissions": permissions["effective"],
            "configuredPermissions": permissions["configured"],
            "acknowledgement": [inbox.get("acknowledged_occurrence_id"),inbox.get("acknowledged_at")],
            "policyVersion": self.POLICY_VERSION,
        }
        fingerprint = self.digest(material)
        evidence = {
            "schemaVersion": "ATTENTION_EVIDENCE_V1",
            "relationshipKey": opaque_key,
            "attentionOccurrenceId": occurrence_id,
            "operationalStatus": projection["operationalStatus"],
            "operationalStatusReason": projection["operationalStatusReason"],
            "predicateVersion": self.relationships.OPERATIONAL_PREDICATE_VERSION,
            "latestTriggeringInbound": self._message(history[-1] if history else None),
            "latestConfirmedOutbound": self._message(last_outbound),
            "causalOperation": self._safe_operation(causal),
            "currentAuthorityOperation": self._safe_operation(target),
            "coalescedAuthority": bool(target and causal and target.operation_id != causal.operation_id),
            "qualityGateReasons": self._quality_reasons(inbox.get("operation_last_error")),
            "acknowledgement": {"acknowledged": bool(inbox.get("acknowledged_at")),
                                "occurrenceMatches": inbox.get("acknowledged_occurrence_id") == occurrence_id},
            "automationMode": inbox.get("control_mode") or "AVA_AUTO",
            "permissions": {"configured": permissions["configured"], "effective": permissions["effective"]},
            "runtimeHealth": {key: runtime.get(key) for key in
                              ("ready","status","reason","code","lifecycleState","authorized","databaseHealthy")},
            "scheduler": {"nextRetryAt": inbox.get("next_retry_at"),
                          "activeClaim": projection["hasActiveClaim"]},
            "deployedLifecyclePolicyVersion": self.POLICY_VERSION,
            "globalRepairAlreadyExists": failure in self.FIXED_FAILURES,
            "failureSignature": failure,
            "similarCurrentCases": similar,
            "boundedConversation": [self._message(item) for item in history],
            "stateFingerprint": fingerprint,
            "targetOperationId": str(target.operation_id) if target else None,
            "causalOperationId": str(causal.operation_id) if causal else None,
            "evidenceReferences": [f"attention:{occurrence_id}"] +
                ([f"operation:{causal.operation_id}"] if causal else []) +
                ([f"operation:{target.operation_id}"] if target else []),
        }
        evidence["evidenceDigest"] = self.digest(evidence)
        return evidence

    def _similar_cases(self, *, inboxes, creator_profile_id, fanvue_account_id,
                       current_user_id, failure_signature):
        if failure_signature == "UNKNOWN":
            return []
        labels = {item["telegramUserId"]: item for item in self.relationships.list(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            limit=100)["items"]}
        result=[]
        for user_id, inbox in inboxes.items():
            projection=self.relationships._operational_projection(inbox)
            if (user_id == current_user_id or projection["operationalStatus"] != "NEEDS_ATTENTION"
                    or self._failure_signature(inbox) != failure_signature):
                continue
            person=labels.get(user_id) or {}
            raw=f"telegram:{creator_profile_id}:{fanvue_account_id}:{user_id}"
            result.append({"relationshipKey":"relationship:"+hashlib.sha256(raw.encode()).hexdigest()[:32],
                           "attentionOccurrenceId":projection["attentionOccurrenceId"],
                           "displayLabel":str(person.get("displayName") or "Telegram customer")})
        return result

    def _latest_operation(self, *, account_scope, chat_id, sender_user_id):
        with self.ordinary.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
              WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                AND inbound_sender_telegram_user_id=%s
              ORDER BY inbound_telegram_message_id DESC LIMIT 1""",
              (account_scope,chat_id,sender_user_id))
            return self.ordinary._item(cursor.fetchone())

    @staticmethod
    def _failure_signature(inbox):
        error=str(inbox.get("operation_last_error") or "")
        if ("CUSTOMER_QUESTION_UNANSWERED" in error
                or "TURN_OBLIGATIONS_UNSATISFIED" in error):
            return "REQUIRED_RESPONSE_QUALITY_FAILURE"
        if inbox.get("operation_state") == "SEND_UNCERTAIN": return "SEND_UNCERTAIN"
        if inbox.get("operation_state") == "TERMINAL_FAILED": return "RETRY_EXHAUSTED"
        if inbox.get("operation_state") == "RETRYABLE" and not inbox.get("next_retry_at"):
            return "UNSCHEDULED_RETRYABLE"
        return "UNKNOWN"

    @staticmethod
    def _quality_reasons(error):
        return [name for name in ("CUSTOMER_QUESTION_UNANSWERED","TURN_OBLIGATIONS_UNSATISFIED")
                if name in str(error or "")]

    @staticmethod
    def _safe_operation(operation):
        if not operation: return None
        return {"operationId":str(operation.operation_id),"inboundMessageId":operation.inbound_telegram_message_id,
                "state":operation.state.value,"generationAttempts":operation.generation_attempt_count,
                "sendAttempts":operation.send_attempt_count,"nextRetryAt":operation.next_retry_at,
                "hasClaim":bool(operation.claim_owner and operation.lease_expires_at),
                "terminalReason":operation.last_error}

    @classmethod
    def _operation_state(cls, operation):
        return cls._safe_operation(operation)

    @staticmethod
    def _message(item):
        if not item: return None
        text=re.sub(r"\s+"," ",str(item.get("content") or "")).strip()[:600]
        return {"direction":item.get("direction"),"messageId":item.get("telegramMessageId"),
                "timestamp":item.get("timestamp"),"text":text,
                "trust":"UNTRUSTED_CUSTOMER_DATA" if item.get("direction")=="CUSTOMER" else "SYSTEM_OUTPUT"}

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),
                                             default=str).encode()).hexdigest()

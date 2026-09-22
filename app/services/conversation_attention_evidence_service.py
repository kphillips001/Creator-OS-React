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
    FIXED_FAILURES = frozenset({
        "REQUIRED_RESPONSE_QUALITY_FAILURE",
        "FINAL_REPETITION_FAILURE",
        "MANUFACTURED_ENGAGEMENT_QUESTION",
        "RETRY_EXHAUSTED",
    })

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
        failure_operation = causal or target
        failure = self._failure_signature(inbox, failure_operation)
        quality_failure_evidence = self._manufactured_engagement_evidence(
            failure_operation
        )
        similar = self._similar_cases(
            inboxes=inboxes, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, current_user_id=telegram_user_id,
            failure_signature=failure)
        runtime = self.readiness.read(creator_profile_id=creator_profile_id)
        from app.services.historical_corrective_eligibility_service import (
            HistoricalCorrectiveEligibilityService,
        )
        recovery_eligibility = HistoricalCorrectiveEligibilityService(
            connection_factory=self.ordinary.connection_factory,
        ).evaluate(
            root=causal, parent=target,
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=int(inbox["telegram_chat_id"]),
            chat_allowed=bool(permissions["effective"].get("chatAllowed")),
        )
        commercial_authority = self._current_commercial_authority(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=int(inbox["telegram_chat_id"]),
        )
        opaque_key = "relationship:" + hashlib.sha256(expected.encode()).hexdigest()[:32]
        material = {
            "predicateVersion": self.relationships.OPERATIONAL_PREDICATE_VERSION,
            "relationshipKey": opaque_key,
            "attentionOccurrenceId": occurrence_id,
            "latestInbound": [inbox.get("last_inbound_message_id"), inbox.get("last_customer_inbound_at")],
            "latestConfirmedOutboundAt": inbox.get("last_visible_outbound_at"),
            "causalOperation": self._operation_state(causal),
            "targetOperation": self._operation_state(target),
            "recoveryEligibility": recovery_eligibility,
            "currentCommercialAuthority": commercial_authority,
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
            "rootCausalOperation": self._safe_operation(causal),
            "latestRecoveryOperation": (
                self._safe_operation(target)
                if target and getattr(target, "operation_kind", "PRIMARY") == "HISTORICAL_CORRECTIVE"
                else None
            ),
            "latestDeliveryOutcome": self._delivery_outcome(target),
            "recoveryEligibility": recovery_eligibility,
            "currentCommercialAuthority": commercial_authority,
            "coalescedAuthority": bool(target and causal and target.operation_id != causal.operation_id),
            "qualityGateReasons": self._quality_reasons(inbox.get("operation_last_error")),
            "qualityFailureEvidence": quality_failure_evidence,
            "acknowledgement": {"acknowledged": bool(inbox.get("acknowledged_at")),
                                "occurrenceMatches": inbox.get("acknowledged_occurrence_id") == occurrence_id},
            "automationMode": inbox.get("control_mode") or "AVA_AUTO",
            "permissions": {"configured": permissions["configured"], "effective": permissions["effective"]},
            "runtimeHealth": {key: runtime.get(key) for key in
                              ("ready","status","reason","code","lifecycleState","authorized","databaseHealthy")},
            "currentGlobalReadiness": {key: runtime.get(key) for key in
                                      ("ready","status","reason","code","lifecycleState","authorized","databaseHealthy")},
            "historicalCausalFailure": self._historical_failure(causal or target),
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
        if failure == "SEND_UNCERTAIN" and causal:
            evidence["commercialDeliveryEvidence"] = self._commercial_delivery_evidence(
                causal, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=int(inbox["telegram_chat_id"]),
            )
        evidence["evidenceDigest"] = self.digest(evidence)
        return evidence

    def _current_commercial_authority(self, *, creator_profile_id,
                                      fanvue_account_id, telegram_user_id,
                                      telegram_chat_id):
        """Describe current authority; historical PurchaseIntent rows confer none."""
        with self.ordinary.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT purchase_intent_id,status,expires_at,purchased_at,
                                      presented_at,clicked_at
                FROM public.purchase_intents
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                ORDER BY created_at DESC LIMIT 1""", (
                creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id,
            ))
            row = cursor.fetchone()
        intent = dict(row) if row else None
        now = datetime.now(timezone.utc)
        expires_at = intent.get("expires_at") if intent else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        active = bool(
            intent
            and intent.get("status") in {"PRESENTED", "CLICKED"}
            and intent.get("purchased_at") is None
            and (expires_at is None or expires_at > now)
        )
        return {
            "active": active,
            "authority": "CURRENT_ACTIVE_PURCHASE_INTENT" if active else "NONE",
            "purchaseIntentId": str(intent["purchase_intent_id"]) if intent else None,
            "status": intent.get("status") if intent else None,
            "terminalHistoricalRowOnly": bool(intent and not active),
            "rule": "ROW_EXISTENCE_DOES_NOT_CONFER_CURRENT_AUTHORITY",
        }

    @classmethod
    def _recovery_eligibility(cls, root, parent):
        root_id = str(root.operation_id) if root else None
        parent_id = str(parent.operation_id) if parent else None
        base = {
            "eligible": False, "mode": None, "reason": "MISSING_LINEAGE",
            "rootOperationId": root_id, "parentOperationId": parent_id,
        }
        if not root or not parent:
            return base
        root_kind = getattr(root, "operation_kind", "PRIMARY")
        root_state = getattr(root.state, "value", root.state)
        root_error = str(getattr(root, "last_error", "") or "")
        if not (
            root_kind == "PRIMARY" and root_state == "SUPPRESSED"
            and getattr(root, "outbound_telegram_message_id", None) is None
            and getattr(root, "send_attempt_count", 0) == 0
            and (root_error.startswith("quality_blocked_before_delivery:")
                 or root_error.startswith("quality_corrective_retry_exhausted:"))
        ):
            base["reason"] = "ROOT_NOT_QUALIFYING_QUALITY_FAILURE"
            return base
        if parent.operation_id == root.operation_id:
            return {**base, "eligible": True, "mode": "FIRST_CORRECTIVE",
                    "reason": "ROOT_QUALITY_FAILURE_DEFINITIVELY_UNSENT"}
        if (getattr(parent, "operation_kind", None) != "HISTORICAL_CORRECTIVE"
                or str(getattr(parent, "causal_operation_id", "")) != root_id):
            base["reason"] = "PARENT_NOT_IN_ROOT_LINEAGE"
            return base
        outcome = cls._delivery_outcome(parent)
        if outcome["classification"] != "DEFINITIVE_NOT_DELIVERED":
            base["reason"] = outcome["reason"]
            return base
        return {**base, "eligible": True,
                "mode": "FOLLOW_UP_AFTER_DEFINITIVE_NON_DELIVERY",
                "reason": outcome["reason"]}

    @staticmethod
    def _delivery_outcome(operation):
        if not operation:
            return {"classification": "UNKNOWN", "reason": "MISSING_OPERATION"}
        state = getattr(operation.state, "value", operation.state)
        if state == "SENT_CONFIRMED" or getattr(operation, "outbound_telegram_message_id", None):
            return {"classification": "CUSTOMER_VISIBLE", "reason": "DELIVERY_CONFIRMED"}
        if state == "SEND_UNCERTAIN":
            return {"classification": "AMBIGUOUS", "reason": "SEND_UNCERTAIN_PROHIBITED"}
        payload = dict(getattr(operation, "delivery_payload", None) or {})
        rejection = dict(payload.get("telegramDefinitiveRejection") or {})
        explicit_peer_failure = (
            getattr(operation, "last_error", None)
            == "RECOVERY_ABORTED_TELEGRAM_PEER_ID_INVALID"
        )
        durable_rejection = (
            rejection.get("classification") == "DEFINITIVE_NOT_DELIVERED"
            and rejection.get("automaticRetryAllowed") is False
        )
        if (state in {"SUPPRESSED", "TERMINAL_FAILED"}
                and (explicit_peer_failure or durable_rejection)):
            return {"classification": "DEFINITIVE_NOT_DELIVERED",
                    "reason": ("TELEGRAM_PEER_ID_INVALID"
                               if explicit_peer_failure else "DURABLE_PROVIDER_REJECTION")}
        return {"classification": "NOT_ELIGIBLE",
                "reason": "NO_DEFINITIVE_NON_DELIVERY_EVIDENCE"}

    def _commercial_delivery_evidence(self, operation, *, creator_profile_id,
                                      fanvue_account_id, telegram_user_id,
                                      telegram_chat_id):
        response = dict(operation.response_payload or {})
        delivery = dict(response.get("delivery_payload") or operation.delivery_payload or {})
        url = str(delivery.get("delivery_url") or delivery.get("media_link") or "")
        diagnostics = dict(response.get("diagnostic_metadata") or {})
        legacy_verified = bool(
            operation.state.value == "SEND_UNCERTAIN"
            and operation.last_error ==
                "ConnectionError: Commercial presentation was not verified complete provider-side"
            and url
            and diagnostics.get("structured_paid_presentation") is True
            and diagnostics.get("telegram_delivery_payload_ready") is True
        )
        intent = None
        if url:
            with self.ordinary.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute("""SELECT purchase_intent_id,status,presented_at,clicked_at
                    FROM public.purchase_intents
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s AND telegram_chat_id=%s
                      AND delivery_url=%s
                    ORDER BY created_at DESC LIMIT 1""", (
                    creator_profile_id, fanvue_account_id, telegram_user_id,
                    telegram_chat_id, url,
                ))
                row = cursor.fetchone()
                intent = dict(row) if row else None
                if intent is None and operation.generated_at and operation.uncertain_at:
                    cursor.execute("""SELECT purchase_intent_id,status,presented_at,clicked_at
                        FROM public.purchase_intents
                        WHERE creator_profile_id=%s AND fanvue_account_id=%s
                          AND telegram_user_id=%s AND telegram_chat_id=%s
                          AND created_at BETWEEN %s-INTERVAL '1 second'
                                             AND %s+INTERVAL '1 second'
                        ORDER BY created_at""", (
                        creator_profile_id, fanvue_account_id, telegram_user_id,
                        telegram_chat_id, operation.generated_at, operation.uncertain_at,
                    ))
                    candidates=cursor.fetchall()
                    intent=dict(candidates[0]) if len(candidates)==1 else None
        with self.ordinary.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT outcome,provider_acceptance_evidence,
                    provider_readback_evidence,evidence,resolution_id
                FROM public.operator_delivery_resolutions
                WHERE ordinary_operation_id=%s""", (operation.operation_id,))
            resolved = cursor.fetchone()
        resolution = dict(resolved) if resolved else {}
        negative_history = bool(
            resolution.get("outcome") == "NOT_DELIVERED"
            and resolution.get("provider_readback_evidence") is True
            and dict(resolution.get("evidence") or {}).get("attestationMethod")
                == "AUTHENTICATED_TELEGRAM_HISTORY_NEGATIVE_ATTESTATION"
        )
        return {
            "qualifyingCommercialPresentation": bool(intent and (legacy_verified or negative_history)),
            "purchaseIntentId": str(intent["purchase_intent_id"]) if intent else None,
            "purchaseIntentState": intent.get("status") if intent else None,
            "providerAcceptanceEvidence": legacy_verified,
            "providerReadbackEvidence": bool(legacy_verified or negative_history),
            "destinationVerified": bool(url),
            "telegramMessageIdAvailable": bool(operation.outbound_telegram_message_id),
            "presentationMode": "VISIBLE_URL" if url else "UNKNOWN",
            "historicalTimestamp": operation.uncertain_at,
            "legacyEvidenceClass": (
                "TELETHON_VISIBLE_URL_READBACK_VERIFICATION_DEFECT"
                if legacy_verified else None
            ),
            "negativeHistoryAttestation": ({
                "resolutionId": str(resolution["resolution_id"]),
                "method": dict(resolution.get("evidence") or {}).get("attestationMethod"),
                "version": dict(resolution.get("evidence") or {}).get("attestationVersion"),
            } if negative_history else None),
        }

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
              ORDER BY inbound_telegram_message_id DESC,
                CASE WHEN state IN ('PENDING_GENERATION','GENERATING','GENERATED',
                     'RETRYABLE','SENDING') THEN 0
                     WHEN state='SENT_CONFIRMED' THEN 1 ELSE 2 END,
                created_at DESC LIMIT 1""",
              (account_scope,chat_id,sender_user_id))
            return self.ordinary._item(cursor.fetchone())

    @staticmethod
    def _failure_signature(inbox, operation=None):
        error=str(inbox.get("operation_last_error") or "")
        if "FINAL_REPETITION_FAILURE" in error:
            return "FINAL_REPETITION_FAILURE"
        if ("MANUFACTURED_ENGAGEMENT_QUESTION" in error
                and ConversationAttentionEvidenceService
                    ._manufactured_engagement_evidence(operation)[
                        "classificationSupported"
                    ]):
            return "MANUFACTURED_ENGAGEMENT_QUESTION"
        if ("CUSTOMER_QUESTION_UNANSWERED" in error
                or "TURN_OBLIGATIONS_UNSATISFIED" in error):
            return "REQUIRED_RESPONSE_QUALITY_FAILURE"
        if inbox.get("operation_state") == "SEND_UNCERTAIN": return "SEND_UNCERTAIN"
        if inbox.get("operation_state") == "TERMINAL_FAILED": return "RETRY_EXHAUSTED"
        if inbox.get("operation_state") == "RETRYABLE" and not inbox.get("next_retry_at"):
            return "UNSCHEDULED_RETRYABLE"
        return "UNKNOWN"

    @staticmethod
    def _manufactured_engagement_evidence(operation):
        """Require durable quality diagnostics; the terminal string is not authority."""
        if operation is None:
            return {
                "classificationSupported": False,
                "recoverySupported": False,
                "reason": "MISSING_OPERATION_EVIDENCE",
            }

        def value(name, default=None):
            if isinstance(operation, dict):
                return operation.get(name, default)
            return getattr(operation, name, default)

        response_payload = dict(value("response_payload") or {})
        diagnostics = dict(response_payload.get("diagnostic_metadata") or {})
        style = dict(diagnostics.get("conversationStyle") or {})
        quality_gate = dict(diagnostics.get("delivery_quality_gate") or {})
        blocking = set(quality_gate.get("blockingReasons") or ())
        quality_reasons = set(diagnostics.get("conversationQualityReasons") or ())
        terminal_reason = str(value("last_error") or "")
        candidate = str(
            response_payload.get("response_text")
            or value("response_text")
            or ""
        ).strip()
        classification_supported = bool(
            terminal_reason
                == "quality_blocked_before_delivery:MANUFACTURED_ENGAGEMENT_QUESTION"
            and quality_gate.get("disposition") == "BLOCKED_BEFORE_DELIVERY"
            and "MANUFACTURED_ENGAGEMENT_QUESTION" in blocking
            and "MANUFACTURED_ENGAGEMENT_QUESTION" in quality_reasons
            and style.get("manufacturedQuestionRisk") is True
            and style.get("questionAsked") is True
            and style.get("questionReason") == "MANUFACTURED_ENGAGEMENT"
            and style.get("questionValue") in {"LOW", "MEDIUM", "HIGH"}
            and int(value("generation_attempt_count") or 0) >= 1
            and candidate
        )
        obligation_evidence = (
            ConversationAttentionEvidenceService
            ._historical_obligation_evidence(
                inbound_text=value("inbound_message_text"), style=style,
            )
        )
        return {
            "classificationSupported": classification_supported,
            "recoverySupported": bool(
                classification_supported and obligation_evidence["supported"]
            ),
            "reason": (
                "AUTHORITATIVE_MANUFACTURED_ENGAGEMENT_EVIDENCE"
                if classification_supported and obligation_evidence["supported"]
                else obligation_evidence["reason"]
                if classification_supported
                else "AUTHORITATIVE_QUALITY_DIAGNOSTICS_REQUIRED"
            ),
            "blockingReason": (
                "MANUFACTURED_ENGAGEMENT_QUESTION"
                if "MANUFACTURED_ENGAGEMENT_QUESTION" in blocking else None
            ),
            "questionReason": style.get("questionReason"),
            "questionValue": style.get("questionValue"),
            "customerQuestionSemanticSlot": style.get(
                "customerQuestionSemanticSlot"
            ),
            "turnObligations": list(style.get("turnObligations") or ()),
            "obligationEvidence": obligation_evidence,
            "candidatePreserved": bool(candidate),
        }
    @staticmethod
    def _historical_obligation_evidence(*, inbound_text, style):
        """Prove the obligation from its persisted current-turn semantics."""
        inbound_present = bool(str(inbound_text or "").strip())
        obligations = tuple(dict.fromkeys(
            str(item) for item in style.get("turnObligations") or ()
            if str(item).strip()
        ))
        base = {
            "supported": False,
            "obligations": list(obligations),
            "authority": None,
            "reason": "CURRENT_TURN_OBLIGATION_EVIDENCE_REQUIRED",
        }
        if not inbound_present or not obligations:
            return base
        if set(obligations).intersection({
            "ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION",
        }):
            supported = bool(
                style.get("customerAskedQuestion") is True
                and style.get("semanticQuestionDetected") is True
                and str(style.get("customerQuestionSemanticSlot") or "").strip()
            )
            return {
                **base, "supported": supported,
                "authority": "PERSISTED_CURRENT_TURN_QUESTION_SEMANTICS",
                "reason": (
                    "AUTHORITATIVE_CURRENT_TURN_QUESTION_EVIDENCE"
                    if supported else "CURRENT_TURN_QUESTION_EVIDENCE_REQUIRED"
                ),
            }
        if "RESPOND_TO_GREETING" in obligations:
            supported = style.get("semanticGreetingDetected") is True
            return {
                **base, "supported": supported,
                "authority": "PERSISTED_SEMANTIC_GREETING_DETECTION",
                "reason": (
                    "AUTHORITATIVE_CURRENT_TURN_GREETING_EVIDENCE"
                    if supported else "CURRENT_TURN_GREETING_EVIDENCE_REQUIRED"
                ),
            }
        if "ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in obligations:
            supported = bool(
                style.get("customerSelfDisclosureDetected") is True
                and str(style.get("customerSelfDisclosureSignificance") or "")
                    not in {"", "NONE", "LOW"}
            )
            return {
                **base, "supported": supported,
                "authority": "PERSISTED_CUSTOMER_SELF_DISCLOSURE_SEMANTICS",
                "reason": (
                    "AUTHORITATIVE_VOLUNTEERED_DETAIL_EVIDENCE"
                    if supported else "CURRENT_TURN_VOLUNTEERED_DETAIL_EVIDENCE_REQUIRED"
                ),
            }
        if "HONOR_COMMERCIAL_REQUEST" in obligations:
            supported = bool(
                style.get("commercialDiscoveryAuthorized") is True
                or str(style.get("customerQuestionDomain") or "") == "COMMERCIAL"
            )
            return {
                **base, "supported": supported,
                "authority": "PERSISTED_CURRENT_TURN_COMMERCIAL_SEMANTICS",
                "reason": (
                    "AUTHORITATIVE_CURRENT_TURN_COMMERCIAL_EVIDENCE"
                    if supported else "CURRENT_TURN_COMMERCIAL_EVIDENCE_REQUIRED"
                ),
            }
        return base

    @staticmethod
    def _quality_reasons(error):
        return [name for name in ("CUSTOMER_QUESTION_UNANSWERED","TURN_OBLIGATIONS_UNSATISFIED",
                                  "FINAL_REPETITION_FAILURE")
                if name in str(error or "")]

    @staticmethod
    def _safe_operation(operation):
        if not operation: return None
        payload = dict(getattr(operation, "delivery_payload", None) or {})
        deterministic = dict(payload.get("deterministicDeliveryBlock") or {})
        recovery = dict(payload.get("operatorAuthorizedDeliveryRecovery") or {})
        return {"operationId":str(operation.operation_id),"inboundMessageId":operation.inbound_telegram_message_id,
                "operationKind":getattr(operation,"operation_kind","PRIMARY"),
                "causalOperationId":str(operation.causal_operation_id) if getattr(operation,"causal_operation_id",None) else None,
                "recoveryParentOperationId":str(operation.recovery_parent_operation_id) if getattr(operation,"recovery_parent_operation_id",None) else None,
                "inboundText":str(getattr(operation,"inbound_message_text","") or "")[:600],
                "state":operation.state.value,"generationAttempts":operation.generation_attempt_count,
                "maxGenerationAttempts":operation.max_generation_attempts,
                "sendAttempts":operation.send_attempt_count,"maxSendAttempts":operation.max_send_attempts,
                "nextRetryAt":operation.next_retry_at,
                "hasClaim":bool(operation.claim_owner and operation.lease_expires_at),
                "terminalReason":operation.last_error,
                "generatedPayloadExists":operation.response_payload is not None,
                "generatedAt":operation.generated_at,"sendingAt":operation.sending_at,
                "failedAt":operation.failed_at,"sentConfirmedAt":operation.sent_confirmed_at,
                "outboundTelegramMessageId":operation.outbound_telegram_message_id,
                "originalBlockingReason":deterministic.get("reason") or recovery.get("historicalCause"),
                "deliveryExecuted":bool(operation.outbound_telegram_message_id),
                "createdAt":operation.created_at}

    @staticmethod
    def _historical_failure(operation):
        if not operation:
            return None
        payload = dict(getattr(operation, "delivery_payload", None) or {})
        deterministic = dict(payload.get("deterministicDeliveryBlock") or {})
        recovery = dict(payload.get("operatorAuthorizedDeliveryRecovery") or {})
        reason = deterministic.get("reason") or recovery.get("historicalCause")
        if not reason:
            return None
        return {
            "reason": reason,
            "infrastructureCause": recovery.get("historicalInfrastructureCause"),
            "resolvedAt": recovery.get("incidentResolvedAt"),
            "deliveryExecuted": bool(getattr(operation,"outbound_telegram_message_id",None)),
            "evidenceAuthority": (
                "DETERMINISTIC_DELIVERY_BLOCK"
                if deterministic.get("reason") else "OPERATOR_AUTHORIZED_INCIDENT_RECOVERY"
            ),
        }

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

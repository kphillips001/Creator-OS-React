"""Canonical root taxonomy for immutable historical corrective operations."""
from __future__ import annotations

from app.database import get_db_connection


class HistoricalCorrectiveEligibilityService:
    QUALITY = "QUALIFYING_QUALITY_FAILURE"
    NOT_DELIVERED = "CANONICALLY_CONFIRMED_NOT_DELIVERED"
    CONSTRAINT_FAILURE_FOLLOW_UP = "RECOVERY_CONSTRAINT_FAILURE_NOT_DELIVERED"
    RETRY_EXHAUSTED = "RETRY_EXHAUSTED_ZERO_CANDIDATE"

    def __init__(self, *, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def evaluate(self, *, root, parent, creator_profile_id, fanvue_account_id,
                 telegram_user_id, telegram_chat_id, chat_allowed=True):
        root_id = str(root.operation_id) if root else None
        parent_id = str(parent.operation_id) if parent else None
        base = {"eligible": False, "category": None, "mode": None,
                "reason": "MISSING_LINEAGE", "rootOperationId": root_id,
                "parentOperationId": parent_id, "resolutionId": None}
        if not root or not parent:
            return base
        root_kind = getattr(root, "operation_kind", "PRIMARY")
        root_state = getattr(root.state, "value", root.state)
        root_error = str(getattr(root, "last_error", "") or "")
        quality = bool(
            root_kind == "PRIMARY" and root_state == "SUPPRESSED"
            and getattr(root, "outbound_telegram_message_id", None) is None
            and getattr(root, "send_attempt_count", 0) == 0
            and (root_error.startswith("quality_blocked_before_delivery:")
                 or root_error.startswith("quality_corrective_retry_exhausted:"))
        )
        if quality:
            if "MANUFACTURED_ENGAGEMENT_QUESTION" in root_error:
                from app.services.conversation_attention_evidence_service import (
                    ConversationAttentionEvidenceService,
                )
                proof = ConversationAttentionEvidenceService._manufactured_engagement_evidence(
                    root
                )
                if not proof["classificationSupported"]:
                    return {
                        **base,
                        "reason": (
                            "HISTORICAL_CORRECTIVE_MANUFACTURED_ENGAGEMENT_"
                            "EVIDENCE_REQUIRED"
                        ),
                    }
                if not proof["recoverySupported"]:
                    evidence_reason = str(proof.get("reason") or "")
                    if evidence_reason == "CURRENT_TURN_QUESTION_EVIDENCE_REQUIRED":
                        reason = (
                            "HISTORICAL_CORRECTIVE_CURRENT_TURN_QUESTION_"
                            "EVIDENCE_REQUIRED"
                        )
                    elif evidence_reason == "CURRENT_TURN_GREETING_EVIDENCE_REQUIRED":
                        reason = (
                            "HISTORICAL_CORRECTIVE_CURRENT_TURN_GREETING_"
                            "EVIDENCE_REQUIRED"
                        )
                    else:
                        reason = (
                            "HISTORICAL_CORRECTIVE_CURRENT_TURN_OBLIGATION_"
                            "EVIDENCE_REQUIRED"
                        )
                    return {
                        **base,
                        "reason": reason,
                    }
            if "FINAL_REPETITION_FAILURE" in root_error:
                payload = dict(getattr(root, "response_payload", None) or {})
                rejected = str(
                    payload.get("response_text")
                    or getattr(root, "response_text", "") or ""
                ).strip()
                if not rejected:
                    return {
                        **base,
                        "reason": (
                            "HISTORICAL_CORRECTIVE_REJECTED_CANDIDATE_"
                            "EVIDENCE_REQUIRED"
                        ),
                    }
            if parent.operation_id == root.operation_id:
                return {**base, "eligible": True, "category": self.QUALITY,
                        "mode": "FIRST_CORRECTIVE",
                        "reason": "ROOT_QUALITY_FAILURE_DEFINITIVELY_UNSENT"}
            if (getattr(parent, "operation_kind", None) != "HISTORICAL_CORRECTIVE"
                    or str(getattr(parent, "causal_operation_id", "")) != root_id):
                return {**base, "reason": "PARENT_NOT_IN_ROOT_LINEAGE"}
            outcome = self._delivery_outcome(parent)
            if outcome["classification"] != "DEFINITIVE_NOT_DELIVERED":
                return {**base, "reason": outcome["reason"]}
            return {**base, "eligible": True, "category": self.QUALITY,
                    "mode": "FOLLOW_UP_AFTER_DEFINITIVE_NON_DELIVERY",
                    "reason": outcome["reason"]}

        retry_exhausted = bool(
            root_kind == "PRIMARY"
            and root_state == "TERMINAL_FAILED"
            and root_error.startswith("DECISION_ENGINE_EXCEPTION:")
            and int(getattr(root, "generation_attempt_count", 0) or 0)
                >= int(getattr(root, "max_generation_attempts", 0) or 0) > 0
            and not str(getattr(root, "response_text", "") or "").strip()
            and not dict(getattr(root, "response_payload", None) or {}).get(
                "response_text"
            )
            and int(getattr(root, "send_attempt_count", 0) or 0) == 0
            and getattr(root, "outbound_telegram_message_id", None) is None
            and getattr(root, "sent_confirmed_at", None) is None
        )
        if retry_exhausted:
            return self._retry_exhausted_eligibility(
                base=base, root=root, parent=parent,
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                chat_allowed=chat_allowed,
            )

        if not (root_kind == "PRIMARY" and root_state == "SEND_UNCERTAIN"):
            return {**base, "reason": "ROOT_NOT_QUALIFYING_QUALITY_OR_NOT_DELIVERED"}
        follow_up = parent.operation_id != root.operation_id
        if follow_up and not self._constraint_failure_parent(root, parent):
            return {**base, "reason": "NOT_DELIVERED_PARENT_NOT_BOUNDED_CONSTRAINT_FAILURE"}
        if (getattr(root, "outbound_telegram_message_id", None) is not None
                or getattr(root, "sent_confirmed_at", None) is not None):
            return {**base, "reason": "CONFIRMED_OUTBOUND_CONTRADICTS_NOT_DELIVERED"}
        if not chat_allowed:
            return {**base, "reason": "CURRENT_CONTACT_AUTHORITY_DENIED"}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM operator_delivery_resolutions
                WHERE ordinary_operation_id=%s""", (root.operation_id,))
            row = cursor.fetchone()
            resolution = dict(row) if row else None
            if not self._authoritative_not_delivered(resolution):
                return {**base, "reason": "CANONICAL_NOT_DELIVERED_RESOLUTION_REQUIRED"}
            if follow_up:
                cursor.execute("""SELECT parameters FROM conversation_resolution_plans
                    WHERE plan_id=%s""", (parent.recovery_resolution_plan_id,))
                plan = cursor.fetchone()
                constraint = dict(dict(plan or {}).get("parameters") or {}).get(
                    "recoveryExecutionConstraint")
                from app.services.recovery_execution_constraint_service import (
                    RecoveryExecutionConstraintService,
                )
                if constraint != RecoveryExecutionConstraintService.authority():
                    return {**base, "reason": "PARENT_CONSTRAINT_AUTHORITY_NOT_PROVEN"}
                if not RecoveryExecutionConstraintService.supports_repaired_conversation_only_policy():
                    return {**base, "reason": "CURRENT_POLICY_REPAIR_NOT_PROVEN"}
            cursor.execute("""SELECT 1 WHERE
                EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                  WHERE newer.telegram_account_scope=%s AND newer.telegram_chat_id=%s
                    AND newer.telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                  WHERE newer.telegram_account_scope=%s AND newer.telegram_chat_id=%s
                    AND newer.inbound_telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                  WHERE answered.telegram_account_scope=%s AND answered.telegram_chat_id=%s
                    AND answered.state='SENT_CONFIRMED'
                    AND answered.sent_confirmed_at>%s)
                OR EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                  WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                    AND manual.telegram_user_id=%s AND manual.telegram_chat_id=%s
                    AND manual.state='CONFIRMED' AND manual.confirmed_at>%s)""", (
                root.telegram_account_scope, telegram_chat_id,
                root.inbound_telegram_message_id, root.telegram_account_scope,
                telegram_chat_id, root.inbound_telegram_message_id,
                root.telegram_account_scope, telegram_chat_id, root.inbound_received_at,
                creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id, root.inbound_received_at))
            if cursor.fetchone() is not None:
                return {**base, "reason": "SOURCE_INBOUND_NO_LONGER_FRESH"}
            cursor.execute("""SELECT COALESCE(mode,'AVA_AUTO') mode,
                    COALESCE(communication_disposition,'ACTIVE') disposition
                FROM telegram_relationship_controls WHERE creator_profile_id=%s
                  AND fanvue_account_id=%s AND telegram_user_id=%s
                  AND telegram_chat_id=%s LIMIT 1""", (
                creator_profile_id, fanvue_account_id, telegram_user_id, telegram_chat_id))
            control = cursor.fetchone()
            if control and (control["mode"] != "AVA_AUTO"
                            or control["disposition"] != "ACTIVE"):
                return {**base, "reason": "RELATIONSHIP_CONTROL_BLOCKED"}
        return {**base, "eligible": True,
                "category": (self.CONSTRAINT_FAILURE_FOLLOW_UP if follow_up
                             else self.NOT_DELIVERED),
                "mode": ("FOLLOW_UP_AFTER_REPAIRED_RECOVERY_CONSTRAINT_FAILURE"
                         if follow_up else
                         "FIRST_CORRECTIVE_AFTER_ATTESTED_NON_DELIVERY"),
                "reason": ("REPAIRED_CONVERSATION_ONLY_FAILURE_DEFINITIVELY_UNSENT"
                           if follow_up else
                           "CANONICAL_NOT_DELIVERED_SOURCE_INBOUND_UNANSWERED"),
                "resolutionId": str(resolution["resolution_id"])}

    def _retry_exhausted_eligibility(
        self, *, base, root, parent, creator_profile_id, fanvue_account_id,
        telegram_user_id, telegram_chat_id, chat_allowed,
    ):
        """Authorize one immutable-history reevaluation from complete evidence."""
        if parent.operation_id != root.operation_id:
            return {**base, "reason": "RETRY_EXHAUSTED_RECOVERY_ALREADY_EXISTS"}
        if not chat_allowed:
            return {**base, "reason": "CURRENT_CONTACT_AUTHORITY_DENIED"}
        delivery = dict(getattr(root, "delivery_payload", None) or {})
        obligations = tuple(getattr(root, "burst_member_obligations", None) or ())
        meaningful = bool(
            obligations if getattr(root, "conversation_burst_id", None)
            else dict(delivery.get("attentionInvestment") or {}).get(
                "meaningfulObligation"
            ) is True
        )
        if not meaningful:
            return {**base, "reason": "NO_SURVIVING_MEANINGFUL_OBLIGATION"}
        lease = getattr(root, "lease_expires_at", None)
        if getattr(root, "claim_owner", None) and lease is not None:
            from datetime import datetime, timezone
            if lease.tzinfo is None:
                lease = lease.replace(tzinfo=timezone.utc)
            if lease > datetime.now(timezone.utc):
                return {**base, "reason": "ACTIVE_OPERATION_LEASE"}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT 1 FROM ordinary_reply_generation_attempts
                WHERE operation_id=%s AND BTRIM(COALESCE(candidate_text,''))<>''
                LIMIT 1""", (root.operation_id,))
            if cursor.fetchone() is not None:
                return {**base, "reason": "DURABLE_GENERATED_CANDIDATE_EXISTS"}
            cursor.execute("""SELECT 1 WHERE
                EXISTS(SELECT 1 FROM ordinary_chat_reply_operations child
                  WHERE child.causal_operation_id=%s
                    AND child.operation_kind='HISTORICAL_CORRECTIVE')
                OR EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                  WHERE newer.telegram_account_scope=%s
                    AND newer.telegram_chat_id=%s
                    AND newer.telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                  WHERE newer.telegram_account_scope=%s
                    AND newer.telegram_chat_id=%s
                    AND newer.inbound_telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                  WHERE answered.telegram_account_scope=%s
                    AND answered.telegram_chat_id=%s
                    AND answered.state='SENT_CONFIRMED'
                    AND answered.sent_confirmed_at>%s)
                OR EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                  WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                    AND manual.telegram_user_id=%s AND manual.telegram_chat_id=%s
                    AND manual.state='CONFIRMED' AND manual.confirmed_at>%s)""", (
                root.operation_id, root.telegram_account_scope, telegram_chat_id,
                root.inbound_telegram_message_id, root.telegram_account_scope,
                telegram_chat_id, root.inbound_telegram_message_id,
                root.telegram_account_scope, telegram_chat_id,
                root.inbound_received_at, creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id, root.inbound_received_at,
            ))
            if cursor.fetchone() is not None:
                return {**base, "reason": "SOURCE_INBOUND_NO_LONGER_FRESH"}
            cursor.execute("""SELECT 1 FROM telegram_private_inbound_messages
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND telegram_user_id=%s AND telegram_message_id=%s
                  AND creator_profile_id=%s AND fanvue_account_id=%s""", (
                root.telegram_account_scope, telegram_chat_id, telegram_user_id,
                root.inbound_telegram_message_id, creator_profile_id,
                fanvue_account_id,
            ))
            if cursor.fetchone() is None:
                return {**base, "reason": "CURRENT_INBOUND_EVIDENCE_MISSING"}
            cursor.execute("""SELECT COALESCE(mode,'AVA_AUTO') mode,
                    COALESCE(communication_disposition,'ACTIVE') disposition
                FROM telegram_relationship_controls WHERE creator_profile_id=%s
                  AND fanvue_account_id=%s AND telegram_user_id=%s
                  AND telegram_chat_id=%s LIMIT 1""", (
                creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id,
            ))
            control = cursor.fetchone()
            if control and (control["mode"] != "AVA_AUTO"
                            or control["disposition"] != "ACTIVE"):
                return {**base, "reason": "RELATIONSHIP_CONTROL_BLOCKED"}
        return {
            **base, "eligible": True, "category": self.RETRY_EXHAUSTED,
            "mode": "FIRST_REEVALUATION_AFTER_RETRY_EXHAUSTION",
            "reason": "CURRENT_UNANSWERED_OBLIGATION_WITHOUT_DURABLE_CANDIDATE",
        }

    @staticmethod
    def _constraint_failure_parent(root, parent):
        state = getattr(parent.state, "value", parent.state)
        return bool(
            getattr(parent, "operation_kind", None) == "HISTORICAL_CORRECTIVE"
            and str(getattr(parent, "causal_operation_id", ""))
                == str(root.operation_id)
            and str(getattr(parent, "recovery_parent_operation_id", ""))
                == str(root.operation_id)
            and state in {"SUPPRESSED", "TERMINAL_FAILED"}
            and getattr(parent, "send_attempt_count", 0) == 0
            and getattr(parent, "outbound_telegram_message_id", None) is None
            and getattr(parent, "sent_confirmed_at", None) is None
            and str(getattr(parent, "last_error", "") or "")
                == "recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY"
            and getattr(parent, "recovery_resolution_plan_id", None) is not None
        )

    @staticmethod
    def _authoritative_not_delivered(resolution):
        if not resolution:
            return False
        evidence = dict(resolution.get("evidence") or {})
        return bool(
            resolution.get("outcome") == "NOT_DELIVERED"
            and resolution.get("provenance") == "OPERATOR_ATTESTED"
            and resolution.get("provider_acceptance_evidence") is False
            and resolution.get("provider_readback_evidence") is True
            and evidence.get("classification") == "CONFIRMED_NOT_DELIVERED"
            and evidence.get("complete") is True
            and evidence.get("matchingCandidateCount") == 0
        )

    @staticmethod
    def _delivery_outcome(operation):
        state = getattr(operation.state, "value", operation.state)
        if state == "SENT_CONFIRMED" or getattr(operation, "outbound_telegram_message_id", None):
            return {"classification": "CUSTOMER_VISIBLE", "reason": "DELIVERY_CONFIRMED"}
        payload = dict(getattr(operation, "delivery_payload", None) or {})
        rejection = dict(payload.get("telegramDefinitiveRejection") or {})
        if (state in {"SUPPRESSED", "TERMINAL_FAILED"}
                and rejection.get("classification") == "DEFINITIVE_NOT_DELIVERED"
                and rejection.get("automaticRetryAllowed") is False):
            return {"classification": "DEFINITIVE_NOT_DELIVERED",
                    "reason": "DURABLE_PROVIDER_REJECTION"}
        if (state in {"SUPPRESSED", "TERMINAL_FAILED"}
                and getattr(operation, "last_error", None)
                == "RECOVERY_ABORTED_TELEGRAM_PEER_ID_INVALID"):
            return {"classification": "DEFINITIVE_NOT_DELIVERED",
                    "reason": "TELEGRAM_PEER_ID_INVALID"}
        return {"classification": "NOT_ELIGIBLE",
                "reason": "NO_DEFINITIVE_NON_DELIVERY_EVIDENCE"}

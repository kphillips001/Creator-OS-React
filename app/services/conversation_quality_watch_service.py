"""Observational final-response quality alerts for Creator_OS Monitor."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from hashlib import sha256

from app.repositories.customer_abuse_review_repository import CustomerAbuseReviewRepository
from app.services.operator_telegram_alert_service import OperatorTelegramAlertService


class ConversationQualityWatchService:
    WINDOW_SECONDS = 21600

    def __init__(self, *, repository=None, alert_service=None):
        self.repository = repository or CustomerAbuseReviewRepository()
        self.alerts = alert_service or OperatorTelegramAlertService(repository=self.repository)

    @staticmethod
    def material_reasons(response_text, diagnostics):
        style = dict(diagnostics.get("conversationStyle") or diagnostics.get("conversation_style") or {})
        summary = dict(diagnostics.get("commercial_summary") or {})
        reasons = []
        if style.get("customerCommercialStateOverstatementReasons"):
            reasons.append("CUSTOMER_COMMERCIAL_STATE_OVERSTATEMENT")
        if style.get("turnObligationsSatisfied") is False:
            reasons.append("FINAL_TURN_OBLIGATION_FAILURE")
        if style.get("finalResponseRepetitionSatisfied") is False:
            reasons.append("FINAL_REPETITION_FAILURE")
        if style.get("memoryUsageClassification") == "UNSUPPORTED_MEMORY_EXPRESSION":
            reasons.append("UNSUPPORTED_MEMORY_IN_FINAL_RESPONSE")
        if style.get("manufacturedQuestionRisk") is True:
            reasons.append("MANUFACTURED_ENGAGEMENT_QUESTION")
        if re.search(r"(?:\$\s*\d+(?:\.\d{1,2})?|\b\d+(?:\.\d{1,2})?\s*(?:usd|dollars?)\b)", str(response_text or ""), re.I):
            reasons.append("NUMERIC_PAID_PRICE_IN_AVA_PROSE")
        if dict(summary.get("offeringCopySafety") or {}).get("internalOfferingMetadataExposedToGeneration") is True:
            reasons.append("INTERNAL_OFFERING_METADATA_EXPOSED")
        return list(dict.fromkeys(reasons))

    def observe(self, *, response_text, customer_message, diagnostics,
                creator_profile_id=None, fanvue_account_id=None,
                telegram_user_id=None, telegram_chat_id=None,
                correlation_id=None, buyer_context=None, username=None,
                recent_history=()):
        reasons = self.material_reasons(response_text, diagnostics)
        result = {"conversationQualityWatchTriggered": bool(reasons),
                  "conversationQualitySeverity": None,
                  "conversationQualityReasons": reasons,
                  "conversationQualityAlertAuthorized": False,
                  "conversationQualityAlertOperationId": None,
                  "conversationQualityAlertConfirmed": False,
                  "conversationQualityAlertFailed": False}
        if not reasons:
            return result
        high = {"CUSTOMER_COMMERCIAL_STATE_OVERSTATEMENT", "UNSUPPORTED_MEMORY_IN_FINAL_RESPONSE",
                "NUMERIC_PAID_PRICE_IN_AVA_PROSE", "INTERNAL_OFFERING_METADATA_EXPOSED"}
        severity = "HIGH" if high.intersection(reasons) else "REVIEW"
        result["conversationQualitySeverity"] = severity
        now = datetime.now(timezone.utc)
        identity = str(telegram_user_id or telegram_chat_id or "unknown")
        reason = ",".join(sorted(reasons))
        bucket = int(now.timestamp()) // self.WINDOW_SECONDS
        digest = sha256(f"{creator_profile_id}:{identity}:{reason}:{bucket}".encode()).hexdigest()[:24]
        buyer = dict(buyer_context or {})
        customer = f"@{str(username).lstrip('@')} / {identity}" if username else identity
        decision = dict(dict(diagnostics.get("commercial_summary") or {}).get("finalSalesDecision") or {})
        context_lines = []
        for item in list(recent_history or ())[-4:]:
            if isinstance(item, dict):
                role, content = item.get("role"), item.get("content")
            else:
                role, content = getattr(item, "role", None), getattr(item, "content", None)
            if content:
                label = "Customer" if str(role or "").lower() in {"user", "customer"} else "Ava"
                context_lines.append(f"{label}: {str(content)[:220]}")
        bounded_context = (
            "Context:\n" + "\n".join(context_lines) + "\n\n"
            if context_lines else ""
        )
        text = ("⚠️ Ava Conversation Review\n\n"
                f"Severity: {severity}\nReason: {reason}\n\nCustomer: {customer}\n"
                f"Mapped: {'YES' if fanvue_account_id else 'NO'}\n"
                f"Buyer Stage: {buyer.get('buyerStage') or 'UNKNOWN'}\n"
                f"Value Tier: {buyer.get('valueTier') or 'UNKNOWN'}\n"
                f"Lifetime Spend: ${int(buyer.get('lifetimeSpendMinor') or 0)/100:.2f}\n\n"
                f"{bounded_context}"
                f"Customer:\n\"{str(customer_message or '')[:300]}\"\n\n"
                f"Ava:\n\"{str(response_text or '')[:300]}\"\n\n"
                f"Sales Brain:\n{decision.get('decision') or 'UNKNOWN'}\n\n"
                "Conversation continued normally.\nReview when convenient.")
        operation = self.alerts.authorize_and_attempt(
            text=text, notification_type="AVA_CONVERSATION_REVIEW",
            correlation_id=f"quality:{digest}", context={
                "creator_profile_id": creator_profile_id, "fanvue_account_id": fanvue_account_id,
                "telegram_user_id": telegram_user_id, "telegram_chat_id": telegram_chat_id,
                "source_correlation_id": correlation_id, "quality_reason": reason,
                "severity": severity, "incident_window_started_at": now,
            })
        state = str((operation or {}).get("state") or "")
        result.update({"conversationQualityAlertAuthorized": state in {"AUTHORIZED","CLAIMED","SENT_CONFIRMED","FAILED"},
                       "conversationQualityAlertOperationId": str((operation or {}).get("notification_operation_id") or "") or None,
                       "conversationQualityAlertConfirmed": state == "SENT_CONFIRMED",
                       "conversationQualityAlertFailed": state == "FAILED"})
        return result

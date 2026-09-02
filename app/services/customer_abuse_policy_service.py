"""Global mapping-aware qualifying-abuse stop-chat authority."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from app.repositories.customer_abuse_review_repository import CustomerAbuseReviewRepository
from app.services.contextual_customer_tone_service import ContextualCustomerToneService
from app.services.operator_telegram_alert_service import OperatorTelegramAlertService


@dataclass(frozen=True)
class AbusePolicyDecision:
    suppressed: bool
    code: str | None = None
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


class CustomerAbusePolicyService:
    def __init__(self, *, repository=None, prospect_service=None,
                 tone_service=None, alert_service=None):
        self.repository = repository or CustomerAbuseReviewRepository()
        self.prospects = prospect_service
        self.tone = tone_service or ContextualCustomerToneService()
        self.alerts = alert_service or OperatorTelegramAlertService(
            repository=self.repository
        )

    def existing_authority(self, *, creator_profile_id, fanvue_account_id,
                           telegram_user_id, canonical_identity, prospect=None):
        mapping_state = "MAPPED_CUSTOMER" if canonical_identity else "UNMAPPED_TELEGRAM"
        if canonical_identity:
            incident = self.repository.active_for_customer(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=canonical_identity.fanvue_account_id,
                fanvue_user_id=canonical_identity.local_fanvue_user_id,
            )
            if incident:
                status = str(incident["review_status"])
                return AbusePolicyDecision(True,
                    "CUSTOMER_MANUALLY_BLOCKED" if status == "MANUALLY_BLOCKED"
                    else "CUSTOMER_ABUSE_REVIEW_HOLD",
                    self._diagnostics(mapping_state, incident=incident))
        elif prospect is not None and self.prospects is not None:
            block = self.prospects.contact_block(prospect)
            if block and block.get("state") == "PERMANENT_BLOCKED":
                return AbusePolicyDecision(True, "TELEGRAM_ABUSE_BLOCKED", {
                    **self._diagnostics(mapping_state),
                    "unmappedTelegramAutoBlocked": True,
                    "telegramBlockReason": block.get("reason"),
                })
        return AbusePolicyDecision(False, diagnostics=self._diagnostics(mapping_state))

    def evaluate_current(self, *, creator_profile_id, fanvue_account_id,
                         telegram_user_id, telegram_chat_id, inbound_message_id,
                         correlation_id, message, canonical_identity,
                         recent_transcript: Sequence[Mapping] = (), prospect=None,
                         buyer_context: Mapping | None = None,
                         telegram_username=None):
        mapping_state = "MAPPED_CUSTOMER" if canonical_identity else "UNMAPPED_TELEGRAM"
        tone = self.tone.classify(
            message=message, recent_transcript=recent_transcript,
            relationship_context={}, commerce_context=dict(buyer_context or {}),
        )
        base = self._diagnostics(mapping_state, tone=tone)
        if not tone.get("qualifyingAbuse"):
            return AbusePolicyDecision(False, diagnostics=base)
        if canonical_identity is None:
            if self.prospects is None:
                raise RuntimeError("Unmapped prospect persistence is required for abuse blocking.")
            self.prospects.record_contact_block(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                reason=str(tone.get("abuseCategory")), correlation_id=correlation_id,
            )
            return AbusePolicyDecision(True, "TELEGRAM_ABUSE_AUTO_BLOCKED", {
                **base, "unmappedTelegramAutoBlocked": True,
                "telegramBlockReason": tone.get("abuseCategory"),
            })
        context = dict(buyer_context or {})
        incident = self.repository.create_or_append_open(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=canonical_identity.fanvue_account_id,
            fanvue_user_id=canonical_identity.local_fanvue_user_id,
            telegram_user_id=telegram_user_id, telegram_chat_id=telegram_chat_id,
            abuse_severity=tone["abuseSeverity"],
            abuse_category=tone["abuseCategory"],
            abuse_reason=tone["abuseCategory"], inbound_message_id=inbound_message_id,
            inbound_correlation_id=correlation_id,
            sanitized_excerpt=self._sanitize_excerpt(message),
            buyer_stage_snapshot=context.get("buyerStage"),
            value_tier_snapshot=context.get("valueTier"),
            lifetime_spend_minor_snapshot=context.get("lifetimeSpendMinor", 0),
            incident_group_key=(f"{creator_profile_id}:{canonical_identity.fanvue_account_id}:"
                                f"{canonical_identity.local_fanvue_user_id}:OPEN"),
        )
        notification = None
        if incident.get("created"):
            notification = self.alerts.authorize_and_attempt(
                incident=incident,
                text=self._alert_text(incident, telegram_username=telegram_username),
                notification_type="ABUSIVE_CUSTOMER_REVIEW",
            )
        return AbusePolicyDecision(True, "CUSTOMER_ABUSE_REVIEW_HOLD", {
            **base, **self._diagnostics(mapping_state, incident=incident,
                                        notification=notification),
        })

    def release(self, *, incident_id, reviewed_by, reason,
                creator_profile_id=None):
        return self.repository.resolve(incident_id=incident_id,
            target_status="RELEASED", reviewed_by=reviewed_by, reason=reason,
            creator_profile_id=creator_profile_id)

    def manual_block(self, *, incident_id, reviewed_by, reason,
                     creator_profile_id=None):
        return self.repository.resolve(incident_id=incident_id,
            target_status="MANUALLY_BLOCKED", reviewed_by=reviewed_by, reason=reason,
            creator_profile_id=creator_profile_id)

    @staticmethod
    def _sanitize_excerpt(message):
        value = re.sub(r"https?://\S+|\b\d{6,}\b", "[redacted]", str(message or ""))
        return value.replace("\n", " ").replace("\r", " ").strip()[:180] or None

    @staticmethod
    def _alert_text(incident, *, telegram_username=None):
        identity = f"@{str(telegram_username).lstrip('@')}" if telegram_username else str(incident["telegram_user_id"])
        spend = int(incident.get("lifetime_spend_minor_snapshot") or 0) / 100
        return (
            "🚨 Abusive Customer Review\n\n"
            f"Customer: {identity} / {incident['telegram_user_id']}\n"
            f"Buyer Stage: {incident.get('buyer_stage_snapshot') or 'UNKNOWN'}\n"
            f"Value Tier: {incident.get('value_tier_snapshot') or 'UNKNOWN'}\n"
            f"Lifetime Spend: ${spend:.2f}\n"
            f"Severity: {incident['abuse_severity']}\nReason: {incident['abuse_category']}\n\n"
            f"Customer:\n\"{incident.get('sanitized_excerpt') or '[redacted]'}\"\n\n"
            "AVA HAS STOPPED CHATTING WITH THIS CUSTOMER.\n\n"
            "Status: REVIEW HOLD\nManual review required.\n"
            "Customer has NOT been permanently blocked."
        )

    @staticmethod
    def _diagnostics(mapping_state, *, tone=None, incident=None, notification=None):
        tone = dict(tone or {})
        incident = dict(incident or {})
        notification = dict(notification or {})
        state = str(notification.get("state") or "")
        return {
            "mappingState": mapping_state,
            "hostilityLevel": tone.get("hostilityLevel"),
            "qualifyingAbuse": bool(tone.get("qualifyingAbuse")),
            "abuseCategory": tone.get("abuseCategory"),
            "abuseSeverity": tone.get("abuseSeverity"),
            "abuseReviewIncidentId": str(incident.get("incident_id") or "") or None,
            "abuseReviewStatus": incident.get("review_status"),
            "interactionReviewHoldActive": bool(incident.get("interaction_hold_active")),
            "mappedCustomerManualReviewRequired": incident.get("review_status") == "OPEN",
            "operatorAlertAuthorized": state in {"AUTHORIZED","CLAIMED","SENT_CONFIRMED","FAILED"},
            "operatorAlertAttempted": bool(notification.get("attempted_at")),
            "operatorAlertConfirmed": state == "SENT_CONFIRMED",
            "operatorAlertFailed": state == "FAILED",
        }

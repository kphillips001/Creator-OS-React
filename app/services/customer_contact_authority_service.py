"""One purpose-aware authority for customer contact timing and coordination."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.models.customer_contact import (
    ContactPolicyResult, ContactPurpose, CustomerContactDecision,
)


class CustomerContactAuthorityService:
    """Decide whether a proposed contact is appropriate now.

    This service deliberately does not choose products, copy, or commercial
    strategy. Callers supply canonical lifecycle/delivery evidence already
    owned by those domains.
    """

    PRIORITY = {
        ContactPurpose.PURCHASE_ACKNOWLEDGEMENT: 100,
        ContactPurpose.REACTIVE_CONVERSATION: 95,
        ContactPurpose.REACTIVE_COMMERCIAL: 95,
        ContactPurpose.SESSION_CONTINUATION: 90,
        ContactPurpose.ACTIVE_OFFER_FOLLOWUP: 80,
        ContactPurpose.DELAYED_FOLLOWUP: 55,
        ContactPurpose.FREE_ENGAGEMENT: 40,
        ContactPurpose.RE_ENGAGEMENT: 30,
        ContactPurpose.OUTREACH: 25,
        ContactPurpose.MASS_PPV: 10,
    }
    OPTIONAL_PROACTIVE = frozenset({
        ContactPurpose.FREE_ENGAGEMENT, ContactPurpose.RE_ENGAGEMENT,
        ContactPurpose.OUTREACH, ContactPurpose.DELAYED_FOLLOWUP,
        ContactPurpose.MASS_PPV,
    })
    PROMOTIONAL = OPTIONAL_PROACTIVE

    def __init__(self, reservation_repository=None):
        self._reservation_repository = reservation_repository

    def authorize_proactive(self, *, purpose: ContactPurpose | str,
                            fanvue_account_id: int, customer_scope: str,
                            owner_id: str, evidence=None,
                            creator_profile_id: int | None = None,
                            correlation_id: str | None = None,
                            lease_seconds: int = 300):
        decision = self.decide(purpose=purpose, evidence=evidence)
        if decision.result is not ContactPolicyResult.ALLOW:
            return decision, None
        if decision.purpose not in self.OPTIONAL_PROACTIVE:
            return decision, None
        repository = self._reservations()
        reservation, competing = repository.try_acquire(
            fanvue_account_id=fanvue_account_id,
            customer_scope=customer_scope,
            contact_purpose=decision.purpose.value,
            owner_id=owner_id, creator_profile_id=creator_profile_id,
            correlation_id=correlation_id, lease_seconds=lease_seconds,
            metadata={"priority": decision.priority},
        )
        if reservation is not None:
            return decision, reservation
        blocked = CustomerContactDecision(
            purpose=decision.purpose, reactive=False,
            result=ContactPolicyResult.DEFER,
            reason="PROACTIVE_CONTACT_RESERVATION_HELD",
            priority=decision.priority,
            competing_interaction=(
                f"{competing.contact_purpose}:{competing.state}"
                if competing else "PROACTIVE_CONTACT"
            ),
            evidence={**dict(decision.evidence),
                      "competingReservationId": str(competing.reservation_id) if competing else None},
        )
        return blocked, None

    def finalize_reservation(self, reservation, *, outcome: str,
                             delivery_reference: str | None = None,
                             error: str | None = None):
        return self._reservations().finalize(
            reservation.reservation_id, owner_id=reservation.owner_id,
            state=outcome, delivery_reference=delivery_reference,
            last_error=error,
        )

    def _reservations(self):
        if self._reservation_repository is None:
            from app.repositories.customer_contact_reservation_repository import (
                CustomerContactReservationRepository,
            )
            self._reservation_repository = CustomerContactReservationRepository()
        return self._reservation_repository

    def decide(self, *, purpose: ContactPurpose | str,
               evidence: Mapping[str, Any] | None = None,
               now: datetime | None = None) -> CustomerContactDecision:
        purpose = purpose if isinstance(purpose, ContactPurpose) else ContactPurpose(str(purpose))
        state = dict(evidence or {})
        reactive = purpose in {
            ContactPurpose.REACTIVE_CONVERSATION,
            ContactPurpose.REACTIVE_COMMERCIAL,
        }
        priority = self.PRIORITY[purpose]
        current = now or datetime.now(timezone.utc)
        base = {
            "activeOffer": bool(state.get("active_offer")),
            "activeSession": bool(state.get("active_session")),
            "backOff": bool(state.get("back_off")),
            "attentionMode": str(state.get("attention_mode") or "STANDARD").upper(),
            "buyerValueTier": str(state.get("buyer_value_tier") or "UNKNOWN").upper(),
            "recentPurchase": bool(state.get("recent_purchase")),
            "pendingDelivery": bool(state.get("pending_delivery")),
            "uncertainDelivery": bool(state.get("uncertain_delivery")),
            "activeConversation": bool(state.get("active_conversation")),
            "lastConfirmedContactAt": self._iso(state.get("last_confirmed_contact_at")),
            "evaluatedAt": current.isoformat(),
        }

        def decision(result, reason, competing=None):
            return CustomerContactDecision(
                purpose=purpose, reactive=reactive, result=result,
                reason=reason, priority=priority,
                competing_interaction=competing, evidence=base,
            )

        if state.get("safety_blocked") or state.get("customer_boundary_blocked"):
            return decision(ContactPolicyResult.SUPPRESS, "CUSTOMER_SAFETY_BLOCKED", "SAFETY")
        if reactive:
            return decision(ContactPolicyResult.ALLOW, "LEGITIMATE_REACTIVE_CONTACT")
        if purpose is ContactPurpose.PURCHASE_ACKNOWLEDGEMENT:
            return decision(ContactPolicyResult.ALLOW, "PURCHASE_ACKNOWLEDGEMENT_PRIORITY")
        if state.get("uncertain_delivery"):
            return decision(ContactPolicyResult.DEFER, "DELIVERY_OUTCOME_UNCERTAIN", "SEND_UNCERTAIN")
        if state.get("pending_delivery"):
            return decision(ContactPolicyResult.DEFER, "HIGHER_PRIORITY_DELIVERY_IN_FLIGHT", "PENDING_DELIVERY")
        if purpose in self.OPTIONAL_PROACTIVE and state.get("back_off"):
            return decision(ContactPolicyResult.SUPPRESS, "BACK_OFF_SUPPRESSES_OPTIONAL_CONTACT", "BACK_OFF")
        if purpose in self.OPTIONAL_PROACTIVE and str(state.get("attention_mode") or "").upper() in {"MINIMAL", "COMPRESSED"}:
            return decision(ContactPolicyResult.SUPPRESS, "LOW_ATTENTION_SUPPRESSES_OPTIONAL_CONTACT", "ATTENTION_TAPER")
        if state.get("active_session"):
            if purpose is ContactPurpose.SESSION_CONTINUATION:
                return decision(ContactPolicyResult.ALLOW, "ACTIVE_SESSION_CONTINUATION_PRIORITY", "SALES_SESSION")
            if purpose in self.OPTIONAL_PROACTIVE:
                return decision(ContactPolicyResult.SUPPRESS, "ACTIVE_SESSION_SUPPRESSES_UNRELATED_CONTACT", "SALES_SESSION")
        if state.get("active_offer"):
            if purpose is ContactPurpose.ACTIVE_OFFER_FOLLOWUP:
                return decision(
                    ContactPolicyResult.ALLOW if state.get("followup_due") else ContactPolicyResult.DEFER,
                    "ACTIVE_OFFER_FOLLOWUP_DUE" if state.get("followup_due") else "ACTIVE_OFFER_FOLLOWUP_NOT_DUE",
                    "PURCHASE_INTENT",
                )
            if purpose in self.PROMOTIONAL:
                return decision(ContactPolicyResult.SUPPRESS, "ACTIVE_OFFER_SUPPRESSES_COMPETING_PROMOTION", "PURCHASE_INTENT")
        if purpose in self.PROMOTIONAL and state.get("recent_purchase"):
            return decision(ContactPolicyResult.DEFER, "RECENT_PURCHASE_PROTECTION", "RECENT_PURCHASE")
        if purpose in self.OPTIONAL_PROACTIVE and state.get("active_conversation"):
            return decision(ContactPolicyResult.DEFER, "ACTIVE_CONVERSATION_HAS_PRIORITY", "ACTIVE_CONVERSATION")
        if purpose is ContactPurpose.FREE_ENGAGEMENT and state.get("recent_ppv"):
            return decision(ContactPolicyResult.DEFER, "RECENT_PPV_SUPPRESSES_FREE_ENGAGEMENT", "RECENT_PPV")
        if purpose in {ContactPurpose.OUTREACH, ContactPurpose.RE_ENGAGEMENT} and state.get("recent_free_teaser"):
            return decision(ContactPolicyResult.DEFER, "RECENT_FREE_ENGAGEMENT_SUPPRESSES_OUTREACH", "RECENT_FREE_ENGAGEMENT")
        if state.get("cooldown_active"):
            return decision(ContactPolicyResult.DEFER, "PURPOSE_COOLDOWN_ACTIVE")
        return decision(ContactPolicyResult.ALLOW, "CONTACT_POLICY_CLEAR")

    @staticmethod
    def _iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else value

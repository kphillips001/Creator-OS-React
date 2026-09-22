"""Canonical, identity-neutral policy for one unresolved presented offer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.models.purchase_intent import PurchaseIntentStatus


@dataclass(frozen=True)
class ActiveOfferFollowThroughDecision:
    eligible: bool
    mode: str | None
    reason: str
    next_eligible_at: datetime | None


class ActiveOfferFollowThroughService:
    QUALIFYING = frozenset({PurchaseIntentStatus.PRESENTED, PurchaseIntentStatus.CLICKED})

    def evaluate(self, *, intent, now: datetime, nudge_delay: timedelta,
                 contextual_continuation: str | None = None,
                 fresh_direct_intent: bool = False,
                 meaningful_turns_after_presentation: int = 0,
                 engagement_delay: timedelta = timedelta(minutes=45),
                 rejected: bool = False) -> ActiveOfferFollowThroughDecision:
        if intent is None or rejected:
            return ActiveOfferFollowThroughDecision(False, None, "NO_QUALIFYING_ACTIVE_OFFER", None)
        current = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
        expiry = getattr(intent, "expires_at", current + nudge_delay)
        expiry = expiry if expiry.tzinfo else expiry.replace(tzinfo=timezone.utc)
        unsettled = not any((getattr(intent, "purchased_at", None),
            getattr(intent, "provider_transaction_order_id", None),
            getattr(intent, "provider_payment_id", None),
            getattr(intent, "provider_event_id", None)))
        if getattr(intent, "status", None) not in self.QUALIFYING or expiry <= current or not unsettled:
            return ActiveOfferFollowThroughDecision(False, None, "NO_QUALIFYING_ACTIVE_OFFER", None)
        presented = getattr(intent, "presented_at", None) or getattr(intent, "created_at", None)
        if presented is None:
            return ActiveOfferFollowThroughDecision(False, None, "PRESENTATION_NOT_PROVEN", None)
        if contextual_continuation or fresh_direct_intent:
            return ActiveOfferFollowThroughDecision(True, "CONTEXTUAL", "CUSTOMER_CONTEXT", current)
        engagement_at = presented + engagement_delay
        if meaningful_turns_after_presentation >= 4 and current >= engagement_at:
            return ActiveOfferFollowThroughDecision(True, "ENGAGEMENT", "SUSTAINED_ENGAGEMENT", engagement_at)
        eligible_at = presented + nudge_delay
        return ActiveOfferFollowThroughDecision(
            current >= eligible_at, "TIMED" if current >= eligible_at else None,
            "TIMED_NUDGE_ELIGIBLE" if current >= eligible_at else "WAITING_PERIOD",
            eligible_at,
        )

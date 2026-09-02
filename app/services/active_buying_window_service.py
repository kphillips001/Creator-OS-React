"""Canonical derived ordinary-commerce buying-window policy."""
from __future__ import annotations

from collections.abc import Mapping


class ActiveBuyingWindowService:
    """Project current customer-led momentum without authorizing commerce."""

    @staticmethod
    def project(*, recent_verified_purchase: bool, fresh_direct_intent: bool,
                explicit_continuation: bool, active_purchase_intent: bool,
                acknowledgement_pending: bool, declined: bool,
                safety_allowed: bool, active_session: bool,
                cooldown_active: bool, receptiveness: Mapping | None = None,
                deferred_continuation: Mapping | None = None,
                active_offer_context: bool = False) -> dict:
        deferred = dict(deferred_continuation or {})
        deferred_ready = deferred.get("state") in {"READY", "CLAIMED"}
        continuation_commercial_context = bool(
            recent_verified_purchase
            or active_purchase_intent
            or active_offer_context
            or acknowledgement_pending
            or deferred_ready
        )
        continuation_authority = bool(
            fresh_direct_intent
            or deferred_ready
            or (explicit_continuation and continuation_commercial_context)
        )
        evidence = {
            "recentVerifiedPurchase": bool(recent_verified_purchase),
            "freshDirectIntent": bool(fresh_direct_intent),
            "explicitContinuationIntent": bool(explicit_continuation),
            "commercialReceptiveness": dict(receptiveness or {}),
            "activePurchaseIntent": bool(active_purchase_intent),
            "activeOfferContext": bool(active_offer_context),
            "pendingAcknowledgement": bool(acknowledgement_pending),
            "declineOrBackOff": bool(declined),
            "safetyAllowed": bool(safety_allowed),
            "activeSession": bool(active_session),
            "purchaseCooldownActive": bool(cooldown_active),
            "deferredContinuationState": deferred.get("state"),
            "commercialInterestType": dict(receptiveness or {}).get(
                "commercialInterestType", "NONE"
            ),
            "continuationCommercialContextPresent": (
                continuation_commercial_context
            ),
            "activeBuyingWindowAuthoritySatisfied": continuation_authority,
        }
        if not safety_allowed:
            active, reason = False, "SAFETY_RESTRICTION"
        elif active_session:
            active, reason = False, "ACTIVE_SESSION_PRECEDENCE"
        elif declined:
            active, reason = False, "DECLINE_OR_BACK_OFF"
        elif active_purchase_intent:
            active, reason = False, "UNRESOLVED_ACTIVE_PURCHASE_INTENT"
        elif acknowledgement_pending and explicit_continuation:
            active, reason = True, "ACKNOWLEDGEMENT_FIRST_CONTINUATION_DEFERRED"
        elif deferred_ready:
            active, reason = True, "DEFERRED_CUSTOMER_CONTINUATION"
        elif fresh_direct_intent:
            active, reason = True, "CURRENT_CUSTOMER_DIRECT_INTENT"
        elif explicit_continuation and continuation_commercial_context:
            active, reason = True, "COMMERCIAL_CONTEXT_CONTINUATION"
        elif explicit_continuation:
            active, reason = False, "CONTINUATION_WITHOUT_COMMERCIAL_CONTEXT"
        else:
            active, reason = False, (
                "PURCHASE_COOLDOWN_WITHOUT_DIRECT_CONTINUATION"
                if cooldown_active else "NO_CURRENT_CUSTOMER_LED_BUYING_MOMENTUM"
            )
        another_sale = bool(
            active and not acknowledgement_pending and not active_purchase_intent
            and not active_session and safety_allowed and not declined
        )
        if active:
            momentum = (
                "DEFERRED_CUSTOMER_CONTINUATION"
                if deferred_ready else
                "EXPLICIT_CUSTOMER_CONTINUATION"
                if explicit_continuation and continuation_commercial_context else
                "FRESH_DIRECT_BUYING_INTENT"
            )
            decay_reason = None
        else:
            momentum = "INACTIVE"
            decay_reason = reason
        return {
            "active": active,
            "reason": reason,
            "evidence": evidence,
            "source": "PRODUCTION_CUSTOMER_STATE",
            "currentCommercialMomentum": momentum,
            "momentumDecayReason": decay_reason,
            "purchaseCooldownOverridden": bool(
                cooldown_active and active and (
                    fresh_direct_intent or explicit_continuation or deferred_ready
                )
            ),
            "anotherSaleAppropriateNow": another_sale,
            "anotherSaleSuppressionReason": None if another_sale else reason,
            "customerLedContinuation": bool(
                active and explicit_continuation
                and continuation_commercial_context
            ),
            "continuationCommercialContextPresent": (
                continuation_commercial_context
            ),
            "activeBuyingWindowAuthoritySatisfied": continuation_authority,
            "scenarioInfluencedCommercialAuthority": False,
        }

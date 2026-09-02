"""Canonical boundary between ordinary PPV continuation and Session proposal."""
from __future__ import annotations

import re
from collections.abc import Mapping


class SessionEscalationDecisionService:
    """Derive strategy only; never creates a Sales Session or PurchaseIntent."""

    ONGOING = re.compile(
        r"\b(?:keep\s+(?:this\s+)?going|don(?:'|.)t\s+stop|keep\s+showing|"
        r"what\s+comes\s+next|take\s+me\s+through|the\s+(?:whole|rest)|"
        r"whole\s+(?:thing|sequence)|keep\s+it\s+going|going\s+with\s+you)\b",
        re.I,
    )
    DISCRETE = re.compile(
        r"\b(?:send|show)(?:\s+me)?\s+another(?:\s+one)?\b|"
        r"\b(?:got|have)\s+another\b|\bnext\s+one\b|"
        r"\banything\s+hotter\b|\banother\s+(?:one|pic|photo|video)\b",
        re.I,
    )
    ACCEPT = re.compile(
        r"\b(?:yes|yeah|yep|i(?:'| a)m\s+in|let(?:'| u)s\s+do\s+it|"
        r"sounds\s+good|keep\s+it\s+going)\b", re.I,
    )
    STOP = re.compile(
        r"\b(?:stop|no\s+more|not\s+interested|done|that(?:'| i)s\s+enough)\b",
        re.I,
    )

    @classmethod
    def continuation_intent(cls, message: str) -> str:
        value = str(message or "")
        if cls.ONGOING.search(value):
            return "ONGOING_EXPERIENCE"
        if cls.DISCRETE.search(value):
            return "DISCRETE_ITEM"
        return "NONE"

    @classmethod
    def proposal_reaction(cls, message: str, *, proposal_pending: bool) -> str:
        if not proposal_pending:
            return "NONE"
        value = str(message or "")
        continuation = cls.continuation_intent(value)
        if cls.STOP.search(value):
            return "DECLINE_AND_STOP"
        if continuation == "DISCRETE_ITEM" and re.search(
            r"\b(?:rather|just|instead|not\s+(?:that|the\s+whole))\b", value, re.I,
        ):
            return "DECLINE_SESSION_BUT_WANTS_MORE"
        if cls.ACCEPT.search(value) or continuation == "ONGOING_EXPERIENCE":
            return "ACCEPT_OR_LEAN_IN"
        return "NONE"

    @classmethod
    def project(
        cls, *, active_buying_window: bool, purchase_count: int,
        recent_purchase_count: int, current_message: str,
        explicit_continuation_count: int,
        session_inventory_available: bool,
        ordinary_inventory_available: bool,
        active_purchase_intent: bool = False, active_session: bool = False,
        rejection_or_back_off: bool = False, safety_allowed: bool = True,
        proposal_pending: bool = False,
        deferred_continuation: Mapping | None = None,
    ) -> dict:
        deferred = dict(deferred_continuation or {})
        current_intent = cls.continuation_intent(current_message)
        if current_intent == "NONE" and deferred.get("state") in {"READY", "CLAIMED"}:
            current_intent = str(deferred.get("continuationType") or "NONE")
        reaction = cls.proposal_reaction(
            current_message, proposal_pending=proposal_pending,
        )
        repeated_purchases = int(purchase_count) >= 2
        ongoing = current_intent == "ONGOING_EXPERIENCE"
        candidate = bool(active_buying_window and repeated_purchases and ongoing)
        reason = (
            "REPEATED_PURCHASES_AND_ONGOING_EXPERIENCE_INTENT"
            if candidate else "SESSION_CANDIDATE_EVIDENCE_INSUFFICIENT"
        )
        if not safety_allowed or rejection_or_back_off or reaction == "DECLINE_AND_STOP":
            decision, escalation_reason = "NO_FURTHER_SALE_NOW", "SAFETY_OR_CUSTOMER_STOP"
        elif active_session:
            decision, escalation_reason = "NO_FURTHER_SALE_NOW", "ACTIVE_SESSION_PRECEDENCE"
        elif active_purchase_intent:
            decision, escalation_reason = "NO_FURTHER_SALE_NOW", "UNRESOLVED_PURCHASE_INTENT"
        elif reaction == "ACCEPT_OR_LEAN_IN":
            decision, escalation_reason = "SESSION_ACCEPTED", "CUSTOMER_ACCEPTED_SESSION_PROPOSAL"
        elif reaction == "DECLINE_SESSION_BUT_WANTS_MORE":
            decision, escalation_reason = "CONTINUE_DISCRETE_PPVS", "SESSION_DECLINED_DISCRETE_CONTINUATION"
        elif proposal_pending:
            decision, escalation_reason = "NO_FURTHER_SALE_NOW", "SESSION_PROPOSAL_PENDING"
        elif candidate and session_inventory_available:
            decision, escalation_reason = "PROPOSE_SESSION", "SESSION_CANDIDATE_AND_INVENTORY_READY"
        elif candidate and not session_inventory_available and ordinary_inventory_available:
            decision, escalation_reason = "CONTINUE_DISCRETE_PPVS", "SESSION_NOT_AVAILABLE"
        elif current_intent == "DISCRETE_ITEM" and active_buying_window:
            decision, escalation_reason = "CONTINUE_DISCRETE_PPVS", "CUSTOMER_REQUESTED_DISCRETE_ITEM"
        elif ongoing and active_buying_window and ordinary_inventory_available:
            decision, escalation_reason = "CONTINUE_DISCRETE_PPVS", "DEFAULT_ORDINARY_AFTER_ONE_PURCHASE"
        else:
            decision, escalation_reason = "NO_FURTHER_SALE_NOW", "NO_CURRENT_AUTHORIZED_CONTINUATION"
        return {
            "sessionCandidate": candidate,
            "sessionCandidateReason": reason,
            "sessionCompatibleInventoryAvailable": bool(session_inventory_available),
            "sessionEscalationDecision": decision,
            "sessionEscalationReason": escalation_reason,
            "continueDiscretePpvsAuthorized": decision == "CONTINUE_DISCRETE_PPVS",
            "sessionProposalAuthorized": decision == "PROPOSE_SESSION" and not proposal_pending,
            "sessionProposalPending": bool(
                decision == "PROPOSE_SESSION"
                or (proposal_pending and reaction == "NONE")
            ),
            "sessionProposalCustomerReaction": reaction,
            "activeSessionPrecedence": bool(active_session),
            "sessionUnavailableFallback": escalation_reason == "SESSION_NOT_AVAILABLE",
            "ownershipSafeOrdinaryInventoryAvailable": bool(ordinary_inventory_available),
            "purchaseStreakCount": int(purchase_count),
            "recentPurchaseVelocity": {
                "recentPurchaseCount": int(recent_purchase_count),
                "supportingEvidenceOnly": True,
            },
            "explicitContinuationCount": int(explicit_continuation_count),
            "currentContinuationIntent": current_intent,
            "sessionStartAuthorityEligible": decision == "SESSION_ACCEPTED",
            "sessionStarted": False,
        }

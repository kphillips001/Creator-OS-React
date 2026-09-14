"""Deterministic final gate immediately before ordinary Telegram delivery."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryQualityDecision:
    allowed: bool
    reasons: tuple[str, ...]
    disposition: str


class OrdinaryReplyDeliveryQualityGate:
    BLOCKING_REASONS = frozenset({
        "MANUFACTURED_ENGAGEMENT_QUESTION",
        "FINAL_REPETITION_FAILURE",
        "CUSTOMER_QUESTION_UNANSWERED",
        "FINAL_TURN_OBLIGATION_FAILURE",
        "TURN_OBLIGATIONS_UNSATISFIED",
        "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",
        "EXCESSIVE_FLIRT_ESCALATION",
        "REPEATED_FLIRT_FUNCTION",
        "UNAUTHORIZED_COMMERCIAL_TEASE",
    })

    def evaluate(self, result) -> DeliveryQualityDecision:
        diagnostics = dict(result.diagnostic_metadata or {})
        style = dict(diagnostics.get("conversationStyle") or {})
        reasons = set(diagnostics.get("conversationQualityReasons") or ())
        reasons.update(style.get("styleRewriteReasons") or ())
        reasons.update(style.get("unsatisfiedTurnObligations") or ())
        # A prior candidate may retain risk diagnostics after a successful
        # deletion-first repair. Only a question still present in the final
        # customer-facing text can be a final manufactured-question failure.
        final_text = str(getattr(result, "response_text", "") or "")
        from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
        if AvaNaturalConversationPolicy.RECIPROCAL_CLAIM.search(final_text):
            reasons.add("UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM")
        premium = dict(diagnostics.get("premiumSextingAuthority") or {})
        if (AvaNaturalConversationPolicy.SEXUAL_ELABORATION.search(final_text)
                and not (premium.get("authorized") is True and premium.get("evidence"))):
            reasons.add("EXCESSIVE_FLIRT_ESCALATION")
        sales_decision = str(
            diagnostics.get("customer_sales_decision")
            or diagnostics.get("customerSalesDecision")
            or diagnostics.get("decision") or ""
        ).upper()
        if (AvaNaturalConversationPolicy.COMMERCIAL_TEASE.search(final_text)
                and sales_decision not in {"PRESENT_OFFER", "BUILD_INTEREST"}
                and diagnostics.get("paidPresentationAuthorized") is not True
                and diagnostics.get("commercialTeaseAuthorized") is not True):
            reasons.add("UNAUTHORIZED_COMMERCIAL_TEASE")
        if style.get("manufacturedQuestionRisk") is True and "?" in final_text:
            reasons.add("MANUFACTURED_ENGAGEMENT_QUESTION")
        if style.get("finalResponseRepetitionSatisfied") is False:
            reasons.add("FINAL_REPETITION_FAILURE")
        if style.get("customerQuestionAnswered") is False:
            reasons.add("CUSTOMER_QUESTION_UNANSWERED")
        if style.get("turnObligationsSatisfied") is False:
            reasons.add("TURN_OBLIGATIONS_UNSATISFIED")
        natural = dict(diagnostics.get("naturalConversation") or {})
        if natural.get("finalRelationshipBoundarySatisfied") is False:
            reasons.add("UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM")
        if natural.get("finalEscalationBoundarySatisfied") is False:
            reasons.add("EXCESSIVE_FLIRT_ESCALATION")
        if natural.get("finalRepeatedFlirtFunctionSatisfied") is False:
            reasons.add("REPEATED_FLIRT_FUNCTION")
        blocking = tuple(sorted(reasons.intersection(self.BLOCKING_REASONS)))
        return DeliveryQualityDecision(
            allowed=not blocking, reasons=blocking,
            disposition="ALLOWED" if not blocking else "BLOCKED_BEFORE_DELIVERY",
        )

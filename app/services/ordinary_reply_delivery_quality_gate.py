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
        "INERT_ENGAGED_RESPONSE",
        "UNSUPPORTED_EXPLICIT_CALLBACK",
        "MANUFACTURED_ENGAGEMENT_QUESTION",
        "FINAL_REPETITION_FAILURE",
        "CUSTOMER_QUESTION_UNANSWERED",
        "FINAL_TURN_OBLIGATION_FAILURE",
        "TURN_OBLIGATIONS_UNSATISFIED",
        "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",
        "EXCESSIVE_FLIRT_ESCALATION",
        "REPEATED_FLIRT_FUNCTION",
        "UNAUTHORIZED_COMMERCIAL_TEASE",
        "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY",
        "INTERNAL_FAILURE_PAYLOAD",
        "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION",
        "UNNECESSARY_POLICY_NARRATION",
    })

    def evaluate(self, result, *, customer_text: str = "",
                 recent_context=()) -> DeliveryQualityDecision:
        diagnostics = dict(result.diagnostic_metadata or {})
        style = dict(diagnostics.get("conversationStyle") or {})
        reasons = set(diagnostics.get("conversationQualityReasons") or ())
        if (diagnostics.get("generation_fallback")
                or diagnostics.get("internal_generation_failure")
                or str(diagnostics.get("status") or "").lower() == "engine_exception"
                or str(getattr(result, "error_code", "") or "").startswith("internal_")):
            reasons.add("INTERNAL_FAILURE_PAYLOAD")
        reasons.update(style.get("styleRewriteReasons") or ())
        reasons.update(style.get("unsatisfiedTurnObligations") or ())
        # A prior candidate may retain risk diagnostics after a successful
        # deletion-first repair. Only a question still present in the final
        # customer-facing text can be a final manufactured-question failure.
        final_text = str(getattr(result, "response_text", "") or "")
        from app.services.conversation_momentum_strategy import ConversationMomentumStrategy as Momentum
        previous_momentum = style.get("conversationMomentum") or {}
        if previous_momentum.get("version") == Momentum.VERSION:
            # Natural-conversation policy may have edited text after generation.
            # Recheck the exact final text rather than certifying a discarded draft.
            momentum = Momentum.assess(customer_text, final_text, plan=previous_momentum,
                question_reason=style.get("questionReason"),
                manufactured=bool(style.get("manufacturedQuestionRisk")),
                contribution=style.get("contributionType", "NONE"),
                memory_callback=bool(style.get("memoryCallbackUsed")))
            for key in ("fallbackUsed", "styleIntervention", "candidateReplaced"):
                momentum[key] = bool(previous_momentum.get(key))
            reasons.discard("INERT_ENGAGED_RESPONSE")
            reasons.update(momentum["blockingReasons"])
            style["conversationMomentum"] = momentum
            result.diagnostic_metadata["conversationStyle"] = style
        from app.services.policy_narration_quality_service import (
            PolicyNarrationQualityService,
        )
        if PolicyNarrationQualityService.violation(
            final_text, diagnostics=diagnostics,
        ):
            reasons.add("UNNECESSARY_POLICY_NARRATION")
        from app.services.ava_offline_access_policy import (
            AvaOfflineAccessPolicy, OfflineAccessAuthority, OfflineContextType,
        )
        offline_policy = AvaOfflineAccessPolicy()
        offline_data = dict(diagnostics.get("offlineAccessAuthority")
                            or diagnostics.get("offline_access_authority") or {})
        try:
            context_type = OfflineContextType(
                offline_data.get("offlineContextType") or "NO_OFFLINE_CONTEXT")
        except ValueError:
            context_type = OfflineContextType.NO_OFFLINE_CONTEXT
        if not offline_data:
            offline_authority = offline_policy.classify(
                customer_text, recent_history=recent_context)
        else:
            offline_authority = OfflineAccessAuthority(
                context_type=context_type,
                boundary_required=bool(offline_data.get("boundaryRequired")),
                evidence=tuple(offline_data.get("evidence") or ()),
            )
        offline_reasons = offline_policy.candidate_violation_reasons(
            final_text, authority=offline_authority, customer_text=customer_text,
        )
        reasons.update(offline_reasons)
        offline_validation = {
            **offline_authority.diagnostics(),
            "offlineExpectationViolation": bool(offline_reasons),
            "offlineQualityReason": (
                "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION"
                if offline_reasons else None),
            "finalOfflineAccessDisposition": (
                "BLOCKED_BEFORE_DELIVERY" if offline_reasons else "ALLOWED"
            ),
        }
        diagnostics["offlineAccessValidation"] = offline_validation
        # ``diagnostic_metadata`` is the operation-bound mutable projection at
        # this boundary. Persist the bounded result with the candidate so resume
        # and pre-send authorization can prove what was validated.
        result.diagnostic_metadata["offlineAccessValidation"] = offline_validation
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
        from app.services.ordinary_quality_rejection import PROGRESSION_REASONS
        blocking = tuple(sorted(reasons.intersection(self.BLOCKING_REASONS | PROGRESSION_REASONS)))
        return DeliveryQualityDecision(
            allowed=not blocking, reasons=blocking,
            disposition="ALLOWED" if not blocking else "BLOCKED_BEFORE_DELIVERY",
        )

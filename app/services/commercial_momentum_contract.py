"""Current-turn evidence bridge; Sales Brain alone owns commercial authority."""
from hashlib import sha256

from app.services.conversation_momentum_strategy import ConversationMomentumStrategy


class CommercialMomentumContract:
    VERSION = "COMMERCIAL_MOMENTUM_V1"

    @staticmethod
    def message_digest(message):
        return sha256(str(message or "").encode("utf-8")).hexdigest()

    @classmethod
    def current_evidence(cls, context):
        heat = dict(context.get("customer_heat_signal") or {})
        classifier = dict(context.get("classifier_result") or {})
        recent = [str(row.get("content") or "") for row in context.get("recent_transcript") or ()
                  if isinstance(row, dict) and row.get("role") == "assistant"]
        plan = ConversationMomentumStrategy.plan(str(context.get("latest_message") or ""),
            evidence={"heat": heat.get("strength"), "classifier": classifier,
                      "backoff": str((context.get("sales_progression") or {}).get("phase")) == "BACK_OFF"},
            recent=recent)
        return {"version": cls.VERSION, "turnId": context.get("commercial_turn_id"),
                "messageDigest": cls.message_digest(context.get("latest_message")),
                "currentHeat": heat.get("strength", "NONE"), "heatType": heat.get("type"),
                "currentTurn": heat.get("currentTurn") is True,
                "customerInitiation": heat.get("initiationSource"),
                "customerEscalation": heat.get("initiationSource") == "CUSTOMER_ESCALATED",
                "semanticEngagement": classifier.get("sexual_engagement") is True,
                "escalationReady": classifier.get("escalation_ready") is True,
                "momentumIntent": plan["momentumIntent"],
                "authority": "CURRENT_SALES_BRAIN_EVALUATION"}

    @classmethod
    def preserves_hot_presentation(cls, decision, gateway_input, preliminary):
        """Recognize a completed current decision, never promote heat into a sale."""
        if (decision.decision.value != "PRESENT_OFFER" or not decision.sell_allowed
                or decision.recommended_offering_id is None
                or decision.active_purchase_intent_id is not None
                or preliminary.get("no_buy_boundary") is True
                or preliminary.get("temporal_deferred") is True):
            return False
        metadata = dict(decision.decision_metadata or {})
        evidence = dict(metadata.get("currentTurnCommercialEvidence") or {})
        hot = dict(metadata.get("proactiveHotOpportunity") or {})
        heat = dict(hot.get("customerHeatSignal") or {})
        return bool(
            evidence.get("version") == cls.VERSION
            and evidence.get("authority") == "CURRENT_SALES_BRAIN_EVALUATION"
            and evidence.get("turnId")
            and evidence["turnId"] == getattr(gateway_input, "correlation_id", None)
            and evidence.get("messageDigest") == cls.message_digest(getattr(gateway_input, "message_text", ""))
            and hot.get("authority") == "CUSTOMER_SALES_BRAIN_CANONICAL_HOT_OPPORTUNITY"
            and hot.get("proactiveHotOpportunityAuthorized") is True
            and hot.get("commercialSafeguardsPassed") is True
            and not hot.get("hotOpportunityBlockers")
            and heat.get("currentTurn") is True and heat.get("strength") == "STRONG"
            and heat.get("warmupOverrideEligible") is True
            and heat.get("initiationSource") in {"CUSTOMER_INITIATED", "CUSTOMER_ESCALATED"})

    @classmethod
    def observation(cls, decision, *, offer_authorized=False, blocked=False):
        if decision is None:
            return {"version": cls.VERSION, "commercialEvaluationTriggered": False,
                    "presentOfferConsidered": False, "finalDecision": "UNAVAILABLE",
                    "blockers": ["CANONICAL_DECISION_UNAVAILABLE"], "actionOwner": "ORDINARY"}
        metadata = dict(decision.decision_metadata or {})
        evidence = dict(metadata.get("currentTurnCommercialEvidence") or {})
        hot = dict(metadata.get("proactiveHotOpportunity") or {})
        consistency = dict(metadata.get("commercialAuthorityConsistency") or {})
        phase = str((metadata.get("salesProgression") or {}).get("phase") or "CONVERSATIONAL")
        actual = decision.decision.value
        owns = bool(offer_authorized and not blocked)
        blockers = [] if owns else list(hot.get("hotOpportunityBlockers") or ())
        if not owns:
            blockers.append(str(consistency.get("reason") or decision.reason_code.value))
        if blocked:
            blockers.append("CURRENT_ACTION_BLOCKED")
        return {**evidence, "version": cls.VERSION, "commercialEvaluationTriggered": True,
                "progressionPhase": phase,
                "presentOfferConsidered": bool(actual == "PRESENT_OFFER" or phase == "PRESENT_OFFER"
                    or consistency.get("requestedDecision") == "PRESENT_OFFER"
                    or hot.get("proactiveHotOpportunityAuthorized")),
                "finalDecision": actual, "blockers": list(dict.fromkeys(blockers)),
                "selectedOffering": str(decision.recommended_offering_id) if owns and decision.recommended_offering_id else None,
                "actionOwner": "CANONICAL_OFFER_PRESENTATION" if owns else "NONE" if blocked else "ORDINARY",
                "ordinaryPreludeAllowed": False if owns else None,
                "authority": "CUSTOMER_SALES_BRAIN"}

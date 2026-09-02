"""Single canonical receptiveness policy for ordinary Sales Brain turns."""
from __future__ import annotations

import re

from app.models.commercial_receptiveness import (
    CommercialReceptiveness,
    CommercialReceptivenessState,
)


class CommercialReceptivenessService:
    """Consolidate bounded message, classifier, purchase and pressure evidence."""

    CONTINUATION_PATTERN = re.compile(
        r"\b(?:another|more|next(?:\s+one)?|what\s+else|anything\s+else|"
        r"something\s+(?:hotter|else)|got\s+anything\s+hotter|keep\s+going|"
        r"don(?:'|.)t\s+stop|keep\s+(?:this\s+)?going|keep\s+showing|"
        r"what\s+comes\s+next|take\s+me\s+through|whole\s+(?:thing|sequence))\b",
        re.I,
    )
    POSITIVE_PATTERN = re.compile(
        r"\b(?:damn|wow|hot|love(?:d)?\s+(?:it|that)|that(?:'|.)s\s+(?:hot|amazing)|"
        r"so\s+good|need\s+to\s+see|keep\s+going)\b", re.I,
    )
    NEUTRAL_EXIT_PATTERN = re.compile(
        r"\b(?:anyway|heading\s+to\s+work|gotta\s+go|talk\s+later|goodnight|"
        r"thanks(?:\s+(?:anyway|though))?)\b", re.I,
    )
    ACTIVE_OFFER_CONTINUATION_PATTERNS = (
        ("PRICE_REQUEST", re.compile(
            r"\b(?:how much|what(?:'s| is) the price|what does it cost|price)\b",
            re.I,
        )),
        ("SEND_OR_LINK_REQUEST", re.compile(
            r"\b(?:send(?:\s+me)?(?:\s+(?:it|that|the\s+link))?|"
            r"(?:where(?:'s| is)|give me)\s+(?:the\s+)?link|"
            r"where\s+do\s+i\s+unlock|let\s+me\s+(?:get|unlock)\s+(?:it|that)|"
            r"i\s+want\s+(?:it|that)|show\s+me)\b",
            re.I,
        )),
    )
    INTEREST_PATTERNS = (
        ("PURCHASE_ACCEPTANCE", re.compile(
            r"\b(?:i(?:'ll| will)\s+(?:buy|take|get)\s+(?:it|that)|"
            r"i(?:'m| am)\s+ready\s+to\s+(?:buy|unlock)|deal|sold)\b", re.I)),
        ("SEND_OR_LINK_REQUEST", ACTIVE_OFFER_CONTINUATION_PATTERNS[1][1]),
        ("PRICE_REQUEST", ACTIVE_OFFER_CONTINUATION_PATTERNS[0][1]),
        ("DIRECT_CONTENT_INTENT", re.compile(
            r"\b(?:show me (?:your|the|what)|want to see|let me see|"
            r"what (?:content|pics|videos|sets) do you have|unlock something)\b", re.I)),
        ("COMMERCIAL_CURIOSITY", re.compile(
            r"\b(?:what are you (?:selling|offering)|got anything (?:special|private)|"
            r"what(?:'s| is) behind (?:the|your) (?:paywall|unlock)|curious about your content|"
            r"(?:i(?:'m| am) )?curious(?:\b|\s+about)|tell me (?:a |some )?(?:little |bit )?more|"
            r"what (?:did you mean|were you teasing|are you teasing)|"
            r"what(?:'s| is) (?:the )?(?:tease|hint))\b", re.I)),
    )

    def __init__(self, direct_intent_detector):
        self.direct_intent_detector = direct_intent_detector

    @classmethod
    def explicit_continuation_detected(cls, message: str) -> bool:
        return bool(cls.CONTINUATION_PATTERN.search(str(message or "")))

    def evaluate(self, *, context: dict | None, recent_purchase: bool,
                 cooldown_active: bool, readiness: dict | None = None,
                 active_offer: bool = False) -> CommercialReceptiveness:
        values = dict(context or {})
        flags = dict(readiness or {})
        message = str(values.get("latest_message") or "")
        commercial_interest_type = self.commercial_interest_type(message)
        direct = bool(self.direct_intent_detector(message))
        active_offer_continuation = (
            self.active_offer_continuation_type(message)
            if active_offer else None
        )
        direct = direct or active_offer_continuation is not None
        continuation = self.explicit_continuation_detected(message)
        deferred = dict(values.get("deferred_continuation") or {})
        deferred_ready = bool(
            deferred.get("state") == "READY"
            or (
                deferred.get("state") == "CLAIMED"
                and str(deferred.get("claimCorrelationId") or "")
                == str(values.get("conversation_id") or "")
            )
        )
        if deferred_ready:
            continuation = True
            direct = True
        positive_turn = bool(self.POSITIVE_PATTERN.search(message))
        action = str(flags.get("recommended_conversational_action") or "").upper()
        # A request to continue talking ("tell me a little more") is not by
        # itself an actionable request to buy, unlock, receive, or price
        # content. It only inherits direct continuation authority inside a
        # verified post-purchase buying window; deterministic direct/link/price
        # patterns remain authoritative everywhere.
        direct = direct or (continuation and recent_purchase) or bool(
            flags.get("current_buying_intent") is True
            or flags.get("classifier_buying_intent") is True
            or flags.get("classifier_close_ready") is True
            or action == "PRESENT_OFFER"
        )
        curiosity = commercial_interest_type == "COMMERCIAL_CURIOSITY"
        positive_turn = positive_turn or curiosity or bool(
            flags.get("escalation_ready") is True
            or flags.get("positive_tease_response") is True
            or str(flags.get("engagement_level") or "").lower() == "high"
            or str(flags.get("buyer_likelihood") or "").lower() == "high"
        )
        back_off = bool(
            action == "BACK_OFF"
            or values.get("offer_declined") is True
        )
        if not back_off:
            back_off = bool(re.search(
                r"\b(?:no|nah|stop|not\s+interested|don(?:'|.)t\s+want|maybe\s+later)\b",
                message, re.I,
            ))
        neutral_exit = bool(self.NEUTRAL_EXIT_PATTERN.search(message))

        positive: list[str] = []
        resistance: list[str] = []
        pressure: list[str] = []
        strength = 0
        if direct:
            positive.append("FRESH_DIRECT_BUYING_INTENT")
            strength += 75
        if continuation:
            positive.append("EXPLICIT_CONTINUATION_REQUEST")
            strength += 20
        if positive_turn:
            positive.append("STRONG_POSITIVE_ENGAGEMENT")
            strength += 30
        if recent_purchase:
            positive.append("RECENT_VERIFIED_PURCHASE")
            strength += 20
        if active_offer:
            pressure.append("ACTIVE_PURCHASE_INTENT")
        if cooldown_active:
            pressure.append("PURCHASE_COOLDOWN_ACTIVE")
        if neutral_exit:
            resistance.append("NEUTRAL_SUBJECT_EXIT")
        if back_off:
            resistance.append("CURRENT_DECLINE_OR_BACK_OFF")

        if back_off:
            state = CommercialReceptivenessState.BACK_OFF
            appropriate = False
            reason = "CURRENT_RESISTANCE_TAKES_PRECEDENCE"
        elif neutral_exit or (recent_purchase and not direct and not positive_turn):
            state = CommercialReceptivenessState.COOLING
            appropriate = False
            reason = "RECENT_PURCHASE_WITHOUT_FRESH_COMMERCIAL_EVIDENCE"
        elif direct or (recent_purchase and positive_turn):
            state = CommercialReceptivenessState.HOT
            appropriate = direct
            reason = (
                "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN"
                if cooldown_active and direct else
                "STRONG_CURRENT_COMMERCIAL_EVIDENCE"
            )
        elif positive_turn or strength >= 25:
            state = CommercialReceptivenessState.WARM
            appropriate = False
            reason = "POSITIVE_EVIDENCE_SUPPORTS_COMMERCIAL_NURTURE"
        else:
            state = CommercialReceptivenessState.COLD
            appropriate = False
            reason = "NO_CURRENT_COMMERCIAL_EVIDENCE"

        eligible = state in {
            CommercialReceptivenessState.HOT,
            CommercialReceptivenessState.WARM,
        } and not back_off
        return CommercialReceptiveness(
            state=state, strength=min(100, strength),
            positive_evidence=tuple(positive),
            resistance_evidence=tuple(resistance),
            pressure_evidence=tuple(pressure), fresh_direct_intent=direct,
            recent_purchase=recent_purchase, continuation_eligible=eligible,
            another_sale_appropriate_now=appropriate,
            reason=reason,
            commercial_interest_type=commercial_interest_type,
        )

    @classmethod
    def commercial_interest_type(cls, message: str) -> str:
        for interest_type, pattern in cls.INTEREST_PATTERNS:
            if pattern.search(str(message or "")):
                return interest_type
        return "NONE"

    @classmethod
    def active_offer_continuation_type(cls, message: str) -> str | None:
        for continuation_type, pattern in cls.ACTIVE_OFFER_CONTINUATION_PATTERNS:
            if pattern.search(str(message or "")):
                return continuation_type
        return None

    @staticmethod
    def refine_projection(existing: dict | None, readiness: dict | None) -> dict:
        """Merge provider classifier evidence into the same canonical result."""
        result = dict(existing or {})
        flags = dict(readiness or {})
        positive = list(result.get("positiveEvidence") or ())
        action = str(flags.get("recommended_conversational_action") or "").upper()
        direct = bool(
            result.get("freshDirectIntentDetected")
            or (
                result.get("commercialInterestType") != "COMMERCIAL_CURIOSITY"
                and (
                    flags.get("current_buying_intent") is True
                    or flags.get("classifier_buying_intent") is True
                    or flags.get("classifier_close_ready") is True
                    or action == "PRESENT_OFFER"
                )
            )
        )
        strong = bool(
            flags.get("escalation_ready") is True
            or flags.get("positive_tease_response") is True
            or str(flags.get("engagement_level") or "").lower() == "high"
            or str(flags.get("buyer_likelihood") or "").lower() == "high"
        )
        back_off = action == "BACK_OFF"
        recent = bool(result.get("recentPurchaseDetected"))
        if direct and "FRESH_DIRECT_BUYING_INTENT" not in positive:
            positive.append("FRESH_DIRECT_BUYING_INTENT")
        if strong and "STRONG_POSITIVE_ENGAGEMENT" not in positive:
            positive.append("STRONG_POSITIVE_ENGAGEMENT")
        if back_off:
            result.update({
                "state": "BACK_OFF", "continuationEligible": False,
                "anotherSaleAppropriateNow": False,
                "reason": "CURRENT_RESISTANCE_TAKES_PRECEDENCE",
            })
        elif direct:
            result.update({
                "state": "HOT", "continuationEligible": True,
                "anotherSaleAppropriateNow": True,
                "reason": (
                    "FRESH_DIRECT_INTENT_OVERRIDES_DEFAULT_COOLDOWN"
                    if "PURCHASE_COOLDOWN_ACTIVE" in tuple(
                        result.get("pressureEvidence") or ()
                    ) else "STRONG_CURRENT_COMMERCIAL_EVIDENCE"
                ),
            })
        elif recent and strong:
            result.update({
                "state": "HOT", "continuationEligible": True,
                "anotherSaleAppropriateNow": False,
                "reason": "STRONG_CURRENT_COMMERCIAL_EVIDENCE",
            })
        elif strong and result.get("state") not in {"BACK_OFF", "COOLING"}:
            result.update({
                "state": "WARM", "continuationEligible": True,
                "reason": "POSITIVE_EVIDENCE_SUPPORTS_COMMERCIAL_NURTURE",
            })
        result["positiveEvidence"] = positive
        result["freshDirectIntentDetected"] = direct
        result.setdefault("commercialInterestType", "NONE")
        return result

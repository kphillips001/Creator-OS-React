"""Deterministic WHEN/HOW policy applied after canonical opportunity selection."""
from __future__ import annotations

import re
from dataclasses import replace

from app.models.customer_sales_decision import (
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)


class ConversationalSalesProgressionService:
    """Bounded per-opportunity progression; never selects or fulfills products."""

    DIRECT_PATTERNS = tuple(re.compile(value, re.I) for value in (
        r"\b(?:send|show|give)\s+(?:me\s+)?(?:it|that|(?:a|the)\s+(?:pic|picture|photo|image|set)|more)\b",
        r"\b(?:okay|ok|alright|fine)[,!\s]+(?:send|show|give)\s+me\b",
        r"\b(?:send|show|give)\s+me\s+(?:.{0,40}\s)?(?:pic|picture|photo|image|set)\b",
        r"^\s*(?:send|show|give)\s+me\s*[.!?]*$",
        r"\b(?:send|show|give)\s+me\s+(?:something|anything)\b",
        r"\bshow\s+me\s+what\s+(?:you['\u2019]ve\s+got|you\s+(?:have|got))\b",
        r"\b(?:show|send|give)\s+me\s+(?:the\s+)?(?:private\s+one|good\s+stuff)\b",
        r"\bwhat\s+do\s+i\s+get\b",
        r"\bwhat\s+(?:can\s+i\s+buy|do\s+you\s+have)\b",
        r"\bwhat\s+can\s+i\s+unlock\b",
        r"\bwhat\s+(?:private\s+)?(?:sets?|content)\s+do\s+you\s+have\b",
        r"\bdo\s+you\s+have\s+(?:anything|something)\s+(?:i\s+can\s+)?unlock\b",
        r"\b(?:got|have)\s+(?:anything|something)\s+i\s+can\s+unlock\b",
        r"\bwhere\s+can\s+i\s+get\s+more\b",
        r"\bi(?:'|\u2019)ll\s+buy\s+(?:it|that|one)\b",
        r"\b(?:i\s+want|i(?:'|’)ll\s+take|let\s+me\s+(?:see|have)|where\s+(?:do\s+i|can\s+i)\s+(?:buy|get|unlock))\b",
        r"\b(?:how\s+much|what(?:'|’)s\s+the\s+(?:price|cost)|price\?|cost\?)",
        r"\b(?:whole|full|complete|entire)\s+(?:thing|set)\b",
        r"\b(?:next\s+one|next\s+unlock)\b",
        r"\b(?:send|show|give)\s+me\s+another\b",
        r"\b(?:show|send|give)\s+me\s+more\b",
        r"\bwhat\s+else\s+do\s+you\s+have\b",
        r"\b(?:got|have)\s+anything\s+hotter\b",
        r"^\s*more\s*[.!?]*$",
        r"\banything\s+hotter\b",
        r"\bi\s+want\s+another\b",
        r"\bhow\s+do\s+i\s+(?:buy|get|unlock)\s+(?:it|that)\b",
    ))
    PRICE_PATTERN = re.compile(r"\b(?:how\s+much|price|cost)\b", re.I)
    NEGATIVE_PATTERN = re.compile(
        r"\b(?:no|nah|not\s+(?:now|interested)|stop|don(?:'|’)t\s+want|leave\s+it|maybe\s+later)\b",
        re.I,
    )
    HESITATION_PATTERN = re.compile(
        r"\b(?:too\s+expensive|can(?:'|’)t\s+afford|maybe|later|not\s+sure|hesitant)\b",
        re.I,
    )
    # Standalone playful ambiguity ("maybe") is not a commercial objection.
    HESITATION_PATTERN = re.compile(
        r"\b(?:too\s+expensive|can(?:'|.)t\s+afford|maybe\s+(?:later|another\s+time|not)|later|not\s+sure|hesitant)\b",
        re.I,
    )
    POSITIVE_TEASE_PATTERNS = tuple(re.compile(value, re.I) for value in (
        r"\b(?:yes|yeah|yep|definitely|interested|intrigued|curious)\b",
        r"\b(?:have|got|caught|grabbed)\s+(?:my\s+)?attention\b",
        r"\b(?:give|tell)\s+me\s+(?:a\s+|another\s+|little\s+)?hint\b",
        r"\b(?:tell\s+me\s+more|keep\s+going|go\s+on)\b",
        r"\b(?:tell|give)\s+me\s+(?:(?:a|some)\s+)?(?:little|bit)\s+more\b",
    ))
    REVEAL_REQUEST_PATTERNS = tuple(re.compile(value, re.I) for value in (
        r"\bwhat\s+(?:is|was)\s+it\b",
        r"\bwhat\s+(?:exactly\s+)?(?:are|were)\s+you\s+(?:teasing|hinting|talking)(?:\s+(?:me\s+)?about|\s+at)?\b",
        r"\b(?:you(?:'|’)?ve\s+)?teased\s+me\s+enough\b",
        r"\benough\s+(?:with\s+the\s+)?teasing\b",
        r"\b(?:reveal|show|tell)\s+me\s+what\s+(?:you['\u2019]ve\s+(?:actually\s+)?got|you\s+(?:have|got|mean))\b",
        r"\b(?:reveal|show|tell)(?:\s+me)?\s+what\s+you(?:['\u2019]re|\s+are|\s+were)\s+(?:teasing|hinting)(?:\s+(?:me|at))?\b",
        r"\blet\s+me\s+see\s+what\s+you\s+mean\b",
    ))
    MAX_TEASE_TURNS = 2

    CONVERSATIONAL_ACTIONS = frozenset({
        "CHAT", "FLIRT", "TEASE_OFFER", "PRESENT_OFFER", "BACK_OFF",
    })

    _RELATIONAL_WARMTH_PATTERNS = tuple(re.compile(value, re.I) for value in (
        r"\b(?:you\s+(?:seem|are|look)|talking (?:to|with) (?:a )?)\b.{0,20}\b(?:cute|sweet|pretty|beautiful)\b",
        r"\b(?:like|love|enjoy)(?:d|ing)?\b.{0,24}\b(?:talking|chatting|time with you)\b",
        r"\b(?:easy|comfortable|fun|nice)\b.{0,24}\b(?:talk|chat|with you)\b",
        r"\b(?:opened|opening|warmed|warming)\s+up\b",
        r"\b(?:lost track of time|still (?:talking|chatting)|kept me (?:talking|chatting))\b",
        r"\byou\s+(?:actually\s+)?remember(?:ed)?\b.{0,32}\b(?:cute|sweet|thoughtful)\b",
    ))

    @classmethod
    def relationship_warming_evidence(cls, messages) -> dict[str, object]:
        """Project generalized, non-commercial rapport evidence.

        This classifier deliberately does not infer buying intent and does not
        inspect scenario identifiers or turn numbers. It only summarizes the
        customer's voluntary relationship signals across the supplied history.
        """
        values = [str(item or "").strip() for item in tuple(messages or ())]
        values = [item for item in values if item]
        matching_turns = sum(
            1 for item in values
            if any(pattern.search(item) for pattern in cls._RELATIONAL_WARMTH_PATTERNS)
        )
        low_return_turns = sum(
            1 for item in values
            if len(re.findall(r"[A-Za-z0-9']+", item)) <= 7
            and not any(pattern.search(item) for pattern in cls._RELATIONAL_WARMTH_PATTERNS)
            and not any(pattern.search(item) for pattern in cls.DIRECT_PATTERNS)
        )
        return {
            "voluntaryCustomerTurnCount": len(values),
            "relationalWarmthTurnCount": matching_turns,
            "reciprocalWarmingObserved": matching_turns >= 2,
            "lowConversationalReturnCount": low_return_turns,
        }

    def has_direct_purchase_intent(self, message: str) -> bool:
        """Expose the existing authoritative matcher without duplicating phrases."""
        return any(pattern.search(str(message or "")) for pattern in self.DIRECT_PATTERNS)

    @classmethod
    def recommended_conversational_action(
        cls, message: str, classifier_result: dict | None,
        explicit_profile: dict | None = None,
    ) -> str:
        """Normalize model semantics into a bounded timing recommendation.

        This recommendation never selects an offering or authorizes commerce.
        Deterministic safety and eligibility remain downstream authority.
        """
        text = str(message or "")
        classifier = dict(classifier_result or {})
        explicit = dict(explicit_profile or {})
        if cls.NEGATIVE_PATTERN.search(text) or cls.HESITATION_PATTERN.search(text):
            return "BACK_OFF"
        if explicit.get("suppress_sales_pressure") is True:
            return "FLIRT" if explicit.get("explicit_requested") else "CHAT"
        recommended = str(classifier.get("recommended_action") or "").lower()
        direct = any(pattern.search(text) for pattern in cls.DIRECT_PATTERNS)
        if (
            direct
            or classifier.get("buying_intent") is True
            or classifier.get("close_ready") is True
            or recommended in {"offer", "close", "custom_request"}
            or str(classifier.get("user_state") or "").lower()
            in {"ready_to_buy", "converted"}
        ):
            return "PRESENT_OFFER"
        features = cls.transition_features(text)
        if (
            features["reveal_request"]
            and (
                classifier.get("escalation_ready") is True
                or str(classifier.get("buyer_likelihood") or "").lower() == "high"
                or str(classifier.get("curiosity_level") or "").lower() == "high"
            )
        ):
            return "PRESENT_OFFER"
        if (
            recommended == "build_tension"
            or features["positive_tease_response"]
            or str(classifier.get("curiosity_level") or "").lower() in {"medium", "high"}
        ):
            return "TEASE_OFFER"
        if (
            classifier.get("sexual_engagement") is True
            or str(classifier.get("route") or "").lower() == "flirt"
        ):
            return "FLIRT"
        return "CHAT"

    @classmethod
    def transition_features(cls, message: str) -> dict[str, bool]:
        """Extract bounded current-turn concepts without persisting classifier truth."""
        text = str(message or "")
        direct_request = any(pattern.search(text) for pattern in cls.DIRECT_PATTERNS)
        positive = any(
            pattern.search(text) for pattern in cls.POSITIVE_TEASE_PATTERNS
        ) or bool(__import__("re").search(
            r"\b(?:what kind of trouble|what trouble|bring it out of me|"
            r"you(?:'re| are) (?:kinda |kind of )?trouble)\b", text,
            __import__("re").I,
        ))
        reveal = any(
            pattern.search(text) for pattern in cls.REVEAL_REQUEST_PATTERNS
        )
        return {
            "content_request": direct_request,
            "positive_tease_response": positive or reveal,
            "reveal_request": reveal,
            "sustained_interest": positive or reveal,
            "commercial_response_interest": positive or reveal,
            "commercial_response_interest_meaning": (
                "POSITIVE_RESPONSE_TO_TEASE_OR_REVEAL_REQUEST"
            ),
        }

    def back_off_reason(self, context: dict | None):
        values = dict(context or {})
        state = dict(values.get("sales_progression") or {})
        if str(state.get("phase") or "").upper() not in {
            "TEASE", "BUILD_INTEREST",
        }:
            return None
        message = str(values.get("latest_message") or "")
        if self.NEGATIVE_PATTERN.search(message):
            return CustomerSalesReasonCode.CUSTOMER_DECLINED
        if self.HESITATION_PATTERN.search(message):
            return CustomerSalesReasonCode.CUSTOMER_HESITATION
        return None

    def refine(
        self, decision: CustomerSalesDecision, context: dict | None,
    ) -> CustomerSalesDecision:
        if (
            decision.recommended_offering_id is None
            or decision.decision is not CustomerSalesDecisionType.PRESENT_OFFER
        ):
            return decision
        values = dict(context or {})
        if values.get("critical_grounding_available") is False:
            return self._without_offer(
                decision, CustomerSalesDecisionType.NO_SALE,
                CustomerSalesReasonCode.INSUFFICIENT_GROUNDING,
                "Critical canonical product grounding is unavailable.",
                phase="CONVERSATIONAL", tease_count=0,
            )
        message = str(values.get("latest_message") or "").strip()
        features = self.transition_features(message)
        state = dict(values.get("sales_progression") or {})
        previous = str(state.get("phase") or "CONVERSATIONAL").upper()
        previous_offering = str(state.get("offeringId") or "")
        same_opportunity = previous_offering == str(decision.recommended_offering_id)
        tease_count = int(state.get("teaseCount") or 0) if same_opportunity else 0

        if self.NEGATIVE_PATTERN.search(message):
            return self._without_offer(
                decision, CustomerSalesDecisionType.BACK_OFF,
                CustomerSalesReasonCode.CUSTOMER_DECLINED,
                "Customer declined or deferred the sales opportunity.",
                phase="BACK_OFF", tease_count=tease_count,
            )
        if self.HESITATION_PATTERN.search(message):
            return self._without_offer(
                decision, CustomerSalesDecisionType.BACK_OFF,
                CustomerSalesReasonCode.CUSTOMER_HESITATION,
                "Customer hesitation requires reduced sales pressure.",
                phase="BACK_OFF", tease_count=tease_count,
            )
        customer_led_continuation = bool(dict(
            values.get("active_buying_window") or {}
        ).get("anotherSaleAppropriateNow"))
        if self.has_direct_purchase_intent(message) or customer_led_continuation:
            reason = (
                CustomerSalesReasonCode.PRICE_REQUEST
                if self.PRICE_PATTERN.search(message)
                else CustomerSalesReasonCode.SESSION_NEXT_UNLOCK_REQUEST
                if re.search(r"\bnext\b", message, re.I)
                else CustomerSalesReasonCode.DIRECT_PURCHASE_INTENT
            )
            return replace(
                decision, reason_code=reason,
                reason_summary="Strong purchase intent authorizes the deterministic offer now.",
                decision_metadata=self._metadata(
                    decision, "PRESENT_OFFER", tease_count, reason.value,
                    prior_phase=previous,
                    transition_signal="DIRECT_PURCHASE_INTENT",
                ),
            )
        if same_opportunity and previous in {"TEASE", "BUILD_INTEREST"}:
            if features["positive_tease_response"]:
                if (
                    previous == "BUILD_INTEREST"
                    or tease_count >= self.MAX_TEASE_TURNS
                ):
                    return replace(
                        decision,
                        reason_code=CustomerSalesReasonCode.PRESENT_AFTER_POSITIVE_TEASE_RESPONSE,
                        reason_summary="Positive response to bounded product-grounded teasing authorizes the offer.",
                        decision_metadata=self._metadata(
                            decision, "PRESENT_OFFER", tease_count,
                            "PRESENT_AFTER_POSITIVE_TEASE_RESPONSE",
                            prior_phase=previous,
                            transition_signal=(
                                "REVEAL_REQUEST"
                                if features["reveal_request"]
                                else "SUSTAINED_INTEREST"
                            ),
                        ),
                    )
                return self._without_offer(
                    decision, CustomerSalesDecisionType.BUILD_INTEREST,
                    CustomerSalesReasonCode.BUILD_INTEREST,
                    "Positive response advances product-grounded anticipation.",
                    phase="BUILD_INTEREST", tease_count=tease_count + 1,
                    prior_phase=previous,
                    transition_signal="POSITIVE_TEASE_RESPONSE",
                )
            if tease_count >= self.MAX_TEASE_TURNS:
                return self._without_offer(
                    decision, CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                    CustomerSalesReasonCode.TEASE_LIMIT_REACHED,
                    "Bounded tease limit reached without stronger intent.",
                    phase="CONVERSATIONAL", tease_count=tease_count,
                )
            return self._without_offer(
                decision, CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesReasonCode.WEAK_INTEREST_RESPONSE,
                "Weak response does not authorize a paid offer.",
                phase=previous, tease_count=tease_count,
            )
        if same_opportunity and previous == "BACK_OFF":
            return self._without_offer(
                decision, CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                CustomerSalesReasonCode.BACK_OFF,
                "Recent back-off suppresses immediate renewed sales pressure.",
                phase="CONVERSATIONAL", tease_count=tease_count,
            )
        return self._without_offer(
            decision, CustomerSalesDecisionType.TEASE,
            CustomerSalesReasonCode.TEASE_RELEVANT_OPPORTUNITY,
            "A relevant grounded opportunity exists, but purchase intent is not yet strong.",
            phase="TEASE", tease_count=1,
        )

    @classmethod
    def _without_offer(cls, decision, decision_type, reason, summary, *, phase,
                       tease_count, prior_phase=None, transition_signal=None):
        return replace(
            decision, decision=decision_type, reason_code=reason,
            reason_summary=summary, sell_allowed=False, nudge_allowed=False,
            decision_metadata=cls._metadata(
                decision, phase, tease_count, reason.value,
                prior_phase=prior_phase,
                transition_signal=transition_signal,
            ),
        )

    @staticmethod
    def _metadata(decision, phase, tease_count, reason_code, *,
                  prior_phase=None, transition_signal=None):
        prior = prior_phase or dict(
            dict(decision.decision_metadata or {}).get("salesProgression") or {}
        ).get("phase") or "CONVERSATIONAL"
        tease_type = "OPPORTUNITY_GROUNDED" if phase == "TEASE" else None
        return immutable_mapping({
            **dict(decision.decision_metadata),
            "salesProgression": {
                "phase": phase,
                "reasonCode": reason_code,
                "offeringId": str(decision.recommended_offering_id),
                "teaseCount": int(tease_count),
                "teaseType": tease_type,
            },
            "teaseType": tease_type,
            "salesProgressionTransition": {
                "priorPhase": str(prior).upper(),
                "transitionSignal": transition_signal or "NONE",
                "nextPhase": phase,
            },
        })

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
        r"don(?:'|.)t\s+stop|keep\s+(?:(?:this|the\s+session)\s+)?going|keep\s+showing|"
        r"what\s+comes\s+next|take\s+me\s+through|whole\s+(?:thing|sequence))\b",
        re.I,
    )
    INVENTORY_EXISTENCE_QUESTION_PATTERN = re.compile(
        r"\b(?:got|have|is there|are there|do you have)\b.{0,40}"
        r"\b(?:anything|something|more|new|else|stuff|content)\b|"
        r"\b(?:anything|something)\s+i\s+haven['’]?t\s+"
        r"(?:seen|bought|unlocked)\b|\bis\s+there\s+anything\s+else\b",
        re.I,
    )
    INVENTORY_ACTION_OR_COMPARISON_PATTERN = re.compile(
        r"\b(?:show|send|drop|share|link|how much|price|cost|range|"
        r"smaller|cheaper|lower-priced|similar)\b",
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
            r"i\s+want\s+(?:it|that)|show\s+me|"
            r"(?:send|give)(?:\s+me)?\s+(?:that|this|the)\s+"
            r"(?:one|option|cheaper\s+(?:one|option)|smaller\s+(?:one|option)|"
            r"other\s+(?:one|option)|\$?\d+(?:\.\d{1,2})?\s+(?:one|option))|"
            r"i(?:'|.)ll\s+take\s+(?:that|this|the)\s+"
            r"(?:one|option|cheaper\s+(?:one|option)|smaller\s+(?:one|option)|"
            r"\$?\d+(?:\.\d{1,2})?\s+(?:one|option))|"
            r"i\s+want\s+(?:the\s+)?(?:cheaper|smaller|\$?\d+(?:\.\d{1,2})?)\s+"
            r"(?:one|option)(?:\s+you\s+(?:showed|sent)(?:\s+me)?)?)\b",
            re.I,
        )),
    )
    FRESH_COMPARATIVE_PRICE_PATTERN = re.compile(
        r"\b(?:anything|something)\s+(?:even\s+)?cheaper\s+than\b|"
        r"\b(?:anything|something)\s+(?:even\s+)?cheaper\b|"
        r"\b(?:can\s+you\s+go|go)\s+lower\b|"
        r"\b(?:anything|something)\s+(?:under|below|less\s+than)\s+\$?\d|"
        r"\b(?:that|this|it)\s+(?:is|(?:'|.)s)\s+still\s+(?:too\s+much|too\s+expensive)\b|"
        r"\beven\s+cheaper\b",
        re.I,
    )
    INTEREST_PATTERNS = (
        ("PURCHASE_ACCEPTANCE", re.compile(
            r"\b(?:i(?:'ll| will)\s+(?:buy|take|get)\s+(?:it|that)|"
            r"i(?:'m| am)\s+ready\s+to\s+(?:buy|unlock)|deal|sold)\b", re.I)),
        ("SEND_OR_LINK_REQUEST", ACTIVE_OFFER_CONTINUATION_PATTERNS[1][1]),
        ("PRICE_REQUEST", ACTIVE_OFFER_CONTINUATION_PATTERNS[0][1]),
        ("DIRECT_CONTENT_INTENT", re.compile(
            r"\b(?:show me (?:your|the|what)|want to see|let me see|"
            r"what (?:content|pics|videos|sets) do you have|unlock something|"
            r"i(?:'m| am) looking to buy something|"
            r"i(?:'m| am) ready for (?:the )?(?:finale|final (?:part|step)))\b",
            re.I)),
        ("COMMERCIAL_CURIOSITY", re.compile(
            r"\b(?:what are you (?:selling|offering)|got anything (?:special|private)|"
            r"what(?:'s| is) behind (?:the|your) (?:paywall|unlock)|curious about your content|"
            r"(?:i(?:'m| am) )?curious(?:\b|\s+about)|tell me (?:a |some )?(?:little |bit )?more|"
            r"what (?:did you mean|were you teasing|are you teasing)|"
            r"what(?:'s| is) (?:the )?(?:tease|hint))\b", re.I)),
    )
    CURRENT_OFFERING_AVAILABILITY_PATTERN = re.compile(
        r"\b(?:"
        r"what\s+(?:(?:private|paid)\s+)?(?:content|pics?|photos?|videos?|sets?|bundles?)"
        r"\s+do\s+you\s+(?:actually\s+)?have(?:\s+available(?:\s+right\s+now)?)?"
        r"|what\s+do\s+you\s+(?:actually\s+)?have\s+(?:for\s+sale|available(?:\s+right\s+now)?)"
        r"|what\s+(?:can\s+i\s+(?:buy|unlock)|are\s+you\s+selling)"
        r")\b",
        re.I,
    )
    NON_CURRENT_COMMERCIAL_PATTERN = re.compile(
        r"\b(?:"
        r"i\s+(?:do\s+not|don(?:'|.)t|am\s+not|(?:'|.)m\s+not)\s+"
        r"(?:buy|buying|pay|paying|unlock|unlocking)"
        r"|maybe\s+(?:someday|one\s+day|later)"
        r"|used\s+to|previously|last\s+(?:week|month|year)"
        r")\b",
        re.I,
    )
    TEMPORAL_DEFERMENT_PATTERNS = (
        ("ANOTHER_TIME", re.compile(r"\b(?:another|some\s+other)\s+time\b", re.I)),
        ("LATER", re.compile(r"\b(?:maybe\s+)?later\b", re.I)),
        ("FUTURE_DAY", re.compile(
            r"\b(?:when|once)\s+i\s*(?:'|.)?(?:m|am)?\s*"
            r"(?:feel\s+)?(?:actually\s+)?ready\b|"
            r"\bwhen\s+i\s+(?:actually\s+)?(?:feel\s+like|want)\s+"
            r"(?:buying|to\s+buy|something)\b|"
            r"\bwhen\s+i\s*(?:'|.)?(?:m|am)?\s+(?:actually\s+)?in\s+the\s+mood"
            r"(?:\s+to\s+buy)?\b",
            re.I,
        )),
        ("FUTURE_DAY", re.compile(
            r"\b(?:tomorrow|next\s+time|some\s+other\s+(?:night|day)|"
            r"when\s+i(?:'|.)m\s+less\s+(?:tired|busy))\b", re.I,
        )),
    )

    @classmethod
    def temporal_commercial_deferment(cls, message: str) -> dict:
        """Resolve current-vs-future timing before commercial action predicates."""
        text = str(message or "").replace("Ã¢â‚¬â„¢", "'").replace("’", "'")
        commercial_predicate = bool(re.search(
            r"\b(?:show|send|give|share|drop|buy|buying|purchase|unlock|link|"
            r"offer|ask|look|see|check)\b|"
            r"\b(?:content|sets?|stuff|made|something)\b",
            text, re.I,
        ))
        for qualifier, pattern in cls.TEMPORAL_DEFERMENT_PATTERNS:
            match = pattern.search(text)
            standalone_deferment = bool(match and re.search(
                r"\b(?:another|some\s+other)\s+time\b|"
                r"\bmaybe\s+later\b|\bnext\s+time\b|"
                r"\bmaybe\s+tomorrow\b|"
                r"\bsome\s+other\s+(?:night|day)\b|"
                r"\bwhen\s+i(?:'|.)m\s+less\s+(?:tired|busy)\b|"
                r"\b(?:when|once)\s+i\s*(?:'|.)?(?:m|am)?\s*"
                r"(?:feel\s+)?(?:actually\s+)?ready\b|"
                r"\bwhen\s+i\s+(?:actually\s+)?(?:feel\s+like|want)\s+"
                r"(?:buying|to\s+buy|something)\b|"
                r"\bwhen\s+i\s*(?:'|.)?(?:m|am)?\s+(?:actually\s+)?in\s+the\s+mood"
                r"(?:\s+to\s+buy)?\b",
                text, re.I,
            ))
            if match and (commercial_predicate or standalone_deferment):
                return {
                    "deferredCommercialInterest": True,
                    "deferredInterestReason": "CUSTOMER_SPECIFIED_FUTURE_TIMING",
                    "currentCommercialInterest": False,
                    "futureCommercialReentryAllowed": True,
                    "temporalCommercialQualifier": qualifier,
                }
        return {
            "deferredCommercialInterest": False,
            "deferredInterestReason": None,
            "currentCommercialInterest": False,
            "futureCommercialReentryAllowed": True,
            "temporalCommercialQualifier": None,
        }

    @staticmethod
    def commercial_boundary_type(message: str) -> str | None:
        """Classify negative polarity before any positive commercial predicate."""
        text = str(message or "").replace("â€™", "'")
        if re.search(
            r"\b(?:don['.]?t|do not|no)\s+(?:send|share|drop)\b.{0,24}\blink\b|"
            r"\bno,?\s+don['.]?t\s+send\s+another\s+link\b|"
            r"\bstop\s+sending\b.{0,24}\b(?:links?|offers?)\b",
            text, re.I,
        ):
            return "NO_LINK_BOUNDARY"
        if re.search(
            r"\b(?:don['.]?t|do not)\s+(?:show|send|give)\b.{0,32}"
            r"\b(?:another|more|one|it|that)\b",
            text, re.I,
        ):
            return "CURRENT_NO_BUY_BOUNDARY"
        if re.search(
            r"\bi(?:'ll| will)\s+(?:reach out|let you know|come back)\b"
            r".{0,40}\b(?:interested|ready|want)\b",
            text, re.I,
        ):
            return "DEFERRED_SELF_REACTIVATION"
        if re.search(
            r"\b(?:just|only)\s+(?:wanted|want)\s+to\s+"
            r"(?:check in|talk|chat)\b",
            text, re.I,
        ):
            return "RELATIONSHIP_ONLY_BOUNDARY"
        if re.search(
            r"\b(?:not\s+(?:really\s+)?(?:looking|trying)\s+to\s+buy|"
            r"not\s+buying|don['.]?t\s+want\s+to\s+buy|"
            r"not\s+interested(?:\s+right\s+now)?|"
            r"leave\s+the\s+sales\s+stuff\s+for\s+later|not\s+tonight)\b",
            text, re.I,
        ):
            return "CURRENT_NO_BUY_BOUNDARY"
        return None

    def __init__(self, direct_intent_detector):
        self.direct_intent_detector = direct_intent_detector

    @classmethod
    def explicit_continuation_detected(cls, message: str) -> bool:
        value = str(message or "")
        if cls.inventory_existence_question(value):
            return False
        return bool(cls.CONTINUATION_PATTERN.search(value))

    @classmethod
    def inventory_existence_question(cls, message: str) -> bool:
        value = str(message or "")
        return bool(
            cls.INVENTORY_EXISTENCE_QUESTION_PATTERN.search(value)
            and not cls.INVENTORY_ACTION_OR_COMPARISON_PATTERN.search(value)
        )

    def evaluate(self, *, context: dict | None, recent_purchase: bool,
                 cooldown_active: bool, readiness: dict | None = None,
                 active_offer: bool = False) -> CommercialReceptiveness:
        values = dict(context or {})
        flags = dict(readiness or {})
        message = str(values.get("latest_message") or "")
        temporal = self.temporal_commercial_deferment(message)
        commercial_boundary = self.commercial_boundary_type(message)
        commercial_interest_type = self.commercial_interest_type(message)
        direct = bool(self.direct_intent_detector(message))
        # The canonical receptiveness taxonomy owns current offering-
        # availability semantics.  Treating this category as direct prevents
        # the independent phrase matcher from becoming a second authority for
        # the same concept.
        direct = direct or commercial_interest_type in {
            "OFFERING_AVAILABILITY_INQUIRY", "PURCHASE_ACCEPTANCE",
            "SEND_OR_LINK_REQUEST", "PRICE_REQUEST", "DIRECT_CONTENT_INTENT",
        }
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
        if temporal["deferredCommercialInterest"]:
            direct = False
            continuation = False
            positive_turn = False
            commercial_interest_type = "NONE"
        curiosity = commercial_interest_type == "COMMERCIAL_CURIOSITY"
        positive_turn = positive_turn or curiosity or bool(
            flags.get("escalation_ready") is True
            or flags.get("positive_tease_response") is True
            or str(flags.get("engagement_level") or "").lower() == "high"
            or str(flags.get("buyer_likelihood") or "").lower() == "high"
        )
        if commercial_boundary:
            commercial_interest_type = "NONE"
            direct = False
            continuation = False
            positive_turn = False
        back_off = bool(
            action == "BACK_OFF"
            or values.get("offer_declined") is True
        )
        if temporal["deferredCommercialInterest"]:
            # A temporal qualifier is not itself a rejection, but separate
            # explicit negative language retains its normal boundary authority.
            back_off = bool(re.search(
                r"\b(?:no(?:\s+thanks)?|nah|stop|not\s+interested|"
                r"don(?:'|.)t\s+want)\b",
                message, re.I,
            ))
        elif not back_off:
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
            state = CommercialReceptivenessState.BACK_OFF
            appropriate = False
            reason = "CURRENT_RESISTANCE_TAKES_PRECEDENCE"
        elif temporal["deferredCommercialInterest"]:
            state = CommercialReceptivenessState.COOLING
            appropriate = False
            reason = "CUSTOMER_DEFERRED_COMMERCIAL_INTEREST"
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
            deferred_commercial_interest=bool(temporal["deferredCommercialInterest"]),
            deferred_interest_reason=temporal["deferredInterestReason"],
            current_commercial_interest=bool(direct),
            future_commercial_reentry_allowed=True,
            temporal_commercial_qualifier=temporal["temporalCommercialQualifier"],
        )

    @classmethod
    def commercial_interest_type(cls, message: str) -> str:
        text = str(message or "")
        if cls.temporal_commercial_deferment(text)["deferredCommercialInterest"]:
            return "NONE"
        if cls.commercial_boundary_type(text):
            return "NONE"
        if (
            cls.CURRENT_OFFERING_AVAILABILITY_PATTERN.search(text)
            and not cls.NON_CURRENT_COMMERCIAL_PATTERN.search(text)
        ):
            return "OFFERING_AVAILABILITY_INQUIRY"
        for interest_type, pattern in cls.INTEREST_PATTERNS:
            if pattern.search(text):
                return interest_type
        return "NONE"

    @classmethod
    def active_offer_continuation_type(cls, message: str) -> str | None:
        text = str(message or "")
        if cls.temporal_commercial_deferment(text)["deferredCommercialInterest"]:
            return None
        if cls.commercial_boundary_type(text):
            return None
        # Resolve an explicit request for a new lower price before binding
        # referential words to the one authoritative active offer.
        if cls.FRESH_COMPARATIVE_PRICE_PATTERN.search(text):
            return None
        for continuation_type, pattern in cls.ACTIVE_OFFER_CONTINUATION_PATTERNS:
            if pattern.search(text):
                return continuation_type
        return None

    @staticmethod
    def refine_projection(existing: dict | None, readiness: dict | None) -> dict:
        """Merge provider classifier evidence into the same canonical result."""
        result = dict(existing or {})
        flags = dict(readiness or {})
        positive = list(result.get("positiveEvidence") or ())
        action = str(flags.get("recommended_conversational_action") or "").upper()
        if result.get("deferredCommercialInterest") is True:
            result.update({
                "state": "COOLING",
                "freshDirectIntentDetected": False,
                "currentCommercialInterest": False,
                "continuationEligible": False,
                "anotherSaleAppropriateNow": False,
                "reason": "CUSTOMER_DEFERRED_COMMERCIAL_INTEREST",
                "commercialInterestType": "NONE",
            })
            result["positiveEvidence"] = [
                item for item in result.get("positiveEvidence") or ()
                if item not in {"FRESH_DIRECT_BUYING_INTENT", "EXPLICIT_CONTINUATION_REQUEST"}
            ]
            return result
        negative_polarity = bool(
            action == "BACK_OFF"
            and result.get("commercialInterestType") == "NONE"
            and "CURRENT_DECLINE_OR_BACK_OFF" in tuple(
                result.get("resistanceEvidence") or ()
            )
        )
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
        if negative_polarity:
            direct = False
            strong = False
            positive = [item for item in positive if item not in {
                "FRESH_DIRECT_BUYING_INTENT", "EXPLICIT_CONTINUATION_REQUEST",
                "STRONG_POSITIVE_ENGAGEMENT",
            }]
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

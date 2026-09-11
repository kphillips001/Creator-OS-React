"""Fail-closed validation for Ava-authored paid content presentation text."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import re


@dataclass(frozen=True)
class PaidPresentationValidation:
    valid: bool
    reason: str | None = None
    presentation: str = ""


class CustomerContentPresentationValidator:
    """Validate language only; commerce selection remains backend-owned."""

    _URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+|\b[a-z0-9.-]+\.(?:com|net|org|io|co)\b\S*")
    _UNUSABLE = re.compile(
        r"(?i)^\s*(?:n/?a|none|null|undefined|error|generation failed|"
        r"unable to generate|i cannot (?:help|respond)|as an ai(?: language model)?)\s*[.!]*\s*$"
    )
    _DISCOUNT = re.compile(
        r"(?i)\b(?:discount(?:ed)?|coupon|promo code|sale price|half[ -]?price|"
        r"free instead|\d{1,3}\s*%\s*off)\b"
    )
    _ALTERNATE_OFFER = re.compile(
        r"(?i)\b(?:another|different|replacement)\s+"
        r"(?:offer|bundle|set|photo|video|unlock|product)\b|"
        r"\b(?:selling|send|offer|unlock)\s+.+?\s+instead\b"
    )
    _MONEY = re.compile(
        r"(?ix)(?:\$\s*(?P<symbol>\d+(?:\.\d{1,2})?)|"
        r"\b(?:usd|eur|gbp)\s*(?P<prefix>\d+(?:\.\d{1,2})?)|"
        r"\b(?P<suffix>\d+(?:\.\d{1,2})?)\s*(?:usd|dollars?|bucks?|euros?|pounds?)\b)"
    )
    _EXPLICIT_DECIMAL = re.compile(r"(?<![\w.])\d+\.\d{2}(?![\w.])")
    _SPOKEN_PRICE = re.compile(
        r"(?i)\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
        r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
        r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?\s+"
        r"(?:oh\s+)?(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
        r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
        r"(?:[- ](?:one|two|three|four|five|six|seven|eight|nine))?\b"
    )
    _MEMBER_COUNT = re.compile(
        r"(?i)\b(?P<count>\d+)\s*(?:photos?|images?|pics?|shots?)\b"
    )
    _FINALE_CONTINUATION = re.compile(
        r"(?i)\b(?:another|next|one more)\s+(?:one|photo|image|shot|unlock|step)\s+"
        r"(?:after|following)\b|\bwait until you see (?:the )?next\b|"
        r"\bthere(?:'s| is) (?:another|one more) after this\b"
    )
    _FIRST_UNLOCK_FALSE_HISTORY = re.compile(
        r"(?i)\b(?:all|those|multiple|several|the earlier|previous)\s+"
        r"(?:unlocks?|paid (?:shots?|steps?)|purchases?)\b"
    )
    _IMMEDIATE_OFFER = re.compile(
        r"(?i)\b(?:here(?:'s| is| you go)|this is (?:the|one)|"
        r"i(?:'ve| have) got (?:this|one|something).{0,30}for you|"
        r"unlock (?:it|this)|take a look|i'm showing you|i am showing you)\b"
    )
    _DEFERRED_OFFER = re.compile(
        r"(?i)\b(?:maybe i(?:'ll| will)|maybe later|patience|worth the wait|"
        r"wait (?:and|until)|not yet)\b"
    )
    # PRESENT_OFFER is an execution decision: the structured PPV accompanies
    # this caption now.  A question that conditions delivery on another answer
    # is therefore not a presentation, even when it mentions the right item.
    _PERMISSION_TO_SEND = re.compile(
        r"""(?ix)(?:
            \b(?:want|would\s+you\s+like)\s+(?:me\s+to\s+)?
                (?:send|show|drop|share)(?:\s+you)?\b
          | \bshould\s+i\s+(?:send|show|drop|share)\b
          | \bare\s+you\s+ready\s+(?:for\s+me\s+to\s+)?
                (?:send|show|drop|share)\b
          | \b(?:want|need)\s+(?:the\s+)?(?:link|unlock)\??\s*$
          | \bif\s+you\s+(?:want|would\s+like),?\s+i(?:'ll|\s+will)\s+
                (?:send|show|drop|share)\b
        )"""
    )
    _PURCHASE_ACKNOWLEDGEMENT = re.compile(
        r"""(?ix)(?:
            \b(?:you|u)\s+(?:got|grabbed|unlocked|picked\s+up)\s+(?:it|this|one|that)\b
          | \bi\s+(?:saw|see|noticed)\s+(?:that\s+)?(?:you|u)\s+
                (?:got|grabbed|unlocked|picked\s+up)\b
          | \b(?:it(?:'s|\s+is)|this(?:'s|\s+is))\s+(?:all\s+)?yours\b
          | \b(?:enjoy|hope\s+you\s+(?:enjoy|like|love))\s+(?:it|this|that|this\s+one)\b
          | \bthanks?\s+for\s+(?:grabbing|getting|unlocking|picking\s+up)\b
        )"""
    )
    _PURCHASE_STILL_PENDING = re.compile(
        r"""(?ix)(?:
            \btake\s+your\s+time\b
          | \bwhen\s+you(?:'re|\s+are)\s+ready\b
          | \b(?:unlock|buy|purchase|get|grab)\s+(?:it|this|that|now)\b
          | \b(?:want|ready)\s+to\s+(?:unlock|buy|purchase|get|grab)\b
          | \b(?:did|have)\s+you\s+(?:buy|purchase|get|grab|unlock)\b
          | \bstill\s+(?:deciding|thinking|browsing|scrolling)\b
        )"""
    )
    _COMPLETED_POSITIVE_REACTION = re.compile(
        r"(?ix)\b(?:was\s+(?:really\s+)?(?:good|great|amazing)|"
        r"(?:watched|saw|opened|viewed|checked)\s+(?:it|that).{0,24}"
        r"(?:loved|liked|enjoyed)|(?:loved|liked|enjoyed)\s+(?:it|that)|"
        r"(?:really\s+)?(?:loved|liked|enjoyed)\s+(?:the\s+)?"
        r"(?:(?:last|previous|recent)\s+)?(?:one|set|photo|pic|video|bundle|content)|"
        r"(?:it|that)\s+(?:was|is)\s+(?:really\s+)?(?:good|great|amazing)|"
        r"(?:it|that)\s+was\s+worth\s+it)\b"
    )
    _NEGATIVE_PURCHASE_REACTION = re.compile(
        r"(?ix)\b(?:didn['’]?t|did\s+not)\s+(?:really\s+)?(?:like|love|enjoy)\s+(?:it|that)|"
        r"\b(?:it|that)\s+(?:wasn['’]?t|was\s+not)\s+(?:for\s+me|good|worth\s+it)\b"
    )
    _CURRENT_OPENING_REACTION = re.compile(
        r"(?ix)\b(?:opening|watching|viewing|checking)\s+(?:it|that)\s+(?:now|right\s+now)\b"
    )
    _NEGATIVE_NAMED_PURCHASE_REACTION = re.compile(
        r"(?ix)\b(?:didn['\u2019]?t|did\s+not)\s+(?:really\s+)?"
        r"(?:like|love|enjoy)\s+(?:the\s+)?(?:(?:last|previous|recent)\s+)?"
        r"(?:one|set|photo|pic|video|bundle|content)\b"
    )
    _AGGREGATE_POSITIVE_PURCHASE_REACTION = re.compile(
        r"(?ix)(?:"
        r"\b(?:two|three|four|five|\d+)\s+for\s+(?:two|three|four|five|\d+)\b|"
        r"\b(?:both|all|everything)\b.{0,60}\b(?:good|great|amazing|liked|loved|enjoyed|worth\s+it|landed|hit)\b|"
        r"\b(?:liked|loved|enjoyed|happy\s+with)\b.{0,40}\b(?:both|all|everything)\b|"
        r"\b(?:liked|loved|enjoyed|happy\s+with)\b.{0,40}\b(?:what|stuff|things)\s+i(?:['\u2019]?ve|\s+have)\s+(?:bought|purchased|unlocked|got(?:ten)?)\b|"
        r"\b(?:what|everything|stuff|things)\s+i(?:['\u2019]?ve|\s+have)\s+(?:bought|purchased|unlocked|got(?:ten)?)\b.{0,40}\b(?:good|great|solid|liked|loved|enjoyed)\b|"
        r"\bhaven['\u2019]?t\s+missed\s+yet\b"
        r")"
    )
    _MIXED_PURCHASE_REACTION = re.compile(
        r"(?ix)\b(?:one|some|first|second).{0,30}"
        r"(?:good|great|liked|loved|enjoyed).{0,30}\b(?:but|and|,)?.{0,10}"
        r"(?:one|some|first|second).{0,16}"
        r"(?:wasn['\u2019]?t|was\s+not|didn['\u2019]?t|did\s+not|bad)\b"
    )
    _POSITIVE_EXPERIENCE_ACKNOWLEDGEMENT = re.compile(
        r"(?ix)\b(?:glad|love|happy).{0,40}(?:liked|loved|enjoyed|loving|"
        r"hit|landed|worked\s+out|lived\s+up)|"
        r"\b(?:nice|glad|love).{0,30}\bsurpris(?:e|es|ed|ing)\b|"
        r"\b(?:liked|loved|enjoyed)\s+(?:it|that)|"
        r"\b(?:that|it)\s+(?:hit|landed|worked\s+out)\b"
    )
    _NEGATIVE_EXPERIENCE_ACKNOWLEDGEMENT = re.compile(
        r"(?ix)\b(?:sorry|appreciate\s+you\s+telling\s+me|thanks?\s+for\s+"
        r"telling\s+me|didn['’]?t\s+(?:land|hit)|not\s+your\s+(?:thing|vibe))\b"
    )
    _RESOLVED_COMPLETED_POSITIVE_REACTION = re.compile(
        r"(?ix)\b(?:liked|loved|enjoyed)\b|\b(?:was|is)\s+(?:even\s+|my\s+)?"
        r"(?:favorite|better|best|good|great|amazing|worth\s+it|"
        r"a\s+fun\s+surprise)\b"
    )
    _COMPARATIVE_PURCHASE_REACTION = re.compile(
        r"(?ix)\b(?:even\s+more|better|best|favorite|prefer(?:red)?)\b"
    )
    _COMPARATIVE_PURCHASE_ACKNOWLEDGEMENT = re.compile(
        r"(?ix)\b(?:even\s+more|better|best|favorite|prefer(?:red)?|won)\b|"
        r"\b(?:liked|loved|enjoyed)\s+(?:that|this|the)\s+one\s+more\b"
    )
    _POSITIVE_PURCHASE_VALUE_FEEDBACK = re.compile(
        r"(?ix)\b(?:worth\s+it|good|great|amazing|liked|loved|enjoyed|"
        r"landed|worked|a\s+hit|hit\s+the\s+spot)\b"
    )
    _POSITIVE_PLURAL_RESPONSE = re.compile(
        r"(?ix)\b(?:they|them|those|these|recent\s+ones|last\s+few|"
        r"last\s+(?:couple|two|three)|sets|picks)\b.{0,55}"
        r"\b(?:worth|good|great|land(?:ed|ing)?|work(?:ed|ing)?|hit|"
        r"liked|loved|enjoyed)\b|"
        r"\b(?:glad|happy|good\s+to\s+know|love)\b.{0,45}"
        r"\b(?:they|them|those|these|recent\s+ones|sets|picks)\b"
    )

    @classmethod
    def is_aggregate_positive_purchase_reaction(
        cls, customer_message: str, *, purchase_count: int = 0,
    ) -> bool:
        return bool(
            int(purchase_count or 0) > 1
            and cls._AGGREGATE_POSITIVE_PURCHASE_REACTION.search(
                str(customer_message or "")
            )
        )

    @classmethod
    def purchase_reaction_state(
        cls, customer_message: str, *, purchase_count: int = 0,
        purchase_history_reference: dict | None = None,
    ) -> str:
        text = str(customer_message or "")
        reference = dict(purchase_history_reference or {})
        resolved_completed_purchase = bool(
            reference.get("purchaseHistoryReferentResolved") is True
            and (
                reference.get("resolutionType") in {"AGGREGATE", "RECENT_SUBSET"}
                or (
                    isinstance(reference.get("resolvedOrdinal"), int)
                    and reference.get("resolvedOrdinal") > 0
                )
            )
        )
        if cls._MIXED_PURCHASE_REACTION.search(text):
            return "NEUTRAL_PURCHASE_CONFIRMATION"
        if (
            cls._NEGATIVE_PURCHASE_REACTION.search(text)
            or cls._NEGATIVE_NAMED_PURCHASE_REACTION.search(text)
        ):
            return "COMPLETED_NEGATIVE_EXPERIENCE"
        if cls.is_aggregate_positive_purchase_reaction(
            text, purchase_count=purchase_count,
        ):
            return "COMPLETED_POSITIVE_EXPERIENCE"
        if (
            resolved_completed_purchase
            and cls._RESOLVED_COMPLETED_POSITIVE_REACTION.search(text)
        ):
            return "COMPLETED_POSITIVE_EXPERIENCE"
        if cls._COMPLETED_POSITIVE_REACTION.search(text):
            return "COMPLETED_POSITIVE_EXPERIENCE"
        if cls._CURRENT_OPENING_REACTION.search(text):
            return "OPENING_OR_VIEWING_NOW"
        if re.search(r"\bjust\s+(?:bought|purchased|paid\s+for|unlocked|grabbed)\b", text, re.I):
            return "JUST_PURCHASED"
        return "NEUTRAL_PURCHASE_CONFIRMATION"

    @classmethod
    def purchase_reaction_semantic_frame(
        cls, customer_message: str, *, purchase_count: int = 0,
        purchase_history_reference: dict | None = None,
    ) -> dict:
        reference = dict(purchase_history_reference or {})
        reaction_state = cls.purchase_reaction_state(
            customer_message, purchase_count=purchase_count,
            purchase_history_reference=reference,
        )
        collective = bool(
            reference.get("resolutionType") == "AGGREGATE"
            or reference.get("resolutionType") == "RECENT_SUBSET"
            or cls.is_aggregate_positive_purchase_reaction(
            customer_message, purchase_count=purchase_count,
            )
        )
        recent_subset = reference.get("resolutionType") == "RECENT_SUBSET"
        positive_value = bool(
            recent_subset and cls._POSITIVE_PURCHASE_VALUE_FEEDBACK.search(
                str(customer_message or "")
            )
        )
        return {
            "purchaseReactionState": reaction_state,
            "verifiedPurchaseCount": int(purchase_count or 0),
            "aggregatePurchaseReactionRequired": collective,
            "retrospectivePurchaseReactionRequired": reaction_state in {
                "COMPLETED_POSITIVE_EXPERIENCE",
                "COMPLETED_NEGATIVE_EXPERIENCE",
            },
            "aggregateSubject": (
                "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD" if collective else None
            ),
            "singularAcknowledgementAloneSufficient": not collective,
            "purchaseHistoryReferentDetected": bool(
                reference.get("purchaseHistoryReferentDetected")
            ),
            "purchaseHistoryReferentResolved": bool(
                reference.get("purchaseHistoryReferentResolved")
            ),
            "resolutionType": reference.get("resolutionType"),
            "resolvedOrdinal": reference.get("resolvedOrdinal"),
            "aggregatePurchaseReference": bool(
                reference.get("aggregatePurchaseReference")
            ),
            "resolvedPurchaseCount": int(
                reference.get("resolvedPurchaseCount")
                or (purchase_count if reference.get("resolutionType") == "AGGREGATE" else 0)
            ),
            "resolvedPurchaseIds": list(reference.get("resolvedPurchaseIds") or ()),
            "purchaseFeedbackAggregate": collective,
            **({"recentSubsetPositiveFeedbackRequired": True}
               if positive_value else {}),
            "comparativePurchaseReaction": bool(
                reference.get("purchaseHistoryReferentResolved") is True
                and cls._COMPARATIVE_PURCHASE_REACTION.search(
                    str(customer_message or "")
                )
            ),
        }

    @classmethod
    def recent_subset_positive_feedback_satisfied(
        cls, response: str, *, semantic_frame: dict | None = None,
    ) -> bool:
        frame = dict(semantic_frame or {})
        if not frame.get("recentSubsetPositiveFeedbackRequired"):
            return True
        return bool(cls._POSITIVE_PLURAL_RESPONSE.search(str(response or "")))

    _TRACK_RECORD_PREDICATE = (
        r"(?:on\s+(?:a\s+)?(?:roll|streak)|on\s+fire|two\s+for\s+two|"
        r"kill(?:ing|ed)\s+it|crush(?:ing|ed)\s+it|nailed\s+it|"
        r"(?:have\s+not|haven['\u2019]?t)\s+missed|(?:keep|keeps)\s+landing)"
    )

    @classmethod
    def aggregate_purchase_subject_analysis(
        cls, response: str, *, expected_subject: str = "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD",
    ) -> dict:
        """Validate the proposition owner independently of response wording."""
        text = " ".join(str(response or "").split())
        expected_ava_or_content = expected_subject == (
            "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD"
        )
        customer_success = re.compile(
            rf"(?ix)(?:\b(?:you(?:['\u2019]?re|\s+are)|youre|u\s+r)\b.{{0,24}}"
            rf"\b{cls._TRACK_RECORD_PREDICATE}\b|"
            rf"\blook\s+at\s+you\b.{{0,30}}\b{cls._TRACK_RECORD_PREDICATE}\b)"
        )
        ava_success = re.compile(
            rf"(?ix)(?:\b(?:i|we(?:['\u2019]?re|\s+are))\b"
            rf".{{0,24}}\b{cls._TRACK_RECORD_PREDICATE}\b|"
            rf"\b{cls._TRACK_RECORD_PREDICATE}\b.{{0,18}}\b(?:for\s+me|for\s+us)\b|"
            rf"\b(?:two|three|four|five|\d+)\s+wins?\s+for\s+(?:me|us)\b)"
        )
        content_success = re.compile(
            r"(?ix)(?:\b(?:my|our)\s+(?:picks?|content|sets?|stuff|ones?)\b.{0,35}"
            r"\b(?:work(?:ing|ed)?|land(?:ing|ed)?|hit|keep|keeps)\b|"
            r"\b(?:both|all|everything|they|them)\b.{0,45}"
            r"\b(?:landed|hit|worked|liked|loved|enjoyed)\b|"
            r"\b(?:glad|love|happy).{0,35}\b(?:both|all|everything|they|them)\b|"
            r"\b(?:you|u)\s+(?:liked|loved|enjoyed).{0,25}\b(?:both|all|them)\b)"
            r"|\b(?:glad|love|happy|good\s+to\s+know).{0,45}\b(?:they|them|those|things|purchases|unlocks|sets|picks)\b"
            r"|\b(?:they|those|the\s+(?:things|purchases|unlocks|sets|picks))\b.{0,45}\b(?:hit|landed|worked|good|great|solid)\b"
        )
        customer_owned = bool(customer_success.search(text))
        ava_or_content_owned = bool(
            ava_success.search(text) or content_success.search(text)
        )
        if expected_ava_or_content:
            contradictory = customer_owned
            supported = ava_or_content_owned
        elif expected_subject == "CUSTOMER_TRACK_RECORD":
            contradictory = ava_or_content_owned
            supported = customer_owned
        else:
            contradictory = False
            supported = bool(customer_owned or ava_or_content_owned)
        compatible = not contradictory
        return {
            "semanticFrameSubject": expected_subject,
            "finalResponseSubjectCompatible": compatible,
            "contradictorySemanticSegmentDetected": contradictory,
            "aggregatePurchaseReactionSatisfied": bool(supported and compatible),
        }

    @classmethod
    def aggregate_purchase_reaction_satisfied(
        cls, response: str, *, semantic_frame: dict | None = None,
    ) -> bool:
        frame = dict(semantic_frame or {})
        return bool(cls.aggregate_purchase_subject_analysis(
            response,
            expected_subject=str(
                frame.get("aggregateSubject")
                or "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD"
            ),
        )["aggregatePurchaseReactionSatisfied"])

    def validate_paid(self, presentation: str, *, offering,
                      presentation_context=None) -> PaidPresentationValidation:
        text = str(presentation or "").strip()
        if not text:
            return PaidPresentationValidation(False, "PAID_PRESENTATION_EMPTY")
        if self._UNUSABLE.fullmatch(text) or not re.search(r"[A-Za-z0-9]", text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_UNUSABLE")
        if self._URL.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_UNAUTHORIZED_URL")
        if self._DISCOUNT.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_UNAUTHORIZED_DISCOUNT")
        if self._ALTERNATE_OFFER.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_ALTERNATE_OFFER")
        authoritative = Decimal(int(offering.price_minor)) / Decimal(100)
        for match in self._MONEY.finditer(text):
            raw = next(value for value in match.groupdict().values() if value is not None)
            try:
                claimed = Decimal(raw)
            except InvalidOperation:
                return PaidPresentationValidation(False, "PAID_PRESENTATION_INVALID_PRICE")
            if claimed != authoritative:
                return PaidPresentationValidation(False, "PAID_PRESENTATION_CONTRADICTORY_PRICE")
        context = dict(presentation_context or {})
        if (
            self._MONEY.search(text)
            or self._EXPLICIT_DECIMAL.search(text)
            or self._SPOKEN_PRICE.search(text)
        ):
            return PaidPresentationValidation(
                False, "PAID_PRESENTATION_CONVERSATIONAL_PRICE"
            )
        # Structured bundle/session authority is more specific than generic
        # language-shape failures.  Validate contradictions first so rejected
        # work retains the exact fail-closed diagnostic at every downstream
        # boundary.
        bundle = dict(context.get("bundle") or {})
        bundle_offer = dict(bundle.get("bundleOffer") or {})
        member_count = bundle_offer.get("paidMemberCount")
        if member_count is not None:
            for match in self._MEMBER_COUNT.finditer(text):
                if int(match.group("count")) != int(member_count):
                    return PaidPresentationValidation(
                        False, "PAID_PRESENTATION_CONTRADICTORY_BUNDLE_COUNT"
                    )
        session = dict(context.get("session") or {})
        progression = dict(session.get("progressionAwareness") or {})
        role = str(progression.get("currentRole") or "").upper()
        if role == "FINALE" and self._FINALE_CONTINUATION.search(text):
            return PaidPresentationValidation(
                False, "PAID_PRESENTATION_FINALE_CONTINUATION_CLAIM"
            )
        if (
            role == "FIRST_UNLOCK"
            and int(progression.get("previousPaidUnlocks") or 0) == 0
            and self._FIRST_UNLOCK_FALSE_HISTORY.search(text)
        ):
            return PaidPresentationValidation(
                False, "PAID_PRESENTATION_FALSE_SESSION_HISTORY"
            )
        if self._DEFERRED_OFFER.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_DEFERRED")
        if self._PERMISSION_TO_SEND.search(text):
            return PaidPresentationValidation(
                False, "PAID_PRESENTATION_PERMISSION_GATE"
            )
        lifecycle = dict(context.get("lifecycle") or {})
        if lifecycle.get("messagePurpose") == "NUDGE":
            original = self._normalize_comparison(lifecycle.get("originalPresentation"))
            candidate = self._normalize_comparison(text)
            if original and candidate and (
                candidate == original
                or SequenceMatcher(None, candidate, original).ratio() >= 0.90
            ):
                return PaidPresentationValidation(
                    False, "PAID_PRESENTATION_REPEATS_ORIGINAL"
                )
        if (
            lifecycle.get("messagePurpose") != "NUDGE"
            and not self._IMMEDIATE_OFFER.search(text)
        ):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_NOT_AN_OFFER")
        if len(text) > 320:
            return PaidPresentationValidation(False, "PAID_PRESENTATION_NOT_CONCISE")
        if lifecycle.get("purchaseKind") == "SESSION_FINALE_PURCHASE" and self._FINALE_CONTINUATION.search(text):
            return PaidPresentationValidation(False, "PURCHASE_ACKNOWLEDGEMENT_FINALE_CONTINUATION_CLAIM")
        return PaidPresentationValidation(True, presentation=text)

    @classmethod
    def numeric_price_present(cls, presentation: str) -> bool:
        """Detect price-shaped prose without inspecting structured commerce."""
        text = str(presentation or "")
        return bool(
            cls._MONEY.search(text)
            or cls._EXPLICIT_DECIMAL.search(text)
            or cls._SPOKEN_PRICE.search(text)
        )

    def validate_lifecycle(self, presentation: str, *, lifecycle,
                           require_purchase_acknowledgement: bool = False,
                           customer_message: str = "",
                           purchase_count: int = 0,
                           question_authorized: bool = True,
                           purchase_history_reference: dict | None = None) -> PaidPresentationValidation:
        text = str(presentation or "").strip()
        if not text or self._UNUSABLE.fullmatch(text):
            return PaidPresentationValidation(False, "LIFECYCLE_PRESENTATION_UNUSABLE")
        context = dict(lifecycle or {})
        if require_purchase_acknowledgement:
            semantic_frame = self.purchase_reaction_semantic_frame(
                customer_message, purchase_count=purchase_count,
                purchase_history_reference=purchase_history_reference,
            )
            reaction_state = semantic_frame["purchaseReactionState"]
            if not question_authorized and "?" in text:
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_UNAUTHORIZED_QUESTION"
                )
            if self._PURCHASE_STILL_PENDING.search(text):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_IMPLIES_PENDING"
                )
            if self._PERMISSION_TO_SEND.search(text):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_REASKS_PERMISSION"
                )
            completed_positive = bool(
                reaction_state == "COMPLETED_POSITIVE_EXPERIENCE"
                and self._POSITIVE_EXPERIENCE_ACKNOWLEDGEMENT.search(text)
                and not re.search(r"\bhope\s+you\s+(?:enjoy|like|love)\b", text, re.I)
            )
            completed_negative = bool(
                reaction_state == "COMPLETED_NEGATIVE_EXPERIENCE"
                and self._NEGATIVE_EXPERIENCE_ACKNOWLEDGEMENT.search(text)
                and not re.search(r"\b(?:congrats|glad\s+you\s+(?:liked|loved)|hope\s+you\s+enjoy)\b", text, re.I)
            )
            if reaction_state == "COMPLETED_POSITIVE_EXPERIENCE" and re.search(
                r"\bhope\s+you\s+(?:enjoy|like|love)\b", text, re.I,
            ):
                return PaidPresentationValidation(False, "PURCHASE_ACKNOWLEDGEMENT_TEMPORAL_MISMATCH")
            if reaction_state == "COMPLETED_NEGATIVE_EXPERIENCE" and not completed_negative:
                return PaidPresentationValidation(False, "PURCHASE_ACKNOWLEDGEMENT_SENTIMENT_MISMATCH")
            if (
                semantic_frame["comparativePurchaseReaction"]
                and not self._COMPARATIVE_PURCHASE_ACKNOWLEDGEMENT.search(text)
            ):
                return PaidPresentationValidation(
                    False,
                    "PURCHASE_ACKNOWLEDGEMENT_COMPARATIVE_SEMANTICS_MISSING",
                )
            if (
                semantic_frame["aggregatePurchaseReactionRequired"]
                and not self.aggregate_purchase_reaction_satisfied(
                    text, semantic_frame=semantic_frame,
                )
            ):
                return PaidPresentationValidation(
                    False,
                    "PURCHASE_ACKNOWLEDGEMENT_AGGREGATE_SEMANTICS_MISSING",
                )
            if not (self._PURCHASE_ACKNOWLEDGEMENT.search(text)
                    or completed_positive or completed_negative
                    or (
                        semantic_frame["aggregatePurchaseReactionRequired"]
                        and self.aggregate_purchase_reaction_satisfied(
                            text, semantic_frame=semantic_frame,
                        )
                    )):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_MISSING"
                )
        if context.get("purchaseKind") == "SESSION_FINALE_PURCHASE" and self._FINALE_CONTINUATION.search(text):
            return PaidPresentationValidation(False, "PURCHASE_ACKNOWLEDGEMENT_FINALE_CONTINUATION_CLAIM")
        return PaidPresentationValidation(True, presentation=text)

    @staticmethod
    def _normalize_comparison(value):
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

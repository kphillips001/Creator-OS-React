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
        if self._DEFERRED_OFFER.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_DEFERRED")
        if self._PERMISSION_TO_SEND.search(text):
            return PaidPresentationValidation(
                False, "PAID_PRESENTATION_PERMISSION_GATE"
            )
        if not self._IMMEDIATE_OFFER.search(text):
            return PaidPresentationValidation(False, "PAID_PRESENTATION_NOT_AN_OFFER")
        if len(text) > 320:
            return PaidPresentationValidation(False, "PAID_PRESENTATION_NOT_CONCISE")
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
        lifecycle = dict(context.get("lifecycle") or {})
        if lifecycle.get("messagePurpose") == "NUDGE":
            original = self._normalize_comparison(lifecycle.get("originalPresentation"))
            candidate = self._normalize_comparison(text)
            if original and candidate and (candidate == original or SequenceMatcher(None, candidate, original).ratio() >= 0.90):
                return PaidPresentationValidation(False, "PAID_PRESENTATION_REPEATS_ORIGINAL")
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
                           require_purchase_acknowledgement: bool = False) -> PaidPresentationValidation:
        text = str(presentation or "").strip()
        if not text or self._UNUSABLE.fullmatch(text):
            return PaidPresentationValidation(False, "LIFECYCLE_PRESENTATION_UNUSABLE")
        context = dict(lifecycle or {})
        if require_purchase_acknowledgement:
            if self._PURCHASE_STILL_PENDING.search(text):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_IMPLIES_PENDING"
                )
            if self._PERMISSION_TO_SEND.search(text):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_REASKS_PERMISSION"
                )
            if not self._PURCHASE_ACKNOWLEDGEMENT.search(text):
                return PaidPresentationValidation(
                    False, "PURCHASE_ACKNOWLEDGEMENT_MISSING"
                )
        if context.get("purchaseKind") == "SESSION_FINALE_PURCHASE" and self._FINALE_CONTINUATION.search(text):
            return PaidPresentationValidation(False, "PURCHASE_ACKNOWLEDGEMENT_FINALE_CONTINUATION_CLAIM")
        return PaidPresentationValidation(True, presentation=text)

    @staticmethod
    def _normalize_comparison(value):
        return " ".join(re.findall(r"[a-z0-9]+", str(value or "").lower()))

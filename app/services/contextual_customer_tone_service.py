"""Contextual interaction tone projection; never authorizes commerce."""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from app.models.commercial_objection import CommercialObjectionType
from app.services.commercial_objection_service import CommercialObjectionService


class ContextualCustomerToneService:
    """Keep hostility, provocation, boundaries, and commerce independent."""

    DISENGAGEMENT = re.compile(
        r"\b(?:leave me alone|stop (?:messaging|bothering|talking to) me|"
        r"go away|never buying anything|don['’]?t contact me|fuck off)\b", re.I,
    )
    NEGATIVE_DIRECTIVE = re.compile(
        r"\b(?:shut up|go away|stop bothering|(?:stop )?wast(?:e|ing) my time|nonsense|"
        r"disgusting|worthless|hate (?:you|this))\b", re.I,
    )
    DEGRADING_CONSTRUCTION = re.compile(
        r"\b(?:you(?:'re| are) (?:a |an |such a )|what a )[^.!?]{1,32}"
        r"(?:[.!?]|$)", re.I,
    )
    PROVOCATIVE = re.compile(
        r"(?:😏|😉|🔥)|\b(?:naughty|dirty|horny|turned on|"
        r"turning me on|sex(?:y|ual)?|bad girl|such a)\b", re.I,
    )
    FRUSTRATION = re.compile(
        r"\b(?:ridiculous|seriously|come on|this is bullshit|what the hell|"
        r"too much|more than .*expected)\b", re.I,
    )
    PRICE = re.compile(r"(?:\$\s*\d|\b(?:price|cost|too much|expensive)\b)", re.I)
    COMMERCIAL = re.compile(
        r"(?:\$\s*\d)|\b(?:how much|price|cost|buy|purchase|unlock|private (?:stuff|set|content)|"
        r"send it|show me what you have)\b", re.I,
    )
    REACTION_BAIT = re.compile(
        r"\b(?:answer me|keep (?:answering|responding)|what,? scared|"
        r"too scared to (?:answer|respond)|trying to get a reaction)\b", re.I,
    )
    DIRECT_ABUSE = re.compile(
        r"\b(?:you(?:'re| are)\s+(?:a\s+)?(?:worthless|pathetic|disgusting|stupid|"
        r"idiot(?:ic)?|moron(?:ic)?|piece of (?:shit|trash))|"
        r"(?:worthless|pathetic|stupid|disgusting)\s+(?:bitch|whore|slut)|"
        r"kill yourself)\b", re.I,
    )
    THREAT = re.compile(
        r"\b(?:i(?:'m| am| will|'ll)\s+(?:going to\s+)?(?:hurt|kill|attack|find|"
        r"destroy|ruin)\s+(?:you|her)|you(?:'re| are)\s+dead|watch your back|"
        r"i know where you live)\b", re.I,
    )
    HARASSMENT = re.compile(
        r"\b(?:i(?:'ll| will)\s+(?:never stop|keep)\s+(?:messaging|harassing|"
        r"contacting|following)\s+you|you can(?:not|'t)\s+get rid of me)\b", re.I,
    )
    # Ordinary contempt is often expressed without profanity or a direct insult.
    # These constructions describe dismissal of the other person's contribution
    # or a one-sided demand for attention; they are intentionally weaker than the
    # severe-abuse/direct-boundary vocabulary above.
    DISMISSIVE_CONTEMPT = re.compile(
        r"\b(?:"
        r"(?:you(?:'re| are)\s+)?trying\s+(?:a\s+(?:little|bit)\s+)?too\s+hard|"
        r"(?:i\s+)?didn['’]?t\s+ask(?:\s+for)?|who\s+asked|nobody\s+asked|"
        r"(?:talking|acting)\s+like\s+i\s+care|as\s+if\s+i\s+care|"
        r"do\s+you\s+ever\s+stop\s+talking|you\s+always\s+this\s+chatty|"
        r"keep\s+me\s+entertained|entertain\s+me|"
        r"this\s+is\s+(?:getting\s+)?boring|you(?:'re| are)\s+boring|"
        r"i\s+don['’]?t\s+care\s+what\s+you\s+(?:think|say|want)"
        r")\b",
        re.I,
    )

    def classify(self, *, message: str,
                 recent_transcript: Sequence[Mapping] = (),
                 relationship_context: Mapping | None = None,
                 commerce_context: Mapping | None = None) -> dict:
        text = str(message or "").strip()
        recent = tuple(recent_transcript or ())[-12:]
        relationship = dict(relationship_context or {})
        commerce = dict(commerce_context or {})
        canonical_objection = CommercialObjectionService().evaluate(
            message=text, context={}
        )
        prior_text = " ".join(
            str(item.get("content") or "") for item in recent
            if str(item.get("role") or "").lower() in {"user", "customer"}
        )
        prior_boundary_turns = sum(
            CommercialObjectionService().evaluate(
                message=str(item.get("content") or ""), context={}
            ).objection_type is CommercialObjectionType.GLOBAL_DECLINE
            for item in recent
            if str(item.get("role") or "").lower() in {"user", "customer"}
        )
        # The canonical commercial-boundary classifier already owns global
        # decline semantics.  Compose it here so tone, Sales Brain, and
        # allocation cannot disagree about the same customer boundary.
        explicit_disengagement = bool(
            canonical_objection.objection_type
            is CommercialObjectionType.GLOBAL_DECLINE
            or self.DISENGAGEMENT.search(text)
            or (
                self.NEGATIVE_DIRECTIVE.search(text)
                and re.search(r"\b(?:stop|leave|go|don['â€™]?t)\b", text, re.I)
            )
        )
        dismissive = bool(self.DISMISSIVE_CONTEMPT.search(text))
        strong_negative = bool(
            self.NEGATIVE_DIRECTIVE.search(text)
            or self.FRUSTRATION.search(text)
            or explicit_disengagement
        )
        negative = bool(
            strong_negative or dismissive
        )
        provocative = bool(self.PROVOCATIVE.search(text))
        prior_hostile_turns = sum(bool(
            self.NEGATIVE_DIRECTIVE.search(str(item.get("content") or ""))
            or self.DISENGAGEMENT.search(str(item.get("content") or ""))
            or self.DISMISSIVE_CONTEMPT.search(str(item.get("content") or ""))
        ) for item in recent if str(item.get("role") or "").lower() in {
            "user", "customer"
        })
        current_hostile = bool(
            self.NEGATIVE_DIRECTIVE.search(text) or explicit_disengagement
            or dismissive
        )
        hostile_carryover_bait = bool(
            provocative and prior_hostile_turns >= 2
            and not relationship.get("mutualFlirtation")
            and not relationship.get("mutual_flirtation")
        )
        repeated = bool(
            (current_hostile and prior_hostile_turns >= 1)
            or hostile_carryover_bait
        )
        degrading = bool(
            dismissive or (
                self.DEGRADING_CONSTRUCTION.search(text)
                and (negative or not provocative or repeated)
            )
        )
        prior_flirt = bool(
            relationship.get("mutualFlirtation")
            or relationship.get("mutual_flirtation")
            or re.search(r"(?:😏|😉|flirt|naughty|teas(?:e|ing))", prior_text, re.I)
        )
        relationship_depth = int(
            relationship.get("conversationDepth")
            or relationship.get("inboundMessageCount") or 0
        )
        verified_buyer = bool(
            commerce.get("verifiedPurchaseCount")
            or commerce.get("purchaseCount")
            or relationship.get("verifiedBuyer")
        )
        playful = bool(
            provocative and not explicit_disengagement
            and (prior_flirt or relationship_depth >= 12 or verified_buyer)
            and not self.NEGATIVE_DIRECTIVE.search(text)
        )
        commercial = bool(self.COMMERCIAL.search(text))
        price_objection = bool(self.PRICE.search(text) and self.FRUSTRATION.search(text))
        rage_bait = bool(
            repeated and (negative or degrading or self.REACTION_BAIT.search(text))
            and not playful and not commercial and not price_objection
        )
        threat = bool(self.THREAT.search(text))
        harassment = bool(self.HARASSMENT.search(text))
        direct_abuse = bool(self.DIRECT_ABUSE.search(text))
        severe_repeated = bool(
            repeated and prior_hostile_turns >= 2 and degrading
            and not playful and not price_objection and not commercial
        )
        qualifying_abuse = bool(
            threat or harassment or direct_abuse or severe_repeated
        )
        abuse_category = (
            "THREAT" if threat else
            "HARASSMENT" if harassment else
            "DIRECT_ABUSE" if direct_abuse else
            "REPEATED_HOSTILITY" if severe_repeated else
            "DISMISSIVE_OR_RUDE" if dismissive else
            "ORDINARY_NEGATIVITY" if negative else "NONE"
        )
        hostility_score = (
            (3 if explicit_disengagement else 0)
            + (2 if strong_negative else 0)
            + (1 if dismissive else 0)
            + (1 if degrading else 0)
            + ((4 if strong_negative or hostile_carryover_bait else 2)
               if repeated else 0)
            - (2 if playful else 0)
        )
        hostility = (
            "SEVERE" if hostility_score >= 7 else
            "HIGH" if hostility_score >= 5 else
            "MODERATE" if hostility_score >= 3 else
            "LOW" if hostility_score >= 1 else "NONE"
        )
        abuse_severity = (
            "CRITICAL" if threat else "SEVERE" if qualifying_abuse else
            hostility
        )
        return {
            "hostilityLevel": hostility,
            "negativeSentiment": negative,
            "insultingOrDegrading": degrading,
            "dismissiveOrContemptuous": dismissive,
            "sexualOrProvocative": provocative,
            "playfulOrBanter": playful,
            "frustration": bool(self.FRUSTRATION.search(text)),
            "repeatedHostility": repeated,
            "explicitDisengagement": explicit_disengagement,
            "commercialCuriosity": commercial,
            "buyingIntent": commercial,
            "priceObjection": price_objection,
            "rageBaitPattern": rage_bait,
            "priorHostileTurnCount": prior_hostile_turns,
            "priorExplicitDisengagementCount": prior_boundary_turns,
            "relationshipContextApplied": bool(
                prior_flirt or relationship_depth or verified_buyer
            ),
            "hardBoundaryAuthoritative": explicit_disengagement,
            "qualifyingAbuse": qualifying_abuse,
            "abuseCategory": abuse_category,
            "abuseSeverity": abuse_severity,
        }

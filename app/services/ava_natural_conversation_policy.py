"""Deterministic ordinary-chat restraint at the final response boundary."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NaturalConversationDecision:
    text: str
    repaired: bool
    reasons: tuple[str, ...]
    energy: str
    function: str

    def diagnostics(self) -> dict:
        return {
            "policy": "AVA_NATURAL_CONVERSATION_V1",
            "repaired": self.repaired,
            "repairReasons": list(self.reasons),
            "energyAuthority": self.energy,
            "conversationalFunction": self.function,
            "finalRelationshipBoundarySatisfied": True,
            "finalEscalationBoundarySatisfied": True,
            "finalRepeatedFlirtFunctionSatisfied": True,
            "naturalTurnEndingAllowed": True,
        }


class AvaNaturalConversationPolicy:
    SHORT_INPUT = re.compile(
        r"^(?:haha+|lol+|nice|always|yes(?:\s+babe)?|m+m+|okay(?:\s+babe)?|[\W_]+)$",
        re.I | re.UNICODE,
    )
    RECIPROCAL_CLAIM = re.compile(
        r"\b(?:love\s+you\s+too|i(?:'m|\s+am)\s+in\s+love\s+with\s+you|"
        r"i(?:'m|\s+am)\s+yours|always\s+your\s+girl|you(?:'re|\s+are)\s+mine|"
        r"you\s+own\s+me|i\s+belong\s+to\s+you|you(?:'re|\s+are)\s+my\s+man|"
        r"my\s+boyfriend|we\s+belong\s+together)\b",
        re.I,
    )
    SEXUAL_ELABORATION = re.compile(
        r"\b(?:fuck(?:ing)?\s+you|make\s+love\s+to\s+you|what\s+i(?:'d|\s+would)\s+do\s+to\s+you|"
        r"between\s+your\s+legs|make\s+you\s+(?:cum|come)|ride\s+you)\b",
        re.I,
    )
    HOOK = re.compile(
        r"\b(?:is\s+that\s+all|saving\s+some\s+for\s+later|what\s+comes\s+next|"
        r"where\s+this\s+is\s+going|where\s+this\s+goes|more\s+to\s+discover|"
        r"you\s+still\s+haven't\s+seen|keeps?\s+things\s+interesting)\b",
        re.I,
    )
    COMMERCIAL_TEASE = re.compile(
        r"\b(?:i(?:'ve|\s+have)\s+got\s+(?:something|a\s+(?:pic|photo))\s+(?:special|private)|"
        r"i\s+want\s+to\s+show\s+you\s+something|maybe\s+i(?:'ll|\s+will)\s+show\s+you\s+more|"
        r"you\s+haven't\s+seen\s+my\s+dangerous\s+side)\b", re.I,
    )
    FUNCTIONS = {
        "CURIOSITY_HOOK": re.compile(
            r"\b(?:making\s+me\s+curious|got\s+me\s+(?:wondering|curious)|"
            r"i(?:'m|\s+am)\s+intrigued|keeping\s+things\s+interesting|"
            r"can't\s+decide\s+if|curious\s+what)\b", re.I),
        "TEMPTATION_HOOK": re.compile(
            r"\b(?:tempting\s+me|you(?:'re|\s+are)\s+tempting|dangerous\s+side|"
            r"turning\s+up\s+the\s+heat|the\s+mood)\b", re.I),
        "RELATIONSHIP_HOOK": re.compile(
            r"\b(?:between\s+us|where\s+this\s+(?:is\s+going|goes)|"
            r"what\s+comes\s+next|whole\s+adventure|door\s+is\s+open)\b", re.I),
    }

    @classmethod
    def function(cls, text: str) -> str:
        for name, pattern in cls.FUNCTIONS.items():
            if pattern.search(text or ""):
                return name
        return "ACKNOWLEDGEMENT" if "?" not in (text or "") else "QUESTION"

    @staticmethod
    def _relationship_authorized(diagnostics: dict) -> bool:
        # Existing canonical relationship facts describe bounded context; none
        # represents mutual romantic commitment or exclusivity authority.
        return False

    @staticmethod
    def _premium_sexual_authorized(diagnostics: dict) -> bool:
        authority = dict(diagnostics.get("premiumSextingAuthority") or {})
        return authority.get("authorized") is True and bool(authority.get("evidence"))

    @staticmethod
    def _warm_fallback(customer_text: str) -> str:
        lowered = (customer_text or "").lower()
        if "love" in lowered or "adore" in lowered:
            return "That's really sweet of you ❤️"
        if "mine" in lowered or "my girl" in lowered or "claim" in lowered or "own" in lowered:
            return "You're cute when you're bold 😘"
        return "You're sweet 😘"

    def evaluate(self, *, customer_text: str, candidate: str,
                 diagnostics: dict | None = None,
                 recent_ava_responses=(), attention: str = "NORMAL") -> NaturalConversationDecision:
        diagnostics = dict(diagnostics or {})
        original = str(candidate or "").strip()
        text = original
        reasons: list[str] = []
        function = self.function(text)
        relationship_authorized = self._relationship_authorized(diagnostics)

        if self.RECIPROCAL_CLAIM.search(text) and not relationship_authorized:
            reasons.append("UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM")
            text = self._warm_fallback(customer_text)

        if self.SEXUAL_ELABORATION.search(text) and not self._premium_sexual_authorized(diagnostics):
            reasons.append("EXCESSIVE_FLIRT_ESCALATION")
            text = "You're bold 😘"

        sales_decision = str(
            diagnostics.get("customer_sales_decision")
            or diagnostics.get("customerSalesDecision")
            or diagnostics.get("decision") or ""
        ).upper()
        commercial_tease_authorized = bool(
            sales_decision in {"PRESENT_OFFER", "BUILD_INTEREST"}
            or diagnostics.get("paidPresentationAuthorized") is True
            or diagnostics.get("commercialTeaseAuthorized") is True
        )
        if self.COMMERCIAL_TEASE.search(text) and not commercial_tease_authorized:
            reasons.append("UNAUTHORIZED_COMMERCIAL_TEASE")
            text = self._warm_fallback(customer_text)

        recent_functions = [self.function(str(item or "")) for item in recent_ava_responses][-6:]
        if function in self.FUNCTIONS and recent_functions.count(function) >= 2:
            reasons.append("REPEATED_FLIRT_FUNCTION")
            text = self._warm_fallback(customer_text)
        elif function in self.FUNCTIONS and sum(
                item in self.FUNCTIONS for item in recent_functions) >= 2:
            reasons.append("EXCESSIVE_FLIRT_ESCALATION")
            text = self._warm_fallback(customer_text)

        if self.SHORT_INPUT.fullmatch((customer_text or "").strip()) and (
                "?" in text or self.HOOK.search(text) or len(text.split()) > 12):
            reasons.append("SHORT_INPUT_OVEREXPANSION")
            text = "😘" if re.fullmatch(r"[\W_]+", (customer_text or "").strip()) else "You're sweet 😘"

        if attention in {"LOWER_PRIORITY", "MINIMAL_NURTURE"} and len(text.split()) > 10:
            reasons.append("ATTENTION_EXPANSION_RESTRAINT")
            text = self._warm_fallback(customer_text)

        final_function = self.function(text)
        return NaturalConversationDecision(
            text=text, repaired=text != original, reasons=tuple(dict.fromkeys(reasons)),
            energy="MATCH_ENERGY" if not relationship_authorized else "CONTEXT_AUTHORIZED",
            function=final_function,
        )

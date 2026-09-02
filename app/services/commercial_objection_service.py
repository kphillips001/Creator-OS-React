"""Deterministic normalization of current-turn commercial objections."""
from __future__ import annotations

import re
from types import MappingProxyType

from app.models.commercial_objection import (
    CommercialObjection,
    CommercialObjectionType,
)


class CommercialObjectionService:
    """Classify scope and recovery authority; never selects or mutates commerce."""

    PAYMENT = re.compile(
        r"\b(?:link (?:doesn['’]?t|does not) work|payment failed|"
        r"(?:it|checkout) won['’]?t let me buy|checkout (?:is )?broken|"
        r"can['’]?t (?:pay|checkout)|payment (?:is )?pending)\b", re.I)
    TRUST = re.compile(
        r"\b(?:is this (?:real|legit|safe)|don['’]?t trust|scam|need help|support)\b", re.I)
    GLOBAL = re.compile(
        r"\b(?:stop asking|not buying anything|not interested|don['’]?t want anything|"
        r"leave me alone|stop (?:trying to )?sell(?:ing)?|no more offers)\b|^\s*(?:no|nah|nope)\s*[.!?]*$", re.I)
    HESITATION = re.compile(
        r"\b(?:maybe later|maybe i(?:'ll| will)|let me think|not right now|"
        r"maybe another time|i might|not sure|probably|perhaps)\b", re.I)
    COMMERCIAL_HESITATION_LINK = re.compile(
        r"\b(?:buy|buying|purchase|purchasing|offer|price|pay|payment|checkout|"
        r"unlock|unlocking|paid content|ppv|that one|this one|get it|want it)\b",
        re.I,
    )
    PRICE = re.compile(
        r"\b(?:too expensive|too much|that['’]?s a lot|anything cheaper|something cheaper|"
        r"can['’]?t (?:spend|afford) (?:that|this) much|for less|lower price|cheaper one)\b", re.I)
    DISCOUNT = re.compile(
        r"\b(?:give (?:it|me)(?: to me)? for \$?\d+|give me a discount|"
        r"make it cheaper|best price|do (?:it )?for \$?\d+)\b", re.I)
    SOFT_PRICE = re.compile(
        r"\b(?:more than (?:i )?(?:expected|wanted to spend)|"
        r"(?:a little|a bit|way) more than (?:i )?expected)\b",
        re.I,
    )
    CHEAPER_PRODUCT = re.compile(
        r"\b(?:anything cheaper|something cheaper|cheaper one|for less|lower price)\b",
        re.I,
    )
    BUDGET = re.compile(
        r"\b(?:i (?:really )?only have|i can['’]?t spend more than|"
        r"i(?:'ve| have) got(?: like)?|anything around|my budget is)\s*"
        r"\$?(\d+(?:\.\d{1,2})?)\b", re.I)
    CONTENT = re.compile(
        r"\b(?:not (?:really )?into that|got something else|anything different|"
        r"something different|don['’]?t like that kind|not that one|not that kind|"
        r"anything hotter|something hotter|more teasing)\b", re.I)
    PRODUCT = re.compile(r"\b(?:different (?:one|product)|another one instead)\b", re.I)

    def evaluate(self, *, message: str, context: dict | None = None) -> CommercialObjection:
        text = str(message or "").strip()
        values = dict(context or {})
        previous = dict(values.get("sales_progression") or {})
        prior_attempts = int(previous.get("recoveryAttemptCount") or 0)

        if self.PAYMENT.search(text):
            return self._result(CommercialObjectionType.PAYMENT_TECHNICAL,
                                strength="STRONG", current=True, selling=False,
                                authoritative=True, alternative=False,
                                evidence=("PAYMENT_OR_LINK_FAILURE_LANGUAGE",))
        if self.TRUST.search(text):
            return self._result(CommercialObjectionType.TRUST_OR_SUPPORT,
                                strength="STRONG", current=False, selling=False,
                                authoritative=True, alternative=False,
                                evidence=("TRUST_OR_SUPPORT_LANGUAGE",))
        if self.GLOBAL.search(text) or (
            prior_attempts >= 1 and re.search(
                r"^\s*(?:still too much|still no|no thanks)\b", text, re.I
            )
        ):
            return self._result(CommercialObjectionType.GLOBAL_DECLINE,
                                strength="STRONG", current=False, selling=False,
                                authoritative=False, alternative=False,
                                evidence=("GLOBAL_OR_REPEATED_DECLINE",))
        budget = self.BUDGET.search(text)
        if budget:
            amount_minor = int(round(float(budget.group(1)) * 100))
            # A newly supplied hard ceiling is materially new evidence even
            # after one value-defense turn. It can authorize one different
            # product; it never changes the original product's price.
            allowed = True
            return self._result(
                CommercialObjectionType.BUDGET_LIMIT, strength="STRONG",
                current=True, selling=allowed, authoritative=False,
                alternative=allowed, evidence=("EXPLICIT_BUDGET_CEILING",),
                constraints={"maximumPriceMinor": amount_minor,
                             "priceRecovery": True},
                recovery_strategy="ALTERNATIVE_PRODUCT",
                budget_constraint_minor=amount_minor,
            )
        if self.DISCOUNT.search(text):
            return self._result(
                CommercialObjectionType.DISCOUNT_REQUEST, strength="MODERATE",
                current=True, selling=prior_attempts < 1, authoritative=True,
                alternative=False,
                evidence=("DISCOUNT_NEGOTIATION_LANGUAGE",),
                recovery_strategy="VALUE_DEFENSE",
                negative_contact_authorized=prior_attempts < 1,
            )
        if self.CHEAPER_PRODUCT.search(text):
            allowed = prior_attempts < 1
            return self._result(
                CommercialObjectionType.PRICE_RESISTANCE, strength="MODERATE",
                current=True, selling=allowed, authoritative=False,
                alternative=allowed,
                evidence=("EXPLICIT_CHEAPER_PRODUCT_REQUEST",),
                constraints={"priceRecovery": True},
                recovery_strategy="ALTERNATIVE_PRODUCT",
            )
        if (self.HESITATION.search(text)
                and self.COMMERCIAL_HESITATION_LINK.search(text)):
            allowed = prior_attempts < 1
            return self._result(CommercialObjectionType.TEMPORARY_HESITATION,
                                strength="MODERATE", current=True, selling=allowed,
                                authoritative=True, alternative=False,
                                evidence=("TEMPORARY_DELAY_LANGUAGE",),
                                recovery_strategy="VALUE_DEFENSE",
                                negative_contact_authorized=allowed)
        if self.SOFT_PRICE.search(text) or self.PRICE.search(text):
            allowed = prior_attempts < 1
            return self._result(CommercialObjectionType.PRICE_RESISTANCE,
                                strength="MODERATE", current=True,
                                selling=allowed, authoritative=True,
                                alternative=False,
                                evidence=("PRICE_RESISTANCE_LANGUAGE",),
                                constraints={"priceRecovery": True},
                                recovery_strategy="VALUE_DEFENSE",
                                negative_contact_authorized=allowed)
        if self.CONTENT.search(text):
            allowed = prior_attempts < 1
            preference = (
                "HOTTER" if re.search(r"\bhotter\b", text, re.I) else
                "MORE_TEASING" if re.search(r"\bmore teasing\b", text, re.I)
                else None
            )
            return self._result(CommercialObjectionType.CONTENT_MISMATCH,
                                strength="MODERATE", current=True,
                                selling=allowed, authoritative=False,
                                alternative=allowed,
                                evidence=("CONTENT_MISMATCH_LANGUAGE",),
                                constraints={"contentPreference": preference})
        if self.PRODUCT.search(text):
            allowed = prior_attempts < 1
            return self._result(CommercialObjectionType.PRODUCT_REJECTION,
                                strength="MODERATE", current=True,
                                selling=allowed, authoritative=False,
                                alternative=allowed,
                                evidence=("PRODUCT_REJECTION_LANGUAGE",))
        return self._result(CommercialObjectionType.NONE, strength="NONE",
                            current=False, selling=True, authoritative=True,
                            alternative=False, pressure=False)

    @staticmethod
    def _result(kind, *, strength, current, selling, authoritative,
                alternative, evidence=(), constraints=None, pressure=True,
                recovery_strategy="NONE", negative_contact_authorized=False,
                budget_constraint_minor=None):
        return CommercialObjection(
            objection_type=kind, strength=strength,
            current_product_scoped=current, continue_selling=selling,
            current_offer_authoritative=authoritative,
            consider_alternative=alternative, pressure_decrease=pressure,
            evidence=tuple(evidence),
            selector_constraints=MappingProxyType(dict(constraints or {})),
            recovery_strategy=recovery_strategy,
            negative_contact_authorized=negative_contact_authorized,
            budget_constraint_minor=budget_constraint_minor,
        )

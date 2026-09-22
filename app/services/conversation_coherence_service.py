from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class ConversationCoherenceProjection:
    resolved: bool
    resolved_customer_meaning: str | None = None
    persona_domain: str | None = None
    turn_obligations: tuple[str, ...] = ()
    failure_reason: str | None = None

    def diagnostics(self, *, operation_id: str | None = None) -> dict[str, Any]:
        return {
            "unresolvedAntecedentDetected": bool(operation_id),
            "unresolvedAntecedentOperationId": operation_id,
            "clarificationResolved": self.resolved,
            "resolvedCustomerMeaning": self.resolved_customer_meaning,
            "resolvedPersonaDomain": self.persona_domain,
            "resolvedTurnObligations": list(self.turn_obligations),
            "semanticRelevanceSatisfied": None,
            "semanticRelevanceFailureReason": self.failure_reason,
        }


class ConversationCoherenceService:
    """Bounded projection of unresolved meaning; never mutates an operation."""

    MAX_AGE = timedelta(minutes=10)

    @classmethod
    def resolve(cls, *, current_text: str, antecedent: dict[str, Any] | None,
                now: datetime | None = None) -> ConversationCoherenceProjection:
        if not antecedent:
            return ConversationCoherenceProjection(False)
        created = antecedent.get("inbound_received_at")
        clock = now or datetime.now(timezone.utc)
        if created is None or clock - created > cls.MAX_AGE:
            return ConversationCoherenceProjection(False, failure_reason="ANTECEDENT_EXPIRED")
        obligations = tuple(antecedent.get("unsatisfied_obligations") or ())
        if not ({"ANSWER_DIRECT_QUESTION", "ANSWER_DIRECT_PERSONAL_QUESTION"}
                & set(obligations)):
            return ConversationCoherenceProjection(False, failure_reason="NO_UNRESOLVED_QUESTION")
        current = cls._clean(current_text)
        prior = cls._clean(antecedent.get("inbound_message_text"))
        if not current or not prior:
            return ConversationCoherenceProjection(False, failure_reason="MISSING_TEXT")
        resolved, domain = cls._resolve_pair(prior, current)
        if not resolved:
            return ConversationCoherenceProjection(False, failure_reason="NO_PLAUSIBLE_ANTECEDENT")
        return ConversationCoherenceProjection(
            True, resolved_customer_meaning=resolved, persona_domain=domain,
            turn_obligations=("ANSWER_DIRECT_QUESTION",),
        )

    @staticmethod
    def _clean(value: Any) -> str:
        return " ".join(str(value or "").replace("…", " ").split()).strip()

    @classmethod
    def _resolve_pair(cls, prior: str, current: str) -> tuple[str | None, str | None]:
        p, c = prior.lower(), current.lower().strip(" .!?")
        work = bool(re.fullmatch(
            r"(?:i mean(?:t)? )?(?:for work|work-wise|professionally)(?:,? (?:that is|though|i mean))?",
            c,
        ))
        if work and re.search(r"\b(?:do you|what|anything|content|job|work)\b", p):
            if re.search(r"\bcontent\b", p):
                return "What else do you do for work besides content?", "OCCUPATION_WORK"
            return f"{prior.rstrip('?')} for work?", "OCCUPATION_WORK"
        fun = bool(re.fullmatch(r"(?:i mean )?for fun(?:,? i mean)?", c))
        match = re.search(r"\bdo you\s+([a-z][a-z -]{1,40})\??$", p)
        if fun and match:
            return f"Do you {match.group(1)} for fun?", "INTERESTS_LIFESTYLE"
        photos = bool(re.fullmatch(r"mostly photos", c))
        if photos and re.search(r"\b(?:make|create|post|do)\s+content\b", p):
            return "Is the content you make mostly photos?", "CONTENT_FORMAT"
        return None, None

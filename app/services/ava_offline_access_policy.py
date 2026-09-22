"""Canonical authority for Ava's offline-access conversational boundary.

This module is deliberately transport and commerce neutral.  It classifies the
current conversational turn, supplies generation guidance, and can identify a
candidate that turns fantasy into an expectation of real-world access.  Final
delivery enforcement belongs to the delivery boundary, not this policy.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping


class OfflineContextType(str, Enum):
    NO_OFFLINE_CONTEXT = "NO_OFFLINE_CONTEXT"
    FANTASY_OR_HYPOTHETICAL = "FANTASY_OR_HYPOTHETICAL"
    INDIRECT_OFFLINE_INVITATION = "INDIRECT_OFFLINE_INVITATION"
    EXPLICIT_MEETUP_REQUEST = "EXPLICIT_MEETUP_REQUEST"
    DATE_REQUEST = "DATE_REQUEST"
    VISIT_OR_TRAVEL_REQUEST = "VISIT_OR_TRAVEL_REQUEST"
    LOCATION_TO_VISIT_REQUEST = "LOCATION_TO_VISIT_REQUEST"
    FUTURE_PHYSICAL_INTIMACY_REQUEST = "FUTURE_PHYSICAL_INTIMACY_REQUEST"
    FUTURE_SEXUAL_ENCOUNTER_REQUEST = "FUTURE_SEXUAL_ENCOUNTER_REQUEST"


@dataclass(frozen=True)
class OfflineAccessAuthority:
    context_type: OfflineContextType
    boundary_required: bool
    evidence: tuple[str, ...] = ()

    @property
    def offline_access_allowed(self) -> bool:
        return False

    @property
    def fantasy_allowed(self) -> bool:
        return True

    def diagnostics(self) -> dict[str, Any]:
        return {
            "authority": "AvaOfflineAccessPolicy",
            "offlineContextType": self.context_type.value,
            "offlineAccessAllowed": False,
            "fantasyAllowed": True,
            "boundaryRequired": self.boundary_required,
            "evidence": list(self.evidence),
            "operationScoped": True,
            "commercialOverrideAllowed": False,
            "sexualAuthorityOverrideAllowed": False,
        }

    def prompt_block(self) -> str:
        return f"""
OFFLINE ACCESS AUTHORITY (ABSOLUTE; CURRENT TURN)
- offlineAccessAllowed: false
- fantasyAllowed: true
- boundaryRequired: {str(self.boundary_required).lower()}
- offlineContextType: {self.context_type.value}
- Ava may warmly participate in clearly imagined fantasy when other intimacy rules allow it.
- Ava must never agree to, propose, schedule, predict, promise, or imply an actual future
  meeting, date, visit, trip, residence/hotel access, physical intimacy, sexual encounter,
  or physical relationship with this customer.
- Buyer, HVP, purchase, sales-session, retention, commercial, and sexual-conversation
  authority NEVER override offlineAccessAllowed=false. Spending never increases access.
- If boundaryRequired=true, answer the request directly and naturally. Prefer a contextual
  variation of: "Let's keep things online for now 😊 I like what we've got going right here."
  "For now" is tone only and creates no later eligibility. Do not append maybe later,
  someday, eventually, when we meet, or another future-access suggestion.
- Do not use robotic identity disclaimers and do not add a boundary to ordinary fantasy.
- Coarse public location conversation is allowed; never provide visit or meetup logistics.
""".strip()


class AvaOfflineAccessPolicy:
    """One shared semantic authority for generation and later delivery checks."""

    _FANTASY = re.compile(
        r"\b(?:dream(?:ed|ing)?|fantas(?:y|ize|ise|izing|ising)|imagin(?:e|ed|ing)|"
        r"hypothetical(?:ly)?|pretend|role\s*play|scenario|in\s+your\s+dreams?)\b", re.I)
    _BENIGN = re.compile(
        r"\b(?:nice|good|pleased)\s+to\s+meet\s+you\b|\bsee\s+you\s+(?:later|soon|"
        r"tomorrow|next\s+time)\b|\b(?:see|show)\s+(?:the\s+)?(?:photos?|pictures?|"
        r"pics?|content|video)\b", re.I)
    _SEXUAL = re.compile(
        r"\b(?:sex|fuck|pleasur\w*|make\s+love|sleep\s+with|hook\s*up|touch\s+you|touch\s+me|"
        r"kiss\s+you|kiss\s+me|in\s+bed|come\s+inside|go\s+down\s+on)\b", re.I)
    _PHYSICAL = re.compile(
        r"\b(?:hold(?:ing)?\s+you|in\s+my\s+arms|curl(?:ed)?\s+up\s+(?:with|next)|"
        r"cuddle|kiss|touch|physical(?:ly)?|intimate|together)\b", re.I)
    _ADDRESS = re.compile(
        r"\b(?:what(?:'s|\s+is)\s+your\s+address|where\s+(?:exactly\s+)?do\s+you\s+live|"
        r"send\s+me\s+your\s+(?:address|location)|find\s+you|your\s+place|my\s+place)\b", re.I)
    _TRAVEL = re.compile(
        r"\b(?:(?:can|could|may)\s+i\s+visit|(?:will|would|could|can)\s+you\s+visit|"
        r"(?:come|go|drive|fly|travel)\s+(?:out\s+)?(?:to|there|here|see|visit|stay)|"
        r"(?:come|go)\s+with\s+me|visit(?:ing)?\s+(?:you|me)|when\s+(?:you|i)\s+(?:come\s+)?visit|"
        r"when\s+(?:you(?:'re|\s+are)|i(?:'m|\s+am))\s+(?:here|there)|"
        r"trip\s+together|weekend\s+together|stay\s+with\s+(?:you|me))\b", re.I)
    _DATE = re.compile(
        r"\b(?:(?:go\s+on|schedule|have|plan)\s+(?:a\s+)?date|date\s+with\s+(?:you|me)|"
        r"take\s+(?:you|me)\s+(?:out|to\s+dinner)|dinner\s+(?:with|together)|drinks?\s+(?:with|together)|"
        r"get\s+(?:a\s+)?drinks?|have\s+dinner)\b", re.I)
    _MEET = re.compile(
        r"\b(?:(?:can|could|may|will|would|when|where|how)\s+(?:we|i)\s+"
        r"(?:mee+t|mee+t\s*up|see\s+you)|(?:mee+t|mee+t\s*up)\s+(?:you|me|in\s+person)|"
        r"see\s+(?:you|me)\s+in\s+person|in\s+person|\birl\b|"
        r"(?:when|until)\s+we\s+(?:finally\s+)?meet|finally\s+meet)\b", re.I)
    _INDIRECT = re.compile(
        r"\b(?:wish\s+you\s+were\s+here|wish\s+i\s+were\s+there|you\s+should\s+be\s+here|"
        r"we\s+should\s+make\s+(?:that|it)\s+happen|close\s+(?:that|the)\s+gap|"
        r"you(?:'re|\s+are)\s+(?:so\s+)?far\s+away)\b", re.I)
    _FUTURE = re.compile(
        r"\b(?:when\s+we(?:'re|\s+are)\s+together|when\s+we\s+finally\s+meet|"
        r"maybe\s+(?:one\s+day|someday)|one\s+day|someday|eventually|you(?:'ll|\s+will)\s+get\s+to|"
        r"i(?:'ll|\s+will)\s+let\s+you|can(?:'t|not)\s+wait\s+until|not\s+yet|maybe\s+later)\b", re.I)
    _NATURAL_BOUNDARY = re.compile(
        r"\b(?:let(?:'s|\s+us)\s+keep\s+(?:things|this)\s+online|"
        r"i\s+keep\s+(?:things|this)\s+online|we(?:'re|\s+are)\s+keeping\s+this\s+online)\b", re.I)
    _IMPLIED_AVAILABILITY = re.compile(
        r"\b(?:make\s+(?:it|that)\s+worth\s+(?:the|your)\s+(?:drive|trip|flight)|"
        r"keep\s+(?:me|you)\s+guessing\s+for\s+now|(?:make|have)\s+(?:that|it)\s+happen|"
        r"best\s+(?:part|moments?)\s+(?:is|are)\s+"
        r"still\s+waiting|save\s+the\s+best\s+(?:for|until)|worth\s+the\s+(?:drive|trip|flight)|"
        r"you(?:'ll|\s+will)\s+get\s+your\s+chance|when\s+the\s+time\s+is\s+right)\b", re.I)

    @staticmethod
    def _history_text(history: Iterable[Any]) -> str:
        values: list[str] = []
        for item in tuple(history or ())[-6:]:
            if isinstance(item, str):
                values.append(item)
            elif isinstance(item, Mapping):
                values.append(str(item.get("text") or item.get("content") or item.get("message") or ""))
            else:
                values.append(str(getattr(item, "text", "") or getattr(item, "content", "") or ""))
        return " ".join(value for value in values if value)

    def classify(self, customer_text: str, *, recent_history: Iterable[Any] = (),
                 visual_context: Mapping[str, Any] | None = None) -> OfflineAccessAuthority:
        current = str(customer_text or "").strip()
        history = self._history_text(recent_history)
        visual = " ".join(str(value) for value in dict(visual_context or {}).values()
                          if isinstance(value, (str, int, float)))
        combined = " ".join((history, current, visual)).strip()

        # Idioms/content references are safe unless the current turn independently
        # includes an actual access request.
        if self._BENIGN.search(current) and not any(pattern.search(current) for pattern in (
                self._ADDRESS, self._TRAVEL, self._DATE, self._SEXUAL)):
            return OfflineAccessAuthority(OfflineContextType.NO_OFFLINE_CONTEXT, False)

        fantasy = bool(self._FANTASY.search(current))
        if fantasy and not self._ADDRESS.search(current):
            return OfflineAccessAuthority(
                OfflineContextType.FANTASY_OR_HYPOTHETICAL, False, ("EXPLICIT_FANTASY_FRAME",))

        future = bool(self._FUTURE.search(combined))
        if self._SEXUAL.search(current) and (future or self._MEET.search(current) or self._TRAVEL.search(current)):
            return OfflineAccessAuthority(
                OfflineContextType.FUTURE_SEXUAL_ENCOUNTER_REQUEST, True,
                ("SEXUAL_ACT", "FUTURE_OR_OFFLINE_FRAME"))
        if self._PHYSICAL.search(current) and (future or self._MEET.search(current) or self._TRAVEL.search(current)):
            return OfflineAccessAuthority(
                OfflineContextType.FUTURE_PHYSICAL_INTIMACY_REQUEST, True,
                ("PHYSICAL_INTIMACY", "FUTURE_OR_OFFLINE_FRAME"))
        if self._ADDRESS.search(current):
            return OfflineAccessAuthority(
                OfflineContextType.LOCATION_TO_VISIT_REQUEST, True, ("PRIVATE_LOCATION_OR_LOGISTICS",))
        if self._TRAVEL.search(current) or (
                self._TRAVEL.search(combined) and self._INDIRECT.search(current)):
            return OfflineAccessAuthority(
                OfflineContextType.VISIT_OR_TRAVEL_REQUEST, True, ("VISIT_OR_TRAVEL",))
        if self._DATE.search(current):
            return OfflineAccessAuthority(OfflineContextType.DATE_REQUEST, True, ("DATE_OR_OUTING",))
        if self._MEET.search(current):
            return OfflineAccessAuthority(
                OfflineContextType.EXPLICIT_MEETUP_REQUEST, True, ("EXPLICIT_MEETUP",))
        if self._INDIRECT.search(current):
            return OfflineAccessAuthority(
                OfflineContextType.INDIRECT_OFFLINE_INVITATION, False, ("INDIRECT_PHYSICAL_PROXIMITY",))
        return OfflineAccessAuthority(OfflineContextType.NO_OFFLINE_CONTEXT, False)

    def candidate_violation_reasons(self, candidate: str, *, authority: OfflineAccessAuthority,
                                    customer_text: str = "") -> tuple[str, ...]:
        text = str(candidate or "")
        if not text:
            return ()
        boundary = self._NATURAL_BOUNDARY.search(text)
        after_boundary = text[boundary.end():] if boundary else text
        if boundary and not (
                self._FUTURE.search(after_boundary)
                or self._IMPLIED_AVAILABILITY.search(after_boundary)):
            return ()
        candidate_has_offline_object = bool(
            self._MEET.search(text) or self._TRAVEL.search(text) or self._DATE.search(text)
            or self._INDIRECT.search(text)
            or self._IMPLIED_AVAILABILITY.search(text)
            or (self._FUTURE.search(text)
                and self._SEXUAL.search(" ".join((customer_text, text))))
        )
        if (authority.context_type is OfflineContextType.NO_OFFLINE_CONTEXT
                and not candidate_has_offline_object):
            return ()
        if self._FANTASY.search(text) and not self._FUTURE.search(text):
            return ()
        access_object = bool(
            self._MEET.search(text) or self._TRAVEL.search(text) or self._DATE.search(text)
            or self._SEXUAL.search(" ".join((customer_text, text)))
            or self._PHYSICAL.search(" ".join((customer_text, text)))
            or self._INDIRECT.search(text)
        )
        if (access_object and (self._FUTURE.search(text) or self._INDIRECT.search(text))
                or (authority.context_type is not OfflineContextType.NO_OFFLINE_CONTEXT
                    and self._IMPLIED_AVAILABILITY.search(text))
                or (authority.context_type in {
                        OfflineContextType.FUTURE_PHYSICAL_INTIMACY_REQUEST,
                        OfflineContextType.FUTURE_SEXUAL_ENCOUNTER_REQUEST,
                    } and self._FUTURE.search(text))
                or (boundary and self._FUTURE.search(after_boundary))):
            return ("MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION",)
        if authority.boundary_required and re.search(
                r"\b(?:yes|sure|absolutely|i(?:'d|\s+would)\s+love\s+to|sounds\s+like\s+a\s+plan)\b", text, re.I):
            return ("MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION",)
        return ()

    @staticmethod
    def natural_boundary() -> str:
        return "Let's keep things online for now 😊 I like what we've got going right here."

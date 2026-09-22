"""Canonical dual-clock context for Ava conversations."""
from __future__ import annotations

from datetime import datetime, timezone
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class AvaTemporalContextService:
    AVA_TIMEZONE = "America/New_York"
    _REFERENCE = re.compile(
        r"\b(?:this\s+morning|this\s+afternoon|this\s+evening|"
        r"later\s+tonight|morning|afternoon|evening|tonight|night|today|day|late|early)\b",
        re.I,
    )
    _ASSUMED_DAYPART = {
        "morning": "MORNING",
        "this morning": "MORNING",
        "afternoon": "AFTERNOON",
        "this afternoon": "AFTERNOON",
        "evening": "EVENING",
        "this evening": "EVENING",
        "night": "NIGHT",
        "tonight": "NIGHT",
        "later tonight": "NIGHT",
    }
    _INBOUND_SALUTATION = re.compile(
        r"^\s*(?:good\s+)?(?P<daypart>morning|afternoon|evening)\b", re.I,
    )
    _DURATION = re.compile(
        r"\b(?:from\s+(?:morning|afternoon|evening|night)\s+to\s+"
        r"(?:morning|afternoon|evening|night)|all\s+(?:morning|afternoon|"
        r"evening|night|day)|(?:morning|afternoon|evening|night)\s+(?:through|"
        r"until|till)\s+(?:morning|afternoon|evening|night))\b", re.I,
    )
    _FUTURE_PLANNING = re.compile(
        r"\b(?:tomorrow|next\s+(?:morning|afternoon|evening|night)|later\s+"
        r"(?:today|tonight|this\s+(?:morning|afternoon|evening)))\b", re.I,
    )
    _CUSTOMER_ELAPSED = re.compile(
        r"\b(?:i|we|my|our)\b[^.!?]{0,80}\b(?:this\s+)?"
        r"(?P<elapsed>morning|afternoon|evening|night)\b", re.I,
    )
    _RESPONSE_SALUTATION = re.compile(
        r"^\s*(?:good\s+)?(?P<daypart>morning|afternoon|evening)"
        r"(?=\b|[!,.\u2026])", re.I,
    )
    _RESPONSE_SIGNOFF = re.compile(
        r"(?:^|[.!?]\s*)(?:good\s*night|night|sweet\s+dreams)"
        r"(?=\b|[!,.\u2026])", re.I,
    )

    def __init__(self, *, clock=lambda: datetime.now(timezone.utc)):
        self._clock = clock

    def build(self, *, customer_timezone: str | None = None) -> dict:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        ava = now.astimezone(ZoneInfo(self.AVA_TIMEZONE))
        result = {
            "runtimeUtc": now.astimezone(timezone.utc).isoformat(),
            "avaTimezone": self.AVA_TIMEZONE,
            "avaLocalTime": ava.isoformat(),
            "avaDayOfWeek": ava.strftime("%A"),
            "avaDaypart": self._daypart(ava.hour),
            "customerTimezone": None,
            "customerLocalTime": None,
            "customerDayOfWeek": None,
            "customerDaypart": None,
        }
        if customer_timezone:
            try:
                customer = now.astimezone(ZoneInfo(customer_timezone))
            except ZoneInfoNotFoundError:
                pass
            else:
                result.update({"customerTimezone": customer_timezone,
                    "customerLocalTime": customer.isoformat(),
                    "customerDayOfWeek": customer.strftime("%A"),
                    "customerDaypart": self._daypart(customer.hour)})
        return result

    @classmethod
    def classify_customer_reference(cls, message: str, context: dict) -> dict:
        """Separate customer wording from the authoritative Ava clock."""
        value = str(message or "").replace("â€™", "'").replace("’", "'")
        duration_match = cls._DURATION.search(value)
        future_planning_match = cls._FUTURE_PLANNING.search(value)
        elapsed_match = cls._CUSTOMER_ELAPSED.search(value)
        salutation_match = cls._INBOUND_SALUTATION.match(value)
        ava_match = re.search(
            r"\b(?:your\s+(?P<owned>morning|afternoon|evening|night|day)|"
            r"you\s+(?:doing|up to).*?(?P<future>later\s+tonight|tonight|morning|"
            r"afternoon|evening|night))\b", value, re.I,
        )
        greeting_match = salutation_match
        match = (duration_match or future_planning_match or elapsed_match
                 or ava_match or greeting_match or cls._REFERENCE.search(value))
        canonical = cls._canonical_daypart(context.get("avaDaypart"))
        temporal_function = (
            "DURATION" if duration_match
            else "FUTURE_PLANNING" if future_planning_match
            else "CUSTOMER_ELAPSED_CONTEXT" if elapsed_match
            else "SALUTATION" if greeting_match
            else "AVA_CURRENT_TIME_REFERENCE" if ava_match
            else "TEMPORAL_REFERENCE" if match
            else "NONE"
        )
        result = {
            "canonicalAvaTimezone": context.get("avaTimezone"),
            "canonicalAvaLocalTime": context.get("avaLocalTime"),
            "canonicalAvaDaypart": canonical,
            "customerTimezone": context.get("customerTimezone"),
            "customerTemporalReferenceDetected": bool(match),
            "customerTemporalReference": match.group(0).lower() if match else None,
            "customerTemporalFunction": temporal_function,
            "customerTemporalReferenceTarget": "NONE",
            "customerAssumedAvaDaypart": None,
            "customerTemporalRelation": "NONE",
            "temporalCompatibility": "NOT_APPLICABLE",
            "temporalMismatchDetected": False,
        }
        if not match:
            return result
        if duration_match:
            reference = duration_match.group(0).lower()
        elif elapsed_match:
            reference = str(elapsed_match.group("elapsed")).lower()
        elif ava_match:
            reference = str(ava_match.group("owned") or ava_match.group("future")).lower()
        elif future_planning_match:
            reference = future_planning_match.group(0).lower()
        elif greeting_match:
            reference = str(greeting_match.group("daypart")).lower()
        else:
            reference = match.group(0).lower()
        lowered = value.lower()
        future = bool(future_planning_match or re.search(r"\b(?:later\s+tonight|what are you doing .*tonight|"
                                r"what will you .*tonight|will you .*tonight)\b", lowered))
        ava_directed = bool(ava_match or greeting_match)
        customer_directed = bool(
            re.search(r"\b(?:i|i'm|i am|my|we|we're|we are)\b", lowered)
            and not ava_directed
        )
        if duration_match:
            target = "GENERAL"
        elif elapsed_match:
            target = "CUSTOMER"
        elif reference in {"day", "today"} and re.search(r"\byour\s+(?:day|today)\b", lowered):
            target = "GENERAL"
        elif ava_match:
            target = "AVA"
        elif future_planning_match:
            target = "GENERAL"
        elif ava_directed:
            target = "AVA"
        elif customer_directed:
            target = "CUSTOMER"
        elif reference in {"day", "today"} or re.search(r"\byour day\b", lowered):
            target = "GENERAL"
        else:
            target = "AMBIGUOUS"
        assumed = cls._ASSUMED_DAYPART.get(reference) if target == "AVA" else None
        relation = "FUTURE" if future else "CURRENT_OR_ELAPSED"
        if duration_match:
            relation = "DURATION"
        elif elapsed_match:
            relation = "ELAPSED"
        if (duration_match or elapsed_match
                or (future_planning_match and target != "AVA")):
            compatibility = "NOT_APPLICABLE"
        elif target != "AVA" or assumed is None:
            compatibility = "NOT_APPLICABLE" if target != "GENERAL" else "BROAD_COMPATIBLE"
        elif future:
            compatibility = "FUTURE_COMPATIBLE"
        elif assumed == canonical:
            compatibility = "MATCH"
        else:
            compatibility = "MISMATCH"
        result.update({
            "customerTemporalReference": reference,
            "customerTemporalReferenceTarget": target,
            "customerAssumedAvaDaypart": assumed,
            "customerTemporalRelation": relation,
            "temporalCompatibility": compatibility,
            "temporalMismatchDetected": compatibility == "MISMATCH",
        })
        return result

    @classmethod
    def is_inbound_salutation(cls, message: str) -> bool:
        """Expose the canonical inbound SALUTATION function to obligation logic."""
        value = str(message or "").replace("â€™", "'").replace("â€™", "'")
        incidental_span = re.search(
            r"^\s*(?:good\s+)?(?:morning|afternoon|evening)\s+to\s+"
            r"(?:morning|afternoon|evening|night)\b",
            value, re.I,
        )
        return bool(
            cls._INBOUND_SALUTATION.match(value)
            and not cls._DURATION.search(value)
            and not incidental_span
        )

    @classmethod
    def evaluate_response(cls, message: str, response: str, context: dict) -> dict:
        turn = cls.classify_customer_reference(message, context)
        value = str(response or "").replace("â€™", "'").replace("’", "'").lower()
        claim = None
        response_function = "NONE"
        salutation = cls._RESPONSE_SALUTATION.match(value)
        signoff = cls._RESPONSE_SIGNOFF.search(value)
        if salutation:
            claim = str(salutation.group("daypart")).upper()
            response_function = "SALUTATION"
        elif signoff:
            claim = "NIGHT"
            response_function = "SIGNOFF"
        elif re.search(r"\b(?:my|this)\s+morning\b|\bmorning\s+(?:for me|over here)\b", value):
            claim = "MORNING"
        elif re.search(r"\b(?:my|this)\s+afternoon\b|\b(?:still|it's|it is)\s+afternoon\b", value):
            claim = "AFTERNOON"
        elif re.search(r"\b(?:my|this)\s+evening\b|\b(?:still|it's|it is)\s+evening\b", value):
            claim = "EVENING"
        elif re.search(r"\bmy\s+night\b|\bsettling\s+in\s+for\s+the\s+night\b|"
                       r"\bwinding\s+down\s+for\s+the\s+night\b", value):
            claim = "NIGHT"
        elif re.search(r"\bmy\s+day\b|\bday's\s+been\b", value):
            claim = "GENERAL_DAY"
        if claim is not None and response_function == "NONE":
            response_function = "CURRENT_TIME_CLAIM"
        canonical = turn["canonicalAvaDaypart"]
        if response_function == "SIGNOFF":
            aligned, reason = True, "CONVERSATIONAL_SIGNOFF"
        elif claim is None:
            aligned, reason = True, "TEMPORALLY_NEUTRAL"
        elif claim == "GENERAL_DAY":
            aligned = not turn["temporalMismatchDetected"]
            reason = ("BROAD_DAY_CLAIM_DOES_NOT_RESOLVE_MISMATCH"
                      if not aligned else "BROAD_DAY_COMPATIBLE")
        else:
            aligned = claim == canonical
            reason = "CANONICAL_DAYPART_MATCH" if aligned else "RESPONSE_DAYPART_CONFLICT"
        source = str(message or "").replace("â€™", "'").lower()
        event_relation = "UNSPECIFIED"
        if re.search(r"\b(?:next\s+friday|tomorrow|later\s+today|later\s+tonight|"
                     r"has (?:his|her|their) .+? (?:friday|tomorrow)|"
                     r"appointment (?:is )?(?:friday|tomorrow|later))\b", source):
            event_relation = "FUTURE_OR_PLANNED"
        elif re.search(r"\b(?:was yesterday|had (?:it|his|her|their) .+? yesterday|"
                       r"had it earlier today|already had)\b", source):
            event_relation = "PAST_OR_COMPLETED"
        elif re.search(r"\b(?:is happening now|at the appointment now|in the appointment)\b", source):
            event_relation = "CURRENT"
        invented_recovery = bool(
            event_relation == "FUTURE_OR_PLANNED"
            and re.search(r"\b(?:recover|recovering|recovered|after vet day|after the appointment|"
                          r"(?:feeling|feel) (?:fine|better|okay) after|"
                          r"wore (?:him|her|them) out|must be tired from|"
                          r"(?:earned|deserv(?:e|ed))[^.!?]{0,40}\bafter\b|"
                          r"(?:appointment|vet visit)[^.!?]{0,30}\b(?:workout|exhausting)\b)", value)
        )
        invented_routine_procedure = bool(
            re.search(r"\b(?:yearly|routine|regular)\s+(?:vet\s+)?(?:appointment|checkup)\b", source)
            and re.search(r"\b(?:(?:get|gets|getting|need|needs|needing) (?:a |the )?shots?|"
                          r"surgery|procedure|sedat(?:e|ed|ion)|medicine|medication)\b", value)
        )
        if invented_recovery or invented_routine_procedure:
            aligned, reason = False, "FUTURE_EVENT_TREATED_AS_COMPLETED"
        return {**turn,
            "responseTemporalClaim": claim or "NONE",
            "responseTemporalFunction": response_function,
            "responseSalutationDaypart": (
                claim if response_function == "SALUTATION" else None
            ),
            "responseTemporalAlignmentSatisfied": aligned,
            "responseTemporalAlignmentReason": reason,
            "customerEventTemporalRelation": event_relation,
            "inventedPostEventState": invented_recovery,
            "inventedRoutineAppointmentDetail": invented_routine_procedure,
        }

    @staticmethod
    def _canonical_daypart(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return {
            "morning": "MORNING", "afternoon": "AFTERNOON",
            "evening": "EVENING", "late night": "NIGHT", "night": "NIGHT",
        }.get(normalized)

    @staticmethod
    def _daypart(hour: int) -> str:
        if 5 <= hour < 12: return "morning"
        if 12 <= hour < 17: return "afternoon"
        if 17 <= hour < 22: return "evening"
        return "late night"

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
        ava_match = re.search(
            r"\b(?:your\s+(?P<owned>morning|afternoon|evening|night|day)|"
            r"you\s+(?:doing|up to).*?(?P<future>later\s+tonight|tonight|morning|"
            r"afternoon|evening|night))\b", value, re.I,
        )
        greeting_match = re.match(
            r"\s*good\s+(?P<greeting>morning|afternoon|evening|night)\b", value, re.I,
        )
        match = ava_match or greeting_match or cls._REFERENCE.search(value)
        canonical = cls._canonical_daypart(context.get("avaDaypart"))
        result = {
            "canonicalAvaTimezone": context.get("avaTimezone"),
            "canonicalAvaLocalTime": context.get("avaLocalTime"),
            "canonicalAvaDaypart": canonical,
            "customerTimezone": context.get("customerTimezone"),
            "customerTemporalReferenceDetected": bool(match),
            "customerTemporalReference": match.group(0).lower() if match else None,
            "customerTemporalReferenceTarget": "NONE",
            "customerAssumedAvaDaypart": None,
            "customerTemporalRelation": "NONE",
            "temporalCompatibility": "NOT_APPLICABLE",
            "temporalMismatchDetected": False,
        }
        if not match:
            return result
        if ava_match:
            reference = str(ava_match.group("owned") or ava_match.group("future")).lower()
        elif greeting_match:
            reference = str(greeting_match.group("greeting")).lower()
        else:
            reference = match.group(0).lower()
        lowered = value.lower()
        future = bool(re.search(r"\b(?:later\s+tonight|what are you doing .*tonight|"
                                r"what will you .*tonight|will you .*tonight)\b", lowered))
        ava_directed = bool(ava_match or greeting_match)
        customer_directed = bool(
            re.search(r"\b(?:i|i'm|i am|my|we|we're|we are)\b", lowered)
            and not ava_directed
        )
        if reference in {"day", "today"} and re.search(r"\byour\s+(?:day|today)\b", lowered):
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
        if target != "AVA" or assumed is None:
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
    def evaluate_response(cls, message: str, response: str, context: dict) -> dict:
        turn = cls.classify_customer_reference(message, context)
        value = str(response or "").replace("â€™", "'").replace("’", "'").lower()
        claim = None
        if re.search(r"\b(?:my|this)\s+morning\b|\bmorning\s+(?:for me|over here)\b", value):
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
        canonical = turn["canonicalAvaDaypart"]
        if claim is None:
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

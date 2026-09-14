"""Display eligibility policy; persistence never implies snapshot visibility."""
from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.conversational_memory_service import ConversationalMemoryService


class CustomerSnapshotPolicy:
    TELEGRAM_ALLOWED = {
        "fact": {"location", "timezone"},
        "pet": {"pet_name", "pet_type", "pet_breed"},
        "entity": None,
        "hobby": None,
        "interest": None,
        "preference": None,
        "routine": None,
        "event": None,
    }
    _SENSITIVE = re.compile(
        r"\b(?:diagnos|medical|doctor|surgery|procedure|therapy|medication|"
        r"sexual|nude|explicit|income|debt|bank|credit card|password|token|"
        r"verification code|social security|street address|home address)\b", re.I,
    )

    @classmethod
    def telegram_eligibility(cls, record: Mapping[str, Any]) -> str | None:
        if record.get("status") != "current":
            return "Superseded"
        category, key = str(record.get("category") or ""), str(record.get("key") or "")
        if category not in cls.TELEGRAM_ALLOWED:
            return "Not snapshot eligible"
        allowed_keys = cls.TELEGRAM_ALLOWED[category]
        if allowed_keys is not None and key not in allowed_keys:
            return "Not snapshot eligible"
        valid, rejected = ConversationalMemoryService._validate_extracted_records(
            [dict(record)],
        )
        if not valid or rejected:
            return "Malformed value"
        value = record.get("value")
        searchable = f"{key} {value}"
        if float(record.get("confidence") or 0) < .80:
            return "Low/ambiguous ownership confidence"
        if key == "location" and re.search(
            r"\d|\b(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|"
            r"drive|dr|apartment|apt|suite)\b", str(value), re.I,
        ):
            return "Sensitive category"
        if cls._SENSITIVE.search(searchable):
            # A pet's ordinary veterinary appointment is allowed; customer
            # health details are not part of the initial snapshot policy.
            if not (category == "event" and isinstance(value, Mapping)
                    and value.get("subject") not in {None, "customer"}
                    and re.search(r"\bvet\b", searchable, re.I)):
                return "Sensitive category"
        if category == "entity":
            if not isinstance(value, Mapping) or not str(value.get("relationship") or "").startswith("customer's "):
                return "Low/ambiguous ownership confidence"
        if category == "event":
            if not isinstance(value, Mapping):
                return "Malformed value"
            status = str(value.get("status") or "").lower()
            if status == "past":
                return "Past event"
            if status != "upcoming":
                return "Not snapshot eligible"
            if not value.get("scheduledFor"):
                return "Malformed value"
        return None

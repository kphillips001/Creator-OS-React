"""Bounded authority for personal-question referents and unknown biography."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


class AutobiographicalQuestionAuthority:
    NAME_ORIGIN = "AUTOBIOGRAPHICAL_NAME_ORIGIN"
    CHILDHOOD_MEMORY = "AUTOBIOGRAPHICAL_CHILDHOOD_MEMORY"

    _NAME_ORIGIN = re.compile(
        r"\b(?:where\s+does\s+(?:your\s+)?name\s+come\s+from|"
        r"how\s+did\s+you\s+get\s+(?:your\s+)?name|"
        r"why\s+are\s+you\s+named\b|story\s+behind\s+(?:your\s+)?name|"
        r"what\s+does\s+(?:your\s+)?name\s+mean\s+to\s+you)\b",
        re.I,
    )
    _ANAPHORIC_NAME_ORIGIN = re.compile(
        r"\b(?:where\s+(?:does|did)\s+it\s+come\s+from|"
        r"where(?:'d|\s+did)\s+it\s+come\s+from|"
        r"is\s+there\s+(?:a\s+)?story\s+behind\s+it|"
        r"how\s+did\s+you\s+get\s+it)\b",
        re.I,
    )
    _COMPETING_REFERENT_AFTER_NAME = re.compile(
        r"\b(?:and|or)\s+(?:(?:your|the|that|this|a|an)\s+)?[a-z][a-z'-]*\b",
        re.I,
    )
    _CHILDHOOD_MEMORY = re.compile(
        r"\b(?:favorite|favourite)\s+childhood\s+memor(?:y|ies)\b", re.I
    )

    @classmethod
    def referent(cls, question: str) -> str | None:
        value = str(question or "").replace("\u2019", "'")
        if cls._NAME_ORIGIN.search(value):
            return cls.NAME_ORIGIN
        # Resolve only a same-turn, immediately preceding explicit ``name``
        # antecedent.  Coordinated noun phrases fail closed because ``it`` can
        # no longer be proven to refer to the name.
        anaphora = cls._ANAPHORIC_NAME_ORIGIN.search(value)
        if anaphora:
            prefix = value[:anaphora.start()]
            names = tuple(re.finditer(r"\bname\b", prefix, re.I))
            if names:
                between = prefix[names[-1].end():]
                if (len(between) <= 120
                        and not cls._COMPETING_REFERENT_AFTER_NAME.search(between)):
                    return cls.NAME_ORIGIN
        if cls._CHILDHOOD_MEMORY.search(value):
            return cls.CHILDHOOD_MEMORY
        return None

    @classmethod
    def canonical_fact(cls, referent: str | None, persona: Any) -> str | None:
        """Return only an explicitly supplied fact for the requested referent."""
        if not referent:
            return None
        values: list[str] = []
        if isinstance(persona, Mapping):
            for key in ("selected_persona_facts", "selected_lifestyle_facts", "stable_public"):
                raw = persona.get(key)
                values.extend(str(item) for item in raw or () if str(item).strip())
            for key in ("name_origin", "childhood_memory"):
                if persona.get(key):
                    values.append(str(persona[key]))
        else:
            for key in ("selected_persona_facts", "selected_lifestyle_facts", "stable_public"):
                values.extend(str(item) for item in getattr(persona, key, ()) or ())
        patterns = {
            cls.NAME_ORIGIN: re.compile(
                r"\b(?:name(?:d)?\s+(?:ava|after)|ava(?:'s)?\s+name|"
                r"name\s+(?:was\s+)?chosen|meaning\s+of\s+(?:her|my)\s+name)\b",
                re.I,
            ),
            cls.CHILDHOOD_MEMORY: re.compile(
                r"\b(?:favorite|favourite)\s+childhood\s+memor(?:y|ies)\b", re.I
            ),
        }
        matcher = patterns.get(referent)
        return next((item for item in values if matcher and matcher.search(item)), None)

    @classmethod
    def projection(cls, question: str, persona: Any = None) -> dict[str, Any]:
        referent = cls.referent(question)
        fact = cls.canonical_fact(referent, persona)
        return {
            "referent": referent,
            "autobiographical": referent is not None,
            "canonicalFactAvailable": fact is not None,
            "canonicalFact": fact,
            "unknownBiographyAuthorized": bool(referent and not fact),
            "authority": "AutobiographicalQuestionAuthority",
        }

    @classmethod
    def truthful_unknown_answer(cls, referent: str | None, response: str) -> bool:
        value = str(response or "").replace("\u2019", "'")
        uncertainty = bool(re.search(
            r"\b(?:i\s+(?:honestly\s+)?don['’]?t\s+(?:really\s+)?(?:know|have|remember)|"
            r"i\s+never\s+(?:knew|heard)|there\s+(?:isn['’]?t|is\s+not)|"
            r"no\s+(?:big|specific|particular|real)\s+(?:story|memory)|"
            r"not\s+(?:sure|something\s+i\s+know))\b",
            value, re.I,
        ))
        if referent == cls.NAME_ORIGIN:
            grounded = bool(re.search(r"\b(?:name|named|story\s+behind\s+it|how\s+i\s+got\s+it)\b", value, re.I))
        elif referent == cls.CHILDHOOD_MEMORY:
            grounded = bool(re.search(r"\b(?:childhood|memory|remember)\b", value, re.I))
        else:
            grounded = False
        deferred = bool(re.search(r"\b(?:try\s+(?:me\s+)?again|ask\s+me\s+later|give\s+me\s+(?:a\s+)?moment)\b", value, re.I))
        return bool(uncertainty and grounded and not deferred)

    @classmethod
    def safe_unknown_fallback(cls, referent: str | None) -> str:
        if referent == cls.NAME_ORIGIN:
            return "I honestly don't have a specific story behind my name, but I've always liked how it sounds"
        if referent == cls.CHILDHOOD_MEMORY:
            return "I honestly don't have one specific childhood memory I can point to"
        return ""

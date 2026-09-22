"""Bounded multi-turn conversation progression quality.

This module is deliberately free of provider, persistence, and Sales Brain
dependencies.  It judges only whether an ordinary-chat candidate contributes
enough after a short run of low-novelty Ava replies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import re


class DialogueFunction(str, Enum):
    ACKNOWLEDGEMENT_REACTION = "ACKNOWLEDGEMENT_REACTION"
    OBSERVATION = "OBSERVATION"
    CALLBACK = "CALLBACK"
    SELF_DISCLOSURE = "SELF_DISCLOSURE"
    DIRECT_PERSONAL_ANSWER = "DIRECT_PERSONAL_ANSWER"
    PLAYFUL_CHALLENGE = "PLAYFUL_CHALLENGE"
    USEFUL_QUESTION = "USEFUL_QUESTION"
    NEW_DETAIL = "NEW_DETAIL"
    TEASE = "TEASE"
    COMMERCIAL_PROGRESSION = "COMMERCIAL_PROGRESSION"
    MIRRORING_WITH_GENERIC_AFFECT = "MIRRORING_WITH_GENERIC_AFFECT"


@dataclass(frozen=True)
class ProgressionAssessment:
    recent_dialogue_functions: tuple[str, ...]
    progression_pressure_active: bool
    customer_hook_detected: bool
    callback_continuity_detected: bool
    topic_reset_detected: bool
    candidate_contribution_function: str
    candidate_contributive: bool
    mirroring_with_generic_affect: bool
    accepted: bool
    rejection_reason: str | None

    def diagnostics(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ResponseNoveltyAssessment:
    semantic_family: str | None
    recent_family_counts: dict[str, int]
    exhausted_families: tuple[str, ...]
    exact_reuse: bool
    family_exhausted: bool
    self_novel: bool

    def diagnostics(self) -> dict:
        return asdict(self)


class ConversationProgressionFailure(RuntimeError):
    """Fail-closed progression rejection with sanitized durable evidence."""

    def __init__(self, reason: str, diagnostics: dict):
        super().__init__(reason)
        self.diagnostics = dict(diagnostics)


class ConversationProgressionQualityService:
    """Detect short sequential dialogue-function loops without forcing hooks."""

    NOVELTY_WINDOW = 6
    _FAMILY_EXHAUSTION_THRESHOLDS = {
        "TROUBLE_CHALLENGE": 1,
        "IMAGINATION_REFLECTION": 2,
        "GENERIC_CURIOSITY": 2,
        "CONTINUATION_PROMPT": 2,
    }
    _SEMANTIC_FAMILIES = {
        "TROUBLE_CHALLENGE": re.compile(
            r"\b(?:trouble|dangerous\s+side|naughty\s+side|mischievous\s+side|"
            r"haven['’]?t\s+seen(?:\s+my)?\s+\w+\s+side|"
            r"still\s+haven['’]?t\s+seen)\b", re.I,
        ),
        "IMAGINATION_REFLECTION": re.compile(
            r"\b(?:vivid|quite\s+an?)\s+imagination\b|"
            r"\b(?:paint(?:ing|ed)?|picture(?:d|ing)?)\s+(?:quite\s+)?(?:the|a|that)?\s*picture\b|"
            r"\bi\s+can\s+picture\s+that\b", re.I,
        ),
        "GENERIC_CURIOSITY": re.compile(
            r"\b(?:makes?\s+me\s+curious|i['’]?m\s+curious|curious\s+(?:how|what|where|"
            r"whether|to\s+see))\b", re.I,
        ),
        "CONTINUATION_PROMPT": re.compile(
            r"\b(?:keep\s+talking|tell\s+me\s+more|what\s+else\s+would\s+you|"
            r"what\s+else\s+do\s+you|go\s+on)\b", re.I,
        ),
    }

    _LOW_INFORMATION = re.compile(
        r"^(?:ok(?:ay)?|k|yeah|yep|yup|sure|fine|right|got it|sounds good|"
        r"thanks|thank you|lol|haha|goodnight|night|bye|later)[.! ]*$", re.I,
    )
    _CLOSING = re.compile(
        r"\b(?:good ?night|talk (?:to you )?later|gotta go|have a good "
        r"(?:night|day)|catch you later|bye for now)\b", re.I,
    )
    _PLAYFUL_CHALLENGE = re.compile(
        r"\b(?:prove it|try me|make me|bet you|you(?:'ll| will) have to|"
        r"don't make it too easy|earn (?:it|that)|keep up|we(?:'ll| will) see)\b",
        re.I,
    )
    _TEASE = re.compile(
        r"\b(?:teas(?:e|ing)|trouble|tempt(?:ing|ed)?|dangerous|naughty|"
        r"keep you guessing|little secret|bold of you)\b", re.I,
    )
    _COMMERCIAL = re.compile(
        r"(?:\$\s*\d|\b(?:buy|price|unlock|offer|purchase|checkout|pay)\b)", re.I,
    )
    _SELF_DISCLOSURE = re.compile(
        r"\b(?:i(?:'m| am| like| love| prefer| tend| usually| always| never)|"
        r"my (?:favorite|weekend|idea|kind|weakness))\b", re.I,
    )
    _DIRECT_PERSONAL_QUESTION = re.compile(
        r"\b(?:what|which)\s+would\s+be\s+your\s+(?:dream|ideal|perfect)\s+date\b|"
        r"\bwhat(?:'s| is)\s+your\s+(?:idea|kind)\s+of\s+(?:a\s+)?(?:dream|ideal|perfect)\s+date\b",
        re.I,
    )
    _DIRECT_DATE_PREFERENCE_ANSWER = re.compile(
        r"\b(?:my\s+(?:dream|ideal|perfect)\s+date|my\s+kind\s+of\s+date|"
        r"i(?:'d| would)\s+(?:pick|choose|love|prefer)|"
        r"(?:sunset|dinner|coffee|beach|water|porch|mountain|walk|conversation|laughter|"
        r"slow\s+evening|quiet\s+evening|night\s+out))\b",
        re.I,
    )
    _DIRECT_WELLBEING_QUESTION = re.compile(
        r"\bhow\s+are\s+you(?:\s+doing)?\b|"
        r"\bhow(?:'s| is)\s+(?:ava|cutie|beautiful|gorgeous|sexy|sunshine|"
        r"pretty\s+girl)\s+(?:doing|feeling)\b",
        re.I,
    )
    _DIRECT_WELLBEING_ANSWER = re.compile(
        r"\bi(?:'m| am)\s+(?:doing|feeling)\s+|"
        r"\bdoing\s+(?:pretty\s+)?(?:good|well|great|okay|alright)\b",
        re.I,
    )
    _ACK = re.compile(
        r"^(?:aww|aw|oh|ooh|ugh|mm+|hmm+|haha|lol|yeah|well|okay|true|"
        r"that(?:'s| is| sounds)|sounds|it (?:is|can|does))\b", re.I,
    )
    _GENERIC_APHORISM = re.compile(
        r"\b(?:has (?:its|a) own kind of|there(?:'s| is) something (?:about|to)|"
        r"sometimes .{0,35} is (?:the|a) (?:best|real)|"
        r"(?:patience|confidence|honesty|timing) (?:definitely )?(?:has|is|can))\b",
        re.I,
    )
    _GENERIC_AFFECT = re.compile(
        r"\b(?:sounds?|seems?|feels?|definitely|quite|really|very|intense|"
        r"tempting|amazing|incredible|unforgettable|exciting|fun|nice|good|"
        r"great|spark(?:s|ed)?(?:\s+a)?\s+fire|hard\s+to\s+forget|"
        r"wouldn['’]t\s+want\s+to\s+end)\b", re.I,
    )
    _STOPWORDS = frozenset({
        "about", "after", "again", "also", "and", "are", "been", "but",
        "can", "could", "did", "does", "for", "from", "have", "here",
        "how", "into", "its", "just", "like", "maybe", "really", "that",
        "the", "their", "then", "there", "they", "this", "too", "very",
        "want", "was", "were", "what", "when", "with", "would", "you",
        "your", "i'm", "i've", "it's", "that's", "you're", "careful",
        "still", "little", "bit", "own", "kind",
    })
    _SEMANTIC_CONCEPTS = (
        frozenset({"hike", "hiking", "trail", "outdoors", "outside", "nature", "camping"}),
        frozenset({"job", "work", "shift", "office", "career", "meeting"}),
        frozenset({"trip", "travel", "flight", "vacation", "journey"}),
        frozenset({"dog", "puppy", "cat", "kitten", "pet"}),
        frozenset({"song", "music", "band", "concert", "artist"}),
        frozenset({"tease", "teasing", "flirt", "flirting", "playful", "tempting"}),
    )

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token for token in re.findall(r"[a-z']{3,}", str(text or "").lower())
            if token not in cls._STOPWORDS
        }

    @staticmethod
    def _normalize_exact(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9']+", str(text or "").lower()))

    @classmethod
    def semantic_family(cls, text: str) -> str | None:
        value = str(text or "")
        return next((name for name, pattern in cls._SEMANTIC_FAMILIES.items()
                     if pattern.search(value)), None)

    @classmethod
    def novelty_assessment(
        cls, candidate: str, recent_ava_responses: list[str] | tuple[str, ...] = (),
    ) -> ResponseNoveltyAssessment:
        recent = tuple(str(item or "") for item in recent_ava_responses)[
            -cls.NOVELTY_WINDOW:
        ]
        families = tuple(cls.semantic_family(item) for item in recent)
        counts = {
            family: families.count(family)
            for family in cls._FAMILY_EXHAUSTION_THRESHOLDS
            if families.count(family)
        }
        exhausted = tuple(
            family for family, threshold in cls._FAMILY_EXHAUSTION_THRESHOLDS.items()
            if counts.get(family, 0) >= threshold
        )
        family = cls.semantic_family(candidate)
        normalized = cls._normalize_exact(candidate)
        exact_reuse = bool(normalized and any(
            normalized == cls._normalize_exact(item) for item in recent
        ))
        family_exhausted = bool(family and family in exhausted)
        return ResponseNoveltyAssessment(
            semantic_family=family,
            recent_family_counts=counts,
            exhausted_families=exhausted,
            exact_reuse=exact_reuse,
            family_exhausted=family_exhausted,
            self_novel=not (exact_reuse or family_exhausted),
        )

    @classmethod
    def _proposition_tokens(cls, text: str) -> set[str]:
        """Normalize proposition-bearing words without pretending to be an LLM."""
        scrubbed = cls._GENERIC_AFFECT.sub(" ", str(text or "").lower())
        tokens = cls._tokens(scrubbed)
        normalized = set()
        for token in tokens:
            root = re.sub(r"(?:ing|ed|es|s)$", "", token)
            normalized.add(root if len(root) >= 4 else token)
        return normalized

    @classmethod
    def mirroring_with_generic_affect(
        cls, customer_message: str, candidate: str,
    ) -> bool:
        """Detect an inbound proposition repeated inside generic evaluation."""
        customer = cls._proposition_tokens(customer_message)
        response = cls._proposition_tokens(candidate)
        shared = customer & response
        if len(shared) < 2 or not cls._GENERIC_AFFECT.search(candidate):
            return False
        # A stance, challenge, callback, or useful question is a contribution,
        # even when it naturally carries one or two foreground words forward.
        constructive = bool(
            "?" in candidate
            or cls._PLAYFUL_CHALLENGE.search(candidate)
            or re.search(r"\b(?:back to|reminds? me|remember when|you always|"
                         r"you(?:'ve| have) been|i(?:'d| would| can| can't| could|"
                         r" prefer| like| love| think| bet))\b", candidate, re.I)
        )
        if constructive:
            return False
        novel = response - customer
        return len(shared) >= 3 or len(novel) <= 2

    @classmethod
    def _concept_continuity(cls, left: str, right: str) -> bool:
        """Lexical-semantic continuity, including affixed forms, without phrases."""
        left_tokens, right_tokens = cls._tokens(left), cls._tokens(right)
        if left_tokens & right_tokens:
            return True
        if any(left_tokens & concept and right_tokens & concept
               for concept in cls._SEMANTIC_CONCEPTS):
            return True
        for first in left_tokens:
            for second in right_tokens:
                if min(len(first), len(second)) >= 5 and (
                    first in second or second in first
                ):
                    return True
                # Lightweight morphology covers continuations such as
                # behave/misbehave without encoding any domain-specific pair.
                first_root = re.sub(r"^(?:mis|un|re)|(?:ing|ed|s)$", "", first)
                second_root = re.sub(r"^(?:mis|un|re)|(?:ing|ed|s)$", "", second)
                if len(first_root) >= 4 and first_root == second_root:
                    return True
                if min(len(first_root), len(second_root)) >= 5 and (
                    first_root[:5] == second_root[:5]
                ):
                    return True
        return False

    @classmethod
    def _emoji_only(cls, text: str) -> bool:
        return bool(text.strip()) and not bool(re.search(r"[A-Za-z0-9]", text))

    @classmethod
    def customer_hook(
        cls, customer_message: str, *, recent_exchange: tuple[str, ...] = (),
    ) -> tuple[bool, bool]:
        text = str(customer_message or "").strip()
        if (not text or cls._emoji_only(text) or cls._LOW_INFORMATION.fullmatch(text)
                or cls._CLOSING.search(text)):
            return False, False
        callback = any(
            cls._concept_continuity(text, prior)
            for prior in recent_exchange[-4:] if prior
        )
        if (recent_exchange and re.search(
                r"\b(?:that|it|this|same|too|also|so can i|me too)\b", text, re.I,
        )):
            callback = True
        meaningful = bool(
            callback or "?" in text or cls._PLAYFUL_CHALLENGE.search(text)
            or cls._TEASE.search(text) or cls._SELF_DISCLOSURE.search(text)
            or len(cls._tokens(text)) >= 2
        )
        return meaningful, callback

    @classmethod
    def classify(
        cls, response: str, *, customer_message: str = "",
        recent_exchange: tuple[str, ...] = (),
        commercial_progression_authorized: bool = False,
    ) -> DialogueFunction:
        text = str(response or "").strip()
        if (cls._DIRECT_WELLBEING_QUESTION.search(str(customer_message or ""))
                and cls._DIRECT_WELLBEING_ANSWER.search(text)):
            return DialogueFunction.DIRECT_PERSONAL_ANSWER
        if cls.mirroring_with_generic_affect(customer_message, text):
            return DialogueFunction.MIRRORING_WITH_GENERIC_AFFECT
        if (cls._DIRECT_PERSONAL_QUESTION.search(str(customer_message or ""))
                and cls._DIRECT_DATE_PREFERENCE_ANSWER.search(text)):
            return DialogueFunction.DIRECT_PERSONAL_ANSWER
        if (commercial_progression_authorized and cls._COMMERCIAL.search(text)):
            return DialogueFunction.COMMERCIAL_PROGRESSION
        if "?" in text:
            return DialogueFunction.USEFUL_QUESTION
        if cls._PLAYFUL_CHALLENGE.search(text):
            return DialogueFunction.PLAYFUL_CHALLENGE
        if cls._SELF_DISCLOSURE.search(text):
            return DialogueFunction.SELF_DISCLOSURE
        if re.search(r"\b(?:back to|reminds? me|remember when)\b", text, re.I):
            return DialogueFunction.CALLBACK
        if cls._ACK.search(text):
            return DialogueFunction.ACKNOWLEDGEMENT_REACTION
        if cls._GENERIC_APHORISM.search(text):
            return DialogueFunction.OBSERVATION
        candidate_tokens = cls._tokens(text)
        customer_tokens = cls._tokens(customer_message)
        if (customer_message and len(candidate_tokens - customer_tokens) >= 2
                and not re.search(r"\b(?:back to|reminds? me|remember when)\b", text, re.I)):
            return DialogueFunction.NEW_DETAIL
        callback_sources = (customer_message,) + tuple(recent_exchange[-3:])
        if any(cls._concept_continuity(text, item) for item in callback_sources if item):
            if cls._TEASE.search(text):
                return DialogueFunction.TEASE
            return DialogueFunction.CALLBACK
        if cls._TEASE.search(text):
            return DialogueFunction.TEASE
        return DialogueFunction.OBSERVATION

    @classmethod
    def _is_low_novelty(
        cls, response: str, function: DialogueFunction, *, customer_message: str = "",
    ) -> bool:
        if (function is DialogueFunction.MIRRORING_WITH_GENERIC_AFFECT
                or cls._GENERIC_APHORISM.search(response)):
            return True
        if function in {
            DialogueFunction.ACKNOWLEDGEMENT_REACTION,
            DialogueFunction.OBSERVATION,
        }:
            return True
        if function in {DialogueFunction.CALLBACK, DialogueFunction.TEASE}:
            # Merely reflecting the customer's foreground concept is still a
            # reaction; a callback/tease must add another useful concept.
            if not customer_message:
                return True
            novel = cls._tokens(response) - cls._tokens(customer_message)
            return len(novel) < 2
        return False

    @classmethod
    def assess(
        cls, *, customer_message: str, candidate: str,
        recent_ava_responses: list[str] | tuple[str, ...] = (),
        recent_customer_messages: list[str] | tuple[str, ...] = (),
        commercial_progression_authorized: bool = False,
        safety_redirect: bool = False,
    ) -> ProgressionAssessment:
        recent_ava = tuple(str(item or "") for item in recent_ava_responses[-3:])
        recent_customer = tuple(
            str(item or "") for item in recent_customer_messages[-3:]
        )
        exchange = recent_customer + recent_ava
        hook, callback = cls.customer_hook(
            customer_message, recent_exchange=exchange,
        )
        recent_functions = tuple(cls.classify(item).value for item in recent_ava)
        low_run = 0
        for item, function_name in zip(reversed(recent_ava), reversed(recent_functions)):
            function = DialogueFunction(function_name)
            if cls._is_low_novelty(item, function):
                low_run += 1
            else:
                break

        # A new concrete topic is contribution in its own right and must not
        # inherit stale debt from a semantically unrelated exchange.
        current_tokens = cls._tokens(customer_message)
        prior_tokens = set().union(*(cls._tokens(item) for item in exchange)) if exchange else set()
        topic_reset = bool(
            len(current_tokens) >= 3 and prior_tokens
            and not any(cls._concept_continuity(customer_message, item) for item in exchange)
        )
        pressure = bool(
            not safety_redirect and hook and not topic_reset and low_run >= 2
        )
        function = cls.classify(
            candidate, customer_message=customer_message,
            recent_exchange=exchange,
            commercial_progression_authorized=commercial_progression_authorized,
        )
        contributive = not cls._is_low_novelty(
            candidate, function, customer_message=customer_message,
        )
        rejection = None
        mirroring = function is DialogueFunction.MIRRORING_WITH_GENERIC_AFFECT
        if mirroring:
            rejection = "MIRRORING_WITH_GENERIC_AFFECT"
        elif pressure and cls._GENERIC_APHORISM.search(candidate):
            rejection = "GENERIC_APHORISM_UNDER_PROGRESSION_PRESSURE"
        elif pressure and not contributive:
            rejection = "SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP"
        return ProgressionAssessment(
            recent_dialogue_functions=recent_functions,
            progression_pressure_active=pressure,
            customer_hook_detected=hook,
            callback_continuity_detected=callback,
            topic_reset_detected=topic_reset,
            candidate_contribution_function=function.value,
            candidate_contributive=contributive,
            mirroring_with_generic_affect=mirroring,
            accepted=not bool(rejection),
            rejection_reason=rejection,
        )

    @classmethod
    def bounded_fallback(cls, *, customer_message: str, intimacy_bounded: bool) -> str:
        """Short contribution; never commercial and never more explicit."""
        if cls._TEASE.search(customer_message) or intimacy_bounded:
            return "then don't make it too easy for me"
        return "give me one real detail and I'll meet you there"

"""Conservative, provider-free language policy for Ava Telegram conversation."""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class InboundLanguage(str, Enum):
    ENGLISH = "ENGLISH"
    NON_ENGLISH = "NON_ENGLISH"
    UNKNOWN = "UNKNOWN_INSUFFICIENT_TEXT"


@dataclass(frozen=True)
class LanguageAssessment:
    outcome: InboundLanguage
    meaningful_tokens: int
    english_signals: int
    non_english_signals: int
    policy: str = "AVA_ENGLISH_ONLY_CONVERSATION_V1"

    def diagnostics(self) -> dict:
        return {
            "policy": self.policy,
            "outcome": self.outcome.value,
            "meaningfulTokens": self.meaningful_tokens,
            "englishSignals": self.english_signals,
            "nonEnglishSignals": self.non_english_signals,
            "providerBacked": False,
            "conservative": True,
        }


@dataclass(frozen=True)
class EnglishOnlyDisposition:
    action: str
    operation: object
    assessment: LanguageAssessment
    notice_authority: str | None = None


class EnglishOnlyConversationPolicy:
    """Classify only high-confidence prose; ambiguity always proceeds normally."""

    NOTICE_TEXT = "Hi 😊 Sorry, I only speak English."
    POLICY = "AVA_ENGLISH_ONLY_CONVERSATION_V1"
    AFTER_NOTICE_REASON = "NON_ENGLISH_AFTER_ENGLISH_ONLY_NOTICE"
    NOTICE_PENDING_REASON = "NON_ENGLISH_WHILE_ENGLISH_ONLY_NOTICE_PENDING"

    _TOKEN = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)?", re.UNICODE)
    _ENGLISH = frozenset("""
        a about am an and are as at be been but by can could did do does for from
        have he hello hey hi how i if in is it just like much my no not of okay
        on one or our please price she so sorry speak tell that the this to want
        was we what when where which who why will with would yes you your
    """.split())
    _NON_ENGLISH = frozenset("""
        ahora algo aunque avec beaucoup bueno buenos como con cuando cuanto cuánto
        cuesta de del desde donde dónde el ella en entonces eres esta este esto et
        faire gracias habe ich il je la las le les lo los mais me mi muy necesito
        nicht para pero por porque que qué quiero savoir se si sin son soy suis te
        tengo tiene tu un una usted vous y ya yo gostaria gostaria quanto você nao
        não uma meu minha danke bitte der die das ist und wie was warum bonjour
        merci ciao grazie sono per perché vorrei sapere quanto costa questo
        contenuto posso comprarlo
    """.split())

    def classify(self, text: str | None) -> LanguageAssessment:
        cleaned = re.sub(r"https?://\S+|www\.\S+|@\w+", " ", str(text or ""))
        tokens = [token.casefold().replace("’", "'") for token in self._TOKEN.findall(cleaned)]
        meaningful = [token for token in tokens if len(token) >= 2]
        if len(meaningful) < 3:
            return LanguageAssessment(InboundLanguage.UNKNOWN, len(meaningful), 0, 0)
        english = sum(token in self._ENGLISH for token in meaningful)
        non_english = sum(token in self._NON_ENGLISH for token in meaningful)
        signals = english + non_english
        if english >= 2 and (signals == 0 or english / signals >= 0.45):
            outcome = InboundLanguage.ENGLISH
        elif non_english >= 3 and signals and non_english / signals >= 0.70:
            outcome = InboundLanguage.NON_ENGLISH
        else:
            outcome = InboundLanguage.UNKNOWN
        return LanguageAssessment(outcome, len(meaningful), english, non_english)

    def evaluate(self, operation, repository, *, creator_profile_id,
                 fanvue_account_id) -> EnglishOnlyDisposition:
        assessment = self.classify(getattr(operation, "inbound_message_text", None))
        if assessment.outcome is not InboundLanguage.NON_ENGLISH:
            return EnglishOnlyDisposition("NORMAL_PROCESSING", operation, assessment)
        action, updated, authority = repository.reserve_english_only_notice(
            operation.operation_id,
            policy=self.POLICY,
            after_notice_reason=self.AFTER_NOTICE_REASON,
            notice_pending_reason=self.NOTICE_PENDING_REASON,
            classification=assessment.diagnostics(),
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
        )
        return EnglishOnlyDisposition(action, updated or operation, assessment, authority)

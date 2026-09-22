from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.english_only_conversation_policy import (
    EnglishOnlyConversationPolicy, InboundLanguage,
)
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


@pytest.mark.parametrize("text,expected", [
    ("Hola", InboundLanguage.UNKNOWN),
    ("😊💕", InboundLanguage.UNKNOWN),
    ("I said hola but I still want to know the price", InboundLanguage.ENGLISH),
    ("I visited Guadalajara and I really loved the place", InboundLanguage.ENGLISH),
    ("Gracias, but I would like to know how much the photo set is", InboundLanguage.ENGLISH),
    ("Hola, me gustaría saber cuánto cuesta este set y cómo puedo comprarlo",
     InboundLanguage.NON_ENGLISH),
    ("Bonjour, je voudrais savoir combien cela coûte et comment faire",
     InboundLanguage.NON_ENGLISH),
    ("Hallo, ich mochte wissen wie viel das kostet und wie ich es kaufen kann",
     InboundLanguage.NON_ENGLISH),
    ("Ola, gostaria de saber quanto custa este conteudo e como posso comprar",
     InboundLanguage.NON_ENGLISH),
    ("Ciao, vorrei sapere quanto costa questo contenuto e come posso comprarlo",
     InboundLanguage.NON_ENGLISH),
])
def test_conservative_local_language_classification(text, expected):
    result = EnglishOnlyConversationPolicy().classify(text)
    assert result.outcome is expected
    assert result.diagnostics()["providerBacked"] is False


def test_exact_notice_is_deterministic_and_provider_free():
    operation = SimpleNamespace(
        operation_id=uuid4(), correlation_id="ordinary:test", inbound_message_text="hola",
    )
    payload = SimpleNamespace(telegram_chat_id=44, telegram_user_id=44, message_id=7)
    service = OrdinaryChatReplyService(repository=SimpleNamespace())
    result = service.english_only_notice_result(operation, payload)
    assert result.response_text == "Hi 😊 Sorry, I only speak English."
    assert result.offer_authorized is False
    assert result.delivery_requires_payment is False
    assert result.diagnostic_metadata["english_only_conversation_policy"] == {
        "policy": "AVA_ENGLISH_ONLY_CONVERSATION_V1", "firstNotice": True,
        "deterministic": True, "providerCalls": 0,
        "salesBrainGenerationCalls": 0,
    }
    operation.response_payload = {
        "diagnostic_metadata": result.diagnostic_metadata,
    }
    assert service._resource_classification(operation) == "EXCLUDED_NONORDINARY"


class PolicyRepository:
    def __init__(self): self.calls = []
    def reserve_english_only_notice(self, operation_id, **kwargs):
        self.calls.append((operation_id, kwargs))
        return "SUPPRESSED_AFTER_NOTICE", SimpleNamespace(last_error=
            "NON_ENGLISH_AFTER_ENGLISH_ONLY_NOTICE"), "CONFIRMED_ORDINARY_NOTICE"


def test_non_english_delegates_to_durable_authority_but_english_does_not():
    policy = EnglishOnlyConversationPolicy(); repository = PolicyRepository()
    spanish = SimpleNamespace(operation_id=uuid4(), inbound_message_text=
        "Hola, quiero saber cuánto cuesta este contenido y cómo comprarlo")
    decision = policy.evaluate(spanish, repository, creator_profile_id=2,
                               fanvue_account_id=2)
    assert decision.action == "SUPPRESSED_AFTER_NOTICE"
    assert decision.notice_authority == "CONFIRMED_ORDINARY_NOTICE"
    english = SimpleNamespace(operation_id=uuid4(), inbound_message_text=
        "Okay, how much is the photo set?")
    assert policy.evaluate(english, repository, creator_profile_id=2,
                           fanvue_account_id=2).action == "NORMAL_PROCESSING"
    assert len(repository.calls) == 1

import pytest

from app.models.commercial_objection import CommercialObjectionType
from app.services.commercial_objection_service import CommercialObjectionService
from app.services.gpt_service import GPTService


@pytest.mark.parametrize("message", [
    "link expired", "link has expired", "expired link", "the link expired",
    "link doesn't work", "link doesn’t work", "broken link", "dead link",
    "invalid link", "unavailable link", "this link is dead", "link not working",
    "checkout doesn't work", "can't open checkout", "payment link problem",
    "payment failed", "Th link has expired", "the lnk has expierd", "link doesnt work",
    "Maybe I'll buy later, the link has expired",
])
def test_technical_classification_and_concise_acknowledgement(message):
    objection = CommercialObjectionService().evaluate(message=message)
    assert objection.objection_type is CommercialObjectionType.PAYMENT_TECHNICAL
    assert not objection.continue_selling
    assert not objection.consider_alternative
    assert objection.selector_constraints["technicalAcknowledgementOnly"] is True
    # No client initialization, LLM call, provider, or database access is needed.
    reply = GPTService.__new__(GPTService).generate_response(
        persona_name="Test assistant", mode="NORMAL", user_message=message,
        user_memory={}, send_offer=False)
    assert reply == "Let me check into it."
    assert "?" not in reply


@pytest.mark.parametrize("message", [
    "My passport has expired", "the milk expired", "my parking permit expired",
    "my subscription expired", "The recipe link expired", "the zoom link is broken",
    "The password reset link has expired", "I want to buy this template",
    "can't open it", "the deadline expired",
])
def test_unrelated_expiration_is_not_commerce_support(message):
    assert CommercialObjectionService().evaluate(message=message).objection_type is not CommercialObjectionType.PAYMENT_TECHNICAL


def test_ambiguous_report_requires_commerce_evidence():
    result = CommercialObjectionService().evaluate(
        message="can't open it", context={"active_purchase_intent_id": "test-transaction"})
    assert result.objection_type is CommercialObjectionType.PAYMENT_TECHNICAL

from types import SimpleNamespace

import pytest

from app.services.customer_content_presentation_validator import (
    CustomerContentPresentationValidator,
)


@pytest.fixture
def validator():
    return CustomerContentPresentationValidator()


@pytest.fixture
def offering():
    return SimpleNamespace(price_minor=1999, currency="USD", title="Private Set")


@pytest.mark.parametrize("text", ["", "   ", "generation failed", "... 😏"])
def test_paid_presentation_rejects_empty_or_unusable(validator, offering, text):
    assert validator.validate_paid(text, offering=offering).valid is False


def test_question_only_tease_is_not_a_paid_presentation(validator, offering):
    result = validator.validate_paid(
        "You sure you're ready for this one? 😏", offering=offering,
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_NOT_AN_OFFER"


def test_short_natural_immediate_paid_presentation_is_valid(validator, offering):
    result = validator.validate_paid(
        "Here it is - unlock this private one.", offering=offering,
    )
    assert result.valid is True


@pytest.mark.parametrize("text", [
    "I've got this one for you. Want me to send it?",
    "Here's the private set. Should I send the link?",
    "This is the one. Are you ready for me to show you?",
    "I've got something for you; if you want, I'll send it.",
])
def test_authorized_paid_presentation_cannot_seek_send_permission(
    validator, offering, text,
):
    result = validator.validate_paid(text, offering=offering)
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_PERMISSION_GATE"


def test_short_teasing_caption_still_presents_now(validator, offering):
    result = validator.validate_paid(
        "Mm, I've got this one for you ðŸ˜ unlock it now.",
        offering=offering,
    )
    assert result.valid is True


@pytest.mark.parametrize("text", [
    "Use https://evil.example/pay",
    "Try another offer instead",
    "I can give you a 20% off discount",
    "I'll give it to you for $5",
    "Only 5 dollars for you",
])
def test_paid_presentation_rejects_external_commerce_claims(validator, offering, text):
    assert validator.validate_paid(text, offering=offering).valid is False


def test_matching_authoritative_price_is_still_forbidden_in_prose(validator, offering):
    result = validator.validate_paid(
        "This one is USD 19.99 when you're ready.", offering=offering,
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_CONVERSATIONAL_PRICE"


@pytest.mark.parametrize("text", [
    "This one is $19.99 when you're ready.",
    "This one is 19.99 when you're ready.",
    "You can unlock it for nineteen ninety-nine.",
])
def test_every_paid_presentation_must_be_price_neutral(validator, offering, text):
    result = validator.validate_paid(
        text, offering=offering, presentation_context={"price_neutral": True},
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_CONVERSATIONAL_PRICE"


def test_mapped_paid_presentation_cannot_verbalize_canonical_price(validator, offering):
    result = validator.validate_paid(
        "Here's this one for you — unlock it for $19.99.", offering=offering,
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_CONVERSATIONAL_PRICE"


def test_unmapped_paid_presentation_keeps_natural_price_neutral_copy(validator, offering):
    result = validator.validate_paid(
        "I saved a private one I think you'll love.",
        offering=offering, presentation_context={"price_neutral": True},
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_NOT_AN_OFFER"


@pytest.mark.parametrize("text", [
    "Maybe I'll show you later - it'll be worth the wait.",
    "Patience, I might reveal it soon.",
])
def test_present_offer_rejects_deferred_copy(validator, offering, text):
    result = validator.validate_paid(text, offering=offering)
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_DEFERRED"


def test_unmapped_paid_presentation_rejects_direct_fanvue_media_link(validator, offering):
    result = validator.validate_paid(
        "Unlock it at https://www.fanvue.com/ava/media/fvml-137",
        offering=offering,
        presentation_context={"price_neutral": True},
    )
    assert result.valid is False
    assert result.reason == "PAID_PRESENTATION_UNAUTHORIZED_URL"


@pytest.mark.parametrize("text", [
    "No worries, take your time! Sometimes the best finds pop up while scrolling.",
    "Unlock it when you're ready.",
    "Did you buy it?",
    "That sounds like a chill night.",
])
def test_verified_purchase_rejects_missing_or_pending_acknowledgement(validator, text):
    result = validator.validate_lifecycle(
        text, lifecycle={}, require_purchase_acknowledgement=True,
    )
    assert result.valid is False


@pytest.mark.parametrize("text", [
    "I saw you grabbed it — hope you enjoy this one.",
    "Hehe you got it 😏 enjoy.",
    "You unlocked this one — enjoy it while you scroll.",
])
def test_verified_purchase_accepts_natural_nonrobotic_acknowledgement(validator, text):
    result = validator.validate_lifecycle(
        text, lifecycle={}, require_purchase_acknowledgement=True,
    )
    assert result.valid is True

from types import SimpleNamespace

import pytest

from app.services.customer_content_presentation_validator import (
    CustomerContentPresentationValidator,
)
from app.services.gpt_service import GPTService


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


@pytest.mark.parametrize(("customer_message", "response"), [
    (
        "that set I bought was really good",
        "I'm glad you're loving it! Feels good to find a set that hits just right, doesn't it?",
    ),
    (
        "I already watched it and loved it",
        "I love that you enjoyed it — that one really landed for you.",
    ),
])
def test_completed_positive_purchase_reaction_accepts_experience_acknowledgement(
    validator, customer_message, response,
):
    result = validator.validate_lifecycle(
        response, lifecycle={}, require_purchase_acknowledgement=True,
        customer_message=customer_message,
    )
    assert result.valid is True


def test_completed_positive_purchase_reaction_rejects_prospective_enjoyment(validator):
    result = validator.validate_lifecycle(
        "I saw you grabbed it — hope you enjoy this one.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="I already watched it and loved it",
    )
    assert result.valid is False
    assert result.reason == "PURCHASE_ACKNOWLEDGEMENT_TEMPORAL_MISMATCH"


@pytest.mark.parametrize(("customer_message", "expected"), [
    ("I liked the last set", "COMPLETED_POSITIVE_EXPERIENCE"),
    ("that set I bought was really good", "COMPLETED_POSITIVE_EXPERIENCE"),
    ("I enjoyed the last one", "COMPLETED_POSITIVE_EXPERIENCE"),
    ("I didn't like the last one", "COMPLETED_NEGATIVE_EXPERIENCE"),
    ("I just bought it", "JUST_PURCHASED"),
    ("I'm opening it now", "OPENING_OR_VIEWING_NOW"),
    ("I bought that one", "NEUTRAL_PURCHASE_CONFIRMATION"),
])
def test_purchase_reaction_state_preserves_temporal_and_sentiment_distinctions(
    customer_message, expected,
):
    assert CustomerContentPresentationValidator.purchase_reaction_state(
        customer_message
    ) == expected


@pytest.mark.parametrize(("message", "resolution_type", "ordinal"), [
    ("I liked the second set even more", "ORDINAL", 2),
    ("I liked the first one better", "ORDINAL", 1),
    ("the $18 one was even better", "UNIQUE_PRICE", 2),
    ("the outdoor one was my favorite", "DESCRIPTOR", 2),
])
def test_resolved_purchase_identity_drives_completed_comparative_reaction(
    message, resolution_type, ordinal,
):
    history = {"historyEntries": (
        {"ordinal": 1, "grossMinor": 1200, "currency": "USD",
         "purchaseConfirmed": True, "safeTags": ("indoor",)},
        {"ordinal": 2, "grossMinor": 1800, "currency": "USD",
         "purchaseConfirmed": True, "safeTags": ("outdoor",)},
    )}
    reference = GPTService._resolve_purchase_history_reference(message, history)
    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        message, purchase_count=2, purchase_history_reference=reference,
    )

    assert reference["purchaseHistoryReferentResolved"] is True
    assert reference["resolutionType"] == resolution_type
    assert reference["resolvedOrdinal"] == ordinal
    assert frame["purchaseReactionState"] == "COMPLETED_POSITIVE_EXPERIENCE"
    assert frame["comparativePurchaseReaction"] is True


def test_resolved_session_part_worth_it_is_singular_completed_positive_feedback():
    reference = {
        "purchaseHistoryReferentDetected": True,
        "purchaseHistoryReferentResolved": True,
        "resolutionType": "ORDINAL",
        "resolvedOrdinal": 1,
        "resolvedPurchaseCount": 1,
        "resolvedPurchaseIds": ["intent-step-one"],
    }

    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        "that first part was worth it",
        purchase_count=1,
        purchase_history_reference=reference,
    )

    assert frame["purchaseReactionState"] == "COMPLETED_POSITIVE_EXPERIENCE"
    assert frame["retrospectivePurchaseReactionRequired"] is True
    assert frame["purchaseFeedbackAggregate"] is False
    assert frame["resolvedPurchaseIds"] == ["intent-step-one"]


@pytest.mark.parametrize("message", (
    "the third set was best",
    "the portrait one was my favorite",
))
def test_unresolved_purchase_reference_does_not_fabricate_completed_reaction(message):
    history = {"historyEntries": (
        {"ordinal": 1, "purchaseConfirmed": True, "safeTags": ("portrait",)},
        {"ordinal": 2, "purchaseConfirmed": True, "safeTags": ("portrait",)},
    )}
    reference = GPTService._resolve_purchase_history_reference(message, history)
    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        message, purchase_count=2, purchase_history_reference=reference,
    )

    assert reference["purchaseHistoryReferentResolved"] is False
    assert frame["purchaseHistoryReferentResolved"] is False
    assert frame["purchaseReactionState"] == "NEUTRAL_PURCHASE_CONFIRMATION"
    assert frame["comparativePurchaseReaction"] is False


def test_resolved_comparative_reaction_accepts_natural_retrospective_candidate(
    validator,
):
    reference = {
        "purchaseHistoryReferentDetected": True,
        "purchaseHistoryReferentResolved": True,
        "resolutionType": "ORDINAL",
        "resolvedOrdinal": 2,
    }
    result = validator.validate_lifecycle(
        "Glad you liked that one more—guess I nailed the vibe just right this time.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="I liked the second set even more", purchase_count=2,
        purchase_history_reference=reference,
    )

    assert result.valid is True


def test_resolved_historical_topic_preserves_fun_surprise_as_completed_feedback(
    validator,
):
    reference = {
        "purchaseHistoryReferentDetected": True,
        "purchaseHistoryReferentResolved": True,
        "resolutionType": "RECENCY",
        "resolvedOrdinal": 1,
    }
    frame = validator.purchase_reaction_semantic_frame(
        "it was a fun surprise", purchase_count=1,
        purchase_history_reference=reference,
    )
    result = validator.validate_lifecycle(
        "Nice, surprises like that definitely stick with you.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="it was a fun surprise", purchase_count=1,
        purchase_history_reference=reference,
    )

    assert frame["purchaseReactionState"] == "COMPLETED_POSITIVE_EXPERIENCE"
    assert frame["retrospectivePurchaseReactionRequired"] is True
    assert result.valid is True


def test_resolved_comparative_reaction_rejects_prospective_or_flat_candidate(
    validator,
):
    reference = {
        "purchaseHistoryReferentDetected": True,
        "purchaseHistoryReferentResolved": True,
        "resolutionType": "ORDINAL",
        "resolvedOrdinal": 2,
    }
    prospective = validator.validate_lifecycle(
        "I saw you grabbed it — hope you enjoy this one.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="I liked the second set even more", purchase_count=2,
        purchase_history_reference=reference,
    )
    flat = validator.validate_lifecycle(
        "I'm glad you liked it.", lifecycle={},
        require_purchase_acknowledgement=True,
        customer_message="I liked the second set even more", purchase_count=2,
        purchase_history_reference=reference,
    )

    assert prospective.reason == "PURCHASE_ACKNOWLEDGEMENT_TEMPORAL_MISMATCH"
    assert flat.reason == "PURCHASE_ACKNOWLEDGEMENT_COMPARATIVE_SEMANTICS_MISSING"


@pytest.mark.parametrize("customer_message", [
    "you've been two for two so far",
    "both sets have been really good",
    "I've liked both of the ones I bought",
])
def test_repeat_purchase_aggregate_positive_reaction_requires_verified_history(
    customer_message,
):
    classifier = CustomerContentPresentationValidator.purchase_reaction_state
    assert classifier(customer_message, purchase_count=2) == (
        "COMPLETED_POSITIVE_EXPERIENCE"
    )
    assert classifier(customer_message, purchase_count=1) == (
        "NEUTRAL_PURCHASE_CONFIRMATION"
    )


@pytest.mark.parametrize("customer_message", [
    "I bought two",
    "I might buy two",
    "one was good, one wasn't",
])
def test_repeat_purchase_neutral_future_and_mixed_history_are_not_aggregate_positive(
    customer_message,
):
    assert CustomerContentPresentationValidator.purchase_reaction_state(
        customer_message, purchase_count=2,
    ) != "COMPLETED_POSITIVE_EXPERIENCE"


def test_negative_purchase_reaction_requires_sentiment_grounding(validator):
    rejected = validator.validate_lifecycle(
        "Congrats on grabbing it — hope you enjoy it.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="I bought it but didn't like it",
    )
    accepted = validator.validate_lifecycle(
        "I'm sorry that one didn't land for you — I appreciate you telling me.",
        lifecycle={}, require_purchase_acknowledgement=True,
        customer_message="I bought it but didn't like it",
    )
    assert rejected.valid is False
    assert rejected.reason == "PURCHASE_ACKNOWLEDGEMENT_SENTIMENT_MISMATCH"
    assert accepted.valid is True
@pytest.mark.parametrize("response", (
    "you’re on a roll — glad you grabbed it",
    "Glad you grabbed it",
    "hope you enjoy this one",
))
def test_aggregate_completed_reaction_rejects_semantic_corruption(response):
    result = CustomerContentPresentationValidator().validate_lifecycle(
        response,
        lifecycle={},
        require_purchase_acknowledgement=True,
        customer_message="you've been two for two so far",
        purchase_count=2,
    )

    assert result.valid is False


@pytest.mark.parametrize("response", (
    "love that both landed",
    "glad they keep landing for you",
    "I’m still on a roll with you.",
))
def test_aggregate_completed_reaction_accepts_concise_preserved_semantics(response):
    result = CustomerContentPresentationValidator().validate_lifecycle(
        response,
        lifecycle={},
        require_purchase_acknowledgement=True,
        customer_message="you've been two for two so far",
        purchase_count=2,
    )

    assert result.valid is True


@pytest.mark.parametrize("response", (
    "Guess I\u2019m on fire today.",
    "okay, I haven't missed yet.",
    "Glad they both landed.",
    "Looks like my picks are working.",
    "Two wins for me then.",
))
def test_aggregate_subject_authority_accepts_ava_or_content_owner(response):
    analysis = CustomerContentPresentationValidator.aggregate_purchase_subject_analysis(
        response,
    )

    assert analysis == {
        "semanticFrameSubject": "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD",
        "finalResponseSubjectCompatible": True,
        "contradictorySemanticSegmentDetected": False,
        "aggregatePurchaseReactionSatisfied": True,
    }


@pytest.mark.parametrize("response", (
    "You're on a roll.",
    "Look at you, on a roll.",
    "Look at you, killing it.",
    "Look at you, on a roll! Glad you grabbed both.",
))
def test_aggregate_subject_authority_rejects_customer_owner(response):
    analysis = CustomerContentPresentationValidator.aggregate_purchase_subject_analysis(
        response,
    )

    assert analysis["finalResponseSubjectCompatible"] is False
    assert analysis["contradictorySemanticSegmentDetected"] is True
    assert analysis["aggregatePurchaseReactionSatisfied"] is False


def test_customer_success_subject_remains_valid_when_semantic_frame_requires_it():
    analysis = CustomerContentPresentationValidator.aggregate_purchase_subject_analysis(
        "You're on a roll.", expected_subject="CUSTOMER_TRACK_RECORD",
    )

    assert analysis["finalResponseSubjectCompatible"] is True
    assert analysis["contradictorySemanticSegmentDetected"] is False
    assert analysis["aggregatePurchaseReactionSatisfied"] is True


def test_unauthorized_question_fails_protected_acknowledgement_validation():
    result = CustomerContentPresentationValidator().validate_lifecycle(
        "I’m still on a roll with you. Should I be worried?",
        lifecycle={},
        require_purchase_acknowledgement=True,
        customer_message="you've been two for two so far",
        purchase_count=2,
        question_authorized=False,
    )

    assert result.reason == "PURCHASE_ACKNOWLEDGEMENT_UNAUTHORIZED_QUESTION"


@pytest.mark.parametrize("message", (
    "I've liked what I've bought from you",
    "I've liked everything I've bought",
    "what I've bought has been good",
    "everything I've unlocked has been solid",
    "I've been happy with the stuff I've bought",
    "the things I've bought from you have been great",
))
def test_collective_purchase_history_language_resolves_aggregate(message):
    history = {"historyEntries": (
        {"ordinal": 1, "purchaseIntentId": "intent-1", "purchaseConfirmed": True},
        {"ordinal": 2, "purchaseIntentId": "intent-2", "purchaseConfirmed": True},
        {"ordinal": 3, "purchaseIntentId": "intent-3", "purchaseConfirmed": True},
    )}

    reference = GPTService._resolve_purchase_history_reference(message, history)
    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        message, purchase_count=3, purchase_history_reference=reference,
    )

    assert reference["purchaseHistoryReferentDetected"] is True
    assert reference["purchaseHistoryReferentResolved"] is True
    assert reference["resolutionType"] == "AGGREGATE"
    assert reference["aggregatePurchaseReference"] is True
    assert reference["resolvedPurchaseCount"] == 3
    assert reference["resolvedPurchaseIds"] == ["intent-1", "intent-2", "intent-3"]
    assert frame["purchaseFeedbackAggregate"] is True
    assert frame["purchaseReactionState"] == "COMPLETED_POSITIVE_EXPERIENCE"


def test_exact_c15_aggregate_feedback_requires_collective_response_shape():
    reference = GPTService._resolve_purchase_history_reference(
        "I've liked what I've bought from you",
        {"historyEntries": ({"ordinal": 1}, {"ordinal": 2}, {"ordinal": 3})},
    )
    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        "I've liked what I've bought from you", purchase_count=3,
        purchase_history_reference=reference,
    )

    assert CustomerContentPresentationValidator.aggregate_purchase_reaction_satisfied(
        "Glad they've been landing for you.", semantic_frame=frame,
    ) is True
    assert CustomerContentPresentationValidator.aggregate_purchase_reaction_satisfied(
        "Glad you liked it—you have good taste.", semantic_frame=frame,
    ) is False
    assert frame["purchaseReactionState"] != "JUST_PURCHASED"

import pytest

from app.services.conversation_progression_quality_service import (
    ConversationProgressionQualityService as Progression,
)
from app.services.gpt_service import GPTService
from app.test_phone_texting_style import memory_none, service_with, user_memory


JOHNNY = (
    "Good morning Ava\n"
    "How’s cutie doing this morning.\n\n"
    "Hope your day is a beautiful as you."
)
EXPECTED = {
    "RESPOND_TO_GREETING",
    "ANSWER_DIRECT_PERSONAL_QUESTION",
    "ACKNOWLEDGE_COMPLIMENT",
}


def obligations(message):
    return set(GPTService._turn_obligations(message, new_relationship=False))


def style(candidate, inbound=JOHNNY):
    return GPTService._style_analysis(
        candidate, inbound, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=False, recent_responses=[],
    )


@pytest.mark.parametrize(
    "message",
    ["Good morning Ava", "Good morning", "Morning Ava", "Morning 😊",
     "Good afternoon", "Good evening", "Hey", "Hi", "Hello"],
)
def test_semantic_greetings_create_obligation(message):
    assert "RESPOND_TO_GREETING" in obligations(message)


@pytest.mark.parametrize("message", ["morning to night", "I worked this morning"])
def test_incidental_daypart_is_not_a_greeting(message):
    assert "RESPOND_TO_GREETING" not in obligations(message)


@pytest.mark.parametrize(
    "message",
    ["How are you doing.", "How are you doing!", "How are you doing 😊",
     "How are you doing"],
)
def test_punctuation_free_semantic_personal_questions(message):
    result = GPTService._semantic_question(message)
    assert result["detected"] is True
    assert result["type"] == "DIRECT_PERSONAL_QUESTION"
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in obligations(message)


@pytest.mark.parametrize(
    "message",
    ["How's cutie doing this morning.", "How's cutie doing this morning",
     "How's cutie doing this morning 😊"],
)
def test_affectionate_question_resolves_to_ava(message):
    result = GPTService._semantic_question(message)
    assert result["type"] == "DIRECT_PERSONAL_QUESTION"
    assert result["personalAddresseeResolution"]["target"] == "AVA"
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in obligations(message)


def test_cutie_is_not_globally_rewritten_to_ava():
    result = GPTService._personal_addressee_resolution(
        "I saw a cutie at the coffee shop"
    )
    assert result["resolved"] is False


@pytest.mark.parametrize(
    "message",
    ["Hope your day is as beautiful as you.",
     "Hope your day is a beautiful as you.",
     "Nothing is as pretty as you.", "That smile of yours is gorgeous.",
     "You're looking amazing.", "Cutie looks good today."],
)
def test_bounded_ava_compliments_create_obligation(message):
    assert GPTService._compliment_semantics(message) == {
        "detected": True, "target": "AVA",
    }
    assert "ACKNOWLEDGE_COMPLIMENT" in obligations(message)


def test_unrelated_comparison_is_not_an_ava_compliment():
    assert GPTService._compliment_semantics(
        "This trail is as beautiful as the lake."
    )["detected"] is False


def test_johnny_exact_inbound_creates_all_three_obligations():
    assert obligations(JOHNNY) == EXPECTED


@pytest.mark.parametrize(
    "candidate",
    ["Morning 😊 I'm doing pretty good—and you're sweet for saying that.",
     "Morning 😊 doing pretty good, you're sweet."],
)
def test_natural_concise_response_satisfies_all_three_without_one_sentence_each(candidate):
    result = style(candidate)
    assert result["turnObligationsSatisfied"] is True
    assert set(result["satisfiedTurnObligations"]) == EXPECTED
    assert result["meaningfulContribution"] is True


def test_generic_ack_fails_every_johnny_obligation():
    result = style("fair enough")
    assert set(result["unsatisfiedTurnObligations"]) == EXPECTED
    assert result["turnObligationsSatisfied"] is False
    assert result["customerQuestionAnswered"] is False


@pytest.mark.parametrize("candidate", ["fair enough", "gotcha", "okay", "makes sense", "yeah"])
def test_generic_neutral_ack_never_answers_required_direct_question(candidate):
    result = style(candidate, "How are you doing.")
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in result["unsatisfiedTurnObligations"]


def test_combined_fallback_composes_all_obligations_and_rejects_neutral_default():
    candidate = GPTService._combined_obligation_fallback(
        JOHNNY, effort_mode="STANDARD", obligations=EXPECTED,
    )
    assert candidate.lower() != "fair enough"
    assert style(candidate)["turnObligationsSatisfied"] is True


def test_final_composition_recomputes_original_inbound_obligations():
    memory = memory_none()
    service, _ = service_with(
        "fair enough",
        "Morning 😊 I'm doing pretty good—and you're sweet for saying that.",
        "Morning 😊 I'm doing pretty good—and you're sweet for saying that.",
        "Morning 😊 I'm doing pretty good—and you're sweet for saying that.",
    )
    response = service.generate_response(
        "default", "casual", JOHNNY, user_memory(memory), False,
        chat_history=[],
    )
    diagnostics = memory["memoryDiagnostics"]["conversationStyle"]
    assert response != "fair enough"
    assert set(diagnostics["originalInboundObligations"]).issuperset(EXPECTED)
    assert set(diagnostics["finalRecomputedObligations"]).issuperset(EXPECTED)
    assert diagnostics["finalUnsatisfiedObligations"] == []
    assert diagnostics["finalObligationRecomputationResult"] == "PASS"


def test_part2_semantic_diagnostics_are_exposed():
    result = style("Morning 😊 I'm doing well—and you're sweet for saying that.")
    assert result["semanticGreetingDetected"] is True
    assert result["semanticQuestionDetected"] is True
    assert result["semanticQuestionType"] == "DIRECT_PERSONAL_QUESTION"
    assert result["personalAddresseeResolution"]["target"] == "AVA"
    assert result["complimentDetected"] is True
    assert result["complimentTarget"] == "AVA"


def test_direct_personal_answer_is_meaningful_without_followup_question():
    candidate = "I'm doing pretty good this morning 😊"
    result = style(candidate, "How's cutie doing this morning.")
    assessment = Progression.assess(
        customer_message="How's cutie doing this morning.", candidate=candidate,
    )
    assert result["turnObligationsSatisfied"] is True
    assert result["meaningfulContribution"] is True
    assert assessment.candidate_contributive is True
    assert "?" not in candidate


def test_dave_dream_date_direct_answer_regression():
    inbound = "What would be your dream date?"
    candidate = "My dream date is a sunset by the water with good conversation"
    assert obligations(inbound) == {"ANSWER_DIRECT_PERSONAL_QUESTION"}
    assert style(candidate, inbound)["turnObligationsSatisfied"] is True

from datetime import datetime, timezone

from app.services.ava_temporal_context_service import AvaTemporalContextService
from app.services.conversation_progression_quality_service import (
    ConversationProgressionQualityService as Progression,
)
from app.services.gpt_service import GPTService


def _context(at):
    return AvaTemporalContextService(
        clock=lambda: at,
    ).build()


def test_long_joseph_style_sequence_preserves_quality_properties():
    inbound = "Hi sexy, I want to pleasure you from morning to night"
    evening = _context(datetime(2026, 9, 17, 0, 8, tzinfo=timezone.utc))
    recent = [
        "careful, you haven't seen trouble yet",
        "that makes me curious",
        "you have a vivid imagination",
        "you still haven't seen my dangerous side",
        "I'm curious how far you'd take it",
        "you're painting quite the picture",
    ]
    selected = GPTService._function_first_flirt_fallback(
        inbound, recent_responses=recent,
        candidates=["then don't make it too easy for me"],
    )
    response = selected["response"]
    novelty = Progression.novelty_assessment(response, recent)
    temporal = AvaTemporalContextService.evaluate_response(
        inbound, response, evening,
    )
    progression = Progression.assess(
        customer_message=inbound,
        candidate=response,
        recent_ava_responses=recent,
        recent_customer_messages=[inbound] * 3,
    )
    style = GPTService._style_analysis(
        response, inbound, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=False,
        recent_responses=recent,
    )

    assert temporal["canonicalAvaDaypart"] == "EVENING"
    assert temporal["responseTemporalAlignmentSatisfied"] is True
    assert not response.lower().startswith(("good morning", "morning"))
    assert not Progression.mirroring_with_generic_affect(inbound, response)
    assert novelty.self_novel and not novelty.exact_reuse
    assert progression.accepted and progression.candidate_contributive
    assert style["sexualResponseSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True
    assert len(response.split()) <= 10
    assert "?" not in response


def test_multi_turn_family_diagnostics_transition_and_reeligibility():
    candidate = "I'm curious what you'd do next"
    eligible = Progression.novelty_assessment(candidate, [])
    used_once = Progression.novelty_assessment(
        candidate, ["that makes me curious"],
    )
    exhausted = Progression.novelty_assessment(candidate, [
        "that makes me curious", "curious how far you'd take it",
    ])
    avoided = Progression.novelty_assessment(
        "then don't make it too easy for me",
        ["that makes me curious", "curious how far you'd take it"],
    )
    distant = [
        "that makes me curious", "curious how far you'd take it",
        *[f"unrelated response {index}" for index in range(Progression.NOVELTY_WINDOW)],
    ]
    eligible_again = Progression.novelty_assessment(candidate, distant)

    assert eligible.diagnostics()["self_novel"] is True
    assert used_once.recent_family_counts == {"GENERIC_CURIOSITY": 1}
    assert exhausted.family_exhausted and not exhausted.self_novel
    assert "GENERIC_CURIOSITY" in exhausted.exhausted_families
    assert avoided.self_novel and avoided.semantic_family is None
    assert eligible_again.self_novel and not eligible_again.family_exhausted


def test_neutral_ack_transition_is_exact_reuse_safe():
    recent = [
        "then don't make it too easy for me",
        "I like that confidence",
        "okayyy... I felt that",
        "well then... message received",
    ]
    selected = GPTService._function_first_flirt_fallback(
        "same energy again", recent_responses=recent,
    )
    novelty = Progression.novelty_assessment(selected["response"], recent)

    assert selected["neutral"] is True
    assert selected["response"] == ""
    assert selected["function"] == "NO_VALID_SAVED_CANDIDATE"


def test_part1_temporal_and_mirroring_remain_binding_in_long_fixture():
    evening = _context(datetime(2026, 9, 17, 0, 8, tzinfo=timezone.utc))
    inbound = "Hi sexy, I want to pleasure you from morning to night"
    wrong_time = AvaTemporalContextService.evaluate_response(
        inbound, "Good morning, sexy", evening,
    )
    mirrored = Progression.assess(
        customer_message=inbound,
        candidate=(
            "Pleasuring me from morning to night sounds like a day "
            "I wouldn't want to end"
        ),
    )

    assert wrong_time["responseTemporalAlignmentSatisfied"] is False
    assert wrong_time["responseTemporalFunction"] == "SALUTATION"
    assert mirrored.mirroring_with_generic_affect
    assert not mirrored.accepted


def test_dream_date_is_a_direct_personal_preference_obligation():
    inbound = "I get excited thinking about it! What would be your dream date?"
    assert GPTService._direct_personal_question_slot(inbound) == "DATE_PREFERENCE"
    assert GPTService._turn_obligations(
        inbound, new_relationship=False,
    ) == ["ANSWER_DIRECT_PERSONAL_QUESTION"]


def test_dream_date_provider_answer_satisfies_personal_obligation():
    inbound = "What would be your dream date?"
    candidate = (
        "A slow evening where time slips away, good conversation, "
        "some laughter, and a little surprise."
    )
    style = GPTService._style_analysis(
        candidate, inbound, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=False, recent_responses=[],
    )
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_direct_personal_answer_is_contributive_and_not_mirroring():
    inbound = "What would be your dream date?"
    candidate = "My dream date is a sunset by the water with good conversation"
    assessment = Progression.assess(
        customer_message=inbound, candidate=candidate,
        recent_ava_responses=["That sounds nice.", "That could be fun."],
    )
    assert assessment.candidate_contribution_function == "DIRECT_PERSONAL_ANSWER"
    assert assessment.candidate_contributive
    assert assessment.accepted
    assert not assessment.mirroring_with_generic_affect


def test_direct_personal_fallback_answers_without_forcing_question():
    inbound = "What would be your dream date?"
    selected = GPTService._function_first_flirt_fallback(
        inbound,
        recent_responses=[
            "careful, you haven't seen trouble yet",
            "I'm curious how far you'd take it",
        ],
    )
    assert selected["function"] == "DIRECT_PERSONAL_ANSWER"
    assert "?" not in selected["response"]
    assert GPTService._direct_personal_answer_satisfies(
        "DATE_PREFERENCE", selected["response"],
    )
    assert Progression.novelty_assessment(
        selected["response"],
        ["careful, you haven't seen trouble yet"],
    ).self_novel


def test_neutral_acknowledgement_does_not_answer_personal_question():
    style = GPTService._style_analysis(
        "That sounds nice.", "What would be your dream date?",
        pressure={}, ordinary=True, memory_callback=False,
        new_relationship=False, recent_responses=[],
    )
    assert style["customerQuestionAnswered"] is False
    assert style["unsatisfiedTurnObligations"] == [
        "ANSWER_DIRECT_PERSONAL_QUESTION"
    ]

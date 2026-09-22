from app.services.autobiographical_question_authority import (
    AutobiographicalQuestionAuthority as Authority,
)
from app.services.gpt_service import GPTService


def style(question, answer, persona=None):
    projection = Authority.projection(question, persona or {})
    projection.pop("canonicalFact", None)
    return GPTService._style_analysis(
        answer, question,
        pressure={"autobiographicalQuestion": projection},
        ordinary=True, memory_callback=False,
    )


def test_name_origin_referents_are_not_location():
    for question in (
        "Where does your name come from?", "Why are you named Ava?",
        "Is there a story behind your name?", "How did you get your name?",
        "What does your name mean to you?",
    ):
        result = style(question, "I honestly don't have a specific story behind my name")
        assert result["customerQuestionDomain"] == Authority.NAME_ORIGIN
        assert result["customerQuestionSemanticSlot"] == Authority.NAME_ORIGIN
        assert result["customerQuestionAnswered"] is True
        assert result["turnObligationsSatisfied"] is True


def test_miroslav_exact_same_turn_name_pronoun_is_permanent_regression():
    question = "You have a beautiful name; where does it come from?"
    projection = Authority.projection(question, {})
    assert projection["referent"] == Authority.NAME_ORIGIN
    assert projection["canonicalFactAvailable"] is False
    assert projection["unknownBiographyAuthorized"] is True
    result = style(
        question,
        "I don't really have some big story behind it, but I've always liked how it sounds.",
    )
    assert result["customerQuestionDomain"] == Authority.NAME_ORIGIN
    assert result["customerQuestionAnswered"] is True
    assert result["turnObligationsSatisfied"] is True


def test_bounded_same_turn_name_pronoun_forms():
    for question in (
        "Your name is beautiful. Where does it come from?",
        "I like your name. Where did it come from?",
        "Ava is such a pretty name. Is there a story behind it?",
        "That's an interesting name. How did you get it?",
        "your name is beautiful where does it come from",
        "Your name is beautiful... where does it come from?",
        "love your name, where'd it come from?",
        "YOUR NAME IS BEAUTIFUL; WHERE DOES IT COME FROM?",
    ):
        assert Authority.referent(question) == Authority.NAME_ORIGIN


def test_arbitrary_and_ambiguous_pronouns_fail_closed():
    for question in (
        "I bought a new truck. Where does it come from?",
        "That photo is gorgeous. Where did you take it?",
        "I love your necklace. Where did you get it?",
        "Your town sounds nice. What's it like?",
        "That song is good. Where did you hear it?",
        "I love your name and your necklace. Where did you get it?",
    ):
        assert Authority.referent(question) is None


def test_geographic_questions_remain_location():
    for question in ("Where are you from?", "Where do you live?", "What city are you in?"):
        result = style(question, "I'm from a small town")
        assert result["customerQuestionDomain"] == "LOCATION"
        assert result["customerQuestionSemanticSlot"] is None


def test_unknown_biography_accepts_truth_but_blocks_dodges_and_deferral():
    valid = style(
        "Where does your name come from?",
        "I honestly don't have a specific story behind my name, but I like how it sounds",
    )
    assert valid["customerQuestionAnswered"] is True
    assert "ANSWER_DIRECT_QUESTION" in valid["satisfiedTurnObligations"]
    for dodge in (
        "Thanks, I like the sound of it too.",
        "It's kind of mysterious, don't you think?",
        "I don't know, try me again later",
    ):
        rejected = style("Where does your name come from?", dodge)
        assert rejected["customerQuestionAnswered"] is False
        assert "ANSWER_DIRECT_QUESTION" in rejected["unsatisfiedTurnObligations"]


def test_unknown_childhood_memory_and_known_fact_authority_are_distinct():
    unknown = Authority.projection("What's your favorite childhood memory?", {})
    assert unknown["referent"] == Authority.CHILDHOOD_MEMORY
    assert unknown["unknownBiographyAuthorized"] is True
    known = Authority.projection("Where does your name come from?", {
        "name_origin": "The creator chose the name Ava for this fixture.",
    })
    assert known["canonicalFactAvailable"] is True
    assert known["unknownBiographyAuthorized"] is False
    answer = style(
        "Where does your name come from?",
        "The creator chose my name Ava for this fixture",
        {"name_origin": "The creator chose the name Ava for this fixture."},
    )
    assert answer["customerQuestionAnswered"] is True


def test_known_fact_does_not_accept_unknown_fallback():
    answer = style(
        "Where does your name come from?",
        "I honestly don't have a specific story behind my name",
        {"name_origin": "The creator chose the name Ava for this fixture."},
    )
    assert answer["customerQuestionAnswered"] is False


def test_known_hobby_uses_normal_persona_answer_path():
    question = "Do you like hiking?"
    assert Authority.referent(question) is None
    answer = GPTService._style_analysis(
        "I love hiking and taking photos",
        question,
        pressure={},
        ordinary=True,
        memory_callback=False,
    )
    assert answer["customerQuestionAnswered"] is True
    assert answer["turnObligationsSatisfied"] is True


def test_governed_unknown_fallback_is_natural_and_non_deferred():
    answer = Authority.safe_unknown_fallback(Authority.NAME_ORIGIN)
    assert Authority.truthful_unknown_answer(Authority.NAME_ORIGIN, answer)
    assert "try" not in answer.lower()
    assert "database" not in answer.lower()

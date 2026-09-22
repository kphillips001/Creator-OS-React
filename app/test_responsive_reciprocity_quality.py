from app.services.gpt_service import GPTService


def analyze(customer, ava, *, recent=()):
    return GPTService._style_analysis(
        ava, customer,
        pressure={"recentQuestionCount": 0, "questionStreak": 0},
        ordinary=True, memory_callback=False,
        recent_responses=list(recent),
    )


def test_how_are_you_allows_direct_reciprocity_without_punctuation():
    style = analyze(
        "Hi Ava how are you doing today",
        "Hey! I'm doing pretty good, thanks for asking. How about you?",
    )
    assert style["customerAskedQuestion"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["responsiveReciprocity"]["allowed"] is True
    assert style["manufacturedQuestionRisk"] is False
    assert style["questionReason"] == "DIRECT_RECIPROCAL_CURIOSITY"
    assert style["questionClassification"] == "RESPONSIVE_RECIPROCITY"


def test_day_question_allows_matched_reciprocity():
    style = analyze("How was your day?", "Pretty good overall. How was yours?")
    assert style["customerQuestionAnswered"] is True
    assert style["manufacturedQuestionRisk"] is False


def test_plans_question_allows_reasonable_reciprocity():
    style = analyze(
        "What are you doing today?",
        "I'm taking it pretty easy today. What are you up to?",
    )
    assert style["responsiveReciprocity"]["allowed"] is True
    assert style["manufacturedQuestionRisk"] is False


def test_unrelated_generic_engagement_question_remains_blocked():
    style = analyze("That's cool.", "Yeah 😊 What's your favorite thing to do on weekends?")
    assert style["responsiveReciprocity"]["allowed"] is False
    assert style["manufacturedQuestionRisk"] is True


def test_repeated_reciprocity_is_blocked_when_recently_used():
    style = analyze(
        "How are you?", "I'm doing well. How about you?",
        recent=("I'm good too. How about you?",),
    )
    assert style["responsiveReciprocity"]["reason"] == "RECIPROCITY_ALREADY_USED"
    assert style["manufacturedQuestionRisk"] is True


def test_multiple_followup_questions_remain_blocked():
    style = analyze(
        "How are you?",
        "I'm doing well. How about you? What are your weekend plans?",
    )
    assert style["responsiveReciprocity"]["allowed"] is False
    assert style["manufacturedQuestionRisk"] is True


def test_direct_question_obligation_remains_satisfied():
    style = analyze("How are you?", "I'm doing really well. How about you?")
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in style["turnObligations"]
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in style["satisfiedTurnObligations"]
    assert style["turnObligationsSatisfied"] is True

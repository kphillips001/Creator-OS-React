from app.services.gpt_service import GPTService


def analyze(customer, ava, *, recent=(), pressure=None, discovery=None):
    state = {"recentQuestionCount": 0, "questionStreak": 0}
    state.update(pressure or {})
    if discovery is not None:
        state["relationshipDiscovery"] = discovery
    return GPTService._style_analysis(
        ava, customer, pressure=state, ordinary=True,
        memory_callback=False, recent_responses=list(recent),
    )


def test_weekend_plans_answer_plus_matched_reciprocity_is_allowed():
    style = analyze(
        "Do you have any fun plans for the weekend?",
        "I'm keeping it low-key by the beach. What are your weekend plans?",
    )
    assert style["customerQuestionAnswered"] is True
    assert style["responsiveReciprocity"]["allowed"] is True
    assert style["questionClassification"] == "RESPONSIVE_RECIPROCITY"
    assert style["manufacturedQuestionRisk"] is False


def test_weekend_plans_answer_only_remains_valid():
    style = analyze(
        "Do you have any fun plans for the weekend?",
        "I'm keeping it low-key by the beach this weekend.",
    )
    assert style["customerQuestionAnswered"] is True
    assert style["questionClassification"] == "NO_QUESTION"
    assert style["manufacturedQuestionRisk"] is False


def test_volunteered_camping_detail_allows_relevant_curiosity():
    style = analyze(
        "I'm heading camping this weekend.",
        "That sounds like a good reset. Are you camping in the mountains?",
    )
    curiosity = style["genuineContextualCuriosity"]
    assert curiosity["allowed"] is True
    assert curiosity["semanticTopic"] == "OUTDOORS"
    assert style["questionClassification"] == "GENUINE_CONTEXTUAL_CURIOSITY"
    assert style["manufacturedQuestionRisk"] is False


def test_volunteered_detail_unrelated_question_remains_blocked():
    style = analyze(
        "I'm heading camping this weekend.",
        "That sounds fun. What's your favorite movie?",
    )
    assert style["genuineContextualCuriosity"]["allowed"] is False
    assert style["questionClassification"] == "MANUFACTURED_ENGAGEMENT"
    assert style["manufacturedQuestionRisk"] is True


def test_known_answer_discovery_is_not_reasked():
    style = analyze(
        "Charlie is finally feeling better after the vet.",
        "I'm glad Charlie's feeling better. Do you have a dog?",
        discovery={"allowed": False, "suppressionReason": "DOMAIN_ALREADY_KNOWN"},
    )
    assert style["genuineContextualCuriosity"]["knownAnswerRisk"] is True
    assert style["manufacturedQuestionRisk"] is True


def test_recent_question_pressure_blocks_contextual_curiosity():
    style = analyze(
        "I'm heading camping this weekend.",
        "That sounds fun. Are you camping near the mountains?",
        pressure={"recentQuestionCount": 3, "questionStreak": 2},
    )
    assert style["genuineContextualCuriosity"]["reason"] == "RECENT_QUESTION_PRESSURE"
    assert style["manufacturedQuestionRisk"] is True


def test_recent_equivalent_contextual_question_is_blocked():
    style = analyze(
        "I'm camping again this weekend.",
        "That sounds fun. Are you camping in the mountains?",
        recent=("Are you camping near the lake?",),
    )
    assert style["genuineContextualCuriosity"]["reason"] == "RECENT_EQUIVALENT_QUESTION"
    assert style["manufacturedQuestionRisk"] is True


def test_customer_closing_acknowledgement_does_not_force_question():
    style = analyze("Sounds good.", "Perfect, enjoy your night.")
    assert style["questionClassification"] == "NO_QUESTION"
    assert style["manufacturedQuestionRisk"] is False


def test_multiple_contextual_questions_remain_blocked():
    style = analyze(
        "I'm heading camping this weekend.",
        "That sounds fun. Where are you going? Who are you going with?",
    )
    assert style["genuineContextualCuriosity"]["reason"] == "NOT_ONE_MEANINGFUL_QUESTION"
    assert style["manufacturedQuestionRisk"] is True

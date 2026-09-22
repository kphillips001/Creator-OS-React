import pytest

from app.services.conversation_progression_quality_service import (
    ConversationProgressionQualityService as Service,
    DialogueFunction,
)
from app.services.gpt_service import GPTService


LOW_RUN = [
    "That sounds like it took a lot out of you.",
    "Patience definitely has its own kind of charm.",
]


def assess(message, candidate, recent=LOW_RUN, customers=()):
    return Service.assess(
        customer_message=message,
        candidate=candidate,
        recent_ava_responses=recent,
        recent_customer_messages=customers,
    )


def test_one_short_acknowledgement_is_allowed():
    result = assess(
        "Long day at work.", "Those days can really drain you.",
        recent=["I hope work goes smoothly."],
    )
    assert result.accepted
    assert not result.progression_pressure_active


@pytest.mark.parametrize("message", ["ok", "😂", "Goodnight, talk later"])
def test_low_information_input_does_not_force_novelty(message):
    result = assess(message, "fair enough")
    assert result.accepted
    assert not result.customer_hook_detected
    assert not result.progression_pressure_active


def test_two_low_novelty_replies_create_pressure_for_usable_hook():
    result = assess("I can be patient too", "That sounds interesting.")
    assert result.customer_hook_detected
    assert result.progression_pressure_active
    assert not result.accepted
    assert result.rejection_reason == "SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP"


def test_lexically_different_acknowledgement_loop_is_detected():
    result = assess(
        "I can do that too",
        "Patience definitely has its own kind of charm.",
        recent=["That is tempting.", "Taking it slowly can be nice."],
        customers=["I would love to misbehave with you"],
    )
    assert result.progression_pressure_active
    assert not result.accepted
    assert result.rejection_reason == "GENERIC_APHORISM_UNDER_PROGRESSION_PRESSURE"


def test_behave_misbehave_callback_uses_general_morphology():
    hook, callback = Service.customer_hook(
        "I would love to misbehave with you",
        recent_exchange=("Behave yourself", "I'm behaving... but just barely."),
    )
    assert hook and callback


def test_semantic_callback_without_exact_token_match():
    hook, callback = Service.customer_hook(
        "I could hike all weekend",
        recent_exchange=("Getting outside on a trail is my favorite reset",),
    )
    assert hook
    assert callback


def test_irrelevant_old_callback_is_not_current_continuity():
    hook, callback = Service.customer_hook(
        "My new puppy kept me awake",
        recent_exchange=("We talked about hiking last month",),
    )
    assert hook and not callback


@pytest.mark.parametrize(
    ("candidate", "expected"),
    [
        ("then you'll have to prove it", DialogueFunction.PLAYFUL_CHALLENGE),
        ("that takes me back to your camping story", DialogueFunction.CALLBACK),
        ("I'm usually the stubborn one", DialogueFunction.SELF_DISCLOSURE),
        ("the tiny red notebook is the detail I'd remember", DialogueFunction.NEW_DETAIL),
        ("what made the red notebook matter?", DialogueFunction.USEFUL_QUESTION),
    ],
)
def test_distinct_useful_functions_pass_under_pressure(candidate, expected):
    result = assess("I kept the red notebook from that trip", candidate)
    assert result.accepted
    assert result.candidate_contribution_function == expected.value


def test_authorized_tease_with_new_contribution_passes():
    result = assess("You are teasing me", "bold of you—then keep up")
    assert result.accepted
    assert result.candidate_contribution_function in {
        DialogueFunction.PLAYFUL_CHALLENGE.value,
        DialogueFunction.TEASE.value,
    }


def test_manufactured_question_replacement_cannot_be_generic_aphorism():
    result = assess("I can be patient", "Patience definitely has its own kind of charm.")
    assert not result.accepted
    assert "GENERIC_APHORISM" in result.rejection_reason


def test_question_free_useful_replacement_passes():
    result = assess("I can be patient", "then you'll have to prove it")
    assert result.accepted
    assert "?" not in "then you'll have to prove it"


def test_commercial_progression_needs_independent_authority():
    kwargs = dict(
        customer_message="I like that set",
        candidate="unlock it for $20",
        recent_ava_responses=LOW_RUN,
    )
    blocked = Service.assess(**kwargs, commercial_progression_authorized=False)
    authorized = Service.assess(**kwargs, commercial_progression_authorized=True)
    assert blocked.candidate_contribution_function != "COMMERCIAL_PROGRESSION"
    assert authorized.candidate_contribution_function == "COMMERCIAL_PROGRESSION"


def test_safety_redirect_resets_progression_pressure():
    result = Service.assess(
        customer_message="keep going",
        candidate="I need us to keep this respectful.",
        recent_ava_responses=LOW_RUN,
        safety_redirect=True,
    )
    assert result.accepted
    assert not result.progression_pressure_active


def test_new_concrete_topic_resets_stale_progression_debt():
    result = assess(
        "My new puppy kept me awake all night",
        "That sounds exhausting.",
        recent=["Taking it slowly can be nice.", "Patience has its own charm."],
        customers=["I can behave", "You are tempting me"],
    )
    assert result.topic_reset_detected
    assert not result.progression_pressure_active
    assert result.accepted


def test_deterministic_tease_fallback_is_not_semantic_mirror():
    response = GPTService._combined_obligation_fallback(
        "You are teasing me", effort_mode="BALANCED", obligations=(),
    )
    assert response == "then don't make it too easy for me"
    assert "teas" not in response.lower()
    assert len(response.split()) <= 10


def test_bounded_fallback_is_short_question_free_and_noncommercial():
    response = Service.bounded_fallback(
        customer_message="You are teasing me", intimacy_bounded=True,
    )
    assert len(response.split()) <= 10
    assert "?" not in response
    assert not Service._COMMERCIAL.search(response)


def test_stu_sequence_rejects_complete_low_novelty_third_reply():
    result = Service.assess(
        customer_message="You are teasing me",
        candidate="careful, I can still tease you a little",
        recent_ava_responses=[
            "That's tempting... though maybe the best moments come when we take things slow and savor the anticipation.",
            "Patience definitely has its own kind of charm.",
        ],
        recent_customer_messages=[
            "I would love to misbehave with you", "I can do that too",
        ],
    )
    assert result.progression_pressure_active
    assert not result.accepted
    replacement = Service.bounded_fallback(
        customer_message="You are teasing me", intimacy_bounded=True,
    )
    repaired = Service.assess(
        customer_message="You are teasing me",
        candidate=replacement,
        recent_ava_responses=[
            "That's tempting... though maybe the best moments come when we take things slow and savor the anticipation.",
            "Patience definitely has its own kind of charm.",
        ],
        recent_customer_messages=[
            "I would love to misbehave with you", "I can do that too",
        ],
    )
    assert repaired.accepted
    assert repaired.candidate_contributive
    assert "?" not in replacement


def test_multi_customer_short_reactions_are_not_forced_into_questions():
    fixtures = [
        ("Long shift today", "That sounds draining."),
        ("My flight was delayed", "ugh, that is frustrating."),
        ("I finally finished the project", "That must feel good."),
    ]
    for message, response in fixtures:
        result = assess(message, response, recent=[])
        assert result.accepted
        assert not result.progression_pressure_active
        assert "?" not in response


@pytest.mark.parametrize("candidate", (
    "Pleasuring me from morning to night sounds like a day I wouldn't want to end.",
    "Kissing me all day sounds like quite a day.",
))
def test_proposition_mirroring_with_generic_affect_is_rejected(candidate):
    message = (
        "It would be fun to pleasure you from morning to night"
        if "Pleasuring" in candidate else "I'd love to spend all day kissing you"
    )
    result = assess(message, candidate, recent=[])
    assert not result.accepted
    assert result.mirroring_with_generic_affect
    assert result.candidate_contribution_function == "MIRRORING_WITH_GENERIC_AFFECT"
    assert result.rejection_reason == "MIRRORING_WITH_GENERIC_AFFECT"


@pytest.mark.parametrize("candidate", (
    "You'd be testing my ability to get anything else done 😏",
    "Bold plan. You always skip straight to the ambitious part, don't you?",
))
def test_genuine_stance_or_reaction_passes_without_restatement(candidate):
    result = assess("I'd love to spend all day kissing you", candidate, recent=[])
    assert result.accepted
    assert not result.mirroring_with_generic_affect


def test_generic_new_adjectives_do_not_turn_a_mirror_into_new_detail():
    result = assess(
        "I want to kiss you all day",
        "Kissing me all day sounds incredibly exciting and unforgettable.",
        recent=[],
    )
    assert not result.accepted
    assert not result.candidate_contributive


def test_supported_callback_and_natural_question_remain_contributive():
    callback = assess(
        "I'd love to kiss you all day",
        "You've been building this fantasy for two days now 😏",
        recent=[], customers=["Yesterday you started describing the same fantasy"],
    )
    question = assess(
        "I kept the red notebook from that trip",
        "What made the red notebook matter?",
        recent=[],
    )
    assert callback.accepted
    assert question.accepted


def test_short_natural_acknowledgement_remains_available_without_pressure():
    result = assess("I finally finished work", "That sounds exhausting.", recent=[])
    assert result.accepted
    assert not result.progression_pressure_active


@pytest.mark.parametrize(("recent", "candidate", "family"), (
    ("careful, you haven't seen trouble yet",
     "you still haven't seen my dangerous side", "TROUBLE_CHALLENGE"),
    ("you still haven't seen my dangerous side",
     "maybe you'll meet my naughty side", "TROUBLE_CHALLENGE"),
))
def test_trouble_family_exhaustion_crosses_literal_variants(recent, candidate, family):
    result = Service.novelty_assessment(candidate, [recent])
    assert result.semantic_family == family
    assert result.family_exhausted
    assert not result.self_novel


def test_semantic_family_becomes_eligible_after_bounded_distance():
    recent = ["careful, you haven't seen trouble yet"] + [
        f"ordinary unrelated reply {index}" for index in range(Service.NOVELTY_WINDOW)
    ]
    result = Service.novelty_assessment(
        "you still haven't seen my dangerous side", recent,
    )
    assert not result.family_exhausted
    assert result.self_novel


def test_exact_fallback_reuse_fails_across_whole_bounded_window():
    response = "careful, you haven't seen trouble yet"
    recent = [response, "unrelated one", "unrelated two", "unrelated three"]
    result = Service.novelty_assessment(response, recent)
    assert result.exact_reuse
    assert not result.self_novel


def test_one_curiosity_use_is_allowed_but_repetition_exhausts_family():
    candidate = "I'm curious what you'd do next"
    one = Service.novelty_assessment(candidate, ["that makes me curious"])
    repeated = Service.novelty_assessment(candidate, [
        "that makes me curious", "I'm curious how far you'd take it",
    ])
    assert one.self_novel
    assert not one.family_exhausted
    assert repeated.family_exhausted
    assert not repeated.self_novel


@pytest.mark.parametrize(("recent", "candidate", "family"), (
    (["you have a vivid imagination", "you're painting quite the picture"],
     "I can picture that", "IMAGINATION_REFLECTION"),
    (["keep talking", "tell me more"],
     "what else would you do?", "CONTINUATION_PROMPT"),
))
def test_repeated_reflection_and_continuation_families_exhaust(
    recent, candidate, family,
):
    result = Service.novelty_assessment(candidate, recent)
    assert result.semantic_family == family
    assert family in result.exhausted_families
    assert not result.self_novel

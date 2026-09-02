import pytest

from app.testing.session5_scenario_harness import DeterministicSyntheticLanguageProvider
from app.services.gpt_service import GPTService


def test_proactive_tease_validator_rejects_generic_banter_and_accepts_bridge():
    assert GPTService._response_satisfies_proactive_tease(
        "lol okay, I can see that"
    ) is False
    assert GPTService._response_satisfies_proactive_tease(
        "careful, you haven't seen trouble yet"
    ) is True


def memory(*, callback=False, disclosure=False):
    return {"memoryDiagnostics": {
        "continuityGuidance": {
            "relevanceReasons": ["EXPLICIT_MEMORY_REFERENCE"] if callback else [],
            "strongestMemory": {"category": "trait", "key": "social_style",
                                "value": "takes time to warm up to people"} if callback else None,
        },
        "customerSelfDisclosure": {"detected": disclosure},
    }}


@pytest.mark.parametrize(("message", "kwargs", "expected"), (
    ("Hey Ava", {}, "GREETING"),
    ("How are you?", {}, "DIRECT_QUESTION"),
    ("Work was brutal today", {}, "EMOTIONAL_DISCLOSURE"),
    ("You're a cute girl", {}, "LIGHT_FLIRT"),
    ("I love hiking", {"memory": memory(disclosure=True)}, "CUSTOMER_DISCLOSURE"),
    ("See, told you I warm up eventually", {"memory": memory(callback=True)}, "MEMORY_CALLBACK"),
    ("lol okay then", {}, "ORDINARY_BANTER"),
    ("I'm horny", {}, "SEXUAL_ONLY"),
    ("How much, I want to buy it", {}, "IMMEDIATE_BUYER"),
    ("That's too expensive", {}, "OBJECTION"),
    ("hey again", {"purchase_count": 1}, "RETURNING_BUYER"),
    ("keep going", {"active_session": True}, "SESSION_CONTINUATION"),
))
def test_normal_synthetic_provider_matrix_is_contextual_and_deterministic(
    message, kwargs, expected,
):
    options = {"memory": memory(), **kwargs}
    first = DeterministicSyntheticLanguageProvider(message=message, **options)
    second = DeterministicSyntheticLanguageProvider(message=message, **options)
    assert first.draft_class == expected
    assert first.complete() == second.complete()
    assert first.diagnostics()["syntheticProviderMode"] == "NORMAL_DETERMINISTIC_SYNTHETIC_PROVIDER"
    assert first.diagnostics()["liveProviderCalled"] is False


def test_synthetic_outputs_are_differentiated_and_adversarial_fixture_is_explicit():
    messages = ("Hey Ava", "Work was brutal", "You're a cute girl", "lol okay")
    outputs = {
        DeterministicSyntheticLanguageProvider(message=item, memory=memory()).complete()
        for item in messages
    }
    assert len(outputs) == len(messages)
    diagnostics = DeterministicSyntheticLanguageProvider(
        message="anything", memory=memory(),
    ).diagnostics(adversarial=True)
    assert diagnostics["syntheticProviderMode"] == "ADVERSARIAL_DRAFT_FIXTURE"
    assert diagnostics["adversarialFixtureUsed"] is True
    assert diagnostics["liveProviderCalled"] is False


def test_synthetic_rewrite_is_context_aware_and_repeatable():
    provider = DeterministicSyntheticLanguageProvider(
        message="I love hiking", memory=memory(disclosure=True),
    )
    draft = provider.complete()
    rewrite = provider.complete(rewrite=True)
    same = DeterministicSyntheticLanguageProvider(
        message="I love hiking", memory=memory(disclosure=True),
    ).complete(rewrite=True)
    assert rewrite != draft
    assert rewrite == same


def test_synthetic_provider_consumes_canonical_proactive_authority():
    provider = DeterministicSyntheticLanguageProvider(
        message="ordinary social banter", memory=memory(),
    )
    result = provider.complete(prompt_context=(
        "Do not stack another tease until the customer responds."
    ))
    assert provider.draft_class == "PROACTIVE_TEASE"
    assert provider.reason == "CANONICAL_PROACTIVE_PROGRESSION_AUTHORITY"
    assert GPTService._response_satisfies_proactive_tease(result) is True

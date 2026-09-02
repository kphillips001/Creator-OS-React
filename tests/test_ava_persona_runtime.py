from types import SimpleNamespace

from app.services.ava_persona_runtime_service import AvaPersonaRuntimeService
from app.services.gpt_service import GPTService


class Repo:
    def __init__(self, value): self.value = value
    def get(self, **_kwargs): return dict(self.value)


PROFILE = {
    "id": 2, "persona_name": "Ava Blackthorne", "age": 29,
    "personality_description": "Warm, playful, feminine, grounded and approachable.",
    "archetype": "Down-home coastal girl with small-town roots.",
    "backstory": "She grew up in a small town and now lives near the coast.",
    "boundaries": "Consenting adults only.", "sexual_boundaries": "Never coercive.",
    "hard_limits": "No minors, violence, coercion, or dependency.",
}


def service():
    return AvaPersonaRuntimeService(
        profile_loader=lambda _account: dict(PROFILE),
        world_repository=Repo({
            "internal_home_base": "Ava lives in Wilmington, North Carolina.",
            "public_location_description": "Ava lives in a coastal East Coast city.",
            "coastal_environments": "Beaches, marshes, docks, and boardwalks.",
            "home_and_indoor_environments": "Home, porch, coffee, and bookstores.",
        }),
        lifestyle_repository=Repo({
            "outdoor_lifestyle": "Hiking, lakes, cabins, camping, and mountains.",
            "weekend_escapes": "Mountain cabins and lake weekends.",
            "career": "Marketing and events professional.",
            "small_town_roots": "Grounded small-town roots.",
        }),
        social_repository=Repo({"things_to_avoid": "Coercion and artificial glamour."}),
    )


def test_public_projection_excludes_private_location_and_books():
    projection = service().build(fanvue_account_id=2, topic="How is coastal weather?")
    rendered = projection.prompt_block()
    assert "coastal East Coast" in rendered
    assert "Wilmington" not in rendered
    assert "bookstores" in rendered  # prohibition, never an Ava interest
    assert "Home, porch, coffee, and bookstores" not in rendered
    assert projection.diagnostics()["privateFactsExcluded"] is True


def test_relevance_selects_outdoors_but_not_for_sexual_topic():
    hiking = service().build(fanvue_account_id=2, topic="Do you like hiking and camping?")
    assert any("Hiking" in fact for fact in hiking.selected_lifestyle_facts)
    sexual = service().build(fanvue_account_id=2, topic="I'm horny tonight")
    assert sexual.relevance_domains == ("sexual",)
    assert sexual.selected_lifestyle_facts == ()


def test_paid_presentation_uses_runtime_projection_not_legacy_file(monkeypatch):
    runtime = service()
    gpt = GPTService("test", persona_runtime_service=runtime)
    captured = {}
    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(
                message=SimpleNamespace(content="I picked this one for you 😏 tap Unlock."))])
    gpt.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    monkeypatch.setattr(gpt, "load_persona_prompt", lambda _name: (_ for _ in ()).throw(
        AssertionError("legacy ava.txt must not be loaded")))
    result = gpt.generate_paid_presentation_copy(
        user_message="show me", draft="maybe", fanvue_account_id=2,
        offering=SimpleNamespace(title="Coastal set", description="Solo photos", offering_type="SINGLE"),
        price_neutral=True,
        presentation_purpose="PRICE_REQUEST_CONTINUATION",
        same_offer_as_previous_presentation=True,
        continuation_intent_type="PRICE_REQUEST",
        recent_paid_presentation_wording=("Here you go — unlock it.",),
        repetition_repair=True,
    )
    assert "tap Unlock" in result
    prompt = captured["messages"][1]["content"]
    assert "CANONICAL AVA PERSONA RUNTIME" in prompt
    assert "Wilmington" not in prompt
    assert "Paid-presentation purpose: PRICE_REQUEST_CONTINUATION" in prompt
    assert "Continuation intent: PRICE_REQUEST" in prompt
    assert "repetition-repair attempt" in prompt
    assert "numeric paid-content price" in prompt


def test_free_teaser_uses_same_canonical_projection():
    gpt = GPTService("test", persona_runtime_service=service())
    captured = {}
    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="little surprise for you 😊"))])
    gpt.openai_client = SimpleNamespace(chat=SimpleNamespace(completions=Completions()))
    gpt.generate_free_engagement_teaser_caption(
        strategy="WARM_UP", grounded_asset_context={"setting": "porch"},
        customer_context={}, recent_conversation=[], global_conversation_training="",
        creator_profile_id=2, fanvue_account_id=2,
    )
    prompt = captured["messages"][1]["content"]
    assert "CANONICAL AVA PERSONA RUNTIME" in prompt
    assert "Wilmington" not in prompt

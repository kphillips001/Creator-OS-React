from datetime import datetime
from types import MappingProxyType, SimpleNamespace

import pytest

from app.services.creator_lifestyle_engine import CreatorLifestyleEngine


class IntelligenceService:
    def __init__(self):
        self.calls = []

    def get_for_account(self, *, fanvue_account_id):
        self.calls.append(fanvue_account_id)
        return SimpleNamespace(
            personality=MappingProxyType({
                "persona_name": "Ava",
                "personality_description": "Confident and approachable",
            }),
            lifestyle=MappingProxyType({
                "career": "Marketing and events",
                "favorite_activities": "Coffee shops, hiking, and bookstores",
            }),
            social_creative_direction=MappingProxyType({
                "purpose": "Visually engaging public social content",
                "wardrobe": "Fitted clothing",
            }),
        )


class WorldRepository:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def get(self, *, creator_profile_id, fanvue_account_id):
        self.calls.append((creator_profile_id, fanvue_account_id))
        return self.document


def test_generates_ten_activity_first_moments_from_all_canonical_inputs():
    intelligence = IntelligenceService()
    world = WorldRepository({
        "id": 9,
        "creator_profile_id": 20,
        "fanvue_account_id": "2",
        "internal_home_base": "Wilmington, North Carolina",
        "public_location_description": "A coastal East Coast city",
        "home_and_indoor_environments": "Home, office, and bookstore",
        "seasonal_activities": "Summer beaches and indoor cooling-off moments",
    })
    captured = []
    generated = "\n".join(
        f"{number}. Authentic lifestyle moment {number}."
        for number in range(1, 11)
    )
    engine = CreatorLifestyleEngine(
        creator_intelligence=intelligence,
        world_model_repository=world,
        creator_profile_loader=lambda account: {"id": 20},
        text_generator=lambda prompt: captured.append(prompt) or generated,
        now=lambda: datetime(2026, 7, 27),
    )

    moments = engine.generate_moments(fanvue_account_id=2)

    assert len(moments) == 10
    assert moments[0] == "Authentic lifestyle moment 1."
    assert intelligence.calls == ["2"]
    assert world.calls == [(20, "2")]
    prompt = captured[0]
    assert "July (summer)" in prompt
    assert "PERSONALITY" in prompt
    assert "LIFESTYLE" in prompt
    assert "SOCIAL CREATIVE DIRECTION" in prompt
    assert "WORLD MODEL" in prompt
    assert "Wilmington, North Carolina" in prompt
    assert "Never reveal the internal home base" in prompt
    assert "scroll-stopping post would she naturally create today" in prompt
    assert "creative seeds, not captions, prompts, activities" in prompt
    assert "specific, authentic, visually compelling moment" in prompt
    assert "playful tension, curiosity, a shared possibility" in prompt
    assert "stopping before a finished caption" in prompt
    assert "Avoid plain activity summaries" in prompt
    assert "generic engagement-bait questions" in prompt
    assert "reviewing proposals" in prompt
    assert "scroll-stopping post potential first" in prompt
    assert "fashion-forward public presentation" in prompt
    assert "Do not include wardrobe" in prompt
    assert "Do not use Brand Memory" in prompt


def test_output_normalization_removes_bullets_duplicates_and_caps_at_ten():
    output = "\n".join([
        "- Coffee before work.",
        "* Coffee before work.",
        *[f"• Moment {index}." for index in range(2, 13)],
    ])
    engine = CreatorLifestyleEngine(
        creator_intelligence=IntelligenceService(),
        world_model_repository=WorldRepository({
            "public_location_description": "A coastal East Coast city",
        }),
        creator_profile_loader=lambda _: {"id": 20},
        text_generator=lambda _: output,
    )

    moments = engine.generate_moments(fanvue_account_id="2")

    assert len(moments) == 10
    assert moments.count("Coffee before work.") == 1
    assert moments[-1] == "Moment 10."


def test_missing_world_model_fails_instead_of_using_legacy_hardcoded_logic():
    engine = CreatorLifestyleEngine(
        creator_intelligence=IntelligenceService(),
        world_model_repository=WorldRepository(None),
        creator_profile_loader=lambda _: {"id": 20},
        text_generator=lambda _: pytest.fail("AI must not run without context"),
    )

    with pytest.raises(LookupError, match="No World Model"):
        engine.generate_moments(fanvue_account_id=2)

from datetime import datetime
from types import MappingProxyType, SimpleNamespace

import pytest

from app.services.autonomous_inspiration_engine import (
    AutonomousInspirationEngine,
)


class Intelligence:
    def get_for_account(self, *, fanvue_account_id):
        assert fanvue_account_id == "2"
        return SimpleNamespace(
            personality=MappingProxyType({
                "persona_name": "Ava",
                "personality_description": "Confident and playful",
            }),
            lifestyle=MappingProxyType({
                "career": "Marketing and events",
                "favorite_activities": "Coast, mountains, and outdoor life",
            }),
            social_creative_direction=MappingProxyType({
                "purpose": "Scroll-stopping public social content",
                "visual_style": (
                    "Confident, feminine, and approachable. Favor soft smiles, "
                    "quiet confidence, playful smirks, relaxed warmth, and "
                    "confident eye contact over exaggerated enthusiasm. "
                    "Occasional larger smiles remain natural when supported."
                ),
            }),
        )


class WorldRepository:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def get(self, *, creator_profile_id, fanvue_account_id):
        self.calls.append((creator_profile_id, fanvue_account_id))
        return self.document


class CreativeProfile:
    def __init__(self, profile=None):
        self.profile = profile or {
            "positive_event_count": 18,
            "negative_event_count": 2,
            "analyzed_image_count": 18,
            "learned_attributes": {
                "environment": {"dock": 8, "rooftop": 2, "cabin": 1},
                "visual_style": {"confident": 9, "playful": 3, "cozy": 1},
                "composition": {"close portrait": 9, "mid-shot": 3, "full body": 1},
                "pose": {"standing": 8, "walking": 2},
                "season": {"summer": 12, "fall": 2},
                "lighting": {"golden hour": 10, "indoor ambient": 2},
                "wardrobe_category": {"casual summer": 8, "dress": 2},
            },
        }
        self.calls = []

    def get_aggregated_profile(self, *, creator_profile_id, fanvue_account_id):
        self.calls.append((creator_profile_id, fanvue_account_id))
        return self.profile


def test_creates_six_private_image_directions_from_canonical_inputs():
    captured = []
    output = "\n".join(
        f"{index}. Distinct scroll-stopping image direction {index}."
        for index in range(1, 7)
    )
    world = WorldRepository({
        "internal_home_base": "Wilmington",
        "public_location_description": "A coastal East Coast city",
        "home_and_indoor_environments": "Home, hotel, and social venues",
        "seasonal_activities": "Summer coast and lake activities",
    })
    creative_profile = CreativeProfile()
    engine = AutonomousInspirationEngine(
        creator_intelligence=Intelligence(),
        creative_intelligence=creative_profile,
        world_model_repository=world,
        creator_profile_loader=lambda _: {"id": 20},
        text_generator=lambda prompt: captured.append(prompt) or output,
        now=lambda: datetime(2026, 7, 27),
    )

    directions = engine.create_directions(fanvue_account_id=2)

    assert len(directions) == 6
    assert directions[0] == "Distinct scroll-stopping image direction 1."
    assert world.calls == [(20, "2")]
    assert creative_profile.calls == [(20, "2")]
    prompt = captured[0]
    assert "most likely to keep and eventually publish" in prompt
    assert "July (summer)" in prompt
    assert "Social Creative Direction is the primary influence" in prompt
    assert "soft smiles, quiet confidence, playful smirks" in prompt
    assert "Occasional larger smiles remain natural when supported" in prompt
    assert "creator as the unmistakable visual subject" in prompt
    assert "books, reading, laptops, paperwork" in prompt
    assert "invented pets, partners, possessions" in prompt
    assert "do not hardcode a fixed outfit formula" in prompt
    assert "at least four distinct environment families" in prompt
    assert "EDITORIAL CINEMATOGRAPHY — OBSERVED MOMENTS" in prompt
    assert "What authentic moment would naturally be photographed?" in prompt
    assert "Prefer observed moments over static portraits" in prompt
    assert "feels discovered rather than staged" in prompt
    assert "off-camera glances, over-the-shoulder moments" in prompt
    assert "static, centered, symmetrical portrait repetition" in prompt
    assert "not another posed portrait" in prompt
    assert "Do not use pose libraries, movement quotas, eye-contact percentages" in prompt
    assert "Creative Intelligence influences selection and balancing" in prompt
    assert (
        "Environment brand anchors: dock (evidence 8), "
        "rooftop (evidence 2), cabin (evidence 1)"
    ) in prompt
    assert "Environment observed variety opportunities: cabin" in prompt
    assert "Composition observed variety opportunities: full body" in prompt
    assert "Visual style observed variety opportunities: cozy" in prompt
    assert "Counts express observed editorial tendencies only" in prompt
    assert "prompts, prompt previews, captions, hashtags" in prompt
    assert "What wardrobe color palette best complements this scene" in prompt
    assert "other five directions together" in prompt
    assert "including basics, layers, and secondary garments" in prompt
    assert "Do not treat a neutral basic as exempt" in prompt
    assert "equally authentic alternatives would complement those scenes" in prompt
    assert "White remains an authentic, available brand element" in prompt
    assert "prefer the choice that improves variety across the current batch" in prompt
    assert "Do not use seasonal color lists" in prompt
    assert "fixed season-to-color mappings" in prompt
    assert "random selection" in prompt
    assert "Carry the resulting wardrobe palette naturally" in prompt
    assert "WARDROBE SILHOUETTE — EDITORIAL REASONING" in prompt
    assert "confident, feminine, stylish, figure-flattering public brand" in prompt
    assert "repeated necklines, silhouettes, garment structures" in prompt
    assert "without forcing more or less exposure" in prompt
    assert "never from a target, percentage, quota, or escalation rule" in prompt
    assert "Do not use wardrobe templates" in prompt
    assert "Avoid drifting toward uniformly conservative commercial fashion" in prompt
    assert "scene-appropriate midriff visibility as normal" in prompt
    assert "never as a required rotation, slot assignment" in prompt
    assert "AUTONOMOUS SWIMWEAR" in prompt
    assert "select a bikini consistent with the scene" in prompt
    assert "Do not select a one-piece swimsuit" in prompt
    assert "Explicit manual wardrobe requests belong to Creative Studio" in prompt
    assert "PERSONALITY" in prompt
    assert "LIFESTYLE" in prompt
    assert "SOCIAL CREATIVE DIRECTION — PRIMARY" in prompt
    assert "WORLD MODEL" in prompt


def test_rejects_incomplete_direction_batches():
    engine = AutonomousInspirationEngine(
        creator_intelligence=Intelligence(),
        creative_intelligence=CreativeProfile({
            "analyzed_image_count": 0,
            "learned_attributes": {},
        }),
        world_model_repository=WorldRepository({
            "public_location_description": "A coastal East Coast city",
        }),
        creator_profile_loader=lambda _: {"id": 20},
        text_generator=lambda _: "Only one direction.",
    )

    with pytest.raises(ValueError, match="fewer than six"):
        engine.create_directions(fanvue_account_id=2)


def test_empty_editorial_memory_preserves_canonical_inspiration_fallback():
    captured = []
    engine = AutonomousInspirationEngine(
        creator_intelligence=Intelligence(),
        creative_intelligence=CreativeProfile({
            "analyzed_image_count": 0,
            "learned_attributes": {},
        }),
        world_model_repository=WorldRepository({
            "public_location_description": "A coastal East Coast city",
        }),
        creator_profile_loader=lambda _: {"id": 20},
        text_generator=lambda prompt: captured.append(prompt) or "\n".join(
            f"Fresh direction {index}" for index in range(6)
        ),
    )

    assert len(engine.create_directions(fanvue_account_id=2)) == 6
    assert "No analyzed retained-image patterns are available yet" in captured[0]


def test_wardrobe_color_guidance_contains_no_deterministic_seasonal_palette():
    from pathlib import Path

    source = Path(
        "app/services/autonomous_inspiration_engine.py"
    ).read_text(encoding="utf-8").lower()

    forbidden_mappings = (
        "summer ->",
        "summer:",
        "fall ->",
        "fall:",
        "winter ->",
        "winter:",
        "spring ->",
        "spring:",
        "seasonal_color",
        "color_weights",
        "random.choice",
    )
    assert not any(mapping in source for mapping in forbidden_mappings)


def test_silhouette_reasoning_contains_no_exposure_targets_or_wardrobe_templates():
    from pathlib import Path

    source = Path(
        "app/services/autonomous_inspiration_engine.py"
    ).read_text(encoding="utf-8").lower()
    forbidden_implementation = (
        "exposure_percentage",
        "coverage_percentage",
        "coverage_weights",
        "wardrobe_templates =",
        "silhouette_rotation =",
        "required_wardrobe =",
        "random.choice",
    )
    assert not any(value in source for value in forbidden_implementation)

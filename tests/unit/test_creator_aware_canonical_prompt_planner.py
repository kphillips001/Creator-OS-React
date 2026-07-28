from types import MappingProxyType, SimpleNamespace
from datetime import datetime

import pytest

from app.services.creator_aware_canonical_prompt_planner import (
    CreatorAwareCanonicalPromptPlanner,
)


class Intelligence:
    def __init__(self):
        self.calls = []

    def get_for_account(self, *, fanvue_account_id):
        self.calls.append(fanvue_account_id)
        return SimpleNamespace(
            personality=MappingProxyType({
                "persona_name": "Ava Blackthorne",
                "personality_description": "Confident and approachable",
            }),
            lifestyle=MappingProxyType({
                "lifestyle_overview": "Athletic coastal lifestyle",
            }),
            social_creative_direction=MappingProxyType({
                "visual_style": "Feminine, authentic, and socially engaging",
            }),
        )


class World:
    def __init__(self):
        self.calls = []

    def get(self, *, creator_profile_id, fanvue_account_id):
        self.calls.append((creator_profile_id, fanvue_account_id))
        return {
            "creator_profile_id": creator_profile_id,
            "public_location_description": "Coastal East Coast city",
        }


class Creative:
    def __init__(self):
        self.calls = []

    def get_aggregated_profile(self, *, creator_profile_id, fanvue_account_id):
        self.calls.append((creator_profile_id, fanvue_account_id))
        return MappingProxyType({
            "analyzed_image_count": 12,
            "learned_attributes": MappingProxyType({
                "environment": MappingProxyType({"marina": 5}),
                "visual_style": MappingProxyType({"candid": 4}),
            }),
        })


def test_builds_private_creator_aware_question_from_all_five_sources():
    intelligence = Intelligence()
    world = World()
    creative = Creative()
    planner = CreatorAwareCanonicalPromptPlanner(
        creator_intelligence=intelligence,
        creative_intelligence=creative,
        world_model_repository=world,
        creator_profile_loader=lambda account_id: {
            "id": 42,
            "fanvue_account_id": account_id,
        },
        now=lambda: datetime(2026, 7, 27),
    )

    prompt = planner.build_question(
        fanvue_account_id=2,
        question="Give me ten locations.",
    )

    assert intelligence.calls == ["2"]
    assert world.calls == [(42, "2")]
    assert creative.calls == [(42, "2")]
    assert "I have been Ava's creative director for years" in prompt
    assert "always assume the request is about Ava" in prompt
    assert "PERSONALITY:" in prompt
    assert "Athletic coastal lifestyle" in prompt
    assert "SOCIAL CREATIVE DIRECTION:" in prompt
    assert "Coastal East Coast city" in prompt
    assert "CREATIVE INTELLIGENCE — AGGREGATED PROFILE ONLY:" in prompt
    assert '"marina": 5' in prompt
    assert "Do not force coastal" in prompt
    assert "historical prompts, captions, or prior" in prompt
    assert "planner responses" in prompt
    assert "date: July 27, 2026" in prompt
    assert "season: summer" in prompt
    assert "Do not invent pets, partners, possessions" in prompt
    assert prompt.endswith("Give me ten locations.")
    assert "creator_profile_id" not in prompt
    assert "fanvue_account_id" not in prompt


def test_rejects_empty_questions_before_loading_context():
    intelligence = Intelligence()
    planner = CreatorAwareCanonicalPromptPlanner(
        creator_intelligence=intelligence,
    )

    with pytest.raises(ValueError, match="Enter a question"):
        planner.build_question(fanvue_account_id=2, question=" ")

    assert intelligence.calls == []

from types import SimpleNamespace

import pytest

from app.models.photoshoot_queue import CanonicalPhotoshootSeedSummary
from app.services.photoshoot_creative_director_service import (
    PhotoshootCreativeDirectorWorkflowService,
)


class Queue:
    def __init__(self, creative_mode="explicit"):
        self.persisted = None
        self.session = SimpleNamespace(
            session_id="session-1",
            creator_profile_id=7,
            creative_mode=creative_mode,
            creative_continuity={
                "seed_image_id": "seed-1",
                "seed_prompt_text": "Seed image prompt",
                "canonical_seed_summary": {
                    "scene": "A confident portrait beside a hotel window.",
                    "wardrobe": "Black dress.",
                    "mood_and_editorial_intent": "Intimate cinematic confidence.",
                    "creator_identity": "Preserve the same creator.",
                    "artistic_intent": "Tasteful premium editorial.",
                },
                "original_photoshoot_direction": "Seed image prompt",
                "continuity_locks": {"wardrobe": True, "lighting": True},
                "photoshoot_summary": {
                    "summary_text": "Maintain the intimate hotel editorial.",
                    "current_location": "Hotel suite",
                    "current_wardrobe": "Black dress",
                    "lighting": "Warm window light",
                    "visual_style": "Cinematic portrait",
                    "avoid_repetition": "Avoid another seated medium close-up.",
                },
                "session_defaults": {
                    "camera_style": "Preserve the established camera style.",
                    "hairstyle": "Preserve loose dark hair.",
                    "makeup": "Preserve natural makeup.",
                    "identity_continuity": "Preserve the same creator identity.",
                },
                "approved_directions": ({
                    "creative_direction": "Stand beside the window.",
                    "camera_framing": "Full body",
                },),
                "progression_stage": 2,
                "creator_guidance": "Increase emotional intensity.",
                "workflow_stage": "recommendation_ready",
                "photoshoot_summary_updated_at": "2026-07-30T18:00:00Z",
                "seed_output_reference": "https://cdn.test/seed.png",
                "generation_job_id": "generation-job-uuid",
                "current_direction": {
                    "creative_direction": "Turn toward the window.",
                    "camera_framing": "Medium close-up",
                    "lighting": "Warm window light",
                    "emotion": "Confident",
                    "pose_composition": "Seated turn",
                    "continuity_notes": "Keep the wardrobe",
                    "session_direction": "Seed image prompt",
                },
            },
        )

    def get_session(self, session_id):
        return self.session

    def requests_for_session(self, session_id):
        return ()

    def record_creative_direction(self, **kwargs):
        self.persisted = kwargs


class Library:
    def get(self, image_id):
        return SimpleNamespace(prompt_text="Seed image prompt")


class Planner:
    def __init__(self):
        self.request = None

    def plan_prompts(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(prompts=("Final canonical prompt",))


def test_seed_summary_removes_provider_sections_and_preserves_creative_foundation():
    summary = CanonicalPhotoshootSeedSummary.from_provider_prompt(
        "A portrait beside a hotel window in a black dress, warm sunset light, intimate cinematic mood, "
        "medium-format editorial photography.\n\n"
        "PROVIDER OPTIMIZATION\nFINAL REFERENCE BODY LOCK - NON-NEGOTIABLE:\n"
        "Provider-specific implementation instructions."
    )

    assert summary.scene == (
        "A portrait beside a hotel window in a black dress, warm sunset light, intimate cinematic mood, "
        "medium-format editorial photography."
    )
    assert "PROVIDER" not in summary.to_prompt_text()
    assert "REFERENCE BODY LOCK" not in summary.to_prompt_text()


def test_unstructured_legacy_provider_prompt_uses_clean_creative_tags_for_new_summary():
    summary = CanonicalPhotoshootSeedSummary.from_provider_prompt(
        "Provider-oriented implementation language. " * 300,
        creative_tags=("hotel window portrait", "black dress", "warm sunset light"),
    )

    assert summary.scene == "hotel window portrait; black dress; warm sunset light"
    assert len(summary.to_prompt_text()) < 200


def test_existing_session_without_seed_summary_uses_provider_prompt_fallback():
    queue = Queue("premium")
    queue.session.creative_continuity.pop("canonical_seed_summary")
    planner = Planner()
    service = PhotoshootCreativeDirectorWorkflowService(
        queue=queue,
        library=Library(),
        creative_director=planner,
        summary_service=object(),
    )

    service.approve(creator_profile_id=7, session_id="session-1")

    assert "Photoshoot Seed Summary: Seed image prompt" in planner.request["creative_tags"]


@pytest.mark.parametrize(
    ("creative_mode", "planner_mode"),
    (
        ("safe", "photoshoot_safe"),
        ("premium", "photoshoot_premium"),
        ("explicit", "photoshoot_explicit"),
    ),
)
def test_photoshoot_approval_is_one_concept_and_returns_complete_contract(
    creative_mode,
    planner_mode,
):
    queue = Queue(creative_mode)
    planner = Planner()
    service = PhotoshootCreativeDirectorWorkflowService(
        queue=queue,
        library=Library(),
        creative_director=planner,
        summary_service=object(),
    )

    result = service.approve(creator_profile_id=7, session_id="session-1")

    assert planner.request["mode"] == planner_mode
    assert "\n" not in planner.request["creative_tags"]
    assert "Camera framing: Medium close-up" in planner.request["creative_tags"]
    assert "Continuity notes: Keep the wardrobe" in planner.request["creative_tags"]
    assert "Photoshoot Seed Summary: Original scene: A confident portrait beside a hotel window." in planner.request["creative_tags"]
    assert "Wardrobe foundation: Black dress." in planner.request["creative_tags"]
    assert "Seed image prompt" not in planner.request["creative_tags"]
    assert "Photoshoot summary: Maintain the intimate hotel editorial." in planner.request["creative_tags"]
    assert "Latest approved direction: Stand beside the window. Camera framing: Full body" in planner.request["creative_tags"]
    assert "Current wardrobe: Black dress" in planner.request["creative_tags"]
    assert "Current location: Hotel suite" in planner.request["creative_tags"]
    assert "Continuity locks: lighting=locked, wardrobe=locked" in planner.request["creative_tags"]
    assert "Progression stage: 2" in planner.request["creative_tags"]
    assert "Operator guidance: Increase emotional intensity." in planner.request["creative_tags"]
    assert "Required identity instructions: Preserve the same creator identity." in planner.request["creative_tags"]
    for operational_value in (
        "workflow_stage",
        "recommendation_ready",
        "photoshoot_summary_updated_at",
        "2026-07-30T18:00:00Z",
        "seed_output_reference",
        "https://cdn.test/seed.png",
        "generation_job_id",
        "generation-job-uuid",
    ):
        assert operational_value not in planner.request["creative_tags"]
    assert '{"' not in planner.request["creative_tags"]
    assert queue.persisted["final_prompt"] == "Final canonical prompt"
    assert result == {
        "prompt": "Final canonical prompt",
        "recommendation": queue.session.creative_continuity["current_direction"],
        "approval_state": "approved",
        "workflow_stage": "direction_approved",
    }

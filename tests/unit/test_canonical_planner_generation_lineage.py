from types import SimpleNamespace

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationRequest
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.content_studio_generation_service import (
    ContentStudioGenerationService,
)


SCENE = (
    "Golden Hour Marina Walk — Ava wears a coral crop top and denim shorts "
    "while walking beside the marina at sunset, brushing her hair back as "
    "she glances toward the water."
)
ENHANCED = (
    "confident feminine Ava styling, authentic coastal lifestyle, candid "
    "asymmetrical editorial movement"
)
SOURCE = (
    f"[ORIGINAL USER TAGS — mandatory: {SCENE}] "
    f"[ENHANCED SUGGESTIONS — creator-aware: {ENHANCED}]"
)


class Director:
    def __init__(self):
        self.calls = []

    def create_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        return PromptPlan(
            plan_id="planner-plan-1",
            session_id="planner-session-1",
            creator_profile_id=2,
            prompt_text=SOURCE,
            creative_mode="premium_teaser",
            creative_tags=(SOURCE,),
            reference_asset_id=84,
            reference_asset_path="https://example.test/reference.png",
            creative_rationale="Planner-origin test",
            prompt_metadata={
                "prompt_variations": (SOURCE,),
                **kwargs["metadata"],
            },
        )


class Engine:
    def __init__(self):
        self.calls = []

    def queue_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(job_id="planner-job-1")


def test_lineage_and_complete_scene_reach_seedream_payload_without_truncation():
    director = Director()
    engine = Engine()
    lineage = {
        "plannerQuestion": "Give me marina ideas",
        "plannerItemId": "planner-1",
        "plannerItemTitle": "Golden Hour Marina Walk",
        "selectedPlannerItem": SCENE,
        "enhancedResult": ENHANCED,
    }
    service = ContentStudioGenerationService(
        creative_director=director,
        generation_engine=engine,
        generation_library=SimpleNamespace(),
        reference_service=SimpleNamespace(),
    )

    plan, job = service.queue(
        creator_profile={"id": 2},
        creative_tags=SOURCE,
        creative_mode="premium_teaser",
        prompt_count=1,
        provider_id="seedream_5_0_pro",
        prompt_batch=(),
        origin="canonical_planner",
        planner_lineage=lineage,
    )

    assert job.job_id == "planner-job-1"
    assert director.calls[0]["metadata"] == {
        "workflow_origin": "canonical_planner",
        "planner_lineage": lineage,
    }
    queued = engine.calls[0]
    assert queued["metadata"]["workflow_origin"] == "canonical_planner"
    assert queued["metadata"]["planner_lineage"] == lineage

    request = GenerationRequest(
        request_id="request-1",
        creator_profile_id=2,
        prompt_plan_id=plan.plan_id,
        prompt_text=plan.prompt_text,
        reference_asset_id=84,
        reference_asset_path="https://example.test/reference.png",
        provider_id="seedream_5_0_pro",
        generation_type="image_to_image",
        media_type="image",
        metadata={
            **queued["metadata"],
            "creative_mode": "premium_teaser",
            "prompt_variations": plan.prompt_metadata["prompt_variations"],
        },
    )
    payload = Seedream50ProProvider().build_payload(request)
    provider_prompt = payload["prompt"]

    for expected in (
        "coral crop top", "denim shorts", "walking beside the marina",
        "sunset", "brushing her hair back", "glances toward the water",
        "authentic coastal lifestyle", "candid asymmetrical editorial movement",
    ):
        assert expected in provider_prompt
    assert provider_prompt.startswith(SOURCE)
    assert "FINAL REFERENCE BODY LOCK" in provider_prompt

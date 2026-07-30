from types import SimpleNamespace

from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationRequest
from app.prompts.seedream_premium_prompt_builder import (
    build_seedream_premium_prompt,
)
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.canonical_prompt_planner import (
    CanonicalPromptPlanner,
    CanonicalPromptPlanningRequest,
)
from app.services.content_studio_generation_service import (
    ContentStudioGenerationService,
)
from app.services.creative_director_service import CreativeDirectorService
from app.services.seedream_premium_render_locks import (
    enforce_premium_render_body_lock,
)


def test_seedream_premium_instruction_has_no_wan_assumptions():
    instruction = build_seedream_premium_prompt(
        creative_tags="hotel window, satin dress, reflective expression",
        prompt_count=2,
    )

    assert "Seedream 5.0 Pro" in instruction
    assert "WAN" not in instruction.upper()
    assert "CANONICAL PLANNING ARCHITECTURE" in instruction
    assert "EDITORIAL DIRECTION" in instruction
    assert "PROVIDER OPTIMIZATION" in instruction


def test_premium_canonical_metadata_targets_seedream(monkeypatch):
    monkeypatch.setattr(
        "app.services.canonical_prompt_planner.generate_premium_prompts",
        lambda **_kwargs: ("seedream premium prompt",),
    )

    result = CanonicalPromptPlanner().plan(
        CanonicalPromptPlanningRequest(
            mode="premium",
            creative_tags="hotel window",
            prompt_count=1,
        )
    )

    assert result.prompt_builder == "canonical_seedream_premium_planner"
    assert result.metadata["provider_target"] == "seedream_5_0_pro"
    assert result.metadata["provider_optimization"] == (
        "seedream_5_0_pro_native"
    )
    assert "renderer_neutral" not in result.metadata
    assert result.metadata["canonical_planning_order"] == (
        "scene",
        "editorial_guidance",
        "editorial_direction",
        "wardrobe",
        "creator_identity",
        "visual_quality",
        "provider_optimization",
    )


class ReferenceLibrary:
    def get_active_canonical_reference(self, **_kwargs):
        return None


def test_spicy_creative_studio_mode_uses_seedream_canonical_planner(
    monkeypatch, tmp_path
):
    service = CreativeDirectorService(
        storage_dir=tmp_path,
        reference_library_service=ReferenceLibrary(),
    )
    calls = []
    monkeypatch.setattr(
        service,
        "plan_prompts",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(
            prompts=("seedream spicy premium prompt",),
            prompt_builder="canonical_seedream_premium_planner",
            mode="premium",
            metadata={
                "canonical_planner": "creator_os",
                "planning_mode": "premium",
                "provider_target": "seedream_5_0_pro",
            },
        ),
    )
    monkeypatch.setattr(
        service,
        "build_diversified_prompt_batch",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("Spicy reached the Social builder")
        ),
    )

    plan = service.create_prompt_plan(
        creator_profile={"id": 7},
        creative_tags="spicy hotel direction",
        creative_mode="spicy",
        prompt_count=1,
    )

    assert calls[0]["mode"] == "spicy"
    assert plan.prompt_metadata["prompt_builder"] == (
        "canonical_seedream_premium_planner"
    )


class ProviderReadyDirector:
    def __init__(self):
        self.provider_calls = []
        self.planning_calls = []

    def create_provider_prompt_plan(self, **kwargs):
        self.provider_calls.append(kwargs)
        return PromptPlan(
            plan_id="premium-provider-plan",
            session_id="premium-provider-session",
            creator_profile_id=7,
            prompt_text=kwargs["prompts"][0],
            creative_mode=kwargs["creative_mode"],
            creative_tags=(kwargs["creative_tags"],),
            reference_asset_id=84,
            reference_asset_path="https://example.test/reference.png",
            creative_rationale="provider ready",
            prompt_metadata={
                "prompt_variations": kwargs["prompts"],
                **kwargs["metadata"],
            },
        )

    def create_prompt_plan(self, **kwargs):
        self.planning_calls.append(kwargs)
        raise AssertionError("previewed Premium prompts were replanned")


class Engine:
    def __init__(self):
        self.calls = []

    def queue_prompt_plan(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(job_id="premium-job")


def test_previewed_premium_batch_is_reused_without_hidden_replanning():
    director = ProviderReadyDirector()
    engine = Engine()
    preview_prompt = enforce_premium_render_body_lock(
        "Seedream premium hotel-window prompt"
    )
    service = ContentStudioGenerationService(
        creative_director=director,
        generation_engine=engine,
        generation_library=SimpleNamespace(),
        reference_service=SimpleNamespace(),
    )

    plan, job = service.queue(
        creator_profile={"id": 7},
        creative_tags="hotel window",
        creative_mode="premium_teaser",
        prompt_count=1,
        provider_id="seedream_5_0_pro",
        prompt_batch=(preview_prompt,),
    )

    assert job.job_id == "premium-job"
    assert director.planning_calls == []
    assert director.provider_calls[0]["prompts"] == (preview_prompt,)
    assert plan.prompt_metadata["prompt_variations"] == (preview_prompt,)


def test_seedream_receives_exact_provider_ready_preview_prompt():
    preview_prompt = enforce_premium_render_body_lock(
        "Seedream premium balcony prompt"
    )
    request = GenerationRequest(
        request_id="request-1",
        creator_profile_id=7,
        prompt_plan_id="plan-1",
        prompt_text=preview_prompt,
        reference_asset_id=84,
        reference_asset_path="https://example.test/reference.png",
        provider_id="seedream_5_0_pro",
        generation_type="image_to_image",
        media_type="image",
        metadata={
            "creative_mode": "premium_teaser",
            "workflow_type": "premium",
        },
    )

    payload = Seedream50ProProvider().build_payload(request)

    assert payload["prompt"] == preview_prompt
    assert enforce_premium_render_body_lock(payload["prompt"]) == preview_prompt

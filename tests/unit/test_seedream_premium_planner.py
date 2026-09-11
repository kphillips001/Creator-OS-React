import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

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
from app.services.generation_request_diagnostic_service import GenerationRequestDiagnosticService
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


@pytest.mark.parametrize(
    "expression",
    (
        "Direct over-the-shoulder glance with a calm, mildly inviting closed-mouth look",
        "Neutral direct gaze",
        "Soft parted-lips expression",
        "Serious focused expression",
    ),
)
def test_live_recreate_provider_ready_path_preserves_source_expression_authority(
    expression, tmp_path,
):
    director = ProviderReadyDirector()
    engine = Engine()
    service = ContentStudioGenerationService(
        creative_director=director,
        generation_engine=engine,
        generation_library=SimpleNamespace(),
        reference_service=SimpleNamespace(),
    )
    structured_source = (
        "[ORIGINAL USER TAGS — mandatory: Scene: bright living room, "
        f"Expression: {expression}, Camera Framing: medium close]"
    )
    provider_ready_prompt = (
        "Ava kneels on a cream sofa and looks over her shoulder with "
        f"{expression}."
    )

    plan, _job = service.queue(
        creator_profile={"id": 2},
        creative_tags=structured_source,
        creative_mode="premium_teaser",
        prompt_count=1,
        provider_id="seedream_5_0_pro",
        prompt_batch=(provider_ready_prompt,),
        origin="recreate_with_ava",
        diagnostic_trace_id="live-recreate-stage-12",
    )
    queued = engine.calls[0]
    assert queued["metadata"]["render_policy"] == "CONTENT_SPICY"
    assert queued["metadata"]["workflow_origin"] == "recreate_with_ava"
    assert queued["metadata"]["recreate_source_expression_authoritative"] is True

    request = GenerationRequest(
        request_id="live-recreate-request",
        creator_profile_id=2,
        prompt_plan_id=plan.plan_id,
        prompt_text=plan.prompt_text,
        reference_asset_id=93,
        reference_asset_path="https://cdn.test/asset-93.png",
        provider_id="seedream_5_0_pro",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
        metadata={
            **queued["metadata"],
            "canonical_reference_image_url": "https://cdn.test/asset-93.png",
            "reference_image_url": "https://cdn.test/asset-93.png",
            "diagnostic_trace_id": "live-recreate-stage-12",
        },
    )
    trace_path = tmp_path / "traces.json"
    with patch.object(GenerationRequestDiagnosticService, "storage_path", trace_path):
        payload = Seedream50ProProvider(api_key="test-key", http_client=SimpleNamespace()).build_payload(request)
    stage_12 = next(
        event["value"]
        for event in json.loads(trace_path.read_text(encoding="utf-8"))["live-recreate-stage-12"]["events"]
        if event["stage"] == "12_final_provider_prompt"
    )
    assert expression in stage_12
    assert "CANONICAL AVA FACIAL NATURALISM - NON-NEGOTIABLE:" in stage_12
    assert "EXPLICIT EXPRESSION VARIATION:" not in stage_12
    assert "teasing coy smirk, fully open seductive eyes, alluring private appeal" not in stage_12
    assert payload["prompt"] == stage_12


def test_live_recreate_provider_ready_path_without_expression_keeps_fallback():
    director = ProviderReadyDirector()
    engine = Engine()
    service = ContentStudioGenerationService(
        creative_director=director,
        generation_engine=engine,
        generation_library=SimpleNamespace(),
        reference_service=SimpleNamespace(),
    )
    plan, _job = service.queue(
        creator_profile={"id": 2},
        creative_tags="[ORIGINAL USER TAGS — mandatory: Scene: bright living room, Mood: calm]",
        creative_mode="premium_teaser",
        prompt_count=1,
        provider_id="seedream_5_0_pro",
        prompt_batch=("Ava sits calmly in a bright living room.",),
        origin="recreate_with_ava",
    )
    queued = engine.calls[0]
    assert queued["metadata"]["recreate_source_expression_authoritative"] is False
    request = GenerationRequest(
        request_id="recreate-no-expression",
        creator_profile_id=2,
        prompt_plan_id=plan.plan_id,
        prompt_text=plan.prompt_text,
        reference_asset_id=93,
        reference_asset_path="https://cdn.test/asset-93.png",
        provider_id="seedream_5_0_pro",
        generation_type="image_to_image",
        media_type="image",
        image_count=1,
        metadata={
            **queued["metadata"],
            "canonical_reference_image_url": "https://cdn.test/asset-93.png",
        },
    )
    rendered = Seedream50ProProvider(api_key="test-key", http_client=SimpleNamespace())._render_prompt_text(request)
    assert "EXPLICIT EXPRESSION VARIATION:" in rendered

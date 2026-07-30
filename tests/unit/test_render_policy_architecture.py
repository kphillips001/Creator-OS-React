from dataclasses import replace
from unittest.mock import patch

import pytest

from app.models.generation_engine import GenerationRequest
from app.models.render_policy import (
    RenderPolicy,
    content_render_policy,
    photoshoot_planning_mode,
    photoshoot_render_policy,
)
from app.providers.generation.base import GenerationProviderError
from app.providers.generation.seedream_provider import Seedream45Provider
from app.services.canonical_prompt_planner import (
    CanonicalPromptPlanner,
    CanonicalPromptPlanningRequest,
)


def _request(policy: RenderPolicy) -> GenerationRequest:
    return GenerationRequest(
        request_id="request-1",
        creator_profile_id=7,
        prompt_plan_id="plan-1",
        prompt_text="Original workflow prompt.",
        reference_asset_id=84,
        reference_asset_path="https://example.test/reference.png",
        provider_id="seedream_4_5",
        generation_type="image_to_image",
        media_type="image",
        metadata={"render_policy": policy.value},
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("standard", RenderPolicy.CONTENT_STANDARD),
        ("spicy", RenderPolicy.CONTENT_SPICY),
        ("explicit", RenderPolicy.CONTENT_EXPLICIT),
    ],
)
def test_content_workflow_maps_explicit_render_policy(mode, expected):
    assert content_render_policy(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected_policy", "expected_planner"),
    [
        ("safe", RenderPolicy.PHOTOSHOOT_SAFE, "photoshoot_safe"),
        ("premium", RenderPolicy.PHOTOSHOOT_PREMIUM, "photoshoot_premium"),
        ("explicit", RenderPolicy.PHOTOSHOOT_EXPLICIT, "photoshoot_explicit"),
    ],
)
def test_photoshoot_workflow_maps_policy_and_planner(mode, expected_policy, expected_planner):
    assert photoshoot_render_policy(mode) == expected_policy
    assert photoshoot_planning_mode(mode) == expected_planner


def test_provider_routes_only_from_render_policy_and_rejects_unknown():
    provider = Seedream45Provider()
    with pytest.raises(GenerationProviderError, match="Unknown or missing render policy"):
        provider._render_prompt_text(replace(_request(RenderPolicy.EDIT), metadata={}))
    with pytest.raises(GenerationProviderError, match="Unknown or missing render policy"):
        provider._render_prompt_text(
            replace(_request(RenderPolicy.EDIT), metadata={"render_policy": "PHOTOSHOOT"})
        )


def test_photoshoot_and_edit_never_append_social_render_lock():
    provider = Seedream45Provider()
    for policy in (
        RenderPolicy.PHOTOSHOOT_SAFE,
        RenderPolicy.PHOTOSHOOT_PREMIUM,
        RenderPolicy.PHOTOSHOOT_EXPLICIT,
        RenderPolicy.EDIT,
    ):
        rendered = provider._render_prompt_text(_request(policy))
        assert "SOCIAL CLOSE-FRAMING LOCK" not in rendered
    assert "PHOTOSHOOT SAFE CONTINUITY LOCK" in provider._render_prompt_text(
        _request(RenderPolicy.PHOTOSHOOT_SAFE)
    )
    assert provider._render_prompt_text(_request(RenderPolicy.EDIT)) == "Original workflow prompt."


def test_content_standard_uses_social_lock_but_content_explicit_does_not():
    provider = Seedream45Provider()
    assert "SOCIAL CLOSE-FRAMING LOCK" in provider._render_prompt_text(
        _request(RenderPolicy.CONTENT_STANDARD)
    )
    assert "SOCIAL CLOSE-FRAMING LOCK" not in provider._render_prompt_text(
        _request(RenderPolicy.CONTENT_EXPLICIT)
    )


@patch("app.services.photoshoot_prompt_service.generate_premium_prompts")
@patch("app.services.canonical_prompt_planner.generate_premium_prompts")
def test_safe_and_premium_photoshoot_planning_are_separate(generate_premium, safe_generator):
    generate_premium.return_value = ["planned prompt"]
    safe_generator.return_value = ["safe planned prompt"]
    planner = CanonicalPromptPlanner()
    safe = planner.plan(CanonicalPromptPlanningRequest(
        mode="photoshoot_safe", creative_tags="continue the shoot", prompt_count=1,
    ))
    safe_tags = safe_generator.call_args.kwargs["creative_tags"]
    premium = planner.plan(CanonicalPromptPlanningRequest(
        mode="photoshoot_premium", creative_tags="continue the shoot", prompt_count=1,
    ))
    assert safe.mode == "photoshoot_safe"
    assert premium.mode == "photoshoot_premium"
    assert "natural and non-sensual" in safe_tags
    assert premium.prompt_builder == "canonical_photoshoot_premium_prompt_planner"

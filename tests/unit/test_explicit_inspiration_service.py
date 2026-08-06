from app.api.content_studio import ExplicitInspirationRequest
from app.services.creative_diversity_guidance import CREATIVE_DIVERSITY_DIMENSIONS
from app.services.explicit_inspiration_service import ExplicitInspirationService
from app.services.explicit_editorial_guidance import ExplicitEditorialGuidance
import app.services.explicit_prompt_service as explicit_prompt_service
from app.services.explicit_prompt_service import (
    build_explicit_prompt_instruction,
    compact_explicit_anchor_line,
    extract_editorial_direction,
    generate_explicit_prompts,
)
from app.services.explicit_expression_profile import (
    EXPLICIT_EXPRESSION_SECTION,
    ExplicitExpressionProfileService,
)
from app.services.seedream_premium_render_locks import enforce_premium_render_body_lock


def semantic_fields(text: str) -> dict[str, set[str]]:
    """Small test-only semantic projection; assertions do not depend on prose."""
    lowered = text.lower()
    vocabulary = {
        "environment": ("window", "bed", "shower"),
        "wardrobe": ("topless", "fully nude", "buttoned shirt", "towel"),
        "framing": ("waist-up", "full-body", "close-up"),
        "angle": ("low angle", "eye-level", "three-quarter"),
        "composition": ("standing", "kneeling", "reclining", "legs spread"),
        "lighting": ("moonlight", "golden hour", "soft daylight"),
        "mood": ("intimate", "playful", "defiant"),
        "activity": ("masturbating", "fingering", "rubbing her clit"),
        "visibility": ("nipples visible", "pussy visible", "bare breasts"),
        "progression": ("then", "as she", "while"),
    }
    return {
        field: {term for term in terms if term in lowered}
        for field, terms in vocabulary.items()
    }


def test_explicit_inspiration_returns_hardcore_and_softcore_lists():
    captured = []
    call_count = {"n": 0}

    def fake_generator(prompt: str) -> str:
        captured.append(prompt)
        call_count["n"] += 1
        tier = "softcore" if "SOFTCORE REQUIREMENTS" in prompt else "hardcore"
        return "\n".join(f"{tier} visual concept {index}" for index in range(1, 6))

    service = ExplicitInspirationService(
        profile_loader=lambda _account_id: {
            "id": 42,
            "fanvue_account_id": 7,
            "name": "Ava",
            "unsupported_secret": None,
        },
        text_generator=fake_generator,
    )

    result = service.create_concepts(fanvue_account_id=7, count_per_tier=5)

    assert len(result.hardcore) == 5
    assert len(result.softcore) == 5
    assert len(set(result.hardcore) | set(result.softcore)) == 10
    assert call_count["n"] == 2
    assert any("HARDCORE REQUIREMENTS" in prompt for prompt in captured)
    assert any("SOFTCORE REQUIREMENTS" in prompt for prompt in captured)
    assert all("Do not invent biographical facts" in prompt for prompt in captured)
    assert all('"id"' not in prompt for prompt in captured)
    assert all("Ava" not in prompt for prompt in captured)
    assert all("REFERENCE IDENTITY LOCK" not in prompt for prompt in captured)
    assert all("Identity, reference-image continuity" in prompt for prompt in captured)
    assert all("CREATIVE DIVERSITY ENGINE" in prompt for prompt in captured)
    assert all("COLLECTION REVIEW" in prompt for prompt in captured)
    assert all(
        all(dimension in prompt for dimension in CREATIVE_DIVERSITY_DIMENSIONS)
        for prompt in captured
    )
    assert all("Do not use fixed slots, scene templates" in prompt for prompt in captured)
    assert all("Do not repeat the same combination" in prompt for prompt in captured)
    assert all("Start directly with the scene or action" in prompt for prompt in captured)
    # Softcore call should be told to avoid repeating hardcore concepts.
    softcore_prompt = next(prompt for prompt in captured if "SOFTCORE REQUIREMENTS" in prompt)
    assert "already-generated concepts" in softcore_prompt
    assert "hardcore visual concept 1" in softcore_prompt


def test_explicit_inspiration_rejects_incomplete_hardcore_output():
    service = ExplicitInspirationService(
        profile_loader=lambda _account_id: {"id": 42, "name": "Ava"},
        text_generator=lambda prompt: (
            "Only one hardcore concept"
            if "HARDCORE REQUIREMENTS" in prompt
            else "\n".join(f"softcore concept {index}" for index in range(1, 6))
        ),
    )

    try:
        service.create_concepts(fanvue_account_id=7, count_per_tier=5)
    except ValueError as error:
        assert "hardcore" in str(error).lower()
        assert "too few" in str(error).lower()
    else:
        raise AssertionError("Incomplete hardcore concept output should be rejected")


def test_explicit_inspiration_rejects_incomplete_softcore_output():
    service = ExplicitInspirationService(
        profile_loader=lambda _account_id: {"id": 42, "name": "Ava"},
        text_generator=lambda prompt: (
            "\n".join(f"hardcore concept {index}" for index in range(1, 6))
            if "HARDCORE REQUIREMENTS" in prompt
            else "Only one softcore concept"
        ),
    )

    try:
        service.create_concepts(fanvue_account_id=7, count_per_tier=5)
    except ValueError as error:
        assert "softcore" in str(error).lower()
        assert "too few" in str(error).lower()
    else:
        raise AssertionError("Incomplete softcore concept output should be rejected")


def test_canonical_explicit_prompt_stage_injects_identity_after_scene_inspiration():
    instruction = build_explicit_prompt_instruction(
        enhanced_explicit_tags="Reclining beside a rain-streaked window",
        prompt_count=1,
    )

    assert "REFERENCE IDENTITY LOCK" in instruction
    assert "Use the reference image for identity, face, hair, skin tone" in instruction
    assert "same face" in instruction
    assert "EXPLICIT HAIR CONTINUITY LOCK" in instruction


def test_long_selected_concept_survives_enhancement_compaction():
    concept = (
        "Standing topless beside the window in soft daylight, eye-level waist-up "
        "framing, nipples visible, playful and intimate"
    )

    enhanced = compact_explicit_anchor_line(
        raw_line=concept,
        enhanced_line="buttoned shirt, bedroom, editorial realism",
    )

    expected = semantic_fields(concept)
    actual = semantic_fields(enhanced)
    assert expected["environment"] <= actual["environment"]
    assert expected["wardrobe"] <= actual["wardrobe"]
    assert expected["framing"] <= actual["framing"]
    assert expected["angle"] <= actual["angle"]
    assert expected["composition"] <= actual["composition"]
    assert expected["lighting"] <= actual["lighting"]
    assert expected["mood"] <= actual["mood"]
    assert expected["visibility"] <= actual["visibility"]


def test_canonical_planner_restores_all_selected_semantics_when_model_softens(monkeypatch):
    concept = (
        "Fully nude by the shower window in moonlight, kneeling in a three-quarter "
        "close-up while fingering herself, pussy visible, then looking into camera"
    )
    softened_model_output = (
        "1. Wearing a wrapped towel on a bed, she poses in tasteful implied tease, "
        "editorial realism and detailed natural skin"
    )
    monkeypatch.setattr(
        "app.services.explicit_prompt_service.get_grok_api_key",
        lambda: "test-key",
    )
    monkeypatch.setattr(
        "app.services.explicit_prompt_service.generate_prompts_with_grok",
        lambda _instruction, _key: softened_model_output,
    )

    final_prompt = generate_explicit_prompts(concept, 1)[0]
    expected = semantic_fields(concept)
    actual = semantic_fields(final_prompt)

    for field in (
        "environment",
        "wardrobe",
        "framing",
        "angle",
        "composition",
        "lighting",
        "activity",
        "visibility",
        "progression",
    ):
        assert expected[field] <= actual[field], field
    assert "same natural sun-kissed skin tone" in final_prompt
    assert "full natural D-cup bust" in final_prompt
    assert "photorealistic" in final_prompt


def test_provider_prompt_rendering_is_idempotent_for_preview_parity():
    canonical = "Standing topless beside the window, bare breasts and nipples visible"

    preview = enforce_premium_render_body_lock(canonical)
    submitted = enforce_premium_render_body_lock(preview)

    assert submitted == preview
    assert "FINAL REFERENCE BODY LOCK" in preview
    assert "TOPLESS RENDER LOCK" in preview


def test_editorial_direction_is_derived_and_reaches_provider_prompt(monkeypatch):
    concept = (
        "Standing quietly beside the rain-streaked window, looking away from the "
        "camera with reflective posture and an absorbed private mood"
    )
    editorial = {
        "emotional_tone": "quiet, intimate, and reflective",
        "facial_expression": "restrained expression with relaxed features",
        "eye_contact": "looking away rather than meeting the viewer",
        "body_language": "still, relaxed posture absorbed in the moment",
        "editorial_energy": "private cinematic editorial",
        "visual_storytelling": "an unobserved pause beside rain-streaked glass",
        "subject_awareness": "unaware of being photographed",
        "camera_engagement": "no direct engagement with the camera",
    }

    def fake_grok(instruction, _key):
        if "Return one JSON object" in instruction:
            import json
            return json.dumps(editorial)
        return (
            "1. Natural skin texture, restrained cinematic lighting, realistic "
            "anatomy, and shallow depth of field."
        )

    monkeypatch.setattr(
        "app.services.explicit_prompt_service.get_grok_api_key",
        lambda: "test-key",
    )
    monkeypatch.setattr(
        "app.services.explicit_prompt_service.generate_prompts_with_grok",
        fake_grok,
    )

    canonical = generate_explicit_prompts(concept, 1)[0]
    structured = extract_editorial_direction(canonical)
    provider = enforce_premium_render_body_lock(canonical)

    assert structured == editorial
    assert extract_editorial_direction(provider) == editorial
    assert semantic_fields(concept)["environment"] <= semantic_fields(provider)["environment"]
    assert provider.index("SCENE") < provider.index("EXPLICIT EDITORIAL GUIDANCE")
    assert provider.index("EXPLICIT EDITORIAL GUIDANCE") < provider.index("EDITORIAL DIRECTION")
    assert provider.index("EDITORIAL DIRECTION") < provider.index(EXPLICIT_EXPRESSION_SECTION)
    assert provider.index(EXPLICIT_EXPRESSION_SECTION) < provider.index("CREATOR IDENTITY")
    assert provider.index("EDITORIAL DIRECTION") < provider.index("CREATOR IDENTITY")
    assert provider.index("CREATOR IDENTITY") < provider.index("VISUAL QUALITY")
    assert provider.index("VISUAL QUALITY") < provider.index("PROVIDER OPTIMIZATION")
    assert "EXPLICIT EXPRESSION VARIATION" not in provider
    assert "FINAL REFERENCE BODY LOCK" in provider


def test_explicit_expression_profiles_share_premium_identity_and_are_tier_aware():
    softcore = ExplicitExpressionProfileService.build("softcore").render()
    hardcore = ExplicitExpressionProfileService.build("hardcore").render()

    for profile in (softcore, hardcore):
        assert "intimate" in profile
        assert "emotionally engaged" in profile
        assert "private PPV" in profile
        assert "half-lidded" in profile  # banned in limits/eye rules
        assert "no default grinning" in profile
        assert "tongue-out goofy mugging" in profile
        for mood in (
            "teasing",
            "naughty",
            "seductive",
            "sexually enticing",
            "appealing",
            "salacious",
        ):
            assert mood in profile
        assert "fully open" in profile
        assert "never droopy" in profile
        assert "bedroom eyes" not in profile

    assert "quietly confident" in softcore
    assert "intensely aroused" in hardcore
    assert "stronger wanting" in hardcore


def test_canonical_explicit_expression_profile_follows_editorial_and_preserves_scene(
    monkeypatch,
):
    concept = (
        "Hardcore couch scene, rear three-quarter camera angle, explicit pose, "
        "low blue evening light"
    )
    editorial = {
        "emotional_tone": "intense private mood",
        "facial_expression": "derived from the scene",
        "eye_contact": "toward the viewer",
        "body_language": "preserve explicit pose",
        "editorial_energy": "premium cinematic",
        "visual_storytelling": "private paid moment",
        "subject_awareness": "aware of the viewer",
        "camera_engagement": "direct",
    }

    def fake_grok(instruction, _key):
        if "Return one JSON object" in instruction:
            import json

            return json.dumps(editorial)
        return "1. Photorealistic treatment preserving the requested scene."

    monkeypatch.setattr(
        "app.services.explicit_prompt_service.get_grok_api_key",
        lambda: "test-key",
    )
    monkeypatch.setattr(
        "app.services.explicit_prompt_service.generate_prompts_with_grok",
        fake_grok,
    )

    prompt = generate_explicit_prompts(
        concept,
        1,
        original_source=concept,
        concept_tier="hardcore",
    )[0]

    assert f"SCENE\n{concept}." in prompt
    assert prompt.index("EDITORIAL DIRECTION") < prompt.index(EXPLICIT_EXPRESSION_SECTION)
    assert prompt.index(EXPLICIT_EXPRESSION_SECTION) < prompt.index("WARDROBE")
    assert "heightened intensity" in prompt
    assert "stronger wanting" in prompt
    assert "teasing, naughty, seductive, sexually enticing, appealing, and salacious" in prompt
    assert "half-lidded" in prompt
    assert "no default grinning" in prompt
    assert "rear three-quarter camera angle" in prompt
    assert "low blue evening light" in prompt


def test_provider_optimization_does_not_add_a_second_expression_profile():
    canonical = """SCENE
Explicit private scene.

EDITORIAL DIRECTION
Facial expression: scene-derived

EXPLICIT EXPRESSION PROFILE
Facial expression: serious and sensual

VISUAL QUALITY
Photorealistic."""

    provider = enforce_premium_render_body_lock(canonical)

    assert provider.count(EXPLICIT_EXPRESSION_SECTION) == 1
    assert "EXPLICIT EXPRESSION VARIATION" not in provider
    assert provider.index(EXPLICIT_EXPRESSION_SECTION) < provider.index(
        "PROVIDER OPTIMIZATION"
    )


def test_editorial_metadata_has_a_first_class_canonical_planning_layer(monkeypatch):
    from app.services.canonical_prompt_planner import (
        CanonicalPromptPlanner,
        CanonicalPromptPlanningRequest,
    )

    prompt = """SCENE
Window scene.

EXPLICIT EDITORIAL GUIDANCE
Private premium creator editorial language.

EDITORIAL DIRECTION
Emotional tone: reflective
Facial expression: restrained
Eye contact: looking away
Body language: relaxed
Editorial energy: quiet cinematic
Visual storytelling: private pause
Subject awareness: absorbed in the moment
Camera engagement: no direct engagement

WARDROBE
Preserve scene wardrobe.

CREATOR IDENTITY
Preserve reference identity.

VISUAL QUALITY
Photorealistic."""
    monkeypatch.setattr(
        "app.services.canonical_prompt_planner.generate_explicit_prompts",
        lambda **_kwargs: [prompt],
    )

    result = CanonicalPromptPlanner().plan(
        CanonicalPromptPlanningRequest(
            mode="explicit",
            creative_tags="window concept",
            prompt_count=1,
        )
    )

    editorial = result.metadata["editorial_directions"][0]
    assert set(editorial) == {
        "emotional_tone",
        "facial_expression",
        "eye_contact",
        "body_language",
        "editorial_energy",
        "visual_storytelling",
        "subject_awareness",
        "camera_engagement",
    }
    assert result.metadata["canonical_planning_order"] == (
        "scene",
        "explicit_editorial_guidance",
        "editorial_direction",
        "explicit_expression_profile",
        "wardrobe",
        "creator_identity",
        "visual_quality",
        "provider_optimization",
    )
    assert result.metadata["editorial_guidance"] == (
        ExplicitEditorialGuidance().metadata()
    )


def test_explicit_planner_selects_only_explicit_editorial_guidance():
    guidance = ExplicitEditorialGuidance()

    assert explicit_prompt_service.EXPLICIT_EDITORIAL_GUIDANCE == guidance
    assert not hasattr(explicit_prompt_service, "editorial_quality_guidance")
    assert guidance.metadata()["scope"] == "explicit_only"


def test_social_editorial_guidance_remains_independent():
    from app.services.canonical_planner_enhancement_service import (
        editorial_quality_guidance,
    )

    social_guidance = editorial_quality_guidance(workflow="canonical_planner")
    explicit_guidance = ExplicitEditorialGuidance()

    assert editorial_quality_guidance.__module__ == (
        "app.services.editorial_quality_guidance"
    )
    assert explicit_guidance.system_id != "editorial_quality_guidance"
    assert social_guidance


def test_explicit_inspiration_api_request_contract_is_unchanged():
    current = ExplicitInspirationRequest(countPerTier=5)
    legacy = ExplicitInspirationRequest(conceptCount=5)

    assert current.countPerTier == 5
    assert current.conceptCount is None
    assert legacy.countPerTier == 5
    assert legacy.conceptCount == 5

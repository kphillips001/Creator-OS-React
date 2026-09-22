from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.generation_engine import GenerationRequest
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.content_studio_background_executor import ContentStudioBackgroundExecutor
from app.services.content_studio_generation_service import ContentStudioGenerationService
from app.services.explicit_prompt_service import (
    BODY_AND_FRAMING_LOCK_RULES,
    EXPRESSION_PERSONALITY_RULES,
    HAIR_CONTINUITY_RULES,
    IDENTITY_LOCK_RULES,
    NUDITY_GROOMING_RULES,
    TOPLESS_VISIBILITY_RULES,
)
from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService
from app.test_canonical_creator_identity_phase1 import (
    CapturingEngine, EXPECTED_HASH, FrozenDirector, FrozenReferences, contract,
)


EXPECTED_FINGERPRINT = "canonical_identity_v1:295d4a12368e11d9a0a423336135ae53db133594ec870e56847ea59366a0e83f"


def queue(origin, *, explicit_input=None, creative_tags="scene", frozen=None):
    references = FrozenReferences()
    director = FrozenDirector()
    engine = CapturingEngine()
    service = ContentStudioGenerationService(
        creative_director=director, generation_engine=engine,
        generation_library=SimpleNamespace(), reference_service=references,
    )
    plan, _job = service.queue(
        creator_profile={"id": 2}, creative_tags=creative_tags,
        creative_mode="explicit" if origin != "recreate_with_ava" else "premium_teaser",
        prompt_count=1, provider_id="seedream_5_0_pro",
        prompt_batch=("provider prompt",), origin=origin,
        explicit_input=explicit_input, canonical_identity_contract=frozen,
    )
    return references, director, engine, plan


@pytest.mark.parametrize("origin,explicit_input", [
    ("explicit_tags", {"source_type": "operator_tags", "concept_tier": None}),
    ("explicit_inspiration", {"source_type": "selected_inspiration_concept", "concept_tier": "softcore"}),
    ("explicit_inspiration", {"source_type": "selected_inspiration_concept", "concept_tier": "hardcore"}),
])
def test_explicit_modes_use_same_frozen_canonical_identity(origin, explicit_input):
    references, director, engine, _plan = queue(origin, explicit_input=explicit_input)
    identity = engine.contracts[0]
    assert references.calls == 1
    assert director.contracts == [identity]
    assert identity.creator_profile_id == 2
    assert identity.canonical_asset_id == 93
    assert identity.canonical_content_sha256 == EXPECTED_HASH
    assert identity.identity_prompt_policy_id == "canonical_ava_identity"
    assert identity.identity_prompt_policy_version == "v1"
    assert identity.identity_version == EXPECTED_FINGERPRINT
    assert identity.reference_role == "CANONICAL_IDENTITY"


def test_explicit_identity_rules_consume_policy_but_keep_explicit_behavior_local():
    source = Path("app/services/explicit_prompt_service.py").read_text(encoding="utf-8")
    assert "canonical_creator_identity_policy" in source
    assert "Every generated prompt must preserve the reference woman exactly" not in source
    assert "canonical creator exactly" in IDENTITY_LOCK_RULES
    assert "long dark loose hair" in IDENTITY_LOCK_RULES
    assert "natural D-cup" in BODY_AND_FRAMING_LOCK_RULES
    assert "If wet hair is requested" in HAIR_CONTINUITY_RULES
    assert "nipples must be visible" in TOPLESS_VISIBILITY_RULES
    assert "no pubic hair" in NUDITY_GROOMING_RULES
    assert "sole facial-expression authority" in EXPRESSION_PERSONALITY_RULES


def recreate_request(*, authoritative_expression=True):
    identity = contract()
    return GenerationRequest(
        request_id="recreate", creator_profile_id=2, prompt_plan_id="plan",
        prompt_text="Expression: quiet thoughtful gaze, hotel mirror scene",
        reference_asset_id=93, reference_asset_path=identity.canonical_local_path,
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        canonical_identity=identity,
        metadata={
            "workflow_origin": "recreate_with_ava", "render_policy": "CONTENT_SPICY",
            "reference_image_url": identity.canonical_provider_reference,
            "recreate_source_expression_authoritative": authoritative_expression,
            "creative_inspiration_provenance": {
                "reference_role": "CREATIVE_INSPIRATION", "transport": "ANALYSIS_ONLY",
                "identity_transfer_prohibited": True,
            },
        },
    )


def test_recreate_uses_canonical_provider_image_and_analysis_only_inspiration():
    references, _director, engine, plan = queue(
        "recreate_with_ava", creative_tags="Expression: quiet thoughtful gaze",
    )
    assert references.calls == 1
    identity = engine.contracts[0]
    assert identity.canonical_asset_id == 93
    assert identity.identity_version == EXPECTED_FINGERPRINT
    provenance = plan.prompt_metadata["creative_inspiration_provenance"]
    assert provenance == {
        "reference_role": "CREATIVE_INSPIRATION",
        "transport": "ANALYSIS_ONLY",
        "identity_transfer_prohibited": True,
    }
    payload = Seedream50ProProvider(api_key="not-used").build_payload(recreate_request())
    assert payload["images"] == [identity.canonical_provider_reference]
    assert len(payload["images"]) == 1


def test_recreate_authoritative_expression_does_not_receive_random_expression_directive():
    prompt = Seedream50ProProvider(api_key="not-used").build_payload(
        recreate_request(authoritative_expression=True)
    )["prompt"]
    assert "quiet thoughtful gaze" in prompt
    assert "INSPIRE ME NATURAL EXPRESSION NUANCE" not in prompt
    assert "EXPLICIT EXPRESSION VARIATION" not in prompt
    assert "CANONICAL AVA FACIAL NATURALISM" in prompt


def test_prompt_workshop_explicit_preserves_canonical_explicit_expression_semantics():
    identity = contract()
    request = GenerationRequest(
        request_id="workshop-explicit", creator_profile_id=2, prompt_plan_id="plan",
        prompt_text=(
            "Ava in an intentionally explicit private scene.\n\n"
            "EXPLICIT EXPRESSION PROFILE\nFlirty intimate eye contact with naturally parted lips."
        ),
        reference_asset_id=93, reference_asset_path=identity.canonical_local_path,
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        canonical_identity=identity,
        metadata={
            "workflow_origin": "prompt_workshop_explicit",
            "render_policy": "CONTENT_EXPLICIT",
            "reference_image_url": identity.canonical_provider_reference,
        },
    )
    provider = Seedream50ProProvider(api_key="not-used")
    payload = provider.build_payload(request)
    prompt = payload["prompt"]
    assert "Flirty intimate eye contact with naturally parted lips." in prompt
    assert "EXPLICIT EXPRESSION PROFILE" in prompt
    assert "INSPIRE ME NATURAL EXPRESSION NUANCE" not in prompt
    assert "EXPLICIT EXPRESSION VARIATION" not in prompt
    assert "CANONICAL AVA FACIAL NATURALISM" in prompt
    assert payload["images"] == [identity.canonical_provider_reference]
    assert identity.creator_profile_id == 2
    assert identity.canonical_asset_id == 93
    assert identity.canonical_content_sha256 == EXPECTED_HASH
    assert identity.identity_prompt_policy_id == "canonical_ava_identity"
    assert identity.identity_prompt_policy_version == "v1"
    assert identity.identity_version == EXPECTED_FINGERPRINT
    assert identity.reference_role == "CANONICAL_IDENTITY"
    assert provider.provider_id == "seedream_5_0_pro"
    assert provider.capabilities.metadata["model"] == "seedream-v5.0-pro/edit"


def test_recreate_recipe_records_identity_and_creative_inspiration_roles():
    repository = SimpleNamespace(create=lambda recipe: recipe)
    request = recreate_request()
    provider = Seedream50ProProvider(api_key="not-used")
    recipe = GenerationRecipeCaptureService(repository).capture(
        request=request, provider=provider, final_payload=provider.build_payload(request),
    )
    assert recipe.normalized_settings["canonical_identity"]["identity_version"] == EXPECTED_FINGERPRINT
    assert recipe.normalized_settings["canonical_identity"]["reference_roles"] == ["CANONICAL_IDENTITY"]
    assert recipe.normalized_settings["creative_inspiration_provenance"]["reference_role"] == "CREATIVE_INSPIRATION"
    assert recipe.references[0].role == "CANONICAL_IDENTITY"
    assert len(recipe.references) == 1


def test_frozen_retry_contract_bypasses_new_identity_resolution():
    references, _director, engine, _plan = queue(
        "explicit_inspiration", frozen=contract().to_dict(),
        explicit_input={"concept_tier": "hardcore"},
    )
    assert references.calls == 0
    assert engine.contracts == [contract()]


def test_background_observer_persists_frozen_contract_into_retry_request():
    updates = []
    operation = SimpleNamespace(
        operation_id="operation", metadata={"request": {"origin": "explicit_inspiration"}},
    )
    repository = SimpleNamespace(renew_lease=lambda *_args, **_kwargs: None)
    operations = SimpleNamespace(
        repository=repository,
        progress=lambda *_args, **kwargs: updates.append(kwargs),
    )
    observe = ContentStudioBackgroundExecutor.operation_observer(
        operation, operations, worker_id="worker", total=1,
    )
    observe({
        "status": "queued", "canonicalIdentityContract": contract().to_dict(),
        "jobId": "job", "message": "queued",
    })
    persisted = updates[0]["metadata"]["request"]["canonicalIdentityContract"]
    assert persisted["identity_version"] == EXPECTED_FINGERPRINT
    assert persisted["canonical_asset_id"] == 93

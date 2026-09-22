from dataclasses import replace
from pathlib import Path

import pytest

from app.models.canonical_creator_identity import canonical_identity_version
from app.models.generation_engine import GenerationRequest
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.prompts.seedream_premium_prompt_builder import PREMIUM_INTIMACY_PROMPT_RULES
from app.services.canonical_creator_identity_policy import (
    CANONICAL_IDENTITY_POLICY_ID,
    CANONICAL_IDENTITY_POLICY_VERSION,
    canonical_creator_identity_policy,
)
from app.services.canonical_facial_naturalism import CANONICAL_FACIAL_NATURALISM
from app.services.seedream_premium_render_locks import PREMIUM_RENDER_BODY_LOCK
from app.test_canonical_creator_identity_phase1 import EXPECTED_HASH, contract


EXPECTED_PHASE1_FINGERPRINT = "canonical_identity_v1:ee44079959a238f64238996f5acfef92b85db32e01ec1ae07557c2faae2239e4"
EXPECTED_PHASE2A_FINGERPRINT = "canonical_identity_v1:295d4a12368e11d9a0a423336135ae53db133594ec870e56847ea59366a0e83f"


def request(origin):
    identity = contract()
    return GenerationRequest(
        request_id="request", creator_profile_id=2, prompt_plan_id="plan",
        prompt_text="A neutral portrait", reference_asset_id=93,
        reference_asset_path=identity.canonical_local_path,
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        canonical_identity=identity,
        metadata={
            "workflow_origin": origin, "render_policy": "CONTENT_SPICY",
            "reference_image_url": identity.canonical_provider_reference,
        },
    )


def test_one_creator_aware_versioned_policy_owns_stable_ava_facts():
    policy = canonical_creator_identity_policy(2)
    assert policy.policy_id == "canonical_ava_identity" == CANONICAL_IDENTITY_POLICY_ID
    assert policy.policy_version == "v1" == CANONICAL_IDENTITY_POLICY_VERSION
    assert "long dark loose hair" in policy.appearance_continuity
    assert "natural D-cup" in policy.bust_continuity
    assert "feminine hourglass" in policy.body_continuity
    assert "sun-kissed" in policy.skin_continuity
    assert "exact facial identity" in policy.facial_continuity
    with pytest.raises(ValueError, match="No canonical textual identity policy"):
        canonical_creator_identity_policy(3)


def test_phase2a_policy_rotates_fingerprint_without_changing_asset_identity():
    identity = contract()
    assert identity.creator_profile_id == 2
    assert identity.canonical_asset_id == 93
    assert identity.canonical_content_sha256 == EXPECTED_HASH
    assert identity.identity_version == EXPECTED_PHASE2A_FINGERPRINT
    assert identity.identity_version != EXPECTED_PHASE1_FINGERPRINT
    assert identity.identity_version == canonical_identity_version(
        creator_profile_id=2, canonical_asset_id=93,
        canonical_content_sha256=EXPECTED_HASH,
        identity_prompt_policy_id=CANONICAL_IDENTITY_POLICY_ID,
        identity_prompt_policy_version=CANONICAL_IDENTITY_POLICY_VERSION,
    )


def test_normal_renderers_consume_policy_without_provider_owned_identity_copy():
    policy = canonical_creator_identity_policy(2)
    assert policy.premium_render_identity_opening in PREMIUM_RENDER_BODY_LOCK
    assert policy.premium_render_body_identity in PREMIUM_RENDER_BODY_LOCK
    assert policy.facial_naturalism_continuity in CANONICAL_FACIAL_NATURALISM
    assert policy.planner_identity_summary in PREMIUM_INTIMACY_PROMPT_RULES

    provider_source = Path("app/providers/generation/base.py").read_text(encoding="utf-8")
    lock_source = Path("app/services/seedream_premium_render_locks.py").read_text(encoding="utf-8")
    facial_source = Path("app/services/canonical_facial_naturalism.py").read_text(encoding="utf-8")
    planner_source = Path("app/prompts/seedream_premium_prompt_builder.py").read_text(encoding="utf-8")
    assert "CANONICAL AVA FACE + BODY IDENTITY" not in provider_source
    assert policy.appearance_continuity not in provider_source
    assert policy.appearance_continuity not in lock_source
    assert policy.facial_naturalism_continuity not in facial_source
    assert "canonical_creator_identity_policy" in planner_source


def test_inspire_and_ordinary_creative_studio_share_natural_expression_safeguards():
    provider = Seedream50ProProvider(api_key="not-used")
    inspire = provider.build_payload(request("autonomous_inspiration"))["prompt"]
    assert "INSPIRE ME NATURAL EXPRESSION NUANCE" in inspire
    assert "CANONICAL AVA FACIAL NATURALISM" in inspire
    assert PREMIUM_RENDER_BODY_LOCK in inspire
    for origin in ("manual_creative_concept", "canonical_planner"):
        creative = provider.build_payload(request(origin))["prompt"]
        assert "INSPIRE ME NATURAL EXPRESSION NUANCE" in creative
        assert "EXPLICIT EXPRESSION VARIATION" not in creative
        assert "CANONICAL AVA FACIAL NATURALISM" in creative
        assert PREMIUM_RENDER_BODY_LOCK in creative
    assert PREMIUM_RENDER_BODY_LOCK in creative


@pytest.mark.parametrize("origin", [
    "autonomous_inspiration", "manual_creative_concept", "canonical_planner",
])
def test_phase2a_request_keeps_provider_model_and_single_identity_image(origin):
    provider = Seedream50ProProvider(api_key="not-used")
    payload = provider.build_payload(request(origin))
    assert provider.provider_id == "seedream_5_0_pro"
    assert provider.capabilities.metadata["model"] == "seedream-v5.0-pro/edit"
    assert len(payload["images"]) == 1
    assert request(origin).canonical_identity.reference_role == "CANONICAL_IDENTITY"


@pytest.mark.parametrize("origin", [
    "manual_creative_concept", "canonical_planner", "manual_prompt",
    "prompt_workshop_premium",
])
def test_creative_studio_expression_alignment_preserves_full_identity_contract(origin):
    generation_request = request(origin)
    identity = generation_request.canonical_identity
    payload = Seedream50ProProvider(api_key="not-used").build_payload(generation_request)
    assert identity.creator_profile_id == 2
    assert identity.canonical_asset_id == 93
    assert identity.canonical_content_sha256 == EXPECTED_HASH
    assert identity.identity_prompt_policy_id == "canonical_ava_identity"
    assert identity.identity_prompt_policy_version == "v1"
    assert identity.identity_version == EXPECTED_PHASE2A_FINGERPRINT
    assert identity.reference_role == "CANONICAL_IDENTITY"
    assert generation_request.provider_id == "seedream_5_0_pro"
    assert Seedream50ProProvider.capabilities.metadata["model"] == "seedream-v5.0-pro/edit"
    assert payload["images"] == [identity.canonical_provider_reference]

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.canonical_creator_identity import (
    CanonicalCreatorIdentityContract,
    GenerationReferenceRole,
    canonical_identity_version,
)
from app.models.creative_director import PromptPlan
from app.models.generation_engine import GenerationRequest
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.content_studio_generation_service import ContentStudioGenerationService
from app.services.canonical_creator_identity_policy import (
    CANONICAL_IDENTITY_POLICY_ID,
    CANONICAL_IDENTITY_POLICY_VERSION,
)
from app.services.generation_engine_service import GenerationEngineService
from app.services.generation_recipe_capture_service import GenerationRecipeCaptureService
from app.services.reference_library_service import ReferenceLibraryService


EXPECTED_HASH = "6D14784CD9D98C72591C057058219AF1337B9328DE6B63BB692FA4A06A3432B4"


class Hosted:
    def __init__(self, checksum=EXPECTED_HASH, url="https://media.example/ava.png"):
        self.value = checksum
        self.url = url

    def checksum(self, _path):
        return self.value

    def cached_url(self, **_kwargs):
        return self.url


def projection(path, *, creator=2, asset=93, active=True, canonical=True, protected=True):
    return SimpleNamespace(
        asset_id=asset, creator_profile_id=creator, is_active=active,
        asset=SimpleNamespace(original_path=str(path)),
        metadata={
            "canonical": canonical, "protected": protected,
            "canonical_sha256": EXPECTED_HASH,
        },
    )


def resolver(tmp_path, reference, hosted=None):
    service = ReferenceLibraryService.__new__(ReferenceLibraryService)
    service.hosted_references = hosted or Hosted()
    service.get_active_canonical_reference = lambda **_kwargs: reference
    return service


def resolve(service):
    return service.resolve_canonical_identity_contract(
        creator_profile={"id": 2, "display_name": "Ava Blackthorne"},
        provider_id="seedream_5_0_pro",
        identity_prompt_policy_id=CANONICAL_IDENTITY_POLICY_ID,
        identity_prompt_policy_version=CANONICAL_IDENTITY_POLICY_VERSION,
    )


def test_audited_canonical_identity_resolves_as_immutable_contract(tmp_path):
    source = tmp_path / "93.png"
    source.write_bytes(b"fixture")
    contract = resolve(resolver(tmp_path, projection(source)))
    assert contract.creator_profile_id == 2
    assert contract.canonical_asset_id == 93
    assert contract.canonical_content_sha256 == EXPECTED_HASH
    assert contract.reference_role == GenerationReferenceRole.CANONICAL_IDENTITY.value
    assert contract.canonical_provider_reference == "https://media.example/ava.png"


@pytest.mark.parametrize("reference", [None, "wrong_owner", "unprotected"])
def test_canonical_identity_fails_closed(tmp_path, reference):
    source = tmp_path / "93.png"
    source.write_bytes(b"fixture")
    value = {
        None: None,
        "wrong_owner": projection(source, creator=9),
        "unprotected": projection(source, protected=False),
    }[reference]
    with pytest.raises(ValueError):
        resolve(resolver(tmp_path, value))


def test_canonical_identity_hash_mismatch_fails_closed(tmp_path):
    source = tmp_path / "93.png"
    source.write_bytes(b"fixture")
    with pytest.raises(ValueError, match="SHA-256"):
        resolve(resolver(tmp_path, projection(source), Hosted(checksum="0" * 64)))


def test_identity_fingerprint_is_stable_and_excludes_hosted_url():
    values = dict(
        creator_profile_id=2, canonical_asset_id=93,
        canonical_content_sha256=EXPECTED_HASH,
        identity_prompt_policy_id="policy", identity_prompt_policy_version="1",
    )
    baseline = canonical_identity_version(**values)
    assert baseline == canonical_identity_version(**values)
    assert baseline != canonical_identity_version(**{**values, "canonical_asset_id": 94})
    assert baseline != canonical_identity_version(**{**values, "canonical_content_sha256": "A" * 64})
    assert baseline != canonical_identity_version(**{**values, "identity_prompt_policy_version": "2"})
    first = CanonicalCreatorIdentityContract(
        **values, creator_identity_key="creator_profile:2", canonical_local_path="93.png",
        canonical_provider_reference="https://one.example/93", identity_version=baseline,
        resolved_at="now", reference_role="CANONICAL_IDENTITY",
    )
    second = CanonicalCreatorIdentityContract(
        **{**first.to_dict(), "canonical_provider_reference": "https://two.example/93"}
    )
    assert first.identity_version == second.identity_version


def contract():
    version = canonical_identity_version(
        creator_profile_id=2, canonical_asset_id=93,
        canonical_content_sha256=EXPECTED_HASH,
        identity_prompt_policy_id=CANONICAL_IDENTITY_POLICY_ID,
        identity_prompt_policy_version=CANONICAL_IDENTITY_POLICY_VERSION,
    )
    return CanonicalCreatorIdentityContract(
        creator_profile_id=2, creator_identity_key="creator_profile:2",
        canonical_asset_id=93, canonical_content_sha256=EXPECTED_HASH,
        canonical_local_path="D:/Ava_CMS/vault/originals/images/93.png",
        canonical_provider_reference="https://media.example/93.png",
        identity_version=version, resolved_at="2026-09-17T00:00:00",
        reference_role="CANONICAL_IDENTITY",
        identity_prompt_policy_id=CANONICAL_IDENTITY_POLICY_ID,
        identity_prompt_policy_version=CANONICAL_IDENTITY_POLICY_VERSION,
    )


def plan(mode="premium_teaser"):
    return PromptPlan(
        plan_id="plan", session_id="session", creator_profile_id=2,
        prompt_text="A neutral portrait", creative_mode=mode, creative_tags=("neutral",),
        reference_asset_id=93, reference_asset_path=contract().canonical_local_path,
        creative_rationale="fixture", prompt_metadata={"prompt_variations": ("A neutral portrait",)},
    )


class FrozenReferences:
    def __init__(self):
        self.calls = 0

    def resolve_canonical_identity_contract(self, **_kwargs):
        self.calls += 1
        return contract()


class FrozenDirector:
    def __init__(self):
        self.contracts = []

    def create_provider_prompt_plan(self, **kwargs):
        self.contracts.append(kwargs["canonical_identity"])
        value = plan(kwargs["creative_mode"])
        return replace(
            value,
            prompt_metadata={**dict(value.prompt_metadata), **dict(kwargs.get("metadata") or {})},
        )

    create_prompt_plan = create_provider_prompt_plan


class CapturingEngine:
    def __init__(self):
        self.contracts = []

    def queue_prompt_plan(self, **kwargs):
        self.contracts.append(kwargs["canonical_identity"])
        return SimpleNamespace(job_id="job", request=SimpleNamespace())


@pytest.mark.parametrize("origin,mode", [
    ("autonomous_inspiration", "premium_teaser"),
    ("canonical_planner", "premium_teaser"),
    ("canonical_planner", "spicy"),
    ("canonical_planner", "story_sequence"),
    ("manual_prompt", "premium_teaser"),
    ("prompt_workshop_premium", "premium_teaser"),
    ("prompt_workshop_explicit", "explicit"),
])
def test_normal_content_studio_resolves_once_and_all_modes_share_identity(origin, mode):
    references = FrozenReferences()
    director = FrozenDirector()
    engine = CapturingEngine()
    service = ContentStudioGenerationService(
        creative_director=director, generation_engine=engine,
        generation_library=SimpleNamespace(), reference_service=references,
    )
    planned, _job = service.queue(
        creator_profile={"id": 2}, creative_tags="neutral portrait",
        creative_mode=mode, prompt_count=1, provider_id="seedream_5_0_pro",
        prompt_batch=("A neutral portrait",), origin=origin,
    )
    assert references.calls == 1
    assert director.contracts == [contract()]
    assert engine.contracts == [contract()]
    assert planned.reference_asset_id == 93
    assert engine.contracts[0].identity_version == contract().identity_version


@pytest.mark.parametrize("origin,mode", [
    ("explicit_inspiration", "explicit"),
    ("recreate_with_ava", "premium_teaser"),
])
def test_phase2b_migrates_explicit_and_recreate(origin, mode):
    references = FrozenReferences()
    director = FrozenDirector()
    engine = CapturingEngine()
    service = ContentStudioGenerationService(
        creative_director=director, generation_engine=engine,
        generation_library=SimpleNamespace(), reference_service=references,
    )
    service.queue(
        creator_profile={"id": 2}, creative_tags="existing behavior",
        creative_mode=mode, prompt_count=1, provider_id="seedream_5_0_pro",
        prompt_batch=("existing prompt",), origin=origin,
    )
    assert references.calls == 1
    assert director.contracts == [contract()]
    assert engine.contracts == [contract()]


def test_generation_engine_uses_frozen_contract_without_second_lookup(tmp_path):
    class References:
        def get_active_canonical_reference(self, **_kwargs):
            raise AssertionError("active canonical identity was resolved twice")
    engine = GenerationEngineService(
        storage_dir=tmp_path, reference_library_service=References(),
        hosted_reference_service=Hosted(), providers={},
    )
    request = engine.create_request(
        creator_profile={"id": 2}, prompt_plan=plan(),
        provider_id="seedream_5_0_pro", canonical_identity=contract(),
        metadata={"workflow_type": "premium", "creative_mode": "premium_teaser"},
    )
    assert request.reference_asset_id == 93
    assert request.reference_asset_path == contract().canonical_local_path
    assert request.metadata["reference_image_url"] == contract().canonical_provider_reference


def test_seedream_baseline_has_one_canonical_image_and_preserves_autonomous_render_path():
    identity = contract()
    request = GenerationRequest(
        request_id="request", creator_profile_id=2, prompt_plan_id="plan",
        prompt_text="A neutral portrait", reference_asset_id=93,
        reference_asset_path=identity.canonical_local_path,
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        canonical_identity=identity,
        metadata={
            "workflow_origin": "autonomous_inspiration", "render_policy": "CONTENT_SPICY",
            "reference_image_url": identity.canonical_provider_reference,
        },
    )
    provider = Seedream50ProProvider(api_key="not-used")
    payload = provider.build_payload(request)
    assert provider.capabilities.metadata["model"] == "seedream-v5.0-pro/edit"
    assert payload["images"] == [identity.canonical_provider_reference]
    assert len(payload["images"]) == 1
    assert "FINAL REFERENCE BODY LOCK - NON-NEGOTIABLE" in payload["prompt"]
    assert "INSPIRE ME NATURAL EXPRESSION NUANCE" in payload["prompt"]


def test_recipe_captures_phase1_identity_provenance():
    captured = []
    repository = SimpleNamespace(create=lambda recipe: captured.append(recipe) or recipe)
    identity = contract()
    request = GenerationRequest(
        request_id="request", creator_profile_id=2, prompt_plan_id="plan", prompt_text="prompt",
        reference_asset_id=93, reference_asset_path=identity.canonical_local_path,
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image",
        canonical_identity=identity, metadata={"workflow_type": "premium", "render_policy": "CONTENT_SPICY"},
    )
    provider = Seedream50ProProvider(api_key="not-used")
    recipe = GenerationRecipeCaptureService(repository).capture(
        request=request, provider=provider,
        final_payload={"prompt": "prompt", "images": [identity.canonical_provider_reference], "output_format": "png"},
    )
    provenance = recipe.normalized_settings["canonical_identity"]
    assert provenance["creator_profile_id"] == 2
    assert provenance["canonical_asset_id"] == 93
    assert provenance["canonical_content_sha256"] == EXPECTED_HASH
    assert provenance["identity_version"] == identity.identity_version
    assert provenance["reference_roles"] == ["CANONICAL_IDENTITY"]
    assert recipe.references[0].role == "CANONICAL_IDENTITY"
    assert recipe.references[0].content_sha256 == EXPECTED_HASH


def test_legacy_request_without_contract_still_deserializes(tmp_path):
    value = {
        "job_id": "legacy", "request": {
            "request_id": "request", "creator_profile_id": 2, "prompt_plan_id": "plan",
            "prompt_text": "prompt", "reference_asset_id": 93,
            "reference_asset_path": "93.png", "provider_id": "seedream_5_0_pro",
            "generation_type": "image_to_image", "media_type": "image", "metadata": {},
        },
    }
    loaded = GenerationEngineService._job_from_dict(value)
    assert loaded.request.canonical_identity is None
    assert loaded.request.reference_asset_id == 93

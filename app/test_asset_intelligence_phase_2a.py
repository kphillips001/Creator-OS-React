from pathlib import Path

from app.models.asset_intelligence import AssetIntelligenceProfile, AssetIntelligenceStatus
from app.models.asset_intelligence_execution import AssetIntelligenceProviderRequest
from app.models.asset_intelligence_execution import AssetIntelligenceProviderPolicy
from app.services.asset_intelligence_provider_adapters import (
    GptVisionAssetIntelligenceAdapter,
    GrokVisionAssetIntelligenceAdapter,
    NudeNetAssetIntelligenceAdapter,
)
from app.services.asset_registration_service import AssetRegistrationService
from app.services.asset_intelligence_orchestrator import AssetIntelligenceOrchestrator
from app.services.asset_intelligence_service import AssetIntelligenceService
from app.test_asset_intelligence_orchestrator import FakeRunRepository, RunAwareIntelligenceRepository
from app.test_asset_registration_service import (
    FakeAssetIntelligenceService,
    FakeAssetRepository,
    FakeGenerationLibrary,
    generated_record,
)


def request(path):
    return AssetIntelligenceProviderRequest(
        run_id="run", asset_id=1, creator_profile_id=2, media_type="image",
        managed_media_path=str(path), original_filename=path.name,
        schema_version="v1",
    )


def test_existing_provider_adapters_normalize_their_owned_fields(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    gpt = GptVisionAssetIntelligenceAdapter(runner=lambda _: {
        "short_safe_summary": "Description", "suggested_tags": ["portrait"],
        "detected_themes": ["studio"], "classification": "TEASE", "confidence": .8,
        "reasoning": "must remain raw",
    }).analyze(request(image))
    grok = GrokVisionAssetIntelligenceAdapter(runner=lambda _: {
        "title": "Quiet Studio Confidence",
        "short_description": "Grok description", "tags": ["confident"],
        "themes": ["editorial"], "safety_classification": "SAFE",
        "quality_score": .9, "keywords": ["portrait", "studio"],
        "private": "raw only",
    }).analyze(request(image))
    nude = NudeNetAssetIntelligenceAdapter(runner=lambda _: [
        {"class": "FEMALE_BREAST_EXPOSED", "score": .99},
    ]).analyze(request(image))

    vision_fields = {"short_description", "tags", "themes", "safety_classification", "quality_score", "keywords"}
    semantic_fields = vision_fields | {"title", "content_summary", "search_phrases"}
    assert set(gpt.normalized_fields) == vision_fields
    assert set(grok.normalized_fields) == semantic_fields
    assert set(nude.normalized_fields) <= vision_fields
    assert nude.normalized_fields["safety_classification"] == "NUDITY"
    assert "reasoning" not in gpt.normalized_fields
    assert "private" not in grok.normalized_fields
    assert grok.normalized_fields["title"] == "Quiet Studio Confidence"


def test_three_fake_providers_build_one_ready_unified_profile(tmp_path):
    image = tmp_path / "image.png"
    image.write_bytes(b"image")
    adapters = {
        "gpt-vision": GptVisionAssetIntelligenceAdapter(runner=lambda _: {
            "short_safe_summary": "Unified description", "suggested_tags": ["portrait"],
            "detected_themes": ["studio"], "classification": "TEASE", "confidence": .8,
        }),
        "grok-vision": GrokVisionAssetIntelligenceAdapter(runner=lambda _: {
            "title": "Quiet Studio Confidence",
            "short_description": "Unified description", "tags": ["portrait", "confident"],
            "themes": ["studio"], "safety_classification": "SAFE",
            "quality_score": .95, "keywords": ["portrait", "studio"],
        }),
        "nudenet": NudeNetAssetIntelligenceAdapter(runner=lambda _: []),
    }
    profiles = RunAwareIntelligenceRepository()
    intelligence = AssetIntelligenceService(repository=profiles)
    orchestrator = AssetIntelligenceOrchestrator(
        run_repository=FakeRunRepository(), intelligence_service=intelligence, adapters=adapters,
    )

    run = orchestrator.execute_analysis(
        asset_id=1, creator_profile_id=2, media_type="image",
        managed_media_path=str(image), original_filename=image.name,
        policy=AssetIntelligenceProviderPolicy(required_providers=tuple(adapters)),
    )
    profile = intelligence.get_profile(1)

    assert run.status.value == "READY"
    assert len(profiles.profiles) == 1
    assert profile.analysis_status == AssetIntelligenceStatus.READY
    assert profile.short_description == "Unified description"
    assert profile.title == "Quiet Studio Confidence"
    assert profile.tags
    assert profile.themes == ("studio",)
    assert profile.safety_classification == "SAFE"
    assert profile.quality_score == .95
    assert profile.keywords == ("portrait", "studio")
    assert len(profiles.results) == 3


class FakeAnalysis:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def analyze(self, *, asset_id, creator_profile_id, progress):
        self.calls.append((asset_id, creator_profile_id))
        for label in ("GPT Vision", "Grok Vision", "NudeNet", "Building Asset Intelligence"):
            progress(label)
        if self.fail:
            raise RuntimeError("synthetic provider failure")
        return object()


def test_registration_hides_asset_until_synchronous_analysis_completes(tmp_path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"image")
    inserted, statuses, progress = [], [], []
    generation = FakeGenerationLibrary()
    analysis = FakeAnalysis()
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(), generation_library_service=generation,
        asset_intelligence_service=FakeAssetIntelligenceService(),
        asset_analysis_service=analysis,
        content_item_inserter=lambda payload: inserted.append(payload) or 81,
        content_item_updater=lambda asset_id, fields: statuses.append((asset_id, fields["status"])),
    )

    result = service.register_generated_image(
        generated_record(source), creator_profile_id=2, progress=progress.append,
    )

    assert result.success
    assert inserted[0]["status"] == "analyzing"
    assert statuses == [(81, "approved")]
    assert generation.links == [("generated-image-1", 81)]
    assert progress == ["Registering Asset", "GPT Vision", "Grok Vision", "NudeNet", "Building Asset Intelligence", "Completed"]


def test_failed_analysis_never_exposes_or_links_asset(tmp_path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"image")
    statuses = []
    generation = FakeGenerationLibrary()
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(), generation_library_service=generation,
        asset_intelligence_service=FakeAssetIntelligenceService(),
        asset_analysis_service=FakeAnalysis(fail=True),
        content_item_inserter=lambda payload: 82,
        content_item_updater=lambda asset_id, fields: statuses.append(fields["status"]),
    )

    result = service.register_generated_image(
        generated_record(source), creator_profile_id=2, progress=lambda _: None,
    )

    assert not result.success
    assert result.asset_id == 82
    assert statuses == ["analysis_failed"]
    assert generation.links == []


def test_intelligence_ui_does_not_render_raw_provider_payloads():
    source = Path("app/dashboard/pages/asset_library.py").read_text(encoding="utf-8")
    intelligence = source[source.index("def _render_intelligence"):source.index("def _render_operations_details")]
    assert "gpt_vision_result" not in intelligence
    assert "nudenet_result" not in intelligence
    for label in ("Description", "Tags", "Themes", "Safety", "Quality"):
        assert label in intelligence

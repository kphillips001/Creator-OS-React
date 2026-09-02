from pathlib import Path

from app.models.generation_library import GeneratedImageRecord
from app.services.asset_registration_service import AssetRegistrationService


class FakeAssetRepository:
    def __init__(self):
        self.existing = None

    def get_by_generation_image_id(self, _image_id):
        return self.existing


class FakeGenerationLibrary:
    def __init__(self):
        self.links = []

    def mark_registered(self, image_id, asset_id):
        self.links.append((image_id, asset_id))


class FakeAssetIntelligenceService:
    def __init__(self):
        self.pending = []

    def initialize_pending(self, *, asset_id, creator_profile_id):
        self.pending.append((asset_id, creator_profile_id))


def generated_record(path: Path, *, imported_asset_id=None):
    return GeneratedImageRecord(
        image_id="generated-image-1",
        generation_job_id="job-1",
        generation_request_id="request-1",
        generation_result_id="result-1",
        output_reference=str(path),
        creator_profile_id=2,
        provider_id="provider",
        prompt_plan_id="plan-1",
        prompt_text="prompt",
        creative_mode=None,
        reference_asset_id=None,
        imported_asset_id=imported_asset_id,
    )


def test_register_generated_image_creates_minimal_creator_asset(tmp_path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"generated-image")
    inserted = []
    generation_library = FakeGenerationLibrary()
    intelligence = FakeAssetIntelligenceService()
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(),
        generation_library_service=generation_library,
        asset_intelligence_service=intelligence,
        content_item_inserter=lambda payload: inserted.append(payload) or 91,
        analyze_on_registration=False,
    )

    result = service.register_generated_image(
        generated_record(source),
        creator_profile_id=2,
    )

    assert result.success
    assert result.asset_id == 91
    assert source.exists()
    assert inserted[0]["creator_profile_id"] == 2
    assert inserted[0]["file_path"] == str(source)
    assert inserted[0]["requires_vision"] is False
    assert inserted[0]["requires_nudenet"] is False
    assert inserted[0]["classification"] == "SINGLE_IMAGE"
    assert inserted[0]["status"] == "approved"
    assert inserted[0]["is_active"] is True
    assert "commerce" not in inserted[0]
    assert generation_library.links == [("generated-image-1", 91)]
    assert intelligence.pending == [(91, 2)]


def test_photoshoot_member_registration_uses_non_independent_classification(tmp_path):
    source = tmp_path / "member.png"
    source.write_bytes(b"generated-image")
    inserted = []
    generation_library = FakeGenerationLibrary()
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(),
        generation_library_service=generation_library,
        asset_intelligence_service=FakeAssetIntelligenceService(),
        content_item_inserter=lambda payload: inserted.append(payload) or 92,
        analyze_on_registration=False,
    )

    result = service.register_generated_image(
        generated_record(source), creator_profile_id=2,
        classification="UNCLASSIFIED", finalize_generation=False,
    )

    assert result.success is True
    assert inserted[0]["classification"] == "UNCLASSIFIED"
    assert generation_library.links == []


def test_register_generated_image_prevents_duplicate_insert(tmp_path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"generated-image")
    generation_library = FakeGenerationLibrary()
    intelligence = FakeAssetIntelligenceService()
    inserts = []
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(),
        generation_library_service=generation_library,
        asset_intelligence_service=intelligence,
        content_item_inserter=lambda payload: inserts.append(payload) or 100,
        analyze_on_registration=False,
    )

    result = service.register_generated_image(
        generated_record(source, imported_asset_id=44),
        creator_profile_id=2,
    )

    assert result.success
    assert result.already_registered
    assert result.asset_id == 44
    assert inserts == []
    assert generation_library.links == [("generated-image-1", 44)]
    assert intelligence.pending == [(44, 2)]


def test_intelligence_completion_does_not_overwrite_single_image_classification(tmp_path):
    source = tmp_path / "generated.png"
    source.write_bytes(b"generated-image")
    inserted = []
    updates = []
    analysis_calls = []
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(),
        generation_library_service=FakeGenerationLibrary(),
        asset_intelligence_service=FakeAssetIntelligenceService(),
        asset_analysis_service=type(
            "FakeAnalysis", (), {"analyze": lambda self, **kwargs: analysis_calls.append(kwargs)}
        )(),
        content_item_inserter=lambda payload: inserted.append(payload) or 91,
        content_item_updater=lambda asset_id, payload: updates.append((asset_id, payload)),
    )

    result = service.register_generated_image(generated_record(source), creator_profile_id=2)

    assert result.success is True
    assert inserted[0]["classification"] == "SINGLE_IMAGE"
    assert analysis_calls == [{"asset_id": 91, "creator_profile_id": 2, "progress": None}]
    assert updates == [(91, {"status": "approved"})]


def test_register_generated_image_rejects_protected_reference_role(tmp_path):
    source = tmp_path / "reference.png"
    source.write_bytes(b"reference")
    record = generated_record(source)
    record = GeneratedImageRecord(**{
        **record.__dict__,
        "generation_metadata": {"reference_library": {"is_reference": True, "protected": True, "role": "creator_identity"}},
    })
    inserts = []
    service = AssetRegistrationService(
        asset_repository=FakeAssetRepository(), generation_library_service=FakeGenerationLibrary(),
        asset_intelligence_service=FakeAssetIntelligenceService(),
        content_item_inserter=lambda payload: inserts.append(payload) or 100,
        analyze_on_registration=False,
    )

    result = service.register_generated_image(record, creator_profile_id=2)

    assert result.success is False
    assert "Protected Reference" in result.message
    assert inserts == []


def test_generation_library_ui_exposes_registration_dialog_and_states():
    source = Path("app/dashboard/pages/content_studio.py").read_text(
        encoding="utf-8"
    )

    assert '@_asset_registration_dialog("⭐ Register Asset")' in source
    assert 'help="Register Asset"' in source
    assert 'help="Already Registered"' in source
    assert '"This image will be added to your Creator Inventory."' in source
    assert '"Register Asset"' in source

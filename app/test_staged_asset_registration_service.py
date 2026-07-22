from pathlib import Path
from types import SimpleNamespace

from app.models.generation_library import GeneratedImageRecord
from app.services.asset_registration_service import AssetRegistrationService
from app.services.staged_asset_registration_service import (
    StagedAssetRegistrationService,
)


class FakeAssets:
    def __init__(self):
        self.asset = None

    def get_by_generation_image_id(self, _image_id):
        return self.asset

    def get_by_id(self, asset_id):
        return self.asset if self.asset and self.asset.id == asset_id else None


class FakeGenerationLibrary:
    def __init__(self):
        self.links = []
        self.promotions = []

    def mark_registered(self, image_id, asset_id):
        self.links.append((image_id, asset_id))

    def mark_business_registered(self, image_id, asset_id):
        self.promotions.append((image_id, asset_id))


class FakeIntelligence:
    def __init__(self):
        self.pending = []

    def initialize_pending(self, *, asset_id, creator_profile_id):
        self.pending.append((asset_id, creator_profile_id))
        return SimpleNamespace(analysis_status=SimpleNamespace(value="PENDING"))


class FakeBusinessAssets:
    def __init__(self):
        self.records = {}
        self.upserts = 0

    def get_by_asset_id(self, asset_id):
        return self.records.get(asset_id)

    def upsert_record(self, record):
        self.upserts += 1
        self.records[record.asset_id] = record
        return record


def staged_record(path: Path) -> GeneratedImageRecord:
    return GeneratedImageRecord(
        image_id="generation-1",
        generation_job_id="job-1",
        generation_request_id="request-1",
        generation_result_id="result-1",
        output_reference=str(path),
        creator_profile_id=7,
        provider_id="seedream",
        prompt_plan_id="plan-1",
        prompt_text="editorial portrait",
        creative_mode="portrait",
        reference_asset_id=12,
        status="staged_asset_library",
        provider_metadata={"provider_request_id": "provider-1"},
        prompt_metadata={"tags": ["editorial"]},
        generation_metadata={"seed": 123},
    )


def test_staged_registration_creates_pending_business_asset_without_analysis(tmp_path):
    image = tmp_path / "generation.png"
    image.write_bytes(b"image")
    assets = FakeAssets()
    library = FakeGenerationLibrary()
    intelligence = FakeIntelligence()
    business_assets = FakeBusinessAssets()
    inserted = []

    def insert(payload):
        inserted.append(payload)
        assets.asset = SimpleNamespace(
            id=51,
            creator_profile_id=7,
            media_metadata=payload["media_metadata"],
            status="approved",
        )
        return 51

    no_analysis_calls = []
    asset_registration = AssetRegistrationService(
        asset_repository=assets,
        generation_library_service=library,
        asset_intelligence_service=intelligence,
        asset_analysis_service=SimpleNamespace(
            analyze=lambda **_kwargs: no_analysis_calls.append(True)
        ),
        content_item_inserter=insert,
        analyze_on_registration=False,
    )
    service = StagedAssetRegistrationService(
        asset_registration_service=asset_registration,
        commerce_registration_repository=business_assets,
        generation_library_service=library,
    )

    result = service.register(staged_record(image), creator_profile_id=7)

    assert result.success is True
    assert result.asset_id == 51
    assert result.analysis_status == "PENDING"
    assert result.business_lifecycle_state == "INTELLIGENCE_PENDING"
    assert no_analysis_calls == []
    assert inserted[0]["file_path"] == str(image)
    assert image.exists()
    metadata = inserted[0]["media_metadata"]["asset_registration"]
    assert metadata["prompt_text"] == "editorial portrait"
    assert metadata["provider_id"] == "seedream"
    assert metadata["provider_metadata"] == {"provider_request_id": "provider-1"}
    assert inserted[0]["media_metadata"]["asset_provenance"]["classification"] == "CREATOR_APPROVAL"
    assert intelligence.pending == [(51, 7)]
    record = business_assets.records[51]
    assert record.content_intelligence_status == "PENDING"
    assert record.content_intelligence_ready is False
    assert record.commerce_registration_status.value == "PENDING"
    assert record.commerce_destination_status.value == "NOT_READY"
    assert record.product_ids == ()
    assert record.experience_ids == ()
    assert record.registration_provenance["approval_identity"]["source_item_id"] == "generation-1"
    assert library.promotions == [("generation-1", 51)]


def test_staged_registration_reuses_asset_and_business_registration(tmp_path):
    image = tmp_path / "generation.png"
    image.write_bytes(b"image")
    assets = FakeAssets()
    library = FakeGenerationLibrary()
    intelligence = FakeIntelligence()
    business_assets = FakeBusinessAssets()
    inserts = []

    def insert(payload):
        inserts.append(payload)
        assets.asset = SimpleNamespace(
            id=51,
            creator_profile_id=7,
            media_metadata=payload["media_metadata"],
            status="approved",
        )
        return 51

    service = StagedAssetRegistrationService(
        asset_registration_service=AssetRegistrationService(
            asset_repository=assets,
            generation_library_service=library,
            asset_intelligence_service=intelligence,
            content_item_inserter=insert,
            analyze_on_registration=False,
        ),
        commerce_registration_repository=business_assets,
        generation_library_service=library,
    )
    record = staged_record(image)

    first = service.register(record, creator_profile_id=7)
    second = service.register(record, creator_profile_id=7)

    assert first.asset_id == second.asset_id == 51
    assert second.success is True
    assert second.already_registered is True
    assert len(inserts) == 1
    assert business_assets.upserts == 1
    assert len(business_assets.records) == 1

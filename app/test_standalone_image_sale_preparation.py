from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.asset_intelligence import AssetIntelligenceStatus
from app.models.commercial_offering import CommercialOfferingStatus, CommercialOfferingType, PrimarySalesChannel
from app.models.commercial_publication import CommercialPublicationProvider, CommercialPublicationStatus, ProviderResourceStatus
from app.services.standalone_image_sale_preparation_service import StandaloneImageSalePreparationService


class Assets:
    def __init__(self, asset): self.asset, self.blur_updates, self.metadata_updates = asset, [], []
    def get_by_id(self, _): return self.asset
    def update_blurred_preview(self, asset_id, **values):
        self.blur_updates.append((asset_id, values))
        self.asset.blurred_preview_path = values["path"]
        self.asset.media_metadata = values["media_metadata"]
    def update_media_metadata(self, asset_id, metadata): self.metadata_updates.append((asset_id, metadata))


class Offerings:
    def __init__(self): self.value = None
    def get_by_idempotency_key(self, **_): return self.value
    def update_metadata(self, offering_id, **values):
        self.value.title = values["title"]
        self.value.description = values["description"]
        self.value.hero_asset_id = values["hero_asset_id"]
        return self.value


class OfferingService:
    def __init__(self, repository): self.repository, self.calls = repository, []
    def create(self, **values):
        self.calls.append(values)
        if self.repository.value is None:
            self.repository.value = SimpleNamespace(
                offering_id=uuid4(), status=CommercialOfferingStatus.READY,
                offering_type=CommercialOfferingType.SINGLE_IMAGE,
                primary_sales_channel=PrimarySalesChannel.AI_CHAT,
                title=values["title"], description=values["description"],
                hero_asset_id=values["hero_asset_id"])
        return self.repository.value


class Publications:
    def __init__(self): self.value, self.created, self.repository = None, 0, self
    def list_publications(self, **_): return (self.value,) if self.value else ()
    def create_publication(self, **values):
        self.created += 1
        self.value = SimpleNamespace(
            publication_id=uuid4(), provider=CommercialPublicationProvider.FANVUE,
            status=CommercialPublicationStatus.READY_TO_PUBLISH,
            provider_resource_status=ProviderResourceStatus.UNVERIFIED,
            publication_metadata=values["publication_metadata"], last_error=None)
        return self.value
    def update_metadata(self, publication_id, **values):
        self.value.publication_metadata = values["metadata"]
        return self.value


class Media:
    def __init__(self, path): self.path, self.generated = str(path), str(path)
    def resolve_derivative(self, asset, _):
        return asset.blurred_preview_path if getattr(asset, "blurred_preview_path", None) else None
    def generate_blurred_preview(self, _asset): self.generated_count = getattr(self, "generated_count", 0) + 1; return self.generated
    def build_derivative_metadata(self, **_): return {"path": self.generated}
    def merge_derivative_metadata(self, metadata, **_): return {**(metadata or {}), "derivatives": {"blurred_preview": {"path": self.generated}}}


class Teasers:
    def __init__(self): self.rows, self.vault_calls = {}, 0; self.repository = self
    def get(self, asset_id, use): return self.rows.get(use)
    def list(self, _asset_id): return tuple(self.rows.values())
    def ensure_vault(self, asset_id, *, creator_profile_id):
        self.vault_calls += 1
        self.rows["CONTENT_VAULT"] = {"teaser_id": uuid4(), "source_asset_id": asset_id,
            "distribution_use": "CONTENT_VAULT", "teaser_style": "FULL_BLUR", "status": "READY",
            "derivative_path": self.path, "derived_asset_id": None}
        return self.rows["CONTENT_VAULT"]


def make_service(tmp_path):
    original, blurred = tmp_path / "image.jpg", tmp_path / "blur.jpg"
    original.write_bytes(b"image"); blurred.write_bytes(b"blur")
    asset = SimpleNamespace(
        id=42, creator_profile_id=7, media_type="image",
        file_name="image.jpg", file_path=str(original), local_vault_path=str(original),
        blurred_preview_path=None, media_metadata={})
    assets, offerings, publications, media = Assets(asset), Offerings(), Publications(), Media(blurred)
    offering_service = OfferingService(offerings)
    profile = SimpleNamespace(
        analysis_status=AssetIntelligenceStatus.READY, title="Studio portrait",
        short_description="Portrait description", content_summary=None)
    uploads = SimpleNamespace(get=lambda *_: None)
    teasers = Teasers(); teasers.path = str(blurred)
    service = StandaloneImageSalePreparationService(
        assets=assets, intelligence=SimpleNamespace(get_profile=lambda _: profile),
        offerings=offerings, offering_service=offering_service,
        publications=publications, uploads=uploads, media=media,
        executor=SimpleNamespace(execute=lambda *_a, **_k: None), teasers=teasers)
    return service, assets, offerings, offering_service, publications, media


def test_stage_reuses_ready_intelligence_blur_and_canonical_offering(tmp_path):
    service, assets, offerings, offering_service, publications, media = make_service(tmp_path)
    first = service.stage(42, creator_profile_id=7, price_minor=1250)
    second = service.stage(42, creator_profile_id=7, price_minor=1250)
    assert first.publication_id == second.publication_id
    assert len(assets.blur_updates) == 1
    assert media.generated_count == 1
    assert publications.created == 1
    assert len(offering_service.calls) == 2
    assert offering_service.calls[0]["idempotency_key"] == offering_service.calls[1]["idempotency_key"]
    assert offering_service.calls[0]["source_photoshoot_deliverable_id"] if "source_photoshoot_deliverable_id" in offering_service.calls[0] else None is None


def test_inspect_derives_ready_only_from_real_persisted_state(tmp_path):
    service, assets, offerings, _, publications, media = make_service(tmp_path)
    publication = service.stage(42, creator_profile_id=7, price_minor=1250)
    publication.status = CommercialPublicationStatus.LIVE
    publication.provider_resource_status = ProviderResourceStatus.PRESENT
    publication.publication_metadata = {"media_link": {"url": "https://fanvue.example/link"}}
    service.uploads = SimpleNamespace(get=lambda *_: SimpleNamespace(
        upload_status="uploaded", processing_status="ready", last_error=None))
    inspected = service.inspect(42, creator_profile_id=7)
    assert inspected["status"] == "READY"
    assert inspected["destinations"] == ["CHAT"]


def test_pending_intelligence_does_not_create_commerce_or_photoshoot_state(tmp_path):
    service, assets, offerings, offering_service, publications, media = make_service(tmp_path)
    service.intelligence = SimpleNamespace(get_profile=lambda _: SimpleNamespace(
        analysis_status=AssetIntelligenceStatus.ANALYZING))
    try:
        service.stage(42, creator_profile_id=7, price_minor=1250)
        assert False, "stage should wait for canonical intelligence"
    except ValueError as error:
        assert "Intelligence must be READY" in str(error)
    assert not offering_service.calls
    assert publications.created == 0


def test_vault_only_derives_full_blur_and_preserves_one_offering(tmp_path):
    service, _, offerings, offering_service, publications, _ = make_service(tmp_path)
    service.stage(42, creator_profile_id=7, price_minor=1250, destinations=["CONTENT_VAULT"])
    service.stage(42, creator_profile_id=7, price_minor=1250, destinations=["CONTENT_VAULT"])
    assert service.teasers.vault_calls == 2
    assert publications.created == 1
    assert len({call["idempotency_key"] for call in offering_service.calls}) == 1


def test_vault_selective_requires_its_own_content_vault_teaser(tmp_path):
    service, assets, _, _, publications, media = make_service(tmp_path)
    service.teasers.rows["CHAT"] = {
        "teaser_id": uuid4(), "source_asset_id": 42, "distribution_use": "CHAT",
        "teaser_style": "SELECTIVE_BLUR", "status": "READY",
        "derivative_path": str(media.path), "derived_asset_id": 90,
    }
    with pytest.raises(ValueError, match="selective Content Vault teaser"):
        service.stage(42, creator_profile_id=7, price_minor=1250,
                      destinations=["CONTENT_VAULT"], teaser_style="SELECTIVE_BLUR")
    assert publications.created == 0

    service.teasers.rows["CONTENT_VAULT"] = {
        "teaser_id": uuid4(), "source_asset_id": 42, "distribution_use": "CONTENT_VAULT",
        "teaser_style": "SELECTIVE_BLUR", "status": "READY",
        "derivative_path": str(media.path), "derived_asset_id": 91,
    }
    service.stage(42, creator_profile_id=7, price_minor=1250,
                  destinations=["CONTENT_VAULT"], teaser_style="SELECTIVE_BLUR")
    persisted = assets.metadata_updates[-1][1]["standalone_sale_preparation"]
    assert persisted["destinations"] == ["CONTENT_VAULT"]
    assert persisted["teaser_style"] == "SELECTIVE_BLUR"
    assert service.teasers.vault_calls == 0


def test_stage_rejects_multiple_standalone_sale_destinations(tmp_path):
    service, _, _, offering_service, publications, _ = make_service(tmp_path)
    try:
        service.stage(
            42, creator_profile_id=7, price_minor=1250,
            destinations=["CHAT", "CONTENT_VAULT"],
        )
        assert False, "standalone preparation must allow exactly one selling mode"
    except ValueError as error:
        assert "exactly one selling mode" in str(error)
    assert not offering_service.calls
    assert publications.created == 0


def test_chat_requires_operator_accepted_selective_teaser(tmp_path):
    service, *_ = make_service(tmp_path)
    try:
        service.stage(42, creator_profile_id=7, price_minor=1250, destinations=["CHAT"])
        assert False
    except ValueError as error:
        assert "selective Chat teaser" in str(error)


def test_legacy_chat_fallback_requires_ready_canonical_foundation(tmp_path):
    service, _, offerings, _, _, _ = make_service(tmp_path)
    service.stage(42, creator_profile_id=7, price_minor=1250)
    # Offering type alone (and any unrelated SINGLE_PPV destination) is not authority.
    assert offerings.value.offering_type == CommercialOfferingType.SINGLE_IMAGE
    assert service.inspect(42, creator_profile_id=7)["destinations"] == []


def test_generated_filename_is_never_used_as_customer_facing_title(tmp_path):
    service, assets, offerings, offering_service, _, _ = make_service(tmp_path)
    assets.asset.file_name = "generated_image_608df091d31189fc1ccb2ff4.png"
    service.intelligence = SimpleNamespace(get_profile=lambda _: SimpleNamespace(
        analysis_status=AssetIntelligenceStatus.READY, title=None,
        short_description=None, content_summary=None))
    service.stage(42, creator_profile_id=7, price_minor=1250)
    assert offering_service.calls[0]["title"] == "Image 42"
    assert offerings.value.title == "Image 42"


def test_commercial_title_repair_updates_only_internal_fallbacks(tmp_path):
    service, _, offerings, _, publications, _ = make_service(tmp_path)
    service.stage(42, creator_profile_id=7, price_minor=1250)
    offerings.value.title = "generated_image_deadbeef.png"
    publications.value.publication_metadata = {
        "offering_snapshot": {"title": "generated_image_deadbeef.png"},
    }
    assert service.repair_commercial_title(42, creator_profile_id=7) is True
    assert offerings.value.title == "Studio portrait"
    assert publications.value.publication_metadata["offering_snapshot"]["title"] == "Studio portrait"

    offerings.value.title = "Operator Custom Title"
    publications.value.publication_metadata["offering_snapshot"]["title"] = "Operator Custom Title"
    assert service.repair_commercial_title(42, creator_profile_id=7) is False
    assert offerings.value.title == "Operator Custom Title"

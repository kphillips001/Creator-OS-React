from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.asset_library import SalePreparationRequest
from app.models.commercial_offering import (
    CommercialOffering, CommercialOfferingAsset, CommercialOfferingStatus,
    CommercialOfferingType, PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublication, CommercialPublicationProvider,
    CommercialPublicationStatus, ProviderResourceStatus,
)
from app.models.photoshoot_session_sales_strategy import SessionShotSalesRecommendation
from app.services.photoshoot_sale_preparation_service import PhotoshootSalePreparationService

NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


class Offerings:
    def __init__(self): self.by_key = {}; self.by_id = {}; self.created = 0
    def get_by_idempotency_key(self, *, idempotency_key, **_): return self.by_key.get(idempotency_key)
    def update_pricing(self, offering_id, *, price_minor, currency, **_):
        item = replace(self.by_id[offering_id], price_minor=price_minor, currency=currency)
        self.by_id[offering_id] = item
        for key, value in self.by_key.items():
            if value.offering_id == offering_id: self.by_key[key] = item
        return item
    def update_status(self, offering_id, *, status, **_):
        item = replace(self.by_id[offering_id], status=status)
        self.by_id[offering_id] = item
        for key, value in self.by_key.items():
            if value.offering_id == offering_id: self.by_key[key] = item
        return item


class OfferingService:
    def __init__(self, repository): self.repository = repository
    def create(self, *, idempotency_key, creator_profile_id, asset_ids, price_minor, currency,
               title, description, source_photoshoot_deliverable_id, **_):
        self.repository.created += 1
        identifier = uuid4()
        item = CommercialOffering(
            identifier, creator_profile_id, CommercialOfferingType.SINGLE_IMAGE,
            title, description, asset_ids[0], PrimarySalesChannel.AI_CHAT,
            CommercialOfferingStatus.DRAFT,
            (CommercialOfferingAsset(asset_ids[0], 1, True),), NOW, NOW,
            price_minor, currency, source_photoshoot_deliverable_id,
        )
        self.repository.by_key[idempotency_key] = item
        self.repository.by_id[identifier] = item
        return item


class Publications:
    def __init__(self): self.by_offering = {}; self.by_id = {}; self.created = 0
    def get_by_offering_provider(self, offering_id, _provider): return self.by_offering.get(offering_id)
    def update_metadata(self, publication_id, *, metadata, **_):
        item = replace(self.by_id[publication_id], publication_metadata=metadata, updated_at=NOW)
        self.by_id[publication_id] = item; self.by_offering[item.commercial_offering_id] = item
        return item


class PublicationService:
    def __init__(self, repository): self.repository = repository
    def create_publication(self, *, commercial_offering_id, publication_metadata, **_):
        self.repository.created += 1
        item = CommercialPublication(
            uuid4(), commercial_offering_id, CommercialPublicationProvider.FANVUE,
            CommercialPublicationStatus.READY_TO_PUBLISH, None, None, NOW, NOW,
            None, 0, publication_metadata,
        )
        self.repository.by_offering[commercial_offering_id] = item
        self.repository.by_id[item.publication_id] = item
        return item
    def get_publication(self, publication_id, **_): return self.repository.by_id.get(publication_id)
    def update_status(self, publication_id, *, status, **_):
        item = self.repository.by_id[publication_id]
        item = replace(item, status=CommercialPublicationStatus(status))
        self.repository.by_id[publication_id] = item; self.repository.by_offering[item.commercial_offering_id] = item
        return item


class Uploads:
    def list_for_publication(self, _): return ()


def strategy():
    def shot(asset, order, role, access):
        return SessionShotSalesRecommendation(asset, order, order, role, access == "FREE", access,
            "progress", None, "purpose", "escalation", "psychology", "conversation")
    return SimpleNamespace(
        strategy_version="v1", creator_profile_id=1,
        shots=(shot(1, 1, "FREE_TEASER", "FREE"), shot(2, 2, "FIRST_UNLOCK", "PAID"), shot(3, 3, "ESCALATION", "PAID")),
    )


def review(prices=None):
    prices = prices or {2: 500, 3: 900}
    return [
        {"assetId": 1, "shotOrder": 1, "salesPosition": 1, "role": "FREE_TEASER", "access": "FREE", "priceMinor": None, "currency": "USD"},
        {"assetId": 2, "shotOrder": 2, "salesPosition": 2, "role": "FIRST_UNLOCK", "access": "PAID", "priceMinor": prices.get(2), "currency": "USD"},
        {"assetId": 3, "shotOrder": 3, "salesPosition": 3, "role": "ESCALATION", "access": "PAID", "priceMinor": prices.get(3), "currency": "USD"},
    ]


def stage(preparation, prices=None):
    return preparation.stage(
        "deliverable", creator_profile_id=1, fanvue_account_id=7,
        strategy_version="v1", reviewed_steps=review(prices),
    )


def service(tmp_path):
    teaser = tmp_path / "teaser.jpg"; teaser.write_bytes(b"image")
    offerings, publications = Offerings(), Publications()
    assets = SimpleNamespace(get_by_id=lambda asset_id: SimpleNamespace(
        id=asset_id, file_path=str(teaser), local_vault_path=None,
    ))
    result = PhotoshootSalePreparationService(
        photoshoots=SimpleNamespace(get=lambda _: {
            "deliverable_id": uuid4(), "photoshoot_session_id": "session-1",
            "creator_profile_id": 1, "registration_state": "IN_ASSET_LIBRARY",
        }), strategies=SimpleNamespace(latest=lambda _: strategy()), assets=assets,
        offerings=offerings, publications=publications, uploads=Uploads(),
        offering_service=OfferingService(offerings),
        publication_service=PublicationService(publications),
        executor=SimpleNamespace(execute=lambda *_, **__: None),
    )
    return result, offerings, publications


def test_one_request_materializes_each_paid_step_without_teaser(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    staged = stage(preparation)
    assert len(staged) == 2
    assert offerings.created == 2 and publications.created == 2
    assert sorted(item.assets[0].asset_id for item in offerings.by_id.values()) == [2, 3]
    assert all(len(item.assets) == 1 for item in offerings.by_id.values())
    assert all(item.status is CommercialPublicationStatus.PUBLISHING for item in publications.by_id.values())
    assert {item.publication_metadata["session_role"] for item in publications.by_id.values()} == {"FIRST_UNLOCK", "ESCALATION"}


def test_bundle_mode_returns_placeholder_and_rejects_session_preparation(tmp_path):
    preparation, _, _ = service(tmp_path)
    preparation.photoshoots = SimpleNamespace(get=lambda _: {
        "deliverable_id": uuid4(), "photoshoot_session_id": "session-1",
        "creator_profile_id": 1, "registration_state": "IN_ASSET_LIBRARY",
        "selling_mode": "BUNDLE",
    })
    readiness = preparation.inspect("deliverable", creator_profile_id=1)
    assert readiness["sellingMode"] == "BUNDLE"
    assert readiness["status"] == "NOT_CONFIGURED"
    assert readiness["steps"] == []
    with pytest.raises(ValueError, match="BUNDLE selling mode"):
        stage(preparation)


def test_missing_strategy_is_a_normal_structured_state_without_steps(tmp_path):
    preparation, _, _ = service(tmp_path)
    preparation.strategies = SimpleNamespace(latest=lambda _: None)
    readiness = preparation.inspect("deliverable", creator_profile_id=1)
    assert readiness["photoshootSessionId"] == "session-1"
    assert readiness["sellingMode"] == "SESSION"
    assert readiness["strategyExists"] is False and readiness["strategyStatus"] == "MISSING"
    assert readiness["status"] == "STRATEGY_REQUIRED" and readiness["statusLabel"] == "Not Prepared"
    assert readiness["steps"] == [] and readiness["paidStepCount"] == 0
    with pytest.raises(ValueError, match="Generate a Session Sales Strategy"):
        stage(preparation)


def test_repeated_preparation_reuses_offerings_and_publications(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    for _ in range(2):
        stage(preparation)
    assert offerings.created == 2
    assert publications.created == 2


def test_aggregate_readiness_requires_every_paid_publication(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    stage(preparation)
    assert preparation.inspect("deliverable", creator_profile_id=1)["status"] == "PREPARING"
    first = next(iter(publications.by_id.values()))
    publications.by_id[first.publication_id] = replace(first, status=CommercialPublicationStatus.FAILED, last_error="provider")
    publications.by_offering[first.commercial_offering_id] = publications.by_id[first.publication_id]
    assert preparation.inspect("deliverable", creator_profile_id=1)["status"] == "NEEDS_ATTENTION"


def test_ready_projection_uses_persisted_link_and_ready_offering(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    stage(preparation)
    for publication_id, publication in tuple(publications.by_id.items()):
        metadata = {**publication.publication_metadata, "media_link": {"url": f"https://fanvue/{publication_id}"}}
        live = replace(publication, status=CommercialPublicationStatus.LIVE,
                       provider_resource_status=ProviderResourceStatus.PRESENT,
                       external_product_id=f"link-{publication_id}", publication_metadata=metadata,
                       published_at=NOW)
        publications.by_id[publication_id] = live; publications.by_offering[live.commercial_offering_id] = live
        offerings.update_status(live.commercial_offering_id, creator_profile_id=1, status=CommercialOfferingStatus.READY)
    result = preparation.inspect("deliverable", creator_profile_id=1)
    assert result["status"] == "READY"
    assert result["readyPaidStepCount"] == 2
    assert all(step.get("deliveryUrl") for step in result["steps"] if step["access"] == "PAID")


@pytest.mark.parametrize("mutate,message", [
    (lambda items: items[:-1], "every strategy step"),
    (lambda items: [items[0], items[1], items[1]], "duplicate Assets"),
    (lambda items: [{**items[0], "priceMinor": 300}, *items[1:]], "cannot have a price"),
    (lambda items: [items[0], {**items[1], "role": "FINALE"}, items[2]], "does not match canonical"),
    (lambda items: [items[0], {**items[1], "salesPosition": 8}, items[2]], "does not match canonical"),
    (lambda items: [items[0], items[1], {**items[2], "assetId": 999}], "every strategy step"),
    (lambda items: [items[1], items[0], items[2]], "canonical sales order"),
    (lambda items: [items[0], {**items[1], "priceMinor": 299}, items[2]], "between 300 and 50,000"),
    (lambda items: [items[0], {**items[1], "priceMinor": 50001}, items[2]], "between 300 and 50,000"),
    (lambda items: [items[0], {**items[1], "priceMinor": None}, items[2]], "between 300 and 50,000"),
])
def test_complete_review_is_validated_before_any_persistence(tmp_path, mutate, message):
    preparation, offerings, publications = service(tmp_path)
    with pytest.raises(ValueError, match=message):
        preparation.stage(
            "deliverable", creator_profile_id=1, fanvue_account_id=7,
            strategy_version="v1", reviewed_steps=mutate(review()),
        )
    assert offerings.created == 0
    assert publications.created == 0


def make_live(offerings, publications, *, price=500):
    offering = next(item for item in offerings.by_id.values() if item.assets[0].asset_id == 2)
    publication = publications.by_offering[offering.offering_id]
    live = replace(
        publication, status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        publication_metadata={**publication.publication_metadata, "price_minor": price,
                              "media_link": {"url": "https://fanvue/live-2"}},
        external_product_id="link-2", published_at=NOW,
    )
    publications.by_id[live.publication_id] = live
    publications.by_offering[offering.offering_id] = live
    offerings.update_status(offering.offering_id, creator_profile_id=1,
                            status=CommercialOfferingStatus.READY)
    return offering, live


def test_same_price_live_publication_is_reused(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    stage(preparation)
    _, live = make_live(offerings, publications)
    stage(preparation)
    assert publications.created == 2
    assert publications.by_id[live.publication_id] == live


def test_different_price_live_publication_is_preserved_and_conflicts(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    stage(preparation)
    offering, live = make_live(offerings, publications)
    with pytest.raises(ValueError, match="does not currently support editing"):
        stage(preparation, {2: 600, 3: 900})
    assert publications.by_id[live.publication_id] == live
    assert offerings.by_id[offering.offering_id].price_minor == 500


def test_failed_unpublished_offering_can_be_repriced(tmp_path):
    preparation, offerings, publications = service(tmp_path)
    stage(preparation)
    offering = next(item for item in offerings.by_id.values() if item.assets[0].asset_id == 2)
    publication = publications.by_offering[offering.offering_id]
    failed = replace(publication, status=CommercialPublicationStatus.FAILED)
    publications.by_id[failed.publication_id] = failed
    publications.by_offering[offering.offering_id] = failed
    stage(preparation, {2: 650, 3: 900})
    assert offerings.by_id[offering.offering_id].price_minor == 650


@pytest.mark.parametrize("price", ["", "not-a-price", 3.5])
def test_request_schema_rejects_nonnumeric_or_noninteger_minor_units(price):
    with pytest.raises(ValidationError):
        SalePreparationRequest.model_validate({
            "strategyVersion": "v1",
            "steps": [{"assetId": 2, "shotOrder": 2, "salesPosition": 2,
                       "role": "FIRST_UNLOCK", "access": "PAID",
                       "priceMinor": price, "currency": "USD"}],
        })

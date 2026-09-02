from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from app.models.commercial_offering import (
    CommercialOffering, CommercialOfferingAsset, CommercialOfferingStatus,
    CommercialOfferingType, PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublication, CommercialPublicationProvider,
    CommercialPublicationStatus, ProviderResourceStatus,
)
from app.services.photoshoot_bundle_sale_preparation_service import (
    PhotoshootBundleSalePreparationService,
)

NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
DELIVERABLE = uuid4()


class Photoshoots:
    def __init__(self, mode="BUNDLE", creator=7):
        self.row = {"deliverable_id": DELIVERABLE, "photoshoot_session_id": "session-1",
                    "creator_profile_id": creator, "registration_state": "IN_ASSET_LIBRARY",
                    "selling_mode": mode, "display_name": "Complete Set", "hero_asset_id": 12,
                    "commercial_intelligence_status": "READY", "commercial_intelligence_stage": "COMPLETE",
                    "intelligence_profile": {
                        "commercial_title": "Complete Set", "subtitle": "Three chapters",
                        "commercial_summary": "All originals", "buyer_profile": {"audience": "collector"},
                        "sales_strategy": {"positioning": "complete set"},
                        "sales_brain_brief": "Sell the complete sequence.",
                    }}
    def get(self, _): return self.row
    def members(self, _):
        return ({"asset_id": 12, "shot_order": 2}, {"asset_id": 11, "shot_order": 1},
                {"asset_id": 13, "shot_order": 3})


class Offerings:
    def __init__(self): self.item = None; self.created = 0
    def get_by_idempotency_key(self, **_): return self.item
    def update_pricing(self, offering_id, *, price_minor, currency, **_):
        self.item = replace(self.item, price_minor=price_minor, currency=currency)
        return self.item
    def update_status(self, offering_id, *, status, **_):
        self.item = replace(self.item, status=status); return self.item


class OfferingService:
    def __init__(self, repository): self.repository = repository
    def prepare_photoshoot(self, *_args, **_kwargs):
        return {"title": "Complete Set", "description": "All originals", "hero_asset_id": 12}
    def create(self, *, creator_profile_id, offering_type, title, description,
               hero_asset_id, primary_sales_channel, asset_ids, price_minor,
               currency, source_photoshoot_deliverable_id, **_):
        self.repository.created += 1
        assets = tuple(CommercialOfferingAsset(asset, index, asset == hero_asset_id)
                       for index, asset in enumerate(asset_ids, 1))
        self.repository.item = CommercialOffering(
            uuid4(), creator_profile_id, offering_type, title, description,
            hero_asset_id, primary_sales_channel, CommercialOfferingStatus.DRAFT,
            assets, NOW, NOW, price_minor, currency, source_photoshoot_deliverable_id,
        )
        return self.repository.item
    def update_pricing(self, offering_id, **kwargs):
        return self.repository.update_pricing(offering_id, **kwargs)


class Publications:
    def __init__(self): self.item = None; self.created = 0
    def get_by_offering_provider(self, *_): return self.item
    def update_metadata(self, publication_id, *, metadata, **_):
        self.item = replace(self.item, publication_metadata=metadata); return self.item


class PublicationService:
    def __init__(self, repository): self.repository = repository
    def create_publication(self, *, commercial_offering_id, publication_metadata, **_):
        self.repository.created += 1
        self.repository.item = CommercialPublication(
            uuid4(), commercial_offering_id, CommercialPublicationProvider.FANVUE,
            CommercialPublicationStatus.READY_TO_PUBLISH, None, None, NOW, NOW,
            None, 0, publication_metadata,
        )
        return self.repository.item
    def get_publication(self, *_args, **_kwargs): return self.repository.item
    def update_status(self, publication_id, *, status, **_):
        self.repository.item = replace(self.repository.item, status=CommercialPublicationStatus(status))
        return self.repository.item


class Executor:
    def __init__(self): self.calls = []
    def execute(self, publication_id, **kwargs): self.calls.append((publication_id, kwargs))
    def replace_live_media_link(self, publication_id, **kwargs):
        self.calls.append(("replace", publication_id, kwargs))


class Teasers:
    def __init__(self, status="NOT_CONFIGURED"): self.status = status
    def inspect(self, *_args, **_kwargs):
        return {
            "status": self.status,
            "statusLabel": {
                "READY": "Promotional Teaser Ready",
                "NEEDS_ATTENTION": "Teaser Needs Attention",
                "NOT_CONFIGURED": "Teaser Not Configured",
            }[self.status],
            "teaserAssetId": 100 if self.status != "NOT_CONFIGURED" else None,
        }


def subject(mode="BUNDLE", creator=7, teaser_status="NOT_CONFIGURED"):
    offerings, publications, executor = Offerings(), Publications(), Executor()
    service = PhotoshootBundleSalePreparationService(
        photoshoots=Photoshoots(mode, creator), assets=SimpleNamespace(),
        offerings=offerings, publications=publications,
        uploads=SimpleNamespace(), offering_service=OfferingService(offerings),
        publication_service=PublicationService(publications), executor=executor,
        teasers=Teasers(teaser_status),
    )
    return service, offerings, publications, executor


def test_bundle_preparation_creates_one_ordered_complete_offering_and_publication():
    service, offerings, publications, _ = subject()
    ids = service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    assert len(ids) == 1
    assert offerings.created == 1 and publications.created == 1
    assert offerings.item.offering_type is CommercialOfferingType.BUNDLE
    assert offerings.item.title == "Complete Set"
    assert offerings.item.source_photoshoot_deliverable_id == DELIVERABLE
    assert [member.asset_id for member in offerings.item.assets] == [11, 12, 13]
    assert offerings.item.price_minor == 3000
    assert publications.item.commercial_offering_id == offerings.item.offering_id
    assert publications.item.publication_metadata["asset_ids"] == [11, 12, 13]


def test_retry_reuses_offering_publication_and_executor_receives_one_bundle_publication():
    service, offerings, publications, executor = subject()
    first = service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    second = service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    assert first == second
    assert offerings.created == 1 and publications.created == 1
    service.execute_staged(second, creator_profile_id=7, fanvue_account_id=9)
    assert executor.calls == [(second[0], {"creator_profile_id": 7, "fanvue_account_id": 9})]


def test_existing_explicit_bundle_title_is_preserved():
    service, offerings, publications, _ = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    offerings.item = replace(offerings.item, title="Collector's Shower Edition")

    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)

    assert offerings.item.title == "Collector's Shower Edition"
    assert offerings.created == 1 and publications.created == 1


def test_ready_requires_live_present_media_link():
    service, offerings, publications, _ = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    assert service.inspect(DELIVERABLE, creator_profile_id=7)["status"] == "PREPARING"
    publications.item = replace(publications.item, status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="link-1", publication_metadata={
            **publications.item.publication_metadata,
            "media_link": {"url": "https://fanvue.example/bundle", "mediaUuids": ["1", "2", "3"]},
        })
    readiness = service.inspect(DELIVERABLE, creator_profile_id=7)
    assert readiness["status"] == "READY"
    assert readiness["statusLabel"] == "Paid Bundle Ready"
    assert readiness["bundleSalesChannel"] == "CHAT"
    assert readiness["salesChannel"] == "CHAT"
    assert readiness["deliveryUrl"] == "https://fanvue.example/bundle"
    assert readiness["autonomousSales"] == {
        "status": "NEEDS_SETUP", "statusLabel": "Needs Setup",
        "reason": "Needs promotional teaser",
    }


def test_retry_of_live_bundle_with_matching_price_is_an_idempotent_no_op():
    service, offerings, publications, executor = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    offerings.item = replace(offerings.item, status=CommercialOfferingStatus.READY)
    publication_id = publications.item.publication_id
    publications.item = replace(
        publications.item,
        status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="link-1",
        publication_metadata={
            **publications.item.publication_metadata,
            "media_link": {"url": "https://fanvue.example/bundle"},
        },
    )

    pending = service.stage(
        DELIVERABLE, creator_profile_id=7,
        fanvue_account_id=9, price_minor=3000,
    )
    service.execute_staged(pending, creator_profile_id=7, fanvue_account_id=9)

    assert pending == ()
    assert offerings.created == 1 and publications.created == 1
    assert publications.item.publication_id == publication_id
    assert publications.item.status is CommercialPublicationStatus.LIVE
    assert executor.calls == []
    readiness = service.inspect(DELIVERABLE, creator_profile_id=7)
    assert readiness["status"] == "READY"
    assert readiness["promotionalTeaser"]["status"] == "NOT_CONFIGURED"


def test_retry_of_live_bundle_rejects_a_changed_locked_price():
    service, offerings, publications, _ = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    offerings.item = replace(offerings.item, status=CommercialOfferingStatus.READY)
    publications.item = replace(
        publications.item,
        status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="link-1",
    )

    with pytest.raises(ValueError, match="live Bundle Media Link price is locked"):
        service.stage(
            DELIVERABLE, creator_profile_id=7,
            fanvue_account_id=9, price_minor=3100,
        )


def test_price_replacement_stages_existing_publication_without_mutating_price_or_link():
    service, offerings, publications, executor = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=1999)
    offerings.item = replace(offerings.item, status=CommercialOfferingStatus.READY)
    old_publication_id = publications.item.publication_id
    publications.item = replace(
        publications.item, status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="old-link", publication_metadata={
            **publications.item.publication_metadata,
            "media_link": {"uuid": "old-link", "url": "https://fanvue.example/old",
                           "price_minor": 1999, "media_uuids": ["m1", "m2", "m3"]},
        },
    )

    staged = service.stage_price_replacement(
        DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=2499)

    assert staged == (old_publication_id,)
    assert offerings.item.price_minor == 1999
    assert publications.item.external_product_id == "old-link"
    assert publications.item.publication_metadata["media_link"]["url"].endswith("/old")
    assert publications.item.publication_metadata["media_link_replacement"] == {
        "state": "QUEUED", "target_price_minor": 2499, "currency": "USD",
        "old_uuid": "old-link", "old_url": "https://fanvue.example/old",
        "old_price_minor": 1999, "asset_ids": [11, 12, 13],
        "fanvue_account_id": 9,
    }
    assert service.inspect(DELIVERABLE, creator_profile_id=7)["status"] == "PREPARING"
    assert executor.calls == []


def test_unchanged_bundle_price_is_an_idempotent_replacement_no_op():
    service, offerings, publications, executor = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=1999)
    offerings.item = replace(offerings.item, status=CommercialOfferingStatus.READY)
    publications.item = replace(
        publications.item, status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="old-link", publication_metadata={
            **publications.item.publication_metadata,
            "media_link": {"uuid": "old-link", "url": "https://fanvue.example/old"},
        },
    )

    assert service.stage_price_replacement(
        DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=1999) == ()
    assert executor.calls == []


def test_second_price_replacement_request_is_rejected_before_execution():
    service, offerings, publications, _ = subject()
    service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=1999)
    offerings.item = replace(offerings.item, status=CommercialOfferingStatus.READY)
    publications.item = replace(
        publications.item, status=CommercialPublicationStatus.LIVE,
        provider_resource_status=ProviderResourceStatus.PRESENT,
        external_product_id="old-link", publication_metadata={
            **publications.item.publication_metadata,
            "media_link": {"uuid": "old-link", "url": "https://fanvue.example/old"},
            "media_link_replacement": {"state": "QUEUED", "target_price_minor": 2499},
        },
    )

    with pytest.raises(ValueError, match="already in progress"):
        service.stage_price_replacement(
            DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=2599)


def test_bundle_readiness_projects_persisted_content_wall_channel():
    service, _, _, _ = subject()
    service.photoshoots.row["bundle_sales_channel"] = "CONTENT_WALL"

    readiness = service.inspect(DELIVERABLE, creator_profile_id=7)

    assert readiness["bundleSalesChannel"] == "CONTENT_WALL"
    assert readiness["salesChannel"] == "WALL"
    assert readiness["sellingMode"] == "BUNDLE"


@pytest.mark.parametrize(("paid_status", "teaser_status", "expected_status", "reason"), [
    ("NOT_CONFIGURED", "NOT_CONFIGURED", "NEEDS_SETUP", "Needs Bundle media"),
    ("READY", "NOT_CONFIGURED", "NEEDS_SETUP", "Needs promotional teaser"),
    ("NOT_CONFIGURED", "READY", "NEEDS_SETUP", "Needs Bundle media"),
    ("READY", "READY", "READY", None),
    ("NEEDS_ATTENTION", "READY", "NEEDS_SETUP", "Bundle publication needs attention"),
    ("READY", "NEEDS_ATTENTION", "NEEDS_SETUP", "Promotional teaser needs attention"),
])
def test_chat_autonomous_readiness_requires_paid_bundle_and_teaser(
    paid_status, teaser_status, expected_status, reason,
):
    result = PhotoshootBundleSalePreparationService._autonomous_sales_readiness(
        paid_status=paid_status, teaser_status=teaser_status, channel="CHAT",
    )
    assert result["status"] == expected_status
    assert result["reason"] == reason


def test_content_wall_never_reports_autonomous_chat_ready():
    result = PhotoshootBundleSalePreparationService._autonomous_sales_readiness(
        paid_status="READY", teaser_status="READY", channel="CONTENT_WALL",
    )
    assert result == {
        "status": "DISABLED", "statusLabel": "Chat Sales Disabled",
        "reason": "Designated for Ava's Content Wall",
    }


def test_complete_media_and_teaser_are_not_autonomously_ready_without_intelligence():
    result = PhotoshootBundleSalePreparationService._autonomous_sales_readiness(
        paid_status="READY", teaser_status="READY", channel="CHAT",
        intelligence_ready=False,
    )
    assert result == {
        "status": "NEEDS_SETUP", "statusLabel": "Commercial Intelligence Incomplete",
        "reason": "Commercial intelligence needs attention",
    }


def test_historical_single_image_offering_is_not_bundle_readiness():
    service, offerings, _, _ = subject()
    offerings.item = CommercialOffering(
        uuid4(), 7, CommercialOfferingType.SINGLE_IMAGE, "Old", None, 11,
        PrimarySalesChannel.AI_CHAT, CommercialOfferingStatus.READY,
        (CommercialOfferingAsset(11, 1, True),), NOW, NOW, 500, "USD", DELIVERABLE,
    )
    readiness = service.inspect(DELIVERABLE, creator_profile_id=7)
    assert readiness["status"] == "NEEDS_ATTENTION"
    assert "non-BUNDLE" in readiness["error"]


def test_prepared_bundle_fails_closed_when_approved_membership_changes():
    service, offerings, _, _ = subject()
    service.stage(
        DELIVERABLE, creator_profile_id=7,
        fanvue_account_id=9, price_minor=3000,
    )
    offerings.item = replace(
        offerings.item, assets=offerings.item.assets[:-1]
    )
    readiness = service.inspect(DELIVERABLE, creator_profile_id=7)
    assert readiness["status"] == "NEEDS_ATTENTION"
    assert "membership differs" in readiness["error"]


@pytest.mark.parametrize("price", [None, True, 299, 50001])
def test_invalid_price_is_rejected(price):
    service, *_ = subject()
    with pytest.raises(ValueError, match="between 300 and 50,000"):
        service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=price)


def test_mode_and_creator_scope_are_enforced():
    service, *_ = subject(mode="SESSION")
    with pytest.raises(ValueError, match="requires BUNDLE"):
        service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)
    service, *_ = subject(creator=8)
    with pytest.raises(KeyError, match="not found"):
        service.stage(DELIVERABLE, creator_profile_id=7, fanvue_account_id=9, price_minor=3000)

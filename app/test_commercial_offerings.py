from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commercial_offerings as api
from app.models.commercial_offering import (
    CommercialOffering,
    CommercialOfferingAsset,
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)
from app.models.commercial_publication import CommercialPublicationStatus
from app.repositories.commercial_offering_repository import CommercialOfferingRepository
from app.services.commercial_offering_service import CommercialOfferingService
from app.services.commercial_offering_service import CommercialOfferingBusinessError


class Assets:
    def __init__(self, media):
        self.media = media
    def get_by_id(self, asset_id):
        kind = self.media.get(asset_id)
        return SimpleNamespace(id=asset_id, creator_profile_id=7, media_type=kind) if kind else None


class Destinations:
    def __init__(self, available=True):
        self.available = available
        self.committed = []
    def is_available_inventory(self, _): return self.available
    def commit_to_destination(self, asset_id, destination, **context):
        self.committed.append((asset_id, destination, context))


class Offerings:
    def __init__(self): self.created = None
    def create(self, **values):
        self.created = values
        now = datetime.now(timezone.utc)
        return CommercialOffering(
            uuid4(), values["creator_profile_id"], values["offering_type"],
            values["title"], values["description"], values["hero_asset_id"],
            values["primary_sales_channel"], CommercialOfferingStatus.DRAFT,
            tuple(CommercialOfferingAsset(asset_id, position, asset_id == values["hero_asset_id"])
                  for position, asset_id in enumerate(values["asset_ids"], 1)),
            now, now,
        )


class Photoshoots:
    def common_approved_photoshoot(self, asset_ids):
        return "photoshoot-1" if len(asset_ids) >= 2 else None


@pytest.mark.parametrize("offering_type,media", [
    ("SINGLE_IMAGE", {1: "image"}),
    ("PHOTOSET", {1: "image", 2: "image"}),
    ("VIDEO", {1: "video"}),
    ("STORY", {1: "story"}),
    ("STORY_SET", {1: "story", 2: "story"}),
    ("BUNDLE", {1: "image", 2: "video"}),
])
def test_create_supported_offering_shapes(offering_type, media):
    repository = Offerings()
    service = CommercialOfferingService(
        repository=repository, asset_repository=Assets(media),
        content_destinations=Destinations(),
        photoshoot_repository=Photoshoots(),
    )
    result = service.create(
        creator_profile_id=7, offering_type=offering_type, title="Launch",
        description=None, hero_asset_id=next(iter(media)),
        primary_sales_channel="AI_CHAT", asset_ids=list(media),
    )
    assert result.offering_type.value == offering_type
    assert tuple(member.asset_id for member in result.assets) == tuple(media)
    if offering_type in {"PHOTOSET", "BUNDLE"}:
        assert [item[0] for item in service.content_destinations.committed] == list(media)
        assert all(
            item[1].value == offering_type
            and item[2]["source_workflow"] == "commercial_offering_creation"
            for item in service.content_destinations.committed
        )
    else:
        assert service.content_destinations.committed == []


@pytest.mark.parametrize("offering_type,media", [
    ("SINGLE_IMAGE", {1: "image", 2: "image"}),
    ("PHOTOSET", {1: "image"}),
    ("VIDEO", {1: "image"}),
    ("STORY", {1: "story", 2: "story"}),
    ("STORY_SET", {1: "story"}),
])
def test_invalid_counts_and_media_types_are_rejected(offering_type, media):
    service = CommercialOfferingService(
        repository=Offerings(), asset_repository=Assets(media),
        content_destinations=Destinations(),
        photoshoot_repository=Photoshoots(),
    )
    with pytest.raises(ValueError, match="requires"):
        service.create(
            creator_profile_id=7, offering_type=offering_type, title="Invalid",
            description=None, hero_asset_id=1, primary_sales_channel="AI_CHAT",
            asset_ids=list(media),
        )


def test_invalid_channel_duplicate_membership_and_committed_asset_are_rejected():
    service = CommercialOfferingService(
        repository=Offerings(), asset_repository=Assets({1: "image"}),
        content_destinations=Destinations(),
        photoshoot_repository=Photoshoots(),
    )
    common = dict(creator_profile_id=7, offering_type="SINGLE_IMAGE", title="One",
                  description=None, hero_asset_id=1)
    with pytest.raises(ValueError, match="Primary Sales Channel"):
        service.create(**common, primary_sales_channel="FANVUE", asset_ids=[1])
    with pytest.raises(ValueError, match="Duplicate"):
        service.create(**common, primary_sales_channel="AI_CHAT", asset_ids=[1, 1])
    service.content_destinations = Destinations(False)
    with pytest.raises(ValueError, match="already commercially committed"):
        service.create(**common, primary_sales_channel="AI_CHAT", asset_ids=[1])
    service.content_destinations = Destinations()
    with pytest.raises(ValueError, match="requires"):
        service.create(
            **{**common, "offering_type": "BUNDLE"},
            primary_sales_channel="AI_CHAT", asset_ids=[1],
        )


def test_bundle_reuses_already_committed_canonical_assets():
    destinations = Destinations(False)
    service = CommercialOfferingService(
        repository=Offerings(),
        asset_repository=Assets({1: "image", 2: "image"}),
        content_destinations=destinations,
        photoshoot_repository=Photoshoots(),
    )
    result = service.create(
        creator_profile_id=7, offering_type="BUNDLE", title="Full Set",
        description=None, hero_asset_id=1, primary_sales_channel="AI_CHAT",
        asset_ids=[1, 2],
    )
    assert result.offering_type is CommercialOfferingType.BUNDLE
    assert tuple(member.asset_id for member in result.assets) == (1, 2)
    assert destinations.committed == []


def test_reference_asset_cannot_become_a_commercial_offering():
    class ReferenceAssets:
        def get_by_id(self, asset_id):
            return SimpleNamespace(
                id=asset_id, creator_profile_id=7, media_type="image",
                classification="REFERENCE",
                media_metadata={
                    "reference_library": {
                        "is_reference": True, "canonical": True, "protected": True,
                    }
                },
                suggested_tags=["canonical-reference", "identity"],
            )

    service = CommercialOfferingService(
        repository=Offerings(), asset_repository=ReferenceAssets(),
        content_destinations=Destinations(),
    )
    with pytest.raises(ValueError, match="identity-only"):
        service.create(
            creator_profile_id=7, offering_type="SINGLE_IMAGE", title="Invalid",
            description=None, hero_asset_id=93, primary_sales_channel="AI_CHAT",
            asset_ids=[93],
        )


class Cursor:
    def __init__(self, statements):
        self.statements = statements
        self.row = None
        self.rows = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params):
        self.statements.append((sql, params))
        now = datetime.now(timezone.utc)
        if "INSERT INTO public.commercial_offerings" in sql:
            self.row = {
                "offering_id": params[0], "creator_profile_id": 7,
                "offering_type": "PHOTOSET", "title": "Ordered",
                "description": None, "hero_asset_id": 2,
                "primary_sales_channel": "TELEGRAM_WALL", "status": "DRAFT",
                "created_at": now, "updated_at": now,
            }
        elif "SELECT asset_id,position,is_hero" in sql:
            self.rows = [
                {"asset_id": 2, "position": 1, "is_hero": True},
                {"asset_id": 1, "position": 2, "is_hero": False},
            ]
    def fetchone(self): return self.row
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, statements): self.statements = statements
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return Cursor(self.statements)


def test_repository_persists_order_and_prevents_duplicate_members_structurally():
    statements = []
    result = CommercialOfferingRepository(
        connection_factory=lambda: Connection(statements)
    ).create(
        creator_profile_id=7, offering_type=CommercialOfferingType.PHOTOSET,
        title="Ordered", description=None, hero_asset_id=2,
        primary_sales_channel=PrimarySalesChannel.TELEGRAM_WALL,
        asset_ids=(2, 1),
    )
    member_inserts = [params for sql, params in statements if "INSERT INTO public.commercial_offering_assets" in sql]
    assert [(params[1], params[2]) for params in member_inserts] == [(2, 1), (1, 2)]
    assert [member.asset_id for member in result.assets] == [2, 1]
    migration = open("migrations/forward/20260723_002_commercial_offerings_foundation.sql", encoding="utf-8").read()
    assert "PRIMARY KEY (offering_id, asset_id)" in migration
    assert "UNIQUE (offering_id, position)" in migration


class ApiService:
    def __init__(self):
        self.repository = Offerings()
    def create(self, **values):
        return self.repository.create(
            creator_profile_id=values["creator_profile_id"],
            offering_type=CommercialOfferingType(values["offering_type"]),
            title=values["title"], description=values["description"],
            hero_asset_id=values["hero_asset_id"],
            primary_sales_channel=PrimarySalesChannel(values["primary_sales_channel"]),
            asset_ids=tuple(values["asset_ids"]),
        )


def test_create_api_is_narrow_and_returns_membership(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "_service", ApiService)
    app = FastAPI(); app.include_router(api.router)
    response = TestClient(app).post("/api/v1/commercial-offerings", json={
        "offeringType": "SINGLE_IMAGE", "title": "One",
        "primarySalesChannel": "AI_CHAT", "assetIds": [1], "heroAssetId": 1,
    })
    assert response.status_code == 201
    assert response.json()["primarySalesChannel"] == "AI_CHAT"
    assert response.json()["assets"] == [{"assetId": 1, "position": 1, "isHero": True}]


class PublicationRows:
    def __init__(self, statuses=()):
        self.rows = tuple(SimpleNamespace(status=status) for status in statuses)

    def list(self, **_values):
        return self.rows


class PricingOfferings:
    def __init__(self):
        self.updated = []

    def update_pricing(self, offering_id, **values):
        self.updated.append((offering_id, values))
        return "updated"


@pytest.mark.parametrize(
    "status",
    [
        CommercialPublicationStatus.DRAFT,
        CommercialPublicationStatus.READY_TO_PUBLISH,
        CommercialPublicationStatus.FAILED,
        CommercialPublicationStatus.ARCHIVED,
    ],
)
def test_pricing_is_editable_before_or_after_non_live_publication(status):
    repository = PricingOfferings()
    service = CommercialOfferingService(
        repository=repository,
        publication_repository=PublicationRows([status]),
    )
    assert service.update_pricing(
        uuid4(), creator_profile_id=7, price_minor=1299, currency="USD"
    ) == "updated"
    assert repository.updated


def test_live_pricing_is_rejected_before_database_update():
    repository = PricingOfferings()
    service = CommercialOfferingService(
        repository=repository,
        publication_repository=PublicationRows(
            [CommercialPublicationStatus.LIVE]
        ),
    )
    with pytest.raises(CommercialOfferingBusinessError) as captured:
        service.update_pricing(
            uuid4(), creator_profile_id=7, price_minor=1299, currency="USD"
        )
    assert captured.value.code == "LIVE_PRICE_LOCKED"
    assert captured.value.required_action
    assert repository.updated == []


def test_generic_pricing_api_returns_structured_live_conflict(monkeypatch):
    class LockedService:
        def update_pricing(self, *_args, **_kwargs):
            raise CommercialOfferingBusinessError(
                "LIVE_PRICE_LOCKED",
                "Price cannot change while the provider publication is LIVE.",
                required_action="Use the provider-backed publication replacement workflow.",
            )

    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(api, "_service", LockedService)
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).patch(
        f"/api/v1/commercial-offerings/{uuid4()}/pricing",
        json={"priceMinor": 1299, "currency": "USD"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "LIVE_PRICE_LOCKED"

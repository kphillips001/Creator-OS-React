from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_offering import (
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)
from app.models.commercial_publication import CommercialPublicationStatus
from app.services.commerce_authoring_service import (
    CommerceAuthoringError,
    CommerceAuthoringService,
)
from app.services.commercial_offering_service import CommercialOfferingBusinessError


class OfferingDomain:
    def __init__(self):
        self.created = None
        self.current = None
        self.updated = []
        self.repository = SimpleNamespace(archive=self.archive)

    def create(self, **values):
        self.created = values
        return SimpleNamespace(offering_id=uuid4(), **values)

    def get(self, *_args, **_kwargs):
        return self.current

    def update_metadata(self, offering_id, **values):
        self.updated.append(("metadata", values))
        return self.current

    def update_pricing(self, offering_id, **values):
        self.updated.append(("pricing", values))
        return self.current

    def validate_pricing_update(self, offering_id, **values):
        return None

    def archive(self, offering_id, **values):
        self.updated.append(("archive", values))
        return self.current


class Publications:
    def __init__(self, statuses=()):
        self.items = tuple(
            SimpleNamespace(status=status, publication_id=uuid4())
            for status in statuses
        )
        self.created = 0

    def list_publications(self, **_values):
        return self.items

    def create_publication(self, **_values):
        self.created += 1
        return SimpleNamespace(
            publication_id=uuid4(),
            status=CommercialPublicationStatus.READY_TO_PUBLISH,
        )


def current_offering(price=999):
    return SimpleNamespace(
        offering_id=uuid4(), title="Existing", description=None,
        hero_asset_id=42, price_minor=price, currency="USD",
        status=CommercialOfferingStatus.DRAFT,
    )


@pytest.mark.parametrize(
    ("offering_type", "asset_ids"),
    [
        ("SINGLE_IMAGE", [1]),
        ("PHOTOSET", [1, 2]),
        ("VIDEO", [3]),
    ],
)
def test_authoring_creates_supported_ai_chat_offerings_with_atomic_price(
    offering_type, asset_ids,
):
    offerings = OfferingDomain()
    service = CommerceAuthoringService(
        offerings=offerings, publications=Publications()
    )
    service.create(
        creator_profile_id=2, offering_type=offering_type, title="New",
        description="Description", hero_asset_id=asset_ids[0],
        primary_sales_channel="AI_CHAT", asset_ids=asset_ids,
        price_minor=999, currency="USD",
    )
    assert offerings.created["asset_ids"] == asset_ids
    assert offerings.created["price_minor"] == 999
    assert offerings.created["currency"] == "USD"


@pytest.mark.parametrize(
    ("values", "code"),
    [
        ({"offering_type": "STORY"}, "INVALID_OFFERING_TYPE"),
        ({"primary_sales_channel": "OTHER"}, "INVALID_SALES_CHANNEL"),
        ({"price_minor": 0}, "INVALID_PRICE"),
        ({"currency": "EUR"}, "INVALID_CURRENCY"),
    ],
)
def test_authoring_returns_structured_validation_errors(values, code):
    defaults = dict(
        creator_profile_id=2, offering_type="SINGLE_IMAGE", title="New",
        description=None, hero_asset_id=1, primary_sales_channel="AI_CHAT",
        asset_ids=[1], price_minor=999, currency="USD",
    )
    defaults.update(values)
    with pytest.raises(CommerceAuthoringError) as error:
        CommerceAuthoringService(
            offerings=OfferingDomain(), publications=Publications()
        ).create(**defaults)
    assert error.value.code == code


def test_underlying_asset_and_destination_errors_remain_structured():
    offerings = OfferingDomain()
    offerings.create = lambda **_values: (_ for _ in ()).throw(
        ValueError("Asset 7 is already commercially committed.")
    )
    with pytest.raises(CommerceAuthoringError) as error:
        CommerceAuthoringService(
            offerings=offerings, publications=Publications()
        ).create(
            creator_profile_id=2, offering_type="SINGLE_IMAGE", title="New",
            description=None, hero_asset_id=7, primary_sales_channel="AI_CHAT",
            asset_ids=[7], price_minor=999, currency="USD",
        )
    assert error.value.code == "ASSET_NOT_AVAILABLE"


def test_live_price_change_and_publishing_edit_are_blocked():
    offerings = OfferingDomain()
    offerings.current = current_offering()
    offerings.validate_pricing_update = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        CommercialOfferingBusinessError(
            "LIVE_PRICE_LOCKED",
            "Price cannot change while the provider publication is LIVE.",
        )
    )
    live = CommerceAuthoringService(
        offerings=offerings,
        publications=Publications([CommercialPublicationStatus.LIVE]),
    )
    with pytest.raises(CommerceAuthoringError) as error:
        live.update(
            offerings.current.offering_id, creator_profile_id=2,
            title="Existing", description=None, price_minor=1099, currency="USD",
        )
    assert error.value.code == "LIVE_PRICE_LOCKED"
    publishing = CommerceAuthoringService(
        offerings=offerings,
        publications=Publications([CommercialPublicationStatus.PUBLISHING]),
    )
    with pytest.raises(CommerceAuthoringError) as error:
        publishing.archive(offerings.current.offering_id, creator_profile_id=2)
    assert error.value.code == "OFFERING_STATE_CONFLICT"


def test_publish_reuses_existing_record_and_prevents_duplicate_creation():
    offerings = OfferingDomain()
    offerings.current = current_offering()
    publications = Publications([CommercialPublicationStatus.READY_TO_PUBLISH])
    result = CommerceAuthoringService(
        offerings=offerings, publications=publications
    ).resolve_publication(offerings.current.offering_id, creator_profile_id=2)
    assert result is publications.items[0]
    assert publications.created == 0


def test_creation_repository_is_transactional_and_ordered():
    source = open(
        "app/repositories/commercial_offering_repository.py", encoding="utf-8"
    ).read()
    assert "with self._connection_factory() as connection" in source
    assert "enumerate(asset_ids, 1)" in source
    assert "price_minor,currency" in source

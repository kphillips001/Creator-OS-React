from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.commercial_offering import (
    CommercialOfferingAsset,
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublication,
    CommercialPublicationProvider,
    CommercialPublicationStatus,
    ProviderResourceStatus,
)
from app.models.content_destination import ContentDestination
from app.services.commercial_fulfillment_service import CommercialFulfillmentService
from app.services.commercial_publication_service import CommercialPublicationService
from app.services.fanvue_commercial_publication_reconciliation_service import (
    FanvueCommercialPublicationReconciliationService,
)


def _publication(status=CommercialPublicationStatus.LIVE):
    now = datetime.now(timezone.utc)
    return CommercialPublication(
        uuid4(), uuid4(), CommercialPublicationProvider.FANVUE, status,
        "link-1", now, now, now, None, 0,
        {"media_link": {
            "uuid": "link-1", "url": "https://fanvue.com/fvml-1",
            "price_minor": 999, "media_uuids": ["media-1"],
        }},
    )


class _PublicationBoundary:
    def __init__(self, publication):
        self.publication = publication

    def get_publication(self, *_args, **_kwargs):
        return self.publication


class _ReconciliationRepository:
    def __init__(self, publication):
        self.publication = publication
        self.recorded = None

    def record_reconciliation(self, _publication_id, **values):
        self.recorded = values
        status = (
            CommercialPublicationStatus.ARCHIVED
            if values.get("archive_live")
            else self.publication.status
        )
        return CommercialPublication(
            **{
                **self.publication.__dict__,
                "status": status,
                "provider_resource_status": values["resource_status"],
                "last_reconciled_at": datetime.now(timezone.utc),
                "reconciliation_result": values["result"],
            }
        )


class _FanvueReads:
    def __init__(self, records):
        self.records = records
        self.calls = 0

    def list_media_links(self):
        self.calls += 1
        return {"data": self.records}


@pytest.mark.parametrize(
    ("records", "expected", "result", "archived"),
    [
        (
            [{"uuid": "link-1", "price": 999, "mediaUuids": ["media-1"]}],
            ProviderResourceStatus.PRESENT, "PROVIDER_RESOURCE_CONFIRMED", False,
        ),
        ([], ProviderResourceStatus.MISSING, "PROVIDER_RESOURCE_MISSING", True),
        (
            [{"uuid": "link-1", "price": 1000, "mediaUuids": ["media-1"]}],
            ProviderResourceStatus.MISMATCH,
            "PROVIDER_COMPOSITION_OR_PRICE_MISMATCH", False,
        ),
        (
            [
                {"uuid": "link-1", "price": 999, "mediaUuids": ["media-1"]},
                {"uuid": "link-1", "price": 999, "mediaUuids": ["media-1"]},
            ],
            ProviderResourceStatus.AMBIGUOUS, "MULTIPLE_PROVIDER_RECORDS", False,
        ),
    ],
)
def test_fanvue_reconciliation_is_read_only_and_classifies_provider_state(
    records, expected, result, archived,
):
    publication = _publication()
    repository = _ReconciliationRepository(publication)
    client = _FanvueReads(records)
    outcome = FanvueCommercialPublicationReconciliationService(
        repository=repository,
        publication_service=_PublicationBoundary(publication),
        client_factory=lambda _account_id: client,
    ).reconcile(publication.publication_id, creator_profile_id=7, fanvue_account_id=3)

    assert client.calls == 1
    assert outcome.provider_resource_status == expected
    assert outcome.result == result
    assert repository.recorded["archive_live"] is archived if archived else "archive_live" not in repository.recorded


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Destinations:
    def __init__(self):
        self.commits = []

    def commit_to_destination(self, asset_id, destination, **values):
        self.commits.append((asset_id, destination, values))


class _FinalizationRepository:
    def __init__(self, publication):
        self.publication = publication
        self.finalized = None

    def get(self, *_args, **_kwargs):
        return self.publication

    def finalize_live(self, publication_id, **values):
        self.finalized = (publication_id, values)
        return self.publication


def test_live_finalization_commits_single_asset_atomically():
    publication = _publication(CommercialPublicationStatus.PUBLISHING)
    offering = SimpleNamespace(
        offering_id=publication.commercial_offering_id,
        offering_type=CommercialOfferingType.SINGLE_IMAGE,
        assets=(CommercialOfferingAsset(101, 1, True),),
    )
    destinations = _Destinations()
    repository = _FinalizationRepository(publication)
    service = CommercialPublicationService(
        repository=repository,
        offering_repository=SimpleNamespace(get=lambda *_args, **_kwargs: offering),
        content_destinations=destinations,
        connection_factory=_Transaction,
        commercial_eligibility=SimpleNamespace(
            require_offering=lambda *_args, **_kwargs: None
        ),
    )
    service.finalize_provider_live(
        publication.publication_id, creator_profile_id=7,
        external_product_id="link-1", delivery_url="https://fanvue.com/fvml-1",
        metadata=publication.publication_metadata,
    )

    assert destinations.commits[0][0:2] == (101, ContentDestination.SINGLE_PPV)
    assert destinations.commits[0][2]["connection"] is repository.finalized[1]["connection"]


class _FulfillmentRepository:
    def __init__(self, row):
        self.row = row

    def get(self, *_args, **_kwargs):
        return self.row


def test_stale_publication_cannot_fulfill_and_does_not_leak_deleted_url():
    row = {
        "offering_id": uuid4(), "title": "Test", "description": None,
        "offering_type": "SINGLE_IMAGE", "primary_sales_channel": "AI_CHAT",
        "price_minor": 999, "currency": "USD", "hero_asset_id": 101,
        "asset_ids": [101], "destinations": ["AVAILABLE_INVENTORY"],
        "offering_status": "DRAFT", "publication_id": uuid4(),
        "provider": "FANVUE", "external_product_id": "deleted-link",
        "delivery_url": "https://fanvue.com/deleted",
        "publication_status": "ARCHIVED",
        "provider_resource_status": "MISSING",
        "last_reconciled_at": datetime.now(timezone.utc), "published_at": None,
    }
    result = CommercialFulfillmentService(
        repository=_FulfillmentRepository(row)
    ).get_fulfillment(row["offering_id"], creator_profile_id=7)

    assert result.fulfillable is False
    assert result.ineligibility_reason == "PUBLICATION_NOT_LIVE"
    assert result.provider_resource_id is None
    assert result.delivery_url is None

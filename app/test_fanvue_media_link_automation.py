from types import SimpleNamespace
import hashlib
from uuid import uuid4
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from app.services.fanvue_official_client import FanvueAPIError, FanvueOfficialClient
from app.services.fanvue_oauth_service import FanvueReauthorizationRequired
from app.services.fanvue_media_link_publication_executor import (
    FanvueMediaLinkPublicationExecutor, PublicationPending,
)
from app.services.commercial_fulfillment_service import CommercialFulfillmentService
from app.services.conversation_gateway import ConversationGateway
from app.models.commercial_offering import (
    CommercialOffering,
    CommercialOfferingAsset,
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)
from app.models.commercial_publication import (
    CommercialPublication,
    CommercialPublicationProvider,
    CommercialPublicationStatus,
)


class Response:
    def __init__(self, status=200, body=None, text="", headers=None):
        self.status_code, self._body, self.text = status, body, text
        self.headers = headers or {}
    def json(self):
        if self._body is None:
            raise ValueError
        return self._body


class OAuth:
    def __init__(self, scopes=None, refresh=None):
        self.scopes = set(scopes or ())
        self.refresh = refresh or {"success": True, "access_token": "new-token"}
        self.refresh_calls = 0
    def get_valid_access_token(self): return "token"
    def refresh_access_token(self):
        self.refresh_calls += 1
        return self.refresh
    def require_scopes(self, *scopes):
        missing = set(scopes) - self.scopes
        if missing:
            raise FanvueReauthorizationRequired("reauthorization required")


class Session:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)
    def put(self, url, **kwargs):
        self.calls.append(("PUT", url, kwargs))
        return Response(headers={"ETag": '"part-etag"'})


SCOPES = {"read:creator", "write:creator", "read:media", "write:media"}


def test_version_header_and_401_refresh_exactly_once():
    oauth = OAuth(SCOPES)
    session = Session([Response(401, {}), Response(200, {"status": "ready"})])
    body = FanvueOfficialClient(1, oauth=oauth, session=session).get_media("media-1")
    assert body["status"] == "ready"
    assert oauth.refresh_calls == 1
    assert all(call[2]["headers"]["X-Fanvue-API-Version"] == "2025-06-26"
               for call in session.calls)
    assert session.calls[1][2]["headers"]["Authorization"] == "Bearer new-token"


def test_invalid_grant_requires_reauthorization():
    oauth = OAuth(SCOPES, {"success": False, "response": {"error": "invalid_grant"}})
    client = FanvueOfficialClient(1, oauth=oauth, session=Session([Response(401, {})]))
    with pytest.raises(FanvueReauthorizationRequired):
        client.get_media("media-1")


def test_429_honors_retry_after():
    sleeps = []
    session = Session([
        Response(429, {}, headers={"Retry-After": "7"}),
        Response(200, {"data": []}),
    ])
    client = FanvueOfficialClient(1, oauth=OAuth(SCOPES), session=session, sleep=sleeps.append)
    assert client.list_media_links() == {"data": []}
    assert sleeps == [7]


def test_media_link_crud_and_exact_reconciliation():
    link = {"uuid": "link-1", "price": 900, "mediaUuids": ["b", "a"]}
    session = Session([
        Response(200, {"data": [link]}),
        Response(201, link),
        Response(204, None),
    ])
    client = FanvueOfficialClient(1, oauth=OAuth(SCOPES), session=session)
    assert client.find_equivalent_media_link(["a", "b"], 900) == [link]
    assert client.create_media_link(["a", "b"], 900)["uuid"] == "link-1"
    assert client.delete_media_link("link-1") is None
    assert [call[0] for call in session.calls] == ["GET", "POST", "DELETE"]
    with pytest.raises(ValueError):
        client.create_media_link(["a"], 299)


def test_missing_write_creator_scope_is_explicit():
    client = FanvueOfficialClient(
        1, oauth=OAuth({"read:creator", "read:media", "write:media"}),
        session=Session([]),
    )
    with pytest.raises(FanvueReauthorizationRequired):
        client.create_media_link(["a"], 500)


class Uploads:
    def __init__(self, checkpoint=None):
        self.checkpoint, self.parts, self.session_saves = checkpoint, {}, 0
        self.reusable = None
    def get(self, *_): return self.checkpoint
    def initialize(self, **values):
        self.checkpoint = SimpleNamespace(
            publication_upload_id=uuid4(), provider_media_uuid=None,
            provider_upload_id=None, part_size_bytes=None, total_parts=None,
            uploaded_parts={}, upload_status="pending", processing_status="pending",
            content_hash=values["content_hash"], file_size_bytes=values["file_size_bytes"])
        return self.checkpoint
    def find_ready_reusable(self, **_values): return self.reusable
    def initialize_reused(self, **values):
        self.checkpoint = SimpleNamespace(
            publication_upload_id=uuid4(), provider_media_uuid=values["provider_media_uuid"],
            provider_upload_id=None, part_size_bytes=None, total_parts=None,
            uploaded_parts={}, upload_status="uploaded", processing_status="ready",
            content_hash=values["content_hash"], file_size_bytes=values["file_size_bytes"])
        return self.checkpoint
    def save_session(self, _, *, media_uuid, upload_id, part_size, total_parts):
        self.session_saves += 1
        self.checkpoint.provider_media_uuid, self.checkpoint.provider_upload_id = media_uuid, upload_id
        self.checkpoint.part_size_bytes, self.checkpoint.total_parts = part_size, total_parts
        self.checkpoint.upload_status = "uploading"
        return self.checkpoint
    def save_part(self, _, *, part_number, etag):
        self.parts[str(part_number)] = etag
        self.checkpoint.uploaded_parts = dict(self.parts)
    def mark_uploaded(self, _, processing_status):
        self.checkpoint.upload_status = "uploaded"
        self.checkpoint.processing_status = processing_status
    def mark_processing(self, _, status, error=None):
        self.checkpoint.processing_status = status


class UploadClient:
    def __init__(self, statuses=("created", "ready")):
        self.statuses, self.puts, self.completed, self.sessions = list(statuses), [], None, 0
    def create_upload_session(self, **_):
        self.sessions += 1
        return {"mediaUuid": "media-1", "uploadId": "upload-1", "partSize": 3, "totalParts": 3}
    def get_upload_part_url(self, _, number): return f"https://signed.invalid/{number}"
    def put_part(self, _, content):
        self.puts.append(content)
        return f"etag-{len(self.puts)}"
    def complete_upload(self, _, parts):
        self.completed = parts
        return {"status": "processing"}
    def get_media(self, _): return {"status": self.statuses.pop(0) if self.statuses else "processing"}


def test_executor_splits_multiple_parts_and_preserves_ordered_etags(tmp_path):
    path = tmp_path / "asset.jpg"
    path.write_bytes(b"1234567")
    uploads, client = Uploads(), UploadClient(statuses=("ready",))
    executor = FanvueMediaLinkPublicationExecutor(
        assets=SimpleNamespace(get_by_id=lambda _: SimpleNamespace(
            creator_profile_id=7, media_type="image", local_vault_path=None,
            file_path=str(path))),
        uploads=uploads, sleep=lambda _: None)
    assert executor._upload_asset(client, uuid4(), 10, 7, 3) == "media-1"
    assert client.puts == [b"123", b"456", b"7"]
    assert client.completed == [
        {"PartNumber": 1, "ETag": "etag-1"},
        {"PartNumber": 2, "ETag": "etag-2"},
        {"PartNumber": 3, "ETag": "etag-3"},
    ]


def test_executor_reuses_ready_upload_for_same_account_asset_and_hash(tmp_path):
    path = tmp_path / "asset.jpg"
    path.write_bytes(b"same revision")
    uploads, client = Uploads(), UploadClient(statuses=("ready",))
    uploads.reusable = SimpleNamespace(provider_media_uuid="existing-media")
    executor = FanvueMediaLinkPublicationExecutor(
        assets=SimpleNamespace(get_by_id=lambda _: SimpleNamespace(
            creator_profile_id=7, media_type="image", local_vault_path=None,
            file_path=str(path))), uploads=uploads, sleep=lambda _: None)
    assert executor._upload_asset(client, uuid4(), 10, 7, 3) == "existing-media"
    assert client.sessions == 0
    assert client.puts == []


def test_processing_timeout_resumes_existing_media_without_new_upload(tmp_path):
    path = tmp_path / "asset.jpg"
    path.write_bytes(b"123")
    uploads, first = Uploads(), UploadClient(statuses=("processing",) * 4)
    executor = FanvueMediaLinkPublicationExecutor(
        assets=SimpleNamespace(get_by_id=lambda _: SimpleNamespace(
            creator_profile_id=7, media_type="image", local_vault_path=None,
            file_path=str(path))),
        uploads=uploads, sleep=lambda _: None)
    publication_id = uuid4()
    with pytest.raises(PublicationPending):
        executor._upload_asset(first, publication_id, 10, 7, 3)
    second = UploadClient(statuses=("ready",))
    assert executor._upload_asset(second, publication_id, 10, 7, 3) == "media-1"
    assert second.sessions == 0
    assert second.puts == []


def test_ambiguous_completion_timeout_reconciles_persisted_media_before_resuming(tmp_path):
    from requests.exceptions import ReadTimeout

    path = tmp_path / "asset.jpg"
    path.write_bytes(b"123")
    uploads = Uploads()

    class Client(UploadClient):
        def __init__(self):
            super().__init__(("processing", "ready"))

        def complete_upload(self, _upload_id, _parts):
            raise ReadTimeout("completion response timed out")

    client = Client()
    executor = FanvueMediaLinkPublicationExecutor(
        assets=SimpleNamespace(get_by_id=lambda _: SimpleNamespace(
            creator_profile_id=7, media_type="image", local_vault_path=None,
            file_path=str(path))),
        uploads=uploads, sleep=lambda _: None,
    )

    assert executor._upload_asset(client, uuid4(), 10, 7, 3) == "media-1"
    assert uploads.checkpoint.upload_status == "uploaded"
    assert uploads.checkpoint.processing_status == "ready"


def test_retry_skips_upload_completion_when_media_uuid_is_already_processing(tmp_path):
    path = tmp_path / "asset.jpg"
    path.write_bytes(b"123")
    uploads = Uploads()
    publication_id = uuid4()
    uploads.checkpoint = uploads.initialize(
        publication_id=publication_id, asset_id=10, fanvue_account_id=3,
        media_type="image", content_hash=hashlib.sha256(b"123").hexdigest(),
        file_size_bytes=3,
    )
    uploads.save_session(
        uploads.checkpoint.publication_upload_id, media_uuid="media-1",
        upload_id="upload-1", part_size=3, total_parts=1,
    )
    uploads.save_part(uploads.checkpoint.publication_upload_id, part_number=1, etag="etag-1")
    client = UploadClient(statuses=("processing", "ready"))
    executor = FanvueMediaLinkPublicationExecutor(
        assets=SimpleNamespace(get_by_id=lambda _: SimpleNamespace(
            creator_profile_id=7, media_type="image", local_vault_path=None,
            file_path=str(path))),
        uploads=uploads, sleep=lambda _: None,
    )

    assert executor._upload_asset(client, publication_id, 10, 7, 3) == "media-1"
    assert client.completed is None


def test_bundle_is_supported_by_existing_multi_media_link_executor():
    publication = SimpleNamespace(
        provider=CommercialPublicationProvider.FANVUE,
        status=CommercialPublicationStatus.READY_TO_PUBLISH,
    )
    offering = SimpleNamespace(
        status=CommercialOfferingStatus.READY,
        primary_sales_channel=PrimarySalesChannel.AI_CHAT,
        offering_type=CommercialOfferingType.BUNDLE,
        price_minor=1200,
        assets=(SimpleNamespace(asset_id=1), SimpleNamespace(asset_id=2)),
    )
    FanvueMediaLinkPublicationExecutor._validate(publication, offering)


@pytest.mark.parametrize("channel", [
    PrimarySalesChannel.AI_CHAT,
    PrimarySalesChannel.TELEGRAM_WALL,
])
def test_media_link_executor_accepts_supported_commercial_channels(channel):
    publication = SimpleNamespace(
        provider=CommercialPublicationProvider.FANVUE,
        status=CommercialPublicationStatus.READY_TO_PUBLISH,
    )
    offering = SimpleNamespace(
        status=CommercialOfferingStatus.DRAFT,
        primary_sales_channel=channel,
        offering_type=CommercialOfferingType.BUNDLE,
        price_minor=2499,
        assets=tuple(SimpleNamespace(asset_id=value) for value in (174, 172, 173)),
    )
    FanvueMediaLinkPublicationExecutor._validate(publication, offering)


def test_media_link_executor_rejects_unsupported_channel():
    publication = SimpleNamespace(
        provider=CommercialPublicationProvider.FANVUE,
        status=CommercialPublicationStatus.READY_TO_PUBLISH,
    )
    offering = SimpleNamespace(
        status=CommercialOfferingStatus.DRAFT,
        primary_sales_channel="UNSUPPORTED",
        offering_type=CommercialOfferingType.BUNDLE,
        price_minor=2499,
        assets=(SimpleNamespace(asset_id=174),),
    )
    with pytest.raises(ValueError, match="unavailable for this sales channel"):
        FanvueMediaLinkPublicationExecutor._validate(publication, offering)


def test_claimed_validation_failure_is_persisted_and_claim_is_released():
    publication_id, offering_id = uuid4(), uuid4()
    publication = SimpleNamespace(
        publication_id=publication_id, commercial_offering_id=offering_id,
        provider=CommercialPublicationProvider.FANVUE,
        status=CommercialPublicationStatus.PUBLISHING,
    )
    offering = SimpleNamespace(
        status=CommercialOfferingStatus.DRAFT,
        primary_sales_channel="UNSUPPORTED",
        offering_type=CommercialOfferingType.BUNDLE,
        price_minor=2499,
        assets=(SimpleNamespace(asset_id=174),),
    )

    class Repository:
        released = None
        def claim_execution(self, *_args, **_kwargs): return "claim-1"
        def release_execution(self, publication_id, claim): self.released = (publication_id, claim)

    class PublicationService:
        failed = None
        def get_publication(self, *_args, **_kwargs): return publication
        def mark_failed(self, publication_id, **kwargs):
            self.failed = (publication_id, kwargs["error"])
            publication.status = CommercialPublicationStatus.FAILED

    repository, publication_service = Repository(), PublicationService()
    executor = FanvueMediaLinkPublicationExecutor(
        publications=repository,
        offerings=SimpleNamespace(get=lambda *_args, **_kwargs: offering),
        publication_service=publication_service,
    )
    with pytest.raises(ValueError, match="unavailable for this sales channel"):
        executor.execute(publication_id, creator_profile_id=7, fanvue_account_id=2)
    assert publication_service.failed == (
        publication_id, "Fanvue Media Links are unavailable for this sales channel.",
    )
    assert publication.status is CommercialPublicationStatus.FAILED
    assert repository.released == (publication_id, "claim-1")


def test_full_bundle_publication_preserves_order_and_reuses_provider_link():
    now = datetime.now(timezone.utc)
    offering = CommercialOffering(
        offering_id=uuid4(), creator_profile_id=7,
        offering_type=CommercialOfferingType.BUNDLE,
        title="Complete Photoshoot", description=None, hero_asset_id=10,
        primary_sales_channel=PrimarySalesChannel.AI_CHAT,
        status=CommercialOfferingStatus.READY,
        assets=(
            CommercialOfferingAsset(asset_id=10, position=0, is_hero=True),
            CommercialOfferingAsset(asset_id=11, position=1, is_hero=False),
        ),
        created_at=now, updated_at=now, price_minor=1200,
    )
    publications = [
        CommercialPublication(
            publication_id=uuid4(), commercial_offering_id=offering.offering_id,
            provider=CommercialPublicationProvider.FANVUE,
            status=CommercialPublicationStatus.READY_TO_PUBLISH,
            external_product_id=None, published_at=None, created_at=now,
            updated_at=now, last_error=None, retry_count=0,
        )
        for _ in range(2)
    ]
    memberships = ((10, "photoshoot-1"), (11, "photoshoot-1"))

    class PublicationRepository:
        def __init__(self):
            self.metadata = []

        def claim_execution(self, *_args, **_kwargs):
            return "claim"

        def release_execution(self, *_args):
            pass

        def update_metadata(self, _id, *, metadata, **_kwargs):
            self.metadata.append(metadata)

    class PublicationService:
        def __init__(self):
            self.by_id = {value.publication_id: value for value in publications}
            self.live = []

        def get_publication(self, publication_id, **_kwargs):
            return self.by_id[publication_id]

        def update_status(self, publication_id, *, status, **_kwargs):
            return replace(self.by_id[publication_id], status=status)

        def finalize_provider_live(self, publication_id, **values):
            self.live.append((publication_id, values))
            return SimpleNamespace(
                publication_id=publication_id,
                status=CommercialPublicationStatus.LIVE,
                delivery_url=values["delivery_url"],
            )

        def mark_failed(self, *_args, **_kwargs):
            raise AssertionError("publication should not fail")

    class Client:
        API_VERSION = "test"

        def __init__(self):
            self.link = None
            self.creations = 0
            self.reconciliations = []

        def require_media_link_scopes(self):
            pass

        def get_current_user(self):
            return {"uuid": "creator-uuid"}

        def find_equivalent_media_link(self, media_uuids, price):
            self.reconciliations.append((tuple(media_uuids), price))
            return [self.link] if self.link else []

        def create_media_link(self, media_uuids, price):
            self.creations += 1
            self.link = {
                "uuid": "link-1", "url": "https://fanvue.test/link-1",
                "price": price, "mediaUuids": list(media_uuids),
            }
            return self.link

    repository = PublicationRepository()
    publication_service = PublicationService()
    client = Client()
    executor = FanvueMediaLinkPublicationExecutor(
        publications=repository,
        offerings=SimpleNamespace(get=lambda *_args, **_kwargs: offering),
        publication_service=publication_service,
        client_factory=lambda _account: client,
    )
    executor.commercial_eligibility = SimpleNamespace(
        require_offering=lambda *_args, **_kwargs: None
    )
    executor._upload_asset = (
        lambda _client, _publication, asset_id, *_args:
        f"media-{asset_id}"
    )

    results = [
        executor.execute(
            publication.publication_id,
            creator_profile_id=7,
            fanvue_account_id=3,
        )
        for publication in publications
    ]

    assert all(result.status is CommercialPublicationStatus.LIVE for result in results)
    assert client.creations == 1
    assert client.reconciliations == [
        (("media-10", "media-11"), 1200),
        (("media-10", "media-11"), 1200),
    ]
    assert repository.metadata[-1]["ordered_asset_ids"] == [10, 11]
    assert memberships == ((10, "photoshoot-1"), (11, "photoshoot-1"))
    assert [member.asset_id for member in offering.assets] == [10, 11]

    fulfillment_row = {
        "offering_id": offering.offering_id, "title": offering.title,
        "description": None, "offering_type": "BUNDLE",
        "primary_sales_channel": "AI_CHAT", "price_minor": 1200,
        "currency": "USD", "hero_asset_id": 10, "asset_ids": [10, 11],
        "destinations": ["BUNDLE", "BUNDLE"], "offering_status": "READY",
        "publication_id": publications[0].publication_id, "provider": "FANVUE",
        "external_product_id": "link-1",
        "delivery_url": "https://fanvue.test/link-1",
        "publication_status": "LIVE", "provider_resource_status": "PRESENT",
        "last_reconciled_at": now, "published_at": now,
    }
    fulfillment = CommercialFulfillmentService(
        repository=SimpleNamespace(get=lambda *_args, **_kwargs: fulfillment_row)
    ).get_fulfillment(offering.offering_id, creator_profile_id=7)
    delivery = ConversationGateway.__new__(ConversationGateway)._authoritative_delivery(
        response_text="Here is the approved bundle.",
        offering=fulfillment,
    )

    assert fulfillment.fulfillable is True
    assert fulfillment.ordered_asset_ids == (10, 11)
    assert delivery[0] == "https://fanvue.test/link-1"
    assert delivery[3] is True

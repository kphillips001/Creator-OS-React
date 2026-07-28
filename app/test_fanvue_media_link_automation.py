from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.fanvue_official_client import FanvueAPIError, FanvueOfficialClient
from app.services.fanvue_oauth_service import FanvueReauthorizationRequired
from app.services.fanvue_media_link_publication_executor import (
    FanvueMediaLinkPublicationExecutor, PublicationPending,
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
    def get(self, *_): return self.checkpoint
    def initialize(self, **values):
        self.checkpoint = SimpleNamespace(
            publication_upload_id=uuid4(), provider_media_uuid=None,
            provider_upload_id=None, part_size_bytes=None, total_parts=None,
            uploaded_parts={}, upload_status="pending", processing_status="pending",
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
    def __init__(self, statuses=("ready",)):
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
    uploads, client = Uploads(), UploadClient()
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

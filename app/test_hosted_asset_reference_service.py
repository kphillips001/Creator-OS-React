from datetime import datetime, timedelta, timezone
from dataclasses import replace
from types import SimpleNamespace

import pytest
import requests

from app.models.generation_engine import GenerationRequest
from app.providers.generation.base import SafeTransportError, WaveSpeedSubmissionAmbiguousError
from app.providers.generation.seedream_provider import Seedream50ProProvider
from app.services.hosted_asset_reference_service import HostedAssetReferenceError, HostedAssetReferenceService


class FakeRepository:
    def __init__(self, current=None):
        self.current = current
        self.saved = []
        self.used = []
        self.verified = []
        self.stale = []

    def find_current(self, **_): return self.current
    def touch_used(self, value): self.used.append(value)
    def touch_verified(self, value): self.verified.append(value)
    def mark_stale(self, value, **kwargs): self.stale.append((value, kwargs))
    def save_ready(self, **kwargs): self.saved.append(kwargs); return SimpleNamespace(**kwargs)


class Response:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status; self._body = body or {}; self.headers = headers or {}
    def json(self): return self._body
    def raise_for_status(self):
        if self.status_code >= 400: raise requests.HTTPError(str(self.status_code))


class SequencedHttp:
    def __init__(self, *, gets=(), posts=()): self.gets=list(gets); self.posts=list(posts); self.calls=[]
    def get(self, url, **kwargs): self.calls.append(("GET", url, kwargs)); value=self.gets.pop(0); return value if not isinstance(value, Exception) else (_ for _ in ()).throw(value)
    def post(self, url, **kwargs): self.calls.append(("POST", url, kwargs)); value=self.posts.pop(0); return value if not isinstance(value, Exception) else (_ for _ in ()).throw(value)


def test_reuses_recent_checksum_matched_reference_without_network(tmp_path):
    source = tmp_path / "canonical.png"; source.write_bytes(b"canonical")
    record = SimpleNamespace(reference_id="hosted-1", hosted_url="https://cdn.test/canonical.png",
                             verified_at=datetime.now(timezone.utc) - timedelta(minutes=2))
    repository = FakeRepository(record)
    http = SequencedHttp()
    service = HostedAssetReferenceService(repository=repository, http_client=http, sleep=lambda _: None)
    assert service.resolve(asset_id=93, source_path=str(source), host_name="imgbb", uploader=lambda _: pytest.fail("upload")) == record.hosted_url
    assert repository.used == ["hosted-1"]
    assert http.calls == []


def test_checksum_change_hosts_verifies_and_persists_once(tmp_path):
    source = tmp_path / "canonical.png"; source.write_bytes(b"new canonical")
    repository = FakeRepository()
    http = SequencedHttp(gets=[Response(200)])
    uploads = []
    service = HostedAssetReferenceService(repository=repository, http_client=http, sleep=lambda _: None)
    url = service.resolve(asset_id=94, source_path=str(source), host_name="imgbb",
                          uploader=lambda path: uploads.append(path) or "https://cdn.test/new.png")
    assert url == "https://cdn.test/new.png"
    assert len(uploads) == len(repository.saved) == 1
    assert repository.saved[0]["asset_id"] == 94
    assert repository.saved[0]["source_checksum"] == service.checksum(source)


def test_verification_retries_connection_resets_then_succeeds():
    http = SequencedHttp(gets=[requests.ConnectionError("reset"), requests.ConnectionError("reset"), Response(206)])
    sleeps = []
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=http, sleep=sleeps.append)
    service.verify("https://cdn.test/canonical.png", asset_id=93)
    assert len(http.calls) == 3
    assert sleeps == [2.0, 5.0]


def test_three_verification_resets_produce_clear_retryable_failure():
    http = SequencedHttp(gets=[requests.ConnectionError("raw one"), requests.ConnectionError("raw two"), requests.ConnectionError("raw three")])
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=http, sleep=lambda _: None)
    with pytest.raises(HostedAssetReferenceError, match="could not be verified after 3 attempts") as caught:
        service.verify("https://cdn.test/canonical.png", asset_id=93)
    assert "ConnectionError" not in str(caught.value)


def test_expiring_provider_reference_is_replaced_before_submission(tmp_path, monkeypatch):
    monkeypatch.setenv("HOSTED_REFERENCE_MAX_AGE_SECONDS", "518400")
    source = tmp_path / "canonical.png"; source.write_bytes(b"canonical")
    current = SimpleNamespace(
        reference_id="old", hosted_url="https://cdn.test/old.png",
        created_at=datetime.now(timezone.utc) - timedelta(days=6, seconds=1),
        verified_at=datetime.now(timezone.utc),
    )
    repository = FakeRepository(current)
    http = SequencedHttp(gets=[Response(200, headers={"Content-Type": "image/png", "Content-Length": "9"})])
    service = HostedAssetReferenceService(repository=repository, http_client=http, sleep=lambda _: None)
    resolved = service.resolve(
        asset_id=93, source_path=str(source), host_name="wavespeed_media",
        uploader=lambda _: "https://cdn.test/fresh.png",
    )
    assert resolved == "https://cdn.test/fresh.png"
    assert repository.stale[0][1]["error_code"] == "hosted_reference_expiring"


def test_non_image_provider_reference_is_rejected():
    http = SequencedHttp(gets=[Response(200, headers={"Content-Type": "text/html"})])
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=http, sleep=lambda _: None)
    with pytest.raises(HostedAssetReferenceError, match="non-image content"):
        service.verify("https://cdn.test/not-an-image", asset_id=93)


def test_reference_preparation_failure_prevents_provider_submission(tmp_path):
    source = tmp_path / "canonical.png"; source.write_bytes(b"canonical")
    request = _request()
    request = replace(request, reference_asset_path=str(source), metadata={})
    http = SequencedHttp()
    hosted = SimpleNamespace(resolve=lambda **_: (_ for _ in ()).throw(
        HostedAssetReferenceError("Provider input preparation failed before submission.")
    ))
    provider = Seedream50ProProvider(
        api_key="test", http_client=http, hosted_reference_service=hosted, sleep=lambda _: None,
    )
    result = provider.execute(request)
    assert result.failure_reason == "Provider input preparation failed before submission."
    assert http.calls == []


def _request():
    return GenerationRequest(
        request_id=f"request-{datetime.now(timezone.utc).timestamp()}", creator_profile_id=2, prompt_plan_id="plan-1", prompt_text="Portrait",
        reference_asset_id=93, reference_asset_path="https://cdn.test/reference.png",
        provider_id="seedream_5_0_pro", generation_type="image_to_image", media_type="image", image_count=1,
        metadata={"reference_image_url": "https://cdn.test/reference.png"},
    )


def test_wavespeed_poll_get_retries_transport_reset():
    http = SequencedHttp(gets=[requests.ConnectionError("reset"), Response(200, {"data": {"status": "completed", "outputs": ["https://cdn.test/output.png"]}})])
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    result = provider.poll_status_once(SimpleNamespace(provider_request_id="prediction-1"))
    assert result.status == "succeeded"
    assert len(http.calls) == 2


def test_ambiguous_wavespeed_submission_is_not_retried():
    http = SequencedHttp(posts=[requests.ConnectionError("reset")])
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    with pytest.raises(WaveSpeedSubmissionAmbiguousError, match="could not safely confirm") as caught:
        provider.submit_generation(_request())
    assert caught.value.may_have_been_accepted is True
    assert len(http.calls) == 1


def test_ambiguous_submission_records_stage_and_acceptance_risk():
    http = SequencedHttp(posts=[requests.ConnectionError("reset")])
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    result = provider.execute(_request())
    failure = result.execution_metadata["failures"][0]
    assert failure["stage"] == "wavespeed_submission"
    assert failure["may_have_been_accepted"] is True
    assert "ConnectionError" not in result.failure_reason
    assert len(http.calls) == 1


def test_three_poll_resets_are_mapped_without_raw_python_tuple():
    http = SequencedHttp(gets=[requests.ConnectionError("reset")] * 3)
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    with pytest.raises(SafeTransportError, match="status check was interrupted after 3 attempts"):
        provider.poll_status_once(SimpleNamespace(provider_request_id="prediction-1"))


def test_canonical_upload_uses_wavespeed_media_endpoint(tmp_path):
    source = tmp_path / "canonical.png"; source.write_bytes(b"not-an-image")
    http = SequencedHttp(posts=[
        requests.ConnectionError("reset"), requests.ConnectionError("reset"),
        Response(200, {"data": {"download_url": "https://cdn.wavespeed.ai/uploads/canonical.png"}}),
    ])
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    assert provider._upload_reference_image(source, asset_id=93) == "https://cdn.wavespeed.ai/uploads/canonical.png"
    assert len(http.calls) == 3
    assert all(call[1] == provider.media_upload_endpoint for call in http.calls)
    assert "file" in http.calls[-1][2]["files"]


def test_three_canonical_upload_resets_surface_clear_retry_message(tmp_path):
    source = tmp_path / "canonical.png"; source.write_bytes(b"not-an-image")
    http = SequencedHttp(posts=[requests.ConnectionError("reset")] * 3)
    provider = Seedream50ProProvider(api_key="test", http_client=http, sleep=lambda _: None)
    service = HostedAssetReferenceService(repository=FakeRepository(), http_client=http, sleep=lambda _: None)
    with pytest.raises(HostedAssetReferenceError, match="Could not host the canonical reference after 3 attempts") as caught:
        service.resolve(asset_id=93, source_path=str(source), host_name="wavespeed_media",
                        uploader=lambda path: provider._upload_reference_image(path, asset_id=93))
    assert "ConnectionResetError" not in str(caught.value)

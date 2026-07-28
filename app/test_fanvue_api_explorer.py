from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import fanvue_api_explorer as api
from app.services.fanvue_api_explorer_service import (
    FanvueAPIExplorerService,
    redact_sensitive,
)
from app.services.fanvue_official_client import FanvueAPIError


class Response:
    status_code = 200
    headers = {"x-request-id": "request-1", "authorization": "secret"}
    text = ""

    def json(self):
        return {
            "data": {"items": [{"uuid": "buyer-1", "amount": 999}]},
            "pagination": {"cursor": "next-1", "nextPage": "page-2"},
        }


class Client:
    calls = []

    def __init__(self, account_id):
        self.account_id = account_id

    def request(self, method, path, **kwargs):
        self.calls.append((self.account_id, method, path, kwargs))
        return Response()


def test_service_executes_allowlisted_get_and_returns_diagnostics():
    service = FanvueAPIExplorerService(
        client_factory=Client, clock=iter((1.0, 1.125)).__next__
    )
    result = service.inspect(
        fanvue_account_id=2,
        operation="earnings",
        scopes=("read:insights",),
        start_date="2026-07-01",
        end_date="2026-07-24",
        page_size=25,
    )
    assert Client.calls[-1][1:3] == ("GET", "/insights/earnings")
    assert Client.calls[-1][3]["params"] == {
        "startDate": "2026-07-01", "endDate": "2026-07-24", "limit": 25
    }
    assert result["httpStatus"] == 200
    assert result["elapsedMs"] == 125.0
    assert result["recordCount"] == 1
    assert result["cursor"] == "next-1"
    assert result["headers"]["authorization"] == "[REDACTED]"


def test_service_returns_provider_unauthorized_response():
    class Unauthorized(Client):
        def request(self, method, path, **kwargs):
            raise FanvueAPIError(
                "Fanvue request failed with HTTP 401.",
                status_code=401,
                body={"error": "unauthorized", "access_token": "do-not-show"},
            )

    result = FanvueAPIExplorerService(client_factory=Unauthorized).inspect(
        fanvue_account_id=2, operation="current-user"
    )
    assert result["httpStatus"] == 401
    assert result["body"] == {
        "error": "unauthorized", "access_token": "[REDACTED]"
    }


def test_endpoint_requires_oauth_and_rejects_unknown_operations(monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    monkeypatch.setattr(api, "selected_account_id", lambda: 2)
    monkeypatch.setattr(api, "get_account_by_id", lambda _: {"id": 2})
    headers = {"X-Creator-OS-Developer": "true"}
    response = client.get(
        "/api/v1/developer/fanvue-api-explorer/current-user",
        headers=headers,
    )
    assert response.status_code == 401

    monkeypatch.setattr(
        api, "get_account_by_id",
        lambda _: {"id": 2, "oauth_access_token": "token"},
    )
    response = client.get(
        "/api/v1/developer/fanvue-api-explorer/delete-media",
        headers=headers,
    )
    assert response.status_code == 400
    assert "Unsupported" in response.json()["detail"]


def test_media_endpoint_validates_and_selects_uuid():
    media_uuid = "11111111-1111-4111-8111-111111111111"
    result = FanvueAPIExplorerService(
        client_factory=Client
    ).inspect(fanvue_account_id=2, operation="media", media_uuid=media_uuid)
    assert result["endpoint"] == f"/media/{media_uuid}"
    try:
        FanvueAPIExplorerService(client_factory=Client).inspect(
            fanvue_account_id=2, operation="media", media_uuid="../posts"
        )
    except ValueError as exc:
        assert "valid UUID" in str(exc)
    else:
        raise AssertionError("Invalid Media UUID must be rejected.")


def test_read_only_operations_map_to_the_official_get_endpoints():
    Client.calls.clear()
    service = FanvueAPIExplorerService(client_factory=Client)
    service.inspect(fanvue_account_id=2, operation="media-links")
    service.inspect(fanvue_account_id=2, operation="current-user")

    assert [(call[1], call[2]) for call in Client.calls] == [
        ("GET", "/media-links"),
        ("GET", "/users/me"),
    ]


def test_recursive_redaction_preserves_business_identifiers():
    assert redact_sensitive({
        "accessToken": "secret",
        "nested": {"client_secret": "secret", "uuid": "buyer-uuid"},
        "cookies": "secret",
        "mediaUuids": ["media-1"],
    }) == {
        "accessToken": "[REDACTED]",
        "nested": {"client_secret": "[REDACTED]", "uuid": "buyer-uuid"},
        "cookies": "[REDACTED]",
        "mediaUuids": ["media-1"],
    }

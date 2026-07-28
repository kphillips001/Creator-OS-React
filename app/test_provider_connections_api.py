from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import provider_connections as api
from app import fanvue_callback_server as callback_server


def account(scope="read:creator read:media write:media"):
    now = datetime.now(timezone.utc)
    return {
        "id": 2, "display_name": "Ava Blackthorne", "account_name": "ava",
        "username": "ava", "fanvue_user_uuid": "fanvue-1",
        "oauth_access_token": "secret", "oauth_refresh_token": "refresh-secret",
        "oauth_scope": scope, "oauth_expires_at": 2_000_000_000,
        "oauth_connected_at": now, "updated_at": now,
    }


def client(monkeypatch, tmp_path, value=None):
    selected = tmp_path / "selected.json"
    selected.write_text('{"last_selected_account_id": 2}', encoding="utf-8")
    monkeypatch.setattr(api, "SELECTED_ACCOUNT_FILE", selected)
    monkeypatch.setattr(api, "OAUTH_SESSION_FILE", tmp_path / "oauth.json")
    monkeypatch.setattr(api, "get_account_by_id", lambda _: value or account())
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app)


def test_status_is_safe_and_reports_missing_write_creator(monkeypatch, tmp_path):
    response = client(monkeypatch, tmp_path).get("/api/v1/administration/providers/fanvue")
    assert response.status_code == 200
    body = response.json()
    assert body["connectionStatus"] == "REAUTHORIZATION_REQUIRED"
    assert body["missingScopes"] == ["write:creator"]
    assert body["mediaLinkCapability"]["ready"] is False
    serialized = str(body)
    assert "secret" not in serialized


def test_connected_status_has_media_link_capability(monkeypatch, tmp_path):
    value = account("read:creator write:creator read:media write:media")
    body = client(monkeypatch, tmp_path, value).get(
        "/api/v1/administration/providers/fanvue").json()
    assert body["connectionStatus"] == "CONNECTED"
    assert body["publicationReady"] is True
    assert body["mediaLinkCapability"] == {"ready": True, "reason": None}


def test_authorize_reuses_oauth_service_and_persists_server_side_pkce(monkeypatch, tmp_path):
    class OAuth:
        def __init__(self, account_id, redirect_uri):
            assert account_id == 2
            assert redirect_uri == api.DEFAULT_REACT_CALLBACK_URI
        def generate_authorization_url(self):
            return {"authorization_url": "https://auth.fanvue.test/oauth",
                    "code_verifier": "verifier", "state": "state"}
    monkeypatch.delenv("FANVUE_REACT_REDIRECT_URI", raising=False)
    monkeypatch.setattr(api, "FanvueOAuthService", OAuth)
    value = client(monkeypatch, tmp_path)
    body = value.post("/api/v1/administration/providers/fanvue/authorize").json()
    assert body == {"authorizationUrl": "https://auth.fanvue.test/oauth"}
    session = api.OAUTH_SESSION_FILE.read_text(encoding="utf-8")
    assert '"flow": "react_administration"' in session
    assert '"code_verifier": "verifier"' in session
    assert f'"redirect_uri": "{api.DEFAULT_REACT_CALLBACK_URI}"' in session


def test_react_callback_validates_state_exchanges_and_returns_to_react(
    monkeypatch, tmp_path
):
    session_file = tmp_path / "oauth.json"
    session_file.write_text(
        """{"flow":"react_administration","fanvue_account_id":2,"code_verifier":"""
        """"verifier","state":"expected","redirect_uri":"http://localhost:8001/"""
        """api/v1/administration/providers/fanvue/callback"}""",
        encoding="utf-8",
    )
    exchanged = {}

    class OAuth:
        def __init__(self, account_id, redirect_uri):
            exchanged.update(account_id=account_id, redirect_uri=redirect_uri)

        def exchange_code_for_tokens(self, code, code_verifier):
            exchanged.update(code=code, code_verifier=code_verifier)
            return {"success": True}

    monkeypatch.setattr(callback_server, "REACT_OAUTH_SESSION_FILE", session_file)
    monkeypatch.setattr(callback_server, "FanvueOAuthService", OAuth)
    monkeypatch.setenv("CREATOR_OS_REACT_URL", "http://localhost:5174")
    response = TestClient(callback_server.app).get(
        "/api/v1/administration/providers/fanvue/callback"
        "?code=authorization-code&state=expected",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://localhost:5174/administration/providers?fanvue=connected"
    )
    assert exchanged == {
        "account_id": 2,
        "redirect_uri": (
            "http://localhost:8001/api/v1/administration/providers/fanvue/callback"
        ),
        "code": "authorization-code",
        "code_verifier": "verifier",
    }
    assert not session_file.exists()


def test_react_callback_rejects_invalid_state_without_exchanging(monkeypatch, tmp_path):
    session_file = tmp_path / "oauth.json"
    session_file.write_text(
        '{"flow":"react_administration","state":"expected"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(callback_server, "REACT_OAUTH_SESSION_FILE", session_file)
    monkeypatch.setattr(
        callback_server,
        "FanvueOAuthService",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Token exchange must not run")
        ),
    )
    response = TestClient(callback_server.app).get(
        "/api/v1/administration/providers/fanvue/callback"
        "?code=authorization-code&state=wrong",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"].endswith(
        "/administration/providers?fanvue=state_error"
    )
    assert session_file.exists()


def test_legacy_callback_still_routes_to_streamlit():
    response = TestClient(callback_server.app).get(
        "/callback?code=legacy-code&state=legacy-state",
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://localhost:8501?code=legacy-code&state=legacy-state"
    )

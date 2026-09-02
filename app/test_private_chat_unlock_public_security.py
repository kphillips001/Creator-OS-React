import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import private_chat_unlock
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
)
from app.services.unlock_token_log_filter import (
    UnlockTokenLogFilter,
    install_unlock_token_log_redaction,
)


def _client(monkeypatch, resolver):
    monkeypatch.setattr(
        private_chat_unlock,
        "PrivateChatUnlockGatewayService",
        lambda: SimpleNamespace(resolve=resolver),
    )
    application = FastAPI()
    application.include_router(private_chat_unlock.router)
    application.include_router(private_chat_unlock.public_alias_router)
    return TestClient(application)


def test_public_unlock_error_is_generic_and_never_cached(monkeypatch):
    def fail(_token):
        raise UnlockUnavailableError("Offering is no longer eligible.")

    response = _client(monkeypatch, fail).get(
        "/api/v1/commerce/unlock/" + "a" * 64
    )
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "detail": "This Unlock link is unavailable. Please return to Telegram and try again."
    }
    assert "Offering" not in response.text


def test_public_unlock_redirect_is_never_cached(monkeypatch):
    response = _client(
        monkeypatch, lambda _token: "https://www.fanvue.com/example"
    ).get("/api/v1/commerce/unlock/" + "a" * 64, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["location"] == "https://www.fanvue.com/example"


def test_public_alias_error_is_generic_and_never_cached(monkeypatch):
    monkeypatch.setattr(
        private_chat_unlock,
        "PrivateChatUnlockGatewayService",
        lambda: SimpleNamespace(resolve_alias=lambda _alias: (_ for _ in ()).throw(
            UnlockUnavailableError("sensitive alias detail")
        )),
    )
    application = FastAPI()
    application.include_router(private_chat_unlock.public_alias_router)
    response = TestClient(application).get("/u/" + "a" * 22)
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    assert "sensitive" not in response.text


@pytest.mark.parametrize(
    "destination",
    [
        "http://www.fanvue.com/example",
        "https://localhost/example",
        "https://127.0.0.1/example",
        "https://fanvue.example/example",
        "https://www.fanvue.com:444/example",
        "not-a-url",
    ],
)
def test_final_redirect_rejects_unsafe_destination(destination):
    with pytest.raises(UnlockUnavailableError, match="security validation"):
        PrivateChatUnlockGatewayService._validated_fanvue_destination(destination)


@pytest.mark.parametrize(
    "destination",
    ["https://fanvue.com/example", "https://www.fanvue.com/example"],
)
def test_final_redirect_accepts_authoritative_fanvue_https(destination):
    assert (
        PrivateChatUnlockGatewayService._validated_fanvue_destination(destination)
        == destination
    )


def test_uvicorn_access_log_filter_redacts_entire_unlock_token():
    token = "a" * 64
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", f"/api/v1/commerce/unlock/{token}", "1.1", 409),
        None,
    )
    assert UnlockTokenLogFilter().filter(record) is True
    rendered = record.getMessage()
    assert token not in rendered
    assert "/api/v1/commerce/unlock/<redacted>" in rendered


def test_uvicorn_access_log_filter_redacts_entire_public_alias():
    alias = "a" * 22
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1", "GET", f"/u/{alias}", "1.1", 409), None,
    )
    UnlockTokenLogFilter().filter(record)
    rendered = record.getMessage()
    assert alias not in rendered
    assert "/u/<redacted>" in rendered


def test_redaction_filter_is_installed_on_uvicorn_access_handlers():
    logger = logging.getLogger("uvicorn.access")
    handler = logging.NullHandler()
    logger.addHandler(handler)
    try:
        install_unlock_token_log_redaction()
        assert any(isinstance(item, UnlockTokenLogFilter) for item in handler.filters)
    finally:
        logger.removeHandler(handler)

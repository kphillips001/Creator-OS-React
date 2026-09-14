import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.providers.social.telegram_provider import TelegramPublishResult
from tools.post_main_channel_chat_cta import (
    BUTTON_TEXT,
    DESTINATION_AUTHORITY,
    MESSAGE,
    execute,
)


CHAT_URL = "https://t.me/avablackthorne"
MAIN_URL = "https://t.me/+private-main"


class Http:
    def __init__(self, *, main_id="-100123"):
        self.main_id = main_id
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        payload = {"ok": True, "result": {
            "id": self.main_id,
            "type": "channel",
            "title": "Ava Main Channel",
            "invite_link": MAIN_URL,
        }}
        return SimpleNamespace(ok=True, json=lambda: payload)


class Provider:
    def __init__(self, *, chat_url=CHAT_URL, delivered_chat="-100123"):
        self.calls = []
        self.config = {
            "bot_token": "secret-token",
            "main_chat_id": "-100123",
            "main_channel_url": MAIN_URL,
            "chat_url": chat_url,
            "dmgate_url": CHAT_URL,
        }
        self.delivered_chat = delivered_chat

    def load_telegram_env(self):
        return self.config

    def publish(self, **kwargs):
        self.calls.append(kwargs)
        keyboard = {"inline_keyboard": [[{"text": BUTTON_TEXT, "url": CHAT_URL}]]}
        return TelegramPublishResult(
            success=True,
            post_to="main",
            provider_post_id="44",
            metadata={"response": {"result": {
                "message_id": 44,
                "chat": {"id": self.delivered_chat},
                "text": MESSAGE,
                "reply_markup": keyboard,
            }}},
        )


def test_exact_main_channel_post_uses_canonical_chat_url_and_one_button(tmp_path):
    provider = Provider()
    result = execute(
        provider=provider,
        http_client=Http(),
        marker=tmp_path / "marker.json",
        now=lambda: datetime(2026, 9, 12, tzinfo=timezone.utc),
    )
    assert result["status"] == "PUBLISHED"
    assert provider.calls == [{
        "image_reference": None,
        "caption": "Want to talk? 💋",
        "post_to": "main",
        "cta_enabled": True,
        "cta_label": "💬 Come Chat!",
        "cta_url": CHAT_URL,
    }]
    assert result["destination_authority"] == "TELEGRAM_CHAT_URL"


@pytest.mark.parametrize("chat_url", ("", "https://", "https://example.com/chat"))
def test_invalid_chat_url_fails_closed_before_publish(tmp_path, chat_url):
    provider = Provider(chat_url=chat_url)
    with pytest.raises(RuntimeError):
        execute(provider=provider, http_client=Http(), marker=tmp_path / "marker.json")
    assert provider.calls == []


def test_ambiguous_private_chat_authorities_fail_closed(tmp_path):
    provider = Provider()
    provider.config["dmgate_url"] = "https://t.me/another-destination"
    with pytest.raises(RuntimeError, match="ambiguous"):
        execute(provider=provider, http_client=Http(), marker=tmp_path / "marker.json")
    assert provider.calls == []


def test_wrong_main_channel_identity_fails_closed(tmp_path):
    provider = Provider()
    with pytest.raises(RuntimeError, match="wrong Main Channel"):
        execute(provider=provider, http_client=Http(main_id="-100999"), marker=tmp_path / "marker.json")
    assert provider.calls == []


def test_second_execution_is_idempotently_skipped_and_marker_has_no_secrets(tmp_path):
    marker = tmp_path / "marker.json"
    first = Provider()
    execute(provider=first, http_client=Http(), marker=marker)
    second = Provider()
    result = execute(provider=second, http_client=Http(), marker=marker)
    assert result["status"] == "ALREADY_PUBLISHED"
    assert second.calls == []
    persisted = json.loads(marker.read_text(encoding="utf-8"))
    assert persisted["message"] == MESSAGE
    assert persisted["button_text"] == BUTTON_TEXT
    assert persisted["destination_authority"] == DESTINATION_AUTHORITY
    serialized = json.dumps(persisted)
    assert "secret-token" not in serialized
    assert "+private-main" not in serialized
    assert CHAT_URL not in serialized

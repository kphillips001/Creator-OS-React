"""One-off, idempotent Main Channel to private-chat CTA post."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.providers.social.telegram_provider import (
    TelegramPublishError,
    TelegramPublishingProvider,
)


MESSAGE = "Want to talk? 💋"
BUTTON_TEXT = "💬 Come Chat!"
DESTINATION_AUTHORITY = "TELEGRAM_CHAT_URL"
MARKER = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "one_off_telegram"
    / "main_channel_chat_cta.json"
)


def _chat(http_client, bot_token: str, chat_id: str) -> dict:
    response = http_client.get(
        f"https://api.telegram.org/bot{bot_token}/getChat",
        params={"chat_id": chat_id},
        timeout=20,
    )
    payload = response.json()
    if not response.ok or payload.get("ok") is not True:
        raise RuntimeError("Telegram could not verify the configured Main Channel.")
    return dict(payload.get("result") or {})


def _validate_marker(marker: Path) -> dict | None:
    if not marker.exists():
        return None
    prior = json.loads(marker.read_text(encoding="utf-8"))
    expected = {
        "message": MESSAGE,
        "button_text": BUTTON_TEXT,
        "destination_authority": DESTINATION_AUTHORITY,
    }
    if any(prior.get(key) != value for key, value in expected.items()):
        raise RuntimeError("The existing Main Channel CTA marker is inconsistent; refusing to publish.")
    if not str(prior.get("message_id") or "").isdigit():
        raise RuntimeError("The existing Main Channel CTA marker lacks a confirmed message ID.")
    return prior


def _validate_config(config: dict[str, str], http_client) -> tuple[dict, dict]:
    required = ("bot_token", "main_chat_id", "main_channel_url", "chat_url")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"Missing Telegram configuration: {', '.join(missing)}")

    chat_url = str(config["chat_url"]).strip()
    if not TelegramPublishingProvider.valid_cta_url(chat_url):
        raise RuntimeError("Configured TELEGRAM_CHAT_URL is invalid.")
    parsed = urlparse(chat_url)
    if parsed.scheme != "https" or parsed.netloc.lower() not in {"t.me", "www.t.me"}:
        raise RuntimeError("TELEGRAM_CHAT_URL must be an HTTPS Telegram destination.")
    dmgate_url = str(config.get("dmgate_url") or "").strip()
    if dmgate_url and dmgate_url.rstrip("/") != chat_url.rstrip("/"):
        raise RuntimeError("Configured private-chat destinations are ambiguous; refusing to publish.")

    main = _chat(http_client, config["bot_token"], str(config["main_chat_id"]))
    if str(main.get("id")) != str(config["main_chat_id"]):
        raise RuntimeError("Telegram returned the wrong Main Channel identity.")
    if str(main.get("type") or "") != "channel":
        raise RuntimeError("Configured Main Channel is not a Telegram channel.")
    if str(main.get("invite_link") or "") != str(config["main_channel_url"]):
        raise RuntimeError("Configured Main Channel URL does not match Telegram's verified channel invite.")

    keyboard = TelegramPublishingProvider.build_inline_keyboard(
        cta_enabled=True,
        cta_label=BUTTON_TEXT,
        cta_url=chat_url,
    )
    return main, dict(keyboard or {})


def execute(
    *, provider: TelegramPublishingProvider | None = None,
    http_client=None,
    marker: Path = MARKER,
    now=None,
) -> dict:
    prior = _validate_marker(marker)
    if prior is not None:
        return {"status": "ALREADY_PUBLISHED", **prior}

    telegram = provider or TelegramPublishingProvider()
    http = http_client or requests
    config = telegram.load_telegram_env()
    main, keyboard = _validate_config(config, http)

    print("AVA'S MAIN CHANNEL")
    print()
    print(MESSAGE)
    print()
    print(f"[ {BUTTON_TEXT} ]")
    print()
    print(f"Destination authority: {DESTINATION_AUTHORITY}")
    print("No other post or channel will be modified.")

    result = telegram.publish(
        image_reference=None,
        caption=MESSAGE,
        post_to="main",
        cta_enabled=True,
        cta_label=BUTTON_TEXT,
        cta_url=config["chat_url"],
    )
    response = dict(result.metadata.get("response") or {})
    delivered = dict(response.get("result") or {})
    actual_keyboard = delivered.get("reply_markup")
    if (
        not result.success
        or not str(result.provider_post_id or "").isdigit()
        or str((delivered.get("chat") or {}).get("id")) != str(main["id"])
        or str(delivered.get("message_id")) != str(result.provider_post_id)
        or delivered.get("text") != MESSAGE
        or actual_keyboard != keyboard
    ):
        raise TelegramPublishError(
            "Telegram did not confirm the exact Main Channel message and keyboard."
        )

    evidence = {
        "channel_id": str(main["id"]),
        "message_id": str(result.provider_post_id),
        "message": MESSAGE,
        "button_text": BUTTON_TEXT,
        "button_type": "URL",
        "destination_authority": DESTINATION_AUTHORITY,
        "published_at": (now or (lambda: datetime.now(timezone.utc)))().isoformat(),
    }
    marker.parent.mkdir(parents=True, exist_ok=True)
    temporary = marker.with_suffix(".tmp")
    temporary.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(marker)
    return {"status": "PUBLISHED", **evidence}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    result = execute()
    if result["status"] == "ALREADY_PUBLISHED":
        print(
            "NOT SENT: this one-off message was already confirmed as "
            f"Telegram message_id={result['message_id']}."
        )
        return 2
    print(f"PUBLISHED: Telegram message_id={result['message_id']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

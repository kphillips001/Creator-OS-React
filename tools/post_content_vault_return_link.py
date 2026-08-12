"""One-off, idempotent Content Vault navigation post."""

from __future__ import annotations

import json
from pathlib import Path

import requests

from app.providers.social.telegram_provider import TelegramPublishingProvider


MESSAGE = "📣 Back to Ava's Main Channel"
BUTTON_TEXT = "Return"
MARKER = Path(__file__).resolve().parents[1] / "data" / "one_off_telegram" / "content_vault_return_link.json"


def _chat(bot_token: str, chat_id: str) -> dict:
    response = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getChat",
        params={"chat_id": chat_id},
        timeout=20,
    )
    payload = response.json()
    if not response.ok or payload.get("ok") is not True:
        raise RuntimeError("Telegram could not verify a configured channel.")
    return dict(payload.get("result") or {})


def main() -> int:
    if MARKER.exists():
        prior = json.loads(MARKER.read_text(encoding="utf-8"))
        print(
            "NOT SENT: this one-off message was already delivered "
            f"as Telegram message_id={prior.get('message_id')}."
        )
        return 2

    config = TelegramPublishingProvider.load_telegram_env()
    required = ("bot_token", "vault_chat_id", "main_chat_id", "main_channel_url")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(f"Missing Telegram configuration: {', '.join(missing)}")
    if config["vault_chat_id"] == config["main_chat_id"]:
        raise RuntimeError("Content Vault and Main Broadcast resolve to the same chat ID; refusing to send.")

    vault = _chat(config["bot_token"], config["vault_chat_id"])
    main_chat = _chat(config["bot_token"], config["main_chat_id"])
    if str(vault.get("id")) != config["vault_chat_id"] or "content vault" not in str(vault.get("title") or "").lower():
        raise RuntimeError("Configured Content Vault ID did not verify as Ava's Content Vault; refusing to send.")
    if str(main_chat.get("id")) != config["main_chat_id"]:
        raise RuntimeError("Configured Main Broadcast ID did not verify; refusing to send.")
    if str(main_chat.get("invite_link") or "") != config["main_channel_url"]:
        raise RuntimeError("Configured Main Broadcast URL does not match Telegram's verified channel invite; refusing to send.")

    print(f"Content Vault destination: {config['vault_chat_id']} ({vault.get('title')})")
    print(f"Main Broadcast URL: {config['main_channel_url']}")
    print(f"Message: {MESSAGE}")
    print(f"Button: {BUTTON_TEXT}")
    print(f"Button URL: {config['main_channel_url']}")

    result = TelegramPublishingProvider().publish(
        image_reference=None,
        caption=MESSAGE,
        post_to="vault",
        cta_enabled=True,
        cta_label=BUTTON_TEXT,
        cta_url=config["main_channel_url"],
    )
    if not result.success or not result.provider_post_id:
        raise RuntimeError("Telegram did not confirm successful delivery with a message ID.")

    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(json.dumps({
        "chat_id": config["vault_chat_id"],
        "message_id": result.provider_post_id,
        "message": MESSAGE,
        "button_text": BUTTON_TEXT,
        "button_url": config["main_channel_url"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Telegram chat_id: {config['vault_chat_id']}")
    print(f"Telegram message_id: {result.provider_post_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

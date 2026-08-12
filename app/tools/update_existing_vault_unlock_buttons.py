"""One-off migration for existing Telegram Content Vault unlock keyboards.

Dry-run is the default. Pass ``--execute`` to edit eligible messages in place.
This utility intentionally does not modify Creator_OS publishing persistence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row

from app.providers.social.telegram_provider import TelegramPublishingProvider


ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = ROOT / "data" / "social_publishing" / "social_queue.json"
HISTORY_PATH = ROOT / "data" / "social_publishing" / "social_history.json"
TELEGRAM_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Target:
    message_id: int
    offering_id: UUID
    publication_id: UUID
    price_minor: int
    currency: str
    unlock_url: str
    destination: str

    @property
    def price_label(self) -> str:
        symbols = {"USD": "$", "EUR": "€", "GBP": "£"}
        prefix = symbols.get(self.currency, f"{self.currency} ")
        return f"{prefix}{self.price_minor / 100:.2f}"

    @property
    def old_text(self) -> str:
        return f"Unlock Now · {self.price_label}"

    @property
    def new_text(self) -> str:
        return f"🔓 Unlock · {self.price_label}"


def _read_json(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError(f"Expected a JSON list: {path}")
    return value


def _posted_vault_candidates() -> list[dict[str, Any]]:
    queue = _read_json(QUEUE_PATH)
    history = _read_json(HISTORY_PATH)
    candidates: list[dict[str, Any]] = []
    for item in queue:
        source = str(item.get("generated_image_id") or "")
        if (
            item.get("platform") != "telegram"
            or item.get("status") != "posted"
            or not source.startswith("commercial-offering:")
        ):
            continue
        posted = [
            event
            for event in history
            if event.get("queue_item_id") == item.get("queue_item_id")
            and event.get("status") == "posted"
        ]
        if not posted:
            candidates.append({"skip": "posted queue item has no posted history", "item": item})
            continue
        metadata = dict(posted[0].get("metadata") or {})
        if metadata.get("telegram_destination") != "vault" or metadata.get("telegram_post_to") != "vault":
            continue
        candidates.append({"item": item, "metadata": metadata})
    return candidates


def resolve_targets(database_url: str) -> tuple[list[Target], list[str]]:
    candidates = _posted_vault_candidates()
    targets: list[Target] = []
    skipped: list[str] = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for candidate in candidates:
            if candidate.get("skip"):
                skipped.append(str(candidate["skip"]))
                continue
            metadata = candidate["metadata"]
            source = str(candidate["item"].get("generated_image_id") or "")
            try:
                offering_id = UUID(source.removeprefix("commercial-offering:"))
                publication_id = UUID(str(metadata.get("fanvue_publication_id") or ""))
                message_id = int(metadata.get("provider_post_id"))
            except (TypeError, ValueError) as error:
                skipped.append(f"{source}: invalid offering/publication/message identifier ({error})")
                continue
            row = connection.execute(
                """
                SELECT cp.publication_id, cp.commercial_offering_id, cp.provider,
                       cp.status, cp.provider_resource_status, cp.publication_metadata,
                       co.status AS offering_status, co.price_minor, co.currency
                  FROM commercial_publications cp
                  JOIN commercial_offerings co
                    ON co.offering_id = cp.commercial_offering_id
                 WHERE cp.publication_id = %s
                   AND cp.commercial_offering_id = %s
                """,
                (publication_id, offering_id),
            ).fetchone()
            if row is None:
                skipped.append(f"message {message_id}: commercial publication was not found")
                continue
            reasons: list[str] = []
            if row["provider"] != "FANVUE": reasons.append("provider is not FANVUE")
            if row["status"] != "LIVE": reasons.append("publication is not LIVE")
            if row["provider_resource_status"] != "PRESENT": reasons.append("provider resource is not PRESENT")
            if row["offering_status"] != "READY": reasons.append("offering is not READY")
            if row["price_minor"] is None or int(row["price_minor"]) <= 0: reasons.append("canonical price is missing")
            currency = str(row["currency"] or "").strip().upper()
            if not currency: reasons.append("canonical currency is missing")
            publication_metadata = dict(row["publication_metadata"] or {})
            media_link = publication_metadata.get("media_link") or {}
            unlock_url = str(media_link.get("url") or "").strip() if isinstance(media_link, dict) else ""
            if not unlock_url.startswith(("https://", "http://")): reasons.append("persisted Fanvue Media Link URL is missing")
            if reasons:
                skipped.append(f"message {message_id}: {', '.join(reasons)}")
                continue
            targets.append(Target(
                message_id=message_id,
                offering_id=offering_id,
                publication_id=publication_id,
                price_minor=int(row["price_minor"]),
                currency=currency,
                unlock_url=unlock_url,
                destination="Ava Content Vault (persisted vault + configured vault chat)",
            ))
        connection.rollback()
    return sorted(targets, key=lambda item: item.message_id), skipped


def print_dry_run(targets: list[Target], skipped: list[str], vault_chat_id: str) -> None:
    print(f"Content Vault destination: {vault_chat_id}")
    print("message_id | offering / publication | price | existing button | existing URL | proposed button | destination")
    for item in targets:
        print(
            f"{item.message_id} | {item.offering_id} / {item.publication_id} | "
            f"{item.price_label} | {item.old_text} | {item.unlock_url} | "
            f"{item.new_text} | {item.destination}"
        )
    for reason in skipped:
        print(f"SKIPPED | {reason}")


def edit_keyboard(target: Target, *, bot_token: str, chat_id: str) -> tuple[str, str]:
    response = requests.post(
        f"https://api.telegram.org/bot{bot_token}/editMessageReplyMarkup",
        data={
            "chat_id": chat_id,
            "message_id": target.message_id,
            "reply_markup": json.dumps({
                "inline_keyboard": [[{"text": target.new_text, "url": target.unlock_url}]]
            }, ensure_ascii=False),
        },
        timeout=TELEGRAM_TIMEOUT_SECONDS,
    )
    try:
        payload = response.json()
    except ValueError:
        return "FAILED", f"HTTP {response.status_code}: non-JSON Telegram response"
    if payload.get("ok") is True:
        result = payload.get("result") or {}
        keyboard = ((result.get("reply_markup") or {}).get("inline_keyboard") or [])
        button = keyboard[0][0] if keyboard and keyboard[0] else {}
        if button.get("text") != target.new_text or button.get("url") != target.unlock_url:
            return "FAILED", "Telegram returned success but the resulting keyboard did not match"
        return "UPDATED", "Telegram returned success; URL preserved"
    description = str(payload.get("description") or "Telegram edit failed")
    if response.status_code == 400 and "message is not modified" in description.lower():
        return "ALREADY CORRECT", "Telegram reports the requested keyboard is already present"
    return "FAILED", f"HTTP {response.status_code}: {description}"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="Perform in-place Telegram keyboard edits")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    config = TelegramPublishingProvider.load_telegram_env()
    bot_token = str(config.get("bot_token") or "").strip()
    vault_chat_id = str(config.get("vault_chat_id") or "").strip()
    if not database_url or not bot_token or not vault_chat_id:
        raise RuntimeError("DATABASE_URL, Telegram bot token, and Content Vault chat ID are required")
    targets, skipped = resolve_targets(database_url)
    print("DRY RUN")
    print_dry_run(targets, skipped, vault_chat_id)
    if not args.execute:
        print(f"TOTAL ELIGIBLE: {len(targets)}\nSKIPPED: {len(skipped)}\nNo Telegram changes made.")
        return 0
    print("EXECUTION")
    counts = {"UPDATED": 0, "ALREADY CORRECT": 0, "FAILED": 0}
    for target in targets:
        status, detail = edit_keyboard(target, bot_token=bot_token, chat_id=vault_chat_id)
        counts[status] += 1
        print(
            f"message {target.message_id}: {status} | {target.old_text} -> {target.new_text} | "
            f"URL unchanged: {target.unlock_url} | {detail}"
        )
    print("FINAL")
    print(f"TOTAL ELIGIBLE: {len(targets)}")
    print(f"UPDATED: {counts['UPDATED']}")
    print(f"ALREADY CORRECT: {counts['ALREADY CORRECT']}")
    print(f"SKIPPED: {len(skipped)}")
    print(f"FAILED: {counts['FAILED']}")
    return 1 if counts["FAILED"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

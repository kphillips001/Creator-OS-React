"""Add canonical content-type hashtags to existing Telegram Content Vault posts.

Dry-run is the default. ``--execute --canary-only`` updates one explicitly
selected non-pinned commercial post. ``--execute`` updates every eligible post
in place with editMessageCaption; media and publication persistence are untouched.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html import escape
import json
import os
from pathlib import Path
import sys
from typing import Any
from uuid import UUID

import psycopg
import requests
from dotenv import load_dotenv
from psycopg.rows import dict_row

from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.services.commerce_telegram_vault_service import CommerceTelegramVaultService


ROOT = Path(__file__).resolve().parents[2]
QUEUE_PATH = ROOT / "data" / "social_publishing" / "social_queue.json"
HISTORY_PATH = ROOT / "data" / "social_publishing" / "social_history.json"
TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Target:
    message_id: int
    offering_id: UUID
    publication_id: UUID
    content_type: str
    caption: str
    hashtag: str
    price_minor: int
    currency: str
    unlock_url: str

    @property
    def updated_caption(self) -> str:
        return CommerceTelegramVaultService.caption_with_content_type_hashtag(
            self.caption, self.hashtag
        )

    @property
    def keyboard(self) -> dict[str, Any]:
        return {"inline_keyboard": [[{
            "text": CommerceTelegramVaultService.unlock_cta_label(
                self.price_minor, self.currency
            ),
            "url": self.unlock_url,
        }]]}


def _json_list(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise RuntimeError(f"Expected JSON list: {path}")
    return value


def _posted_candidates() -> list[dict[str, Any]]:
    queue = _json_list(QUEUE_PATH)
    history = _json_list(HISTORY_PATH)
    candidates = []
    for item in queue:
        source = str(item.get("generated_image_id") or "")
        if (item.get("platform") != "telegram" or item.get("status") != "posted"
                or not source.startswith("commercial-offering:")):
            continue
        event = next((entry for entry in history
            if entry.get("queue_item_id") == item.get("queue_item_id")
            and entry.get("status") == "posted"
            and (entry.get("metadata") or {}).get("telegram_destination") == "vault"
            and (entry.get("metadata") or {}).get("telegram_post_to") == "vault"), None)
        if event:
            candidates.append({"item": item, "metadata": dict(event.get("metadata") or {})})
    return candidates


def _canonical_type(row: dict[str, Any]) -> tuple[str, str] | None:
    if row["offering_type"] == "SINGLE_IMAGE":
        return "SINGLE_IMAGE", "#Photos"
    if row["offering_type"] == "VIDEO":
        return "VIDEO", "#Videos"
    if row["offering_type"] == "PHOTOSET":
        return "PHOTOSHOOT", "#Photoshoots"
    if row["offering_type"] == "BUNDLE" and row["source_photoshoot_deliverable_id"]:
        return "PHOTOSHOOT", "#Photoshoots"
    return None


def resolve_targets(database_url: str) -> tuple[list[Target], list[str]]:
    targets: list[Target] = []
    skipped: list[str] = []
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        connection.execute("SET TRANSACTION READ ONLY")
        for candidate in _posted_candidates():
            metadata = candidate["metadata"]
            source = str(candidate["item"].get("generated_image_id") or "")
            try:
                offering_id = UUID(source.removeprefix("commercial-offering:"))
                publication_id = UUID(str(metadata.get("fanvue_publication_id") or ""))
                message_id = int(metadata.get("provider_post_id"))
            except (TypeError, ValueError) as error:
                skipped.append(f"{source}: invalid canonical identifiers ({error})")
                continue
            row = connection.execute("""
                SELECT o.offering_id,o.offering_type,o.source_photoshoot_deliverable_id,
                       o.source_bundle_studio_bundle_id,o.price_minor,o.currency,o.status,
                       p.publication_id,p.status AS publication_status,
                       p.provider_resource_status,p.publication_metadata
                  FROM commercial_offerings o
                  JOIN commercial_publications p
                    ON p.commercial_offering_id=o.offering_id AND p.provider='FANVUE'
                 WHERE o.offering_id=%s AND p.publication_id=%s
            """, (offering_id, publication_id)).fetchone()
            if not row:
                skipped.append(f"message {message_id}: canonical offering/publication missing")
                continue
            canonical = _canonical_type(row)
            publication_metadata = dict(row["publication_metadata"] or {})
            draft = publication_metadata.get("content_vault_caption_draft") or {}
            media_link = publication_metadata.get("media_link") or {}
            caption = str(draft.get("text") or "").strip() if isinstance(draft, dict) else ""
            audit_caption = str(metadata.get("caption") or "").strip()
            url = str(media_link.get("url") or "").strip() if isinstance(media_link, dict) else ""
            reasons = []
            if not canonical: reasons.append("unsupported canonical content type")
            if row["status"] != "READY": reasons.append("offering is not READY")
            if row["publication_status"] != "LIVE": reasons.append("Fanvue publication is not LIVE")
            if row["provider_resource_status"] != "PRESENT": reasons.append("Fanvue resource is not PRESENT")
            if not caption: reasons.append("persisted caption is missing")
            if audit_caption and audit_caption != caption: reasons.append("publication audit caption differs from persisted caption")
            if row["price_minor"] is None or int(row["price_minor"]) <= 0: reasons.append("price is missing")
            if not str(row["currency"] or "").strip(): reasons.append("currency is missing")
            if not url.startswith(("https://", "http://")): reasons.append("Fanvue Media Link is missing")
            if reasons:
                skipped.append(f"message {message_id}: {', '.join(reasons)}")
                continue
            content_type, hashtag = canonical
            targets.append(Target(
                message_id=message_id, offering_id=offering_id,
                publication_id=publication_id, content_type=content_type,
                caption=caption, hashtag=hashtag, price_minor=int(row["price_minor"]),
                currency=str(row["currency"]).strip().upper(), unlock_url=url,
            ))
        connection.rollback()
    return sorted(targets, key=lambda item: item.message_id), skipped


def pinned_message_id(bot_token: str, chat_id: str) -> int | None:
    response = requests.get(
        f"https://api.telegram.org/bot{bot_token}/getChat",
        params={"chat_id": chat_id}, timeout=TIMEOUT_SECONDS,
    )
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(f"Unable to verify pinned Vault message: {payload.get('description')}")
    value = ((payload.get("result") or {}).get("pinned_message") or {}).get("message_id")
    return int(value) if value is not None else None


def ensure_pinned_excluded(targets: list[Target], pinned: int | None) -> None:
    if pinned is not None and any(item.message_id == pinned for item in targets):
        raise RuntimeError("Pinned Content Vault message resolved as a commercial migration target")


def edit_target(target: Target, provider: TelegramPublishingProvider, chat_id: str) -> tuple[str, str]:
    result = provider.edit_message_caption(
        chat_id=chat_id, message_id=target.message_id,
        caption=escape(target.updated_caption), reply_markup=target.keyboard,
    )
    if result.get("ok"):
        if int(result.get("message_id") or 0) != target.message_id:
            return "FAILED", "Telegram returned a different message ID"
        if result.get("caption") != target.updated_caption:
            return "FAILED", "Telegram returned an unexpected caption"
        if result.get("reply_markup") != target.keyboard:
            return "FAILED", "Telegram returned an unexpected Unlock keyboard"
        entities = result.get("caption_entities") or []
        if not any(item.get("type") == "hashtag" for item in entities if isinstance(item, dict)):
            return "FAILED", "Telegram did not classify the category as a hashtag entity"
        return "UPDATED", "message ID and Unlock keyboard preserved; Telegram hashtag entity confirmed"
    error = str(result.get("error") or "Telegram edit failed")
    if "message is not modified" in error.lower():
        return "ALREADY_CORRECT", error
    return "FAILED", error


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--canary-only", action="store_true")
    parser.add_argument("--canary-message-id", type=int)
    args = parser.parse_args()
    if args.canary_only and (not args.execute or args.canary_message_id is None):
        parser.error("--canary-only requires --execute and --canary-message-id")
    load_dotenv(ROOT / ".env")
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    config = TelegramPublishingProvider.load_telegram_env()
    token = str(config.get("bot_token") or "").strip()
    chat_id = str(config.get("vault_chat_id") or "").strip()
    if not database_url or not token or not chat_id:
        raise RuntimeError("Database and Content Vault Telegram configuration are required")
    targets, skipped = resolve_targets(database_url)
    pinned = pinned_message_id(token, chat_id)
    ensure_pinned_excluded(targets, pinned)
    print(f"Content Vault destination: {chat_id}")
    print(f"Pinned message excluded: {pinned}")
    print(f"Eligible: {len(targets)} | Skipped: {len(skipped)}")
    for item in targets:
        print(f"message {item.message_id}: {item.content_type} -> {item.hashtag}")
    for reason in skipped:
        print(f"SKIPPED: {reason}")
    if not args.execute:
        print("DRY RUN: no Telegram changes made")
        return 0
    if args.canary_only:
        targets = [item for item in targets if item.message_id == args.canary_message_id]
        if len(targets) != 1:
            raise RuntimeError("Requested canary is not one eligible canonical publication")
    provider = TelegramPublishingProvider()
    failed = 0
    for item in targets:
        status, detail = edit_target(item, provider, chat_id)
        print(f"message {item.message_id}: {status} | {detail}")
        failed += status == "FAILED"
        if args.canary_only and failed:
            print("CANARY FAILED: broad migration was not attempted")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

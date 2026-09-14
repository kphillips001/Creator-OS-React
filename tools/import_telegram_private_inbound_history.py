"""One-time bounded Telegram history ledger import. Never generates or sends."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from dotenv import load_dotenv
from telethon import TelegramClient

from app.database import get_db_connection
from app.services.telegram_private_inbound_backlog_service import TelegramPrivateInboundBacklogService


def parse(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None: raise ValueError("timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def media_types(message) -> tuple[str, ...]:
    values = []
    if getattr(message, "photo", None): values.append("photo")
    document = getattr(message, "document", None)
    if document:
        mime = str(getattr(document, "mime_type", "") or "")
        values.append("video" if mime.startswith("video/") else "audio" if mime.startswith("audio/") else "document")
    if getattr(message, "sticker", None): values.append("sticker")
    return tuple(sorted(set(values)))


def safe_controls() -> None:
    config = json.loads(Path("data/config/behavior_config.json").read_text(encoding="utf-8"))
    if config.get("global_automation_enabled") or config.get("global_sends_enabled"):
        raise RuntimeError("Import blocked: automation and Global Sends must both be off.")


async def run(args) -> dict:
    safe_controls()
    start, end = parse(args.start), parse(args.end)
    if end <= start: raise ValueError("end must be after start")
    targets = tuple(dict.fromkeys(int(item) for item in args.chat_ids.split(",") if item.strip()))
    if not targets or len(targets) > 25: raise ValueError("1-25 explicit chat IDs are required")
    service = TelegramPrivateInboundBacklogService()
    manifest = {"importId": str(uuid4()), "executedAt": datetime.now(timezone.utc).isoformat(),
        "startUtc": start.isoformat(), "endUtc": end.isoformat(), "targetChatIds": list(targets),
        "messagesInspected": 0, "customerInboundsFound": 0, "inserted": 0, "deduplicated": 0,
        "skippedOutbound": 0, "mediaMetadataOnly": 0, "failures": [], "paginationRequestEstimate": 0,
        "perConversation": {}}
    client = TelegramClient(args.session, int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
    await client.connect()
    if not await client.is_user_authorized(): raise RuntimeError("Cloned Telegram session is not authorized")
    try:
        for chat_id in targets:
            inspected = 0; found = []; truncated = False
            try:
                async for message in client.iter_messages(chat_id, limit=args.max_messages, offset_date=end):
                    inspected += 1
                    when = message.date.astimezone(timezone.utc)
                    if when < start: break
                    if when >= end: continue
                    manifest["messagesInspected"] += 1
                    if message.out:
                        manifest["skippedOutbound"] += 1; continue
                    found.append(message)
                if inspected >= args.max_messages and found and min(x.date for x in found).astimezone(timezone.utc) > start:
                    truncated = True
                    raise RuntimeError(f"bounded per-chat limit {args.max_messages} reached")
                manifest["paginationRequestEstimate"] += max(1, math.ceil(inspected / 100))
                inserted = deduped = media_count = 0
                for message in reversed(found):
                    kinds = media_types(message)
                    payload = SimpleNamespace(telegram_user_id=chat_id, telegram_chat_id=chat_id,
                        message_id=int(message.id), received_at=message.date.astimezone(timezone.utc),
                        message_text=str(message.message or ""),
                        attachments=tuple(SimpleNamespace(media_kind=kind) for kind in kinds))
                    _, created = service.capture(payload, account_scope="AVA_TELETHON_PRIVATE",
                        automation_state="OFF", provenance="HISTORICAL_TELETHON_IMPORT")
                    inserted += int(created); deduped += int(not created); media_count += int(bool(kinds))
                manifest["customerInboundsFound"] += len(found); manifest["inserted"] += inserted
                manifest["deduplicated"] += deduped; manifest["mediaMetadataOnly"] += media_count
                manifest["perConversation"][str(chat_id)] = {"inspected": inspected, "inbound": len(found),
                    "inserted": inserted, "deduplicated": deduped, "mediaMetadataOnly": media_count,
                    "truncated": truncated}
            except Exception as error:
                manifest["failures"].append({"chatId": chat_id, "error": type(error).__name__,
                    "detail": str(error)[:200]})
    finally:
        await client.disconnect()
    safe_controls()
    manifest_path = Path(args.manifest_dir) / f"{manifest['importId']}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["manifestPath"] = str(manifest_path.resolve())
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    load_dotenv(".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True); parser.add_argument("--end", required=True)
    parser.add_argument("--chat-ids", required=True); parser.add_argument("--session", required=True)
    parser.add_argument("--manifest-dir", default="data/backlog_imports")
    parser.add_argument("--max-messages", type=int, default=500)
    args = parser.parse_args()
    result = asyncio.run(run(args)); print(json.dumps(result))
    return 1 if result["failures"] else 0


if __name__ == "__main__": raise SystemExit(main())

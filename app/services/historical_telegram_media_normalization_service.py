"""Dry-run-first, in-place repair of historical noncanonical Telegram photos."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from PIL import Image

from app.providers.social.telegram_provider import TelegramPublishingProvider
from app.services.telegram_image_normalization_service import TelegramImageNormalizationService


@dataclass(frozen=True)
class HistoricalTelegramMediaCandidate:
    publish_request_id: str
    queue_item_id: str
    channel: str
    chat_id: str | None
    message_id: int | None
    existing_width: int
    existing_height: int
    source_asset_id: str | int | None
    source_path: str | None
    derivative_path: str | None
    expected_width: int | None
    expected_height: int | None
    editable: bool
    caption_available: bool
    keyboard_available: bool
    status: str
    reason: str


class HistoricalTelegramMediaNormalizationService:
    EVENT_TYPE = "HISTORICAL_MEDIA_NORMALIZATION"
    CANONICAL_SIZE = (960, 1280)

    def __init__(
        self, *, root: Path | None = None, telegram=None, normalizer=None,
    ) -> None:
        self.root = Path(root or Path(__file__).resolve().parents[2])
        self.social_dir = self.root / "data" / "social_publishing"
        self.items_path = self.social_dir / "social_publish_items.json"
        self.queue_path = self.social_dir / "social_queue.json"
        self.history_path = self.social_dir / "social_history.json"
        self.audit_path = self.social_dir / "telegram_historical_media_repairs.json"
        self.telegram = telegram or TelegramPublishingProvider()
        self.normalizer = normalizer or TelegramImageNormalizationService()

    def dry_run(self) -> tuple[HistoricalTelegramMediaCandidate, ...]:
        items = self._read(self.items_path)
        queues = {row.get("queue_item_id"): row for row in self._read(self.queue_path)}
        audited = {
            str(row.get("publish_request_id")): row
            for row in self._read(self.audit_path, missing_ok=True)
            if row.get("repair_status") == "REPAIRED"
        }
        results = []
        for item in items:
            candidate = self._candidate(item, queues.get(item.get("queue_item_id")), audited)
            if candidate is not None:
                results.append(candidate)
        return tuple(results)

    def execute(self) -> tuple[dict[str, Any], ...]:
        outcomes = []
        for candidate in self.dry_run():
            if candidate.status != "SAFE":
                continue
            item = self._item(candidate.publish_request_id)
            result_payload = self._provider_result(item)
            result = self.telegram.edit_message_media(
                chat_id=str(candidate.chat_id), message_id=int(candidate.message_id),
                image_path=str(candidate.source_path),
                caption=str(result_payload.get("caption") or ""),
                caption_entities=tuple(result_payload.get("caption_entities") or ()),
                reply_markup=result_payload.get("reply_markup"),
            )
            outcome = self._verify_result(candidate, result_payload, result)
            self._persist_outcome(candidate, outcome, result)
            outcomes.append(outcome)
        return tuple(outcomes)

    def _candidate(self, item, queue, audited):
        metadata = dict(item.get("metadata") or {})
        provider_result = self._provider_result(item)
        photos = provider_result.get("photo") or ()
        if item.get("platform") != "telegram" or item.get("status") != "posted" or not photos:
            return None
        largest = photos[-1]
        width, height = int(largest.get("width") or 0), int(largest.get("height") or 0)
        if (width, height) == self.CANONICAL_SIZE:
            return None
        publish_id = str(item.get("publish_request_id") or "")
        channel = str(metadata.get("telegram_post_to") or provider_result.get("post_to") or "unknown")
        chat = provider_result.get("chat") or provider_result.get("sender_chat") or {}
        chat_id = str(chat.get("id")) if chat.get("id") is not None else None
        message_id = provider_result.get("message_id")
        message_id = int(message_id) if isinstance(message_id, int) else None
        source = self._resolve_source(queue, channel)
        derivative = None
        expected = (None, None)
        reason = []
        if publish_id in audited:
            reason.append("repair audit already records REPAIRED")
        if source is None:
            reason.append("original Creator-OS source could not be resolved uniquely")
        else:
            try:
                presentation = self.normalizer.normalize(source)
                with Image.open(presentation.path) as image:
                    expected = image.size
                derivative = str(presentation.path)
                if expected != self.CANONICAL_SIZE:
                    reason.append(f"derivative is {expected[0]}x{expected[1]}, not 960x1280")
            except Exception as error:
                reason.append(f"normalization failed: {error}")
        caption_available = "caption" in provider_result
        keyboard_available = "reply_markup" in provider_result or not provider_result.get("reply_markup")
        editable = bool(chat_id and message_id and metadata.get("provider_post_id"))
        if not editable:
            reason.append("persisted bot-authored chat/message identity is incomplete")
        if not caption_available:
            reason.append("persisted caption reconstruction is unavailable")
        if not keyboard_available:
            reason.append("persisted keyboard reconstruction is unavailable")
        safe = not reason
        return HistoricalTelegramMediaCandidate(
            publish_request_id=publish_id,
            queue_item_id=str(item.get("queue_item_id") or ""), channel=channel,
            chat_id=chat_id, message_id=message_id,
            existing_width=width, existing_height=height,
            source_asset_id=(queue or {}).get("generated_image_id") or (queue or {}).get("reference_asset_id"),
            source_path=str(source) if source else None,
            derivative_path=derivative,
            expected_width=expected[0], expected_height=expected[1],
            editable=editable, caption_available=caption_available,
            keyboard_available=keyboard_available,
            status="SAFE" if safe else "SKIP", reason="ready" if safe else "; ".join(reason),
        )

    def _resolve_source(self, queue, channel):
        if not queue:
            return None
        recorded = Path(str(queue.get("output_reference") or ""))
        candidates = []
        if recorded.is_file(): candidates.append(recorded)
        if recorded.name:
            target = "Vault" if channel == "vault" else "Main"
            posted = Path(str(recorded).replace("\\Generation\\Active\\", f"\\Posted\\Telegram\\{target}\\"))
            if posted.is_file(): candidates.append(posted)
            content_root = recorded.parents[2] if len(recorded.parents) > 2 else None
            if content_root and content_root.is_dir():
                candidates.extend(content_root.glob(f"Posted/Telegram/{target}/{recorded.name}"))
        unique = {path.resolve(): path for path in candidates if path.is_file()}
        return next(iter(unique.values())) if len(unique) == 1 else None

    @staticmethod
    def _provider_result(item):
        metadata = dict(item.get("metadata") or {})
        return dict((((metadata.get("provider_metadata") or {}).get("response") or {}).get("result") or {}))

    def _verify_result(self, candidate, before, response):
        after = dict((response.get("response") or {}).get("result") or {})
        same_id = after.get("message_id") == candidate.message_id
        same_caption = str(after.get("caption") or "") == str(before.get("caption") or "")
        same_entities = (after.get("caption_entities") or []) == (before.get("caption_entities") or [])
        same_keyboard = (after.get("reply_markup") or None) == (before.get("reply_markup") or None)
        repaired = bool(response.get("ok") and same_id and same_caption and same_entities and same_keyboard)
        return {
            "publish_request_id": candidate.publish_request_id,
            "message_id": candidate.message_id, "channel": candidate.channel,
            "repair_status": "REPAIRED" if repaired else "FAILED",
            "message_id_retained": same_id, "caption_retained": same_caption,
            "caption_entities_retained": same_entities, "keyboard_retained": same_keyboard,
            "error": None if repaired else str(response.get("error") or "Telegram verification failed"),
        }

    def _persist_outcome(self, candidate, outcome, response):
        timestamp = datetime.now(timezone.utc).isoformat()
        audit = self._read(self.audit_path, missing_ok=True)
        audit.append({
            "repair_id": f"telegram_media_repair_{uuid4().hex}",
            "event_type": self.EVENT_TYPE, "repair_timestamp": timestamp,
            **asdict(candidate), **outcome, "telegram_response": response,
            "replacement_width": 960, "replacement_height": 1280,
        })
        self._write(self.audit_path, audit)
        history = self._read(self.history_path)
        history.insert(0, {
            "history_id": f"social_publish_history_{uuid4().hex}",
            "queue_item_id": candidate.queue_item_id, "platform": "telegram",
            "status": "historical_media_normalization",
            "message": outcome["repair_status"], "created_at": timestamp,
            "metadata": {"event_type": self.EVENT_TYPE, **outcome},
        })
        self._write(self.history_path, history)

    def _item(self, publish_request_id):
        return next(row for row in self._read(self.items_path) if row.get("publish_request_id") == publish_request_id)

    @staticmethod
    def _read(path, missing_ok=False):
        if missing_ok and not path.exists(): return []
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(value, list): raise RuntimeError(f"Expected JSON list: {path}")
        return value

    @staticmethod
    def _write(path, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)

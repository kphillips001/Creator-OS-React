"""Temporary, process-local visibility into Fanvue webhook ingress."""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.services.fanvue_api_explorer_service import redact_sensitive


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(redact_sensitive(value), default=str))


class FanvueWebhookMonitorService:
    """Thread-safe ring buffer. It never reads or writes durable storage."""

    def __init__(self, limit: int = 100, clock=time.perf_counter) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=limit)
        self._lock = threading.Lock()
        self._clock = clock

    def begin(
        self, *, raw_body: bytes, headers: dict[str, Any], request_path: str
    ) -> dict[str, Any]:
        try:
            payload: Any = json.loads(raw_body)
        except Exception:
            payload = {"rawBody": raw_body.decode("utf-8", errors="replace")}
        event_name = (
            headers.get("x-fanvue-topic")
            or (payload.get("event_type") if isinstance(payload, dict) else None)
            or (payload.get("type") if isinstance(payload, dict) else None)
            or (payload.get("event") if isinstance(payload, dict) else None)
            or "unknown"
        )
        event_id = (
            headers.get("x-fanvue-event-id")
            or (payload.get("event_id") if isinstance(payload, dict) else None)
            or (payload.get("id") if isinstance(payload, dict) else None)
            or (payload.get("webhook_event_id") if isinstance(payload, dict) else None)
        )
        return {
            "monitorId": str(uuid4()),
            "started": self._clock(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requestPath": request_path,
            "payloadSize": len(raw_body),
            "payload": payload,
            "rawJson": raw_body.decode("utf-8", errors="replace"),
            "headers": dict(headers),
            "signatureHeaders": {
                key: value
                for key, value in headers.items()
                if "signature" in key.lower()
            },
            "eventName": str(event_name),
            "eventId": str(event_id) if event_id is not None else None,
        }

    def complete(
        self,
        trace: dict[str, Any],
        *,
        http_status: int,
        signature_valid: bool | None = None,
        processing_result: Any = None,
        normalization_result: Any = None,
        persistence_result: Any = None,
        delivery_metadata: Any = None,
        exception: Any = None,
    ) -> None:
        item = {
            key: value for key, value in trace.items() if key != "started"
        }
        item.update(
            {
                "httpStatus": int(http_status),
                "signatureValid": signature_valid,
                "processingResult": processing_result,
                "normalizationResult": normalization_result,
                "persistenceResult": persistence_result,
                "deliveryMetadata": delivery_metadata or {},
                "exception": str(exception) if exception else None,
                "durationMs": round((self._clock() - trace["started"]) * 1000, 2),
                "retryCount": self._retry_count(processing_result),
            }
        )
        safe_item = _json_safe(item)
        safe_item["rawJson"] = json.dumps(
            safe_item["payload"], ensure_ascii=False, separators=(",", ":")
        )
        with self._lock:
            self._items.appendleft(safe_item)

    def list_items(self) -> list[dict[str, Any]]:
        with self._lock:
            return _json_safe(list(self._items))

    def clear_for_test(self) -> None:
        with self._lock:
            self._items.clear()

    @classmethod
    def _retry_count(cls, value: Any) -> int | None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key in {"retry_count", "retryCount"}:
                    try:
                        return int(nested)
                    except (TypeError, ValueError):
                        return None
                found = cls._retry_count(nested)
                if found is not None:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = cls._retry_count(nested)
                if found is not None:
                    return found
        return None


fanvue_webhook_monitor = FanvueWebhookMonitorService()

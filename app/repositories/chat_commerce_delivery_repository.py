"""Append-only history persistence for Chat Commerce Delivery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class ChatCommerceDeliveryRepository:
    """Persist delivery lifecycle events without owning delivery decisions."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "data/chat_commerce_delivery/delivery_history.json")

    def record_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return self.append_event("delivery_request", request)

    def record_result(self, result: Mapping[str, Any]) -> dict[str, Any]:
        status = str(result.get("status") or "").lower()
        event_type = "delivery_ready" if status == "ready" else "delivery_failure"
        return self.append_event(event_type, result)

    def record_success(self, delivery_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self.append_event(
            "delivery_success",
            {"delivery_id": delivery_id, "payload": dict(payload or {})},
        )

    def record_failure(
        self,
        delivery_id: str,
        reason: str | None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            "delivery_failure",
            {
                "delivery_id": delivery_id,
                "reason": reason,
                "payload": dict(payload or {}),
            },
        )

    def append_event(
        self,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        event = {"event_type": event_type, "payload": dict(payload or {})}
        events = self._read_events()
        events.append(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(events, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return event

    def list_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._read_events())

    def _read_events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(loaded, list):
            return []
        return [dict(item) for item in loaded if isinstance(item, Mapping)]

"""Append-only persistence for synchronized Commerce Outcomes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class CommerceOutcomeRepository:
    """Persist commerce sync events without owning provider commerce."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "data/commerce_outcomes/outcome_history.json")

    def record_outcome(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        return self.append_event("commerce_outcome", outcome)

    def record_failure(
        self,
        *,
        provider: str,
        provider_transaction_id: str | None,
        reason: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            "commerce_outcome_failure",
            {
                "provider": provider,
                "provider_transaction_id": provider_transaction_id,
                "reason": reason,
                "payload": dict(payload or {}),
            },
        )

    def record_duplicate(
        self,
        *,
        provider: str,
        provider_transaction_id: str | None,
        existing_outcome: Mapping[str, Any] | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.append_event(
            "commerce_outcome_duplicate",
            {
                "provider": provider,
                "provider_transaction_id": provider_transaction_id,
                "existing_outcome": dict(existing_outcome or {}),
                "payload": dict(payload or {}),
            },
        )

    def get_by_provider_transaction(
        self,
        *,
        provider: str,
        provider_transaction_id: str | None,
    ) -> dict[str, Any] | None:
        if not provider_transaction_id:
            return None
        for event in reversed(self._read_events()):
            if event.get("event_type") != "commerce_outcome":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            purchase = payload.get("purchase")
            purchase = purchase if isinstance(purchase, Mapping) else {}
            if (
                str(payload.get("provider") or "").lower() == str(provider).lower()
                and str(purchase.get("provider_transaction_id") or "")
                == str(provider_transaction_id)
            ):
                return dict(payload)
        return None

    def list_outcomes(self) -> tuple[dict[str, Any], ...]:
        outcomes: list[dict[str, Any]] = []
        for event in self._read_events():
            if event.get("event_type") != "commerce_outcome":
                continue
            payload = event.get("payload")
            if isinstance(payload, Mapping):
                outcomes.append(dict(payload))
        return tuple(outcomes)

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

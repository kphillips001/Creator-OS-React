"""Durable append-only persistence for content commerce learning."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class ContentCommerceLearningRepository:
    """Persist learning events and Business Outcomes idempotently."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or "data/content_commerce_learning/learning_history.json")

    def record_recommendation_event(
        self,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._upsert(
            "recommendation_event",
            event,
            key_field="event_id",
        )

    def record_business_outcome(
        self,
        outcome: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._upsert(
            "business_outcome",
            outcome,
            key_field="outcome_id",
        )

    def record_learning_failure(
        self,
        *,
        reason: str,
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id = str(
            (payload or {}).get("event_id")
            or (payload or {}).get("outcome_id")
            or f"failure:{reason}:{len(self._read_events())}"
        )
        return self._upsert(
            "learning_failure",
            {
                "event_id": event_id,
                "reason": reason,
                "payload": dict(payload or {}),
            },
            key_field="event_id",
        )

    def list_recommendation_events(
        self,
        *,
        recommendation_id: str | None = None,
        asset_id: int | str | None = None,
        customer_id: str | None = None,
        delivery_id: str | None = None,
        event_state: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        records = []
        for event in self._read_events():
            if event.get("event_type") != "recommendation_event":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            if recommendation_id and str(payload.get("recommendation_id")) != str(recommendation_id):
                continue
            if asset_id is not None and str(payload.get("asset_id")) != str(asset_id):
                continue
            if customer_id and str(payload.get("customer_id")) != str(customer_id):
                continue
            if delivery_id and str(payload.get("delivery_id")) != str(delivery_id):
                continue
            if event_state and str(payload.get("event_state")) != str(event_state):
                continue
            records.append(dict(payload))
        return tuple(records)

    def list_business_outcomes(
        self,
        *,
        asset_id: int | str | None = None,
        product_id: str | None = None,
        experience_id: str | None = None,
        customer_id: str | None = None,
        recommendation_id: str | None = None,
        delivery_id: str | None = None,
        provider_transaction_id: str | None = None,
        outcome_type: str | None = None,
    ) -> tuple[dict[str, Any], ...]:
        records = []
        for event in self._read_events():
            if event.get("event_type") != "business_outcome":
                continue
            payload = event.get("payload")
            if not isinstance(payload, Mapping):
                continue
            provider_metadata = payload.get("provider_metadata")
            provider_metadata = (
                provider_metadata if isinstance(provider_metadata, Mapping) else {}
            )
            if asset_id is not None and str(payload.get("subject_id")) != str(asset_id):
                continue
            if product_id and str(payload.get("product_id")) != str(product_id):
                continue
            if experience_id and str(payload.get("experience_id")) != str(experience_id):
                continue
            if customer_id and str(payload.get("customer_id")) != str(customer_id):
                continue
            if recommendation_id and str(payload.get("recommendation_id")) != str(recommendation_id):
                continue
            if delivery_id and str(provider_metadata.get("delivery_id")) != str(delivery_id):
                continue
            if provider_transaction_id and str(
                provider_metadata.get("provider_transaction_id")
            ) != str(provider_transaction_id):
                continue
            if outcome_type and str(payload.get("outcome_type")) != str(outcome_type):
                continue
            records.append(dict(payload))
        return tuple(records)

    def list_unmatched_outcomes(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            outcome
            for outcome in self.list_business_outcomes()
            if str(outcome.get("status") or "").upper() == "UNMATCHED"
        )

    def list_failed_learning_events(self) -> tuple[dict[str, Any], ...]:
        failures = []
        for event in self._read_events():
            if event.get("event_type") == "learning_failure":
                payload = event.get("payload")
                if isinstance(payload, Mapping):
                    failures.append(dict(payload))
        return tuple(failures)

    def list_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._read_events())

    def _upsert(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        key_field: str,
    ) -> dict[str, Any]:
        record = {"event_type": event_type, "payload": dict(payload or {})}
        key = record["payload"].get(key_field)
        events = self._read_events()
        if key is not None:
            for index, existing in enumerate(events):
                existing_payload = existing.get("payload")
                if (
                    existing.get("event_type") == event_type
                    and isinstance(existing_payload, Mapping)
                    and str(existing_payload.get(key_field)) == str(key)
                ):
                    merged = {**dict(existing_payload), **record["payload"]}
                    events[index] = {"event_type": event_type, "payload": merged}
                    self._write_events(events)
                    return events[index]
        events.append(record)
        self._write_events(events)
        return record

    def _write_events(self, events: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(events, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

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

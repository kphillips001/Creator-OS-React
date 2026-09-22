"""Chronological recent history for durable unmapped Telegram conversations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


class UnmappedTelegramHistoryService:
    """Merge bounded canonical event candidates before applying the GPT window."""

    DEFAULT_LIMIT = 10
    OVERFETCH_MULTIPLIER = 2

    def __init__(self, *, ordinary_source, manual_source, final_limit: int = DEFAULT_LIMIT):
        self.ordinary_source = ordinary_source
        self.manual_source = manual_source
        self.final_limit = max(1, int(final_limit))

    def recent_history(self, **scope) -> list[dict[str, str]]:
        candidate_limit = self.final_limit * self.OVERFETCH_MULTIPLIER
        ordinary = self.ordinary_source.recent_confirmed_events(
            **scope, limit=candidate_limit,
        )
        manual_scope = {
            key: scope[key] for key in (
                "creator_profile_id", "fanvue_account_id",
                "telegram_user_id", "telegram_chat_id",
            )
        }
        manual = self.manual_source.recent_confirmed_events(
            **manual_scope, limit=candidate_limit,
        )
        events = self.merge_events((*ordinary, *manual), limit=self.final_limit)
        return [
            {
                "role": str(event["role"]),
                "content": str(event["text"]),
                "origin": str(event["origin"]),
            }
            for event in events
        ]

    @classmethod
    def merge_events(
        cls, events: Iterable[Mapping[str, Any]], *, limit: int,
    ) -> list[dict[str, Any]]:
        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for raw in events:
            event = dict(raw)
            identity = cls._identity(event)
            existing = unique.get(identity)
            if existing is None or cls._sort_key(event) < cls._sort_key(existing):
                unique[identity] = event
        ordered = sorted(unique.values(), key=cls._sort_key)
        return ordered[-max(1, int(limit)):]

    @staticmethod
    def _identity(event: Mapping[str, Any]) -> tuple[Any, ...]:
        chat_id = event.get("telegram_chat_id")
        message_id = event.get("telegram_message_id")
        if chat_id is not None and message_id is not None:
            return "telegram", int(chat_id), int(message_id)
        stable = str(event.get("event_id") or "").strip()
        if not stable:
            raise ValueError("A stable history event identity is required.")
        return "event", stable

    @staticmethod
    def _sort_key(event: Mapping[str, Any]) -> tuple[datetime, str]:
        occurred_at = event.get("occurred_at")
        if not isinstance(occurred_at, datetime):
            raise ValueError("A history event occurrence timestamp is required.")
        if occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)
        return occurred_at.astimezone(timezone.utc), repr(
            UnmappedTelegramHistoryService._identity(event)
        )

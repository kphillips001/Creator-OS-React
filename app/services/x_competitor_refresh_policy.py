"""Canonical rolling refresh policy for X Competitor Intelligence."""
from __future__ import annotations

from datetime import datetime, timedelta


class XCompetitorRefreshPolicy:
    INTERVAL = timedelta(days=7)
    FAILURE_BACKOFF = timedelta(hours=6)
    DEFAULT_BATCH_SIZE = 10

    @classmethod
    def next_at(cls, last_success: datetime | None) -> datetime | None:
        return None if last_success is None else last_success + cls.INTERVAL

    @classmethod
    def due(cls, last_success: datetime | None, now: datetime) -> bool:
        next_at = cls.next_at(last_success)
        return next_at is None or next_at <= now

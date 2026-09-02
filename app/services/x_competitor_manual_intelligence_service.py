"""Operator-owned competitor intelligence that provider refreshes must not mutate."""
from __future__ import annotations

from urllib.parse import urlsplit

from app.repositories.x_competitor_intelligence_repository import XCompetitorIntelligenceRepository


class XCompetitorManualIntelligenceService:
    AUDIENCE_TYPES = {"SUBSCRIBERS", "MEMBERS"}
    PRESENCE_VALUES = {"UNKNOWN", "YES", "NO"}

    def __init__(self, repository=None):
        self.repository = repository or XCompetitorIntelligenceRepository()

    @staticmethod
    def validate_telegram_url(value: str | None) -> str | None:
        trimmed = value.strip() if value is not None else ""
        if not trimmed:
            return None
        parsed = urlsplit(trimmed)
        if parsed.scheme != "https" or parsed.hostname is None or parsed.hostname.lower() != "t.me" or not parsed.path.strip("/") or parsed.username or parsed.password:
            raise ValueError("Enter a valid full Telegram URL beginning with https://t.me/.")
        return trimmed

    def update_telegram(self, competitor_id: str, *, presence: str, audience_type: str | None, comments_allowed: bool | None, joined: bool | None, scraped: bool | None = None, telegram_url: str | None = None):
        if presence not in self.PRESENCE_VALUES:
            raise ValueError("Telegram presence must be UNKNOWN, YES, or NO.")
        if audience_type is not None and audience_type not in self.AUDIENCE_TYPES:
            raise ValueError("Telegram audience type must be SUBSCRIBERS, MEMBERS, or null.")
        resolved_url=self.validate_telegram_url(telegram_url)
        result=self.repository.update_manual_telegram_intelligence(competitor_id,presence=presence,telegram_url=resolved_url,audience_type=audience_type,comments_allowed=comments_allowed,joined=joined,scraped=scraped)
        if result is None:raise LookupError("Competitor not found.")
        return result

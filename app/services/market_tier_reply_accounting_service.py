"""DST-aware business-day projection for confirmed ordinary replies."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.repositories.market_tier_reply_accounting_repository import (
    MarketTierReplyAccountingRepository,
)


class MarketTierReplyAccountingService:
    ZONE = ZoneInfo("America/Chicago")

    def __init__(self, repository=None, now=None):
        self.repository = repository or MarketTierReplyAccountingRepository()
        self.now = now or (lambda: datetime.now(timezone.utc))

    @classmethod
    def business_day_bounds(cls, instant):
        local = instant.astimezone(cls.ZONE)
        start_local = datetime(local.year, local.month, local.day, tzinfo=cls.ZONE)
        end_local = start_local + timedelta(days=1)
        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    def today(self, **scope):
        start, end = self.business_day_bounds(self.now())
        return {
            "replies_used_today": self.repository.count_between(
                business_day_start=start, business_day_end=end, **scope),
            "business_day_start": start,
            "business_day_end": end,
            "next_reset_at": end,
        }

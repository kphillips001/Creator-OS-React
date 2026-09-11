"""Read-only contracts for the Creator OS performance snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from zoneinfo import ZoneInfo


class ReportingPeriodKey(str, Enum):
    TODAY = "TODAY"
    YESTERDAY = "YESTERDAY"
    LAST_7_DAYS = "LAST_7_DAYS"
    LAST_30_DAYS = "LAST_30_DAYS"
    THIS_WEEK = "THIS_WEEK"
    THIS_MONTH = "THIS_MONTH"
    LAST_MONTH = "LAST_MONTH"
    ALL_TIME = "ALL_TIME"


@dataclass(frozen=True)
class ReportingPeriod:
    key: ReportingPeriodKey
    timezone_name: str
    start: datetime | None
    end: datetime
    generated_at: datetime

    def contains(self, value: datetime) -> bool:
        instant = _utc(value)
        return (self.start is None or instant >= self.start) and instant < self.end

    def as_dict(self) -> dict:
        return {
            "key": self.key.value,
            "timezone": self.timezone_name,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat(),
            "generatedAt": self.generated_at.isoformat(),
            "interval": "[start,end)",
        }


class ReportingPeriodService:
    """Single authority for America/New_York reporting boundaries."""

    TIMEZONE = "America/New_York"

    def resolve(
        self, key: ReportingPeriodKey | str, *, now: datetime | None = None,
    ) -> ReportingPeriod:
        selected = ReportingPeriodKey(str(getattr(key, "value", key)).upper())
        current = _utc(now or datetime.now(timezone.utc))
        local = current.astimezone(ZoneInfo(self.TIMEZONE))
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if selected is ReportingPeriodKey.TODAY:
            start, end = midnight, midnight + timedelta(days=1)
        elif selected is ReportingPeriodKey.YESTERDAY:
            start, end = midnight - timedelta(days=1), midnight
        elif selected is ReportingPeriodKey.LAST_7_DAYS:
            start, end = current - timedelta(days=7), current
        elif selected is ReportingPeriodKey.LAST_30_DAYS:
            start, end = current - timedelta(days=30), current
        elif selected is ReportingPeriodKey.THIS_WEEK:
            start, end = midnight - timedelta(days=midnight.weekday()), current
        elif selected is ReportingPeriodKey.THIS_MONTH:
            start = midnight.replace(day=1)
            end = (
                start.replace(year=start.year + 1, month=1)
                if start.month == 12 else start.replace(month=start.month + 1)
            )
        elif selected is ReportingPeriodKey.LAST_MONTH:
            end = midnight.replace(day=1)
            start = (end.replace(year=end.year-1,month=12) if end.month==1
                     else end.replace(month=end.month-1))
        else:
            start, end = None, current
        return ReportingPeriod(
            key=selected, timezone_name=self.TIMEZONE,
            start=_utc(start) if start else None, end=_utc(end),
            generated_at=current,
        )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

"""Read-only presentation service for the Delayed Messages dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.repositories.delayed_message_dashboard_repository import (
    build_delayed_message_dashboard_summary,
)
from app.repositories.delayed_message_queue_repository import (
    fetch_recent_delayed_messages,
    get_delayed_message_queue_counts,
)


@dataclass(frozen=True)
class DelayedMessagesDashboard:
    summary: dict
    recent_rows: tuple[dict, ...]


class DelayedMessagesDashboardService:
    """Builds delayed-message queue read models for presentation pages."""

    def __init__(
        self,
        *,
        counts_fetcher: Callable[..., dict] = get_delayed_message_queue_counts,
        recent_fetcher: Callable[..., list[dict]] = fetch_recent_delayed_messages,
        summary_builder: Callable[[dict], dict]
        = build_delayed_message_dashboard_summary,
    ):
        self.counts_fetcher = counts_fetcher
        self.recent_fetcher = recent_fetcher
        self.summary_builder = summary_builder

    def build_dashboard(
        self,
        *,
        fanvue_account_id: int | None = None,
        recent_limit: int = 100,
    ) -> DelayedMessagesDashboard:
        counts = self.counts_fetcher(fanvue_account_id=fanvue_account_id)
        return DelayedMessagesDashboard(
            summary=self.summary_builder(counts),
            recent_rows=tuple(
                self.recent_fetcher(
                    fanvue_account_id=fanvue_account_id,
                    limit=recent_limit,
                )
            ),
        )

"""Read-only presentation service for the Wall Scheduler dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.repositories.wall_post_repository import (
    fetch_wall_queue_counts,
    fetch_wall_queue_dashboard,
)


@dataclass(frozen=True)
class WallSchedulerDashboard:
    counts: dict
    queue_rows: tuple[dict, ...]


class WallSchedulerDashboardService:
    """Builds Wall Scheduler read models for presentation pages."""

    def __init__(
        self,
        *,
        counts_fetcher: Callable[..., dict] = fetch_wall_queue_counts,
        queue_fetcher: Callable[..., list[dict]] = fetch_wall_queue_dashboard,
    ):
        self.counts_fetcher = counts_fetcher
        self.queue_fetcher = queue_fetcher

    def build_dashboard(
        self,
        *,
        fanvue_account_id: int | None = None,
    ) -> WallSchedulerDashboard:
        return WallSchedulerDashboard(
            counts=self.counts_fetcher(fanvue_account_id=fanvue_account_id),
            queue_rows=tuple(
                self.queue_fetcher(fanvue_account_id=fanvue_account_id)
            ),
        )

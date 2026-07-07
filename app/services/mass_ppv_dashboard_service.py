"""Read-only presentation service for the Mass PPV dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.repositories.mass_ppv_campaign_repository import (
    fetch_mass_ppv_campaign_analytics_rows,
    fetch_mass_ppv_campaign_dashboard_rows,
    fetch_mass_ppv_queue_dashboard_rows,
)


@dataclass(frozen=True)
class MassPPVDashboard:
    campaign_rows: tuple[dict, ...]
    queue_rows: tuple[dict, ...]
    analytics_rows: tuple[dict, ...]


class MassPPVDashboardService:
    """Builds Mass PPV read models for presentation pages."""

    def __init__(
        self,
        *,
        campaign_fetcher: Callable[..., list[dict]]
        = fetch_mass_ppv_campaign_dashboard_rows,
        queue_fetcher: Callable[..., list[dict]] = fetch_mass_ppv_queue_dashboard_rows,
        analytics_fetcher: Callable[..., list[dict]]
        = fetch_mass_ppv_campaign_analytics_rows,
    ):
        self.campaign_fetcher = campaign_fetcher
        self.queue_fetcher = queue_fetcher
        self.analytics_fetcher = analytics_fetcher

    def build_dashboard(
        self,
        *,
        fanvue_account_id: int | None = None,
        queue_status: str = "all",
        campaign_limit: int = 100,
        queue_limit: int = 250,
        analytics_limit: int = 100,
    ) -> MassPPVDashboard:
        return MassPPVDashboard(
            campaign_rows=self.get_campaign_rows(
                fanvue_account_id=fanvue_account_id,
                limit=campaign_limit,
            ),
            queue_rows=self.get_queue_rows(
                fanvue_account_id=fanvue_account_id,
                status=queue_status,
                limit=queue_limit,
            ),
            analytics_rows=self.get_analytics_rows(
                fanvue_account_id=fanvue_account_id,
                limit=analytics_limit,
            ),
        )

    def get_campaign_rows(
        self,
        *,
        fanvue_account_id: int | None = None,
        limit: int = 100,
    ) -> tuple[dict, ...]:
        return tuple(
            self.campaign_fetcher(
                fanvue_account_id=fanvue_account_id,
                limit=limit,
            )
        )

    def get_queue_rows(
        self,
        *,
        fanvue_account_id: int | None = None,
        status: str = "all",
        limit: int = 250,
    ) -> tuple[dict, ...]:
        return tuple(
            self.queue_fetcher(
                fanvue_account_id=fanvue_account_id,
                status=status,
                limit=limit,
            )
        )

    def get_analytics_rows(
        self,
        *,
        fanvue_account_id: int | None = None,
        limit: int = 100,
    ) -> tuple[dict, ...]:
        return tuple(
            self.analytics_fetcher(
                fanvue_account_id=fanvue_account_id,
                limit=limit,
            )
        )

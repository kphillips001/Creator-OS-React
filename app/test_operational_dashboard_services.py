import unittest
from pathlib import Path

from app.services.delayed_messages_dashboard_service import (
    DelayedMessagesDashboardService,
)
from app.services.mass_ppv_dashboard_service import MassPPVDashboardService
from app.services.wall_scheduler_dashboard_service import (
    WallSchedulerDashboardService,
)


class OperationalDashboardServiceTests(unittest.TestCase):
    def test_wall_scheduler_service_builds_read_model(self):
        calls = []
        service = WallSchedulerDashboardService(
            counts_fetcher=lambda **kwargs: calls.append(("counts", kwargs))
            or {"pending": 2},
            queue_fetcher=lambda **kwargs: calls.append(("queue", kwargs))
            or [{"id": 1}],
        )

        dashboard = service.build_dashboard(fanvue_account_id=7)

        self.assertEqual(dashboard.counts, {"pending": 2})
        self.assertEqual(dashboard.queue_rows, ({"id": 1},))
        self.assertEqual(
            calls,
            [
                ("counts", {"fanvue_account_id": 7}),
                ("queue", {"fanvue_account_id": 7}),
            ],
        )

    def test_mass_ppv_service_preserves_section_fetch_arguments(self):
        calls = []
        service = MassPPVDashboardService(
            campaign_fetcher=lambda **kwargs: calls.append(("campaign", kwargs))
            or [{"campaign": 1}],
            queue_fetcher=lambda **kwargs: calls.append(("queue", kwargs))
            or [{"queue": 1}],
            analytics_fetcher=lambda **kwargs: calls.append(("analytics", kwargs))
            or [{"analytics": 1}],
        )

        dashboard = service.build_dashboard(
            fanvue_account_id=9,
            queue_status="failed",
            campaign_limit=10,
            queue_limit=20,
            analytics_limit=30,
        )

        self.assertEqual(dashboard.campaign_rows, ({"campaign": 1},))
        self.assertEqual(dashboard.queue_rows, ({"queue": 1},))
        self.assertEqual(dashboard.analytics_rows, ({"analytics": 1},))
        self.assertEqual(
            calls,
            [
                ("campaign", {"fanvue_account_id": 9, "limit": 10}),
                (
                    "queue",
                    {
                        "fanvue_account_id": 9,
                        "status": "failed",
                        "limit": 20,
                    },
                ),
                ("analytics", {"fanvue_account_id": 9, "limit": 30}),
            ],
        )

    def test_delayed_messages_service_builds_summary_and_rows(self):
        calls = []
        service = DelayedMessagesDashboardService(
            counts_fetcher=lambda **kwargs: calls.append(("counts", kwargs))
            or {"pending": 3},
            summary_builder=lambda counts: calls.append(("summary", counts))
            or {"pending": counts["pending"]},
            recent_fetcher=lambda **kwargs: calls.append(("recent", kwargs))
            or [{"id": 2}],
        )

        dashboard = service.build_dashboard(
            fanvue_account_id=4,
            recent_limit=25,
        )

        self.assertEqual(dashboard.summary, {"pending": 3})
        self.assertEqual(dashboard.recent_rows, ({"id": 2},))
        self.assertEqual(
            calls,
            [
                ("counts", {"fanvue_account_id": 4}),
                ("summary", {"pending": 3}),
                ("recent", {"fanvue_account_id": 4, "limit": 25}),
            ],
        )

    def test_cleaned_pages_do_not_import_repositories_directly(self):
        for file_name in (
            "wall_scheduler_dashboard.py",
            "mass_ppv_dashboard.py",
            "delayed_messages_dashboard.py",
        ):
            source = Path(f"app/dashboard/pages/{file_name}").read_text(
                encoding="utf-8"
            )
            self.assertNotIn("from app.repositories", source)
            self.assertNotIn("import app.repositories", source)


if __name__ == "__main__":
    unittest.main()

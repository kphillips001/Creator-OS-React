import json
import unittest
from pathlib import Path

from app.dashboard.navigation import (
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
    PROFILE_LOCKED_PAGES,
    normalize_dashboard_page,
)


class ApprovalQueueRemovalTests(unittest.TestCase):
    def test_approval_queue_is_not_dashboard_navigation_option(self):
        self.assertNotIn("Approval Queue", DASHBOARD_PAGE_OPTIONS)
        self.assertNotIn("Approval Queue", DASHBOARD_PAGE_LABELS)
        self.assertNotIn("Approval Queue", PROFILE_LOCKED_PAGES)

    def test_stale_approval_queue_route_falls_back_to_workspace(self):
        self.assertEqual(
            normalize_dashboard_page("Approval Queue"),
            "Creator Workspace",
        )

    def test_module_switches_no_longer_expose_approval_queue_toggle(self):
        source = Path("app/dashboard/pages/module_switches.py").read_text(
            encoding="utf-8",
        )

        self.assertNotIn("Approval Queue Enabled", source)
        self.assertNotIn("approval_queue_enabled", source)

    def test_current_dashboard_router_no_longer_imports_or_routes_queue(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertNotIn("render_approval_queue", source)
        self.assertNotIn("pages.approval_queue", source)
        self.assertNotIn('== "Approval Queue"', source)

    def test_legacy_dashboard_no_longer_exposes_queue_in_sidebar(self):
        source = Path("app/dashboard.py").read_text(encoding="utf-8")
        source = source.replace("\r\n", "\n")
        navigation_block = source.split("# =========================\n# LOAD CONFIG")[0]

        self.assertNotIn('"Approval Queue"', navigation_block)
        self.assertNotIn("Approval Queue Enabled", source)
        self.assertNotIn("approval_queue_enabled", source)
        self.assertIn('elif False and page == "Approval Queue":', source)

    def test_behavior_config_no_longer_contains_approval_queue_module(self):
        config = json.loads(
            Path("data/config/behavior_config.json").read_text(
                encoding="utf-8",
            )
        )

        self.assertNotIn(
            "approval_queue_enabled",
            config.get("modules", {}),
        )


if __name__ == "__main__":
    unittest.main()

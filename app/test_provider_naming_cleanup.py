import unittest
from pathlib import Path

from app.dashboard.navigation import (
    DASHBOARD_PAGE_LABELS,
    grouped_navigation_label_for_page,
    page_for_grouped_navigation_label,
)
from app.dashboard.pages.creator_workspace import WORKSPACE_SECTIONS


class ProviderNamingCleanupTests(unittest.TestCase):
    def test_provider_connection_label_preserves_legacy_route(self):
        self.assertEqual(
            DASHBOARD_PAGE_LABELS["Fanvue Auth"],
            "Administration: Provider Connections",
        )
        self.assertEqual(
            grouped_navigation_label_for_page("Fanvue Auth"),
            "  Provider Connections",
        )
        self.assertEqual(
            page_for_grouped_navigation_label("  Provider Connections"),
            "Fanvue Auth",
        )

    def test_publishing_labels_preserve_legacy_routes(self):
        self.assertEqual(
            grouped_navigation_label_for_page("Wall Scheduler"),
            "  Wall Publishing Queue",
        )
        self.assertEqual(
            grouped_navigation_label_for_page("Mass PPV Dashboard"),
            "  Campaign Publishing",
        )
        self.assertEqual(
            page_for_grouped_navigation_label("  Wall Publishing Queue"),
            "Wall Scheduler",
        )
        self.assertEqual(
            page_for_grouped_navigation_label("  Campaign Publishing"),
            "Mass PPV Dashboard",
        )

    def test_workspace_uses_provider_neutral_admin_action(self):
        administration = next(
            section
            for section in WORKSPACE_SECTIONS
            if section.title == "Administration"
        )

        self.assertIn(
            ("Provider Connections", "Fanvue Auth"),
            administration.secondary_targets,
        )

    def test_product_catalog_visible_vault_copy_is_provider_neutral(self):
        source = Path("app/dashboard/pages/product_catalog.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Provider Vault", source)
        self.assertNotIn("Upload to Fanvue Vault", source)
        self.assertNotIn("Fanvue Vault upload failed", source)


if __name__ == "__main__":
    unittest.main()

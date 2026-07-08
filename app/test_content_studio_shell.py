import unittest
import sys
import types
from pathlib import Path

if "streamlit" not in sys.modules:
    streamlit = types.ModuleType("streamlit")
    sys.modules["streamlit"] = streamlit

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    rows = types.ModuleType("psycopg.rows")
    psycopg_types = types.ModuleType("psycopg.types")
    json_types = types.ModuleType("psycopg.types.json")
    errors = types.ModuleType("psycopg.errors")
    psycopg.connect = lambda *args, **kwargs: None
    rows.dict_row = object()
    json_types.Json = lambda value: value
    errors.UniqueViolation = type("UniqueViolation", (Exception,), {})
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = rows
    sys.modules["psycopg.types"] = psycopg_types
    sys.modules["psycopg.types.json"] = json_types
    sys.modules["psycopg.errors"] = errors

from app.dashboard.navigation import (
    DASHBOARD_NAVIGATION_GROUPS,
    DASHBOARD_PAGE_LABELS,
    DASHBOARD_PAGE_OPTIONS,
    PROFILE_LOCKED_PAGES,
    grouped_navigation_label_for_page,
    page_for_grouped_navigation_label,
)
from app.dashboard.pages.content_studio import CONTENT_STUDIO_PAGES


class ContentStudioShellTests(unittest.TestCase):
    def test_content_studio_pages_are_registered(self):
        for page in CONTENT_STUDIO_PAGES:
            self.assertIn(page, DASHBOARD_PAGE_OPTIONS)
            self.assertIn(page, PROFILE_LOCKED_PAGES)
            self.assertEqual(
                DASHBOARD_PAGE_LABELS[page],
                f"Content Studio: {page}",
            )
            self.assertEqual(
                page_for_grouped_navigation_label(
                    grouped_navigation_label_for_page(page)
                ),
                page,
            )

    def test_content_studio_navigation_group_matches_shell_pages(self):
        group = next(
            item
            for item in DASHBOARD_NAVIGATION_GROUPS
            if item.label == "Content Studio"
        )

        self.assertEqual(group.icon, "CS")
        self.assertEqual(
            tuple(item.label for item in group.items),
            CONTENT_STUDIO_PAGES,
        )
        self.assertEqual(
            tuple(item.page for item in group.items),
            CONTENT_STUDIO_PAGES,
        )

    def test_dashboard_router_exposes_content_studio_shell(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("render_content_studio_page", source)
        for page in CONTENT_STUDIO_PAGES:
            self.assertIn(f'"{page}"', source)

    def test_content_studio_shell_is_presentation_only(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Generation logic, APIs, prompts, and queues are not migrated", source)
        self.assertIn("Creator OS Local Vault", source)
        self.assertIn("AI Import Workflow", source)
        self.assertNotIn("Wavespeed_App", source)
        self.assertNotIn("submit_wavespeed_task", source)
        self.assertNotIn("poll_wavespeed_result", source)
        self.assertNotIn("upload_to_imgbb", source)
        self.assertNotIn("generate_prompts_with_grok", source)
        self.assertNotIn("requests", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("PublishingService", source)
        self.assertNotIn("AssetRepository", source)


if __name__ == "__main__":
    unittest.main()

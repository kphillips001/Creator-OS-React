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
    DASHBOARD_PAGE_OPTIONS,
    grouped_navigation_label_for_page,
    page_for_grouped_navigation_label,
)
from app.dashboard.pages.asset_library import build_asset_library_filter


class AssetLibraryPageTests(unittest.TestCase):
    def test_asset_library_uses_creator_focused_tabs(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            '["📦 Library", "🧠 Intelligence", "⚙ Operations"]',
            source,
        )
        library = source.split("with library_tab:", 1)[1].split(
            "with intelligence_tab:", 1
        )[0]
        for label in (
            '"Search"',
            '"Media Type"',
            '"Classification"',
            '"Tags"',
            '"Themes"',
            '"Created After"',
            '"Created Before"',
            '"Reference Image"',
        ):
            self.assertIn(label, library)
        for label in (
            '"Limit"',
            '"Relationship Filter"',
            '"Creator Profile ID"',
            '"Publishing Status"',
            '"Local Vault"',
            '"Legacy Content ID"',
        ):
            self.assertNotIn(label, library)

    def test_intelligence_and_operations_own_their_domains(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        intelligence = source.split("def _render_intelligence", 1)[1].split(
            "def _render_operations_details", 1
        )[0]
        for heading in ("Description", "Tags", "Themes", "Safety", "Quality"):
            self.assertIn(f'"#### {heading}"', intelligence)
        self.assertNotIn("gpt_vision_result", intelligence)
        self.assertNotIn("nudenet_result", intelligence)

        operations = source.split("with operations_tab:", 1)[1]
        self.assertIn("_render_chat_commerce_inventory()", operations)
        self.assertIn("_render_bulk_actions", operations)
        self.assertIn("_render_operations_details", operations)

    def test_empty_inventory_has_creator_focused_navigation(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn('st.markdown("### What assets do I own?")', source)
        self.assertNotIn('st.markdown("### Asset Grid")', source)
        self.assertIn('st.markdown("### 📦 No assets yet")', source)
        self.assertIn('"Go to Generation Library"', source)
        self.assertIn(
            'st.session_state["dashboard_page"] = "Generation Library"',
            source,
        )

    def test_library_filters_are_collapsed_by_default(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )
        library = source.split("with library_tab:", 1)[1].split(
            "with intelligence_tab:", 1
        )[0]

        self.assertIn('st.expander("Filters", expanded=False)', library)
        self.assertNotIn('st.expander("Filters", expanded=True)', library)

    def test_empty_selection_gates_intelligence_and_operations(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("if details is None:", source)
        self.assertIn(
            '"🧠 Select an asset from the Library tab to view:"',
            source,
        )
        self.assertIn(
            '"⚙ Select an asset from the Library tab to manage:"',
            source,
        )

    def test_asset_library_route_exists(self):
        self.assertIn("Asset Library", DASHBOARD_PAGE_OPTIONS)
        self.assertEqual(
            page_for_grouped_navigation_label(
                grouped_navigation_label_for_page("Asset Library")
            ),
            "Asset Library",
        )

    def test_navigation_includes_assets_asset_library(self):
        assets_group = next(
            group for group in DASHBOARD_NAVIGATION_GROUPS
            if group.label == "Assets"
        )
        labels = [item.label for item in assets_group.items]
        pages = [item.page for item in assets_group.items]

        self.assertEqual(labels, ["Asset Library"])
        self.assertEqual(pages, ["Asset Library"])

    def test_dashboard_router_imports_and_routes_asset_library(self):
        source = Path("app/dashboard/main.py").read_text(encoding="utf-8")

        self.assertIn("render_asset_library", source)
        self.assertIn('== "Asset Library"', source)

    def test_workspace_assets_card_targets_asset_library(self):
        source = Path("app/dashboard/pages/creator_workspace.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('primary_target="Asset Library"', source)
        self.assertIn('("Ingestion", "CMS Upload")', source)

    def test_page_uses_service_not_repositories(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("AssetLibraryService", source)
        self.assertIn("AssetLibraryFilter", source)
        self.assertIn("get_asset_details", source)
        self.assertNotIn("AssetRepository", source)
        self.assertNotIn("ProductRepository", source)
        self.assertNotIn("RuntimeMediaResolver", source)
        self.assertNotIn("MediaProcessingService", source)
        self.assertNotIn("AssetLifecycleService", source)
        self.assertNotIn("archive_assets", source)
        self.assertNotIn("delete", source.lower())

    def test_filter_values_convert_to_asset_library_filter(self):
        filters = build_asset_library_filter(
            search="  ava  ",
            media_type="all",
            classification="ALL",
            eligible_only=False,
            limit=25,
        )

        self.assertEqual(filters.search, "ava")
        self.assertIsNone(filters.media_type)
        self.assertIsNone(filters.classification)
        self.assertFalse(filters.eligible_only)
        self.assertEqual(filters.limit, 25)

        filters = build_asset_library_filter(
            search="",
            media_type="image",
            classification="VIP",
            eligible_only=True,
            limit=50,
        )

        self.assertIsNone(filters.search)
        self.assertEqual(filters.media_type, "image")
        self.assertEqual(filters.classification, "VIP")
        self.assertTrue(filters.eligible_only)
        self.assertEqual(filters.limit, 50)

    def test_existing_routes_remain_accessible(self):
        self.assertIn("Product Catalog", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("CMS Upload", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("Creator Workspace", DASHBOARD_PAGE_OPTIONS)
        self.assertIn("Pricing Playground", DASHBOARD_PAGE_OPTIONS)

    def test_asset_actions_use_asset_library_service_boundaries(self):
        source = Path("app/dashboard/pages/asset_library.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("service.regenerate_derivative_preview", source)
        self.assertIn("service.refresh_derivative_summary", source)
        self.assertIn("product_catalog_prefill_asset_ids", source)
        self.assertIn("experience_prefill_asset_ids", source)
        self.assertIn("publishing_prefill_asset_ids", source)
        self.assertIn('"dashboard_page"] = "Product Catalog"', source)
        self.assertIn('"dashboard_page"] = "Wall Scheduler"', source)


if __name__ == "__main__":
    unittest.main()

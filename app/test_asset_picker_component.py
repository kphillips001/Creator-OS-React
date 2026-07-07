import unittest
from datetime import datetime, timezone
from pathlib import Path

from app.dashboard.components.asset_picker import (
    build_asset_picker_filter,
    merge_asset_items,
    ordered_selection,
)
from app.models.asset_library import (
    AssetLibraryItem,
    AssetLibraryResult,
    AssetLibraryFilter,
    AssetPublishingSummary,
    AssetRelationshipSummary,
)


def item(asset_id: int) -> AssetLibraryItem:
    return AssetLibraryItem(
        asset_id=asset_id,
        file_name=f"asset-{asset_id}.jpg",
        media_type="image",
        classification="VIP",
        status="approved",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        preview_path=f"preview-{asset_id}.jpg",
        original_path=f"original-{asset_id}.jpg",
        tags=(),
        themes=(),
        relationship=AssetRelationshipSummary(),
        publishing=AssetPublishingSummary(status="Not uploaded to Fanvue"),
    )


class AssetPickerComponentTests(unittest.TestCase):
    def test_build_asset_picker_filter_targets_asset_library_service(self):
        filters = build_asset_picker_filter(
            search="  ava ",
            media_type="all",
            classification=" VIP ",
            eligible_only=True,
            limit=50,
        )

        self.assertIsNone(filters.media_type)
        self.assertEqual(filters.search, "ava")
        self.assertEqual(filters.classification, "VIP")
        self.assertTrue(filters.eligible_only)
        self.assertEqual(filters.limit, 50)

    def test_ordered_selection_preserves_existing_order_and_appends_new(self):
        self.assertEqual(
            ordered_selection(
                current_order=(3, 1, 2),
                selected_asset_ids=(2, 4, 3),
            ),
            (3, 2, 4),
        )

    def test_merge_asset_items_preserves_current_selected_items(self):
        result = AssetLibraryResult(
            items=(item(1), item(2)),
            filters=AssetLibraryFilter(),
            total=2,
        )
        merged = merge_asset_items(result, (item(3), item(2)))

        self.assertEqual(set(merged), {1, 2, 3})
        self.assertEqual(merged[3].file_name, "asset-3.jpg")

    def test_product_catalog_uses_shared_asset_picker(self):
        source = Path("app/dashboard/pages/product_catalog.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("render_asset_picker", source)
        self.assertIn("AssetLibraryService", source)
        self.assertNotIn("service.assets.search_assets", source)
        self.assertNotIn("asset_search_", source)
        self.assertNotIn("asset_media_type_", source)
        self.assertNotIn("asset_classification_", source)


if __name__ == "__main__":
    unittest.main()

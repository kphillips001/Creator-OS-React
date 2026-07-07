import unittest
from datetime import datetime, timezone
from uuid import uuid4

from app.models.asset import Asset
from app.models.product import (
    Product,
    ProductStatus,
    ProductType,
)
from app.services.commerce_foundation_backfill_service import (
    CommerceFoundationBackfillService,
)


def make_asset(asset_id: int, name: str) -> Asset:
    return Asset(
        id=asset_id,
        file_path=f"vault/{name}",
        file_name=name,
        classification="test",
        confidence=None,
        status="approved",
        is_active=True,
        is_test=False,
        ready_for_rotation=True,
        upload_intent=None,
        content_tier=None,
        distribution_type=None,
        blurred_preview_path=None,
        suggested_tags=(),
        detected_themes=(),
        is_explicit=False,
        fanvue_media_preview_uuid=None,
        fanvue_media_full_uuid=None,
        created_at=None,
    )


class AssetTests(unittest.TestCase):
    def test_media_type_is_inferred_without_changing_legacy_data(self):
        self.assertEqual(make_asset(1, "one.JPG").media_type, "image")
        self.assertEqual(make_asset(2, "two.mp4").media_type, "video")
        self.assertEqual(make_asset(3, "three.bin").media_type, "unknown")


class FakeAssetRepository:
    def __init__(self, assets):
        self.assets = assets

    def list_all(self):
        return self.assets


class FakeProductRepository:
    def __init__(self):
        self.products = {}

    def create_draft_for_asset(self, asset):
        existing = self.products.get(asset.id)
        if existing:
            return existing, False
        now = datetime.now(timezone.utc)
        media_product_type = {
            "image": ProductType.SINGLE_IMAGE,
            "video": ProductType.SINGLE_VIDEO,
        }.get(asset.media_type, ProductType.CUSTOM)
        product = Product(
            id=uuid4(),
            creator_profile_id=None,
            legacy_content_item_id=asset.id,
            internal_name=f"legacy-content-{asset.id}",
            display_name=asset.file_name,
            description=None,
            product_type=media_product_type,
            status=ProductStatus.DRAFT,
            price_cents=None,
            base_price_cents=None,
            min_price_cents=None,
            max_price_cents=None,
            currency="USD",
            media_link=None,
            tags=(),
            themes=(),
            metadata={"legacy_content_item_id": asset.id},
            activation_source=None,
            activation_reason=None,
            activated_at=None,
            created_at=now,
            updated_at=now,
        )
        self.products[asset.id] = product
        return product, True


class FakeProductAssetRepository:
    def __init__(self):
        self.links = set()

    def attach_primary(self, product_id, asset_id):
        key = (product_id, asset_id)
        created = key not in self.links
        self.links.add(key)
        return key, created


class BackfillTests(unittest.TestCase):
    def test_backfill_is_idempotent_and_preserves_traceability(self):
        assets = [make_asset(11, "one.jpg"), make_asset(12, "two.mp4")]
        products = FakeProductRepository()
        links = FakeProductAssetRepository()
        service = CommerceFoundationBackfillService(
            FakeAssetRepository(assets), products, links
        )

        first = service.run()
        second = service.run()

        self.assertEqual(first.products_created, 2)
        self.assertEqual(first.product_assets_created, 2)
        self.assertEqual(second.products_created, 0)
        self.assertEqual(second.product_assets_created, 0)
        self.assertEqual(set(products.products), {11, 12})
        self.assertIsNone(products.products[11].price_cents)
        self.assertEqual(products.products[11].status, ProductStatus.DRAFT)


if __name__ == "__main__":
    unittest.main()

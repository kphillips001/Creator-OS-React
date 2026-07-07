import unittest
from uuid import uuid4

from app.database import get_db_connection
from app.models.product import ProductStatus, ProductType
from app.services.product_catalog_service import (
    ProductCatalogCommand,
    ProductCatalogService,
    ProductCatalogValidationError,
)


class ProductCatalogPostgresTests(unittest.TestCase):
    def setUp(self):
        self.service = ProductCatalogService()
        self.product_id = None
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id FROM creator_profiles
                    WHERE is_active = TRUE
                    ORDER BY id LIMIT 1
                    """
                )
                self.creator_profile_id = cursor.fetchone()["id"]
                cursor.execute(
                    """
                    SELECT id FROM creator_profiles
                    WHERE id <> %s ORDER BY id LIMIT 1
                    """,
                    (self.creator_profile_id,),
                )
                other_profile = cursor.fetchone()
                self.other_creator_profile_id = (
                    other_profile["id"] if other_profile else None
                )
                cursor.execute(
                    "SELECT id FROM content_items ORDER BY id LIMIT 2"
                )
                self.asset_ids = tuple(row["id"] for row in cursor.fetchall())
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM customer_entitlements"
                )
                self.entitlements_before = cursor.fetchone()["count"]
        self.internal_name = f"catalog-test-{uuid4()}"

    def tearDown(self):
        if self.product_id:
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM product_assets WHERE product_id = %s",
                        (self.product_id,),
                    )
                    cursor.execute(
                        "DELETE FROM products WHERE id = %s",
                        (self.product_id,),
                    )

    def command(self, *, asset_ids=(), price=None, media_link=None):
        return ProductCatalogCommand(
            creator_profile_id=self.creator_profile_id,
            internal_name=self.internal_name,
            display_name="Catalog Integration Product",
            description="Temporary integration-test record",
            product_type=ProductType.STORY,
            price_cents=price,
            currency="USD",
            media_link=media_link,
            tags=("integration",),
            themes=("Test",),
            asset_ids=tuple(asset_ids),
        )

    def test_crud_ordering_activation_and_lifecycle(self):
        created = self.service.create_product(self.command())
        self.product_id = created.product.id
        self.assertEqual(created.product.status, ProductStatus.DRAFT)

        with self.assertRaises(ProductCatalogValidationError):
            self.service.transition_status(
                self.product_id,
                self.creator_profile_id,
                ProductStatus.ACTIVE,
            )

        command = self.command(
            asset_ids=self.asset_ids,
            price=2500,
            media_link="https://example.test/catalog-product",
        )
        updated = self.service.update_product(
            self.product_id,
            command,
            activate=True,
        )
        self.assertEqual(updated.product.status, ProductStatus.ACTIVE)
        self.assertEqual(
            tuple(link.asset_id for link in updated.product_assets),
            self.asset_ids,
        )
        filtered = self.service.products.list_products(
            creator_profile_id=self.creator_profile_id,
            tag="integration",
            theme="test",
        )
        self.assertIn(self.product_id, {product.id for product in filtered})
        if self.other_creator_profile_id:
            self.assertIsNone(
                self.service.products.get_by_id(
                    self.product_id,
                    creator_profile_id=self.other_creator_profile_id,
                )
            )

        reversed_command = ProductCatalogCommand(
            **{**command.__dict__, "asset_ids": tuple(reversed(self.asset_ids))}
        )
        reordered = self.service.update_product(
            self.product_id,
            reversed_command,
        )
        self.assertEqual(
            tuple(link.asset_id for link in reordered.product_assets),
            tuple(reversed(self.asset_ids)),
        )

        disabled = self.service.transition_status(
            self.product_id,
            self.creator_profile_id,
            ProductStatus.DISABLED,
        )
        self.assertEqual(disabled.status, ProductStatus.DISABLED)
        archived = self.service.transition_status(
            self.product_id,
            self.creator_profile_id,
            ProductStatus.ARCHIVED,
        )
        self.assertEqual(archived.status, ProductStatus.ARCHIVED)

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS count FROM customer_entitlements"
                )
                self.assertEqual(
                    cursor.fetchone()["count"],
                    self.entitlements_before,
                )


if __name__ == "__main__":
    unittest.main()

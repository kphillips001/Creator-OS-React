import unittest

from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessHealth,
    ProductBusinessSnapshot,
)
from app.models.product_catalog_management import (
    ProductCatalogHealth,
    ProductCatalogHealthStatus,
    ProductCatalogRecommendationType,
)
from app.models.product_strategy import (
    ProductStrategyRecommendation,
    ProductStrategyResult,
)
from app.services.product_catalog_management_service import (
    ProductCatalogManagementService,
)


def product(
    product_id,
    *,
    name=None,
    product_type="PHOTO_SET",
    delivery_type="PAID",
    availability=ProductBusinessAvailability.TELEGRAM_READY,
    health=ProductBusinessHealth.HEALTHY,
):
    return ProductBusinessSnapshot(
        product_id=product_id,
        product_name=name or product_id,
        product_type=product_type,
        delivery_type=delivery_type,
        availability=availability,
        product_health=health,
    )


class ProductCatalogManagementServiceTests(unittest.TestCase):
    def test_catalog_health_creation(self):
        health = ProductCatalogHealth(status=ProductCatalogHealthStatus.EMPTY)

        self.assertEqual(health.status, ProductCatalogHealthStatus.EMPTY)
        self.assertEqual(health.total_products, 0)
        self.assertIsNone(health.next_recommendation)

    def test_catalog_recommendations_for_missing_products(self):
        service = ProductCatalogManagementService()

        health = service.build_catalog_health(
            product_business_snapshots=(
                product(
                    "paid-1",
                    product_type="PHOTO_SET",
                    delivery_type="PAID",
                ),
            )
        )

        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in health.recommendations
        }
        self.assertEqual(health.status, ProductCatalogHealthStatus.INCOMPLETE)
        self.assertIn(
            ProductCatalogRecommendationType.CREATE_FREE_PREVIEW,
            recommendation_types,
        )
        self.assertIn(ProductCatalogRecommendationType.CREATE_BUNDLE, recommendation_types)
        self.assertIn(
            ProductCatalogRecommendationType.CREATE_STORY_PRODUCT,
            recommendation_types,
        )

    def test_duplicate_and_incomplete_detection(self):
        service = ProductCatalogManagementService()

        health = service.build_catalog_health(
            product_business_snapshots=(
                product("one", name="Same Name"),
                product("two", name="Same Name"),
                product(
                    "draft",
                    name="Draft",
                    product_type=None,
                    availability=ProductBusinessAvailability.DRAFT,
                    health=ProductBusinessHealth.DRAFT,
                ),
            )
        )

        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in health.recommendations
        }
        self.assertEqual(health.status, ProductCatalogHealthStatus.NEEDS_ATTENTION)
        self.assertIn("name:same name", health.duplicate_groups)
        self.assertIn("draft", health.incomplete_product_ids)
        self.assertIn(
            ProductCatalogRecommendationType.REMOVE_DUPLICATE,
            recommendation_types,
        )
        self.assertIn(
            ProductCatalogRecommendationType.COMPLETE_PRODUCT,
            recommendation_types,
        )

    def test_product_business_integration(self):
        service = ProductCatalogManagementService()

        health = service.build_catalog_health(
            product_business_snapshots=(
                product("free", product_type="PHOTO_SET", delivery_type="FREE"),
                product("paid", product_type="PHOTO_SET", delivery_type="PAID"),
                product("bundle", product_type="BUNDLE", delivery_type="PAID"),
                product("story", product_type="STORY", delivery_type="PAID"),
            )
        )

        self.assertEqual(health.total_products, 4)
        self.assertEqual(health.free_products, 1)
        self.assertEqual(health.paid_products, 3)
        self.assertEqual(health.bundle_products, 1)
        self.assertEqual(health.story_products, 1)
        self.assertTrue(health.compatibility["product_business_consumed"])
        self.assertFalse(health.compatibility["creates_products"])

    def test_product_strategy_integration(self):
        service = ProductCatalogManagementService()
        strategy = ProductStrategyResult(
            source_type="experience",
            source_id="exp-1",
            recommendations=(
                ProductStrategyRecommendation(
                    recommendation_type="collection",
                    source_type="experience",
                    source_id="exp-1",
                ),
                ProductStrategyRecommendation(
                    recommendation_type="story_product",
                    source_type="experience",
                    source_id="exp-1",
                ),
            ),
        )

        health = service.build_catalog_health(
            product_business_snapshots=(
                product("paid", product_type="PHOTO_SET", delivery_type="PAID"),
            ),
            product_strategy_result=strategy,
        )

        labels = {recommendation.label for recommendation in health.recommendations}
        self.assertIn("Create Collection Product", labels)
        self.assertIn("Create Story Product", labels)
        self.assertTrue(health.compatibility["product_strategy_consumed"])
        self.assertFalse(health.compatibility["generates_product_strategy"])

    def test_catalog_complete_recommendation(self):
        service = ProductCatalogManagementService()

        health = service.build_catalog_health(
            product_business_snapshots=(
                product("free", product_type="PHOTO_SET", delivery_type="FREE"),
                product("paid", product_type="PHOTO_SET", delivery_type="PAID"),
                product("bundle", product_type="BUNDLE", delivery_type="PAID"),
                product("story", product_type="STORY", delivery_type="PAID"),
            )
        )

        self.assertEqual(health.status, ProductCatalogHealthStatus.HEALTHY)
        self.assertEqual(
            health.recommendations[0].recommendation_type,
            ProductCatalogRecommendationType.CATALOG_COMPLETE,
        )

    def test_backward_compatibility_mapping_inputs(self):
        service = ProductCatalogManagementService()

        health = service.build_catalog_health(
            product_business_snapshots=(
                {
                    "product_id": "legacy-free",
                    "product_name": "Legacy Free",
                    "product_type": "PHOTO_SET",
                    "delivery_type": "FREE",
                    "availability": "TELEGRAM_READY",
                    "product_health": "HEALTHY",
                },
                {
                    "product_id": "legacy-paid",
                    "product_name": "Legacy Paid",
                    "product_type": "STORY",
                    "delivery_type": "PAID",
                    "availability": "AVAILABLE",
                    "product_health": "ACTIVE",
                },
            )
        )

        self.assertEqual(health.total_products, 2)
        self.assertEqual(health.free_products, 1)
        self.assertEqual(health.paid_products, 1)
        self.assertTrue(health.compatibility["provider_neutral"])


if __name__ == "__main__":
    unittest.main()

import unittest

from app.models.product_availability import ProductAvailability, ProductAvailabilityStatus
from app.models.product_business import ProductBusinessHealth, ProductBusinessSnapshot
from app.models.product_catalog_management import (
    ProductCatalogHealth,
    ProductCatalogHealthStatus,
    ProductCatalogRecommendation,
    ProductCatalogRecommendationType,
)
from app.models.product_composition import (
    ProductComposition,
    ProductCompositionRecommendation,
    ProductCompositionType,
)
from app.models.product_improvement import (
    ProductImprovementPriority,
    ProductImprovementType,
)
from app.models.product_performance import (
    ProductPerformance,
    ProductPerformanceStatus,
    ProductPerformanceSummary,
)
from app.services.product_improvement_service import ProductImprovementService


class ProductImprovementServiceTests(unittest.TestCase):
    def test_product_improvement_generation(self):
        improvement = ProductImprovementService().build_improvement(
            product_business_snapshot=ProductBusinessSnapshot(
                product_id="product-1",
                product_health=ProductBusinessHealth.HEALTHY,
            )
        )

        self.assertEqual(improvement.product_id, "product-1")
        self.assertEqual(
            improvement.recommendations[0].improvement_type,
            ProductImprovementType.PROMOTE_STRONG_PERFORMER,
        )
        self.assertTrue(improvement.compatibility["advisory_only"])
        self.assertFalse(improvement.compatibility["modifies_products"])

    def test_performance_integration(self):
        improvement = ProductImprovementService().build_improvement(
            performance=ProductPerformance(
                product_id="product-1",
                status=ProductPerformanceStatus.UNDERPERFORMING,
                summary=ProductPerformanceSummary(
                    sales_performance={"count": 4, "success_rate": 0.0}
                ),
            )
        )

        types = {item.improvement_type for item in improvement.recommendations}
        self.assertIn(ProductImprovementType.REFRESH_PRODUCT, types)
        self.assertIn(ProductImprovementType.RETIRE_PRODUCT, types)
        self.assertEqual(
            improvement.recommendations[0].priority,
            ProductImprovementPriority.HIGH,
        )

    def test_availability_integration(self):
        improvement = ProductImprovementService().build_improvement(
            availability=ProductAvailability(
                product_id="product-1",
                status=ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK,
                media_link_status="PENDING",
            )
        )

        recommendation = improvement.recommendations[0]
        self.assertEqual(
            recommendation.improvement_type,
            ProductImprovementType.FIX_AVAILABILITY,
        )
        self.assertEqual(recommendation.recommended_next_action, "Paste Media Link")

    def test_catalog_health_integration(self):
        improvement = ProductImprovementService().build_improvement(
            catalog_health=ProductCatalogHealth(
                status=ProductCatalogHealthStatus.INCOMPLETE,
                recommendations=(
                    ProductCatalogRecommendation(
                        recommendation_type=(
                            ProductCatalogRecommendationType.CREATE_FREE_PREVIEW
                        ),
                        label="Create FREE Preview",
                    ),
                    ProductCatalogRecommendation(
                        recommendation_type=ProductCatalogRecommendationType.CREATE_BUNDLE,
                        label="Create Bundle",
                    ),
                ),
            )
        )

        types = {item.improvement_type for item in improvement.recommendations}
        self.assertIn(ProductImprovementType.CREATE_FREE_PREVIEW, types)
        self.assertIn(ProductImprovementType.CREATE_BUNDLE, types)

    def test_composition_integration(self):
        improvement = ProductImprovementService().build_improvement(
            composition_recommendations=(
                ProductCompositionRecommendation(
                    composition=ProductComposition(
                        composition_type=ProductCompositionType.FREE_PREVIEW,
                        included_asset_ids=(101,),
                        cover_asset_id=101,
                    ),
                    label="FREE Preview composition",
                    confidence=0.8,
                ),
                ProductCompositionRecommendation(
                    composition=ProductComposition(
                        composition_type=ProductCompositionType.BUNDLE,
                        included_asset_ids=(101, 102),
                    ),
                    label="Bundle composition",
                    confidence=0.7,
                ),
            )
        )

        types = {item.improvement_type for item in improvement.recommendations}
        self.assertIn(ProductImprovementType.IMPROVE_FREE_PREVIEW, types)
        self.assertIn(ProductImprovementType.IMPROVE_COMPOSITION, types)

    def test_backward_compatibility(self):
        improvement = ProductImprovementService().build_improvement(
            product_business_snapshot={
                "product_id": "legacy-product",
                "product_health": "UNDERPERFORMING",
            },
            availability={
                "product_id": "legacy-product",
                "status": "NEEDS_ATTENTION",
                "media_link_status": "FAILED",
            },
            performance={
                "product_id": "legacy-product",
                "status": "MONITOR",
            },
            composition_recommendations=(
                {
                    "composition_type": "FREE_PREVIEW",
                    "included_asset_ids": (1,),
                    "cover_asset_id": 1,
                    "confidence": 0.5,
                },
            ),
        )

        self.assertEqual(improvement.product_id, "legacy-product")
        self.assertEqual(
            improvement.recommendations[0].priority,
            ProductImprovementPriority.CRITICAL,
        )
        self.assertTrue(improvement.compatibility["provider_neutral"])

    def test_advisory_only_behavior(self):
        improvement = ProductImprovementService().build_improvement()

        self.assertFalse(improvement.compatibility["creates_products"])
        self.assertFalse(improvement.compatibility["archives_products"])
        self.assertFalse(improvement.compatibility["publishes_products"])
        self.assertFalse(improvement.compatibility["executes_telegram"])
        self.assertFalse(improvement.compatibility["records_business_learning"])
        self.assertEqual(
            improvement.recommendations[0].improvement_type,
            ProductImprovementType.MONITOR_PRODUCT,
        )


if __name__ == "__main__":
    unittest.main()

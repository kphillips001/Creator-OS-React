import unittest
from types import SimpleNamespace

from app.models.business_learning import (
    BusinessOutcome,
    BusinessOutcomeType,
    PerformanceMetric,
    PerformanceSnapshot,
)
from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CustomerIntelligenceSnapshot,
)
from app.models.product_business import ProductBusinessHealth, ProductBusinessSnapshot
from app.models.product_performance import (
    ProductPerformance,
    ProductPerformanceStatus,
)
from app.services.business_learning_service import BusinessLearningService
from app.services.product_performance_service import ProductPerformanceService


class ProductPerformanceServiceTests(unittest.TestCase):
    def test_product_performance_generation(self):
        performance = ProductPerformance(product_id="product-1")

        self.assertEqual(performance.product_id, "product-1")
        self.assertEqual(performance.status, ProductPerformanceStatus.NO_DATA)
        self.assertEqual(performance.next_recommended_action, "Monitor")

    def test_business_learning_integration(self):
        performance = ProductPerformanceService().build_performance(
            product=SimpleNamespace(id="product-1"),
            business_outcomes=[
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_OFFERED.value,
                    product_id="product-1",
                ),
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                    product_id="product-1",
                ),
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                    product_id="product-1",
                ),
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.CTA_CLICKED.value,
                    product_id="product-1",
                ),
            ],
        )

        self.assertEqual(performance.status, ProductPerformanceStatus.STRONG_PERFORMER)
        self.assertEqual(performance.next_recommended_action, "Strong Performer")
        self.assertGreater(performance.summary.conversion_rate, 0)
        self.assertEqual(
            performance.summary.sales_performance["metric_type"],
            "product_performance",
        )
        self.assertTrue(performance.compatibility["business_learning_consumed"])
        self.assertFalse(performance.compatibility["records_business_learning"])

    def test_customer_intelligence_integration(self):
        customer = CustomerIntelligenceSnapshot(
            commerce_memory=CustomerCommerceMemory(
                products_offered=("product-1",),
                products_purchased=("product-1",),
                delivered_paid_products=("product-1",),
            )
        )
        performance = ProductPerformanceService().build_performance(
            product=SimpleNamespace(id="product-1"),
            performance_snapshot=PerformanceSnapshot(
                metrics=(
                    PerformanceMetric(
                        metric_name="Product performance",
                        metric_type="product_performance",
                        count=3,
                        success_count=2,
                        failure_count=0,
                        neutral_count=1,
                        success_rate=2 / 3,
                        confidence=0.6,
                    ),
                )
            ),
            customer_snapshot=customer,
        )

        self.assertEqual(performance.summary.customer_reach["customer_count"], 1)
        self.assertEqual(performance.summary.customer_reach["purchased_count"], 1)
        self.assertEqual(performance.status, ProductPerformanceStatus.STRONG_PERFORMER)
        self.assertTrue(performance.compatibility["customer_intelligence_consumed"])

    def test_product_business_integration(self):
        business = ProductBusinessSnapshot(
            product_id="product-1",
            customer_reach={"customer_count": 4, "has_customer_reach": True},
            product_health=ProductBusinessHealth.NEEDS_ATTENTION,
        )

        performance = ProductPerformanceService().build_performance(
            product_business_snapshot=business,
            performance_snapshot=PerformanceSnapshot(
                metrics=(
                    PerformanceMetric(
                        metric_name="Product performance",
                        metric_type="product_performance",
                        count=4,
                        success_count=2,
                        failure_count=1,
                        neutral_count=1,
                        success_rate=0.5,
                        confidence=0.4,
                    ),
                )
            ),
        )

        self.assertEqual(performance.product_id, "product-1")
        self.assertEqual(performance.status, ProductPerformanceStatus.NEEDS_REVIEW)
        self.assertEqual(performance.next_recommended_action, "Needs Review")
        self.assertEqual(performance.summary.customer_reach["customer_count"], 4)
        self.assertTrue(performance.compatibility["product_business_consumed"])

    def test_underperforming_and_monitor_recommendations(self):
        service = ProductPerformanceService()
        underperforming = service.build_performance(
            product=SimpleNamespace(id="weak"),
            performance_snapshot=PerformanceSnapshot(
                metrics=(
                    PerformanceMetric(
                        metric_name="Product performance",
                        metric_type="product_performance",
                        count=4,
                        success_count=0,
                        failure_count=3,
                        neutral_count=1,
                        success_rate=0.0,
                        confidence=0.4,
                    ),
                )
            ),
        )
        monitor = service.build_performance(
            product=SimpleNamespace(id="new"),
            performance_snapshot=PerformanceSnapshot(
                metrics=(
                    PerformanceMetric(
                        metric_name="Product performance",
                        metric_type="product_performance",
                        count=1,
                        success_count=1,
                        success_rate=1.0,
                        confidence=0.1,
                    ),
                )
            ),
        )

        self.assertEqual(
            underperforming.status,
            ProductPerformanceStatus.UNDERPERFORMING,
        )
        self.assertEqual(underperforming.next_recommended_action, "Underperforming")
        self.assertEqual(monitor.status, ProductPerformanceStatus.MONITOR)
        self.assertEqual(monitor.next_recommended_action, "Monitor")

    def test_backward_compatibility_mapping_inputs(self):
        snapshot = BusinessLearningService().build_performance_snapshot(
            outcomes=[
                {"outcome_type": "PRODUCT_OFFERED", "product_id": "legacy"},
                {"outcome_type": "PRODUCT_PURCHASED", "product_id": "legacy"},
                {"outcome_type": "PRODUCT_DECLINED", "product_id": "legacy"},
            ]
        )

        performance = ProductPerformanceService().build_performance(
            product_business_snapshot={
                "product_id": "legacy",
                "customer_reach": {
                    "customer_count": 2,
                    "has_customer_reach": True,
                },
            },
            learning_context={"performance_snapshot": snapshot},
        )

        self.assertEqual(performance.product_id, "legacy")
        self.assertEqual(performance.summary.sales_performance["count"], 3)
        self.assertEqual(performance.summary.customer_reach["customer_count"], 2)
        self.assertTrue(performance.compatibility["provider_neutral"])
        self.assertFalse(performance.compatibility["generates_product_strategy"])


if __name__ == "__main__":
    unittest.main()

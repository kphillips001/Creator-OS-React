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
from app.models.creator_workflow import CreatorWorkflowSnapshot, CreatorWorkflowStage
from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessHealth,
    ProductBusinessSnapshot,
)
from app.models.product_lifecycle import ProductLifecycleStage
from app.models.publishing_automation import PublishingAutomationState
from app.services.business_learning_service import BusinessLearningService
from app.services.product_business_service import ProductBusinessService
from app.services.product_lifecycle_service import ProductLifecycleService
from app.services.publishing_automation_service import PublishingAutomationService


def workflow_snapshot(**kwargs):
    defaults = {
        "workflow_id": "product:product-1",
        "product_id": "product-1",
        "current_stage": CreatorWorkflowStage.IMPORTED,
        "stages": (),
    }
    defaults.update(kwargs)
    return CreatorWorkflowSnapshot(**defaults)


class ProductBusinessServiceTests(unittest.TestCase):
    def test_product_business_snapshot_creation(self):
        snapshot = ProductBusinessSnapshot(
            product_id="product-1",
            product_name="Premium Set",
            product_type="PHOTO_SET",
            delivery_type="PAID",
        )

        self.assertEqual(snapshot.product_id, "product-1")
        self.assertEqual(snapshot.availability, ProductBusinessAvailability.UNKNOWN)
        self.assertEqual(
            snapshot.next_recommended_business_action,
            "No Product Business Action",
        )

    def test_product_business_service_aggregation(self):
        service = ProductBusinessService()
        product = SimpleNamespace(
            id="product-1",
            display_name="Premium Set",
            product_type=SimpleNamespace(value="PHOTO_SET"),
            delivery_type=SimpleNamespace(value="PAID"),
            status=SimpleNamespace(value="ACTIVE"),
        )
        lifecycle = ProductLifecycleService().build_lifecycle(
            workflow_snapshot(product_status="ACTIVE", telegram_ready=True)
        )
        publishing = PublishingAutomationService().build_status(lifecycle=lifecycle)
        performance = PerformanceSnapshot(
            metrics=(
                PerformanceMetric(
                    metric_name="Product performance",
                    metric_type="product_performance",
                    count=4,
                    success_count=3,
                    failure_count=1,
                    success_rate=0.75,
                    confidence=0.8,
                ),
            )
        )

        snapshot = service.build_snapshot(
            product=product,
            lifecycle=lifecycle,
            publishing_status=publishing,
            performance_snapshot=performance,
        )

        self.assertEqual(snapshot.product_id, "product-1")
        self.assertEqual(snapshot.product_name, "Premium Set")
        self.assertEqual(snapshot.availability, ProductBusinessAvailability.TELEGRAM_READY)
        self.assertEqual(snapshot.product_health, ProductBusinessHealth.HEALTHY)
        self.assertTrue(snapshot.compatibility["aggregation_only"])
        self.assertFalse(snapshot.compatibility["modifies_products"])

    def test_product_lifecycle_integration(self):
        service = ProductBusinessService()
        snapshot = service.build_snapshot(
            workflow_snapshot=workflow_snapshot(approval_status="APPROVED")
        )

        self.assertIsNotNone(snapshot.lifecycle)
        self.assertEqual(snapshot.lifecycle.stage, ProductLifecycleStage.APPROVED)
        self.assertEqual(
            snapshot.next_recommended_business_action,
            "Ready to Publish",
        )

    def test_publishing_integration(self):
        service = ProductBusinessService()
        snapshot = service.build_snapshot(
            workflow_snapshot=workflow_snapshot(
                publishing_status="WAITING_FOR_MEDIA_LINK",
                media_link_status="PENDING",
            )
        )

        self.assertEqual(
            snapshot.publishing_status.state,
            PublishingAutomationState.WAITING_FOR_MEDIA_LINK,
        )
        self.assertEqual(
            snapshot.availability,
            ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK,
        )
        self.assertTrue(snapshot.publishing_readiness["manual_media_link_required"])
        self.assertEqual(snapshot.next_recommended_business_action, "Paste Media Link")

    def test_business_learning_integration(self):
        service = ProductBusinessService()
        learning = BusinessLearningService().build_product_learning_context(
            product_reference="product-1",
            outcomes=[
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_OFFERED.value,
                    product_id="product-1",
                ),
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_DECLINED.value,
                    product_id="product-1",
                ),
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PRODUCT_DECLINED.value,
                    product_id="product-1",
                ),
            ],
        )

        snapshot = service.build_snapshot(
            product=SimpleNamespace(id="product-1", status="ACTIVE"),
            learning_context=learning,
        )

        self.assertTrue(snapshot.performance_summary["has_performance_history"])
        self.assertTrue(snapshot.performance_summary["underperforming"])
        self.assertEqual(snapshot.product_health, ProductBusinessHealth.UNDERPERFORMING)
        self.assertTrue(snapshot.compatibility["business_learning_consumed"])

    def test_customer_intelligence_integration(self):
        service = ProductBusinessService()
        customer = CustomerIntelligenceSnapshot(
            commerce_memory=CustomerCommerceMemory(
                products_offered=("product-1",),
                products_purchased=("product-1",),
                delivered_paid_products=("product-1",),
            )
        )

        snapshot = service.build_snapshot(
            product=SimpleNamespace(id="product-1"),
            customer_snapshot=customer,
        )

        self.assertEqual(snapshot.customer_reach["customer_count"], 1)
        self.assertEqual(snapshot.customer_reach["offered_count"], 1)
        self.assertEqual(snapshot.customer_reach["purchased_count"], 1)
        self.assertEqual(snapshot.customer_reach["delivered_count"], 1)
        self.assertTrue(snapshot.compatibility["customer_intelligence_consumed"])

    def test_backward_compatibility_mapping_inputs(self):
        service = ProductBusinessService()
        snapshot = service.build_snapshot(
            product={
                "id": "legacy-product",
                "display_name": "Legacy Product",
                "product_type": "STORY",
                "delivery_type": "FREE",
                "status": "DRAFT",
            },
            lifecycle={
                "workflow_id": "product:legacy",
                "product_id": "legacy-product",
                "current_stage": "IMPORTED",
                "approval_status": "READY_TO_PUBLISH",
                "stages": (),
            },
            publishing_status={
                "publishing_status": "QUEUED",
                "media_link_status": "PENDING",
            },
        )

        self.assertEqual(snapshot.product_id, "legacy-product")
        self.assertEqual(snapshot.product_type, "STORY")
        self.assertEqual(snapshot.delivery_type, "FREE")
        self.assertEqual(
            snapshot.availability,
            ProductBusinessAvailability.WAITING_FOR_MEDIA_LINK,
        )
        self.assertTrue(snapshot.compatibility["provider_neutral"])


if __name__ == "__main__":
    unittest.main()

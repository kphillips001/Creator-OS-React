import unittest

from app.models.commerce_execution import CommerceExecutionResult
from app.models.delivery_management import (
    DeliveryManagement,
    DeliveryPriority,
    DeliveryRecommendationType,
)
from app.models.product_availability import (
    ProductAvailability,
    ProductAvailabilityStatus,
)
from app.models.telegram_business import TelegramBusinessSummary
from app.services.conversation_operations_service import ConversationOperationsService
from app.services.delivery_management_service import DeliveryManagementService
from app.services.sales_management_service import SalesManagementService
from app.test_conversation_operations_service import (
    FakeTelegramBusinessService,
    business_snapshot,
)
from app.test_telegram_business_service import (
    commerce_strategy_result,
    customer_snapshot,
    learning_context,
    product_business_snapshot,
    telegram_commerce_result,
)


class ForbiddenPublishingService:
    def create_publishing_job(self, *args, **kwargs):
        raise AssertionError("DeliveryManagementService must not publish Products")

    def upload_asset_media_item_for_job(self, *args, **kwargs):
        raise AssertionError("DeliveryManagementService must not publish Products")


class ForbiddenCommerceExecutionService:
    def execute(self, *args, **kwargs):
        raise AssertionError("DeliveryManagementService must not execute commerce")

    def execute_runtime_intent(self, *args, **kwargs):
        raise AssertionError("DeliveryManagementService must not execute Telegram")


class ForbiddenCustomerIntelligenceService:
    def update_relationship(self, *args, **kwargs):
        raise AssertionError(
            "DeliveryManagementService must not modify Customer Intelligence"
        )


class ForbiddenProductAvailabilityService:
    def publish(self, *args, **kwargs):
        raise AssertionError("DeliveryManagementService must not publish Products")


def available_product():
    return ProductAvailability(
        product_id="product-1",
        status=ProductAvailabilityStatus.AVAILABLE,
        product_business_snapshot=product_business_snapshot(),
        telegram_ready=True,
        available_for_customers=True,
        evidence={"business_availability": "TELEGRAM_READY"},
    )


class DeliveryManagementServiceTests(unittest.TestCase):
    def test_generates_media_link_delivery_recommendation(self):
        snapshot = business_snapshot(
            products=(
                {
                    "product_id": "product-1",
                    "product_type": "story_product",
                    "delivery_type": "PAID",
                    "product_health": "HEALTHY",
                    "availability": "TELEGRAM_READY",
                },
            )
        )
        operation = ConversationOperationsService().build_operation(
            telegram_business_snapshot=snapshot
        )
        sales = SalesManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            commerce_strategy_result=commerce_strategy_result(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )
        service = DeliveryManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            product_availability=available_product(),
            customer_snapshot=customer_snapshot(),
            commerce_execution_result=CommerceExecutionResult(
                status="deferred",
                executed=False,
                provider="telegram",
            ),
        )

        self.assertIsInstance(management, DeliveryManagement)
        self.assertEqual(management.customer_id, "telegram-customer-1")
        self.assertEqual(
            management.recommendation.recommendation_type,
            DeliveryRecommendationType.SEND_MEDIA_LINK,
        )
        self.assertEqual(management.recommendation.priority, DeliveryPriority.HIGH)
        self.assertEqual(management.recommendation.product_reference, "product-1")
        self.assertEqual(management.recommendation.offer_reference, "offer-1")
        self.assertEqual(management.recommendation.delivery_method, "paid_media_link")
        self.assertEqual(
            management.recommendation.supporting_evidence["commerce_execution"][
                "status"
            ],
            "deferred",
        )

    def test_prevents_duplicate_delivery_from_customer_history(self):
        snapshot = business_snapshot(
            delivery_history={
                "delivery_count": 1,
                "paid_deliveries": ("product-1",),
                "duplicate_prevention_signals": ("product:product-1",),
            }
        )
        service = DeliveryManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            product_availability=available_product(),
            product_business_snapshot=product_business_snapshot(),
            customer_snapshot=customer_snapshot(),
        )

        self.assertEqual(
            management.recommendation.recommendation_type,
            DeliveryRecommendationType.PREVENT_DUPLICATE_DELIVERY,
        )
        self.assertEqual(management.recommendation.priority, DeliveryPriority.CRITICAL)
        self.assertEqual(
            management.recommendation.recommended_next_action,
            "Prevent Duplicate Delivery",
        )
        self.assertIn(
            "product-1",
            management.recommendation.supporting_evidence["customer_intelligence"][
                "delivered_refs"
            ],
        )

    def test_waits_when_product_availability_is_not_ready(self):
        snapshot = business_snapshot(
            telegram_commerce={"blocked": False},
            operation_status="IDLE",
            summary=TelegramBusinessSummary(
                relationship_stage="engaged",
                conversation_state="experience",
                current_experience_id="experience-1",
                current_product_ids=("product-1",),
                active_offer_ids=("offer-1",),
                operation_status="IDLE",
            ),
        )
        waiting = ProductAvailability(
            product_id="product-1",
            status=ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK,
            telegram_ready=False,
            available_for_customers=False,
        )
        service = DeliveryManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            product_availability=waiting,
            product_business_snapshot=product_business_snapshot(),
        )

        self.assertEqual(
            management.recommendation.recommendation_type,
            DeliveryRecommendationType.WAIT,
        )
        self.assertEqual(
            management.recommendation.recommended_next_action,
            "Wait for Media Link",
        )
        self.assertEqual(
            management.recommendation.supporting_evidence["product_availability"][
                "status"
            ],
            ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK.value,
        )

    def test_integrates_with_existing_read_services(self):
        snapshot = business_snapshot()
        telegram_business = FakeTelegramBusinessService(snapshot)
        conversation_operations = ConversationOperationsService(
            telegram_business_service=telegram_business
        )
        sales_management = SalesManagementService(
            telegram_business_service=telegram_business,
            conversation_operations_service=conversation_operations,
        )
        service = DeliveryManagementService(
            telegram_business_service=telegram_business,
            conversation_operations_service=conversation_operations,
            sales_management_service=sales_management,
        )

        management = service.build_management(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            customer_snapshot=customer_snapshot(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )

        self.assertEqual(management.customer_id, "telegram-customer-1")
        self.assertEqual(len(telegram_business.calls), 1)
        self.assertEqual(
            telegram_business.calls[0]["customer_id"],
            "telegram-customer-1",
        )

    def test_backward_compatible_mapping_inputs(self):
        snapshot = {
            "customer_id": "customer-map",
            "provider": "telegram",
            "relationship": {"stage": "engaged"},
            "conversation": {"state": "experience", "commerce_state": "delivery"},
            "summary": {
                "current_product_ids": ("bundle-1",),
                "active_offer_ids": ("offer-bundle",),
            },
            "products": (
                {
                    "product_id": "bundle-1",
                    "product_type": "bundle",
                    "delivery_type": "PAID",
                    "availability": "TELEGRAM_READY",
                },
            ),
            "active_offers": (
                {
                    "offer_id": "offer-bundle",
                    "product_id": "bundle-1",
                    "active": True,
                },
            ),
            "delivery_history": {"delivery_count": 0},
            "telegram_commerce": {"blocked": False, "delivery_method": None},
            "operation_status": "DEFERRED",
            "business_health": "TELEGRAM_READY",
        }
        availability = {
            "product_id": "bundle-1",
            "status": "AVAILABLE",
            "available_for_customers": True,
            "telegram_ready": True,
        }
        service = DeliveryManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            product_availability=availability,
            sales_management={
                "recommendation": {
                    "recommendation_type": "OFFER_BUNDLE",
                    "priority": "HIGH",
                    "confidence": 0.7,
                    "product_reference": "bundle-1",
                    "offer_reference": "offer-bundle",
                }
            },
        )

        self.assertEqual(management.customer_id, "customer-map")
        self.assertEqual(
            management.recommendation.recommendation_type,
            DeliveryRecommendationType.DELIVER_BUNDLE,
        )
        self.assertEqual(management.current_product_ids, ("bundle-1",))

    def test_preserves_recommendation_only_ownership_boundaries(self):
        service = DeliveryManagementService(
            publishing_service=ForbiddenPublishingService(),
            commerce_execution_service=ForbiddenCommerceExecutionService(),
            customer_intelligence_service=ForbiddenCustomerIntelligenceService(),
            product_availability_service=ForbiddenProductAvailabilityService(),
        )

        management = service.build_management(
            telegram_business_snapshot=business_snapshot(),
            conversation_operation=ConversationOperationsService().build_operation(
                telegram_business_snapshot=business_snapshot()
            ),
            sales_management=SalesManagementService().build_management(
                telegram_business_snapshot=business_snapshot()
            ),
            product_availability=available_product(),
        )

        compatibility = management.compatibility
        self.assertTrue(compatibility["read_only"])
        self.assertTrue(compatibility["aggregation_only"])
        self.assertTrue(compatibility["recommendation_only"])
        self.assertFalse(compatibility["executes_telegram"])
        self.assertFalse(compatibility["sends_media"])
        self.assertFalse(compatibility["sends_media_links"])
        self.assertFalse(compatibility["publishes_products"])
        self.assertFalse(compatibility["modifies_products"])
        self.assertFalse(compatibility["modifies_customer_intelligence"])
        self.assertFalse(compatibility["records_business_learning"])
        self.assertEqual(
            compatibility["commerce_execution_owner"],
            "CommerceExecutionService",
        )
        self.assertEqual(compatibility["publishing_owner"], "PublishingService")
        self.assertEqual(
            compatibility["customer_intelligence_owner"],
            "CustomerIntelligenceCompatibilityAdapter",
        )


if __name__ == "__main__":
    unittest.main()

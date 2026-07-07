import unittest

from app.models.conversation_operations import ConversationOperationStatus
from app.models.sales_management import (
    SalesManagement,
    SalesPriority,
    SalesRecommendationType,
)
from app.models.telegram_business import TelegramBusinessSummary
from app.services.conversation_operations_service import ConversationOperationsService
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


class ForbiddenCommerceStrategyService:
    def recommend(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not generate strategy")


class ForbiddenProductBusinessService:
    def build_strategy(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not generate product strategy")

    def update_product(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not modify Products")


class ForbiddenBusinessLearningService:
    def record_business_outcome(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not record learning")


class ForbiddenTelegramRuntime:
    def execute(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not execute Telegram")

    def process_message(self, *args, **kwargs):
        raise AssertionError("SalesManagementService must not generate responses")


class SalesManagementServiceTests(unittest.TestCase):
    def test_generates_sales_recommendation_from_existing_intelligence(self):
        snapshot = business_snapshot()
        operation = ConversationOperationsService().build_operation(
            telegram_business_snapshot=snapshot
        )
        service = SalesManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            customer_snapshot=customer_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )

        self.assertIsInstance(management, SalesManagement)
        self.assertEqual(management.customer_id, "telegram-customer-1")
        self.assertEqual(
            management.recommendation.recommendation_type,
            SalesRecommendationType.OFFER_PREMIUM_PRODUCT,
        )
        self.assertEqual(management.recommendation.priority, SalesPriority.HIGH)
        self.assertEqual(management.recommendation.confidence, 0.8)
        self.assertEqual(
            management.recommendation.product_reference,
            "product-1",
        )
        self.assertEqual(management.recommendation.offer_reference, "offer-1")
        self.assertEqual(
            management.recommendation.supporting_evidence["commerce_strategy"][
                "objectives"
            ],
            ("Sequence premium offer.",),
        )
        self.assertFalse(
            management.recommendation.supporting_evidence["commerce_strategy"][
                "generated_by_sales_management"
            ]
        )

    def test_delays_selling_when_customer_or_conversation_is_waiting(self):
        snapshot = business_snapshot(
            active_offers=(),
            telegram_commerce={"blocked": False},
            operation_status="IDLE",
            metadata={"waiting_for_customer": True},
            summary=TelegramBusinessSummary(
                relationship_stage="engaged",
                conversation_state="chat",
                operation_status="IDLE",
                next_recommended_action="Wait",
            ),
        )
        service = SalesManagementService()

        management = service.build_management(telegram_business_snapshot=snapshot)

        self.assertEqual(
            management.conversation_status,
            ConversationOperationStatus.WAITING_FOR_CUSTOMER.value,
        )
        self.assertEqual(
            management.recommendation.recommendation_type,
            SalesRecommendationType.DELAY_SELLING,
        )
        self.assertEqual(
            management.recommendation.recommended_next_action,
            "Delay Selling",
        )

    def test_continues_experience_for_active_experience_without_sales_signal(self):
        snapshot = business_snapshot(
            active_offers=(),
            products=(),
            conversation={"state": "experience", "commerce_state": "conversation"},
            telegram_commerce={"blocked": False},
            operation_status="IDLE",
            experience={
                "current_experience_id": "experience-1",
                "experience_state": "active",
                "progress_percentage": 45,
                "next_recommended_experience_action": "continue_experience",
            },
            summary=TelegramBusinessSummary(
                relationship_stage="engaged",
                conversation_state="experience",
                current_experience_id="experience-1",
                operation_status="IDLE",
                next_recommended_action="continue_experience",
            ),
        )
        service = SalesManagementService()

        management = service.build_management(telegram_business_snapshot=snapshot)

        self.assertEqual(
            management.conversation_status,
            ConversationOperationStatus.EXPERIENCE_ACTIVE.value,
        )
        self.assertEqual(
            management.recommendation.recommendation_type,
            SalesRecommendationType.CONTINUE_EXPERIENCE,
        )

    def test_integrates_with_telegram_business_and_conversation_services(self):
        snapshot = business_snapshot()
        telegram_business = FakeTelegramBusinessService(snapshot)
        conversation_operations = ConversationOperationsService(
            telegram_business_service=telegram_business
        )
        service = SalesManagementService(
            telegram_business_service=telegram_business,
            conversation_operations_service=conversation_operations,
        )

        management = service.build_management(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            customer_snapshot=customer_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
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
            "relationship": {
                "stage": "new",
                "primary_recommendation": "Build relationship",
            },
            "conversation": {"state": "chat", "commerce_state": "conversation"},
            "summary": {
                "relationship_stage": "new",
                "current_product_ids": ("bundle-1",),
                "active_offer_ids": (),
            },
            "products": (
                {
                    "product_id": "bundle-1",
                    "product_type": "bundle",
                    "delivery_type": "PAID",
                    "availability": "TELEGRAM_READY",
                    "product_health": "HEALTHY",
                },
            ),
            "active_offers": (),
            "delivery_history": {"delivery_count": 0},
            "telegram_commerce": {"blocked": False},
            "operation_status": "IDLE",
            "business_health": "TELEGRAM_READY",
        }
        service = SalesManagementService()

        management = service.build_management(telegram_business_snapshot=snapshot)

        self.assertEqual(management.customer_id, "customer-map")
        self.assertEqual(
            management.recommendation.recommendation_type,
            SalesRecommendationType.OFFER_BUNDLE,
        )
        self.assertEqual(management.current_product_ids, ("bundle-1",))

    def test_preserves_recommendation_only_ownership_boundaries(self):
        service = SalesManagementService(
            commerce_strategy_service=ForbiddenCommerceStrategyService(),
            product_business_service=ForbiddenProductBusinessService(),
            business_learning_service=ForbiddenBusinessLearningService(),
        )

        management = service.build_management(
            telegram_business_snapshot=business_snapshot(),
            conversation_operation=ConversationOperationsService().build_operation(
                telegram_business_snapshot=business_snapshot()
            ),
            commerce_strategy_result=commerce_strategy_result(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
            metadata={"runtime": ForbiddenTelegramRuntime()},
        )

        compatibility = management.compatibility
        self.assertTrue(compatibility["read_only"])
        self.assertTrue(compatibility["aggregation_only"])
        self.assertTrue(compatibility["recommendation_only"])
        self.assertFalse(compatibility["executes_telegram"])
        self.assertFalse(compatibility["generates_responses"])
        self.assertFalse(compatibility["modifies_products"])
        self.assertFalse(compatibility["generates_product_strategy"])
        self.assertFalse(compatibility["generates_commerce_strategy"])
        self.assertFalse(compatibility["publishes_products"])
        self.assertFalse(compatibility["records_business_learning"])
        self.assertFalse(compatibility["modifies_customer_intelligence"])
        self.assertEqual(
            compatibility["commerce_strategy_owner"],
            "CommerceStrategyService",
        )
        self.assertEqual(
            compatibility["product_business_owner"],
            "ProductBusinessService",
        )
        self.assertEqual(
            compatibility["customer_intelligence_owner"],
            "CustomerIntelligenceService",
        )


if __name__ == "__main__":
    unittest.main()

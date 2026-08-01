import unittest
from dataclasses import replace

from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CustomerRelationshipStage,
)
from app.models.relationship_management import (
    RelationshipHealth,
    RelationshipManagement,
    RelationshipPriority,
    RelationshipRecommendationType,
)
from app.models.telegram_business import TelegramBusinessSummary
from app.services.conversation_operations_service import ConversationOperationsService
from app.services.delivery_management_service import DeliveryManagementService
from app.services.relationship_management_service import RelationshipManagementService
from app.services.sales_management_service import SalesManagementService
from app.test_conversation_operations_service import (
    FakeTelegramBusinessService,
    business_snapshot,
)
from app.test_delivery_management_service import available_product
from app.test_telegram_business_service import (
    commerce_strategy_result,
    customer_snapshot,
    learning_context,
    product_business_snapshot,
    telegram_commerce_result,
)


class ForbiddenCustomerIntelligenceService:
    def update_relationship(self, *args, **kwargs):
        raise AssertionError(
            "RelationshipManagementService must not modify Customer Intelligence"
        )

    def enrich_customer_snapshot(self, *args, **kwargs):
        raise AssertionError(
            "RelationshipManagementService must not modify Customer Intelligence"
        )


class ForbiddenBusinessLearningService:
    def record_business_outcome(self, *args, **kwargs):
        raise AssertionError("RelationshipManagementService must not record learning")


class ForbiddenTelegramRuntime:
    def execute(self, *args, **kwargs):
        raise AssertionError("RelationshipManagementService must not execute Telegram")

    def process_message(self, *args, **kwargs):
        raise AssertionError(
            "RelationshipManagementService must not generate responses"
        )


class RelationshipManagementServiceTests(unittest.TestCase):
    def test_generates_increase_selling_recommendation(self):
        snapshot = business_snapshot()
        operation = ConversationOperationsService().build_operation(
            telegram_business_snapshot=snapshot
        )
        sales = SalesManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            customer_snapshot=customer_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )
        delivery = DeliveryManagementService().build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            product_availability=available_product(),
            customer_snapshot=customer_snapshot(),
        )
        service = RelationshipManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            delivery_management=delivery,
            customer_snapshot=customer_snapshot(),
            learning_context=learning_context(),
        )

        self.assertIsInstance(management, RelationshipManagement)
        self.assertEqual(management.customer_id, "telegram-customer-1")
        self.assertEqual(management.relationship_health, RelationshipHealth.SELLING_READY)
        self.assertEqual(
            management.recommendation.recommendation_type,
            RelationshipRecommendationType.INCREASE_SELLING,
        )
        self.assertEqual(management.recommendation.priority, RelationshipPriority.HIGH)
        self.assertEqual(management.recommendation.confidence, 0.8)
        self.assertEqual(
            management.recommendation.supporting_evidence["sales_management"][
                "recommendation_type"
            ],
            "OFFER_PREMIUM_PRODUCT",
        )
        self.assertEqual(
            management.recommendation.supporting_evidence["delivery_management"][
                "recommendation_type"
            ],
            "SEND_MEDIA_LINK",
        )

    def test_detects_vip_customer_from_customer_intelligence(self):
        customer = customer_snapshot()
        vip_customer = replace(
            customer,
            relationship_stage=CustomerRelationshipStage.VIP,
            commerce_memory=replace(
                customer.commerce_memory,
                products_purchased=("product-a", "product-b", "product-c"),
                customer_spending_summary={"total_spend_cents": 75000},
            ),
        )
        snapshot = business_snapshot(
            relationship={
                "stage": "vip",
                "engagement_level": "high",
                "engagement_score": 96,
                "commerce_maturity": "buyer_ready",
            }
        )
        service = RelationshipManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            customer_snapshot=vip_customer,
            learning_context=learning_context(),
        )

        self.assertEqual(
            management.relationship_health,
            RelationshipHealth.VIP_OPPORTUNITY,
        )
        self.assertEqual(
            management.recommendation.recommendation_type,
            RelationshipRecommendationType.VIP_OPPORTUNITY,
        )
        self.assertEqual(
            management.recommendation.recommended_next_action,
            "VIP Opportunity",
        )

    def test_recommends_re_engagement_for_disengaged_customer(self):
        snapshot = business_snapshot(
            relationship={
                "stage": "dormant",
                "engagement_level": "none",
                "engagement_score": 0,
                "commerce_maturity": "none",
            },
            active_offers=(),
            telegram_commerce={"blocked": False},
            operation_status="IDLE",
            summary=TelegramBusinessSummary(
                relationship_stage="dormant",
                conversation_state="chat",
                operation_status="IDLE",
            ),
        )
        service = RelationshipManagementService()

        management = service.build_management(telegram_business_snapshot=snapshot)

        self.assertEqual(management.relationship_health, RelationshipHealth.DISENGAGED)
        self.assertEqual(
            management.recommendation.recommendation_type,
            RelationshipRecommendationType.RE_ENGAGE_CUSTOMER,
        )
        self.assertEqual(
            management.recommendation.recommended_next_action,
            "Re-engage Customer",
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
        delivery_management = DeliveryManagementService(
            telegram_business_service=telegram_business,
            conversation_operations_service=conversation_operations,
            sales_management_service=sales_management,
        )
        service = RelationshipManagementService(
            telegram_business_service=telegram_business,
            conversation_operations_service=conversation_operations,
            sales_management_service=sales_management,
            delivery_management_service=delivery_management,
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
            "relationship": {
                "stage": "new",
                "engagement_level": "low",
                "engagement_score": 15,
                "commerce_maturity": "none",
                "primary_recommendation": "Build relationship",
            },
            "conversation": {"state": "chat", "commerce_state": "conversation"},
            "summary": {
                "relationship_stage": "new",
                "current_product_ids": (),
                "active_offer_ids": (),
            },
            "active_offers": (),
            "delivery_history": {"delivery_count": 0},
            "telegram_commerce": {"blocked": False},
            "operation_status": "IDLE",
            "business_health": "UNKNOWN",
            "business_learning": {"consumed": True, "metric_count": 1},
        }
        service = RelationshipManagementService()

        management = service.build_management(
            telegram_business_snapshot=snapshot,
            sales_management={
                "recommendation": {
                    "recommendation_type": "CONTINUE_RELATIONSHIP",
                    "priority": "NORMAL",
                    "confidence": 0.55,
                }
            },
            delivery_management={
                "recommendation": {
                    "recommendation_type": "NO_DELIVERY",
                    "priority": "LOW",
                }
            },
        )

        self.assertEqual(management.customer_id, "customer-map")
        self.assertEqual(management.relationship_health, RelationshipHealth.TRUST_BUILDING)
        self.assertEqual(
            management.recommendation.recommendation_type,
            RelationshipRecommendationType.BUILD_TRUST,
        )
        self.assertEqual(management.engagement_score, 15)

    def test_preserves_recommendation_only_ownership_boundaries(self):
        service = RelationshipManagementService(
            customer_intelligence_service=ForbiddenCustomerIntelligenceService(),
            business_learning_service=ForbiddenBusinessLearningService(),
        )

        management = service.build_management(
            telegram_business_snapshot=business_snapshot(),
            conversation_operation=ConversationOperationsService().build_operation(
                telegram_business_snapshot=business_snapshot()
            ),
            sales_management=SalesManagementService().build_management(
                telegram_business_snapshot=business_snapshot()
            ),
            delivery_management=DeliveryManagementService().build_management(
                telegram_business_snapshot=business_snapshot(),
                product_availability=available_product(),
            ),
            metadata={"runtime": ForbiddenTelegramRuntime()},
        )

        compatibility = management.compatibility
        self.assertTrue(compatibility["read_only"])
        self.assertTrue(compatibility["aggregation_only"])
        self.assertTrue(compatibility["recommendation_only"])
        self.assertFalse(compatibility["executes_telegram"])
        self.assertFalse(compatibility["generates_responses"])
        self.assertFalse(compatibility["modifies_customer_intelligence"])
        self.assertFalse(compatibility["publishes_products"])
        self.assertFalse(compatibility["modifies_products"])
        self.assertFalse(compatibility["records_business_learning"])
        self.assertEqual(
            compatibility["customer_intelligence_owner"],
            "CustomerIntelligenceCompatibilityAdapter",
        )
        self.assertEqual(
            compatibility["business_learning_owner"],
            "BusinessLearningService",
        )
        self.assertEqual(compatibility["telegram_runtime_owner"], "Telegram runtime")


if __name__ == "__main__":
    unittest.main()

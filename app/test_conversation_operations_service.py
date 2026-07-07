import unittest

from app.models.conversation_operations import (
    ConversationOperation,
    ConversationOperationStatus,
)
from app.models.telegram_business import (
    TelegramBusinessSnapshot,
    TelegramBusinessSummary,
)
from app.services.conversation_operations_service import (
    ConversationOperationsService,
)
from app.test_telegram_business_service import (
    customer_snapshot,
    learning_context,
    product_business_snapshot,
    telegram_commerce_result,
)


class FakeTelegramBusinessService:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def build_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return self.snapshot


class ForbiddenTelegramCommerceService:
    def execute(self, *args, **kwargs):
        raise AssertionError("ConversationOperationsService must not execute Telegram")

    def process_message(self, *args, **kwargs):
        raise AssertionError("ConversationOperationsService must not generate responses")


class ForbiddenCustomerIntelligenceService:
    def update_relationship(self, *args, **kwargs):
        raise AssertionError(
            "ConversationOperationsService must not modify Customer Intelligence"
        )


class ForbiddenExperienceService:
    def update_experience(self, *args, **kwargs):
        raise AssertionError("ConversationOperationsService must not modify Experiences")


class ForbiddenPublishingService:
    def publish(self, *args, **kwargs):
        raise AssertionError("ConversationOperationsService must not publish Products")


def business_snapshot(**overrides):
    values = {
        "customer_id": "telegram-customer-1",
        "provider": "telegram",
        "customer_identity": {
            "customer_id": "telegram-customer-1",
            "canonical_customer_id": "customer-1",
            "telegram_identifier": "123456789",
        },
        "relationship": {
            "stage": "engaged",
            "engagement_level": "high",
            "primary_recommendation": "Continue premium experience",
        },
        "conversation": {
            "state": "experience",
            "commerce_state": "paid_media_link_delivery",
            "current_offer_id": "offer-1",
            "current_offer_kind": "premium",
            "next_recommended_action": "deliver_paid_media_link",
        },
        "experience": {
            "current_experience_id": "experience-1",
            "experience_state": "active",
            "progress_percentage": 45,
            "next_recommended_experience_action": "continue_experience",
        },
        "products": (
            {
                "product_id": "product-1",
                "product_health": "HEALTHY",
                "availability": "TELEGRAM_READY",
            },
        ),
        "active_offers": (
            {
                "offer_id": "offer-1",
                "product_id": "product-1",
                "delivery_method": "paid_media_link",
                "active": True,
            },
        ),
        "delivery_history": {
            "delivery_count": 0,
            "last_delivery": {},
        },
        "telegram_commerce": {
            "delivery_method": "paid_media_link",
            "blocked": False,
            "execution_status": "deferred",
        },
        "business_health": "TELEGRAM_READY",
        "operation_status": "DEFERRED",
        "next_recommended_business_action": "deliver_paid_media_link",
        "summary": TelegramBusinessSummary(
            relationship_stage="engaged",
            conversation_state="experience",
            current_experience_id="experience-1",
            current_product_ids=("product-1",),
            active_offer_ids=("offer-1",),
            delivery_count=0,
            business_health="TELEGRAM_READY",
            operation_status="DEFERRED",
            next_recommended_action="deliver_paid_media_link",
        ),
        "metadata": {},
    }
    values.update(overrides)
    return TelegramBusinessSnapshot(**values)


class ConversationOperationsServiceTests(unittest.TestCase):
    def test_generates_delivery_pending_conversation_operation(self):
        service = ConversationOperationsService()

        operation = service.build_operation(
            telegram_business_snapshot=business_snapshot()
        )

        self.assertIsInstance(operation, ConversationOperation)
        self.assertEqual(
            operation.status,
            ConversationOperationStatus.DELIVERY_PENDING,
        )
        self.assertEqual(operation.customer_id, "telegram-customer-1")
        self.assertEqual(operation.conversation_state, "experience")
        self.assertEqual(operation.current_experience_id, "experience-1")
        self.assertEqual(operation.current_product_ids, ("product-1",))
        self.assertEqual(operation.pending_offer_ids, ("offer-1",))
        self.assertEqual(operation.pending_delivery_methods, ("paid_media_link",))
        self.assertEqual(operation.next_operational_action, "Deliver Product")

    def test_generates_summary_counts_for_operation_states(self):
        service = ConversationOperationsService()
        delivery = service.build_operation(
            telegram_business_snapshot=business_snapshot()
        )
        waiting = service.build_operation(
            telegram_business_snapshot=business_snapshot(
                active_offers=(),
                telegram_commerce={"blocked": False},
                operation_status="IDLE",
                metadata={"waiting_for_customer": True},
                summary=TelegramBusinessSummary(
                    conversation_state="chat",
                    operation_status="IDLE",
                    next_recommended_action="Wait",
                ),
            )
        )
        completed = service.build_operation(
            telegram_business_snapshot=business_snapshot(
                active_offers=(),
                conversation={"state": "experience", "commerce_state": "completed"},
                experience={
                    "current_experience_id": "experience-1",
                    "experience_state": "complete",
                    "progress_percentage": 100,
                },
                telegram_commerce={"blocked": False},
                operation_status="COMPLETED",
                summary=TelegramBusinessSummary(
                    conversation_state="experience",
                    current_experience_id="experience-1",
                    operation_status="COMPLETED",
                ),
            )
        )

        summary = service.build_summary((delivery, waiting, completed))

        self.assertEqual(summary.total_operations, 3)
        self.assertEqual(summary.delivery_pending_count, 1)
        self.assertEqual(summary.waiting_for_customer_count, 1)
        self.assertEqual(summary.completed_count, 1)
        self.assertEqual(summary.active_count, 1)
        self.assertEqual(summary.next_actions["Deliver Product"], 1)
        self.assertEqual(summary.next_actions["Wait"], 1)
        self.assertEqual(summary.next_actions["No Action Required"], 1)

    def test_integrates_with_telegram_business_service_and_existing_context(self):
        snapshot = business_snapshot()
        telegram_business = FakeTelegramBusinessService(snapshot)
        service = ConversationOperationsService(
            telegram_business_service=telegram_business,
            telegram_commerce_service=ForbiddenTelegramCommerceService(),
            customer_intelligence_service=ForbiddenCustomerIntelligenceService(),
            experience_service=ForbiddenExperienceService(),
        )
        customer = customer_snapshot()

        operation = service.build_operation(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            customer_snapshot=customer,
            product_business_snapshot=product_business_snapshot(),
            learning_context=learning_context(),
        )

        self.assertEqual(operation.status, ConversationOperationStatus.DELIVERY_PENDING)
        self.assertEqual(len(telegram_business.calls), 1)
        self.assertEqual(
            telegram_business.calls[0]["customer_id"],
            "telegram-customer-1",
        )
        self.assertIs(telegram_business.calls[0]["customer_snapshot"], customer)

    def test_backward_compatible_mapping_input(self):
        service = ConversationOperationsService()
        snapshot = {
            "customer_id": "customer-map",
            "provider": "telegram",
            "relationship": {"stage": "active"},
            "conversation": {
                "state": "paused",
                "commerce_state": "conversation",
            },
            "experience": {
                "current_experience_id": "experience-map",
                "experience_state": "paused",
                "progress_percentage": 25,
            },
            "summary": {
                "current_product_ids": ("product-map",),
                "active_offer_ids": (),
            },
            "delivery_history": {"delivery_count": 0},
            "telegram_commerce": {"blocked": False},
            "operation_status": "IDLE",
            "business_health": "UNKNOWN",
        }

        operation = service.build_operation(telegram_business_snapshot=snapshot)

        self.assertEqual(operation.status, ConversationOperationStatus.PAUSED)
        self.assertEqual(operation.next_operational_action, "Resume Experience")
        self.assertEqual(operation.current_product_ids, ("product-map",))
        self.assertEqual(operation.current_experience_id, "experience-map")

    def test_preserves_read_only_ownership_boundaries(self):
        service = ConversationOperationsService(
            telegram_commerce_service=ForbiddenTelegramCommerceService(),
            customer_intelligence_service=ForbiddenCustomerIntelligenceService(),
            experience_service=ForbiddenExperienceService(),
            commerce_execution_service=object(),
        )

        operation = service.build_operation(
            telegram_business_snapshot=business_snapshot()
        )
        summary = service.build_summary((operation,))

        self.assertTrue(operation.compatibility["read_only"])
        self.assertTrue(operation.compatibility["aggregation_only"])
        self.assertFalse(operation.compatibility["executes_telegram"])
        self.assertFalse(operation.compatibility["generates_responses"])
        self.assertFalse(operation.compatibility["modifies_customer_intelligence"])
        self.assertFalse(operation.compatibility["modifies_telegram_commerce"])
        self.assertFalse(operation.compatibility["modifies_experiences"])
        self.assertFalse(operation.compatibility["publishes_products"])
        self.assertTrue(summary.compatibility["read_only"])
        self.assertFalse(summary.compatibility["executes_telegram"])


if __name__ == "__main__":
    unittest.main()

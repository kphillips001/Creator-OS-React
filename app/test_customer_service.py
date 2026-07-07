import inspect
import unittest
from datetime import datetime, timezone

from app.models.customer import (
    Customer,
    CustomerConversationSummary,
    CustomerOwnershipSummary,
    CustomerProgressionSummary,
    CustomerProviderIdentity,
    CustomerRecommendationSummary,
    CustomerRelationshipStatus,
    CustomerRelationshipSummary,
)
from app.services.customer_service import CustomerService
import app.services.customer_service as customer_service_module


class FakeCustomerRepository:
    def __init__(self, customer=None):
        self.customer = customer
        self.legacy_calls = []
        self.provider_calls = []

    def get_by_legacy_fanvue_user(self, *, fanvue_account_id, fanvue_user_id):
        self.legacy_calls.append((fanvue_account_id, fanvue_user_id))
        return self.customer

    def get_by_provider_identity(
        self,
        *,
        provider,
        provider_customer_id,
        provider_account_id=None,
    ):
        self.provider_calls.append(
            (provider, provider_customer_id, provider_account_id)
        )
        return self.customer


def sample_customer():
    return Customer(
        customer_id="7:42",
        display_name="Test Customer",
        provider_identities=(
            CustomerProviderIdentity(
                provider="fanvue",
                provider_customer_id="provider-user-42",
                provider_account_id="7",
            ),
            CustomerProviderIdentity(
                provider="telegram",
                provider_customer_id="123456",
                provider_account_id="123456",
            ),
        ),
        relationship=CustomerRelationshipSummary(
            status=CustomerRelationshipStatus.SUBSCRIBER,
            is_follower=True,
            is_subscriber=True,
            value_tier="HIGH_VALUE",
            buyer_tier="ACTIVE_BUYER",
            total_spend_cents=3499,
            purchase_count=2,
            last_active_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        ),
        conversation=CustomerConversationSummary(
            thread_count=1,
            message_count=12,
            inbound_message_count=7,
            outbound_message_count=5,
            last_message_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            current_mode="chat",
        ),
        progression=CustomerProgressionSummary(
            current_experience_id="experience-1",
            active_session=True,
            session_step=3,
        ),
        ownership=CustomerOwnershipSummary(
            owned_product_ids=("product-1", "product-2"),
            owned_experience_ids=("experience-1",),
            entitlement_count=2,
            purchase_count=2,
            last_purchase_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        ),
        recommendation=CustomerRecommendationSummary(
            last_offer_id="offer-1",
            last_offer_at=datetime(2026, 1, 6, tzinfo=timezone.utc),
            offer_count=4,
            preferred_tags=("vip",),
        ),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 7, tzinfo=timezone.utc),
    )


class CustomerServiceTests(unittest.TestCase):
    def test_get_customer_retrieves_by_internal_customer_id(self):
        repository = FakeCustomerRepository(sample_customer())
        service = CustomerService(customer_repository=repository)

        customer = service.get_customer("7:42")

        self.assertEqual(customer.customer_id, "7:42")
        self.assertEqual(repository.legacy_calls, [(7, 42)])
        self.assertEqual(repository.provider_calls, [])

    def test_get_customer_retrieves_by_provider_identity(self):
        repository = FakeCustomerRepository(sample_customer())
        service = CustomerService(customer_repository=repository)

        customer = service.get_customer(
            provider="telegram",
            provider_customer_id=123456,
        )

        self.assertEqual(customer.customer_id, "7:42")
        self.assertEqual(
            repository.provider_calls,
            [("telegram", 123456, None)],
        )
        self.assertEqual(repository.legacy_calls, [])

    def test_customer_summary_is_provider_neutral_presentation_data(self):
        repository = FakeCustomerRepository(sample_customer())
        service = CustomerService(customer_repository=repository)

        summary = service.get_customer_summary("7:42")

        self.assertEqual(summary["customer_id"], "7:42")
        self.assertEqual(summary["display_name"], "Test Customer")
        self.assertEqual(summary["relationship_status"], "subscriber")
        self.assertTrue(summary["is_subscriber"])
        self.assertEqual(summary["total_spend_cents"], 3499)
        self.assertEqual(summary["message_count"], 12)
        self.assertEqual(summary["current_experience_id"], "experience-1")
        self.assertEqual(summary["owned_product_count"], 2)
        self.assertEqual(summary["owned_experience_count"], 1)
        self.assertEqual(summary["provider_count"], 2)
        self.assertEqual(summary["offer_count"], 4)

    def test_section_methods_return_customer_summary_objects(self):
        customer = sample_customer()
        service = CustomerService(customer_repository=FakeCustomerRepository(customer))

        self.assertIs(service.get_customer_relationship("7:42"), customer.relationship)
        self.assertIs(service.get_customer_progression("7:42"), customer.progression)
        self.assertIs(service.get_customer_conversation("7:42"), customer.conversation)
        self.assertIs(service.get_customer_ownership("7:42"), customer.ownership)
        self.assertIs(
            service.get_customer_recommendations("7:42"),
            customer.recommendation,
        )

    def test_customer_timeline_uses_customer_read_model_events(self):
        service = CustomerService(
            customer_repository=FakeCustomerRepository(sample_customer())
        )

        timeline = service.get_customer_timeline("7:42")
        event_types = [event["type"] for event in timeline]

        self.assertEqual(event_types[0], "system")
        self.assertIn("conversation", event_types)
        self.assertIn("recommendation", event_types)
        self.assertIn("product_purchased", event_types)
        self.assertIn("experience_progression", event_types)
        self.assertIn("customer_memory", event_types)
        self.assertIn("media_link", event_types)
        self.assertTrue(
            next(event for event in timeline if event["type"] == "media_link")[
                "future_ready"
            ]
        )
        timestamped = [event for event in timeline if event["timestamp"] is not None]
        self.assertEqual(
            timestamped,
            sorted(
                timestamped,
                key=service._timeline_sort_key,
                reverse=True,
            ),
        )

    def test_decision_inspector_exposes_business_context(self):
        service = CustomerService(
            customer_repository=FakeCustomerRepository(sample_customer())
        )

        inspector = service.get_customer_decision_inspector("7:42")

        self.assertEqual(inspector["customer_id"], "7:42")
        self.assertEqual(
            inspector["current_recommendation"]["last_offer_id"],
            "offer-1",
        )
        self.assertEqual(inspector["recent_recommendations"]["offer_count"], 4)
        self.assertEqual(
            inspector["customer_progression"]["current_experience_id"],
            "experience-1",
        )
        self.assertEqual(inspector["conversation_summary"]["message_count"], 12)
        self.assertEqual(
            inspector["memory_summary"]["relationship_status"],
            "subscriber",
        )
        self.assertTrue(inspector["offer_candidates"]["future_ready"])
        self.assertTrue(inspector["delivery_permissions"]["future_ready"])
        self.assertNotIn("prompt", inspector)
        self.assertNotIn("working_memory", inspector)

    def test_commerce_summary_exposes_customer_commerce_relationship(self):
        service = CustomerService(
            customer_repository=FakeCustomerRepository(sample_customer())
        )

        commerce = service.get_customer_commerce_summary("7:42")

        self.assertEqual(commerce["customer_id"], "7:42")
        self.assertEqual(
            commerce["products_owned"],
            ("product-1", "product-2"),
        )
        self.assertEqual(
            commerce["products_purchased"],
            ("product-1", "product-2"),
        )
        self.assertEqual(commerce["entitlements"]["count"], 2)
        self.assertEqual(commerce["entitlements"]["owned_experience_count"], 1)
        self.assertEqual(
            commerce["purchased_experiences"],
            ("experience-1",),
        )
        self.assertEqual(commerce["purchase_summary"]["purchase_count"], 2)
        self.assertEqual(commerce["purchase_summary"]["total_spend_cents"], 3499)
        self.assertEqual(commerce["customer_value"]["value_tier"], "HIGH_VALUE")
        conversation_state = commerce["telegram_conversation_state"]
        self.assertEqual(
            conversation_state["current_experience"],
            "experience-1",
        )
        self.assertIsNone(conversation_state["current_product"])
        self.assertEqual(conversation_state["current_offer"], "offer-1")
        self.assertEqual(conversation_state["conversation_status"], "chat")
        self.assertEqual(conversation_state["commerce_progress"], "offer_active")
        self.assertEqual(
            conversation_state["next_recommended_action"],
            "continue_experience",
        )
        delivery_decision = commerce["delivery_decision"]
        self.assertEqual(
            delivery_decision["current_delivery_decision"],
            "offer_active",
        )
        self.assertEqual(delivery_decision["delivery_type"], "PAID")
        self.assertEqual(delivery_decision["free_vs_paid"], "PAID")
        self.assertEqual(
            delivery_decision["next_suggested_action"],
            "deliver_paid_media_link",
        )
        self.assertEqual(
            delivery_decision["last_delivery"]["delivery_method"],
            "paid_media_link",
        )
        self.assertIsNone(
            delivery_decision["last_delivery"]["last_paid_media_link"]
        )
        self.assertTrue(commerce["products_offered"]["future_ready"])
        self.assertTrue(commerce["media_links"]["future_ready"])
        commerce_memory = commerce["commerce_memory"]
        self.assertEqual(
            commerce_memory["purchased_products"],
            ("product-1", "product-2"),
        )
        self.assertEqual(commerce_memory["current_commerce_journey"], "customer")
        self.assertEqual(
            commerce_memory["customer_spending_summary"]["total_spend_cents"],
            3499,
        )
        self.assertEqual(
            commerce_memory["customer_engagement_summary"]["message_count"],
            12,
        )
        self.assertEqual(
            commerce_memory["recommended_next_commerce_action"],
            "escalate_commerce_offer",
        )

    def test_experience_progression_summary_exposes_current_progress(self):
        service = CustomerService(
            customer_repository=FakeCustomerRepository(sample_customer())
        )

        progression = service.get_customer_experience_progression_summary("7:42")

        self.assertEqual(progression["current_experience"], "experience-1")
        self.assertEqual(progression["current_experience_state"], "active")
        self.assertIsNone(progression["current_story_position"])
        self.assertEqual(progression["current_asset_position"], "3")
        self.assertEqual(progression["progress_percentage"], 60)
        self.assertEqual(
            progression["last_progression_event"]["source"],
            "customer_progression_summary",
        )
        self.assertEqual(
            progression["next_recommended_experience_action"],
            "continue_experience",
        )

    def test_missing_or_invalid_customer_returns_none(self):
        service = CustomerService(customer_repository=FakeCustomerRepository(None))

        self.assertIsNone(service.get_customer())
        self.assertIsNone(service.get_customer("not-a-customer-id"))
        self.assertIsNone(service.get_customer_summary("7:42"))
        self.assertIsNone(service.get_customer_relationship("7:42"))
        self.assertEqual(service.get_customer_timeline("7:42"), [])
        self.assertIsNone(service.get_customer_decision_inspector("7:42"))
        self.assertIsNone(service.get_customer_commerce_summary("7:42"))
        self.assertIsNone(
            service.get_customer_experience_progression_summary("7:42")
        )

    def test_service_does_not_import_persistence_sources(self):
        source = inspect.getsource(customer_service_module)

        self.assertNotIn("get_db_connection", source)
        self.assertNotIn("get_user_memory_row", source)
        self.assertNotIn("get_thread_messages_for_user", source)
        self.assertNotIn("get_owned_content_tags", source)


if __name__ == "__main__":
    unittest.main()

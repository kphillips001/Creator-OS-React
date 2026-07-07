import unittest
from dataclasses import fields

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


class CustomerModelTests(unittest.TestCase):
    def test_customer_can_represent_provider_neutral_identity(self):
        customer = Customer(
            customer_id="customer-1",
            display_name="Test Customer",
            provider_identities=(
                CustomerProviderIdentity(
                    provider="Telegram",
                    provider_customer_id=12345,
                    provider_account_id=7,
                    channel="Chat",
                    username="test_user",
                ),
            ),
        )

        self.assertEqual(customer.customer_id, "customer-1")
        self.assertEqual(customer.display_name, "Test Customer")
        self.assertTrue(customer.has_provider_identity("telegram"))
        self.assertEqual(
            customer.identity_for("TELEGRAM").provider_customer_id,
            "12345",
        )
        self.assertEqual(
            customer.identity_for("telegram").provider_account_id,
            "7",
        )
        self.assertEqual(customer.identity_for("telegram").channel, "chat")

    def test_relationship_summary_is_business_state_not_provider_state(self):
        relationship = CustomerRelationshipSummary(
            status="subscriber",
            is_follower=True,
            is_subscriber=True,
            value_tier="high",
            buyer_tier="active",
            total_spend_cents="2500",
            purchase_count="2",
        )

        self.assertEqual(relationship.status, CustomerRelationshipStatus.SUBSCRIBER)
        self.assertTrue(relationship.is_follower)
        self.assertTrue(relationship.is_subscriber)
        self.assertEqual(relationship.total_spend_cents, 2500)
        self.assertEqual(relationship.purchase_count, 2)

    def test_customer_aggregates_customer_workspace_summaries(self):
        customer = Customer(
            customer_id=99,
            conversation=CustomerConversationSummary(
                thread_count="1",
                message_count="10",
                inbound_message_count="6",
                outbound_message_count="4",
                current_mode="chat",
            ),
            progression=CustomerProgressionSummary(
                current_experience_id="experience-1",
                seen_experience_ids=["experience-1"],
                seen_content_tags=["tag-a", "tag-b"],
                active_session=True,
                session_step="3",
            ),
            ownership=CustomerOwnershipSummary(
                owned_product_ids=["product-1"],
                owned_experience_ids=["experience-1"],
                entitlement_count="1",
                purchase_count="1",
            ),
            recommendation=CustomerRecommendationSummary(
                seen_offer_ids=["offer-1"],
                recent_product_ids=["product-1"],
                preferred_tags=["tag-a"],
                preferred_themes=["theme-a"],
                offer_count="2",
            ),
        )

        self.assertEqual(customer.customer_id, "99")
        self.assertEqual(customer.conversation.message_count, 10)
        self.assertEqual(customer.progression.session_step, 3)
        self.assertEqual(customer.progression.seen_content_tags, ("tag-a", "tag-b"))
        self.assertTrue(customer.ownership.owns_product("product-1"))
        self.assertTrue(customer.ownership.owns_experience("experience-1"))
        self.assertEqual(customer.recommendation.seen_offer_ids, ("offer-1",))

    def test_metadata_is_copied_to_plain_dicts(self):
        provider_metadata = {"raw": {"id": "provider-id"}}
        customer_metadata = {"source": "unit"}
        customer = Customer(
            customer_id="customer-1",
            provider_identities=(
                CustomerProviderIdentity(
                    provider="fanvue",
                    provider_customer_id="provider-user",
                    metadata=provider_metadata,
                ),
            ),
            metadata=customer_metadata,
        )

        provider_metadata["changed"] = True
        customer_metadata["changed"] = True

        self.assertNotIn("changed", customer.provider_identities[0].metadata)
        self.assertNotIn("changed", customer.metadata)

    def test_model_exposes_no_provider_specific_field_names(self):
        model_classes = (
            Customer,
            CustomerProviderIdentity,
            CustomerRelationshipSummary,
            CustomerConversationSummary,
            CustomerProgressionSummary,
            CustomerOwnershipSummary,
            CustomerRecommendationSummary,
        )
        forbidden_markers = ("fanvue", "telegram")

        for model_class in model_classes:
            with self.subTest(model=model_class.__name__):
                field_names = {field.name for field in fields(model_class)}
                self.assertFalse(
                    any(
                        marker in field_name
                        for marker in forbidden_markers
                        for field_name in field_names
                    )
                )


if __name__ == "__main__":
    unittest.main()

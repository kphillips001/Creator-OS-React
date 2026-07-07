import unittest
from types import SimpleNamespace

from app.models.customer import Customer, CustomerRelationshipStatus
from app.repositories.customer_repository import CustomerRepository


class FakeTelegramIdentityRepository:
    def __init__(self, mapping=None):
        self.mapping = mapping
        self.local_calls = []
        self.telegram_calls = []

    def get_by_local_user_id(self, fanvue_account_id, local_fanvue_user_id):
        self.local_calls.append((fanvue_account_id, local_fanvue_user_id))
        return self.mapping

    def get_by_telegram_user_id(self, telegram_user_id):
        self.telegram_calls.append(telegram_user_id)
        return self.mapping


class CustomerRepositoryTests(unittest.TestCase):
    def test_aggregates_customer_read_model_from_existing_sources(self):
        telegram_mapping = SimpleNamespace(
            telegram_user_id=123456,
            telegram_chat_id=123456,
            fanvue_account_id=7,
            local_fanvue_user_id=42,
            is_active=True,
        )
        telegram_repository = FakeTelegramIdentityRepository(telegram_mapping)
        repo = CustomerRepository(
            fanvue_user_by_id_fetcher=lambda account_id, user_id: {
                "id": user_id,
                "fanvue_account_id": account_id,
                "fanvue_user_uuid": "provider-user-42",
                "username": "test_user",
                "display_name": "Test User",
                "relationship_status": "subscriber",
                "is_follower": True,
                "is_subscriber": True,
            },
            memory_fetcher=lambda account_id, user_id: {
                "message_count": 12,
                "inbound_message_count": 7,
                "outbound_message_count": 5,
                "conversation_mode": "chat",
                "buyer_tier": "ACTIVE_BUYER",
                "user_value_tier": "HIGH_VALUE",
                "purchase_count": 2,
                "total_spend_cents": 3499,
                "seen_content_tags": ["vip-1", "vip-2"],
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "last_offer_type": "vip",
                "offers_shown_count": 4,
                "preferred_content_theme": "cosplay",
            },
            chat_messages_fetcher=lambda account_id, user_id: [
                {"sender_type": "user", "text": "hi", "sent_at": "2026-01-01"},
                {
                    "sender_type": "bot",
                    "text": "hello",
                    "sent_at": "2026-01-02",
                },
            ],
            owned_content_tags_fetcher=lambda account_id, user_id: [
                "vip-1",
                "premium-1",
            ],
            telegram_identity_repository=telegram_repository,
        )

        customer = repo.get_by_legacy_fanvue_user(
            fanvue_account_id=7,
            fanvue_user_id=42,
        )

        self.assertIsInstance(customer, Customer)
        self.assertEqual(customer.customer_id, "7:42")
        self.assertEqual(customer.display_name, "Test User")
        self.assertEqual(
            customer.relationship.status,
            CustomerRelationshipStatus.SUBSCRIBER,
        )
        self.assertTrue(customer.relationship.is_subscriber)
        self.assertEqual(customer.relationship.purchase_count, 2)
        self.assertEqual(customer.conversation.message_count, 12)
        self.assertEqual(customer.conversation.last_message_at, "2026-01-02")
        self.assertTrue(customer.progression.active_session)
        self.assertEqual(customer.progression.session_step, 3)
        self.assertEqual(
            customer.progression.seen_content_tags,
            ("vip-1", "vip-2"),
        )
        self.assertEqual(
            customer.ownership.metadata["owned_content_tags"],
            ("vip-1", "premium-1"),
        )
        self.assertEqual(customer.recommendation.last_offer_kind, "vip")
        self.assertEqual(customer.recommendation.offer_count, 4)
        self.assertEqual(customer.recommendation.preferred_themes, ("cosplay",))
        self.assertTrue(customer.has_provider_identity("fanvue"))
        self.assertTrue(customer.has_provider_identity("telegram"))
        self.assertEqual(telegram_repository.local_calls, [(7, 42)])

    def test_get_by_provider_identity_resolves_fanvue_uuid(self):
        calls = []

        def by_uuid(account_id, customer_id):
            calls.append((account_id, customer_id))
            return {
                "id": 77,
                "fanvue_account_id": account_id,
                "fanvue_user_uuid": customer_id,
                "relationship_status": "follower",
                "is_follower": True,
                "is_subscriber": False,
            }

        repo = CustomerRepository(
            fanvue_user_by_uuid_fetcher=by_uuid,
            fanvue_user_by_id_fetcher=lambda account_id, user_id: {
                "id": user_id,
                "fanvue_account_id": account_id,
                "fanvue_user_uuid": "provider-user-77",
                "relationship_status": "follower",
                "is_follower": True,
            },
            memory_fetcher=lambda account_id, user_id: {},
            chat_messages_fetcher=lambda account_id, user_id: [],
            owned_content_tags_fetcher=lambda account_id, user_id: [],
            telegram_identity_repository=FakeTelegramIdentityRepository(),
        )

        customer = repo.get_by_provider_identity(
            provider="fanvue",
            provider_account_id=9,
            provider_customer_id="provider-user-77",
        )

        self.assertEqual(calls, [(9, "provider-user-77")])
        self.assertEqual(customer.customer_id, "9:77")
        self.assertEqual(
            customer.relationship.status,
            CustomerRelationshipStatus.FOLLOWER,
        )

    def test_get_by_provider_identity_resolves_telegram_mapping(self):
        telegram_mapping = SimpleNamespace(
            telegram_user_id=555,
            telegram_chat_id=555,
            fanvue_account_id=4,
            local_fanvue_user_id=11,
            is_active=True,
        )
        telegram_repository = FakeTelegramIdentityRepository(telegram_mapping)
        repo = CustomerRepository(
            fanvue_user_by_id_fetcher=lambda account_id, user_id: {
                "id": user_id,
                "fanvue_account_id": account_id,
                "fanvue_user_uuid": "provider-user-11",
                "relationship_status": "unknown",
            },
            memory_fetcher=lambda account_id, user_id: {},
            chat_messages_fetcher=lambda account_id, user_id: [],
            owned_content_tags_fetcher=lambda account_id, user_id: [],
            telegram_identity_repository=telegram_repository,
        )

        customer = repo.get_by_provider_identity(
            provider="telegram",
            provider_customer_id=555,
        )

        self.assertEqual(telegram_repository.telegram_calls, [555])
        self.assertEqual(customer.customer_id, "4:11")
        self.assertTrue(customer.has_provider_identity("telegram"))

    def test_missing_customer_returns_none(self):
        repo = CustomerRepository(
            fanvue_user_by_id_fetcher=lambda account_id, user_id: None,
            memory_fetcher=lambda account_id, user_id: {},
            chat_messages_fetcher=lambda account_id, user_id: [],
            owned_content_tags_fetcher=lambda account_id, user_id: [],
            telegram_identity_repository=FakeTelegramIdentityRepository(),
        )

        self.assertIsNone(
            repo.get_by_legacy_fanvue_user(
                fanvue_account_id=1,
                fanvue_user_id=999,
            )
        )
        self.assertIsNone(
            repo.get_by_provider_identity(
                provider="unknown",
                provider_customer_id="customer",
            )
        )


if __name__ == "__main__":
    unittest.main()

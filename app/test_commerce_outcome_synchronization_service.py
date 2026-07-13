import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.models.business_learning import BusinessOutcomeType
from app.models.commerce_outcome import CommerceOutcomeRequest, CommerceOutcomeStatus
from app.repositories.commerce_outcome_repository import CommerceOutcomeRepository
from app.services.commerce_outcome_synchronization_service import (
    CommerceOutcomeSynchronizationService,
)


class FakeDeliveryRepository:
    def __init__(self, events=()):
        self.events = tuple(events)

    def list_events(self):
        return self.events


class FakeBusinessLearningService:
    def __init__(self):
        self.outcomes = []

    def record_business_outcome(self, outcome):
        self.outcomes.append(outcome)
        return {"success": True, "outcome_id": outcome.outcome_id}


class FakeCustomerIntelligenceService:
    def __init__(self):
        self.purchases = []

    def record_purchase(self, commerce_history, **kwargs):
        self.purchases.append((commerce_history, kwargs))
        return SimpleNamespace(
            to_context=lambda: {
                "purchase_count": len(self.purchases),
                "last_purchase": kwargs,
            }
        )


class FakeCommerceRegistrationRepository:
    def get_by_asset_id(self, asset_id):
        return SimpleNamespace(asset_id=asset_id)


class FakeFanvueAPI:
    def __init__(self, records):
        self.records = tuple(records)

    def list_purchases(self, since=None, limit=100):
        return {"success": True, "data": self.records[:limit]}


class CommerceOutcomeSynchronizationServiceTests(unittest.TestCase):
    def service(self, *, path, delivery_events=(), fanvue_records=()):
        self.learning = FakeBusinessLearningService()
        self.customer = FakeCustomerIntelligenceService()
        self.repository = CommerceOutcomeRepository(path)
        return CommerceOutcomeSynchronizationService(
            repository=self.repository,
            delivery_repository=FakeDeliveryRepository(delivery_events),
            commerce_registration_repository=FakeCommerceRegistrationRepository(),
            business_learning_service=self.learning,
            customer_intelligence_service=self.customer,
            fanvue_api_factory=lambda fanvue_account_id: FakeFanvueAPI(fanvue_records),
        )

    def purchase_payload(self, **overrides):
        payload = {
            "external_event_id": "evt-1",
            "event_type": "purchase_received",
            "fanvue_account_id": 2,
            "fanvue_user_id": "fanvue-user-1",
            "fanvue_media_uuid": "media-101",
            "amount": 25.0,
            "currency": "USD",
            "purchased_at": "2026-07-12T12:00:00Z",
            "recommendation_id": "rec-101",
            "delivery_id": "delivery-101",
            "asset_id": 101,
            "product_id": "product-1",
            "experience_id": "experience-1",
            "customer_id": "customer-1",
            "conversation_id": "conversation-1",
        }
        payload.update(overrides)
        return payload

    def test_synchronizes_directly_attributed_purchase(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(path=Path(temp_dir) / "outcomes.json")

            result = service.synchronize_provider_outcome(
                CommerceOutcomeRequest(
                    provider_payload=self.purchase_payload(),
                    provider="fanvue",
                    source="webhook",
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.outcome.status, CommerceOutcomeStatus.SYNCHRONIZED)
            self.assertEqual(result.outcome.attribution.recommendation_id, "rec-101")
            self.assertEqual(result.outcome.attribution.delivery_id, "delivery-101")
            self.assertEqual(result.outcome.attribution.asset_id, 101)
            self.assertEqual(result.outcome.purchase.net_revenue_cents, 2500)
            self.assertEqual(len(self.repository.list_outcomes()), 1)
            self.assertEqual(len(self.learning.outcomes), 1)
            self.assertEqual(
                self.learning.outcomes[0].outcome_type,
                BusinessOutcomeType.PRODUCT_PURCHASED.value,
            )
            self.assertEqual(self.learning.outcomes[0].recommendation_id, "rec-101")
            self.assertEqual(len(self.customer.purchases), 1)
            self.assertEqual(
                self.customer.purchases[0][1]["purchase_id"],
                "evt-1",
            )

    def test_resolves_attribution_from_delivery_history(self):
        delivery_event = {
            "event_type": "delivery_success",
            "payload": {
                "delivery_id": "delivery-202",
                "payload": {
                    "asset_id": 202,
                    "product_id": "product-2",
                    "experience_id": "experience-2",
                    "provider_media_uuid": "media-202",
                    "customer_id": "fanvue-user-2",
                    "conversation_id": "conversation-2",
                    "recommendation_id": "rec-202",
                },
            },
        }
        with TemporaryDirectory() as temp_dir:
            service = self.service(
                path=Path(temp_dir) / "outcomes.json",
                delivery_events=(delivery_event,),
            )

            result = service.synchronize_provider_outcome(
                self.purchase_payload(
                    external_event_id="evt-202",
                    fanvue_user_id="fanvue-user-2",
                    fanvue_media_uuid="media-202",
                    recommendation_id=None,
                    delivery_id=None,
                    asset_id=None,
                    product_id=None,
                    experience_id=None,
                    customer_id=None,
                    conversation_id=None,
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.outcome.attribution.matched_by, "delivery_history")
            self.assertEqual(result.outcome.attribution.recommendation_id, "rec-202")
            self.assertEqual(result.outcome.attribution.delivery_id, "delivery-202")
            self.assertEqual(result.outcome.attribution.asset_id, 202)
            self.assertEqual(result.outcome.attribution.product_id, "product-2")

    def test_duplicate_purchase_is_persisted_without_double_learning(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(path=Path(temp_dir) / "outcomes.json")
            first = service.synchronize_provider_outcome(self.purchase_payload())
            second = service.synchronize_provider_outcome(self.purchase_payload())

            self.assertTrue(first.success)
            self.assertTrue(second.success)
            self.assertTrue(second.duplicate)
            self.assertEqual(len(self.repository.list_outcomes()), 1)
            self.assertEqual(len(self.learning.outcomes), 1)
            event_types = tuple(
                event["event_type"] for event in self.repository.list_events()
            )
            self.assertIn("commerce_outcome_duplicate", event_types)

    def test_refund_syncs_negative_revenue_to_business_learning(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(path=Path(temp_dir) / "outcomes.json")

            result = service.synchronize_provider_outcome(
                self.purchase_payload(
                    external_event_id="refund-1",
                    status="refunded",
                    amount=25.0,
                    refund_amount=25.0,
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.outcome.status, CommerceOutcomeStatus.REFUNDED)
            self.assertEqual(result.outcome.purchase.refund_cents, 2500)
            self.assertEqual(result.outcome.purchase.net_revenue_cents, 0)
            self.assertEqual(self.learning.outcomes[0].outcome_type, "PRODUCT_REFUNDED")

    def test_unmatched_transaction_is_persisted_as_retryable_failure(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(path=Path(temp_dir) / "outcomes.json")

            result = service.synchronize_provider_outcome(
                {
                    "external_event_id": "evt-unmatched",
                    "event_type": "purchase_received",
                    "fanvue_user_id": "fanvue-user-x",
                    "amount": 9.0,
                }
            )

            self.assertFalse(result.success)
            self.assertTrue(result.retryable)
            self.assertEqual(result.outcome.status, CommerceOutcomeStatus.UNMATCHED)
            self.assertIn("recommendation_id", result.warnings)
            self.assertEqual(len(self.learning.outcomes), 1)
            self.assertEqual(self.learning.outcomes[0].status, "UNMATCHED")
            event_types = tuple(
                event["event_type"] for event in self.repository.list_events()
            )
            self.assertIn("commerce_outcome_failure", event_types)

    def test_missing_transaction_id_persists_failure(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(path=Path(temp_dir) / "outcomes.json")

            result = service.synchronize_provider_outcome(
                {"event_type": "purchase_received", "amount": 9.0}
            )

            self.assertFalse(result.success)
            self.assertIn("missing_provider_transaction_id", result.errors)
            self.assertEqual(len(self.repository.list_outcomes()), 0)
            self.assertEqual(
                self.repository.list_events()[0]["event_type"],
                "commerce_outcome_failure",
            )

    def test_sync_fanvue_outcomes_uses_existing_api_boundary(self):
        with TemporaryDirectory() as temp_dir:
            service = self.service(
                path=Path(temp_dir) / "outcomes.json",
                fanvue_records=(self.purchase_payload(external_event_id="evt-api"),),
            )

            results = service.sync_fanvue_outcomes(fanvue_account_id=2)

            self.assertEqual(len(results), 1)
            self.assertTrue(results[0].success)
            self.assertEqual(results[0].outcome.purchase.provider_account_id, "2")


if __name__ == "__main__":
    unittest.main()

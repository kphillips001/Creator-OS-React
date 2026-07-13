import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from app.models.business_learning import BusinessOutcome, BusinessOutcomeType
from app.models.chat_commerce_delivery import ChatDeliveryRequest
from app.models.chat_commerce_registration import ChatInventoryCandidate
from app.models.commerce_outcome import CommerceOutcomeRequest, CommerceOutcomeStatus
from app.models.content_commerce_learning import RecommendationEventState
from app.models.content_recommendation import RecommendationRequest
from app.repositories.commerce_outcome_repository import CommerceOutcomeRepository
from app.repositories.content_commerce_learning_repository import (
    ContentCommerceLearningRepository,
)
from app.services.business_learning_service import BusinessLearningService
from app.services.chat_commerce_delivery_service import ChatCommerceDeliveryService
from app.services.commerce_outcome_synchronization_service import (
    CommerceOutcomeSynchronizationService,
)
from app.services.content_commerce_learning_service import (
    ContentCommerceLearningService,
)
from app.services.content_recommendation_service import ContentRecommendationService


def candidate(asset_id):
    return ChatInventoryCandidate(
        asset_id=asset_id,
        chat_registration_id=uuid4(),
        creator_profile_id=7,
        media_link=f"https://fanvue.example/media/{asset_id}",
        provider_media_id=f"media-{asset_id}",
        product_ids=(f"product-{asset_id}",),
        experience_ids=(f"experience-{asset_id}",),
    )


class FakeInventory:
    def __init__(self, candidates=(), suppressed=()):
        self.candidates = tuple(candidates)
        self.suppressed = {int(value) for value in suppressed}

    def get_recommendation_candidates(self, **kwargs):
        return self.candidates

    def eligibility_for_asset(self, asset_id, *, customer_context=None):
        blocked = int(asset_id) in self.suppressed
        return SimpleNamespace(
            recommendation_eligible=not blocked,
            delivery_eligible=not blocked,
            block_reasons=("not_chat_ready",) if blocked else (),
            warnings=(),
        )


class FakeIntelligence:
    def get_asset_intelligence(self, asset_id):
        return SimpleNamespace(
            confidence=0.9,
            themes=("premium",),
            tags=("premium",),
            keywords=("premium",),
            mood=None,
            setting=None,
            activity=None,
            outfit=None,
            objects=(),
            environment=None,
            activities=(),
            clothing=None,
            classification="photo",
            technical_quality={"has_runtime_media": True},
        )


class FakeChatRecord:
    asset_id = 101
    chat_registration_id = uuid4()
    fulfillment_id = uuid4()
    chat_ready = True
    fulfillment_ready = True
    recommendation_eligible = True
    active = True
    temporarily_unavailable = False
    retired = False
    product_ids = ("product-101",)
    experience_ids = ("experience-101",)
    media_link = "https://fanvue.example/media/101"
    provider_media_id = "media-101"
    provider = "fanvue"
    block_reasons = ()


class FakeChatService:
    def get_by_asset_id(self, asset_id):
        return FakeChatRecord()

    def eligibility_for_asset(self, asset_id, *, customer_context=None):
        return SimpleNamespace(delivery_eligible=True, block_reasons=(), warnings=())


class FakeFulfillment:
    fulfillment_id = uuid4()
    lifecycle_state = "FULFILLMENT_READY"
    media_link_verification_state = "VERIFIED"
    media_link = "https://fanvue.example/media/101"
    provider_media_id = "media-101"
    provider_full_media_id = None
    provider_preview_media_id = None
    provider = "fanvue"


class FakeFulfillmentRepository:
    def get_by_asset_and_route(self, asset_id, route):
        from app.models.fulfillment_registration import (
            FulfillmentLifecycleState,
            MediaLinkVerificationState,
        )

        return SimpleNamespace(
            fulfillment_id=uuid4(),
            lifecycle_state=FulfillmentLifecycleState.FULFILLMENT_READY,
            media_link_verification_state=MediaLinkVerificationState.VERIFIED,
            media_link="https://fanvue.example/media/101",
            provider_media_id="media-101",
            provider_full_media_id=None,
            provider_preview_media_id=None,
            provider="fanvue",
        )


class FakeDeliveryRepository:
    def __init__(self):
        self.events = []

    def record_request(self, payload):
        self.events.append({"event_type": "delivery_request", "payload": payload})

    def record_result(self, payload):
        self.events.append({"event_type": "delivery_ready", "payload": payload})

    def record_success(self, delivery_id, payload):
        self.events.append(
            {"event_type": "delivery_success", "payload": {"delivery_id": delivery_id, "payload": payload}}
        )

    def record_failure(self, delivery_id, reason, payload=None):
        self.events.append(
            {
                "event_type": "delivery_failure",
                "payload": {"delivery_id": delivery_id, "reason": reason, "payload": payload or {}},
            }
        )

    def list_events(self):
        return tuple(self.events)


class FakeCommerceRegistrationRepository:
    def get_by_asset_id(self, asset_id):
        return SimpleNamespace(asset_id=asset_id)


class ContentCommerceLearningServiceTests(unittest.TestCase):
    def make_learning(self, temp_dir):
        repository = ContentCommerceLearningRepository(Path(temp_dir) / "learning.json")
        business_learning = BusinessLearningService(learning_repository=repository)
        service = ContentCommerceLearningService(
            repository=repository,
            business_learning_service=business_learning,
        )
        return repository, business_learning, service

    def test_recommendation_result_records_ranked_selected_and_suppressed(self):
        with TemporaryDirectory() as temp_dir:
            repository, _, learning = self.make_learning(temp_dir)
            service = ContentRecommendationService(
                chat_commerce_inventory_service=FakeInventory(
                    (candidate(101), candidate(202)),
                    suppressed=(202,),
                ),
                content_intelligence_service=FakeIntelligence(),
                content_commerce_learning_service=learning,
            )

            result = service.recommend(
                RecommendationRequest(
                    creator_profile_id=7,
                    customer_context={"customer_id": "customer-1"},
                    conversation_context={"conversation_id": "conversation-1"},
                    limit=2,
                )
            )

            self.assertEqual(result.ranked_assets[0].asset_id, 101)
            events = repository.list_recommendation_events()
            states = tuple(event["event_state"] for event in events)
            self.assertIn(RecommendationEventState.GENERATED.value, states)
            self.assertIn(RecommendationEventState.SELECTED.value, states)
            self.assertIn(RecommendationEventState.SUPPRESSED.value, states)
            self.assertEqual(
                len(events),
                len({event["event_id"] for event in events}),
            )

    def test_asset_performance_automatically_changes_future_ranking(self):
        with TemporaryDirectory() as temp_dir:
            _, business_learning, learning = self.make_learning(temp_dir)
            business_learning.record_business_outcome(
                BusinessOutcome(
                    outcome_id="purchase-101",
                    outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                    subject_type="asset",
                    subject_id="101",
                    product_id="product-101",
                    customer_id="customer-1",
                    recommendation_id="rec-101",
                    value_cents=5000,
                    occurred_at="2026-07-12T12:00:00Z",
                    provider_metadata={"gross_revenue_cents": 5000},
                )
            )
            service = ContentRecommendationService(
                chat_commerce_inventory_service=FakeInventory(
                    (candidate(101), candidate(202)),
                ),
                content_intelligence_service=FakeIntelligence(),
                business_learning_service=business_learning,
                content_commerce_learning_service=learning,
            )

            result = service.recommend(RecommendationRequest(limit=2))

            self.assertEqual(result.ranked_assets[0].asset_id, 101)
            business_evidence = [
                evidence
                for evidence in result.ranked_assets[0].evidence
                if evidence.signal == "business_learning_asset_score"
            ]
            self.assertTrue(business_evidence)
            self.assertIn("Business evidence increased ranking.", result.business_rationale)

    def test_delivery_outcomes_update_recommendation_event_state(self):
        with TemporaryDirectory() as temp_dir:
            repository, _, learning = self.make_learning(temp_dir)
            delivery_repository = FakeDeliveryRepository()
            service = ChatCommerceDeliveryService(
                chat_commerce_registration_service=FakeChatService(),
                fulfillment_repository=FakeFulfillmentRepository(),
                content_usage_service=object(),
                content_ownership_service=object(),
                repository=delivery_repository,
                content_commerce_learning_service=learning,
            )

            result = service.prepare_delivery(
                ChatDeliveryRequest(
                    asset_id=101,
                    recommendation={"asset_id": 101, "recommendation_id": "rec-101"},
                    recommendation_id="rec-101",
                    customer_context={"customer_id": "customer-1"},
                    conversation_context={"conversation_id": "conversation-1"},
                )
            )
            service.record_execution_result(
                result,
                SimpleNamespace(status="sent", executed=True, execution_state="sent"),
            )

            states = tuple(
                event["event_state"]
                for event in repository.list_recommendation_events(
                    recommendation_id="rec-101"
                )
            )
            self.assertIn(RecommendationEventState.DELIVERY_PREPARED.value, states)
            self.assertIn(RecommendationEventState.DELIVERED.value, states)

    def test_commerce_outcome_becomes_business_learning_and_purchase_event(self):
        with TemporaryDirectory() as temp_dir:
            repository, business_learning, learning = self.make_learning(temp_dir)
            outcome_repository = CommerceOutcomeRepository(Path(temp_dir) / "outcomes.json")
            service = CommerceOutcomeSynchronizationService(
                repository=outcome_repository,
                delivery_repository=FakeDeliveryRepository(),
                commerce_registration_repository=FakeCommerceRegistrationRepository(),
                business_learning_service=business_learning,
                customer_intelligence_service=SimpleNamespace(record_purchase=lambda history, **kwargs: history),
                content_commerce_learning_service=learning,
            )

            result = service.synchronize_provider_outcome(
                CommerceOutcomeRequest(
                    provider="fanvue",
                    source="webhook",
                    provider_payload={
                        "external_event_id": "evt-101",
                        "event_type": "purchase_received",
                        "fanvue_media_uuid": "media-101",
                        "amount": 25.0,
                        "recommendation_id": "rec-101",
                        "delivery_id": "delivery-101",
                        "asset_id": 101,
                        "product_id": "product-101",
                        "customer_id": "customer-1",
                    },
                )
            )

            self.assertTrue(result.success)
            self.assertEqual(result.outcome.status, CommerceOutcomeStatus.SYNCHRONIZED)
            self.assertEqual(len(repository.list_business_outcomes(asset_id=101)), 1)
            states = tuple(
                event["event_state"]
                for event in repository.list_recommendation_events(
                    recommendation_id="rec-101"
                )
            )
            self.assertIn(RecommendationEventState.PURCHASED.value, states)

    def test_unmatched_outcome_remains_retryable_and_learning_visible(self):
        with TemporaryDirectory() as temp_dir:
            repository, business_learning, learning = self.make_learning(temp_dir)
            service = CommerceOutcomeSynchronizationService(
                repository=CommerceOutcomeRepository(Path(temp_dir) / "outcomes.json"),
                delivery_repository=FakeDeliveryRepository(),
                commerce_registration_repository=FakeCommerceRegistrationRepository(),
                business_learning_service=business_learning,
                customer_intelligence_service=SimpleNamespace(),
                content_commerce_learning_service=learning,
            )

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
            self.assertEqual(len(repository.list_unmatched_outcomes()), 1)
            states = tuple(
                event["event_state"]
                for event in repository.list_recommendation_events()
            )
            self.assertIn(RecommendationEventState.UNMATCHED.value, states)

    def test_backfill_is_explicit_and_idempotent(self):
        with TemporaryDirectory() as temp_dir:
            repository, _, learning = self.make_learning(temp_dir)
            outcome = BusinessOutcome(
                outcome_id="purchase-202",
                outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                subject_type="asset",
                subject_id="202",
                value_cents=1000,
            )

            first = learning.backfill_from_records(business_outcomes=(outcome,))
            second = learning.backfill_from_records(business_outcomes=(outcome,))

            self.assertTrue(first["success"])
            self.assertTrue(second["success"])
            self.assertEqual(len(repository.list_business_outcomes(asset_id=202)), 1)


if __name__ == "__main__":
    unittest.main()

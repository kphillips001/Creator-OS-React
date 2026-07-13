import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import uuid4

from app.models.chat_commerce_delivery import ChatDeliveryRequest
from app.models.chat_commerce_registration import ChatAvailabilityState
from app.models.fulfillment_registration import (
    FulfillmentLifecycleState,
    MediaLinkVerificationState,
)
from app.services.chat_commerce_delivery_service import ChatCommerceDeliveryService


@dataclass
class FakeChatRecord:
    asset_id: int = 101
    chat_registration_id: object = uuid4()
    fulfillment_id: object = uuid4()
    chat_ready: bool = True
    fulfillment_ready: bool = True
    recommendation_eligible: bool = True
    delivery_eligible: bool = True
    active: bool = True
    temporarily_unavailable: bool = False
    retired: bool = False
    availability_state: ChatAvailabilityState = ChatAvailabilityState.CHAT_READY
    product_ids: tuple[str, ...] = ("product-1",)
    experience_ids: tuple[str, ...] = ("experience-1",)
    media_link: str = "https://fanvue.example/media/101"
    provider_media_id: str = "media-101"
    provider: str = "fanvue"
    block_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass
class FakeFulfillment:
    fulfillment_id: object = uuid4()
    lifecycle_state: FulfillmentLifecycleState = (
        FulfillmentLifecycleState.FULFILLMENT_READY
    )
    media_link_verification_state: MediaLinkVerificationState = (
        MediaLinkVerificationState.VERIFIED
    )
    media_link: str = "https://fanvue.example/media/101"
    provider_media_id: str = "media-101"
    provider_full_media_id: str | None = None
    provider_preview_media_id: str | None = None
    provider: str = "fanvue"


class FakeChatService:
    def __init__(self, record=None, block_reasons=()):
        self.record = record if record is not None else FakeChatRecord()
        self.block_reasons = tuple(block_reasons)

    def get_by_asset_id(self, asset_id):
        return self.record

    def eligibility_for_asset(self, asset_id, *, customer_context=None):
        return SimpleNamespace(
            delivery_eligible=not self.block_reasons,
            block_reasons=self.block_reasons,
            warnings=(),
        )


class FakeFulfillmentRepository:
    def __init__(self, fulfillment=None):
        self.fulfillment = fulfillment if fulfillment is not None else FakeFulfillment()

    def get_by_asset_and_route(self, asset_id, route):
        return self.fulfillment


class FakeHistoryRepository:
    def __init__(self):
        self.events = []

    def record_request(self, payload):
        self.events.append(("request", payload))

    def record_result(self, payload):
        self.events.append(("result", payload))

    def record_success(self, delivery_id, payload):
        self.events.append(("success", delivery_id, payload))

    def record_failure(self, delivery_id, reason, payload=None):
        self.events.append(("failure", delivery_id, reason, payload))


class ChatCommerceDeliveryServiceTests(unittest.TestCase):
    def make_service(self, *, record=None, fulfillment=None, block_reasons=()):
        self.history = FakeHistoryRepository()
        return ChatCommerceDeliveryService(
            chat_commerce_registration_service=FakeChatService(
                record=record,
                block_reasons=block_reasons,
            ),
            fulfillment_repository=FakeFulfillmentRepository(fulfillment),
            content_usage_service=object(),
            content_ownership_service=object(),
            repository=self.history,
        )

    def request(self, **overrides):
        values = {
            "asset_id": 101,
            "recommendation": {
                "asset_id": 101,
                "recommendation_id": "rec-101",
                "media_link": "https://fanvue.example/media/101",
                "provider_media_id": "media-101",
            },
            "customer_context": {"customer_id": "customer-1"},
            "conversation_context": {"conversation_id": "conversation-1"},
            "provider": "telegram",
        }
        values.update(overrides)
        return ChatDeliveryRequest(**values)

    def test_delivery_payload_creation(self):
        service = self.make_service()

        result = service.prepare_delivery(self.request())

        self.assertTrue(result.success)
        self.assertEqual(result.payload.asset_id, 101)
        self.assertEqual(result.payload.product_id, "product-1")
        self.assertEqual(result.payload.experience_id, "experience-1")
        self.assertEqual(result.payload.fanvue_media_link, "https://fanvue.example/media/101")
        self.assertEqual(result.payload.provider_media_uuid, "media-101")
        self.assertEqual(result.payload.recommendation_id, "rec-101")
        self.assertEqual(self.history.events[0][0], "request")
        self.assertEqual(self.history.events[1][0], "result")

    def test_validation_blocks_invalid_media_link(self):
        fulfillment = FakeFulfillment(media_link="not-a-link")
        service = self.make_service(fulfillment=fulfillment)

        result = service.prepare_delivery(self.request())

        self.assertFalse(result.success)
        self.assertIn("invalid_media_link", result.validation.failures)
        self.assertTrue(result.retryable)

    def test_ownership_and_duplicate_suppression_are_exposed(self):
        service = self.make_service(block_reasons=("customer_already_owns_asset",))

        result = service.prepare_delivery(
            self.request(
                customer_context={
                    "customer_id": "customer-1",
                    "seen_asset_ids": ("101",),
                }
            )
        )

        self.assertFalse(result.success)
        self.assertIn("customer_already_owns_asset", result.validation.failures)
        self.assertIn("customer_already_seen_asset", result.validation.failures)

    def test_record_execution_result_persists_success_and_failure(self):
        service = self.make_service()
        result = service.prepare_delivery(self.request())

        service.record_execution_result(
            result,
            SimpleNamespace(status="executed", executed=True, execution_state="sent"),
        )
        service.record_execution_result(
            result.to_context(),
            SimpleNamespace(
                status="failed",
                executed=False,
                execution_state="provider_unavailable",
                blocking_reason="provider_unavailable",
            ),
        )

        event_types = tuple(event[0] for event in self.history.events)
        self.assertIn("success", event_types)
        self.assertIn("failure", event_types)

    def test_retry_request_uses_stable_idempotency_key(self):
        service = self.make_service()
        first = service.prepare_delivery(
            self.request(idempotency_key="retry-key")
        )
        second = service.prepare_delivery(
            self.request(idempotency_key="retry-key", retry_of_delivery_id="old")
        )

        self.assertEqual(first.delivery_id, second.delivery_id)


if __name__ == "__main__":
    unittest.main()

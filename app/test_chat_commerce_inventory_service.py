import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.models.business_learning import BusinessOutcome, BusinessOutcomeType
from app.models.chat_commerce_inventory import ChatCommerceInventoryFilter
from app.models.chat_commerce_registration import (
    ChatAvailabilityState,
    ChatCommerceAssetRecord,
)
from app.models.commerce_destination import DestinationRoutingOwner
from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceDestinationStatus,
    CommerceRegistrationStatus,
)
from app.models.fulfillment_registration import (
    BusinessAssetFulfillmentRecord,
    FulfillmentLifecycleState,
    FulfillmentRoute,
    MediaLinkVerificationState,
)
from app.services.chat_commerce_inventory_service import (
    ChatCommerceInventoryService,
)


def business_asset(
    asset_id,
    *,
    lifecycle=BusinessAssetLifecycleState.DESTINATION_SELECTED,
    destination_status=CommerceDestinationStatus.ROUTED,
    destination="CUSTOMER_CONVERSATIONS",
    product_ids=("product-1",),
    experience_ids=("experience-1",),
    source_workflow="Generation Library",
):
    return BusinessAssetRecord(
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        asset_id=asset_id,
        creator_profile_id=7,
        approval_status="APPROVED",
        content_intelligence_status="READY",
        content_intelligence_ready=True,
        commerce_registration_status=CommerceRegistrationStatus.REGISTERED,
        business_lifecycle_state=lifecycle,
        commerce_destination_status=destination_status,
        selected_commerce_destination=destination,
        destination_source_workflow=source_workflow,
        product_ids=product_ids,
        experience_ids=experience_ids,
    )


def chat_record(
    asset_id,
    *,
    state=ChatAvailabilityState.CHAT_READY,
    chat_ready=True,
    fulfillment_ready=True,
    recommendation_eligible=True,
    delivery_eligible=True,
    temporarily_unavailable=False,
    retired=False,
    block_reasons=(),
):
    return ChatCommerceAssetRecord(
        chat_registration_id=ChatCommerceAssetRecord.deterministic_id(asset_id),
        asset_id=asset_id,
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
            asset_id, FulfillmentRoute.CUSTOMER_CONVERSATIONS
        ),
        creator_profile_id=7,
        commerce_destination="CUSTOMER_CONVERSATIONS",
        availability_state=state,
        chat_ready=chat_ready,
        fulfillment_ready=fulfillment_ready,
        recommendation_eligible=recommendation_eligible,
        delivery_eligible=delivery_eligible,
        temporarily_unavailable=temporarily_unavailable,
        retired=retired,
        product_ids=("product-1",),
        experience_ids=("experience-1",),
        source_workflow="Generation Library",
        media_link="https://fanvue.com/media/ready",
        provider_media_id="media-ready-123",
        block_reasons=block_reasons,
    )


def fulfillment_record(
    asset_id,
    *,
    state=FulfillmentLifecycleState.FULFILLMENT_READY,
    verification=MediaLinkVerificationState.VERIFIED,
    media_link="https://fanvue.com/media/ready",
    retry_required=False,
):
    return BusinessAssetFulfillmentRecord(
        fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
            asset_id, FulfillmentRoute.CUSTOMER_CONVERSATIONS
        ),
        asset_id=asset_id,
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        routing_intent_id=uuid4(),
        route=FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
        provider="fanvue",
        lifecycle_state=state,
        provider_media_id="media-ready-123",
        provider_processing_status="ready",
        media_link=media_link,
        media_link_verification_state=verification,
        retry_required=retry_required,
        provenance={"source_workflow": "Generation Library"},
    )


class FakeAssetLibraryService:
    def get_asset_items(self, asset_ids):
        return tuple(
            SimpleNamespace(
                asset_id=asset_id,
                file_name=f"Asset {asset_id}.png",
                preview_path=f"/tmp/{asset_id}.png",
                relationship=SimpleNamespace(
                    product_ids=("product-1",),
                    experience_ids=("experience-1",),
                ),
                publishing=SimpleNamespace(
                    status="uploaded",
                    provider_media_id=f"library-media-{asset_id}",
                ),
            )
            for asset_id in asset_ids
        )


class FakeCommerceRegistrationRepository:
    def __init__(self, records):
        self.records = tuple(records)

    def list_registered(self, limit=500):
        return tuple(
            record
            for record in self.records
            if record.commerce_destination_status
            != CommerceDestinationStatus.AWAITING_DESTINATION
        )[:limit]

    def list_awaiting_destination(self, limit=500):
        return tuple(
            record
            for record in self.records
            if record.commerce_destination_status
            == CommerceDestinationStatus.AWAITING_DESTINATION
        )[:limit]

    def list_blocked_by_incomplete_intelligence(self, limit=500):
        return tuple(
            record
            for record in self.records
            if record.business_lifecycle_state
            == BusinessAssetLifecycleState.INTELLIGENCE_PENDING
        )[:limit]


class FakeChatCommerceRegistrationService:
    def __init__(self, records):
        self.records = {record.asset_id: record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(asset_id)

    def list_blocked_assets(self, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if record.availability_state == ChatAvailabilityState.BLOCKED
        )[:limit]

    def list_temporarily_unavailable_assets(self, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if record.temporarily_unavailable
        )[:limit]

    def list_retired_assets(self, limit=100):
        return tuple(record for record in self.records.values() if record.retired)[:limit]


class FakeFulfillmentRegistrationService:
    def __init__(self, records):
        self.records = {record.asset_id: record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(asset_id)


class FakeBusinessLearningService:
    def normalize_business_outcomes(self, outcomes):
        return tuple(outcomes or ())


class ChatCommerceInventoryServiceTests(unittest.TestCase):
    def build_service(self, *, records, chat_records=(), fulfillment_records=()):
        return ChatCommerceInventoryService(
            asset_library_service=FakeAssetLibraryService(),
            commerce_registration_repository=FakeCommerceRegistrationRepository(
                records
            ),
            chat_commerce_registration_service=FakeChatCommerceRegistrationService(
                chat_records
            ),
            fulfillment_registration_service=FakeFulfillmentRegistrationService(
                fulfillment_records
            ),
            business_learning_service=FakeBusinessLearningService(),
        )

    def test_build_inventory_projects_business_status_and_metrics(self):
        service = self.build_service(
            records=(
                business_asset(101),
                business_asset(
                    202,
                    lifecycle=BusinessAssetLifecycleState.AWAITING_DESTINATION,
                    destination_status=CommerceDestinationStatus.AWAITING_DESTINATION,
                    destination=None,
                    product_ids=(),
                    experience_ids=(),
                    source_workflow="Photoshoot Library",
                ),
            ),
            chat_records=(chat_record(101),),
            fulfillment_records=(fulfillment_record(101),),
        )
        outcomes = (
            BusinessOutcome(
                outcome_type=BusinessOutcomeType.PRODUCT_OFFERED.value,
                value_cents=0,
                occurred_at="2026-07-12T12:00:00Z",
                provider_metadata={"asset_id": 101},
            ),
            BusinessOutcome(
                outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                value_cents=2500,
                occurred_at="2026-07-12T12:05:00Z",
                provider_metadata={"asset_id": 101},
            ),
            BusinessOutcome(
                outcome_type=BusinessOutcomeType.PRODUCT_DELIVERED.value,
                occurred_at="2026-07-12T12:06:00Z",
                provider_metadata={"asset_id": 101},
            ),
        )

        result = service.build_inventory(business_outcomes=outcomes)

        self.assertEqual(result.summary.total_business_assets, 2)
        self.assertEqual(result.summary.chat_ready, 1)
        self.assertEqual(result.summary.fulfillment_ready, 1)
        self.assertEqual(result.summary.awaiting_destination, 1)
        self.assertEqual(result.summary.total_revenue_cents, 2500)
        self.assertEqual(result.summary.total_purchases, 1)
        self.assertEqual(result.summary.overall_conversion, 1.0)
        self.assertEqual(result.summary.attention_asset_ids, (202,))

        ready_item = next(item for item in result.items if item.asset_id == 101)
        self.assertTrue(ready_item.chat_ready)
        self.assertTrue(ready_item.fulfillment_ready)
        self.assertTrue(ready_item.recommendation_ready)
        self.assertEqual(ready_item.media_link_status, "VERIFIED")
        self.assertEqual(ready_item.fanvue_media_uuid, "media-ready-123")
        self.assertEqual(ready_item.metrics.purchase_count, 1)
        self.assertEqual(ready_item.metrics.delivery_count, 1)
        self.assertEqual(ready_item.metrics.conversion_rate, 1.0)

    def test_pending_registration_appears_in_business_asset_inventory(self):
        pending = business_asset(
            404,
            lifecycle=BusinessAssetLifecycleState.INTELLIGENCE_PENDING,
            destination_status=CommerceDestinationStatus.NOT_READY,
            destination=None,
            product_ids=(),
            experience_ids=(),
            source_workflow="staged_asset_library_registration",
        )
        pending = BusinessAssetRecord(
            **{
                **pending.__dict__,
                "content_intelligence_status": "PENDING",
                "content_intelligence_ready": False,
                "commerce_registration_status": CommerceRegistrationStatus.PENDING,
            }
        )

        result = self.build_service(records=(pending,)).build_inventory()

        self.assertEqual(tuple(item.asset_id for item in result.items), (404,))
        self.assertEqual(result.items[0].current_lifecycle, "INTELLIGENCE_PENDING")
        self.assertEqual(result.items[0].availability, "Pending")
        self.assertFalse(result.items[0].chat_ready)
        self.assertFalse(result.items[0].fulfillment_ready)

    def test_active_projection_keeps_ready_pending_registration_visible(self):
        ready = business_asset(
            405,
            lifecycle=BusinessAssetLifecycleState.INTELLIGENCE_READY,
            destination_status=CommerceDestinationStatus.NOT_READY,
            destination=None,
        )
        ready = BusinessAssetRecord(**{
            **ready.__dict__,
            "content_intelligence_status": "READY",
            "content_intelligence_ready": True,
            "commerce_registration_status": CommerceRegistrationStatus.PENDING,
        })

        class ActiveRepository(FakeCommerceRegistrationRepository):
            def list_active(self, limit=500):
                return self.records[:limit]

        service = self.build_service(records=())
        service.commerce_registrations = ActiveRepository((ready,))

        result = service.build_inventory()

        self.assertEqual(tuple(item.asset_id for item in result.items), (405,))
        self.assertEqual(result.items[0].current_lifecycle, "INTELLIGENCE_READY")

    def test_inventory_query_failure_is_not_reported_as_empty_inventory(self):
        service = self.build_service(records=())

        def fail(*, limit):
            raise RuntimeError("commerce schema is unavailable")

        service.commerce_registrations.list_registered = fail

        with self.assertRaisesRegex(RuntimeError, "commerce schema is unavailable"):
            service.build_inventory()

    def test_filters_by_status_and_relationships(self):
        service = self.build_service(
            records=(
                business_asset(101),
                business_asset(
                    202,
                    lifecycle=BusinessAssetLifecycleState.AWAITING_DESTINATION,
                    destination_status=CommerceDestinationStatus.AWAITING_DESTINATION,
                    destination=None,
                    product_ids=("product-2",),
                    source_workflow="Photoshoot Library",
                ),
            ),
            chat_records=(chat_record(101),),
            fulfillment_records=(fulfillment_record(101),),
        )

        chat_ready = service.build_inventory(
            filters=ChatCommerceInventoryFilter(chat_ready=True)
        )
        product_filtered = service.build_inventory(
            filters=ChatCommerceInventoryFilter(product_id="product-1")
        )
        awaiting = service.build_inventory(
            filters=ChatCommerceInventoryFilter(awaiting_destination=True)
        )

        self.assertEqual(tuple(item.asset_id for item in chat_ready.items), (101,))
        self.assertEqual(tuple(item.asset_id for item in product_filtered.items), (101,))
        self.assertEqual(tuple(item.asset_id for item in awaiting.items), (202,))

    def test_waiting_for_media_link_exposes_creator_actions(self):
        service = self.build_service(
            records=(business_asset(303),),
            fulfillment_records=(
                fulfillment_record(
                    303,
                    state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
                    verification=MediaLinkVerificationState.MISSING,
                    media_link=None,
                ),
            ),
        )

        result = service.build_inventory()
        item = result.items[0]

        self.assertTrue(item.waiting_for_media_link)
        self.assertIn("Open Fanvue", item.quick_actions)
        self.assertIn("Paste Media Link", item.quick_actions)
        self.assertIn("Verify Media Link", item.quick_actions)
        self.assertEqual(result.summary.waiting_for_media_link, 1)
        self.assertEqual(result.summary.attention_asset_ids, (303,))

    def test_attention_chat_records_dedupes_operational_chat_queues(self):
        blocked = chat_record(
            404,
            state=ChatAvailabilityState.BLOCKED,
            chat_ready=False,
            recommendation_eligible=False,
            delivery_eligible=False,
            block_reasons=("media_link_not_verified",),
        )
        unavailable = chat_record(
            404,
            state=ChatAvailabilityState.TEMPORARILY_UNAVAILABLE,
            temporarily_unavailable=True,
        )
        retired = chat_record(
            505,
            state=ChatAvailabilityState.RETIRED,
            chat_ready=False,
            recommendation_eligible=False,
            delivery_eligible=False,
            retired=True,
        )
        service = self.build_service(
            records=(business_asset(404), business_asset(505)),
            chat_records=(blocked, unavailable, retired),
        )

        records = service.attention_chat_records()

        self.assertEqual(tuple(record.asset_id for record in records), (404, 505))


if __name__ == "__main__":
    unittest.main()

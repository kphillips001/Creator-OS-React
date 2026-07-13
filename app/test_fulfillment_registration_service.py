import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.commerce_destination import (
    CommerceDestination,
    DestinationRoutingIntent,
    DestinationRoutingOwner,
    DestinationRoutingStatus,
)
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
    MediaLinkSubmission,
    MediaLinkVerificationState,
)
from app.models.generation_engine import utc_now
from app.services.fulfillment_registration_service import (
    CUSTOMER_CONVERSATIONS_FANVUE_FOLDER,
    FulfillmentRegistrationService,
)


def business_asset(asset_id=101):
    return BusinessAssetRecord(
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        asset_id=asset_id,
        creator_profile_id=7,
        approval_status="approved",
        content_intelligence_status="COMPLETE",
        content_intelligence_ready=True,
        commerce_registration_status=CommerceRegistrationStatus.REGISTERED,
        business_lifecycle_state=BusinessAssetLifecycleState.ROUTING_PENDING,
        commerce_destination_status=CommerceDestinationStatus.ROUTING_PENDING,
        selected_commerce_destination=CommerceDestination.CUSTOMER_CONVERSATIONS.value,
        registration_provenance={
            "approval_identity": {
                "source_workflow": "generation_library",
                "source_item_id": str(asset_id),
                "idempotency_key": f"generation:{asset_id}",
            },
            ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                AssetProvenanceClassification.CREATOR_APPROVAL,
                source="test",
                source_workflow="generation_library",
            ),
        },
    )


def routing_intent(asset_id=101, owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS):
    selected = (
        CommerceDestination.BOTH
        if owner == DestinationRoutingOwner.TELEGRAM_WALL
        else CommerceDestination.CUSTOMER_CONVERSATIONS
    )
    return DestinationRoutingIntent(
        routing_intent_id=uuid4(),
        asset_id=asset_id,
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        selected_destination=selected,
        routing_owner=owner,
        routing_status=DestinationRoutingStatus.ROUTING_PENDING,
        source_workflow="generation_library",
        created_at=utc_now(),
        updated_at=utc_now(),
    )


class MemoryRegistrationRepository:
    def __init__(self, records=()):
        self.records = {int(record.asset_id): record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record


class MemoryDestinationRepository:
    def __init__(self, intents=()):
        self.intents = {str(intent.routing_intent_id): intent for intent in intents}

    def list_pending_routing_intents(self, *, limit=100):
        return tuple(
            intent
            for intent in self.intents.values()
            if intent.routing_status == DestinationRoutingStatus.ROUTING_PENDING
        )[:limit]

    def list_routing_intents(self, asset_id, *, include_cancelled=True):
        return tuple(
            intent
            for intent in self.intents.values()
            if int(intent.asset_id) == int(asset_id)
            and (include_cancelled or intent.routing_status != DestinationRoutingStatus.CANCELLED)
        )

    def upsert_routing_intent(self, intent):
        self.intents[str(intent.routing_intent_id)] = intent
        return intent


class MemoryFulfillmentRepository:
    def __init__(self):
        self.records = {}
        self.history = []

    def get_by_asset_and_route(self, asset_id, route):
        route_value = route.value if hasattr(route, "value") else str(route)
        return self.records.get((int(asset_id), route_value))

    def get_by_route_intent_id(self, routing_intent_id):
        for record in self.records.values():
            if str(record.routing_intent_id) == str(routing_intent_id):
                return record
        return None

    def get_by_media_link(self, media_link):
        for record in self.records.values():
            if record.media_link == media_link:
                return record
        return None

    def upsert_record(self, record):
        stored = replace(record, updated_at=utc_now(), created_at=record.created_at or utc_now())
        self.records[(stored.asset_id, stored.route.value)] = stored
        self.history.append(stored)
        return stored

    def list_by_state(self, state, *, limit=100):
        value = state.value if hasattr(state, "value") else str(state)
        return tuple(
            record for record in self.records.values() if record.lifecycle_state.value == value
        )[:limit]


class FakePublishingService:
    def __init__(self):
        self.jobs = {}
        self.ensure_calls = []
        self.upload_calls = []
        self.link_calls = []

    def ensure_asset_publishing_job(self, **kwargs):
        self.ensure_calls.append(kwargs)
        key = (int(kwargs["asset_id"]), kwargs.get("route_owner"))
        if key in self.jobs:
            return self.jobs[key]
        job = SimpleNamespace(
            id=uuid4(),
            product_id=None,
            asset_id=int(kwargs["asset_id"]),
            provider=kwargs.get("provider") or "fanvue",
            provider_account_id=kwargs.get("provider_account_id"),
            status="QUEUED",
            media_link_status="REQUIRED",
            provider_status=None,
            provider_output_url=None,
            provider_media_id=None,
            provider_preview_media_id=None,
            provider_full_media_id=None,
            provider_metadata=kwargs.get("provider_metadata") or {},
            failure_reason=None,
            retry_count=0,
            max_retries=3,
            next_retry_at=None,
            upload_started_at=None,
            uploaded_at=None,
            completed_at=None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.jobs[key] = job
        return job

    def get_publishing_job(self, job_id):
        for job in self.jobs.values():
            if job.id == job_id:
                return job
        return None

    def project_publishing_status(self, job):
        status = getattr(job, "status", "QUEUED")
        publishing = {
            "QUEUED": "QUEUED",
            "UPLOADING": "UPLOADING",
            "UPLOADED": "WAITING_FOR_MEDIA_LINK",
            "COMPLETED": "PUBLISHING_COMPLETE",
            "FAILED": "RETRY_REQUIRED",
        }.get(status, status)
        return SimpleNamespace(publishing_status=publishing)

    def upload_asset_media_item_for_job(self, **kwargs):
        self.upload_calls.append(kwargs)
        job = self.get_publishing_job(kwargs["job_id"])
        job.status = "UPLOADED"
        job.provider_media_id = f"media-{kwargs['item']['id']}"
        job.provider_preview_media_id = job.provider_media_id
        job.provider_full_media_id = job.provider_media_id
        result = {
            "success": True,
            "media_uuid": job.provider_media_id,
            "preview_uuid": job.provider_media_id,
            "full_uuid": job.provider_media_id,
            "status": "ready",
            "folder_name": kwargs["item"].get("folder_name"),
            "folder_success": True,
        }
        return {"job": job, "upload_result": result}

    def validate_publishing_media_link(self, media_link, **kwargs):
        link = (media_link or "").strip()
        valid = link.startswith("https://")
        return {
            "valid": valid,
            "media_link": link,
            "errors": () if valid else ("invalid_media_link_url",),
            "warnings": (),
        }

    def complete_publishing_media_link_workflow(self, job_id, **kwargs):
        self.link_calls.append({"job_id": job_id, **kwargs})
        job = self.get_publishing_job(job_id)
        job.status = "COMPLETED"
        job.provider_output_url = kwargs["media_link"]
        return {"success": True, "job": job, "product": None}


class MemoryAssetRepository:
    def __init__(self, assets):
        self.assets = {int(asset.id): asset for asset in assets}

    def get_by_id(self, asset_id):
        return self.assets.get(int(asset_id))


class FakeChatCommerceRegistrationService:
    def __init__(self):
        self.calls = []

    def register_fulfilled_asset(self, asset_id, **kwargs):
        self.calls.append({"asset_id": int(asset_id), **kwargs})
        return SimpleNamespace(success=True, asset_id=int(asset_id), chat_ready=True)


class FulfillmentRegistrationServiceTests(unittest.TestCase):
    def make_service(
        self,
        *,
        asset_id=101,
        asset_path=None,
        extra_intents=(),
        chat_commerce_registration_service=None,
    ):
        intent = routing_intent(asset_id)
        self.registration_repo = MemoryRegistrationRepository((business_asset(asset_id),))
        self.destination_repo = MemoryDestinationRepository((intent, *extra_intents))
        self.fulfillment_repo = MemoryFulfillmentRepository()
        self.publishing = FakePublishingService()
        asset = SimpleNamespace(
            id=asset_id,
            file_path=str(asset_path or "missing.png"),
            classification="VIP_IMAGE",
            media_metadata={},
            local_vault_path=None,
        )
        self.asset_repo = MemoryAssetRepository((asset,))
        self.intent = intent
        return FulfillmentRegistrationService(
            fulfillment_repository=self.fulfillment_repo,
            registration_repository=self.registration_repo,
            destination_repository=self.destination_repo,
            publishing_service=self.publishing,
            asset_repository=self.asset_repo,
            chat_commerce_registration_service=chat_commerce_registration_service,
        )

    def test_customer_conversations_routing_intent_creates_record_and_job(self):
        service = self.make_service()

        result = service.consume_pending_customer_conversation_intents(provider_account_id=2)[0]

        self.assertTrue(result.success)
        self.assertEqual(result.record.asset_id, 101)
        self.assertEqual(result.record.route, FulfillmentRoute.CUSTOMER_CONVERSATIONS)
        self.assertEqual(result.record.publishing_job_id, result.publishing_job.id)
        self.assertEqual(result.record.lifecycle_state, FulfillmentLifecycleState.UPLOAD_QUEUED)
        self.assertEqual(self.publishing.ensure_calls[0]["asset_id"], 101)

    def test_duplicate_start_reuses_existing_job_and_record(self):
        service = self.make_service()

        first = service.consume_pending_customer_conversation_intents(provider_account_id=2)[0]
        second = service.create_or_start_fulfillment(
            service._request_from_intent(self.intent, provider_account_id=2)
        )

        self.assertEqual(first.record.fulfillment_id, second.record.fulfillment_id)
        self.assertEqual(first.publishing_job.id, second.publishing_job.id)
        self.assertEqual(len(self.publishing.jobs), 1)

    def test_upload_uses_canonical_asset_id_and_waits_for_media_link(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "asset.png"
            path.write_bytes(b"asset")
            service = self.make_service(asset_path=path)
            service.consume_pending_customer_conversation_intents(provider_account_id=2)

            result = service.upload_customer_conversations_asset(
                asset_id=101,
                fanvue_account_id=2,
            )

        self.assertTrue(result.success)
        self.assertEqual(self.publishing.upload_calls[0]["item"]["id"], 101)
        self.assertEqual(
            self.publishing.upload_calls[0]["item"]["folder_name"],
            CUSTOMER_CONVERSATIONS_FANVUE_FOLDER,
        )
        self.assertEqual(result.record.provider_media_id, "media-101")
        self.assertEqual(
            result.record.lifecycle_state,
            FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
        )
        projected = self.registration_repo.get_by_asset_id(101).fulfillment_readiness
        self.assertTrue(projected["waiting_for_media_link"])

    def test_asset_level_media_link_verifies_without_product(self):
        service = self.make_service()
        service.consume_pending_customer_conversation_intents(provider_account_id=2)
        record = self.fulfillment_repo.get_by_asset_and_route(
            101,
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        )
        self.fulfillment_repo.upsert_record(
            replace(
                record,
                provider_media_id="media-101",
                lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
            )
        )

        result = service.submit_media_link(
            MediaLinkSubmission(
                asset_id=101,
                creator_profile_id=7,
                media_link="https://fanvue.example/media-link",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(result.record.lifecycle_state, FulfillmentLifecycleState.FULFILLMENT_READY)
        self.assertEqual(result.record.media_link_verification_state, MediaLinkVerificationState.VERIFIED)
        self.assertIsNone(self.publishing.link_calls[0].get("product_id"))
        projected = self.registration_repo.get_by_asset_id(101).fulfillment_readiness
        self.assertTrue(projected["fulfillment_ready"])
        self.assertEqual(
            self.destination_repo.intents[str(self.intent.routing_intent_id)].routing_status,
            DestinationRoutingStatus.FULFILLMENT_READY,
        )

    def test_verified_media_link_triggers_chat_registration_bridge(self):
        chat_registration = FakeChatCommerceRegistrationService()
        service = self.make_service(
            chat_commerce_registration_service=chat_registration
        )
        service.consume_pending_customer_conversation_intents(provider_account_id=2)
        record = self.fulfillment_repo.get_by_asset_and_route(
            101,
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        )
        self.fulfillment_repo.upsert_record(
            replace(
                record,
                provider_media_id="media-101",
                lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK,
            )
        )

        result = service.submit_media_link(
            MediaLinkSubmission(
                asset_id=101,
                creator_profile_id=7,
                media_link="https://fanvue.example/media-link",
            )
        )

        self.assertTrue(result.success)
        self.assertEqual(chat_registration.calls[0]["asset_id"], 101)
        self.assertTrue(
            str(chat_registration.calls[0]["idempotency_key"]).startswith(
                "fulfillment-ready:"
            )
        )

    def test_duplicate_media_link_is_rejected(self):
        service = self.make_service()
        service.consume_pending_customer_conversation_intents(provider_account_id=2)
        other = BusinessAssetFulfillmentRecord(
            fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
                202,
                FulfillmentRoute.CUSTOMER_CONVERSATIONS,
            ),
            asset_id=202,
            registration_id=BusinessAssetRecord.deterministic_id(202),
            routing_intent_id=uuid4(),
            route=FulfillmentRoute.CUSTOMER_CONVERSATIONS,
            route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
            provider="fanvue",
            lifecycle_state=FulfillmentLifecycleState.FULFILLMENT_READY,
            media_link="https://fanvue.example/dupe",
            media_link_verification_state=MediaLinkVerificationState.VERIFIED,
        )
        self.fulfillment_repo.upsert_record(other)
        record = self.fulfillment_repo.get_by_asset_and_route(101, FulfillmentRoute.CUSTOMER_CONVERSATIONS)
        self.fulfillment_repo.upsert_record(
            replace(record, lifecycle_state=FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK)
        )

        result = service.submit_media_link(
            MediaLinkSubmission(
                asset_id=101,
                creator_profile_id=7,
                media_link="https://fanvue.example/dupe",
            )
        )

        self.assertFalse(result.success)
        self.assertIn("duplicate_media_link", result.errors)

    def test_retry_reuses_existing_provider_media_uuid(self):
        service = self.make_service()
        service.consume_pending_customer_conversation_intents(provider_account_id=2)
        record = self.fulfillment_repo.get_by_asset_and_route(101, FulfillmentRoute.CUSTOMER_CONVERSATIONS)
        self.fulfillment_repo.upsert_record(
            replace(
                record,
                provider_media_id="media-existing",
                lifecycle_state=FulfillmentLifecycleState.RETRY_REQUIRED,
                retry_required=True,
            )
        )

        result = service.retry_fulfillment(asset_id=101, fanvue_account_id=2)

        self.assertTrue(result.success)
        self.assertEqual(result.record.provider_media_id, "media-existing")
        self.assertEqual(self.publishing.upload_calls, [])
        self.assertIn("existing_provider_media_reused", result.warnings)

    def test_both_destination_keeps_wall_route_independent(self):
        wall = routing_intent(101, owner=DestinationRoutingOwner.TELEGRAM_WALL)
        service = self.make_service(extra_intents=(wall,))

        service.consume_pending_customer_conversation_intents(provider_account_id=2)

        self.assertEqual(
            self.destination_repo.intents[str(wall.routing_intent_id)].routing_status,
            DestinationRoutingStatus.ROUTING_PENDING,
        )
        self.assertEqual(len(self.publishing.jobs), 1)

    def test_legacy_upload_backfill_registers_without_uploading(self):
        service = self.make_service()

        result = service.register_legacy_upload(
            asset_id=101,
            provider_media_id="legacy-media",
            routing_intent_id=self.intent.routing_intent_id,
            registration_id=self.intent.registration_id,
            metadata={"legacy_source": "content_items"},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.record.provider_media_id, "legacy-media")
        self.assertEqual(result.record.lifecycle_state, FulfillmentLifecycleState.WAITING_FOR_MEDIA_LINK)
        self.assertEqual(self.publishing.upload_calls, [])

    def test_ambiguous_legacy_upload_is_not_guessed(self):
        service = self.make_service()

        result = service.register_legacy_upload(
            asset_id=101,
            provider_media_id="",
            routing_intent_id=self.intent.routing_intent_id,
            registration_id=self.intent.registration_id,
        )

        self.assertFalse(result.success)
        self.assertIn("ambiguous_legacy_upload", result.errors)


if __name__ == "__main__":
    unittest.main()

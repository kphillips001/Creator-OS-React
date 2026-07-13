import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    administrative_import_context,
    provenance_context,
)
from app.models.commerce_destination import (
    CommerceDestination,
    CommerceDestinationRequest,
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
from app.models.creator_approval import CreatorApprovalAdapterRequest
from app.models.fulfillment_registration import FulfillmentRegistrationRequest
from app.services.chat_commerce_registration_service import ChatCommerceRegistrationService
from app.services.commerce_destination_service import CommerceDestinationService
from app.services.commerce_registration_service import CommerceRegistrationService
from app.services.fulfillment_registration_service import FulfillmentRegistrationService


class MemoryAssetRepository:
    def __init__(self, assets=()):
        self.assets = {int(asset.id): asset for asset in assets}

    def get_by_id(self, asset_id):
        return self.assets.get(int(asset_id))

    def update_media_metadata(self, asset_id, media_metadata):
        asset = self.assets[int(asset_id)]
        asset.media_metadata = dict(media_metadata or {})

    def search_assets(self, **kwargs):
        return tuple(self.assets.values())


class MemoryProfileRepository:
    def __init__(self, profiles):
        self.profiles = dict(profiles)

    def get_by_asset_id(self, asset_id):
        return self.profiles.get(int(asset_id))


class MemoryRegistrationRepository:
    def __init__(self, records=()):
        self.records = {int(record.asset_id): record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record

    def list_registered(self, *, limit=500):
        return tuple(self.records.values())[:limit]

    def list_awaiting_destination(self, *, limit=500):
        return tuple(self.records.values())[:limit]

    def list_blocked_by_incomplete_intelligence(self, *, limit=500):
        return ()


class MemoryDestinationRepository:
    def __init__(self, intents=()):
        self.intents = {str(intent.routing_intent_id): intent for intent in intents}
        self.history = []

    def append_history(self, entry):
        self.history.append(entry)
        return entry

    def history_by_idempotency_key(self, key):
        return None

    def list_history(self, asset_id, *, limit=100):
        return ()

    def upsert_routing_intent(self, intent):
        self.intents[str(intent.routing_intent_id)] = intent
        return intent

    def list_routing_intents(self, asset_id, *, include_cancelled=True):
        return tuple(
            intent for intent in self.intents.values() if int(intent.asset_id) == int(asset_id)
        )

    def list_pending_routing_intents(self, *, limit=100):
        return tuple(self.intents.values())[:limit]


class MemoryFulfillmentRepository:
    def get_by_asset_and_route(self, asset_id, route):
        return None


class MemoryChatRepository:
    def __init__(self):
        self.records = {}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record


class EmptyProductAssetRepository:
    def list_product_ids_for_asset(self, asset_id):
        return ()


class EmptyProductRepository:
    def get_by_legacy_content_item_id(self, asset_id):
        return None

    def get_by_id(self, product_id):
        return None


class EmptyExperienceService:
    def list_asset_relationships(self, asset_id):
        return ()


class FakePublishingService:
    def project_legacy_asset_record(self, asset):
        return {}

    def get_provider_status_display(self, record, **kwargs):
        return "Not Uploaded", "Local asset only"

    def ensure_asset_publishing_job(self, **kwargs):
        return SimpleNamespace(id=uuid4())

    def project_publishing_status(self, job):
        return SimpleNamespace(publishing_status="QUEUED")


def profile():
    return SimpleNamespace(profile_id="profile-101", ready=True, status=SimpleNamespace(value="COMPLETE"))


def asset(asset_id=101, *, provenance=AssetProvenanceClassification.CREATOR_APPROVAL):
    metadata = {}
    if provenance == AssetProvenanceClassification.CREATOR_APPROVAL:
        metadata["creator_approval"] = {
            "source_workflow": "generation_library",
            "source_item_id": str(asset_id),
            "idempotency_key": f"generation:{asset_id}",
        }
        metadata[ASSET_PROVENANCE_METADATA_KEY] = provenance_context(
            provenance,
            source="test",
            source_workflow="generation_library",
        )
    else:
        metadata[ASSET_PROVENANCE_METADATA_KEY] = administrative_import_context(
            source="test",
            source_workflow="cms_upload",
        )
    return SimpleNamespace(
        id=asset_id,
        status="approved",
        creator_profile_id=7,
        fanvue_upload_status=None,
        fanvue_media_full_uuid=None,
        media_metadata=metadata,
    )


def business_asset(asset_id=101, *, provenance=AssetProvenanceClassification.CREATOR_APPROVAL):
    registration_provenance = {}
    if provenance == AssetProvenanceClassification.CREATOR_APPROVAL:
        registration_provenance = {
            "approval_identity": {
                "source_workflow": "generation_library",
                "source_item_id": str(asset_id),
                "idempotency_key": f"generation:{asset_id}",
            },
            ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                provenance,
                source="test",
                source_workflow="generation_library",
            ),
        }
    else:
        registration_provenance = {
            ASSET_PROVENANCE_METADATA_KEY: administrative_import_context(
                source="test",
                source_workflow="cms_upload",
            )
        }
    return BusinessAssetRecord(
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        asset_id=asset_id,
        creator_profile_id=7,
        approval_status="approved",
        content_intelligence_status="COMPLETE",
        content_intelligence_ready=True,
        commerce_registration_status=CommerceRegistrationStatus.REGISTERED,
        business_lifecycle_state=BusinessAssetLifecycleState.AWAITING_DESTINATION,
        commerce_destination_status=CommerceDestinationStatus.AWAITING_DESTINATION,
        selected_commerce_destination=CommerceDestination.CUSTOMER_CONVERSATIONS.value,
        registration_provenance=registration_provenance,
    )


class Phase31014CreatorApprovalBoundaryTests(unittest.TestCase):
    def test_administrative_asset_cannot_auto_register_for_commerce(self):
        service = CommerceRegistrationService(
            registration_repository=MemoryRegistrationRepository(),
            asset_repository=MemoryAssetRepository(
                (asset(provenance=AssetProvenanceClassification.ADMINISTRATIVE_IMPORT),)
            ),
            content_intelligence_repository=MemoryProfileRepository({101: profile()}),
            product_asset_repository=EmptyProductAssetRepository(),
            product_repository=EmptyProductRepository(),
            experience_service=EmptyExperienceService(),
            publishing_service=FakePublishingService(),
        )

        result = service.register_asset(101)

        self.assertFalse(result.success)
        self.assertIn("creator_approval_provenance_required", result.errors)

    def test_creator_approved_asset_can_auto_register_for_commerce(self):
        service = CommerceRegistrationService(
            registration_repository=MemoryRegistrationRepository(),
            asset_repository=MemoryAssetRepository((asset(),)),
            content_intelligence_repository=MemoryProfileRepository({101: profile()}),
            product_asset_repository=EmptyProductAssetRepository(),
            product_repository=EmptyProductRepository(),
            experience_service=EmptyExperienceService(),
            publishing_service=FakePublishingService(),
        )

        result = service.register_asset(101)

        self.assertTrue(result.success)
        self.assertEqual(result.record.commerce_registration_status, CommerceRegistrationStatus.REGISTERED)

    def test_administrative_business_asset_cannot_select_autonomous_destination(self):
        repo = MemoryRegistrationRepository(
            (business_asset(provenance=AssetProvenanceClassification.ADMINISTRATIVE_IMPORT),)
        )
        service = CommerceDestinationService(
            registration_repository=repo,
            destination_repository=MemoryDestinationRepository(),
            asset_repository=object(),
        )

        result = service.set_destination(
            CommerceDestinationRequest(
                asset_id=101,
                registration_id=BusinessAssetRecord.deterministic_id(101),
                destination=CommerceDestination.CUSTOMER_CONVERSATIONS,
            )
        )

        self.assertFalse(result.success)
        self.assertIn("creator_approval_provenance_required", result.errors)

    def test_non_creator_business_asset_cannot_start_fulfillment_or_chat_registration(self):
        record = business_asset(provenance=AssetProvenanceClassification.ADMINISTRATIVE_IMPORT)
        registration_repo = MemoryRegistrationRepository((record,))
        intent = DestinationRoutingIntent(
            routing_intent_id=uuid4(),
            asset_id=101,
            registration_id=record.registration_id,
            selected_destination=CommerceDestination.CUSTOMER_CONVERSATIONS,
            routing_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
            routing_status=DestinationRoutingStatus.ROUTING_PENDING,
        )
        fulfillment = FulfillmentRegistrationService(
            fulfillment_repository=MemoryFulfillmentRepository(),
            registration_repository=registration_repo,
            destination_repository=MemoryDestinationRepository((intent,)),
            publishing_service=FakePublishingService(),
            asset_repository=MemoryAssetRepository((asset(),)),
        )
        fulfillment_result = fulfillment.create_or_start_fulfillment(
            FulfillmentRegistrationRequest(
                asset_id=101,
                registration_id=record.registration_id,
                routing_intent_id=intent.routing_intent_id,
            )
        )
        self.assertFalse(fulfillment_result.success)
        self.assertIn("creator_approval_provenance_required", fulfillment_result.errors)

        chat = ChatCommerceRegistrationService(
            chat_repository=MemoryChatRepository(),
            registration_repository=registration_repo,
            fulfillment_repository=MemoryFulfillmentRepository(),
            asset_repository=MemoryAssetRepository((asset(),)),
        )
        chat_result = chat.register_fulfilled_asset(101)
        self.assertFalse(chat_result.success)
        self.assertIn("creator_approval_provenance_required", chat_result.errors)

    def test_future_workflow_adapter_shapes_creator_approval_request(self):
        for workflow in ("story_studio", "video_studio", "audio_studio"):
            request = CreatorApprovalAdapterRequest(
                source_workflow=workflow,
                source_item_id=f"{workflow}-item",
                source_session_id=f"{workflow}-session",
                media_reference=f"/tmp/{workflow}.bin",
                creator_profile_id=7,
                approval_intent={"destination": "CUSTOMER_CONVERSATIONS"},
                idempotency_key=f"{workflow}:item:1",
            ).to_approval_request()

            self.assertEqual(request.source.source_workflow, workflow)
            self.assertEqual(request.source.normalized_key(), f"{workflow}:item:1")
            self.assertEqual(
                request.source_metadata["adapter_contract"],
                "CreatorApprovalAdapterRequest",
            )


if __name__ == "__main__":
    unittest.main()

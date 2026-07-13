import unittest
from pathlib import Path
from uuid import UUID

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.commerce_destination import (
    CommerceDestination,
    CommerceDestinationRequest,
    DestinationRoutingStatus,
)
from app.models.commerce_registration import (
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceDestinationStatus,
    CommerceRegistrationStatus,
)
from app.services.commerce_destination_service import CommerceDestinationService


class MemoryRegistrationRepository:
    def __init__(self, records=()):
        self.records = {int(record.asset_id): record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record

    def list_awaiting_destination(self, *, limit=500):
        return tuple(
            record
            for record in self.records.values()
            if record.commerce_destination_status
            == CommerceDestinationStatus.AWAITING_DESTINATION
        )[:limit]

    def list_registered(self, *, limit=500):
        return tuple(
            record
            for record in self.records.values()
            if record.commerce_registration_status == CommerceRegistrationStatus.REGISTERED
        )[:limit]


class MemoryDestinationRepository:
    def __init__(self):
        self.history = []
        self.intents = {}

    def append_history(self, entry):
        self.history.append(entry)
        return entry

    def history_by_idempotency_key(self, idempotency_key):
        for entry in reversed(self.history):
            if entry.idempotency_key == idempotency_key:
                return entry
        return None

    def list_history(self, asset_id, *, limit=100):
        return tuple(
            entry for entry in reversed(self.history) if int(entry.asset_id) == int(asset_id)
        )[:limit]

    def upsert_routing_intent(self, intent):
        self.intents[str(intent.routing_intent_id)] = intent
        return intent

    def list_routing_intents(self, asset_id, *, include_cancelled=True):
        intents = tuple(
            intent
            for intent in self.intents.values()
            if int(intent.asset_id) == int(asset_id)
        )
        if not include_cancelled:
            intents = tuple(
                intent
                for intent in intents
                if intent.routing_status != DestinationRoutingStatus.CANCELLED
            )
        return tuple(sorted(intents, key=lambda item: item.routing_owner.value))

    def list_pending_routing_intents(self, *, limit=100):
        return tuple(
            intent
            for intent in self.intents.values()
            if intent.routing_status == DestinationRoutingStatus.ROUTING_PENDING
        )[:limit]


def business_asset(asset_id=101):
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


class CommerceDestinationServiceTests(unittest.TestCase):
    def make_service(self, record=None):
        self.registration_repository = MemoryRegistrationRepository(
            (record or business_asset(),)
        )
        self.destination_repository = MemoryDestinationRepository()
        return CommerceDestinationService(
            registration_repository=self.registration_repository,
            destination_repository=self.destination_repository,
            asset_repository=object(),
        )

    def request(self, destination, *, asset_id=101, key="key-1"):
        record = self.registration_repository.get_by_asset_id(asset_id)
        return CommerceDestinationRequest(
            asset_id=asset_id,
            registration_id=record.registration_id,
            destination=destination,
            creator_profile_id=7,
            source_workflow="generation_library",
            source_session_id="session-1",
            reason="creator choice",
            idempotency_key=key,
        )

    def test_approved_business_asset_begins_awaiting_destination(self):
        record = business_asset()
        self.assertEqual(record.business_lifecycle_state.value, "AWAITING_DESTINATION")
        self.assertEqual(record.commerce_destination_status.value, "AWAITING_DESTINATION")
        self.assertIsNone(record.selected_commerce_destination)

    def test_creator_can_select_each_supported_destination(self):
        for destination in CommerceDestination:
            service = self.make_service(business_asset(asset_id=200 + len(destination.value)))
            record = next(iter(self.registration_repository.records.values()))
            result = service.set_destination(
                CommerceDestinationRequest(
                    asset_id=record.asset_id,
                    registration_id=record.registration_id,
                    destination=destination,
                    creator_profile_id=7,
                    source_workflow="generation_library",
                    idempotency_key=f"select:{destination.value}",
                )
            )
            self.assertTrue(result.success)
            self.assertEqual(result.selected_destination, destination)
            self.assertEqual(
                self.registration_repository.records[record.asset_id].selected_commerce_destination,
                destination.value,
            )

    def test_repeated_identical_selection_is_idempotent(self):
        service = self.make_service()

        first = service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL))
        second = service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL))

        self.assertTrue(first.changed)
        self.assertTrue(second.unchanged)
        self.assertEqual(len(self.destination_repository.history), 1)
        self.assertEqual(len(self.destination_repository.intents), 1)

    def test_both_creates_two_independent_routing_intents(self):
        service = self.make_service()

        result = service.set_destination(self.request(CommerceDestination.BOTH))

        owners = {intent.routing_owner.value for intent in result.routing_intents}
        self.assertEqual(owners, {"TELEGRAM_WALL", "CUSTOMER_CONVERSATIONS"})
        self.assertTrue(
            all(intent.routing_status.value == "ROUTING_PENDING" for intent in result.routing_intents)
        )

    def test_archive_only_creates_no_chat_or_wall_readiness(self):
        service = self.make_service()

        result = service.set_destination(self.request(CommerceDestination.ARCHIVE_ONLY))

        owners = {intent.routing_owner.value for intent in result.routing_intents}
        self.assertEqual(owners, {"ARCHIVE"})
        record = self.registration_repository.get_by_asset_id(101)
        self.assertEqual(record.selected_commerce_destination, "ARCHIVE_ONLY")
        self.assertNotEqual(record.business_lifecycle_state.value, "CHAT_READY")
        self.assertNotEqual(record.business_lifecycle_state.value, "PUBLISHING_READY")

    def test_destination_changes_write_history(self):
        service = self.make_service()
        service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL, key="one"))

        service.set_destination(self.request(CommerceDestination.CUSTOMER_CONVERSATIONS, key="two"))

        self.assertEqual(len(self.destination_repository.history), 2)
        latest = self.destination_repository.history[-1]
        self.assertEqual(latest.previous_destination, CommerceDestination.TELEGRAM_WALL)
        self.assertEqual(latest.new_destination, CommerceDestination.CUSTOMER_CONVERSATIONS)

    def test_adding_destination_creates_only_missing_intent(self):
        service = self.make_service()
        service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL, key="wall"))

        result = service.set_destination(self.request(CommerceDestination.BOTH, key="both"))

        self.assertEqual(len(result.routing_intents_created), 1)
        self.assertEqual(
            result.routing_intents_created[0].routing_owner.value,
            "CUSTOMER_CONVERSATIONS",
        )
        self.assertEqual(len(self.destination_repository.intents), 2)

    def test_removing_pending_destination_cancels_only_pending_intent(self):
        service = self.make_service()
        service.set_destination(self.request(CommerceDestination.BOTH, key="both"))

        service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL, key="wall"))

        statuses = service.per_route_status(101)
        self.assertEqual(statuses["TELEGRAM_WALL"], "ROUTING_PENDING")
        self.assertEqual(statuses["CUSTOMER_CONVERSATIONS"], "CANCELLED")

    def test_completed_external_actions_are_not_reversed(self):
        service = self.make_service()
        service.set_destination(self.request(CommerceDestination.BOTH, key="both"))
        for intent in list(self.destination_repository.intents.values()):
            if intent.routing_owner.value == "CUSTOMER_CONVERSATIONS":
                self.destination_repository.upsert_routing_intent(
                    intent.__class__(
                        **{
                            **intent.__dict__,
                            "routing_status": DestinationRoutingStatus.ROUTED,
                        }
                    )
                )

        result = service.set_destination(self.request(CommerceDestination.TELEGRAM_WALL, key="wall"))

        self.assertIn(
            "completed_route_not_reversed:CUSTOMER_CONVERSATIONS",
            result.warnings,
        )
        self.assertEqual(service.per_route_status(101)["CUSTOMER_CONVERSATIONS"], "ROUTED")

    def test_compatibility_mapping_infers_only_unambiguous_destinations(self):
        self.assertEqual(
            CommerceDestinationService.suggest_destination_from_compatibility(
                {"upload_intent": "wall_image"}
            ),
            CommerceDestination.TELEGRAM_WALL,
        )
        self.assertEqual(
            CommerceDestinationService.suggest_destination_from_compatibility(
                {"delivery_type": "paid_chat"}
            ),
            CommerceDestination.CUSTOMER_CONVERSATIONS,
        )
        self.assertEqual(
            CommerceDestinationService.suggest_destination_from_compatibility(
                {"archive_only": True}
            ),
            CommerceDestination.ARCHIVE_ONLY,
        )
        self.assertIsNone(
            CommerceDestinationService.suggest_destination_from_compatibility(
                {"upload_intent": "wall_image", "delivery_type": "paid_chat"}
            )
        )

    def test_generation_and_photoshoot_ui_use_shared_service(self):
        source = Path("app/dashboard/pages/content_studio.py").read_text(encoding="utf-8")

        self.assertIn("CommerceDestinationService", source)
        self.assertIn("_render_commerce_destination_selector", source)
        self.assertIn('source_workflow="generation_library"', source)
        self.assertIn('source_workflow="photoshoot_gallery"', source)


if __name__ == "__main__":
    unittest.main()

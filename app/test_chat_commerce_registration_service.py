import unittest
import sys
import types
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

fake_psycopg = types.ModuleType("psycopg")
fake_psycopg_types = types.ModuleType("psycopg.types")
fake_psycopg_json = types.ModuleType("psycopg.types.json")
fake_psycopg_rows = types.ModuleType("psycopg.rows")
fake_psycopg.connect = lambda *args, **kwargs: None
fake_psycopg_json.Json = lambda value: value
fake_psycopg_json.Jsonb = lambda value: value
fake_psycopg_rows.dict_row = object()
sys.modules.setdefault("psycopg", fake_psycopg)
sys.modules.setdefault("psycopg.types", fake_psycopg_types)
sys.modules.setdefault("psycopg.types.json", fake_psycopg_json)
sys.modules.setdefault("psycopg.rows", fake_psycopg_rows)
setattr(sys.modules["psycopg.types.json"], "Json", lambda value: value)
setattr(sys.modules["psycopg.types.json"], "Jsonb", lambda value: value)

from app.engine.decision_engine import DecisionEngine
from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.chat_commerce_registration import (
    ChatAvailabilityState,
    ChatCommerceAssetRecord,
    ChatInventoryCandidate,
)
from app.models.commerce_destination import (
    CommerceDestination,
    DestinationRoutingOwner,
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
    MediaLinkVerificationState,
)
from app.services.chat_commerce_registration_service import (
    ChatCommerceRegistrationService,
)


def business_asset(
    asset_id=101,
    *,
    destination=CommerceDestination.CUSTOMER_CONVERSATIONS,
    approved=True,
    intelligence_ready=True,
):
    return BusinessAssetRecord(
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        asset_id=asset_id,
        creator_profile_id=7,
        approval_status="approved" if approved else "pending",
        content_intelligence_status="COMPLETE" if intelligence_ready else "PENDING",
        content_intelligence_ready=intelligence_ready,
        commerce_registration_status=CommerceRegistrationStatus.REGISTERED,
        business_lifecycle_state=BusinessAssetLifecycleState.FULFILLMENT_READY,
        commerce_destination_status=CommerceDestinationStatus.ROUTED,
        selected_commerce_destination=destination.value,
        product_ids=("product-1",),
        experience_ids=("experience-1",),
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


def fulfillment_record(
    asset_id=101,
    *,
    state=FulfillmentLifecycleState.FULFILLMENT_READY,
    verification=MediaLinkVerificationState.VERIFIED,
    media_link="https://fanvue.example/media/101",
    provider_media_id="media-101",
):
    return BusinessAssetFulfillmentRecord(
        fulfillment_id=BusinessAssetFulfillmentRecord.deterministic_id(
            asset_id,
            FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        ),
        asset_id=asset_id,
        registration_id=BusinessAssetRecord.deterministic_id(asset_id),
        routing_intent_id=uuid4(),
        route=FulfillmentRoute.CUSTOMER_CONVERSATIONS,
        route_owner=DestinationRoutingOwner.CUSTOMER_CONVERSATIONS,
        provider="fanvue",
        lifecycle_state=state,
        provider_media_id=provider_media_id,
        media_link=media_link,
        media_link_verification_state=verification,
        provenance={"source_workflow": "generation_library"},
    )


class MemoryChatRepository:
    def __init__(self):
        self.records = {}
        self.history = []

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        self.history.append(record)
        return record

    def append_history(self, record, event_type, metadata=None):
        self.history.append(record)

    def list_chat_ready(self, *, creator_profile_id=None, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if record.availability_state == ChatAvailabilityState.CHAT_READY
            and record.chat_ready
            and record.active
            and not record.temporarily_unavailable
            and not record.retired
            and (
                creator_profile_id is None
                or record.creator_profile_id == int(creator_profile_id)
            )
        )[:limit]

    def list_by_state(self, state, *, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if record.availability_state == state
        )[:limit]

    def list_by_product(self, product_id, *, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if str(product_id) in record.product_ids
        )[:limit]

    def list_by_experience(self, experience_id, *, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if str(experience_id) in record.experience_ids
        )[:limit]

    def list_recommendation_eligible(self, *, creator_profile_id=None, limit=100):
        return tuple(
            record
            for record in self.list_chat_ready(
                creator_profile_id=creator_profile_id,
                limit=limit,
            )
            if record.recommendation_eligible
        )

    def list_delivery_eligible(self, *, creator_profile_id=None, limit=100):
        return tuple(
            record
            for record in self.list_chat_ready(
                creator_profile_id=creator_profile_id,
                limit=limit,
            )
            if record.delivery_eligible
        )


class MemoryRegistrationRepository:
    def __init__(self, records=()):
        self.records = {int(record.asset_id): record for record in records}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record


class MemoryFulfillmentRepository:
    def __init__(self, records=()):
        self.records = {
            (int(record.asset_id), record.route.value): record for record in records
        }

    def get_by_asset_and_route(self, asset_id, route):
        route_value = route.value if hasattr(route, "value") else str(route)
        return self.records.get((int(asset_id), route_value))

    def list_by_state(self, state, *, limit=100):
        return tuple(
            record
            for record in self.records.values()
            if record.lifecycle_state == state
        )[:limit]


class MemoryAssetRepository:
    def __init__(self, assets=()):
        self.assets = {int(asset.id): asset for asset in assets}

    def get_by_id(self, asset_id):
        return self.assets.get(int(asset_id))


class FakeUsageService:
    def __init__(self, seen=()):
        self.seen = set(seen)

    def has_seen_content(self, fanvue_account_id, fanvue_user_id, content_item_id):
        return (int(fanvue_account_id), fanvue_user_id, int(content_item_id)) in self.seen


class FakeOwnershipService:
    def __init__(self, owned=()):
        self.owned = set(owned)

    def user_already_owns_content(self, fanvue_account_id, fanvue_user_id, content_tag):
        return (int(fanvue_account_id), fanvue_user_id, str(content_tag)) in self.owned


class ChatCommerceRegistrationServiceTests(unittest.TestCase):
    def make_service(
        self,
        *,
        asset_id=101,
        destination=CommerceDestination.CUSTOMER_CONVERSATIONS,
        approved=True,
        intelligence_ready=True,
        fulfillment=None,
        asset_status="approved",
        asset_active=True,
        seen=(),
        owned=(),
    ):
        self.chat_repo = MemoryChatRepository()
        self.registration_repo = MemoryRegistrationRepository(
            (
                business_asset(
                    asset_id,
                    destination=destination,
                    approved=approved,
                    intelligence_ready=intelligence_ready,
                ),
            )
        )
        self.fulfillment_repo = MemoryFulfillmentRepository(
            (fulfillment or fulfillment_record(asset_id),)
        )
        self.asset_repo = MemoryAssetRepository(
            (
                SimpleNamespace(
                    id=asset_id,
                    status=asset_status,
                    is_active=asset_active,
                    creator_profile_id=7,
                ),
            )
        )
        return ChatCommerceRegistrationService(
            chat_repository=self.chat_repo,
            registration_repository=self.registration_repo,
            fulfillment_repository=self.fulfillment_repo,
            asset_repository=self.asset_repo,
            content_usage_service=FakeUsageService(seen),
            content_ownership_service=FakeOwnershipService(owned),
        )

    def test_customer_conversations_fulfillment_ready_registers_chat_ready(self):
        service = self.make_service()

        result = service.register_fulfilled_asset(101)

        self.assertTrue(result.success)
        self.assertEqual(result.availability_state, ChatAvailabilityState.CHAT_READY)
        self.assertEqual(result.product_ids, ("product-1",))
        self.assertEqual(result.experience_ids, ("experience-1",))
        self.assertEqual(
            self.registration_repo.get_by_asset_id(101).business_lifecycle_state,
            BusinessAssetLifecycleState.CHAT_READY,
        )

    def test_both_destination_registers_chat_ready(self):
        service = self.make_service(destination=CommerceDestination.BOTH)

        result = service.register_fulfilled_asset(101)

        self.assertTrue(result.success)
        self.assertEqual(result.record.commerce_destination, CommerceDestination.BOTH.value)

    def test_non_chat_destinations_are_blocked(self):
        for destination in (
            CommerceDestination.TELEGRAM_WALL,
            CommerceDestination.ARCHIVE_ONLY,
        ):
            with self.subTest(destination=destination):
                service = self.make_service(destination=destination)

                result = service.register_fulfilled_asset(101)

                self.assertFalse(result.success)
                self.assertEqual(result.availability_state, ChatAvailabilityState.BLOCKED)
                self.assertIn("invalid_destination", result.block_reasons)

    def test_verified_media_link_is_required(self):
        service = self.make_service(
            fulfillment=fulfillment_record(
                verification=MediaLinkVerificationState.SUBMITTED,
                media_link="https://fanvue.example/media/101",
            )
        )

        result = service.register_fulfilled_asset(101)

        self.assertFalse(result.success)
        self.assertIn("media_link_not_verified", result.block_reasons)

    def test_content_intelligence_and_approval_are_required(self):
        service = self.make_service(intelligence_ready=False, approved=False)

        result = service.register_fulfilled_asset(101)

        self.assertFalse(result.success)
        self.assertIn("content_intelligence_not_ready", result.block_reasons)
        self.assertIn("asset_not_approved", result.block_reasons)

    def test_asset_must_be_active_and_approved(self):
        service = self.make_service(asset_status="draft", asset_active=False)

        result = service.register_fulfilled_asset(101)

        self.assertFalse(result.success)
        self.assertIn("asset_not_approved", result.block_reasons)
        self.assertIn("asset_inactive", result.block_reasons)

    def test_registration_is_idempotent_by_asset_id(self):
        service = self.make_service()

        first = service.register_fulfilled_asset(101)
        second = service.register_fulfilled_asset(101)

        self.assertEqual(first.chat_registration_id, second.chat_registration_id)
        self.assertEqual(len(self.chat_repo.records), 1)
        self.assertEqual(len(self.chat_repo.history), 1)

    def test_inventory_excludes_unavailable_and_retired_assets(self):
        service = self.make_service()
        service.register_fulfilled_asset(101)

        self.assertEqual(len(service.list_chat_ready_assets()), 1)
        service.temporarily_disable(101, reason="operator_hold")
        self.assertEqual(service.list_chat_ready_assets(), ())
        service.re_enable(101)
        self.assertEqual(len(service.list_chat_ready_assets()), 1)
        service.retire_asset(101, reason="expired")
        self.assertEqual(service.list_chat_ready_assets(), ())
        self.assertEqual(len(service.list_retired_assets()), 1)
        self.assertGreaterEqual(len(self.chat_repo.history), 4)

    def test_relationship_and_candidate_queries_use_canonical_asset(self):
        service = self.make_service()
        service.register_fulfilled_asset(101)

        self.assertEqual(service.list_by_product("product-1")[0].asset_id, 101)
        self.assertEqual(service.list_by_experience("experience-1")[0].asset_id, 101)
        candidate = service.get_recommendation_candidates()[0]
        self.assertEqual(candidate.asset_id, 101)
        self.assertEqual(candidate.to_legacy_payload("ava", "vip")["source"], "chat_commerce_inventory")

    def test_customer_usage_and_ownership_block_recommendation(self):
        service = self.make_service(
            seen=((2, "fan-1", 101),),
            owned=((2, "fan-1", "chat_asset_101"),),
        )
        service.register_fulfilled_asset(101)

        eligibility = service.eligibility_for_asset(
            101,
            customer_context={"fanvue_account_id": 2, "fanvue_user_id": "fan-1"},
        )

        self.assertFalse(eligibility.recommendation_eligible)
        self.assertIn("customer_already_seen_asset", eligibility.block_reasons)
        self.assertIn("customer_already_owns_asset", eligibility.block_reasons)

    def test_backfill_registers_fulfillment_ready_records(self):
        service = self.make_service()

        results = service.backfill_from_fulfillment_ready()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].chat_ready)

    def test_decision_engine_prefers_chat_inventory_then_preserves_fallback(self):
        class Logger:
            def info(self, message):
                pass

        class Settings:
            DEFAULT_PERSONA = "ava"

        class ChatInventory:
            def __init__(self, candidates):
                self.candidates = candidates

            def get_recommendation_candidates(self, **kwargs):
                return self.candidates

            def eligibility_for_asset(self, asset_id, **kwargs):
                return SimpleNamespace(recommendation_eligible=True)

        class ProductRecommendations:
            last_offer_candidate_contract = None

            def __init__(self):
                self.called = False

            def get_content(self, offer_type, persona, working_memory):
                self.called = True
                return {"source": "product_recommendation_service"}

        engine = object.__new__(DecisionEngine)
        engine.logger = Logger()
        engine.settings = Settings()
        engine.cms_contract_service = SimpleNamespace(
            build_customer_progress=lambda *args, **kwargs: {"customer": "progress"}
        )
        engine.product_recommendation_service = ProductRecommendations()
        candidate = ChatInventoryCandidate(
            asset_id=101,
            chat_registration_id=ChatCommerceAssetRecord.deterministic_id(101),
            creator_profile_id=7,
            media_link="https://fanvue.example/media/101",
            provider_media_id="media-101",
            product_ids=("product-1",),
        )
        engine.chat_commerce_inventory_service = ChatInventory((candidate,))

        payload = engine._select_cms_content("vip_offer", {"creator_profile_id": 7})

        self.assertEqual(payload["source"], "chat_commerce_inventory")
        self.assertFalse(engine.product_recommendation_service.called)

        engine.chat_commerce_inventory_service = ChatInventory(())
        fallback = engine._select_cms_content("vip_offer", {"creator_profile_id": 7})

        self.assertEqual(fallback["source"], "product_recommendation_service")
        self.assertTrue(engine.product_recommendation_service.called)


if __name__ == "__main__":
    unittest.main()

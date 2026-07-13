import unittest
from types import SimpleNamespace

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
    provenance_context,
)
from app.models.commerce_registration import CommerceRegistrationRequest
from app.services.commerce_registration_service import CommerceRegistrationService


class MemoryCommerceRegistrationRepository:
    def __init__(self):
        self.records = {}

    def get_by_asset_id(self, asset_id):
        return self.records.get(int(asset_id))

    def upsert_record(self, record):
        self.records[int(record.asset_id)] = record
        return record

    def list_registered(self, *, limit=500):
        return tuple(
            record
            for record in self.records.values()
            if getattr(
                record.commerce_registration_status,
                "value",
                record.commerce_registration_status,
            )
            == "REGISTERED"
        )[:limit]

    def list_awaiting_destination(self, *, limit=500):
        return tuple(
            record
            for record in self.records.values()
            if getattr(
                record.commerce_destination_status,
                "value",
                record.commerce_destination_status,
            )
            == "AWAITING_DESTINATION"
        )[:limit]

    def list_blocked_by_incomplete_intelligence(self, *, limit=500):
        return tuple(
            record
            for record in self.records.values()
            if not record.content_intelligence_ready
        )[:limit]


class FakeAssetRepository:
    def __init__(self, assets):
        self.assets = {int(asset.id): asset for asset in assets}

    def get_by_id(self, asset_id):
        return self.assets.get(int(asset_id))

    def search_assets(self, **kwargs):
        return tuple(
            asset
            for asset in self.assets.values()
            if getattr(asset, "status", None) == "approved"
        )


class FakeContentIntelligenceRepository:
    def __init__(self, profiles):
        self.profiles = profiles

    def get_by_asset_id(self, asset_id):
        return self.profiles.get(int(asset_id))


class FakeProductAssetRepository:
    def __init__(self):
        self.product_ids = {}

    def list_product_ids_for_asset(self, asset_id):
        return tuple(self.product_ids.get(int(asset_id), ()))


class FakeProductRepository:
    def __init__(self, products):
        self.products = {str(product.id): product for product in products}
        self.legacy = {}

    def get_by_id(self, product_id):
        return self.products.get(str(product_id))

    def get_by_legacy_content_item_id(self, asset_id):
        return self.legacy.get(int(asset_id))


class FakeExperienceService:
    def __init__(self, relationships=()):
        self.relationships = tuple(relationships)

    def list_asset_relationships(self, asset_id):
        return tuple(
            relationship
            for relationship in self.relationships
            if int(relationship.asset_id) == int(asset_id)
        )


class FakePublishingService:
    def project_legacy_asset_record(self, asset):
        return {
            "provider_status": getattr(asset, "fanvue_upload_status", None),
            "provider_media_id": getattr(asset, "fanvue_media_full_uuid", None),
        }

    def get_provider_status_display(self, record, **kwargs):
        if record and record.get("provider_media_id"):
            return "Uploaded to Provider", record["provider_media_id"]
        return "Not Uploaded to Provider", "Local asset only"


def asset(asset_id=101, *, status="approved"):
    return SimpleNamespace(
        id=asset_id,
        status=status,
        creator_profile_id=7,
        fanvue_upload_status=None,
        fanvue_media_full_uuid=None,
        media_metadata={
            "creator_approval": {
                "source_workflow": "test",
                "source_item_id": str(asset_id),
                "idempotency_key": f"test:{asset_id}",
            },
            ASSET_PROVENANCE_METADATA_KEY: provenance_context(
                AssetProvenanceClassification.CREATOR_APPROVAL,
                source="test",
                source_workflow="test",
            ),
        },
    )


def profile(*, ready=True):
    return SimpleNamespace(
        profile_id="profile-101",
        status=SimpleNamespace(value="COMPLETE" if ready else "PARTIAL"),
        ready=ready,
        missing_components=() if ready else ("embedding",),
        error_message=None,
    )


def product(product_id, *, status="ACTIVE", delivery_type="PAID"):
    return SimpleNamespace(
        id=product_id,
        status=status,
        delivery_type=delivery_type,
        metadata={},
    )


class CommerceRegistrationServiceTests(unittest.TestCase):
    def make_service(self, *, assets=None, profiles=None, products=(), relationships=()):
        self.registration_repository = MemoryCommerceRegistrationRepository()
        self.product_asset_repository = FakeProductAssetRepository()
        self.product_repository = FakeProductRepository(products)
        return CommerceRegistrationService(
            registration_repository=self.registration_repository,
            asset_repository=FakeAssetRepository(assets or (asset(),)),
            content_intelligence_repository=FakeContentIntelligenceRepository(
                profiles or {101: profile()}
            ),
            product_asset_repository=self.product_asset_repository,
            product_repository=self.product_repository,
            experience_service=FakeExperienceService(relationships),
            publishing_service=FakePublishingService(),
        )

    def test_approved_ready_asset_registers_without_product(self):
        service = self.make_service()

        result = service.register_asset(101)

        self.assertTrue(result.success)
        self.assertEqual(result.record.asset_id, 101)
        self.assertEqual(result.record.commerce_registration_status.value, "REGISTERED")
        self.assertEqual(result.record.business_lifecycle_state.value, "AWAITING_DESTINATION")
        self.assertEqual(result.record.product_ids, ())
        self.assertTrue(result.commerce_readiness.ready_for_commerce_destination)

    def test_registration_is_idempotent(self):
        service = self.make_service()

        first = service.register_asset(101)
        second = service.register_asset(101)

        self.assertEqual(first.record.registration_id, second.record.registration_id)
        self.assertEqual(len(self.registration_repository.records), 1)

    def test_unapproved_asset_does_not_register(self):
        service = self.make_service(assets=(asset(status="draft"),))

        result = service.register_asset(101)

        self.assertFalse(result.success)
        self.assertEqual(result.errors, ("asset_not_approved",))
        self.assertEqual(self.registration_repository.records, {})

    def test_incomplete_intelligence_blocks_registration(self):
        service = self.make_service(profiles={101: profile(ready=False)})

        result = service.register_asset(101)

        self.assertFalse(result.success)
        self.assertEqual(result.record.commerce_registration_status.value, "BLOCKED")
        self.assertEqual(result.record.business_lifecycle_state.value, "INTELLIGENCE_PENDING")
        self.assertEqual(result.record.missing_requirements, ("embedding",))
        self.assertFalse(result.commerce_readiness.ready_for_commerce_destination)

    def test_product_draft_and_delivery_are_projected_not_owned(self):
        draft_product = product("11111111-1111-1111-1111-111111111111", status="DRAFT", delivery_type="FREE")
        service = self.make_service(products=(draft_product,))
        self.product_asset_repository.product_ids[101] = (draft_product.id,)

        result = service.register_asset(101)

        self.assertEqual(result.record.product_ids, (draft_product.id,))
        self.assertEqual(result.record.product_draft_ids, (draft_product.id,))
        self.assertEqual(result.record.delivery_type, "FREE")
        self.assertEqual(result.record.delivery_type_source, f"product:{draft_product.id}")
        self.assertFalse(result.record.delivery_type_requires_review)
        self.assertFalse(
            result.record.relationship_provenance["products"]["owns_product_membership"]
        )

    def test_experience_relationships_preserve_compatibility_provenance(self):
        relationship = SimpleNamespace(
            experience_id="experience-1",
            asset_id=101,
            source="products.product_assets",
            compatibility=True,
        )
        service = self.make_service(relationships=(relationship,))

        result = service.register_asset(101)

        self.assertEqual(result.record.experience_ids, ("experience-1",))
        provenance = result.record.relationship_provenance["experiences"]["relationships"][0]
        self.assertTrue(provenance["compatibility"])
        self.assertEqual(provenance["source"], "products.product_assets")

    def test_delivery_recommendation_is_reviewable_when_no_product_owns_it(self):
        service = self.make_service()
        request = CommerceRegistrationRequest(
            asset_id=101,
            delivery_type_recommendation="PAID",
            commerce_intelligence_refs={"delivery": "recommended"},
        )

        result = service.register_asset(101, request=request)

        self.assertEqual(result.record.delivery_type, "PAID")
        self.assertEqual(
            result.record.delivery_type_source,
            "commerce_intelligence_recommendation",
        )
        self.assertTrue(result.record.delivery_type_requires_review)

    def test_publishing_readiness_is_projected_without_execution(self):
        uploaded_asset = asset()
        uploaded_asset.fanvue_media_full_uuid = "media-1"
        service = self.make_service(assets=(uploaded_asset,))

        result = service.register_asset(101)

        self.assertEqual(result.record.publishing_readiness["execution"], "not_run")
        self.assertEqual(result.record.publishing_readiness["detail"], "media-1")

    def test_refresh_updates_relationship_projections(self):
        service = self.make_service()
        service.register_asset(101)
        self.product_asset_repository.product_ids[101] = (
            "22222222-2222-2222-2222-222222222222",
        )

        refreshed = service.refresh_registration_projections(101)

        self.assertEqual(
            refreshed.record.product_ids,
            ("22222222-2222-2222-2222-222222222222",),
        )

    def test_backfill_registers_existing_approved_assets(self):
        service = self.make_service(assets=(asset(101), asset(102)), profiles={101: profile(), 102: profile()})

        results = service.backfill_approved_assets(limit=10)

        self.assertEqual(len(results), 2)
        self.assertTrue(
            all(
                result.record.commerce_registration_status.value == "REGISTERED"
                for result in results
            )
        )


if __name__ == "__main__":
    unittest.main()

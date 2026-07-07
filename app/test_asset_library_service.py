import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from app.models.asset import Asset
from app.models.experience import ExperienceAssetRelationship
from app.models.product import ProductDeliveryType
from app.models.asset_library import (
    AssetLibraryDetails,
    AssetLibraryFilter,
    AssetLibraryResult,
)
from app.services.asset_library_service import AssetLibraryService
from app.services.runtime_media_resolver import RuntimeMediaResolver


def make_asset(**overrides) -> Asset:
    values = {
        "id": 10,
        "file_path": "missing.jpg",
        "file_name": "asset.jpg",
        "classification": "VIP",
        "confidence": 0.91,
        "status": "approved",
        "is_active": True,
        "is_test": False,
        "ready_for_rotation": True,
        "upload_intent": "ppv_image",
        "content_tier": "VIP",
        "distribution_type": "both",
        "blurred_preview_path": None,
        "suggested_tags": ("tag-one",),
        "detected_themes": ("theme-one",),
        "is_explicit": False,
        "fanvue_media_preview_uuid": None,
        "fanvue_media_full_uuid": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "fanvue_upload_status": None,
        "fanvue_upload_error": None,
        "summary": "Asset summary",
        "risk_flags": ("risk",),
        "reasoning": "Reasoning",
        "analysis_provenance": {"source": "test"},
        "media_metadata": {},
        "creator_profile_id": 7,
        "nudity_labels": ("label",),
        "nudity_level": "partial",
        "sexual_intensity": "medium",
        "gpt_vision_result": {"ok": True},
        "nudenet_result": [{"class": "label"}],
        "classification_result": {"final_classification": "VIP"},
    }
    values.update(overrides)
    return Asset(**values)


class FakeAssetRepository:
    def __init__(self, assets):
        self.assets = list(assets)
        self.search_kwargs = None
        self.archive_called = False

    def search_assets(self, **kwargs):
        self.search_kwargs = kwargs
        return self.assets

    def get_by_id(self, asset_id):
        for asset in self.assets:
            if asset.id == asset_id:
                return asset
        return None

    def list_by_ids(self, asset_ids):
        requested = tuple(asset_ids)
        return [
            asset
            for asset_id in requested
            for asset in self.assets
            if asset.id == asset_id
        ]

    def archive_assets(self, *args, **kwargs):
        self.archive_called = True
        raise AssertionError("AssetLibraryService must not mutate assets")


class FakeMediaProcessingService:
    def __init__(self, preview_path=None):
        self.preview_path = preview_path
        self.resolve_calls = []
        self.generate_called = False
        self.regenerate_calls = []

    def resolve_derivative(self, asset, derivative_type):
        self.resolve_calls.append((asset.id, derivative_type))
        return self.preview_path

    def normalize_derivative_metadata(self, metadata, *, derivative_type):
        return {
            "path": metadata.get("path"),
            "type": metadata.get("type") or "blur",
            "storage": metadata.get("storage") or "local_vault",
            "generated_at": metadata.get("generated_at"),
            "source": metadata.get("source") or "media_processing_service",
        }

    def generate_derivative(self, *args, **kwargs):
        self.generate_called = True
        raise AssertionError("AssetLibraryService must not generate derivatives")

    def regenerate_derivatives(self, asset, derivative_types=None, **kwargs):
        self.regenerate_calls.append((asset.id, tuple(derivative_types or ())))
        return {"blurred_preview": "regenerated.jpg"}


class FakeAssetLifecycleService:
    def __init__(self):
        self.save_review_edits_calls = []

    def save_review_edits(self, **kwargs):
        self.save_review_edits_calls.append(kwargs)


class FakeProductAssetRepository:
    def list_product_ids_for_asset(self, asset_id):
        return ("product-linked",)


class FakeProductRepository:
    def get_by_id(self, product_id):
        return SimpleNamespace(
            id=product_id,
            delivery_type=ProductDeliveryType.FREE,
        )

    def get_by_legacy_content_item_id(self, asset_id):
        return SimpleNamespace(
            id="legacy-product",
            delivery_type=ProductDeliveryType.PAID,
        )


class FakePublishingService:
    def project_legacy_asset_record(self, asset):
        return {
            "provider_status": "uploaded",
            "provider_media_id": "media-1",
            "provider_preview_media_id": "preview-1",
            "provider_full_media_id": "full-1",
            "provider_error": None,
        }

    def get_provider_status_display(
        self,
        record,
        *,
        provider_name,
        missing_detail,
        local_detail,
    ):
        return f"Uploaded to {provider_name}", record["provider_media_id"]


class FakeExperienceService:
    def __init__(self):
        self.asset_calls = []

    def list_asset_relationships(self, asset_id):
        self.asset_calls.append(asset_id)
        return (
            ExperienceAssetRelationship(
                experience_id="experience-first-class",
                asset_id=asset_id,
                source="experience_read_model",
                metadata={
                    "source_product_id": "product-linked",
                    "experience_title": "Golden Hour Set",
                    "experience_type": "PHOTOSHOOT",
                    "experience_summary": "Warm outdoor sequence.",
                    "cover_asset_id": asset_id,
                    "suggested_themes": ("sunset",),
                    "suggested_keywords": ("golden", "outdoor"),
                    "mood": "warm",
                    "story_progression": "arrival to closeup",
                    "publishing_readiness": "ready",
                },
            ),
        )

    def list_asset_experience_ids(self, asset_id):
        self.asset_calls.append(asset_id)
        return ("experience-first-class",)


class AssetLibraryServiceTests(unittest.TestCase):
    def test_search_assets_returns_asset_library_result(self):
        asset = make_asset()
        media = FakeMediaProcessingService(preview_path="preview.jpg")
        repo = FakeAssetRepository([asset])
        service = AssetLibraryService(
            asset_repository=repo,
            media_processing_service=media,
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        result = service.search_assets(
            AssetLibraryFilter(
                search="asset",
                media_type="image",
                classification="VIP",
                eligible_only=False,
                limit=25,
                tags=("future",),
                themes=("theme-one",),
                status="future-status",
                creator_profile_id=7,
                product_id="product-linked",
                experience_id="experience-first-class",
                publishing_status="uploaded",
                has_local_vault_original=True,
                has_derivative_preview=False,
                legacy_content_id=10,
            )
        )

        self.assertIsInstance(result, AssetLibraryResult)
        self.assertEqual(result.total, 1)
        self.assertEqual(result.items[0].asset_id, asset.id)
        self.assertEqual(result.items[0].preview_path, "preview.jpg")
        self.assertEqual(result.items[0].relationship.product_count, 2)
        self.assertEqual(
            result.items[0].relationship.product_delivery_types,
            ("FREE", "PAID"),
        )
        self.assertEqual(
            result.items[0].relationship.experience_summaries[0].title,
            "Golden Hour Set",
        )
        self.assertEqual(
            result.items[0].relationship.experience_summaries[0].mood,
            "warm",
        )
        self.assertEqual(
            result.items[0].relationship.experience_summaries[0].themes,
            ("sunset",),
        )
        self.assertEqual(result.items[0].publishing.status, "Uploaded to Fanvue")
        self.assertEqual(
            repo.search_kwargs,
            {
                "search": "asset",
                "media_type": "image",
                "classification": "VIP",
                "eligible_only": False,
                "limit": 25,
                "tags": ("future",),
                "themes": ("theme-one",),
                "status": "future-status",
                "created_after": None,
                "created_before": None,
                "creator_profile_id": 7,
                "product_id": "product-linked",
                "experience_id": "experience-first-class",
                "publishing_status": "uploaded",
                "has_local_vault_original": True,
                "has_derivative_preview": False,
                "legacy_content_id": 10,
            },
        )
        self.assertEqual(media.resolve_calls, [(asset.id, "blurred_preview")])

    def test_relationship_summary_reads_experiences_from_experience_service(self):
        asset = make_asset()
        experiences = FakeExperienceService()
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([asset]),
            media_processing_service=FakeMediaProcessingService(),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
            experience_service=experiences,
        )

        item = service.search_assets(AssetLibraryFilter()).items[0]

        self.assertEqual(experiences.asset_calls, [asset.id])
        self.assertEqual(item.relationship.experience_ids, ("experience-first-class",))
        self.assertEqual(item.relationship.product_ids, ("legacy-product", "product-linked"))

    def test_original_fallback_uses_runtime_media_resolver(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            original_path = Path(tmpdir) / "original.jpg"
            original_path.write_bytes(b"image")
            asset = make_asset(
                file_path=str(original_path),
                media_metadata={"local_vault_path": str(original_path)},
            )
            service = AssetLibraryService(
                asset_repository=FakeAssetRepository([asset]),
                media_processing_service=FakeMediaProcessingService(preview_path=None),
                runtime_media_resolver=RuntimeMediaResolver(),
                product_asset_repository=FakeProductAssetRepository(),
                product_repository=FakeProductRepository(),
                publishing_service=FakePublishingService(),
            )

            item = service.search_assets(AssetLibraryFilter()).items[0]

            self.assertEqual(item.original_path, str(original_path))
            self.assertEqual(item.preview_path, str(original_path))

    def test_get_asset_details_returns_summaries(self):
        asset = make_asset(
            media_metadata={
                "local_vault_path": "vault/originals/images/10.jpg",
                "derivatives": {
                    "blur": {
                        "path": "vault/blurred/10_blurred.jpg",
                        "type": "blur",
                        "storage": "local_vault",
                        "generated_at": "2026-01-01T00:00:00+00:00",
                        "source": "media_processing_service",
                    }
                },
            }
        )
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([asset]),
            media_processing_service=FakeMediaProcessingService(
                preview_path="vault/blurred/10_blurred.jpg"
            ),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        details = service.get_asset_details(asset.id)

        self.assertIsInstance(details, AssetLibraryDetails)
        self.assertEqual(details.item.asset_id, asset.id)
        self.assertEqual(details.storage.local_vault_path, "vault/originals/images/10.jpg")
        self.assertEqual(details.derivative.storage, "local_vault")
        self.assertEqual(details.relationship.product_count, 2)
        self.assertEqual(
            details.relationship.product_delivery_types,
            ("FREE", "PAID"),
        )
        self.assertEqual(details.publishing.provider_media_id, "media-1")
        self.assertEqual(details.summary, "Asset summary")
        self.assertEqual(details.analysis_provenance, {"source": "test"})

    def test_missing_asset_details_returns_none(self):
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([]),
            media_processing_service=FakeMediaProcessingService(),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        self.assertIsNone(service.get_asset_details(999))

    def test_get_asset_items_preserves_requested_order(self):
        first = make_asset(id=1, file_name="one.jpg")
        second = make_asset(id=2, file_name="two.jpg")
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([first, second]),
            media_processing_service=FakeMediaProcessingService(),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        items = service.get_asset_items((2, 1))

        self.assertEqual([item.asset_id for item in items], [2, 1])

    def test_regenerate_preview_uses_media_processing_service(self):
        asset = make_asset()
        media = FakeMediaProcessingService()
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([asset]),
            media_processing_service=media,
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        result = service.regenerate_derivative_preview(asset.id)

        self.assertTrue(result.success)
        self.assertEqual(result.data, {"blurred_preview": "regenerated.jpg"})
        self.assertEqual(media.regenerate_calls, [(asset.id, ("blurred_preview",))])

    def test_update_asset_metadata_uses_asset_lifecycle_service(self):
        asset = make_asset()
        lifecycle = FakeAssetLifecycleService()
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([asset]),
            media_processing_service=FakeMediaProcessingService(),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
            asset_lifecycle_service=lifecycle,
        )

        result = service.update_asset_metadata(
            asset.id,
            classification="PREMIUM",
            tags=("one", "two"),
            themes=("theme",),
        )

        self.assertTrue(result.success)
        self.assertEqual(
            lifecycle.save_review_edits_calls,
            [
                {
                    "asset_id": asset.id,
                    "suggested_tags": ["one", "two"],
                    "detected_themes": ["theme"],
                    "classification": "PREMIUM",
                }
            ],
        )

    def test_missing_asset_action_returns_controlled_failure(self):
        service = AssetLibraryService(
            asset_repository=FakeAssetRepository([]),
            media_processing_service=FakeMediaProcessingService(),
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        self.assertFalse(service.regenerate_derivative_preview(999).success)
        self.assertFalse(
            service.update_asset_metadata(
                999,
                classification="VIP",
                tags=(),
                themes=(),
            ).success
        )

    def test_service_does_not_mutate_assets_or_generate_derivatives(self):
        asset = make_asset()
        repo = FakeAssetRepository([asset])
        media = FakeMediaProcessingService(preview_path=None)
        service = AssetLibraryService(
            asset_repository=repo,
            media_processing_service=media,
            runtime_media_resolver=RuntimeMediaResolver(),
            product_asset_repository=FakeProductAssetRepository(),
            product_repository=FakeProductRepository(),
            publishing_service=FakePublishingService(),
        )

        service.search_assets(AssetLibraryFilter())
        service.get_asset_details(asset.id)

        self.assertFalse(repo.archive_called)
        self.assertFalse(media.generate_called)


if __name__ == "__main__":
    unittest.main()

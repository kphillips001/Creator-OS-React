import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from app.models.asset import Asset
from app.models.experience import (
    Experience,
    ExperienceType,
    ProductExperienceRelationship,
)
from app.models.product import Product, ProductStatus, ProductType
from app.services.product_catalog_service import (
    ProductCatalogCommand,
    ProductCatalogService,
    ProductCatalogValidationError,
)


def asset(asset_id: int, filename: str) -> Asset:
    return Asset(
        id=asset_id,
        file_path=filename,
        file_name=filename,
        classification="PREMIUM",
        confidence=None,
        status="approved",
        is_active=True,
        is_test=False,
        ready_for_rotation=True,
        upload_intent=None,
        content_tier=None,
        distribution_type=None,
        blurred_preview_path=None,
        suggested_tags=(),
        detected_themes=(),
        is_explicit=False,
        fanvue_media_preview_uuid=None,
        fanvue_media_full_uuid=None,
        created_at=None,
    )


class FakeProducts:
    def __init__(self, product=None):
        self.product = product
        self.media_link_product = None
        self.update_media_link_calls = []

    def get_by_id(self, product_id, creator_profile_id=None):
        if not self.product or self.product.id != product_id:
            return None
        if (
            creator_profile_id is not None
            and self.product.creator_profile_id != creator_profile_id
        ):
            return None
        return self.product

    def internal_name_exists(self, *args, **kwargs):
        return False

    def get_by_media_link(self, media_link, *, creator_profile_id=None):
        if (
            self.media_link_product
            and self.media_link_product.media_link == media_link
            and (
                creator_profile_id is None
                or self.media_link_product.creator_profile_id == creator_profile_id
            )
        ):
            return self.media_link_product
        return None

    def update_media_link(self, *, product_id, creator_profile_id, media_link):
        self.update_media_link_calls.append(
            (product_id, creator_profile_id, media_link)
        )
        if not self.product or self.product.id != product_id:
            return None
        self.product = product(
            **{
                **self.product.__dict__,
                "media_link": media_link,
            }
        )
        return self.product


class FakeAssets:
    def __init__(self, values):
        self.values = {value.id: value for value in values}
        self.list_calls = []

    def list_by_ids(self, ids, connection=None):
        requested = tuple(ids)
        self.list_calls.append(requested)
        return [
            self.values[value]
            for value in sorted(requested)
            if value in self.values
        ]


class FakeProductAssets:
    def __init__(self, links):
        self.links = tuple(links)

    def list_for_product(self, product_id):
        return list(self.links)


class FakeEntitlements:
    def count_for_product(self, product_id):
        return 0


class FakeExperienceService:
    def __init__(
        self,
        *,
        asset_order=(3, 1, 2),
        cover_asset_id=3,
        product_assets=(),
    ):
        self.asset_order = asset_order
        self.cover_asset_id = cover_asset_id
        self.product_assets = tuple(product_assets)
        self.build_calls = []
        self.product_asset_calls = []

    def list_product_experience_assets(self, product_id):
        self.product_asset_calls.append(("list", product_id))
        return list(self.product_assets)

    def list_product_relationships(self, product_id):
        self.product_asset_calls.append(("relationships", product_id))
        return (
            ProductExperienceRelationship(
                product_id=product_id,
                experience_id=f"experience:{product_id}",
                source="experience_read_model",
                metadata={
                    "suggested_themes": ("date night",),
                    "suggested_keywords": ("heels", "story"),
                    "mood": "playful",
                    "story_progression": "intro to reveal",
                    "technical_continuity": "same lighting",
                },
            ),
        )

    def count_product_experience_assets(self, product_id):
        self.product_asset_calls.append(("count", product_id))
        return len(self.product_assets)

    def replace_product_experience_assets(
        self,
        product_id,
        asset_ids,
        *,
        connection=None,
    ):
        self.product_asset_calls.append(
            ("replace", product_id, tuple(asset_ids), connection)
        )
        return list(self.product_assets)

    def delete_product_experience_assets(self, product_id, *, connection=None):
        self.product_asset_calls.append(("delete", product_id, connection))
        return len(self.product_assets)

    def build_product_experience(self, product, product_assets):
        links = tuple(product_assets)
        self.build_calls.append((product, links))
        asset_ids = tuple(link.asset_id for link in links)
        return Experience(
            experience_id=f"product:{product.id}",
            experience_type=ExperienceType.PHOTOSHOOT,
            title=product.display_name,
            description=product.description,
            cover_asset_id=self.cover_asset_id,
            asset_ids=asset_ids,
            asset_order=self.asset_order,
            metadata={
                "source": "fake_experience_service",
                "experience_intelligence": {"source": "test"},
            },
        )

    def get_ordered_asset_ids(self, experience):
        if not experience:
            return ()
        return experience.ordered_asset_ids

    def get_cover_asset_id(self, experience):
        if not experience:
            return None
        return experience.cover_asset_id

    def order_assets_for_experience(self, experience, assets):
        ordered_asset_ids = self.get_ordered_asset_ids(experience)
        if not ordered_asset_ids:
            return tuple(assets)
        assets_by_id = {item.id: item for item in assets}
        return tuple(
            assets_by_id[asset_id]
            for asset_id in ordered_asset_ids
            if asset_id in assets_by_id
        )

    def cover_asset_for_experience(self, experience, assets):
        cover_asset_id = self.get_cover_asset_id(experience)
        for item in assets:
            if item.id == cover_asset_id:
                return item
        ordered_assets = self.order_assets_for_experience(experience, assets)
        return ordered_assets[0] if ordered_assets else None


class FakeMediaProcessingService:
    def __init__(self, thumbnail_path="vault/blurred/cover.jpg"):
        self.thumbnail_path = thumbnail_path
        self.calls = []

    def resolve_derivative(self, media, derivative_type):
        self.calls.append((media, derivative_type))
        return self.thumbnail_path


def product(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "creator_profile_id": 2,
        "legacy_content_item_id": 1,
        "internal_name": "photo-set",
        "display_name": "Photo Set",
        "description": "Catalog read model",
        "product_type": ProductType.PHOTO_SET,
        "status": ProductStatus.DRAFT,
        "price_cents": None,
        "base_price_cents": None,
        "min_price_cents": None,
        "max_price_cents": None,
        "currency": "USD",
        "media_link": None,
        "tags": (),
        "themes": (),
        "metadata": {},
        "activation_source": None,
        "activation_reason": None,
        "activated_at": None,
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return Product(**values)


class ProductCatalogValidationTests(unittest.TestCase):
    def service(self, assets):
        return ProductCatalogService(
            product_repository=FakeProducts(),
            asset_repository=FakeAssets(assets),
        )

    def command(self, product_type, asset_ids):
        return ProductCatalogCommand(
            creator_profile_id=2,
            internal_name="  Summer-Date ",
            display_name=" Summer Date ",
            description=" ",
            product_type=product_type,
            price_cents=1999,
            currency="usd",
            media_link="https://example.test/product",
            tags=("Heels", " heels ", "Dress"),
            themes=("GFE", "gfe", "Date Night"),
            asset_ids=asset_ids,
        )

    def test_normalizes_catalog_metadata(self):
        service = self.service([asset(1, "one.jpg")])
        command, _ = service.validate_command(
            self.command(ProductType.SINGLE_IMAGE, (1,)),
            activation=True,
        )
        self.assertEqual(command.internal_name, "Summer-Date")
        self.assertEqual(command.currency, "USD")
        self.assertEqual(command.tags, ("heels", "dress"))
        self.assertEqual(command.themes, ("GFE", "Date Night"))

    def test_single_image_rejects_multiple_assets(self):
        service = self.service([asset(1, "one.jpg"), asset(2, "two.jpg")])
        with self.assertRaises(ProductCatalogValidationError):
            service.validate_command(
                self.command(ProductType.SINGLE_IMAGE, (1, 2)),
                activation=True,
            )

    def test_draft_allows_incomplete_commerce_fields(self):
        service = self.service([])
        command = self.command(ProductType.STORY, ())
        command = ProductCatalogCommand(
            **{
                **command.__dict__,
                "price_cents": None,
                "media_link": None,
            }
        )
        normalized, assets = service.validate_command(command, activation=False)
        self.assertIsNone(normalized.price_cents)
        self.assertEqual(assets, [])

    def test_activation_requires_price_and_assets(self):
        service = self.service([])
        command = self.command(ProductType.STORY, ())
        command = ProductCatalogCommand(
            **{
                **command.__dict__,
                "price_cents": None,
                "media_link": None,
            }
        )
        with self.assertRaises(ProductCatalogValidationError) as caught:
            service.validate_command(command, activation=True)
        self.assertGreaterEqual(len(caught.exception.errors), 2)
        self.assertNotIn(
            "Active products require one media link.",
            caught.exception.errors,
        )

    def test_complete_publishing_media_link_saves_and_activates_product(self):
        product_record = product()
        products = FakeProducts(product_record)
        service = ProductCatalogService(product_repository=products)
        activated = product(
            **{
                **product_record.__dict__,
                "media_link": "https://fanvue.example/media",
                "status": ProductStatus.ACTIVE,
            }
        )
        transition_calls = []
        service.transition_status = lambda product_id, creator_profile_id, target: (
            transition_calls.append((product_id, creator_profile_id, target))
            or activated
        )

        result = service.complete_publishing_media_link(
            product_id=product_record.id,
            creator_profile_id=product_record.creator_profile_id,
            media_link="https://fanvue.example/media",
        )

        self.assertEqual(result.status, ProductStatus.ACTIVE)
        self.assertEqual(
            products.update_media_link_calls,
            [
                (
                    product_record.id,
                    product_record.creator_profile_id,
                    "https://fanvue.example/media",
                )
            ],
        )
        self.assertEqual(
            transition_calls,
            [
                (
                    product_record.id,
                    product_record.creator_profile_id,
                    ProductStatus.ACTIVE,
                )
            ],
        )

    def test_media_link_ownership_rejects_duplicate_product(self):
        product_record = product()
        duplicate = product(media_link="https://fanvue.example/media")
        products = FakeProducts(product_record)
        products.media_link_product = duplicate
        service = ProductCatalogService(product_repository=products)

        with self.assertRaises(ProductCatalogValidationError):
            service.validate_media_link_ownership(
                product_id=product_record.id,
                creator_profile_id=product_record.creator_profile_id,
                media_link="https://fanvue.example/media",
            )

    def test_load_editor_uses_experience_for_asset_order_and_cover(self):
        product_record = product()
        assets = [
            asset(1, "one.jpg"),
            asset(2, "two.jpg"),
            asset(3, "three.jpg"),
        ]
        links = [
            SimpleNamespace(asset_id=1, position=0),
            SimpleNamespace(asset_id=2, position=1),
            SimpleNamespace(asset_id=3, position=2),
        ]
        experience_service = FakeExperienceService(
            asset_order=(3, 1, 2),
            cover_asset_id=3,
            product_assets=links,
        )
        asset_repository = FakeAssets(assets)
        service = ProductCatalogService(
            product_repository=FakeProducts(product_record),
            product_asset_repository=FakeProductAssets(links),
            asset_repository=asset_repository,
            entitlement_repository=FakeEntitlements(),
            experience_service=experience_service,
        )

        editor = service.load_editor(product_record.id, 2)

        self.assertEqual([item.id for item in editor.assets], [3, 1, 2])
        self.assertIsNotNone(editor.experience)
        self.assertEqual(editor.experience.cover_asset_id, 3)
        self.assertEqual(asset_repository.list_calls, [(3, 1, 2)])
        self.assertEqual(len(experience_service.build_calls), 1)
        self.assertEqual(
            experience_service.product_asset_calls,
            [("list", product_record.id)],
        )
        self.assertEqual(
            service.cover_asset_for_experience(
                editor.experience,
                editor.assets,
            ).id,
            3,
        )

    def test_display_model_encapsulates_order_cover_thumbnail_and_publishing(self):
        product_record = product()
        assets = [
            asset(1, "one.jpg"),
            asset(2, "two.jpg"),
            asset(3, "three.jpg"),
        ]
        links = [
            SimpleNamespace(asset_id=1, position=0),
            SimpleNamespace(asset_id=2, position=1),
            SimpleNamespace(asset_id=3, position=2),
        ]
        experience_service = FakeExperienceService(
            asset_order=(3, 1, 2),
            cover_asset_id=2,
            product_assets=links,
        )
        media_processing = FakeMediaProcessingService(
            thumbnail_path="vault/blurred/two_blurred.jpg",
        )
        service = ProductCatalogService(
            product_repository=FakeProducts(product_record),
            product_asset_repository=FakeProductAssets(links),
            asset_repository=FakeAssets(assets),
            entitlement_repository=FakeEntitlements(),
            experience_service=experience_service,
            media_processing_service=media_processing,
        )
        experience = service.project_product_experience(product_record, links)

        display = service.build_display_model(
            product_record,
            links,
            assets,
            experience,
        )

        self.assertEqual([item.id for item in display.ordered_assets], [3, 1, 2])
        self.assertEqual(display.cover_asset.id, 2)
        self.assertEqual(display.preview_asset.id, 2)
        self.assertEqual(display.thumbnail_path, "vault/blurred/two_blurred.jpg")
        self.assertEqual(display.classification_label, "PREMIUM")
        self.assertEqual(display.publishing.status, "Not uploaded to Fanvue")
        self.assertEqual(len(display.asset_displays), 3)
        self.assertIsNotNone(display.experience_presentation)
        self.assertEqual(
            display.experience_presentation.title,
            "Photo Set",
        )
        self.assertEqual(
            display.experience_presentation.themes,
            ("date night",),
        )
        self.assertEqual(
            display.experience_presentation.keywords,
            ("heels", "story"),
        )
        self.assertEqual(
            display.experience_presentation.mood,
            "playful",
        )
        self.assertEqual(
            display.experience_presentation.story_progression,
            "intro to reveal",
        )
        self.assertEqual(
            display.experience_presentation.relationship_source,
            "experience_read_model",
        )
        self.assertEqual(media_processing.calls[0][1], "blurred_preview")

        loaded_display = service.load_display_model(product_record)

        self.assertEqual(
            [item.id for item in loaded_display.ordered_assets],
            [3, 1, 2],
        )
        self.assertEqual(loaded_display.cover_asset.id, 2)

    def test_product_catalog_page_uses_service_asset_helpers(self):
        source = Path("app/dashboard/pages/product_catalog.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("service.build_asset_library_service()", source)
        self.assertIn("service.load_asset_by_id", source)
        self.assertIn("service.load_assets_by_ids", source)
        self.assertNotIn("service.assets.list_by_ids", source)


if __name__ == "__main__":
    unittest.main()

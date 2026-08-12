import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from app.models.asset import Asset
from app.models.experience import ExperienceType
from app.models.product import (
    Product,
    ProductDeliveryType,
    ProductStatus,
    ProductType,
    product_metadata_with_delivery_type,
)
from app.models.product_draft_source import ProductDraftSource
from app.services.ai_product_drafting_service import AIProductDraftingService


def make_asset(
    asset_id: int = 10,
    *,
    file_name: str | None = None,
    file_path: str | None = None,
    media_metadata: dict | None = None,
) -> Asset:
    file_name = file_name or "20260621_120000_000000_lace_set.jpg"
    return Asset(
        id=asset_id,
        file_path=file_path or f"data/uploads/{file_name}",
        file_name=file_name,
        classification="VIP",
        confidence=0.91,
        status="approved",
        is_active=True,
        is_test=False,
        ready_for_rotation=True,
        upload_intent="ppv_image",
        content_tier="VIP",
        distribution_type="both",
        blurred_preview_path=None,
        suggested_tags=("lingerie", "lace"),
        detected_themes=("GFE", "Flirty"),
        is_explicit=False,
        fanvue_media_preview_uuid=None,
        fanvue_media_full_uuid=None,
        created_at=None,
        summary="Soft lace mirror-set with a flirty girlfriend vibe.",
        risk_flags=("manual_review_optional",),
        reasoning="The image is suggestive but not explicit.",
        analysis_provenance={"vision_model": "gpt-4.1-mini"},
        media_metadata=media_metadata or {"mime_type": "image/jpeg"},
        creator_profile_id=2,
        nudity_labels=("FEMALE_BREAST_COVERED",),
        nudity_level="covered",
        sexual_intensity="medium",
    )


def make_product(asset: Asset, *, metadata=None, display_name="Old name") -> Product:
    now = datetime.now(timezone.utc)
    return Product(
        id=uuid4(),
        creator_profile_id=2,
        legacy_content_item_id=asset.id,
        internal_name=f"asset-{asset.id}",
        display_name=display_name,
        description=None,
        product_type=ProductType.CUSTOM,
        status=ProductStatus.DRAFT,
        price_cents=None,
        base_price_cents=None,
        min_price_cents=None,
        max_price_cents=None,
        currency="USD",
        media_link=None,
        tags=(),
        themes=(),
        metadata=metadata or {},
        activation_source=None,
        activation_reason=None,
        activated_at=None,
        created_at=now,
        updated_at=now,
    )


class FakeAssets:
    def __init__(self, asset):
        if isinstance(asset, (list, tuple)):
            self.assets = {item.id: item for item in asset}
        else:
            self.assets = {asset.id: asset}

    def get_by_id(self, asset_id):
        return self.assets.get(asset_id)


class FakeProducts:
    def __init__(self, existing=None):
        self.by_asset = {}
        if existing:
            self.by_asset[existing.legacy_content_item_id] = existing
        self.update_calls = []

    def create_ai_draft_product(self, **kwargs):
        asset = kwargs["asset"]
        existing = self.by_asset.get(asset.id)
        if existing:
            return existing, False
        delivery_type = kwargs.get("delivery_type")
        product = make_product(
            asset,
            metadata=product_metadata_with_delivery_type(
                kwargs["metadata"],
                delivery_type,
            ),
            display_name=kwargs["display_name"],
        )
        product = Product(
            **{
                **product.__dict__,
                "internal_name": kwargs["internal_name"],
                "description": kwargs["description"],
                "product_type": kwargs["product_type"],
                "tags": kwargs["tags"],
                "themes": kwargs["themes"],
                "delivery_type": delivery_type,
            }
        )
        self.by_asset[asset.id] = product
        return product, True

    def assign_to_creator(self, product_id, creator_profile_id):
        return next(
            product for product in self.by_asset.values() if product.id == product_id
        )

    def apply_ai_draft_fields(self, **kwargs):
        product = next(
            product
            for product in self.by_asset.values()
            if product.id == kwargs["product_id"]
        )
        updated = Product(
            **{
                **product.__dict__,
                "display_name": kwargs["display_name"],
                "description": kwargs["description"],
                "product_type": kwargs["product_type"],
                "tags": kwargs["tags"],
                "themes": kwargs["themes"],
                "metadata": product_metadata_with_delivery_type(
                    kwargs["metadata"],
                    kwargs.get("delivery_type"),
                ),
                "delivery_type": kwargs.get("delivery_type"),
            }
        )
        self.by_asset[updated.legacy_content_item_id] = updated
        self.update_calls.append(updated)
        return updated

    def activate_ai_product(self, **kwargs):
        product = next(
            product
            for product in self.by_asset.values()
            if product.id == kwargs["product_id"]
        )
        updated = Product(
            **{
                **product.__dict__,
                "status": ProductStatus.ACTIVE,
                "price_cents": kwargs["base_price_cents"],
                "base_price_cents": kwargs["base_price_cents"],
                "min_price_cents": kwargs["min_price_cents"],
                "max_price_cents": kwargs["max_price_cents"],
                "media_link": kwargs["media_link"],
                "activation_source": kwargs["activation_source"],
                "activation_reason": kwargs["activation_reason"],
                "metadata": product_metadata_with_delivery_type(
                    kwargs["metadata"],
                    kwargs.get("delivery_type"),
                ),
                "delivery_type": kwargs.get("delivery_type"),
            }
        )
        self.by_asset[updated.legacy_content_item_id] = updated
        return updated


class FakeProductAssets:
    def __init__(self):
        self.links = set()
        self.ordered_assets = []

    def attach_primary(self, product_id, asset_id):
        key = (product_id, asset_id)
        created = key not in self.links
        self.links.add(key)
        return key, created

    def replace_product_assets(self, product_id, asset_ids):
        self.ordered_assets = list(asset_ids)
        self.links = {
            (product_id, asset_id)
            for asset_id in self.ordered_assets
        }
        return [
            (product_id, asset_id, position)
            for position, asset_id in enumerate(self.ordered_assets)
        ]


class FakeExperiences:
    def __init__(self):
        self.standalone_calls = []
        self.photoshoot_calls = []
        self.links = set()
        self.ordered_assets = []

    def build_standalone_experience(self, asset, **kwargs):
        self.standalone_calls.append({"asset": asset, **kwargs})
        return SimpleNamespace(
            experience_id=f"asset:{asset.id}",
            experience_type=ExperienceType.STANDALONE,
            title=kwargs.get("title"),
            description=kwargs.get("description"),
            cover_asset_id=asset.id,
            asset_ids=(asset.id,),
            metadata=kwargs.get("metadata") or {},
        )

    def build_photoshoot_experience(self, assets, **kwargs):
        asset_tuple = tuple(assets)
        self.photoshoot_calls.append({"assets": asset_tuple, **kwargs})
        asset_ids = tuple(asset.id for asset in asset_tuple)
        return SimpleNamespace(
            experience_id=f"photoshoot:{'-'.join(str(asset_id) for asset_id in asset_ids)}",
            experience_type=ExperienceType.PHOTOSHOOT,
            title=kwargs.get("title"),
            description=kwargs.get("description"),
            cover_asset_id=kwargs.get("cover_asset_id"),
            asset_ids=asset_ids,
            asset_order=tuple(kwargs.get("asset_order") or asset_ids),
            metadata=kwargs.get("metadata") or {},
        )

    def attach_primary_product_experience_asset(self, product_id, asset_id):
        key = (product_id, asset_id)
        created = key not in self.links
        self.links.add(key)
        return key, created

    def replace_product_experience_assets(self, product_id, asset_ids):
        self.ordered_assets = list(asset_ids)
        self.links = {
            (product_id, asset_id)
            for asset_id in self.ordered_assets
        }
        return [
            (product_id, asset_id, position)
            for position, asset_id in enumerate(self.ordered_assets)
        ]


class AIProductDraftingTests(unittest.TestCase):
    def service(self, asset, products=None, links=None, experiences=None, intelligence=None):
        return AIProductDraftingService(
            asset_repository=FakeAssets(asset),
            product_repository=products or FakeProducts(),
            product_asset_repository=links or FakeProductAssets(),
            experience_service=experiences or FakeExperiences(),
            asset_intelligence_service=intelligence or SimpleNamespace(
                get_profile=lambda _asset_id: None,
            ),
        )

    def test_creates_and_auto_activates_product_from_eligible_asset(self):
        asset = make_asset()
        service = self.service(asset)

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.product.status, ProductStatus.ACTIVE)
        self.assertEqual(result.product.price_cents, result.product.base_price_cents)
        self.assertIsNotNone(result.product.min_price_cents)
        self.assertIsNotNone(result.product.max_price_cents)
        self.assertEqual(result.product.media_link, f"local://content_items/{asset.id}")
        self.assertEqual(result.product.product_type, ProductType.SINGLE_IMAGE)
        self.assertEqual(result.product.description, asset.summary)
        self.assertEqual(result.product.tags, asset.suggested_tags)
        self.assertEqual(result.product.metadata["classification"], "VIP")
        self.assertEqual(result.product.activation_source, "ai_auto_activation")

    def test_creates_product_from_commerce_recommendation_when_provided(self):
        asset = make_asset()
        service = self.service(asset)
        commerce = SimpleNamespace(
            source_type="asset",
            source_id=str(asset.id),
            product_type=ProductType.SINGLE_IMAGE,
            delivery_type=ProductDeliveryType.PAID,
            suggested_name="Commerce Lace Drop",
            suggested_description="Commerce-generated draft description.",
            suggested_tags=("commerce", "lace"),
            suggested_themes=("vip",),
            suggested_keywords=("commerce", "mirror"),
            confidence=0.96,
            price=SimpleNamespace(
                suggested_price_cents=3999,
                min_price_cents=3000,
                max_price_cents=5400,
                pricing_rule="VIP_SINGLE_IMAGE_COMMERCE",
            ),
            publishing=SimpleNamespace(
                status="ready_for_draft",
                action="generate_product_draft",
                reason="Ready.",
            ),
            metadata={
                "classification": "VIP",
                "experience_intelligence": {
                    "suggested_themes": ("vip",),
                    "suggested_keywords": ("commerce", "mirror"),
                    "mood": "soft",
                    "setting": "bedroom",
                    "intelligence_provenance": {
                        "source": "experience_intelligence_service",
                        "new_ai_analysis": False,
                    },
                },
            },
        )

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
            commerce_recommendation=commerce,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.product.display_name, "Commerce Lace Drop")
        self.assertEqual(
            result.product.description,
            "Commerce-generated draft description.",
        )
        self.assertEqual(result.product.tags, ("commerce", "lace"))
        self.assertEqual(result.product.themes, ("vip",))
        self.assertEqual(result.product.price_cents, 3999)
        self.assertEqual(result.product.delivery_type, ProductDeliveryType.PAID)
        self.assertEqual(result.product.metadata["delivery_type"], "PAID")
        commerce_metadata = result.product.metadata["commerce_intelligence"]
        self.assertEqual(commerce_metadata["source_type"], "asset")
        self.assertEqual(commerce_metadata["delivery_type"], "PAID")
        self.assertEqual(
            commerce_metadata["price"]["suggested_price_cents"],
            3999,
        )
        self.assertEqual(
            commerce_metadata["experience_intelligence"]["setting"],
            "bedroom",
        )
        self.assertFalse(
            commerce_metadata["experience_intelligence"][
                "intelligence_provenance"
            ]["new_ai_analysis"]
        )

    def test_free_commerce_recommendation_preserves_delivery_type(self):
        asset = make_asset()
        service = self.service(asset)
        commerce = SimpleNamespace(
            source_type="asset",
            source_id=str(asset.id),
            product_type=ProductType.SINGLE_IMAGE,
            delivery_type=ProductDeliveryType.FREE,
            suggested_name="Free Preview Drop",
            suggested_description="A free teaser preview.",
            suggested_tags=("preview",),
            suggested_themes=("teaser",),
            suggested_keywords=("preview", "conversation"),
            confidence=0.91,
            price=SimpleNamespace(
                suggested_price_cents=0,
                min_price_cents=0,
                max_price_cents=0,
                pricing_rule="FREE_SINGLE_IMAGE",
            ),
            publishing=SimpleNamespace(
                status="ready_for_draft",
                action="generate_product_draft",
                reason="Ready.",
            ),
            metadata={"classification": "TEASE"},
        )

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
            commerce_recommendation=commerce,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(result.product.metadata["delivery_type"], "FREE")
        self.assertEqual(
            result.product.metadata["commerce_intelligence"]["delivery_type"],
            "FREE",
        )
        self.assertEqual(result.product.price_cents, 0)

    def test_single_asset_draft_builds_experience(self):
        asset = make_asset()
        experiences = FakeExperiences()
        service = self.service(asset, experiences=experiences)

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
        )

        self.assertTrue(result.created)
        self.assertEqual(len(experiences.standalone_calls), 1)
        call = experiences.standalone_calls[0]
        self.assertIs(call["asset"], asset)
        self.assertEqual(call["title"], "Lace Set")
        self.assertEqual(call["description"], asset.summary)
        self.assertEqual(call["metadata"]["source_asset_id"], asset.id)
        self.assertEqual(result.product.metadata["experience_id"], f"asset:{asset.id}")
        self.assertEqual(
            result.product.metadata["experience_type"],
            ExperienceType.STANDALONE.value,
        )
        self.assertEqual(result.product.metadata["experience_name"], "Lace Set")
        self.assertEqual(result.product.metadata["experience_summary"], asset.summary)
        self.assertEqual(result.product.metadata["experience_cover_asset_id"], asset.id)

    def test_draft_inherits_experience_intelligence_without_regenerating_it(self):
        asset = make_asset()
        experiences = FakeExperiences()
        service = self.service(asset, experiences=experiences)
        commerce = SimpleNamespace(
            source_type="asset",
            source_id=str(asset.id),
            product_type=ProductType.SINGLE_IMAGE,
            delivery_type=ProductDeliveryType.PAID,
            suggested_name="Canonical Experience Name",
            suggested_description="Canonical Experience summary.",
            suggested_tags=("commerce",),
            suggested_themes=("experience-theme",),
            suggested_keywords=("experience-keyword",),
            confidence=0.96,
            price=SimpleNamespace(
                suggested_price_cents=3999,
                min_price_cents=3000,
                max_price_cents=5400,
                pricing_rule="VIP_SINGLE_IMAGE_COMMERCE",
            ),
            publishing=None,
            metadata={
                "classification": "VIP",
                "experience_intelligence": {
                    "suggested_themes": ("experience-theme",),
                    "suggested_keywords": ("experience-keyword",),
                    "mood": "soft",
                    "story_progression": {"activity_progression": False},
                    "technical_continuity": {"mime_types": ("image/jpeg",)},
                    "intelligence_metadata": {"asset_count": 1},
                    "intelligence_provenance": {
                        "source": "experience_intelligence_service",
                        "new_ai_analysis": False,
                    },
                },
            },
        )

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
            commerce_recommendation=commerce,
        )

        call = experiences.standalone_calls[0]
        self.assertEqual(call["title"], "Canonical Experience Name")
        self.assertEqual(call["description"], "Canonical Experience summary.")
        self.assertEqual(
            result.product.metadata["experience_name"],
            "Canonical Experience Name",
        )
        self.assertEqual(
            result.product.metadata["experience_summary"],
            "Canonical Experience summary.",
        )
        self.assertEqual(
            result.product.metadata["experience_themes"],
            ("experience-theme",),
        )
        self.assertEqual(
            result.product.metadata["experience_keywords"],
            ("experience-keyword",),
        )
        self.assertEqual(result.product.metadata["experience_mood"], "soft")
        self.assertEqual(
            result.product.metadata["experience_story_progression"],
            {"activity_progression": False},
        )
        self.assertEqual(
            result.product.metadata["experience_technical_continuity"],
            {"mime_types": ("image/jpeg",)},
        )
        self.assertFalse(
            result.product.metadata["experience_provenance"]["new_ai_analysis"]
        )
        self.assertEqual(
            result.product.metadata["commerce_intelligence"]["product_type"],
            ProductType.SINGLE_IMAGE.value,
        )

    def test_metadata_prefers_local_vault_original_media(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            legacy_path = root / "legacy.jpg"
            vault_path = root / "vault.jpg"
            legacy_path.write_bytes(b"legacy")
            vault_path.write_bytes(b"vault")
            asset = make_asset(
                file_path=str(legacy_path),
                media_metadata={
                    "mime_type": "image/jpeg",
                    "local_vault_path": str(vault_path),
                },
            )
            service = self.service(asset)

            result = service.create_or_refresh_draft_for_asset(
                asset.id,
                creator_profile_id=2,
            )

        runtime_media = result.product.metadata["analysis"][
            "runtime_original_media"
        ]
        self.assertEqual(runtime_media["path"], str(vault_path))
        self.assertEqual(
            runtime_media["source"],
            "media_metadata.local_vault_path",
        )
        self.assertTrue(runtime_media["exists"])

    def test_metadata_falls_back_to_legacy_original_media(self):
        with TemporaryDirectory() as temp_dir:
            legacy_path = Path(temp_dir) / "legacy.jpg"
            legacy_path.write_bytes(b"legacy")
            asset = make_asset(file_path=str(legacy_path))
            service = self.service(asset)

            result = service.create_or_refresh_draft_for_asset(
                asset.id,
                creator_profile_id=2,
            )

        runtime_media = result.product.metadata["analysis"][
            "runtime_original_media"
        ]
        self.assertEqual(runtime_media["path"], str(legacy_path))
        self.assertEqual(runtime_media["source"], "file_path")
        self.assertTrue(runtime_media["exists"])

    def test_pricing_decision_exposes_playground_debug_fields(self):
        asset = make_asset()

        decision = AIProductDraftingService.pricing_decision_for_asset(
            asset,
            ProductType.SINGLE_IMAGE,
        )

        self.assertEqual(decision["pricing_rule"], "VIP_SINGLE_IMAGE")
        self.assertEqual(decision["classification"], "VIP")
        self.assertEqual(decision["product_type"], "SINGLE_IMAGE")
        self.assertEqual(decision["base_price_cents"], 2999)
        self.assertEqual(decision["min_price_cents"], 2200)
        self.assertEqual(decision["max_price_cents"], 4000)
        self.assertTrue(decision["factors"])
        self.assertIn("explanation", decision)

    def test_pricing_decision_matches_activation_price_band(self):
        asset = make_asset()

        decision = AIProductDraftingService.pricing_decision_for_asset(
            asset,
            ProductType.SINGLE_IMAGE,
        )
        activation_price_band = AIProductDraftingService._price_band_for_asset(
            asset,
            ProductType.SINGLE_IMAGE,
        )

        self.assertEqual(
            {
                "base_price_cents": decision["base_price_cents"],
                "min_price_cents": decision["min_price_cents"],
                "max_price_cents": decision["max_price_cents"],
            },
            activation_price_band,
        )

    def test_product_draft_source_is_narrow_product_facing_contract(self):
        with TemporaryDirectory() as temp_dir:
            media_path = Path(temp_dir) / "source.jpg"
            media_path.write_bytes(b"media")
            asset = make_asset(
                file_path=str(media_path),
                media_metadata={"local_vault_path": str(media_path)},
            )
            service = self.service(asset)

            source = service._draft_source_for_asset(asset)

        self.assertIsInstance(source, ProductDraftSource)
        self.assertEqual(source.source_id, str(asset.id))
        self.assertEqual(source.source_type, "asset")
        self.assertEqual(source.product_type, ProductType.SINGLE_IMAGE)
        self.assertEqual(source.suggested_title, "Lace Set")
        self.assertEqual(source.suggested_description, asset.summary)
        self.assertEqual(source.tags, asset.suggested_tags)
        self.assertEqual(source.themes, asset.detected_themes)
        self.assertEqual(source.asset_ids, (asset.id,))
        self.assertEqual(source.classification, asset.classification)
        self.assertEqual(source.intensity, asset.sexual_intensity)
        source_payload = source.__dict__
        self.assertNotIn("file_path", source_payload)
        self.assertNotIn("local_vault_path", source_payload)
        self.assertNotIn("media_metadata", source_payload)
        self.assertNotIn("blurred_preview_path", source_payload)
        self.assertNotIn("fanvue_media_preview_uuid", source_payload)

    def test_product_title_prefers_canonical_asset_intelligence_over_filename(self):
        asset = make_asset(file_name="generated_image_ababc4467fdaf560323e8164.png")
        intelligence = SimpleNamespace(
            get_profile=lambda _asset_id: SimpleNamespace(title="Sunlit Kitchen Reveal"),
        )

        source = self.service(asset, intelligence=intelligence)._draft_source_for_asset(asset)

        self.assertEqual(source.suggested_title, "Sunlit Kitchen Reveal")

    def test_product_title_prefers_explicit_commerce_name_over_canonical_title(self):
        asset = make_asset()
        intelligence = SimpleNamespace(
            get_profile=lambda _asset_id: SimpleNamespace(title="Sunlit Kitchen Reveal"),
        )
        recommendation = SimpleNamespace(
            product_type=None, delivery_type=None, price_band=None,
            suggested_name="Private Collector Edition", suggested_description=None,
            suggested_tags=None, suggested_themes=None, metadata={}, confidence=None,
        )

        source = self.service(asset, intelligence=intelligence)._draft_source_for_asset(
            asset, recommendation,
        )

        self.assertEqual(source.suggested_title, "Private Collector Edition")

    def test_pricing_decision_for_source_matches_asset_pricing(self):
        asset = make_asset()
        service = self.service(asset)
        source = service._draft_source_for_asset(asset)

        source_decision = AIProductDraftingService.pricing_decision_for_source(
            source
        )
        asset_decision = AIProductDraftingService.pricing_decision_for_asset(
            asset,
            ProductType.SINGLE_IMAGE,
        )

        self.assertEqual(source_decision, asset_decision)

    def test_draft_result_wrapper_returns_service_result_shape(self):
        service = AIProductDraftingService.__new__(AIProductDraftingService)
        product = SimpleNamespace(
            id=uuid4(),
            product_type=ProductType.SINGLE_IMAGE,
            delivery_type=ProductDeliveryType.PAID,
            status=ProductStatus.DRAFT,
            price_cents=1999,
            base_price_cents=1999,
            min_price_cents=999,
            max_price_cents=4999,
        )

        def fake_create(asset_id, *, creator_profile_id):
            self.assertEqual(asset_id, 55)
            self.assertEqual(creator_profile_id, 2)
            return SimpleNamespace(
                product=product,
                created=True,
                updated=False,
                activated=True,
            )

        service.create_or_refresh_draft_for_asset = fake_create

        result = service.create_draft_result_for_asset(
            55,
            creator_profile_id=2,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["created"])
        self.assertFalse(result["updated"])
        self.assertTrue(result["activated"])
        self.assertEqual(result["product_type"], ProductType.SINGLE_IMAGE.value)
        self.assertEqual(result["delivery_type"], ProductDeliveryType.PAID.value)
        self.assertEqual(result["status"], ProductStatus.DRAFT.value)

    def test_draft_result_wrapper_handles_missing_inputs_safely(self):
        service = AIProductDraftingService.__new__(AIProductDraftingService)

        result = service.create_draft_result_for_asset(
            None,
            creator_profile_id=2,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "missing_content_or_creator_profile")

    def test_photo_set_creates_one_active_product_with_ordered_assets(self):
        assets = [
            make_asset(21, file_name="first.jpg"),
            make_asset(22, file_name="second.jpg"),
            make_asset(23, file_name="third.jpg"),
        ]
        products = FakeProducts()
        links = FakeProductAssets()
        experiences = FakeExperiences()
        service = AIProductDraftingService(
            asset_repository=FakeAssets(assets),
            product_repository=products,
            product_asset_repository=links,
            experience_service=experiences,
        )

        result = service.create_photo_set_for_assets(
            [21, 22, 23],
            creator_profile_id=2,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.product.status, ProductStatus.ACTIVE)
        self.assertEqual(result.product.product_type, ProductType.PHOTO_SET)
        self.assertEqual(result.product.delivery_type, ProductDeliveryType.PAID)
        self.assertEqual(result.product.metadata["delivery_type"], "PAID")
        self.assertEqual(result.product.base_price_cents, 4499)
        self.assertEqual(result.product.media_link, f"local://products/{result.product.id}")
        self.assertEqual(experiences.ordered_assets, [21, 22, 23])
        self.assertEqual(links.ordered_assets, [])
        self.assertEqual(
            result.product.metadata["source_asset_ids"],
            [21, 22, 23],
        )
        self.assertEqual(len(experiences.photoshoot_calls), 1)
        call = experiences.photoshoot_calls[0]
        self.assertEqual([asset.id for asset in call["assets"]], [21, 22, 23])
        self.assertEqual(call["asset_order"], [21, 22, 23])
        self.assertEqual(call["cover_asset_id"], 21)
        self.assertEqual(call["metadata"]["product_structure"], "photo_set")
        self.assertEqual(call["metadata"]["source_asset_ids"], [21, 22, 23])
        self.assertEqual(
            result.product.metadata["experience_id"],
            "photoshoot:21-22-23",
        )
        self.assertEqual(
            result.product.metadata["experience_type"],
            ExperienceType.PHOTOSHOOT.value,
        )

    def test_photo_set_uses_experience_recommendation_fields_for_experience(self):
        assets = [
            make_asset(41, file_name="first.jpg"),
            make_asset(42, file_name="second.jpg"),
        ]
        experiences = FakeExperiences()
        service = AIProductDraftingService(
            asset_repository=FakeAssets(assets),
            product_repository=FakeProducts(),
            product_asset_repository=FakeProductAssets(),
            experience_service=experiences,
        )
        commerce = SimpleNamespace(
            source_type="experience",
            source_id="41-42",
            product_type=ProductType.PHOTO_SET,
            delivery_type=ProductDeliveryType.PAID,
            suggested_name="Canonical Photo Experience",
            suggested_description="Canonical photoshoot summary.",
            suggested_tags=("set",),
            suggested_themes=("canonical-theme",),
            suggested_keywords=("canonical-keyword",),
            confidence=0.96,
            price=SimpleNamespace(
                suggested_price_cents=4999,
                min_price_cents=3500,
                max_price_cents=6500,
                pricing_rule="VIP_PHOTO_SET",
            ),
            publishing=None,
            metadata={
                "classification": "VIP",
                "experience_intelligence": {
                    "suggested_themes": ("canonical-theme",),
                    "suggested_keywords": ("canonical-keyword",),
                    "mood": "cinematic",
                    "story_progression": {"filename_sequence": True},
                    "technical_continuity": {"dimensions": ("1080x1350",)},
                    "intelligence_provenance": {
                        "source": "experience_intelligence_service",
                        "new_ai_analysis": False,
                    },
                },
            },
        )

        result = service.create_photo_set_for_assets(
            [41, 42],
            creator_profile_id=2,
            commerce_recommendation=commerce,
        )

        call = experiences.photoshoot_calls[0]
        self.assertEqual(call["title"], "Canonical Photo Experience")
        self.assertEqual(call["description"], "Canonical photoshoot summary.")
        self.assertEqual(
            result.product.display_name,
            "Canonical Photo Experience",
        )
        self.assertEqual(
            result.product.metadata["experience_name"],
            "Canonical Photo Experience",
        )
        self.assertEqual(
            result.product.metadata["experience_summary"],
            "Canonical photoshoot summary.",
        )
        self.assertEqual(
            result.product.metadata["experience_themes"],
            ("canonical-theme",),
        )
        self.assertEqual(
            result.product.metadata["experience_keywords"],
            ("canonical-keyword",),
        )
        self.assertFalse(
            result.product.metadata["experience_provenance"]["new_ai_analysis"]
        )

    def test_photo_set_preserves_commerce_delivery_type(self):
        assets = [
            make_asset(31, file_name="first.jpg"),
            make_asset(32, file_name="second.jpg"),
        ]
        service = AIProductDraftingService(
            asset_repository=FakeAssets(assets),
            product_repository=FakeProducts(),
            product_asset_repository=FakeProductAssets(),
            experience_service=FakeExperiences(),
        )
        commerce = SimpleNamespace(
            source_type="experience",
            source_id="31-32",
            product_type=ProductType.PHOTO_SET,
            delivery_type=ProductDeliveryType.FREE,
            suggested_name="Free Preview Set",
            suggested_description="A free preview set.",
            suggested_tags=("preview",),
            suggested_themes=("teaser",),
            suggested_keywords=("preview",),
            confidence=0.91,
            price=SimpleNamespace(
                suggested_price_cents=0,
                min_price_cents=0,
                max_price_cents=0,
                pricing_rule="FREE_PHOTO_SET",
            ),
            publishing=SimpleNamespace(
                status="ready_for_draft",
                action="generate_product_draft",
                reason="Ready.",
            ),
            metadata={"classification": "TEASE"},
        )

        result = service.create_photo_set_for_assets(
            [31, 32],
            creator_profile_id=2,
            commerce_recommendation=commerce,
        )

        self.assertTrue(result.created)
        self.assertTrue(result.activated)
        self.assertEqual(result.product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(result.product.metadata["delivery_type"], "FREE")
        self.assertEqual(
            result.product.metadata["commerce_intelligence"]["delivery_type"],
            "FREE",
        )

    def test_creation_is_idempotent_by_source_asset(self):
        asset = make_asset()
        products = FakeProducts()
        links = FakeProductAssets()
        service = self.service(asset, products, links)

        first = service.create_or_refresh_draft_for_asset(asset.id, creator_profile_id=2)
        second = service.create_or_refresh_draft_for_asset(asset.id, creator_profile_id=2)

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertFalse(second.product_asset_created)
        self.assertEqual(first.product.id, second.product.id)

    def test_preserves_creator_edits_on_manual_existing_product(self):
        asset = make_asset()
        existing = make_product(
            asset,
            metadata={"manual": True},
            display_name="Creator edited title",
        )
        existing = Product(
            **{
                **existing.__dict__,
                "description": "Creator edited description",
                "tags": ("custom",),
                "themes": ("VIP",),
                "product_type": ProductType.SINGLE_IMAGE,
            }
        )
        products = FakeProducts(existing)
        service = self.service(asset, products)

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
        )

        self.assertFalse(result.created)
        self.assertFalse(result.activated)
        self.assertEqual(result.product.display_name, "Creator edited title")
        self.assertEqual(result.product.description, "Creator edited description")
        self.assertEqual(result.product.tags, ("custom",))
        self.assertEqual(
            result.product.metadata["last_ai_refresh_skipped"],
            "creator_edits_preserved",
        )

    def test_refresh_without_commerce_preserves_existing_delivery_type(self):
        asset = make_asset()
        existing = make_product(
            asset,
            metadata={
                "ai_product_draft": True,
                "draft_source": "ai_cms_asset",
                "delivery_type": "FREE",
            },
        )
        products = FakeProducts(existing)
        service = self.service(asset, products)

        result = service.create_or_refresh_draft_for_asset(
            asset.id,
            creator_profile_id=2,
        )

        self.assertFalse(result.created)
        self.assertEqual(result.product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(result.product.metadata["delivery_type"], "FREE")


if __name__ == "__main__":
    unittest.main()

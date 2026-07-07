import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.experience import (
    Experience,
    ExperienceAssetRelationship,
    ExperienceProductRelationship,
    ExperiencePersistenceSupport,
    ExperienceType,
    ProductExperienceRelationship,
)
from app.models.product import ProductType
from app.repositories.experience_repository import ExperienceRepository


def product(**overrides):
    now = datetime.now(timezone.utc)
    values = {
        "id": uuid4(),
        "creator_profile_id": 7,
        "legacy_content_item_id": None,
        "internal_name": "internal-product",
        "display_name": "Projected Experience",
        "description": "Projected from compatibility product data.",
        "product_type": ProductType.SINGLE_IMAGE,
        "metadata": {},
        "created_at": now,
        "updated_at": now,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def link(asset_id: int, position: int):
    return SimpleNamespace(asset_id=asset_id, position=position)


def asset(asset_id: int, **overrides):
    values = {
        "id": asset_id,
        "file_name": f"asset_{asset_id}.jpg",
        "file_path": f"data/uploads/asset_{asset_id}.jpg",
        "summary": f"Asset {asset_id} summary",
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeProducts:
    def __init__(self, products):
        self.products = {item.id: item for item in products}
        self.list_calls = []

    def get_by_id(self, product_id, creator_profile_id=None):
        product_record = self.products.get(product_id)
        if not product_record:
            return None
        if (
            creator_profile_id is not None
            and product_record.creator_profile_id != creator_profile_id
        ):
            return None
        return product_record

    def list_products(self, **kwargs):
        self.list_calls.append(kwargs)
        return list(self.products.values())


class FakeProductAssets:
    def __init__(self, links_by_product):
        self.links_by_product = links_by_product
        self.calls = []

    def list_for_product(self, product_id):
        self.calls.append(product_id)
        return self.links_by_product.get(product_id, [])

    def list_product_ids_for_asset(self, asset_id):
        return tuple(
            product_id
            for product_id, links in self.links_by_product.items()
            if any(item.asset_id == asset_id for item in links)
        )


class FakeExperienceReadModel:
    def __init__(
        self,
        experiences=None,
        relationships=None,
        product_relationships=None,
        experience_product_relationships=None,
    ):
        self.experiences = list(experiences or [])
        self.relationships = tuple(relationships or ())
        self.product_relationships = tuple(product_relationships or ())
        self.experience_product_relationships = tuple(
            experience_product_relationships or ()
        )

    def get_by_product_id(self, product_id, *, creator_profile_id=None):
        for experience in self.experiences:
            if experience.metadata.get("source_product_id") == str(product_id):
                return experience
        return None

    def list_experiences(self, **kwargs):
        return list(self.experiences)

    def list_asset_relationships(self, asset_id):
        return tuple(
            relationship
            for relationship in self.relationships
            if relationship.asset_id == asset_id
        )

    def list_product_relationships(self, product_id):
        return tuple(
            relationship
            for relationship in self.product_relationships
            if relationship.product_id == str(product_id)
        )

    def list_experience_product_relationships(self, experience_id):
        return tuple(
            relationship
            for relationship in self.experience_product_relationships
            if relationship.experience_id == str(experience_id)
        )

    def support(self):
        return ExperiencePersistenceSupport(
            dedicated_read_model=bool(self.experiences),
            relationship_read_model=bool(
                self.relationships
                or self.product_relationships
                or self.experience_product_relationships
            ),
            source="fake_experience_read_model",
            compatibility_fallback="products.product_assets",
        )


class ExperienceRepositoryTests(unittest.TestCase):
    def repo(self, products, links_by_product=None):
        return ExperienceRepository(
            product_repository=FakeProducts(products),
            product_asset_repository=FakeProductAssets(links_by_product or {}),
        )

    def test_projects_experience_from_product_assets(self):
        product_record = product(
            product_type=ProductType.PHOTO_SET,
            metadata={"product_structure": "photo_set", "mood": "soft"},
        )
        repo = self.repo(
            [product_record],
            {
                product_record.id: [
                    link(12, 1),
                    link(11, 0),
                    link(13, 2),
                ]
            },
        )

        experience = repo.get_experience(product_record.id)

        self.assertIsInstance(experience, Experience)
        self.assertEqual(experience.experience_type, ExperienceType.PHOTOSHOOT)
        self.assertEqual(experience.asset_ids, (11, 12, 13))
        self.assertEqual(experience.asset_order, (11, 12, 13))
        self.assertEqual(experience.cover_asset_id, 11)
        self.assertEqual(experience.metadata["mood"], "soft")
        self.assertEqual(
            experience.metadata["compatibility_source"],
            "products.product_assets",
        )

    def test_dedicated_read_model_wins_over_product_projection(self):
        product_record = product(product_type=ProductType.SINGLE_IMAGE)
        dedicated = Experience(
            experience_id="experience:first-class",
            experience_type=ExperienceType.STORY,
            title="First Class",
            description=None,
            cover_asset_id=99,
            asset_ids=(99,),
            asset_order=(99,),
            metadata={"source_product_id": str(product_record.id)},
        )
        repo = ExperienceRepository(
            product_repository=FakeProducts([product_record]),
            product_asset_repository=FakeProductAssets(
                {product_record.id: [link(11, 0)]}
            ),
            experience_read_model_repository=FakeExperienceReadModel(
                experiences=[dedicated]
            ),
        )

        experience = repo.get_experience(product_record.id)

        self.assertIs(experience, dedicated)
        self.assertEqual(experience.experience_id, "experience:first-class")

    def test_asset_relationships_use_read_model_before_compatibility(self):
        dedicated_relationship = ExperienceAssetRelationship(
            experience_id="experience:first-class",
            asset_id=12,
            position=2,
            source="experience_read_model",
        )
        product_record = product(product_type=ProductType.PHOTO_SET)
        repo = ExperienceRepository(
            product_repository=FakeProducts([product_record]),
            product_asset_repository=FakeProductAssets(
                {product_record.id: [link(12, 0)]}
            ),
            experience_read_model_repository=FakeExperienceReadModel(
                relationships=[dedicated_relationship]
            ),
        )

        relationships = repo.list_asset_relationships(12)

        self.assertEqual(relationships, (dedicated_relationship,))
        self.assertFalse(relationships[0].compatibility)

    def test_product_asset_relationships_are_compatibility_only(self):
        product_record = product(product_type=ProductType.PHOTO_SET)
        repo = self.repo(
            [product_record],
            {product_record.id: [link(12, 1), link(13, 0)]},
        )

        relationships = repo.list_asset_relationships(12)

        self.assertEqual(len(relationships), 1)
        self.assertEqual(
            relationships[0].experience_id,
            f"product:{product_record.id}",
        )
        self.assertTrue(relationships[0].compatibility)
        self.assertEqual(relationships[0].source, "products.product_assets")

    def test_product_relationship_prefers_dedicated_read_model(self):
        product_record = product(product_type=ProductType.PHOTO_SET)
        relationship = ProductExperienceRelationship(
            product_id=product_record.id,
            experience_id="experience:first-class",
            source="experience_read_model",
        )
        repo = ExperienceRepository(
            product_repository=FakeProducts([product_record]),
            product_asset_repository=FakeProductAssets(
                {product_record.id: [link(12, 0)]}
            ),
            experience_read_model_repository=FakeExperienceReadModel(
                product_relationships=[relationship]
            ),
        )

        relationships = repo.list_product_relationships(product_record.id)

        self.assertEqual(relationships, (relationship,))
        self.assertFalse(relationships[0].compatibility)

    def test_product_relationship_fallback_is_compatibility_labeled(self):
        product_record = product(product_type=ProductType.PHOTO_SET)
        repo = self.repo(
            [product_record],
            {product_record.id: [link(12, 0), link(13, 1)]},
        )

        relationships = repo.list_product_relationships(product_record.id)

        self.assertEqual(len(relationships), 1)
        self.assertEqual(
            relationships[0].experience_id,
            f"product:{product_record.id}",
        )
        self.assertTrue(relationships[0].compatibility)
        self.assertTrue(relationships[0].compatibility_experience_id)
        self.assertEqual(relationships[0].source, "products.product_assets")

    def test_experience_product_relationship_fallback_is_compatibility_labeled(self):
        product_id = uuid4()
        repo = self.repo([])

        relationships = repo.list_experience_product_relationships(
            f"product:{product_id}"
        )

        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0].product_id, str(product_id))
        self.assertTrue(relationships[0].compatibility)
        self.assertTrue(relationships[0].compatibility_experience_id)

    def test_explicit_cover_asset_is_preserved(self):
        product_record = product(
            product_type=ProductType.PHOTO_SET,
            metadata={"cover_asset_id": 22},
        )
        repo = self.repo(
            [product_record],
            {product_record.id: [link(21, 0), link(22, 1)]},
        )

        experience = repo.get_by_product_id(product_record.id)

        self.assertEqual(experience.cover_asset_id, 22)
        self.assertEqual(experience.asset_order, (21, 22))

    def test_standalone_experience_falls_back_to_legacy_asset(self):
        product_record = product(
            product_type=ProductType.SINGLE_IMAGE,
            legacy_content_item_id=31,
            metadata=None,
        )
        repo = self.repo([product_record])

        experience = repo.get_experience(product_record.id)

        self.assertEqual(experience.experience_type, ExperienceType.STANDALONE)
        self.assertEqual(experience.asset_ids, (31,))
        self.assertEqual(experience.asset_order, (31,))
        self.assertEqual(experience.cover_asset_id, 31)

    def test_story_experience_uses_product_type(self):
        product_record = product(
            product_type=ProductType.STORY,
            metadata={"asset_order": [42, 41], "source_asset_ids": [41, 42]},
        )
        repo = self.repo([product_record])

        experience = repo.get_experience(product_record.id)

        self.assertEqual(experience.experience_type, ExperienceType.STORY)
        self.assertEqual(experience.asset_ids, (41, 42))
        self.assertEqual(experience.asset_order, (42, 41))
        self.assertEqual(experience.cover_asset_id, 42)

    def test_missing_optional_metadata_is_safe(self):
        product_record = product(
            product_type=ProductType.CUSTOM,
            metadata={},
            description=None,
            legacy_content_item_id=None,
        )
        repo = self.repo([product_record])

        experience = repo.get_experience(product_record.id)

        self.assertEqual(experience.asset_ids, ())
        self.assertEqual(experience.asset_order, ())
        self.assertIsNone(experience.cover_asset_id)
        self.assertEqual(experience.description, None)

    def test_list_experiences_returns_experience_objects(self):
        first = product(product_type=ProductType.SINGLE_IMAGE)
        second = product(product_type=ProductType.STORY)
        repo = self.repo(
            [first, second],
            {
                first.id: [link(51, 0)],
                second.id: [link(61, 0), link(62, 1)],
            },
        )

        experiences = repo.list_experiences(creator_profile_id=7)

        self.assertEqual(len(experiences), 2)
        self.assertTrue(all(isinstance(item, Experience) for item in experiences))
        self.assertEqual(experiences[0].asset_order, (51,))
        self.assertEqual(experiences[1].experience_type, ExperienceType.STORY)

    def test_missing_product_returns_none(self):
        repo = self.repo([])

        self.assertIsNone(repo.get_experience(uuid4()))

    def test_builds_standalone_experience_from_asset(self):
        repo = self.repo([])
        source_asset = asset(71, file_name="cover.jpg")

        experience = repo.build_standalone_experience(
            source_asset,
            title="Standalone Cover",
            metadata={"mood": "bright"},
        )

        self.assertEqual(experience.experience_type, ExperienceType.STANDALONE)
        self.assertEqual(experience.asset_ids, (71,))
        self.assertEqual(experience.asset_order, (71,))
        self.assertEqual(experience.cover_asset_id, 71)
        self.assertEqual(experience.title, "Standalone Cover")
        self.assertEqual(experience.metadata["mood"], "bright")
        self.assertEqual(experience.metadata["source_asset_id"], 71)

    def test_builds_photoshoot_experience_from_ordered_assets(self):
        repo = self.repo([])

        experience = repo.build_photoshoot_experience(
            [asset(81), asset(82), asset(83)],
            title="Editorial Set",
            metadata={"source": "ai_draft"},
            cover_asset_id=82,
            asset_order=[83, 81, 82],
        )

        self.assertEqual(experience.experience_type, ExperienceType.PHOTOSHOOT)
        self.assertEqual(experience.asset_ids, (81, 82, 83))
        self.assertEqual(experience.asset_order, (83, 81, 82))
        self.assertEqual(experience.cover_asset_id, 82)
        self.assertEqual(experience.metadata["asset_count"], 3)
        self.assertEqual(experience.metadata["source_asset_ids"], [81, 82, 83])

    def test_builds_story_experience_from_assets(self):
        repo = self.repo([])

        experience = repo.build_story_experience(
            [asset(91), asset(92)],
            title="Story Sequence",
        )

        self.assertEqual(experience.experience_type, ExperienceType.STORY)
        self.assertEqual(experience.asset_order, (91, 92))
        self.assertEqual(experience.cover_asset_id, 91)


if __name__ == "__main__":
    unittest.main()

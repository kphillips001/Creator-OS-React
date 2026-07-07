import unittest
from uuid import uuid4

from app.models.experience import (
    Experience,
    ExperienceAssetRelationship,
    ExperienceProductRelationship,
    ExperiencePersistenceSupport,
    ExperienceType,
    ProductExperienceRelationship,
)
from app.services.experience_service import ExperienceService


def experience(
    *,
    experience_type=ExperienceType.STANDALONE,
    asset_ids=(101,),
    asset_order=None,
    cover_asset_id=None,
    metadata=None,
):
    asset_order = asset_ids if asset_order is None else asset_order
    return Experience(
        experience_id="experience-test",
        experience_type=experience_type,
        title="Test Experience",
        description="Projected by repository.",
        cover_asset_id=cover_asset_id,
        asset_ids=asset_ids,
        asset_order=asset_order,
        metadata=metadata or {"source": "fake_repository"},
    )


class FakeExperienceRepository:
    def __init__(self):
        self.experience = None
        self.experiences = []
        self.product_assets = []
        self.asset_count = 0
        self.deleted_count = 0
        self.get_calls = []
        self.list_calls = []
        self.build_calls = []
        self.product_asset_calls = []

    def get_experience(self, product_id, *, creator_profile_id=None):
        self.get_calls.append(
            {
                "product_id": product_id,
                "creator_profile_id": creator_profile_id,
            }
        )
        return self.experience

    def list_experiences(self, **kwargs):
        self.list_calls.append(kwargs)
        return self.experiences

    def build_standalone_experience(self, asset, **kwargs):
        self.build_calls.append(("standalone", asset, kwargs))
        return experience(asset_ids=(asset.id,))

    def build_experience(self, product, product_assets=None):
        links = tuple(product_assets or ())
        self.build_calls.append(("product", product, {"links": links}))
        return experience(
            experience_type=ExperienceType.PHOTOSHOOT,
            asset_ids=tuple(link.asset_id for link in links),
            asset_order=tuple(link.asset_id for link in links),
        )

    def build_photoshoot_experience(self, assets, **kwargs):
        self.build_calls.append(("photoshoot", tuple(assets), kwargs))
        return experience(
            experience_type=ExperienceType.PHOTOSHOOT,
            asset_ids=tuple(asset.id for asset in assets),
            asset_order=tuple(kwargs.get("asset_order") or ()),
            cover_asset_id=kwargs.get("cover_asset_id"),
        )

    def build_story_experience(self, assets, **kwargs):
        self.build_calls.append(("story", tuple(assets), kwargs))
        return experience(
            experience_type=ExperienceType.STORY,
            asset_ids=tuple(asset.id for asset in assets),
        )

    def list_product_experience_assets(self, product_id, *, connection=None):
        self.product_asset_calls.append(
            ("list", product_id, connection)
        )
        return list(self.product_assets)

    def count_product_experience_assets(self, product_id):
        self.product_asset_calls.append(("count", product_id))
        return self.asset_count

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

    def attach_primary_product_experience_asset(self, product_id, asset_id):
        self.product_asset_calls.append(("attach", product_id, asset_id))
        return (product_id, asset_id), True

    def delete_product_experience_assets(self, product_id, *, connection=None):
        self.product_asset_calls.append(
            ("delete", product_id, connection)
        )
        return self.deleted_count

    def list_asset_relationships(self, asset_id):
        return (
            ExperienceAssetRelationship(
                experience_id="experience-test",
                asset_id=asset_id,
                position=0,
                source="fake_repository",
            ),
        )

    def list_product_relationships(self, product_id, *, creator_profile_id=None):
        return (
            ProductExperienceRelationship(
                product_id=product_id,
                experience_id="experience-test",
                source="fake_repository",
            ),
        )

    def list_experience_product_relationships(self, experience_id):
        return (
            ExperienceProductRelationship(
                experience_id=experience_id,
                product_id="product-test",
                source="fake_repository",
            ),
        )

    def support(self):
        return ExperiencePersistenceSupport(
            dedicated_read_model=False,
            relationship_read_model=True,
            source="fake_repository",
            compatibility_fallback="products.product_assets",
        )


class ExperienceServiceTests(unittest.TestCase):
    def service(self):
        repository = FakeExperienceRepository()
        return ExperienceService(repository), repository

    def test_retrieves_experience_through_repository(self):
        service, repository = self.service()
        product_id = uuid4()
        repository.experience = experience()

        result = service.get_experience(
            product_id,
            creator_profile_id=7,
        )

        self.assertIs(result, repository.experience)
        self.assertEqual(
            repository.get_calls,
            [{"product_id": product_id, "creator_profile_id": 7}],
        )

    def test_lists_experiences_through_repository(self):
        service, repository = self.service()
        repository.experiences = [
            experience(),
            experience(experience_type=ExperienceType.STORY, asset_ids=(1, 2)),
        ]

        result = service.list_experiences(
            creator_profile_id=7,
            search="set",
            include_archived=True,
            limit=25,
        )

        self.assertEqual(result, repository.experiences)
        self.assertEqual(repository.list_calls[0]["creator_profile_id"], 7)
        self.assertEqual(repository.list_calls[0]["search"], "set")
        self.assertTrue(repository.list_calls[0]["include_archived"])
        self.assertEqual(repository.list_calls[0]["limit"], 25)

    def test_interprets_experience_type(self):
        service, _ = self.service()
        standalone = experience()
        photoshoot = experience(
            experience_type=ExperienceType.PHOTOSHOOT,
            asset_ids=(1, 2),
        )
        story = experience(
            experience_type=ExperienceType.STORY,
            asset_ids=(3, 4),
        )

        self.assertTrue(service.is_standalone(standalone))
        self.assertFalse(service.is_standalone(photoshoot))
        self.assertTrue(service.is_photoshoot(photoshoot))
        self.assertTrue(service.is_story(story))
        self.assertTrue(service.is_collection(photoshoot))
        self.assertTrue(service.is_collection(story))

    def test_returns_ordered_assets_cover_and_metadata(self):
        service, _ = self.service()
        record = experience(
            experience_type=ExperienceType.PHOTOSHOOT,
            asset_ids=(10, 11, 12),
            asset_order=(12, 10, 11),
            cover_asset_id=11,
            metadata={"mood": "soft"},
        )

        self.assertEqual(service.get_asset_ids(record), (10, 11, 12))
        self.assertEqual(service.get_ordered_asset_ids(record), (12, 10, 11))
        self.assertEqual(service.get_cover_asset_id(record), 11)
        self.assertEqual(service.get_metadata(record), {"mood": "soft"})

    def test_missing_experience_is_safe(self):
        service, repository = self.service()
        product_id = uuid4()

        self.assertIsNone(service.get_experience(product_id))
        self.assertIsNone(service.get_experience_type(None))
        self.assertIsNone(service.get_cover_asset_id(None))
        self.assertEqual(service.get_ordered_asset_ids(None), ())
        self.assertEqual(service.get_asset_ids(None), ())
        self.assertEqual(service.get_metadata(None), {})
        self.assertFalse(service.is_standalone(None))
        self.assertFalse(service.is_photoshoot(None))
        self.assertFalse(service.is_story(None))
        self.assertFalse(service.is_collection(None))
        self.assertEqual(repository.get_calls[0]["product_id"], product_id)

    def test_product_convenience_methods_delegate_to_repository_once_each(self):
        service, repository = self.service()
        product_id = uuid4()
        repository.experience = experience(
            experience_type=ExperienceType.STORY,
            asset_ids=(21, 22),
            asset_order=(22, 21),
        )

        self.assertEqual(
            service.get_product_experience_type(product_id),
            ExperienceType.STORY,
        )
        self.assertEqual(service.get_product_cover_asset_id(product_id), 22)
        self.assertEqual(
            service.get_product_ordered_asset_ids(product_id),
            (22, 21),
        )
        self.assertEqual(len(repository.get_calls), 3)

    def test_build_methods_delegate_to_repository(self):
        service, repository = self.service()
        first = type("Asset", (), {"id": 31})()
        second = type("Asset", (), {"id": 32})()
        product = type("Product", (), {"id": uuid4()})()
        link = type("ProductAsset", (), {"asset_id": 30})()

        projected = service.build_product_experience(product, [link])
        standalone = service.build_standalone_experience(
            first,
            title="Single",
        )
        photoshoot = service.build_photoshoot_experience(
            [first, second],
            title="Set",
            cover_asset_id=32,
            asset_order=[32, 31],
        )
        story = service.build_story_experience([first, second])

        self.assertEqual(standalone.experience_type, ExperienceType.STANDALONE)
        self.assertEqual(photoshoot.experience_type, ExperienceType.PHOTOSHOOT)
        self.assertEqual(photoshoot.asset_order, (32, 31))
        self.assertEqual(story.experience_type, ExperienceType.STORY)
        self.assertEqual(
            [call[0] for call in repository.build_calls],
            ["product", "standalone", "photoshoot", "story"],
        )

        self.assertEqual(projected.asset_ids, (30,))
        self.assertEqual(repository.build_calls[0][0], "product")

    def test_product_experience_asset_persistence_delegates_to_repository(self):
        service, repository = self.service()
        product_id = uuid4()
        connection = object()
        repository.product_assets = [
            type("ProductAsset", (), {"asset_id": 41})(),
            type("ProductAsset", (), {"asset_id": 42})(),
        ]
        repository.asset_count = 2
        repository.deleted_count = 2

        listed = service.list_product_experience_assets(
            product_id,
            connection=connection,
        )
        count = service.count_product_experience_assets(product_id)
        replaced = service.replace_product_experience_assets(
            product_id,
            [42, 41],
            connection=connection,
        )
        attached, attached_created = (
            service.attach_primary_product_experience_asset(product_id, 43)
        )
        deleted = service.delete_product_experience_assets(
            product_id,
            connection=connection,
        )

        self.assertEqual([link.asset_id for link in listed], [41, 42])
        self.assertEqual(count, 2)
        self.assertEqual([link.asset_id for link in replaced], [41, 42])
        self.assertEqual(attached, (product_id, 43))
        self.assertTrue(attached_created)
        self.assertEqual(deleted, 2)
        self.assertEqual(
            repository.product_asset_calls,
            [
                ("list", product_id, connection),
                ("count", product_id),
                ("replace", product_id, (42, 41), connection),
                ("attach", product_id, 43),
                ("delete", product_id, connection),
            ],
        )

    def test_asset_relationships_go_through_experience_service(self):
        service, _ = self.service()

        relationships = service.list_asset_relationships(77)

        self.assertEqual(len(relationships), 1)
        self.assertEqual(relationships[0].experience_id, "experience-test")
        self.assertEqual(service.list_asset_experience_ids(77), ("experience-test",))

    def test_product_experience_relationships_go_through_experience_service(self):
        service, _ = self.service()
        product_id = uuid4()

        product_relationships = service.list_product_relationships(product_id)
        experience_relationships = service.list_experience_product_relationships(
            "experience-test"
        )

        self.assertEqual(product_relationships[0].product_id, str(product_id))
        self.assertEqual(product_relationships[0].experience_id, "experience-test")
        self.assertEqual(
            service.list_product_experience_ids(product_id),
            ("experience-test",),
        )
        self.assertEqual(
            experience_relationships[0].product_id,
            "product-test",
        )

    def test_persistence_support_is_exposed_by_service_boundary(self):
        service, _ = self.service()

        support = service.persistence_support()

        self.assertFalse(support.dedicated_read_model)
        self.assertTrue(support.relationship_read_model)
        self.assertEqual(support.compatibility_fallback, "products.product_assets")

    def test_composition_helpers_order_cover_and_preview_assets(self):
        service, _ = self.service()
        record = experience(
            experience_type=ExperienceType.PHOTOSHOOT,
            asset_ids=(1, 2, 3),
            asset_order=(3, 1, 2),
            cover_asset_id=2,
        )
        assets = [
            type("Asset", (), {"id": 1})(),
            type("Asset", (), {"id": 2})(),
            type("Asset", (), {"id": 3})(),
        ]

        ordered = service.order_assets_for_experience(record, assets)
        cover = service.cover_asset_for_experience(record, ordered)
        preview = service.preview_asset_for_experience(record, ordered)

        self.assertEqual([asset.id for asset in ordered], [3, 1, 2])
        self.assertEqual(cover.id, 2)
        self.assertEqual(preview.id, 2)


if __name__ == "__main__":
    unittest.main()

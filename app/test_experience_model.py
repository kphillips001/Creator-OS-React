import unittest
from uuid import uuid4

from app.models.experience import Experience, ExperienceType


class ExperienceModelTests(unittest.TestCase):
    def test_standalone_asset_contract(self):
        experience = Experience.standalone(
            asset_id=101,
            title="Mirror teaser",
        )

        self.assertEqual(experience.experience_type, ExperienceType.STANDALONE)
        self.assertEqual(experience.asset_ids, (101,))
        self.assertEqual(experience.asset_order, (101,))
        self.assertEqual(experience.cover_asset_id, 101)
        self.assertTrue(experience.is_standalone)
        self.assertFalse(experience.is_collection)

    def test_photoshoot_contract_preserves_ordered_assets(self):
        experience_id = uuid4()

        experience = Experience(
            experience_id=experience_id,
            experience_type=ExperienceType.PHOTOSHOOT,
            title="Lace room shoot",
            description="Ordered imported shoot assets.",
            cover_asset_id=None,
            asset_ids=(201, 202, 203),
            asset_order=(202, 201, 203),
            metadata={"lighting": "soft", "source": "cms_upload"},
        )

        self.assertEqual(experience.experience_id, experience_id)
        self.assertEqual(experience.asset_ids, (201, 202, 203))
        self.assertEqual(experience.ordered_asset_ids, (202, 201, 203))
        self.assertEqual(experience.cover_asset_id, 202)
        self.assertEqual(experience.metadata["source"], "cms_upload")
        self.assertTrue(experience.is_collection)

    def test_story_contract_allows_explicit_cover_asset(self):
        experience = Experience(
            experience_id="story-1",
            experience_type=ExperienceType.STORY,
            title="Three-part morning story",
            description=None,
            cover_asset_id=303,
            asset_ids=(301, 302, 303),
            asset_order=(301, 302, 303),
            metadata={"structure": "story"},
        )

        self.assertEqual(experience.experience_type, ExperienceType.STORY)
        self.assertEqual(experience.cover_asset_id, 303)
        self.assertEqual(experience.asset_order, (301, 302, 303))
        self.assertEqual(experience.metadata, {"structure": "story"})

    def test_asset_order_defaults_to_asset_ids(self):
        experience = Experience(
            experience_id=None,
            experience_type=ExperienceType.PHOTOSHOOT,
            title="Upload batch",
            description=None,
            cover_asset_id=None,
            asset_ids=(401, 402),
            asset_order=(),
            metadata={},
        )

        self.assertEqual(experience.asset_order, (401, 402))
        self.assertEqual(experience.cover_asset_id, 401)

    def test_from_row_coerces_values_and_preserves_metadata(self):
        experience = Experience.from_row(
            {
                "id": "experience-row",
                "experience_type": "PHOTOSHOOT",
                "title": "Imported set",
                "description": "Recovered contract row.",
                "cover_asset_id": None,
                "asset_ids": ["501", "502"],
                "asset_order": ["502", "501"],
                "metadata": {"asset_count": 2},
            }
        )

        self.assertEqual(experience.experience_id, "experience-row")
        self.assertEqual(experience.asset_ids, (501, 502))
        self.assertEqual(experience.asset_order, (502, 501))
        self.assertEqual(experience.cover_asset_id, 502)
        self.assertEqual(experience.metadata, {"asset_count": 2})

    def test_product_commerce_fields_are_not_required(self):
        experience = Experience(
            experience_id=None,
            experience_type=ExperienceType.STORY,
            title="No commerce here",
            description=None,
            cover_asset_id=None,
            asset_ids=(601,),
            asset_order=(601,),
            metadata={},
        )

        self.assertFalse(hasattr(experience, "price_cents"))
        self.assertFalse(hasattr(experience, "product_type"))
        self.assertFalse(hasattr(experience, "fulfillment_status"))
        self.assertFalse(hasattr(experience, "media_link"))


if __name__ == "__main__":
    unittest.main()

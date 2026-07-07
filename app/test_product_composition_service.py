import unittest
from types import SimpleNamespace

from app.models.content_intelligence import ContentIntelligence, ContentRecommendation
from app.models.experience import ExperienceType
from app.models.experience_intelligence import ExperienceRecommendation
from app.models.product_business import ProductBusinessSnapshot
from app.models.product_composition import ProductCompositionType
from app.models.product_strategy import (
    ProductCompositionRecommendation as StrategyCompositionRecommendation,
    ProductStrategyRecommendation,
    ProductStrategyResult,
)
from app.services.product_composition_service import ProductCompositionService


def content(asset_id, *, cover=False):
    return ContentIntelligence(
        asset_id=asset_id,
        asset_understanding=SimpleNamespace(),
        summary=f"Asset {asset_id}",
        suggested_cover_image=(
            ContentRecommendation(
                recommendation_type="cover_image",
                asset_id=asset_id,
                recommended=True,
                confidence=0.9,
            )
            if cover
            else None
        ),
    )


def experience(*, experience_type=ExperienceType.PHOTOSHOOT):
    return ExperienceRecommendation(
        experience_type=experience_type,
        asset_ids=(101, 102, 103),
        suggested_name="Set",
        suggested_cover_asset_id=102,
        confidence=0.82,
    )


class ProductCompositionServiceTests(unittest.TestCase):
    def test_product_composition_generation_from_product_strategy(self):
        service = ProductCompositionService()
        strategy = ProductStrategyResult(
            source_type="experience",
            source_id="exp-1",
            recommendations=(
                ProductStrategyRecommendation(
                    recommendation_type="free_preview",
                    source_type="experience",
                    source_id="exp-1",
                    composition=StrategyCompositionRecommendation(
                        composition_type="free_preview",
                        included_asset_ids=(102,),
                        asset_order=(102,),
                        cover_asset_id=102,
                        experience_id="exp-1",
                        relationship_type="experience_product",
                    ),
                    confidence=0.88,
                ),
            ),
        )

        recommendations = service.recommend_compositions(
            product_strategy_result=strategy,
            content_intelligences=(content(101), content(102)),
        )

        recommendation = next(
            item
            for item in recommendations
            if item.composition_type == ProductCompositionType.FREE_PREVIEW
        )
        self.assertEqual(
            recommendation.composition_type,
            ProductCompositionType.FREE_PREVIEW,
        )
        self.assertEqual(recommendation.composition.included_asset_ids, (102,))
        self.assertEqual(recommendation.composition.cover_asset_id, 102)
        self.assertEqual(recommendation.confidence, 0.88)
        self.assertFalse(recommendation.compatibility["creates_products"])
        self.assertFalse(recommendation.compatibility["generates_product_strategy"])

    def test_bundle_recommendations(self):
        recommendations = ProductCompositionService().recommend_compositions(
            experience_context=experience(),
            content_intelligences=(content(101), content(102), content(103)),
        )

        bundle = next(
            item
            for item in recommendations
            if item.composition_type == ProductCompositionType.BUNDLE
        )

        self.assertEqual(bundle.composition.included_asset_ids, (101, 102, 103))
        self.assertEqual(bundle.composition.asset_order, (101, 102, 103))
        self.assertEqual(bundle.composition.cover_asset_id, 102)
        self.assertEqual(bundle.composition.relationship_type, "bundle")

    def test_story_recommendations_preserve_sequence(self):
        recommendations = ProductCompositionService().recommend_compositions(
            experience_context=experience(experience_type=ExperienceType.STORY),
            content_intelligences=(content(101), content(102), content(103)),
        )

        story = next(
            item
            for item in recommendations
            if item.composition_type == ProductCompositionType.STORY_PRODUCT
        )

        self.assertEqual(story.composition.asset_order, (101, 102, 103))
        self.assertEqual(story.composition.relationship_type, "story_sequence")
        self.assertIn(
            "Preserve Experience ordering for story progression.",
            story.rationale,
        )

    def test_free_preview_uses_cover_asset(self):
        recommendation = ProductCompositionService().recommend_free_preview(
            experience_context={"asset_ids": (201, 202), "cover_asset_id": 202},
            content_intelligences=(content(201), content(202)),
        )

        self.assertIsNotNone(recommendation)
        self.assertEqual(
            recommendation.composition_type,
            ProductCompositionType.FREE_PREVIEW,
        )
        self.assertEqual(recommendation.composition.preview_asset_ids, (202,))
        self.assertEqual(recommendation.composition.cover_asset_id, 202)

    def test_product_business_integration_for_related_products(self):
        recommendations = ProductCompositionService().recommend_compositions(
            experience_context=experience(),
            content_intelligences=(content(101), content(102), content(103)),
            product_business_snapshots=(
                ProductBusinessSnapshot(product_id="free-preview"),
                ProductBusinessSnapshot(product_id="premium-set"),
            ),
        )

        collection = next(
            item
            for item in recommendations
            if item.composition_type == ProductCompositionType.COLLECTION
        )

        self.assertEqual(
            collection.composition.related_product_ids,
            ("free-preview", "premium-set"),
        )
        self.assertEqual(
            collection.composition.collection_membership,
            ("free-preview", "premium-set"),
        )

    def test_backward_compatibility_mapping_inputs(self):
        strategy = {
            "source_id": "legacy-exp",
            "recommendations": (
                {
                    "recommendation_type": "story_product",
                    "confidence": 0.7,
                    "composition": {
                        "included_asset_ids": (1, 2, 3),
                        "asset_order": (3, 2, 1),
                        "cover_asset_id": 3,
                        "experience_id": "legacy-exp",
                        "relationship_type": "legacy_story",
                    },
                },
            ),
        }

        recommendations = ProductCompositionService().recommend_compositions(
            product_strategy_result=strategy,
            product_business_snapshots=({"product_id": "related-1"},),
        )

        self.assertEqual(len(recommendations), 1)
        recommendation = recommendations[0]
        self.assertEqual(
            recommendation.composition_type,
            ProductCompositionType.STORY_PRODUCT,
        )
        self.assertEqual(recommendation.composition.asset_order, (3, 2, 1))
        self.assertEqual(recommendation.composition.experience_id, "legacy-exp")
        self.assertTrue(recommendation.compatibility["provider_neutral"])


if __name__ == "__main__":
    unittest.main()

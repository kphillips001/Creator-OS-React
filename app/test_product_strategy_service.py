import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.business_learning import LearningContext, LearningSummary
from app.services.content_intelligence_service import ContentIntelligenceService
from app.services.product_strategy_service import ProductStrategyService


def content_record(asset_id=101):
    understanding = SimpleNamespace(
        identity=SimpleNamespace(asset_id=asset_id),
        media=SimpleNamespace(media_type="image", runtime_exists=True),
        visual=SimpleNamespace(
            summary="Soft mirror set.",
            detected_themes=("mirror",),
            suggested_tags=("vip",),
            mood="soft",
            setting="bedroom",
            outfit="lace set",
            activity="posing",
            objects=("mirror",),
            gpt_vision_result={},
        ),
        classification=SimpleNamespace(
            final_classification="VIP",
            classification="VIP",
            confidence=0.91,
            classification_result={},
        ),
        safety=SimpleNamespace(),
        metadata=SimpleNamespace(media_metadata={}),
        provenance=SimpleNamespace(),
        readiness=SimpleNamespace(
            has_runtime_media=True,
            has_visual_summary=True,
            has_classification=True,
            needs_review=False,
        ),
    )
    return ContentIntelligenceService().build_from_understanding(understanding)


class ProductStrategyServiceTests(unittest.TestCase):
    def test_recommendation_consumes_content_and_experience_context(self):
        service = ProductStrategyService()
        experience = SimpleNamespace(
            experience_id="experience-1",
            asset_ids=(101, 102),
            asset_order=(102, 101),
            suggested_cover_asset_id=102,
            is_collection=True,
            experience_type=SimpleNamespace(value="PHOTOSHOOT"),
        )

        result = service.recommend(
            creator_intent={"content_type": "Photoshoot"},
            content_intelligences=(content_record(101), content_record(102)),
            experience_context=experience,
            commerce_recommendation=SimpleNamespace(),
        )

        self.assertEqual(result.source_type, "experience")
        self.assertEqual(result.source_id, "experience-1")
        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in result.recommendations
        }
        self.assertIn("free_preview", recommendation_types)
        self.assertIn("bundle", recommendation_types)
        self.assertIn("collection", recommendation_types)
        self.assertIn("photoshoot_product", recommendation_types)
        recommendation = result.recommendations[0]
        self.assertEqual(
            result.catalog_recommendation.associated_experience_id,
            "experience-1",
        )
        self.assertEqual(
            result.catalog_recommendation.associated_experience_type,
            "PHOTOSHOOT",
        )
        self.assertEqual(
            result.catalog_recommendation.recommended_products,
            result.recommendations,
        )
        self.assertFalse(
            result.catalog_recommendation.metadata["contains_product_metadata"]
        )
        self.assertEqual(recommendation.asset_ids, (101, 102))
        by_type = {
            recommendation.recommendation_type: recommendation
            for recommendation in result.recommendations
        }
        self.assertEqual(
            by_type["free_preview"].composition.included_asset_ids,
            (102,),
        )
        self.assertEqual(
            by_type["free_preview"].composition.asset_order,
            (102,),
        )
        self.assertEqual(
            by_type["free_preview"].composition.cover_asset_id,
            102,
        )
        self.assertEqual(
            by_type["bundle"].composition.included_asset_ids,
            (102, 101),
        )
        self.assertEqual(
            by_type["bundle"].composition.relationship_type,
            "experience_product",
        )
        self.assertEqual(
            by_type["photoshoot_product"].composition.composition_type,
            "photoshoot_product",
        )
        self.assertGreater(recommendation.confidence, 0)
        self.assertIn("Content recommendations are available.", result.rationale)
        self.assertFalse(result.metadata["creates_products"])
        self.assertFalse(result.metadata["creates_product_drafts"])
        self.assertTrue(result.metadata["commerce_intelligence_consumed"])

    def test_story_experience_generates_story_catalog_recommendations(self):
        service = ProductStrategyService()
        experience = SimpleNamespace(
            experience_id="story-1",
            asset_ids=(201, 202, 203),
            is_collection=True,
            experience_type=SimpleNamespace(value="STORY"),
        )

        result = service.recommend(
            content_intelligences=(
                content_record(201),
                content_record(202),
                content_record(203),
            ),
            experience_context=experience,
        )

        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in result.catalog_recommendation.recommended_products
        }
        self.assertIn("free_preview", recommendation_types)
        self.assertIn("bundle", recommendation_types)
        self.assertIn("story_product", recommendation_types)
        self.assertIn("collection", recommendation_types)
        self.assertNotIn("photoshoot_product", recommendation_types)
        story = next(
            recommendation
            for recommendation in result.recommendations
            if recommendation.recommendation_type == "story_product"
        )
        self.assertEqual(story.composition.included_asset_ids, (201, 202, 203))
        self.assertEqual(story.composition.asset_order, (201, 202, 203))
        self.assertEqual(
            story.composition.rationale,
            ("Preserve Experience ordering for story progression.",),
        )

    def test_single_experience_generates_preview_and_single_premium(self):
        service = ProductStrategyService()
        experience = SimpleNamespace(
            experience_id="single-1",
            asset_ids=(301,),
            is_collection=False,
            experience_type=SimpleNamespace(value="STANDALONE"),
        )

        result = service.recommend(
            content_intelligence=content_record(301),
            experience_context=experience,
        )

        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in result.catalog_recommendation.recommended_products
        }
        self.assertEqual(
            recommendation_types,
            {"free_preview", "single_premium"},
        )
        single = next(
            recommendation
            for recommendation in result.recommendations
            if recommendation.recommendation_type == "single_premium"
        )
        self.assertEqual(single.composition.composition_type, "single_asset_product")
        self.assertEqual(single.composition.included_asset_ids, (301,))

    def test_learning_context_is_consumed_as_evidence_only(self):
        result = ProductStrategyService().recommend(
            content_intelligence=content_record(401),
            learning_context=LearningContext(
                context_type="product_learning",
                learning_summary=LearningSummary(total_insights=1),
            ),
        )

        self.assertTrue(result.metadata["learning_context_consumed"])
        self.assertTrue(result.metadata["learning_context_evidence_only"])
        self.assertIn("learning_context", {item.reason for item in result.evidence})
        self.assertIn(
            "single_premium",
            {item.recommendation_type for item in result.recommendations},
        )

    def test_empty_context_returns_no_recommendations(self):
        result = ProductStrategyService().recommend()

        self.assertEqual(result.recommendations, ())
        self.assertIsNone(result.catalog_recommendation)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.source_type, "content")

    def test_service_imports_do_not_cross_ownership_boundaries(self):
        path = Path("app/services/product_strategy_service.py")
        tree = ast.parse(path.read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "product_catalog",
            "ai_product_drafting",
            "publishing",
            "telegram",
            "decision_engine",
            "product_repository",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module for fragment in forbidden_fragments),
                    module,
                )


if __name__ == "__main__":
    unittest.main()

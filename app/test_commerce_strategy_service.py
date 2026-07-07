import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.business_learning import LearningContext, LearningSummary
from app.services.commerce_strategy_service import CommerceStrategyService


class CommerceStrategyServiceTests(unittest.TestCase):
    def test_recommendation_consumes_existing_strategy_context(self):
        product_strategy = SimpleNamespace(
            source_type="experience",
            source_id="experience-1",
            catalog_recommendation=SimpleNamespace(),
            recommendations=(
                SimpleNamespace(recommendation_type="free_preview"),
                SimpleNamespace(recommendation_type="bundle"),
                SimpleNamespace(recommendation_type="single_premium"),
            ),
        )
        commerce_intelligence = SimpleNamespace(delivery_type="PAID")
        experience = SimpleNamespace(experience_id="experience-1")

        result = CommerceStrategyService().recommend(
            creator_intent={"content_type": "Photoshoot"},
            product_strategy_result=product_strategy,
            content_intelligences=(SimpleNamespace(asset_id=101),),
            experience_context=experience,
            commerce_intelligence=commerce_intelligence,
        )

        self.assertEqual(result.source_type, "experience")
        self.assertEqual(result.source_id, "experience-1")
        self.assertGreater(len(result.recommendations), 1)
        recommendation_types = {
            recommendation.recommendation_type
            for recommendation in result.recommendations
        }
        self.assertIn("best_teaser", recommendation_types)
        self.assertIn("best_first_offer", recommendation_types)
        self.assertIn("best_follow_up", recommendation_types)
        self.assertIn("best_upsell", recommendation_types)
        self.assertIn("cross_sell_opportunity", recommendation_types)
        self.assertIn("offer_sequencing", recommendation_types)
        self.assertIn("conversation_objective", recommendation_types)
        self.assertIn("relationship_stage", recommendation_types)
        self.assertIn("introduce_product", recommendation_types)
        self.assertIn("continue_relationship_building", recommendation_types)
        self.assertIn("delay_selling", recommendation_types)
        self.assertIn("increase_sales_pressure", recommendation_types)
        self.assertIn("customer_progression", recommendation_types)
        recommendation = result.recommendations[0]
        self.assertIsNotNone(recommendation.recommended_objective)
        self.assertIsNotNone(recommendation.customer_journey)
        self.assertIsNotNone(recommendation.customer_journey.journey_stage)
        self.assertIsNotNone(
            recommendation.customer_journey.suggested_progression
        )
        self.assertGreater(recommendation.confidence, 0)
        self.assertIn(
            "Product Strategy recommendations are available.",
            result.rationale,
        )
        self.assertFalse(result.metadata["executes_conversations"])
        self.assertFalse(result.metadata["delivers_products"])
        self.assertFalse(result.metadata["modifies_decision_engine"])
        self.assertFalse(result.metadata["modifies_publishing"])
        self.assertFalse(result.metadata["modifies_telegram"])
        self.assertFalse(result.metadata["persists_products"])
        self.assertFalse(result.metadata["new_ai_analysis"])
        self.assertTrue(result.metadata["product_strategy_consumed"])
        self.assertTrue(result.metadata["commerce_intelligence_consumed"])
        self.assertFalse(recommendation.metadata["runtime_action"])
        self.assertFalse(recommendation.metadata["telegram_specific"])
        self.assertFalse(recommendation.metadata["contains_pricing"])
        self.assertFalse(recommendation.metadata["contains_delivery_type"])
        self.assertFalse(
            recommendation.metadata["contains_publishing_readiness"]
        )
        self.assertFalse(recommendation.metadata["tracks_customer_state"])
        self.assertFalse(recommendation.metadata["contains_customer_memory"])
        self.assertFalse(
            recommendation.customer_journey.metadata["tracks_customer_state"]
        )
        self.assertFalse(
            recommendation.customer_journey.metadata["contains_customer_memory"]
        )

    def test_recommendations_are_generated_for_each_product_strategy_item(self):
        product_strategy = SimpleNamespace(
            source_type="experience",
            source_id="experience-2",
            recommendations=(
                SimpleNamespace(recommendation_type="free_preview"),
                SimpleNamespace(recommendation_type="bundle"),
            ),
        )

        result = CommerceStrategyService().recommend(
            product_strategy_result=product_strategy
        )

        grouped = {}
        for recommendation in result.recommendations:
            key = recommendation.metadata["product_recommendation_type"]
            grouped.setdefault(key, set()).add(recommendation.recommendation_type)

        self.assertIn("best_teaser", grouped["free_preview"])
        self.assertIn("best_upsell", grouped["bundle"])
        self.assertIn("offer_sequencing", grouped["free_preview"])
        self.assertIn("conversation_objective", grouped["bundle"])
        self.assertIn("relationship_stage", grouped["free_preview"])
        self.assertIn("customer_progression", grouped["bundle"])

    def test_customer_journey_recommendations_remain_generic(self):
        product_strategy = SimpleNamespace(
            source_type="experience",
            source_id="experience-3",
            recommendations=(
                SimpleNamespace(recommendation_type="free_preview"),
                SimpleNamespace(recommendation_type="single_premium"),
            ),
        )

        result = CommerceStrategyService().recommend(
            product_strategy_result=product_strategy
        )

        journeys = {
            recommendation.metadata["product_recommendation_type"]: (
                recommendation.customer_journey
            )
            for recommendation in result.recommendations
            if recommendation.recommendation_type == "relationship_stage"
        }

        self.assertEqual(
            journeys["free_preview"].journey_stage,
            "relationship_building",
        )
        self.assertEqual(
            journeys["single_premium"].journey_stage,
            "first_offer",
        )
        for journey in journeys.values():
            self.assertFalse(journey.metadata["tracks_customer_state"])
            self.assertFalse(journey.metadata["runtime_action"])

    def test_learning_context_is_consumed_as_evidence_only(self):
        product_strategy = SimpleNamespace(
            source_type="experience",
            source_id="experience-learning",
            recommendations=(SimpleNamespace(recommendation_type="free_preview"),),
        )

        result = CommerceStrategyService().recommend(
            product_strategy_result=product_strategy,
            learning_context=LearningContext(
                context_type="commerce_learning",
                learning_summary=LearningSummary(total_insights=1),
            ),
        )

        self.assertTrue(result.metadata["learning_context_consumed"])
        self.assertTrue(result.metadata["learning_context_evidence_only"])
        self.assertIn("learning_context", {item.reason for item in result.evidence})
        self.assertIn(
            "best_teaser",
            {item.recommendation_type for item in result.recommendations},
        )

    def test_empty_context_returns_no_recommendations(self):
        result = CommerceStrategyService().recommend()

        self.assertEqual(result.source_type, "commerce")
        self.assertIsNone(result.source_id)
        self.assertEqual(result.recommendations, ())
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.evidence, ())

    def test_service_imports_do_not_cross_ownership_boundaries(self):
        path = Path("app/services/commerce_strategy_service.py")
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
            "conversation_gateway",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module for fragment in forbidden_fragments)
                )


if __name__ == "__main__":
    unittest.main()

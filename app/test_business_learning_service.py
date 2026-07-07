import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.business_learning import (
    BusinessLearningReview,
    BusinessLearningReviewSummary,
    BusinessLearningSnapshot,
    BusinessOutcome,
    BusinessOutcomeType,
    BusinessPerformanceSummary,
    LearningContext,
    LearningInsight,
    LearningMetadata,
    LearningRecommendation,
    LearningSummary,
    PerformanceEvidence,
    PerformanceMetric,
    PerformanceSnapshot,
    RecommendationEvidence,
)
from app.services.business_learning_service import BusinessLearningService
from app.services.commerce_strategy_service import CommerceStrategyService
from app.services.product_strategy_service import ProductStrategyService


class BusinessLearningServiceTests(unittest.TestCase):
    def test_business_learning_models_instantiate(self):
        outcome = BusinessOutcome(
            outcome_id="outcome-1",
            outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
            timestamp="2026-07-05T12:00:00Z",
            customer_reference="customer-1",
            product_reference="product-1",
            status="purchased",
            value_cents=1999,
            provider_metadata={"provider": "provider-neutral-test"},
            evidence_metadata={"source_event": "purchase"},
            compatibility_metadata={"legacy_source": "test"},
        )
        performance = BusinessPerformanceSummary(
            total_outcomes=1,
            successful_outcomes=1,
            total_value_cents=1999,
            success_rate=1.0,
        )
        evidence = RecommendationEvidence(
            recommendation_id="recommendation-1",
            confidence=1.0,
            supporting_outcome_ids=("outcome-1",),
        )
        performance_evidence = PerformanceEvidence(
            evidence_type="product_performance_outcomes",
            outcome_ids=("outcome-1",),
            outcome_types=(BusinessOutcomeType.PRODUCT_PURCHASED.value,),
            positive_count=1,
        )
        performance_metric = PerformanceMetric(
            metric_name="Product performance",
            metric_type="product_performance",
            count=1,
            success_count=1,
            success_rate=1.0,
            confidence=0.1,
            supporting_evidence=(performance_evidence,),
        )
        insight = LearningInsight(
            insight_id="insight-1",
            insight_type="top_performer",
            subject="product_performance",
            confidence=0.1,
            supporting_metric_types=("product_performance",),
            supporting_outcome_ids=("outcome-1",),
            recommendation_evidence=(evidence,),
        )
        learning_recommendation = LearningRecommendation(
            recommendation_id="learning-1",
            recommendation_type="historical_learning_evidence",
            confidence=0.1,
            supporting_insight_ids=("insight-1",),
        )
        learning_context = LearningContext(
            context_type="product_learning",
            subject_reference="product-1",
            learning_summary=LearningSummary(total_insights=1),
            recommendation_evidence=(evidence,),
            learning_insights=(insight,),
            learning_recommendations=(learning_recommendation,),
            performance_snapshot=PerformanceSnapshot(metrics=(performance_metric,)),
        )
        review_summary = BusinessLearningReviewSummary(
            total_outcomes=1,
            total_metrics=1,
            total_insights=1,
            has_learning_history=True,
        )
        review = BusinessLearningReview(
            outcomes=(outcome,),
            performance_metrics=(performance_metric,),
            learning_insights=(insight,),
            recommendation_evidence=(evidence,),
            top_performers=(performance_metric,),
            learning_summary=LearningSummary(total_insights=1),
            review_summary=review_summary,
        )
        snapshot = BusinessLearningSnapshot(
            outcomes=(outcome,),
            performance_summary=performance,
            performance_snapshot=PerformanceSnapshot(metrics=(performance_metric,)),
            recommendation_evidence=(evidence,),
            learning_insights=(insight,),
            learning_recommendations=(learning_recommendation,),
            learning_intelligence_summary=LearningSummary(total_insights=1),
            metadata=LearningMetadata(),
        )

        self.assertEqual(snapshot.outcomes[0].outcome_id, "outcome-1")
        self.assertEqual(
            snapshot.outcomes[0].outcome_type,
            BusinessOutcomeType.PRODUCT_PURCHASED.value,
        )
        self.assertEqual(snapshot.outcomes[0].customer_reference, "customer-1")
        self.assertEqual(snapshot.performance_summary.success_rate, 1.0)
        self.assertEqual(
            snapshot.performance_snapshot.metrics[0].metric_type,
            "product_performance",
        )
        self.assertEqual(snapshot.learning_insights[0].subject, "product_performance")
        self.assertEqual(snapshot.learning_intelligence_summary.total_insights, 1)
        self.assertEqual(learning_context.context_type, "product_learning")
        self.assertTrue(review.review_summary.has_learning_history)
        self.assertTrue(snapshot.metadata.provider_neutral)
        self.assertFalse(snapshot.metadata.generates_decisions)

    def test_record_business_outcome(self):
        outcomes = BusinessLearningService().record_business_outcome(
            outcome_type=BusinessOutcomeType.PRODUCT_OFFERED,
            timestamp="2026-07-05T12:00:00Z",
            customer_reference="customer-1",
            product_reference="product-1",
            provider_metadata={"provider": "telegram"},
            evidence_metadata={"message_id": "message-1"},
            compatibility_metadata={"source": "telegram_commerce_memory"},
            outcome_id="outcome-1",
            status="offered",
        )

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(
            outcomes[0].outcome_type,
            BusinessOutcomeType.PRODUCT_OFFERED.value,
        )
        self.assertEqual(outcomes[0].timestamp, "2026-07-05T12:00:00Z")
        self.assertEqual(outcomes[0].customer_reference, "customer-1")
        self.assertEqual(outcomes[0].product_reference, "product-1")
        self.assertEqual(outcomes[0].provider_metadata["provider"], "telegram")
        self.assertEqual(outcomes[0].evidence_metadata["message_id"], "message-1")
        self.assertTrue(outcomes[0].compatibility_metadata["read_only"])

    def test_summarize_business_outcomes(self):
        service = BusinessLearningService()
        outcomes = service.record_business_outcome(
            outcome_type="PRODUCT_PURCHASED",
            customer_reference="customer-1",
            product_reference="product-1",
        )
        outcomes = service.record_business_outcome(
            outcomes,
            outcome_type="EXPERIENCE_COMPLETED",
            customer_reference="customer-1",
            experience_reference="experience-1",
        )

        summary = service.summarize_business_outcomes(outcomes)

        self.assertEqual(summary["total_outcomes"], 2)
        self.assertEqual(
            summary["outcome_type_counts"][
                BusinessOutcomeType.PRODUCT_PURCHASED.value
            ],
            1,
        )
        self.assertEqual(summary["customer_count"], 1)
        self.assertEqual(summary["product_count"], 1)
        self.assertEqual(summary["experience_count"], 1)
        self.assertFalse(summary["metadata"]["analytics_enabled"])

    def test_categorize_outcomes(self):
        service = BusinessLearningService()
        outcomes = (
            BusinessOutcome(outcome_type=BusinessOutcomeType.CTA_PRESENTED.value),
            BusinessOutcome(outcome_type=BusinessOutcomeType.CTA_CLICKED.value),
            BusinessOutcome(outcome_type=BusinessOutcomeType.CTA_CLICKED.value),
        )

        categories = service.categorize_outcomes(outcomes)

        self.assertEqual(len(categories[BusinessOutcomeType.CTA_PRESENTED.value]), 1)
        self.assertEqual(len(categories[BusinessOutcomeType.CTA_CLICKED.value]), 2)

    def test_build_outcome_snapshot(self):
        snapshot = BusinessLearningService().build_outcome_snapshot(
            outcomes=[
                {
                    "outcome_type": "FREE_ASSET_DELIVERED",
                    "customer_reference": "customer-1",
                    "product_reference": "asset-1",
                }
            ]
        )

        self.assertIsInstance(snapshot, BusinessLearningSnapshot)
        self.assertEqual(snapshot.outcome_summary["total_outcomes"], 1)
        self.assertIn(
            BusinessOutcomeType.FREE_ASSET_DELIVERED.value,
            snapshot.outcome_categories,
        )
        self.assertEqual(snapshot.performance_summary.successful_outcomes, 1)

    def test_learning_context_exposes_typed_evidence_only_contract(self):
        context = BusinessLearningService().build_product_learning_context(
            outcomes=(
                BusinessOutcome(
                    outcome_id="outcome-learning",
                    outcome_type=BusinessOutcomeType.PRODUCT_PURCHASED.value,
                    product_reference="product-learning",
                    status="purchased",
                ),
            ),
            product_reference="product-learning",
        )

        self.assertIsInstance(context, LearningContext)
        self.assertEqual(context.context_type, "product_learning")
        self.assertTrue(context.compatibility_metadata["read_only"])
        self.assertFalse(context.compatibility_metadata["generates_decisions"])
        self.assertFalse(context.compatibility_metadata["modifies_strategy"])

    def test_learning_snapshot_generation(self):
        snapshot = BusinessLearningService().build_learning_snapshot(
            outcomes=[
                {
                    "outcome_id": "outcome-1",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "status": "purchased",
                    "value_cents": 1999,
                    "strategy_source": "commerce_strategy",
                    "recommendation_id": "rec-1",
                }
            ]
        )

        self.assertIsInstance(snapshot, BusinessLearningSnapshot)
        self.assertEqual(len(snapshot.outcomes), 1)
        self.assertEqual(snapshot.performance_summary.total_outcomes, 1)
        self.assertEqual(snapshot.outcome_summary["total_outcomes"], 1)
        self.assertEqual(snapshot.recommendation_evidence[0].recommendation_id, "rec-1")
        self.assertTrue(snapshot.learning_summary["has_learning_history"])

    def test_business_performance_summary_generation(self):
        summary = BusinessLearningService().summarize_business_performance(
            (
                BusinessOutcome(
                    outcome_id="outcome-1",
                    outcome_type="purchase",
                    strategy_source="commerce_strategy",
                    status="purchased",
                    value_cents=2000,
                ),
                BusinessOutcome(
                    outcome_id="outcome-2",
                    outcome_type="offer",
                    strategy_source="product_strategy",
                    status="declined",
                ),
                BusinessOutcome(
                    outcome_id="outcome-3",
                    outcome_type="delivery",
                    strategy_source="commerce_execution",
                    status="delivered",
                ),
            )
        )

        self.assertEqual(summary.total_outcomes, 3)
        self.assertEqual(summary.successful_outcomes, 2)
        self.assertEqual(summary.failed_outcomes, 1)
        self.assertEqual(summary.total_value_cents, 2000)
        self.assertEqual(summary.outcome_type_counts["purchase"], 1)
        self.assertAlmostEqual(summary.success_rate, 2 / 3)
        self.assertTrue(summary.metadata["read_only"])

    def test_product_performance(self):
        service = BusinessLearningService()
        metric = service.calculate_product_performance(
            [
                {
                    "outcome_id": "offer-1",
                    "outcome_type": BusinessOutcomeType.PRODUCT_OFFERED.value,
                },
                {
                    "outcome_id": "purchase-1",
                    "outcome_type": BusinessOutcomeType.PRODUCT_PURCHASED.value,
                },
                {
                    "outcome_id": "decline-1",
                    "outcome_type": BusinessOutcomeType.PRODUCT_DECLINED.value,
                },
            ]
        )

        self.assertEqual(metric.metric_type, "product_performance")
        self.assertEqual(metric.count, 3)
        self.assertEqual(metric.success_count, 1)
        self.assertEqual(metric.failure_count, 1)
        self.assertEqual(metric.neutral_count, 1)
        self.assertAlmostEqual(metric.success_rate, 1 / 3)
        self.assertEqual(metric.confidence, 0.3)
        self.assertTrue(metric.compatibility_metadata["provider_neutral"])

    def test_bundle_performance(self):
        metric = BusinessLearningService().calculate_bundle_performance(
            [
                {
                    "outcome_id": "bundle-1",
                    "outcome_type": BusinessOutcomeType.BUNDLE_PURCHASED.value,
                }
            ]
        )

        self.assertEqual(metric.metric_type, "bundle_performance")
        self.assertEqual(metric.count, 1)
        self.assertEqual(metric.success_count, 1)
        self.assertEqual(metric.success_rate, 1.0)

    def test_story_performance(self):
        metric = BusinessLearningService().calculate_story_performance(
            [BusinessOutcome(outcome_type=BusinessOutcomeType.STORY_COMPLETED.value)]
        )

        self.assertEqual(metric.metric_type, "story_performance")
        self.assertEqual(metric.count, 1)
        self.assertEqual(metric.success_count, 1)

    def test_photoshoot_performance(self):
        metric = BusinessLearningService().calculate_photoshoot_performance(
            [
                BusinessOutcome(
                    outcome_type=BusinessOutcomeType.PHOTOSHOOT_PURCHASED.value
                )
            ]
        )

        self.assertEqual(metric.metric_type, "photoshoot_performance")
        self.assertEqual(metric.count, 1)
        self.assertEqual(metric.success_rate, 1.0)

    def test_experience_performance(self):
        metric = BusinessLearningService().calculate_experience_performance(
            [
                {
                    "outcome_type": BusinessOutcomeType.EXPERIENCE_COMPLETED.value,
                    "experience_reference": "experience-1",
                }
            ]
        )

        self.assertEqual(metric.metric_type, "experience_performance")
        self.assertEqual(metric.count, 1)
        self.assertEqual(metric.success_count, 1)

    def test_customer_engagement_metrics(self):
        metric = BusinessLearningService().calculate_customer_engagement(
            [
                {"outcome_type": BusinessOutcomeType.CONVERSATION_CONTINUED.value},
                {"outcome_type": BusinessOutcomeType.CONVERSATION_ENDED.value},
                {"outcome_type": BusinessOutcomeType.CTA_CLICKED.value},
                {"outcome_type": BusinessOutcomeType.FREE_ASSET_DELIVERED.value},
            ]
        )

        self.assertEqual(metric.metric_type, "customer_engagement")
        self.assertEqual(metric.count, 4)
        self.assertEqual(metric.success_count, 3)
        self.assertEqual(metric.failure_count, 1)
        self.assertAlmostEqual(metric.success_rate, 0.75)

    def test_cta_effectiveness(self):
        metric = BusinessLearningService().calculate_cta_effectiveness(
            [
                {"outcome_id": "presented-1", "outcome_type": "CTA_PRESENTED"},
                {"outcome_id": "clicked-1", "outcome_type": "CTA_CLICKED"},
            ]
        )

        self.assertEqual(metric.metric_type, "cta_effectiveness")
        self.assertEqual(metric.count, 2)
        self.assertEqual(metric.success_count, 1)
        self.assertEqual(metric.neutral_count, 1)
        self.assertEqual(
            metric.supporting_evidence[0].outcome_ids,
            ("presented-1", "clicked-1"),
        )

    def test_performance_summary_generation(self):
        service = BusinessLearningService()
        snapshot = service.build_performance_snapshot(
            outcomes=[
                {"outcome_type": "PRODUCT_OFFERED"},
                {"outcome_type": "PRODUCT_PURCHASED"},
                {"outcome_type": "CTA_PRESENTED"},
                {"outcome_type": "CTA_CLICKED"},
            ]
        )

        self.assertIsInstance(snapshot, PerformanceSnapshot)
        self.assertEqual(snapshot.summary["total_metrics"], 10)
        self.assertEqual(snapshot.summary["total_observations"], 7)
        self.assertIn("cta_effectiveness", snapshot.summary["metric_types"])
        self.assertFalse(snapshot.summary["metadata"]["generates_recommendations"])

    def test_confidence_calculation(self):
        service = BusinessLearningService()

        self.assertEqual(service.calculate_cta_effectiveness().confidence, 0.0)
        self.assertEqual(
            service.calculate_cta_effectiveness(
                [{"outcome_type": "CTA_CLICKED"} for _ in range(12)]
            ).confidence,
            1.0,
        )

    def test_existing_outcome_compatibility_preserved(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[
                BusinessOutcome(
                    outcome_type="purchase",
                    status="purchased",
                    value_cents=2000,
                    strategy_source="commerce_strategy",
                )
            ],
        )

        self.assertEqual(snapshot.performance_summary.total_outcomes, 1)
        self.assertEqual(snapshot.performance_summary.outcome_type_counts["purchase"], 1)
        self.assertEqual(snapshot.learning_summary["total_value_cents"], 2000)
        self.assertIsInstance(snapshot.performance_snapshot, PerformanceSnapshot)

    def test_learning_insight_generation(self):
        service = BusinessLearningService()
        insights = service.generate_learning_insights(
            outcomes=[
                {"outcome_id": "bundle-1", "outcome_type": "BUNDLE_PURCHASED"},
                {"outcome_id": "offer-1", "outcome_type": "PRODUCT_OFFERED"},
                {"outcome_id": "decline-1", "outcome_type": "PRODUCT_DECLINED"},
            ]
        )

        self.assertTrue(any(item.insight_type == "top_performer" for item in insights))
        self.assertTrue(
            any(item.insight_type == "underperformer" for item in insights)
        )
        self.assertTrue(all(item.compatibility_metadata["provider_neutral"] for item in insights))
        self.assertTrue(
            all(item.metadata["automatic_strategy_change"] is False for item in insights)
        )

    def test_learning_summaries(self):
        service = BusinessLearningService()
        insights = (
            LearningInsight(
                insight_id="top-1",
                insight_type="top_performer",
                confidence=0.8,
            ),
            LearningInsight(
                insight_id="under-1",
                insight_type="underperformer",
                confidence=0.4,
            ),
        )
        recommendations = (
            LearningRecommendation(
                recommendation_id="learning-1",
                recommendation_type="historical_learning_evidence",
            ),
        )

        summary = service.generate_learning_summary(
            learning_insights=insights,
            learning_recommendations=recommendations,
        )

        self.assertEqual(summary.total_insights, 2)
        self.assertEqual(summary.total_recommendations, 1)
        self.assertEqual(summary.top_performer_count, 1)
        self.assertEqual(summary.underperformer_count, 1)
        self.assertAlmostEqual(summary.average_confidence, 0.6)
        self.assertTrue(summary.metadata["descriptive_only"])

    def test_learning_recommendation_evidence(self):
        service = BusinessLearningService()
        evidence = service.build_recommendation_evidence(
            outcomes=[
                {
                    "outcome_id": "outcome-1",
                    "recommendation_id": "rec-1",
                    "status": "purchased",
                }
            ]
        )
        recommendations = service.generate_recommendation_evidence(
            learning_insights=(
                LearningInsight(
                    insight_id="insight-1",
                    insight_type="top_performer",
                    confidence=0.7,
                ),
            ),
            recommendation_evidence=evidence,
        )

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(
            recommendations[0].recommendation_type,
            "historical_learning_evidence",
        )
        self.assertEqual(recommendations[0].supporting_insight_ids, ("insight-1",))
        self.assertFalse(recommendations[0].metadata["generates_recommendations"])

    def test_top_performer_identification(self):
        metrics = (
            PerformanceMetric(
                metric_name="Bundle performance",
                metric_type="bundle_performance",
                count=4,
                success_count=4,
                success_rate=1.0,
                confidence=0.4,
            ),
            PerformanceMetric(
                metric_name="Offer effectiveness",
                metric_type="offer_effectiveness",
                count=4,
                success_count=1,
                success_rate=0.25,
                confidence=0.4,
            ),
        )

        top = BusinessLearningService().identify_top_performers(metrics)

        self.assertEqual(len(top), 1)
        self.assertEqual(top[0].metric_type, "bundle_performance")

    def test_underperformer_identification(self):
        metrics = (
            PerformanceMetric(
                metric_name="CTA effectiveness",
                metric_type="cta_effectiveness",
                count=4,
                success_count=3,
                success_rate=0.75,
                confidence=0.4,
            ),
            PerformanceMetric(
                metric_name="Product performance",
                metric_type="product_performance",
                count=4,
                success_count=1,
                failure_count=2,
                success_rate=0.25,
                confidence=0.4,
            ),
        )

        underperformers = BusinessLearningService().identify_underperformers(metrics)

        self.assertEqual(len(underperformers), 1)
        self.assertEqual(underperformers[0].metric_type, "product_performance")

    def test_learning_confidence_calculation(self):
        confidence = BusinessLearningService().calculate_learning_confidence(
            metrics=(
                PerformanceMetric(
                    metric_name="CTA effectiveness",
                    metric_type="cta_effectiveness",
                    confidence=0.4,
                ),
            ),
            insights=(LearningInsight(insight_type="top_performer", confidence=0.8),),
        )

        self.assertAlmostEqual(confidence, 0.6)

    def test_historical_comparison(self):
        ranked = BusinessLearningService().rank_performance(
            (
                PerformanceMetric(
                    metric_name="Offer effectiveness",
                    metric_type="offer_effectiveness",
                    success_rate=0.25,
                    confidence=0.8,
                    count=4,
                ),
                PerformanceMetric(
                    metric_name="Bundle performance",
                    metric_type="bundle_performance",
                    success_rate=0.75,
                    confidence=0.3,
                    count=4,
                ),
            )
        )

        self.assertEqual(ranked[0].metric_type, "bundle_performance")
        self.assertEqual(ranked[1].metric_type, "offer_effectiveness")

    def test_existing_performance_intelligence_preserved(self):
        snapshot = BusinessLearningService().build_learning_snapshot(
            outcomes=[
                {"outcome_type": "PRODUCT_PURCHASED"},
                {"outcome_type": "CTA_CLICKED"},
            ]
        )

        self.assertIsInstance(snapshot.performance_snapshot, PerformanceSnapshot)
        self.assertEqual(snapshot.performance_snapshot.summary["total_metrics"], 10)
        self.assertIsInstance(snapshot.learning_intelligence_summary, LearningSummary)

    def test_product_learning_context(self):
        context = BusinessLearningService().build_product_learning_context(
            product_reference="product-1",
            outcomes=[
                {
                    "outcome_id": "purchase-1",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "product_reference": "product-1",
                    "recommendation_id": "rec-1",
                },
                {
                    "outcome_id": "purchase-2",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "product_reference": "product-2",
                },
            ],
        )

        self.assertIsInstance(context, LearningContext)
        self.assertEqual(context.context_type, "product_learning")
        self.assertEqual(context.subject_reference, "product-1")
        self.assertEqual(context.performance_snapshot.summary["total_observations"], 2)
        self.assertTrue(context.compatibility_metadata["read_only"])

    def test_commerce_learning_context(self):
        context = BusinessLearningService().build_commerce_learning_context(
            outcomes=[
                {"outcome_type": "PRODUCT_OFFERED"},
                {"outcome_type": "PRODUCT_DECLINED"},
                {"outcome_type": "CTA_CLICKED"},
            ]
        )

        self.assertEqual(context.context_type, "commerce_learning")
        self.assertGreaterEqual(context.learning_summary.total_insights, 1)
        self.assertFalse(context.compatibility_metadata["executes_commerce"])
        self.assertFalse(context.compatibility_metadata["generates_decisions"])

    def test_customer_learning_context(self):
        context = BusinessLearningService().build_customer_learning_context(
            customer_reference="customer-1",
            outcomes=[
                {
                    "outcome_type": "CTA_CLICKED",
                    "customer_reference": "customer-1",
                },
                {
                    "outcome_type": "CONVERSATION_ENDED",
                    "customer_reference": "customer-2",
                },
            ],
        )

        self.assertEqual(context.context_type, "customer_learning")
        self.assertEqual(context.subject_reference, "customer-1")
        self.assertTrue(context.compatibility_metadata["provider_neutral"])
        self.assertEqual(context.performance_snapshot.summary["total_observations"], 2)

    def test_unified_learning_snapshot(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[{"outcome_type": "BUNDLE_PURCHASED"}],
            metadata={"phase": "2.7.5"},
        )
        context = service.build_learning_context(snapshot=snapshot)

        self.assertEqual(context.context_type, "unified_learning")
        self.assertIs(context.performance_snapshot, snapshot.performance_snapshot)
        self.assertEqual(context.metadata["consumer_context"], "unified_learning")
        self.assertEqual(snapshot.metadata.metadata["phase"], "2.7.5")

    def test_recommendation_evidence_context(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[
                {
                    "outcome_id": "outcome-1",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "recommendation_id": "rec-1",
                    "strategy_source": "commerce_strategy",
                },
                {
                    "outcome_id": "outcome-2",
                    "outcome_type": "PRODUCT_DECLINED",
                    "recommendation_id": "rec-1",
                    "strategy_source": "commerce_strategy",
                },
            ]
        )
        summary = service.summarize_recommendation_evidence(
            snapshot.recommendation_evidence
        )

        self.assertEqual(summary["total_evidence"], 1)
        self.assertEqual(summary["positive_signal_count"], 1)
        self.assertEqual(summary["negative_signal_count"], 1)
        self.assertEqual(summary["recommendation_ids"], ("rec-1",))
        self.assertTrue(summary["metadata"]["evidence_only"])

    def test_enrich_learning_snapshot(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[{"outcome_id": "one", "outcome_type": "PRODUCT_OFFERED"}]
        )
        enriched = service.enrich_learning_snapshot(
            snapshot,
            outcomes=[{"outcome_id": "two", "outcome_type": "PRODUCT_PURCHASED"}],
            metadata={"integration": "business_learning"},
        )

        self.assertEqual(len(enriched.outcomes), 2)
        self.assertEqual(
            enriched.metadata.metadata["enriched_by"],
            "BusinessLearningService",
        )
        self.assertEqual(enriched.metadata.metadata["integration"], "business_learning")

    def test_existing_learning_intelligence_preserved(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[
                {"outcome_type": "PRODUCT_PURCHASED"},
                {"outcome_type": "PRODUCT_DECLINED"},
            ]
        )

        self.assertIsInstance(snapshot.learning_intelligence_summary, LearningSummary)
        self.assertIsInstance(snapshot.learning_insights, tuple)
        self.assertIsInstance(snapshot.learning_recommendations, tuple)

    def test_existing_product_strategy_preserved(self):
        result = ProductStrategyService().recommend()

        self.assertEqual(result.recommendations, ())
        self.assertEqual(result.confidence, 0.0)
        self.assertFalse(result.metadata["commerce_intelligence_consumed"])

    def test_existing_commerce_strategy_preserved(self):
        result = CommerceStrategyService().recommend()

        self.assertEqual(result.recommendations, ())
        self.assertEqual(result.confidence, 0.0)
        self.assertFalse(result.metadata["commerce_intelligence_consumed"])

    def test_business_review_generation(self):
        review = BusinessLearningService().build_business_review(
            outcomes=[
                {
                    "outcome_id": "purchase-1",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "recommendation_id": "rec-1",
                },
                {
                    "outcome_id": "decline-1",
                    "outcome_type": "PRODUCT_DECLINED",
                    "recommendation_id": "rec-1",
                },
            ],
            metadata={"surface": "creator_workspace"},
        )

        self.assertIsInstance(review, BusinessLearningReview)
        self.assertEqual(len(review.outcomes), 2)
        self.assertTrue(review.compatibility_metadata["presentation_only"])
        self.assertTrue(review.compatibility_metadata["read_only"])
        self.assertEqual(review.metadata["surface"], "creator_workspace")

    def test_business_review_summary(self):
        service = BusinessLearningService()
        review = service.build_business_review(
            outcomes=[
                {"outcome_type": "CTA_PRESENTED"},
                {"outcome_type": "CTA_CLICKED"},
            ]
        )
        summary = service.build_business_review_summary(review)

        self.assertIsInstance(summary, BusinessLearningReviewSummary)
        self.assertEqual(summary.total_outcomes, 2)
        self.assertEqual(summary.total_metrics, 10)
        self.assertTrue(summary.has_learning_history)
        self.assertTrue(summary.metadata["presentation_only"])

    def test_business_review_performance_visibility(self):
        review = BusinessLearningService().build_business_review(
            outcomes=[
                {"outcome_type": "BUNDLE_PURCHASED"},
                {"outcome_type": "PRODUCT_DECLINED"},
            ]
        )

        self.assertTrue(review.performance_metrics)
        self.assertTrue(review.top_performers)
        self.assertTrue(review.underperformers)
        self.assertIn("ranked_performance", review.historical_comparisons)

    def test_business_review_learning_visibility(self):
        review = BusinessLearningService().build_business_review(
            outcomes=[
                {"outcome_type": "BUNDLE_PURCHASED"},
                {"outcome_type": "PRODUCT_DECLINED"},
            ]
        )

        self.assertTrue(review.learning_insights)
        self.assertIsInstance(review.learning_summary, LearningSummary)
        self.assertEqual(
            review.review_summary.total_insights,
            len(review.learning_insights),
        )

    def test_business_review_recommendation_evidence_visibility(self):
        review = BusinessLearningService().build_business_review(
            outcomes=[
                {
                    "outcome_id": "outcome-1",
                    "outcome_type": "PRODUCT_PURCHASED",
                    "recommendation_id": "rec-1",
                }
            ]
        )

        self.assertEqual(len(review.recommendation_evidence), 1)
        self.assertEqual(review.recommendation_evidence[0].recommendation_id, "rec-1")
        self.assertEqual(review.review_summary.recommendation_evidence_count, 1)

    def test_business_review_empty_history_handling(self):
        service = BusinessLearningService()
        review = service.build_business_review()
        activity = service.summarize_learning_activity()

        self.assertEqual(review.outcomes, ())
        self.assertEqual(review.review_summary.total_outcomes, 0)
        self.assertFalse(review.review_summary.has_learning_history)
        self.assertFalse(activity["has_learning_history"])
        self.assertTrue(activity["metadata"]["read_only"])

    def test_business_review_preserves_learning_intelligence(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot(
            outcomes=[
                {"outcome_type": "BUNDLE_PURCHASED"},
                {"outcome_type": "PRODUCT_DECLINED"},
            ]
        )
        review = service.build_business_review(snapshot)

        self.assertEqual(review.learning_insights, snapshot.learning_insights)
        self.assertEqual(
            review.learning_summary,
            snapshot.learning_intelligence_summary,
        )
        self.assertEqual(
            review.review_summary.total_insights,
            snapshot.learning_intelligence_summary.total_insights,
        )

    def test_recommendation_evidence_generation(self):
        evidence = BusinessLearningService().build_recommendation_evidence(
            outcomes=[
                {
                    "outcome_id": "outcome-1",
                    "recommendation_id": "rec-1",
                    "strategy_source": "commerce_strategy",
                    "status": "purchased",
                },
                {
                    "outcome_id": "outcome-2",
                    "recommendation_id": "rec-1",
                    "strategy_source": "commerce_strategy",
                    "status": "declined",
                },
            ]
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].recommendation_id, "rec-1")
        self.assertEqual(evidence[0].positive_signal_count, 1)
        self.assertEqual(evidence[0].negative_signal_count, 1)
        self.assertEqual(evidence[0].confidence, 0.5)
        self.assertFalse(evidence[0].metadata["generates_recommendations"])

    def test_empty_history_handling(self):
        service = BusinessLearningService()
        snapshot = service.build_learning_snapshot()
        summary = service.summarize_business_performance()
        evidence = service.build_recommendation_evidence(
            recommendation_context=SimpleNamespace(
                recommendation_id="future-rec",
                strategy_source="commerce_strategy",
            )
        )

        self.assertEqual(snapshot.outcomes, ())
        self.assertFalse(snapshot.learning_summary["has_learning_history"])
        self.assertEqual(summary.total_outcomes, 0)
        self.assertEqual(summary.success_rate, 0.0)
        self.assertEqual(evidence[0].recommendation_id, "future-rec")
        self.assertEqual(evidence[0].rationale, ("No historical outcomes available yet.",))

    def test_existing_architecture_remains_unchanged(self):
        tree = ast.parse(Path("app/services/business_learning_service.py").read_text())
        imports = []
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    calls.append(node.func.attr)

        forbidden_imports = (
            "telegram",
            "fanvue",
            "decision_engine",
            "product_strategy",
            "commerce_strategy",
            "customer_intelligence",
            "commerce_execution",
            "publishing",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(any(fragment in module for fragment in forbidden_imports))
        self.assertNotIn("execute", calls)


if __name__ == "__main__":
    unittest.main()

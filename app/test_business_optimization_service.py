from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.models.business_optimization import (
    BusinessOpportunityCategory,
    BusinessOpportunityImpact,
    BusinessPerformanceHealth,
    BusinessPerformanceTrend,
    BusinessRecommendationCategory,
    BusinessRecommendationPriority,
    BusinessStrategyHealth,
    BusinessOptimizationHealth,
    BusinessOptimizationPriority,
    BusinessOptimizationSnapshot,
)
from app.services.business_optimization_service import BusinessOptimizationService


class BusinessOptimizationServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BusinessOptimizationService()

    def test_snapshot_can_be_created_with_minimal_data(self) -> None:
        snapshot = self.service.build_snapshot()

        self.assertIsInstance(snapshot, BusinessOptimizationSnapshot)
        self.assertEqual(snapshot.health, BusinessOptimizationHealth.UNKNOWN)
        self.assertEqual(snapshot.revenue_readiness, "unknown")
        self.assertEqual(
            snapshot.next_recommended_business_action,
            "Gather business optimization inputs",
        )
        self.assertTrue(snapshot.compatibility["read_only"])
        self.assertTrue(snapshot.compatibility["provider_neutral"])
        self.assertTrue(snapshot.compatibility["aggregation_only"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])

    def test_business_health_is_derived_deterministically(self) -> None:
        ready_context = self._ready_context()

        first = self.service.build_snapshot(**ready_context)
        second = self.service.build_snapshot(**ready_context)

        self.assertEqual(first.health, BusinessOptimizationHealth.HEALTHY)
        self.assertEqual(first.health, second.health)
        self.assertEqual(first.revenue_readiness, "ready")
        self.assertEqual(first.performance_health, BusinessPerformanceHealth.HEALTHY)

        blocked = self.service.build_snapshot(
            **{
                **ready_context,
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="AT_RISK",
                    value_tier="DORMANT",
                    retention_opportunities=(SimpleNamespace(),),
                    growth_opportunities=(),
                ),
                "publishing_summary": {"failed_count": 1},
            }
        )

        self.assertEqual(blocked.health, BusinessOptimizationHealth.AT_RISK)
        self.assertEqual(blocked.revenue_readiness, "blocked")
        self.assertEqual(blocked.performance_health, BusinessPerformanceHealth.AT_RISK)

    def test_opportunities_aggregate_correctly(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"waiting_media_link_count": 1},
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="HEALTHY",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(SimpleNamespace(),),
                ),
            },
        )

        opportunity_types = {item.opportunity_type for item in snapshot.opportunities}

        self.assertIn("publishing", opportunity_types)
        self.assertIn("customer_growth", opportunity_types)
        self.assertIn("customer_retention", opportunity_types)
        self.assertIn("product_strategy", opportunity_types)
        self.assertIn("commerce_strategy", opportunity_types)

    def test_recommendations_remain_advisory_only(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertGreaterEqual(len(snapshot.recommendations), 1)
        for recommendation in snapshot.recommendations:
            self.assertTrue(recommendation.metadata["read_only"])
            self.assertTrue(recommendation.metadata["aggregation_only"])
            self.assertTrue(recommendation.metadata["advisory_only"])

        self.assertFalse(snapshot.compatibility["modifies_product_business"])
        self.assertFalse(snapshot.compatibility["modifies_customer_business"])
        self.assertFalse(snapshot.compatibility["modifies_business_learning"])
        self.assertFalse(snapshot.compatibility["modifies_product_strategy"])
        self.assertFalse(snapshot.compatibility["modifies_commerce_strategy"])
        self.assertFalse(snapshot.compatibility["modifies_publishing"])
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])

    def test_missing_upstream_services_do_not_break_snapshot_generation(self) -> None:
        service = BusinessOptimizationService(
            product_business_service=None,
            telegram_business_service=None,
            customer_business_service=None,
            product_strategy_service=None,
            commerce_strategy_service=None,
            business_learning_service=None,
            publishing_service=None,
        )

        snapshot = service.build_snapshot()

        self.assertEqual(snapshot.health, BusinessOptimizationHealth.UNKNOWN)
        self.assertEqual(snapshot.product_business_summary["available"], False)
        self.assertEqual(snapshot.telegram_business_summary["available"], False)
        self.assertEqual(snapshot.customer_business_summary["available"], False)
        self.assertEqual(snapshot.summary.opportunity_count, 1)

    def test_business_optimization_does_not_mutate_upstream_domain_objects(self) -> None:
        product_snapshot = SimpleNamespace(
            product_health="HEALTHY",
            next_recommended_business_action="Review Product Business",
            markers=["original"],
        )
        customer_snapshot = {
            "customer_health": "HEALTHY",
            "value_tier": "ENGAGED",
            "growth_opportunities": [],
            "retention_opportunities": [],
            "next_recommended_action": "Continue relationship",
        }
        original_product_markers = list(product_snapshot.markers)
        original_customer = dict(customer_snapshot)

        self.service.build_snapshot(
            product_business_snapshot=product_snapshot,
            customer_business_snapshot=customer_snapshot,
        )

        self.assertEqual(product_snapshot.markers, original_product_markers)
        self.assertEqual(customer_snapshot, original_customer)

    def test_existing_architecture_remains_provider_neutral(self) -> None:
        snapshot = self.service.build_snapshot(
            telegram_business_snapshot=SimpleNamespace(
                provider="telegram",
                business_health="HEALTHY",
                next_recommended_business_action="Review Telegram Business",
            ),
            publishing_summary={"queue_count": 1, "ready_count": 1},
        )

        self.assertTrue(snapshot.metadata["provider_neutral"])
        self.assertTrue(snapshot.metadata["read_only"])
        self.assertEqual(
            snapshot.compatibility["publishing_owner"],
            "PublishingService",
        )
        self.assertEqual(
            snapshot.compatibility["telegram_business_owner"],
            "TelegramBusinessService",
        )
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])

    def test_build_summary_returns_snapshot_summary(self) -> None:
        summary = self.service.build_summary(**self._ready_context())

        self.assertEqual(summary.health, BusinessOptimizationHealth.HEALTHY)
        self.assertEqual(summary.revenue_readiness, "ready")
        self.assertGreaterEqual(summary.recommendation_count, 1)

    def test_performance_summary_generation(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertEqual(snapshot.performance_summary.health, snapshot.performance_health)
        self.assertEqual(snapshot.performance_summary.trend, snapshot.performance_trend)
        self.assertEqual(
            snapshot.performance_summary.signal_count,
            len(snapshot.performance_signals),
        )
        self.assertEqual(snapshot.product_performance_summary["status"], "performing")
        self.assertEqual(snapshot.customer_performance_summary["status"], "active")
        self.assertEqual(snapshot.commerce_performance_summary["status"], "ready")
        self.assertEqual(snapshot.publishing_performance_summary["status"], "ready")
        self.assertGreater(snapshot.performance_confidence, 0.0)

    def test_performance_health_derivation(self) -> None:
        needs_attention = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "product_business_snapshot": SimpleNamespace(
                    product_health="NEEDS_ATTENTION",
                    next_recommended_business_action="Review Product",
                ),
            }
        )
        blocked = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"failed_count": 1},
            }
        )

        self.assertEqual(
            needs_attention.performance_health,
            BusinessPerformanceHealth.NEEDS_ATTENTION,
        )
        self.assertEqual(blocked.performance_health, BusinessPerformanceHealth.AT_RISK)

    def test_performance_trend_generation(self) -> None:
        improving = self.service.build_snapshot(**self._ready_context())
        mixed = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="AT_RISK",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(SimpleNamespace(),),
                    next_recommended_action="Review Customer",
                ),
            }
        )
        unknown = self.service.build_snapshot()

        self.assertEqual(improving.performance_trend, BusinessPerformanceTrend.IMPROVING)
        self.assertEqual(mixed.performance_trend, BusinessPerformanceTrend.MIXED)
        self.assertEqual(unknown.performance_trend, BusinessPerformanceTrend.UNKNOWN)

    def test_performance_recommendation_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"waiting_media_link_count": 1},
            }
        )

        actions = {
            recommendation.recommended_next_action
            for recommendation in snapshot.performance_summary.recommendations
        }

        self.assertIn("Improve publishing readiness", actions)
        for recommendation in snapshot.performance_summary.recommendations:
            self.assertTrue(recommendation.metadata["read_only"])
            self.assertTrue(recommendation.metadata["aggregation_only"])
            self.assertTrue(recommendation.metadata["advisory_only"])
            self.assertTrue(recommendation.metadata["provider_neutral"])

    def test_performance_handles_missing_upstreams(self) -> None:
        snapshot = self.service.build_snapshot()

        self.assertEqual(snapshot.performance_health, BusinessPerformanceHealth.UNKNOWN)
        self.assertEqual(snapshot.performance_trend, BusinessPerformanceTrend.UNKNOWN)
        self.assertEqual(snapshot.performance_confidence, 0.2)
        self.assertEqual(
            snapshot.performance_summary.next_recommended_performance_action,
            "Gather performance inputs",
        )

    def test_performance_does_not_mutate_upstream_domain_objects(self) -> None:
        product_snapshot = SimpleNamespace(
            product_health="HEALTHY",
            next_recommended_business_action="Review Product Business",
            details={"tags": ["original"]},
        )
        product_strategy = SimpleNamespace(
            recommendations=[SimpleNamespace(recommendation_type="RECOMMEND_BUNDLE")],
            confidence=0.6,
        )
        original_details = {"tags": list(product_snapshot.details["tags"])}
        original_recommendations = list(product_strategy.recommendations)

        self.service.build_snapshot(
            product_business_snapshot=product_snapshot,
            product_strategy_result=product_strategy,
        )

        self.assertEqual(product_snapshot.details, original_details)
        self.assertEqual(product_strategy.recommendations, original_recommendations)

    def test_performance_provider_neutrality_preserved(self) -> None:
        snapshot = self.service.build_snapshot(
            telegram_business_snapshot=SimpleNamespace(
                provider="telegram",
                business_health="HEALTHY",
                next_recommended_business_action="Review Telegram Business",
            ),
            publishing_summary={"queue_count": 1, "ready_count": 1},
        )

        self.assertTrue(snapshot.metadata["provider_neutral"])
        self.assertTrue(snapshot.performance_summary.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])
        self.assertFalse(snapshot.compatibility["modifies_publishing"])

    def test_strategy_summary_generation(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertEqual(snapshot.strategy_summary.health, snapshot.strategy_health)
        self.assertEqual(
            snapshot.strategy_summary.signal_count,
            len(snapshot.strategy_signals),
        )
        self.assertEqual(
            snapshot.strategy_summary.opportunity_count,
            len(snapshot.strategy_opportunities),
        )
        self.assertEqual(
            snapshot.strategy_summary.recommended_strategy_actions,
            snapshot.recommended_strategy_actions,
        )
        self.assertGreater(snapshot.strategy_confidence, 0.0)

    def test_strategy_health_derivation(self) -> None:
        healthy = self.service.build_snapshot(**self._ready_context())
        needs_attention = self.service.build_snapshot(
            product_business_snapshot=SimpleNamespace(product_health="HEALTHY"),
            customer_business_snapshot=SimpleNamespace(
                customer_health="HEALTHY",
                value_tier="BUYER",
                growth_opportunities=(),
                retention_opportunities=(),
            ),
        )
        blocked = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"failed_count": 1},
            }
        )

        self.assertEqual(healthy.strategy_health, BusinessStrategyHealth.HEALTHY)
        self.assertEqual(
            needs_attention.strategy_health,
            BusinessStrategyHealth.NEEDS_ATTENTION,
        )
        self.assertEqual(blocked.strategy_health, BusinessStrategyHealth.AT_RISK)

    def test_strategy_opportunity_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="HEALTHY",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(),
                    next_recommended_action="Introduce next Experience",
                ),
                "publishing_summary": {"waiting_media_link_count": 1},
            }
        )

        opportunity_types = {
            opportunity.opportunity_type
            for opportunity in snapshot.strategy_opportunities
        }

        self.assertIn("product_strategy_available", opportunity_types)
        self.assertIn("commerce_strategy_available", opportunity_types)
        self.assertIn("experience_strategy", opportunity_types)
        self.assertIn("publishing_strategy", opportunity_types)

    def test_strategy_recommendation_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "product_strategy_result": SimpleNamespace(
                    recommendations=(
                        SimpleNamespace(recommendation_type="RECOMMEND_BUNDLE"),
                        SimpleNamespace(recommendation_type="RECOMMEND_STORY"),
                    ),
                    confidence=0.8,
                ),
                "commerce_strategy_result": SimpleNamespace(
                    recommendations=(
                        SimpleNamespace(recommended_objective="Offer FREE Preview"),
                        SimpleNamespace(recommended_objective="Offer Story Bundle"),
                    ),
                    confidence=0.78,
                ),
            }
        )

        actions = set(snapshot.recommended_strategy_actions)

        self.assertIn("Improve FREE preview strategy", actions)
        self.assertIn("Improve Bundle strategy", actions)
        self.assertIn("Improve Story strategy", actions)
        for recommendation in snapshot.strategy_summary.recommendations:
            self.assertTrue(recommendation.metadata["read_only"])
            self.assertTrue(recommendation.metadata["aggregation_only"])
            self.assertTrue(recommendation.metadata["advisory_only"])
            self.assertTrue(recommendation.metadata["provider_neutral"])

    def test_strategy_handles_missing_upstreams(self) -> None:
        snapshot = self.service.build_snapshot()

        self.assertEqual(snapshot.strategy_health, BusinessStrategyHealth.OPPORTUNITY)
        self.assertEqual(snapshot.strategy_confidence, 0.2)
        self.assertEqual(snapshot.recommended_strategy_actions, ("Gather strategy inputs",))
        self.assertEqual(snapshot.strategy_summary.recommendation_count, 1)

    def test_strategy_does_not_mutate_upstream_domain_objects(self) -> None:
        commerce_strategy = SimpleNamespace(
            recommendations=[SimpleNamespace(recommended_objective="Offer Bundle")],
            confidence=0.7,
        )
        customer_snapshot = {
            "customer_health": "HEALTHY",
            "value_tier": "BUYER",
            "growth_opportunities": [],
            "retention_opportunities": [],
            "next_recommended_action": "Continue Journey",
        }
        original_recommendations = list(commerce_strategy.recommendations)
        original_customer = dict(customer_snapshot)

        self.service.build_snapshot(
            commerce_strategy_result=commerce_strategy,
            customer_business_snapshot=customer_snapshot,
        )

        self.assertEqual(commerce_strategy.recommendations, original_recommendations)
        self.assertEqual(customer_snapshot, original_customer)

    def test_strategy_provider_neutrality_preserved(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertTrue(snapshot.metadata["provider_neutral"])
        self.assertTrue(snapshot.strategy_summary.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["modifies_product_strategy"])
        self.assertFalse(snapshot.compatibility["modifies_commerce_strategy"])
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])

    def test_opportunity_summary_generation(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertEqual(
            snapshot.opportunity_summary.opportunity_count,
            len(snapshot.opportunity_signals),
        )
        self.assertEqual(
            snapshot.opportunity_summary.recommended_opportunity_actions,
            snapshot.recommended_opportunity_actions,
        )
        self.assertGreater(snapshot.opportunity_confidence, 0.0)
        self.assertGreaterEqual(snapshot.opportunity_summary.recommendation_count, 1)

    def test_opportunity_category_derivation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"waiting_media_link_count": 1},
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="HEALTHY",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(SimpleNamespace(),),
                    next_recommended_action="Offer FREE Preview Bundle",
                ),
            }
        )

        self.assertIn(BusinessOpportunityCategory.REVENUE, snapshot.opportunity_categories)
        self.assertIn(BusinessOpportunityCategory.CUSTOMER, snapshot.opportunity_categories)
        self.assertIn(BusinessOpportunityCategory.PUBLISHING, snapshot.opportunity_categories)
        self.assertIn(BusinessOpportunityCategory.STRATEGY, snapshot.opportunity_categories)

    def test_high_impact_opportunity_detection(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"failed_count": 1},
            }
        )

        impacts = {signal.impact for signal in snapshot.high_impact_opportunities}

        self.assertIn(BusinessOpportunityImpact.CRITICAL, impacts)
        self.assertGreaterEqual(snapshot.opportunity_summary.high_impact_count, 1)

    def test_revenue_opportunity_detection(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        revenue_types = {
            signal.opportunity_type for signal in snapshot.revenue_opportunities
        }

        self.assertIn("missing_bundles", revenue_types)
        self.assertIn("revenue_readiness", revenue_types)

    def test_customer_opportunity_detection(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="AT_RISK",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(SimpleNamespace(),),
                    next_recommended_action="Re-engage customer",
                ),
            }
        )

        customer_types = {
            signal.opportunity_type for signal in snapshot.customer_opportunities
        }

        self.assertIn("customer_growth", customer_types)
        self.assertIn("customer_retention", customer_types)
        self.assertIn("vip_development", customer_types)

    def test_product_opportunity_detection(self) -> None:
        missing = self.service.build_snapshot()
        refresh = self.service.build_snapshot(
            product_business_snapshot=SimpleNamespace(product_health="NEEDS_ATTENTION")
        )

        self.assertIn(
            "missing_products",
            {signal.opportunity_type for signal in missing.product_opportunities},
        )
        self.assertIn(
            "product_refresh",
            {signal.opportunity_type for signal in refresh.product_opportunities},
        )

    def test_publishing_opportunity_detection(self) -> None:
        snapshot = self.service.build_snapshot(
            publishing_summary={"waiting_media_link_count": 1}
        )

        self.assertEqual(len(snapshot.publishing_opportunities), 1)
        self.assertEqual(
            snapshot.publishing_opportunities[0].recommended_action,
            "Complete Media Link",
        )

    def test_strategy_opportunity_signal_detection(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertGreaterEqual(len(snapshot.strategy_opportunity_signals), 1)
        self.assertIn(
            "strategy_improvement",
            {
                signal.opportunity_type
                for signal in snapshot.strategy_opportunity_signals
            },
        )

    def test_opportunity_recommendation_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"waiting_media_link_count": 1},
            }
        )

        actions = set(snapshot.recommended_opportunity_actions)

        self.assertIn("Complete Media Link", actions)
        self.assertIn("Add Bundle", actions)
        for recommendation in snapshot.opportunity_summary.recommendations:
            self.assertTrue(recommendation.metadata["read_only"])
            self.assertTrue(recommendation.metadata["aggregation_only"])
            self.assertTrue(recommendation.metadata["advisory_only"])
            self.assertTrue(recommendation.metadata["provider_neutral"])

    def test_opportunity_handles_missing_upstreams(self) -> None:
        snapshot = self.service.build_snapshot()

        self.assertGreaterEqual(snapshot.opportunity_summary.opportunity_count, 1)
        self.assertIn(
            "Create missing Product",
            snapshot.recommended_opportunity_actions,
        )
        self.assertGreaterEqual(snapshot.opportunity_confidence, 0.0)

    def test_opportunity_does_not_mutate_upstream_domain_objects(self) -> None:
        product_strategy = SimpleNamespace(
            recommendations=[SimpleNamespace(recommendation_type="RECOMMEND_BUNDLE")],
            confidence=0.6,
        )
        publishing = {"waiting_media_link_count": 1, "markers": ["original"]}
        original_recommendations = list(product_strategy.recommendations)
        original_publishing = {
            "waiting_media_link_count": 1,
            "markers": list(publishing["markers"]),
        }

        self.service.build_snapshot(
            product_strategy_result=product_strategy,
            publishing_summary=publishing,
        )

        self.assertEqual(product_strategy.recommendations, original_recommendations)
        self.assertEqual(publishing, original_publishing)

    def test_opportunity_provider_neutrality_preserved(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertTrue(snapshot.metadata["provider_neutral"])
        self.assertTrue(snapshot.opportunity_summary.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])
        self.assertFalse(snapshot.compatibility["modifies_product_business"])
        self.assertFalse(snapshot.compatibility["modifies_customer_business"])
        self.assertFalse(snapshot.compatibility["modifies_publishing"])

    def test_recommendation_summary_generation(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertEqual(
            snapshot.recommendation_summary.recommendation_count,
            len(snapshot.prioritized_recommendations),
        )
        self.assertEqual(
            snapshot.recommendation_summary.today_count,
            len(snapshot.recommended_today_actions),
        )
        self.assertEqual(
            snapshot.recommendation_summary.this_week_count,
            len(snapshot.recommended_this_week_actions),
        )
        self.assertGreater(snapshot.recommendation_confidence, 0.0)

    def test_recommendation_priority_derivation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "publishing_summary": {"failed_count": 1},
            }
        )

        self.assertEqual(
            snapshot.prioritized_recommendations[0].priority,
            BusinessRecommendationPriority.CRITICAL,
        )
        self.assertGreaterEqual(snapshot.recommendation_summary.critical_count, 1)

    def test_recommendation_category_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            **{
                **self._ready_context(),
                "customer_business_snapshot": SimpleNamespace(
                    customer_health="AT_RISK",
                    value_tier="VIP_POTENTIAL",
                    growth_opportunities=(SimpleNamespace(),),
                    retention_opportunities=(SimpleNamespace(),),
                    next_recommended_action="Re-engage customer",
                ),
                "publishing_summary": {"waiting_media_link_count": 1},
            }
        )

        self.assertIn(BusinessRecommendationCategory.CUSTOMER, snapshot.recommendation_categories)
        self.assertIn(BusinessRecommendationCategory.PUBLISHING, snapshot.recommendation_categories)
        self.assertIn(BusinessRecommendationCategory.REVENUE, snapshot.recommendation_categories)
        self.assertIn(BusinessRecommendationCategory.STRATEGY, snapshot.recommendation_categories)

    def test_recommended_today_action_generation(self) -> None:
        snapshot = self.service.build_snapshot(
            publishing_summary={"waiting_media_link_count": 1}
        )

        today_actions = {action.recommended_action for action in snapshot.recommended_today_actions}

        self.assertIn("Publish Products awaiting Media Links", today_actions)
        self.assertTrue(
            all(
                action.priority
                in {
                    BusinessRecommendationPriority.CRITICAL,
                    BusinessRecommendationPriority.HIGH,
                }
                for action in snapshot.recommended_today_actions
            )
        )

    def test_recommended_this_week_action_generation(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        week_actions = {
            action.recommended_action
            for action in snapshot.recommended_this_week_actions
        }

        self.assertIn("Review strategy opportunities", week_actions)
        self.assertTrue(
            all(
                action.priority
                in {
                    BusinessRecommendationPriority.MEDIUM,
                    BusinessRecommendationPriority.LOW,
                }
                for action in snapshot.recommended_this_week_actions
            )
        )

    def test_recommendation_handles_missing_upstreams(self) -> None:
        snapshot = self.service.build_snapshot()

        self.assertGreaterEqual(snapshot.recommendation_summary.recommendation_count, 1)
        self.assertIn(
            "Create missing Product",
            {action.recommended_action for action in snapshot.prioritized_recommendations},
        )
        self.assertGreaterEqual(snapshot.recommendation_confidence, 0.0)

    def test_recommendation_does_not_mutate_upstream_domain_objects(self) -> None:
        customer_snapshot = {
            "customer_health": "AT_RISK",
            "value_tier": "VIP_POTENTIAL",
            "growth_opportunities": [SimpleNamespace()],
            "retention_opportunities": [SimpleNamespace()],
            "next_recommended_action": "Re-engage",
        }
        original_customer = {
            "customer_health": "AT_RISK",
            "value_tier": "VIP_POTENTIAL",
            "growth_opportunities": list(customer_snapshot["growth_opportunities"]),
            "retention_opportunities": list(customer_snapshot["retention_opportunities"]),
            "next_recommended_action": "Re-engage",
        }

        self.service.build_snapshot(customer_business_snapshot=customer_snapshot)

        self.assertEqual(customer_snapshot, original_customer)

    def test_recommendation_provider_neutrality_preserved(self) -> None:
        snapshot = self.service.build_snapshot(**self._ready_context())

        self.assertTrue(snapshot.metadata["provider_neutral"])
        self.assertTrue(snapshot.recommendation_summary.compatibility["provider_neutral"])
        for action in snapshot.prioritized_recommendations:
            self.assertTrue(action.metadata["read_only"])
            self.assertTrue(action.metadata["aggregation_only"])
            self.assertTrue(action.metadata["advisory_only"])
            self.assertTrue(action.metadata["provider_neutral"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])

    @staticmethod
    def _ready_context() -> dict[str, object]:
        return {
            "product_business_snapshot": SimpleNamespace(
                product_health="HEALTHY",
                next_recommended_business_action="Review Product Business",
            ),
            "telegram_business_snapshot": SimpleNamespace(
                business_health="HEALTHY",
                next_recommended_business_action="Review Telegram Business",
            ),
            "customer_business_snapshot": SimpleNamespace(
                customer_health="HEALTHY",
                value_tier="BUYER",
                growth_opportunities=(),
                retention_opportunities=(),
                next_recommended_action="Continue Customer Business",
            ),
            "product_strategy_result": SimpleNamespace(
                recommendations=(
                    SimpleNamespace(recommendation_type="RECOMMEND_BUNDLE"),
                ),
                confidence=0.72,
            ),
            "commerce_strategy_result": SimpleNamespace(
                recommendations=(
                    SimpleNamespace(recommended_objective="Offer Bundle"),
                ),
                confidence=0.76,
            ),
            "business_learning_snapshot": SimpleNamespace(
                summary={"total_outcomes": 3, "total_recommendations": 2}
            ),
            "publishing_summary": {
                "queue_count": 1,
                "ready_count": 1,
                "failed_count": 0,
                "waiting_media_link_count": 0,
            },
        }


if __name__ == "__main__":
    unittest.main()

"""Business Optimization provider-neutral aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.business_optimization import (
    BusinessPerformanceHealth,
    BusinessPerformanceRecommendation,
    BusinessPerformanceSignal,
    BusinessPerformanceSummary,
    BusinessPerformanceTrend,
    BusinessOpportunityCategory,
    BusinessOpportunityImpact,
    BusinessOpportunityRecommendation,
    BusinessOpportunitySignal,
    BusinessOpportunitySummary,
    BusinessRecommendationAction,
    BusinessRecommendationCategory,
    BusinessRecommendationPriority,
    BusinessRecommendationSignal,
    BusinessRecommendationSummary,
    BusinessStrategyHealth,
    BusinessStrategyOpportunity,
    BusinessStrategyRecommendation,
    BusinessStrategySignal,
    BusinessStrategySummary,
    BusinessOptimizationHealth,
    BusinessOptimizationOpportunity,
    BusinessOptimizationPriority,
    BusinessOptimizationRecommendation,
    BusinessOptimizationSnapshot,
    BusinessOptimizationSummary,
)

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.customer_business_service import CustomerBusinessService
    from app.services.product_business_service import ProductBusinessService
    from app.services.product_strategy_service import ProductStrategyService
    from app.services.publishing_service import PublishingService
    from app.services.telegram_business_service import TelegramBusinessService


class BusinessOptimizationService:
    """Build read-only whole-business optimization snapshots.

    Business Optimization aggregates and advises only. It does not execute
    Telegram, mutate Product Business, Customer Business, Business Learning,
    Product Strategy, Commerce Strategy, Publishing, or DecisionEngine behavior.
    """

    def __init__(
        self,
        *,
        product_business_service: "ProductBusinessService | None" = None,
        telegram_business_service: "TelegramBusinessService | None" = None,
        customer_business_service: "CustomerBusinessService | None" = None,
        product_strategy_service: "ProductStrategyService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
        publishing_service: "PublishingService | None" = None,
    ) -> None:
        self.product_business_service = product_business_service
        self.telegram_business_service = telegram_business_service
        self.customer_business_service = customer_business_service
        self.product_strategy_service = product_strategy_service
        self.commerce_strategy_service = commerce_strategy_service
        self.business_learning_service = business_learning_service
        self.publishing_service = publishing_service

    def build_snapshot(
        self,
        *,
        product_business_snapshot: Any | None = None,
        product_business_snapshots: Iterable[Any] | None = None,
        telegram_business_snapshot: Any | None = None,
        telegram_business_snapshots: Iterable[Any] | None = None,
        customer_business_snapshot: Any | None = None,
        customer_business_snapshots: Iterable[Any] | None = None,
        product_strategy_result: Any | None = None,
        commerce_strategy_result: Any | None = None,
        business_learning_snapshot: Any | None = None,
        business_learning_context: Any | None = None,
        publishing_summary: Mapping[str, Any] | Any | None = None,
        publishing_queue_items: Iterable[Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> BusinessOptimizationSnapshot:
        """Return a canonical provider-neutral Business Optimization snapshot."""

        product_summary = self._product_business_summary(
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        telegram_summary = self._telegram_business_summary(
            telegram_business_snapshot=telegram_business_snapshot,
            telegram_business_snapshots=telegram_business_snapshots,
        )
        customer_summary = self._customer_business_summary(
            customer_business_snapshot=customer_business_snapshot,
            customer_business_snapshots=customer_business_snapshots,
        )
        product_strategy = self._product_strategy_summary(product_strategy_result)
        commerce_strategy = self._commerce_strategy_summary(commerce_strategy_result)
        publishing = self._publishing_summary(
            publishing_summary=publishing_summary,
            publishing_queue_items=publishing_queue_items,
        )
        learning = self._learning_summary(
            business_learning_snapshot=business_learning_snapshot,
            business_learning_context=business_learning_context,
        )
        product_performance = self._product_performance_summary(
            product_summary=product_summary,
            product_strategy=product_strategy,
            learning=learning,
        )
        customer_performance = self._customer_performance_summary(
            customer_summary=customer_summary,
            telegram_summary=telegram_summary,
            learning=learning,
        )
        commerce_performance = self._commerce_performance_summary(
            commerce_strategy=commerce_strategy,
            customer_summary=customer_summary,
            product_strategy=product_strategy,
        )
        publishing_performance = self._publishing_performance_summary(
            publishing=publishing
        )
        performance_signals = self._performance_signals(
            product_performance=product_performance,
            customer_performance=customer_performance,
            commerce_performance=commerce_performance,
            publishing_performance=publishing_performance,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
        )
        performance_health = self._performance_health(
            product_performance=product_performance,
            customer_performance=customer_performance,
            publishing_performance=publishing_performance,
            performance_signals=performance_signals,
        )
        performance_trend = self._performance_trend(
            performance_health=performance_health,
            performance_signals=performance_signals,
            product_performance=product_performance,
            customer_performance=customer_performance,
            commerce_performance=commerce_performance,
            publishing_performance=publishing_performance,
        )
        performance_confidence = self._performance_confidence(
            product_performance=product_performance,
            customer_performance=customer_performance,
            commerce_performance=commerce_performance,
            publishing_performance=publishing_performance,
            learning=learning,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
        )
        performance_recommendations = self._performance_recommendations(
            performance_signals=performance_signals,
            performance_health=performance_health,
            performance_trend=performance_trend,
            performance_confidence=performance_confidence,
        )
        performance_summary = BusinessPerformanceSummary(
            health=performance_health,
            trend=performance_trend,
            confidence=performance_confidence,
            signal_count=len(performance_signals),
            recommendation_count=len(performance_recommendations),
            recommendations=performance_recommendations,
            next_recommended_performance_action=(
                performance_recommendations[0].recommended_next_action
                if performance_recommendations
                else "Review Business Performance"
            ),
            compatibility=self._compatibility(),
            metadata={"source": "business_performance_summary"},
        )
        strategy_signals = self._strategy_signals(
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            product_summary=product_summary,
            customer_summary=customer_summary,
            publishing=publishing,
            learning=learning,
        )
        strategy_opportunities = self._strategy_opportunities(
            strategy_signals=strategy_signals,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            customer_summary=customer_summary,
            publishing=publishing,
            learning=learning,
        )
        strategy_health = self._strategy_health(
            strategy_signals=strategy_signals,
            strategy_opportunities=strategy_opportunities,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
        )
        strategy_confidence = self._strategy_confidence(
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            customer_summary=customer_summary,
            product_summary=product_summary,
            publishing=publishing,
            learning=learning,
        )
        strategy_recommendations = self._strategy_recommendations(
            strategy_opportunities=strategy_opportunities,
            strategy_health=strategy_health,
            strategy_confidence=strategy_confidence,
        )
        recommended_strategy_actions = tuple(
            recommendation.recommended_next_action
            for recommendation in strategy_recommendations
        )
        strategy_summary = BusinessStrategySummary(
            health=strategy_health,
            confidence=strategy_confidence,
            signal_count=len(strategy_signals),
            opportunity_count=len(strategy_opportunities),
            recommendation_count=len(strategy_recommendations),
            recommended_strategy_actions=recommended_strategy_actions,
            recommendations=strategy_recommendations,
            compatibility=self._compatibility(),
            metadata={"source": "business_strategy_summary"},
        )
        opportunity_signals = self._opportunity_signals(
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
            learning=learning,
            strategy_opportunities=strategy_opportunities,
            revenue_readiness=self._revenue_readiness(
                product_summary=product_summary,
                telegram_summary=telegram_summary,
                customer_summary=customer_summary,
                commerce_strategy=commerce_strategy,
                publishing=publishing,
            ),
        )
        opportunity_categories = tuple(
            dict.fromkeys(signal.category for signal in opportunity_signals)
        )
        high_impact_opportunities = tuple(
            signal
            for signal in opportunity_signals
            if signal.impact
            in {BusinessOpportunityImpact.HIGH, BusinessOpportunityImpact.CRITICAL}
        )
        revenue_opportunities = self._category_opportunities(
            opportunity_signals, BusinessOpportunityCategory.REVENUE
        )
        customer_opportunities = self._category_opportunities(
            opportunity_signals, BusinessOpportunityCategory.CUSTOMER
        )
        product_opportunities = self._category_opportunities(
            opportunity_signals, BusinessOpportunityCategory.PRODUCT
        )
        publishing_opportunities = self._category_opportunities(
            opportunity_signals, BusinessOpportunityCategory.PUBLISHING
        )
        strategy_opportunity_signals = self._category_opportunities(
            opportunity_signals, BusinessOpportunityCategory.STRATEGY
        )
        opportunity_confidence = self._opportunity_confidence(
            opportunity_signals=opportunity_signals,
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
            learning=learning,
        )
        opportunity_recommendations = self._opportunity_recommendations(
            opportunity_signals=opportunity_signals,
            opportunity_confidence=opportunity_confidence,
        )
        recommended_opportunity_actions = tuple(
            recommendation.recommended_next_action
            for recommendation in opportunity_recommendations
        )
        opportunity_summary = BusinessOpportunitySummary(
            opportunity_count=len(opportunity_signals),
            high_impact_count=len(high_impact_opportunities),
            revenue_count=len(revenue_opportunities),
            customer_count=len(customer_opportunities),
            product_count=len(product_opportunities),
            publishing_count=len(publishing_opportunities),
            strategy_count=len(strategy_opportunity_signals),
            confidence=opportunity_confidence,
            recommendation_count=len(opportunity_recommendations),
            recommended_opportunity_actions=recommended_opportunity_actions,
            recommendations=opportunity_recommendations,
            compatibility=self._compatibility(),
            metadata={"source": "business_opportunity_summary"},
        )
        recommendation_signals = self._recommendation_signals(
            opportunity_signals=opportunity_signals,
            performance_signals=performance_signals,
            strategy_opportunities=strategy_opportunities,
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
            learning=learning,
        )
        prioritized_recommendations = self._prioritized_recommendations(
            recommendation_signals=recommendation_signals,
            opportunity_confidence=opportunity_confidence,
            performance_confidence=performance_confidence,
            strategy_confidence=strategy_confidence,
        )
        recommendation_categories = tuple(
            dict.fromkeys(action.category for action in prioritized_recommendations)
        )
        recommended_today_actions = tuple(
            action
            for action in prioritized_recommendations
            if action.timeframe == "today"
        )
        recommended_this_week_actions = tuple(
            action
            for action in prioritized_recommendations
            if action.timeframe == "this_week"
        )
        recommendation_confidence = self._recommendation_confidence(
            prioritized_recommendations=prioritized_recommendations,
            opportunity_confidence=opportunity_confidence,
            performance_confidence=performance_confidence,
            strategy_confidence=strategy_confidence,
        )
        recommendation_summary = BusinessRecommendationSummary(
            recommendation_count=len(prioritized_recommendations),
            critical_count=sum(
                1
                for action in prioritized_recommendations
                if action.priority == BusinessRecommendationPriority.CRITICAL
            ),
            high_count=sum(
                1
                for action in prioritized_recommendations
                if action.priority == BusinessRecommendationPriority.HIGH
            ),
            medium_count=sum(
                1
                for action in prioritized_recommendations
                if action.priority == BusinessRecommendationPriority.MEDIUM
            ),
            low_count=sum(
                1
                for action in prioritized_recommendations
                if action.priority == BusinessRecommendationPriority.LOW
            ),
            today_count=len(recommended_today_actions),
            this_week_count=len(recommended_this_week_actions),
            confidence=recommendation_confidence,
            next_recommended_action=(
                prioritized_recommendations[0].recommended_action
                if prioritized_recommendations
                else "Review Business Recommendations"
            ),
            compatibility=self._compatibility(),
            metadata={"source": "business_recommendation_summary"},
        )
        revenue_readiness = self._revenue_readiness(
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
        )
        risks = self._business_risks(
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            publishing=publishing,
            learning=learning,
        )
        health = self._health(
            revenue_readiness=revenue_readiness,
            risks=risks,
            product_summary=product_summary,
            customer_summary=customer_summary,
            telegram_summary=telegram_summary,
        )
        opportunities = self._opportunities(
            health=health,
            revenue_readiness=revenue_readiness,
            risks=risks,
            product_summary=product_summary,
            telegram_summary=telegram_summary,
            customer_summary=customer_summary,
            product_strategy=product_strategy,
            commerce_strategy=commerce_strategy,
            publishing=publishing,
            learning=learning,
        )
        recommendations = self._recommendations(
            opportunities=opportunities,
            health=health,
            revenue_readiness=revenue_readiness,
        )
        next_action = self._next_action(recommendations, opportunities)
        summary = BusinessOptimizationSummary(
            health=health,
            revenue_readiness=revenue_readiness,
            risk_count=len(risks),
            opportunity_count=len(opportunities),
            recommendation_count=len(recommendations),
            next_recommended_business_action=next_action,
            compatibility=self._compatibility(),
            metadata={"source": "business_optimization_summary"},
        )
        return BusinessOptimizationSnapshot(
            health=health,
            product_business_summary=product_summary,
            telegram_business_summary=telegram_summary,
            customer_business_summary=customer_summary,
            product_strategy_summary=product_strategy,
            commerce_strategy_summary=commerce_strategy,
            publishing_summary=publishing,
            business_learning_summary=learning,
            revenue_readiness=revenue_readiness,
            performance_summary=performance_summary,
            performance_health=performance_health,
            performance_trend=performance_trend,
            performance_signals=performance_signals,
            product_performance_summary=product_performance,
            customer_performance_summary=customer_performance,
            commerce_performance_summary=commerce_performance,
            publishing_performance_summary=publishing_performance,
            performance_confidence=performance_confidence,
            strategy_summary=strategy_summary,
            strategy_health=strategy_health,
            strategy_signals=strategy_signals,
            strategy_opportunities=strategy_opportunities,
            strategy_confidence=strategy_confidence,
            recommended_strategy_actions=recommended_strategy_actions,
            opportunity_summary=opportunity_summary,
            opportunity_categories=opportunity_categories,
            opportunity_signals=opportunity_signals,
            high_impact_opportunities=high_impact_opportunities,
            revenue_opportunities=revenue_opportunities,
            customer_opportunities=customer_opportunities,
            product_opportunities=product_opportunities,
            publishing_opportunities=publishing_opportunities,
            strategy_opportunity_signals=strategy_opportunity_signals,
            recommended_opportunity_actions=recommended_opportunity_actions,
            opportunity_confidence=opportunity_confidence,
            recommendation_summary=recommendation_summary,
            prioritized_recommendations=prioritized_recommendations,
            recommendation_categories=recommendation_categories,
            recommendation_signals=recommendation_signals,
            recommended_today_actions=recommended_today_actions,
            recommended_this_week_actions=recommended_this_week_actions,
            recommendation_confidence=recommendation_confidence,
            business_risks=risks,
            opportunities=opportunities,
            recommendations=recommendations,
            next_recommended_business_action=next_action,
            summary=summary,
            compatibility=self._compatibility(
                product_business_snapshot=product_business_snapshot,
                product_business_snapshots=product_business_snapshots,
                telegram_business_snapshot=telegram_business_snapshot,
                telegram_business_snapshots=telegram_business_snapshots,
                customer_business_snapshot=customer_business_snapshot,
                customer_business_snapshots=customer_business_snapshots,
                product_strategy_result=product_strategy_result,
                commerce_strategy_result=commerce_strategy_result,
                business_learning_snapshot=business_learning_snapshot,
                business_learning_context=business_learning_context,
                publishing_summary=publishing_summary,
                publishing_queue_items=publishing_queue_items,
            ),
            metadata={
                "source": "business_optimization",
                "owner": "BusinessOptimizationService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_summary(self, **context: Any) -> BusinessOptimizationSummary:
        return self.build_snapshot(**context).summary

    def _product_business_summary(
        self,
        *,
        product_business_snapshot: Any | None,
        product_business_snapshots: Iterable[Any] | None,
    ) -> dict[str, Any]:
        snapshots = self._items(product_business_snapshot, product_business_snapshots)
        health_values = self._text_tuple(
            self._read(item, "product_health") for item in snapshots
        )
        next_actions = self._text_tuple(
            self._read(item, "next_recommended_business_action")
            or self._read(item, "next_business_recommendation", "label")
            for item in snapshots
        )
        return {
            "available": bool(snapshots),
            "product_count": len(snapshots),
            "health_values": health_values,
            "needs_attention_count": sum(
                1
                for value in health_values
                if value.upper() in {"NEEDS_ATTENTION", "AT_RISK", "MISSING"}
            ),
            "opportunity_count": sum(
                1
                for value in health_values
                if value.upper() in {"OPPORTUNITY", "HEALTHY", "TELEGRAM_READY"}
            ),
            "next_actions": next_actions,
            "source": "ProductBusinessService",
        }

    def _telegram_business_summary(
        self,
        *,
        telegram_business_snapshot: Any | None,
        telegram_business_snapshots: Iterable[Any] | None,
    ) -> dict[str, Any]:
        snapshots = self._items(telegram_business_snapshot, telegram_business_snapshots)
        health_values = self._text_tuple(
            self._read(item, "business_health")
            or self._read(item, "summary", "business_health")
            for item in snapshots
        )
        next_actions = self._text_tuple(
            self._read(item, "next_recommended_business_action")
            or self._read(item, "summary", "next_recommended_action")
            for item in snapshots
        )
        return {
            "available": bool(snapshots),
            "customer_count": len(snapshots),
            "health_values": health_values,
            "needs_attention_count": sum(
                1 for value in health_values if value.upper() in {"AT_RISK", "DORMANT", "NEEDS_ATTENTION"}
            ),
            "next_actions": next_actions,
            "source": "TelegramBusinessService",
        }

    def _customer_business_summary(
        self,
        *,
        customer_business_snapshot: Any | None,
        customer_business_snapshots: Iterable[Any] | None,
    ) -> dict[str, Any]:
        snapshots = self._items(customer_business_snapshot, customer_business_snapshots)
        health_values = self._text_tuple(
            self._read(item, "customer_health") for item in snapshots
        )
        value_tiers = self._text_tuple(self._read(item, "value_tier") for item in snapshots)
        growth_counts = tuple(
            len(tuple(self._read(item, "growth_opportunities") or ()))
            for item in snapshots
        )
        retention_counts = tuple(
            len(tuple(self._read(item, "retention_opportunities") or ()))
            for item in snapshots
        )
        next_actions = self._text_tuple(
            self._read(item, "next_recommended_action") for item in snapshots
        )
        return {
            "available": bool(snapshots),
            "customer_count": len(snapshots),
            "health_values": health_values,
            "value_tiers": value_tiers,
            "vip_count": sum(1 for value in value_tiers if value.upper() in {"VIP", "VIP_POTENTIAL"}),
            "at_risk_count": sum(
                1 for value in health_values if value.upper() in {"AT_RISK", "DORMANT", "NEEDS_ATTENTION"}
            ),
            "growth_opportunity_count": sum(growth_counts),
            "retention_opportunity_count": sum(retention_counts),
            "next_actions": next_actions,
            "source": "CustomerBusinessService",
        }

    def _product_strategy_summary(self, result: Any | None) -> dict[str, Any]:
        recommendations = tuple(self._read(result, "recommendations") or ())
        return {
            "available": result is not None,
            "recommendation_count": len(recommendations),
            "confidence": self._float(self._read(result, "confidence")),
            "recommendation_types": self._text_tuple(
                self._read(item, "recommendation_type") for item in recommendations
            ),
            "source": "ProductStrategyService",
        }

    def _commerce_strategy_summary(self, result: Any | None) -> dict[str, Any]:
        recommendations = tuple(self._read(result, "recommendations") or ())
        return {
            "available": result is not None,
            "recommendation_count": len(recommendations),
            "confidence": self._float(self._read(result, "confidence")),
            "objectives": self._text_tuple(
                self._read(item, "recommended_objective") for item in recommendations
            ),
            "source": "CommerceStrategyService",
        }

    def _publishing_summary(
        self,
        *,
        publishing_summary: Mapping[str, Any] | Any | None,
        publishing_queue_items: Iterable[Any] | None,
    ) -> dict[str, Any]:
        items = tuple(publishing_queue_items or ())
        queue_count = self._int(
            self._read(publishing_summary, "queue_count")
            or self._read(publishing_summary, "total_items")
            or len(items)
        )
        waiting_media_link = self._int(
            self._read(publishing_summary, "waiting_media_link_count")
            or sum(
                1
                for item in items
                if bool(self._read(item, "waiting_for_media_link"))
                or self._read(item, "media_link_status") == "WAITING_FOR_MEDIA_LINK"
            )
        )
        failed_count = self._int(
            self._read(publishing_summary, "failed_count")
            or sum(
                1
                for item in items
                if str(self._read(item, "status") or "").upper() == "FAILED"
            )
        )
        ready_count = self._int(
            self._read(publishing_summary, "ready_count")
            or sum(
                1
                for item in items
                if str(self._read(item, "status") or "").upper() in {"READY", "PENDING"}
            )
        )
        return {
            "available": publishing_summary is not None or bool(items),
            "queue_count": queue_count,
            "waiting_media_link_count": waiting_media_link,
            "failed_count": failed_count,
            "ready_count": ready_count,
            "source": "PublishingService",
        }

    def _learning_summary(
        self,
        *,
        business_learning_snapshot: Any | None,
        business_learning_context: Any | None,
    ) -> dict[str, Any]:
        summary = self._read(business_learning_snapshot, "summary")
        return {
            "available": business_learning_snapshot is not None
            or business_learning_context is not None,
            "outcome_count": self._int(
                self._read(summary, "total_outcomes")
                or self._read(business_learning_snapshot, "total_outcomes")
            ),
            "recommendation_count": self._int(
                self._read(summary, "total_recommendations")
                or self._read(business_learning_snapshot, "total_recommendations")
            ),
            "context_type": self._safe_text(
                self._read(business_learning_context, "context_type")
            ),
            "source": "BusinessLearningService",
        }

    @staticmethod
    def _product_performance_summary(
        *,
        product_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> dict[str, Any]:
        product_count = int(product_summary.get("product_count") or 0)
        needs_attention = int(product_summary.get("needs_attention_count") or 0)
        opportunities = int(product_summary.get("opportunity_count") or 0)
        strategy_recommendations = int(
            product_strategy.get("recommendation_count") or 0
        )
        if needs_attention:
            status = "needs_attention"
        elif product_count and (opportunities or strategy_recommendations):
            status = "performing"
        elif product_count:
            status = "monitor"
        else:
            status = "unknown"
        return {
            "available": bool(product_summary.get("available")),
            "status": status,
            "product_count": product_count,
            "needs_attention_count": needs_attention,
            "opportunity_count": opportunities,
            "strategy_recommendation_count": strategy_recommendations,
            "learning_outcome_count": int(learning.get("outcome_count") or 0),
            "source": "ProductBusinessService",
        }

    @staticmethod
    def _customer_performance_summary(
        *,
        customer_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> dict[str, Any]:
        customer_count = int(customer_summary.get("customer_count") or 0)
        at_risk = int(customer_summary.get("at_risk_count") or 0)
        vip = int(customer_summary.get("vip_count") or 0)
        growth = int(customer_summary.get("growth_opportunity_count") or 0)
        retention = int(customer_summary.get("retention_opportunity_count") or 0)
        if at_risk:
            status = "retention_needed"
        elif vip or growth:
            status = "growth_ready"
        elif customer_count:
            status = "active"
        else:
            status = "unknown"
        return {
            "available": bool(customer_summary.get("available")),
            "status": status,
            "customer_count": customer_count,
            "telegram_customer_count": int(telegram_summary.get("customer_count") or 0),
            "vip_count": vip,
            "at_risk_count": at_risk,
            "growth_opportunity_count": growth,
            "retention_opportunity_count": retention,
            "learning_outcome_count": int(learning.get("outcome_count") or 0),
            "source": "CustomerBusinessService",
        }

    @staticmethod
    def _commerce_performance_summary(
        *,
        commerce_strategy: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
    ) -> dict[str, Any]:
        commerce_recommendations = int(
            commerce_strategy.get("recommendation_count") or 0
        )
        product_recommendations = int(
            product_strategy.get("recommendation_count") or 0
        )
        customer_count = int(customer_summary.get("customer_count") or 0)
        if commerce_recommendations and customer_count:
            status = "ready"
        elif commerce_recommendations or product_recommendations:
            status = "strategy_available"
        elif customer_count:
            status = "needs_strategy"
        else:
            status = "unknown"
        return {
            "available": bool(commerce_strategy.get("available"))
            or bool(product_strategy.get("available")),
            "status": status,
            "commerce_recommendation_count": commerce_recommendations,
            "product_strategy_recommendation_count": product_recommendations,
            "customer_count": customer_count,
            "commerce_confidence": float(commerce_strategy.get("confidence") or 0.0),
            "product_strategy_confidence": float(
                product_strategy.get("confidence") or 0.0
            ),
            "objectives": tuple(commerce_strategy.get("objectives") or ()),
            "product_recommendation_types": tuple(
                product_strategy.get("recommendation_types") or ()
            ),
            "source": "CommerceStrategyService",
        }

    @staticmethod
    def _publishing_performance_summary(
        *,
        publishing: Mapping[str, Any],
    ) -> dict[str, Any]:
        failed = int(publishing.get("failed_count") or 0)
        waiting = int(publishing.get("waiting_media_link_count") or 0)
        ready = int(publishing.get("ready_count") or 0)
        queue_count = int(publishing.get("queue_count") or 0)
        if failed:
            status = "blocked"
        elif waiting:
            status = "needs_media_links"
        elif ready:
            status = "ready"
        elif queue_count:
            status = "queued"
        else:
            status = "unknown"
        return {
            "available": bool(publishing.get("available")),
            "status": status,
            "queue_count": queue_count,
            "ready_count": ready,
            "failed_count": failed,
            "waiting_media_link_count": waiting,
            "source": "PublishingService",
        }

    def _performance_signals(
        self,
        *,
        product_performance: Mapping[str, Any],
        customer_performance: Mapping[str, Any],
        commerce_performance: Mapping[str, Any],
        publishing_performance: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
    ) -> tuple[BusinessPerformanceSignal, ...]:
        signals: list[BusinessPerformanceSignal] = []
        if product_performance.get("needs_attention_count"):
            signals.append(
                self._performance_signal(
                    "product_underperformance",
                    "Review underperforming Products",
                    "HIGH",
                    0.74,
                    {"product_performance": dict(product_performance)},
                )
            )
        if product_performance.get("opportunity_count"):
            signals.append(
                self._performance_signal(
                    "product_portfolio_opportunity",
                    "Improve Product portfolio",
                    "NORMAL",
                    0.62,
                    {"product_performance": dict(product_performance)},
                )
            )
        if product_strategy.get("recommendation_count"):
            signals.append(
                self._performance_signal(
                    "experience_expansion",
                    "Expand successful Experiences",
                    "NORMAL",
                    product_strategy.get("confidence") or 0.58,
                    {"product_strategy": dict(product_strategy)},
                )
            )
        if publishing_performance.get("failed_count") or publishing_performance.get(
            "waiting_media_link_count"
        ):
            priority = (
                "CRITICAL" if publishing_performance.get("failed_count") else "HIGH"
            )
            signals.append(
                self._performance_signal(
                    "publishing_readiness",
                    "Improve publishing readiness",
                    priority,
                    0.8,
                    {"publishing_performance": dict(publishing_performance)},
                )
            )
        if customer_performance.get("at_risk_count") or customer_performance.get(
            "retention_opportunity_count"
        ):
            signals.append(
                self._performance_signal(
                    "customer_retention",
                    "Increase customer retention",
                    "HIGH",
                    0.72,
                    {"customer_performance": dict(customer_performance)},
                )
            )
        if customer_performance.get("vip_count") or customer_performance.get(
            "growth_opportunity_count"
        ):
            signals.append(
                self._performance_signal(
                    "vip_development",
                    "Increase VIP development",
                    "NORMAL",
                    0.64,
                    {"customer_performance": dict(customer_performance)},
                )
            )
        objective_text = " ".join(
            tuple(commerce_strategy.get("objectives") or ())
            + tuple(product_strategy.get("recommendation_types") or ())
        ).upper()
        if "BUNDLE" in objective_text:
            signals.append(
                self._performance_signal(
                    "bundle_expansion",
                    "Expand successful Bundles",
                    "NORMAL",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.57,
                    {"commerce_performance": dict(commerce_performance)},
                )
            )
        if not signals:
            signals.append(
                self._performance_signal(
                    "baseline",
                    "Gather performance inputs",
                    "LOW",
                    0.3,
                    {
                        "product_performance": dict(product_performance),
                        "customer_performance": dict(customer_performance),
                        "commerce_performance": dict(commerce_performance),
                        "publishing_performance": dict(publishing_performance),
                    },
                )
            )
        return tuple(signals)

    @staticmethod
    def _performance_health(
        *,
        product_performance: Mapping[str, Any],
        customer_performance: Mapping[str, Any],
        publishing_performance: Mapping[str, Any],
        performance_signals: tuple[BusinessPerformanceSignal, ...],
    ) -> BusinessPerformanceHealth:
        priorities = {signal.priority for signal in performance_signals}
        if BusinessOptimizationPriority.CRITICAL in priorities:
            return BusinessPerformanceHealth.AT_RISK
        if (
            BusinessOptimizationPriority.HIGH in priorities
            or product_performance.get("status") == "needs_attention"
            or customer_performance.get("status") == "retention_needed"
            or publishing_performance.get("status")
            in {"blocked", "needs_media_links"}
        ):
            return BusinessPerformanceHealth.NEEDS_ATTENTION
        if (
            product_performance.get("status") == "performing"
            and customer_performance.get("customer_count")
            and publishing_performance.get("status") in {"ready", "unknown"}
        ):
            return BusinessPerformanceHealth.HEALTHY
        if any(
            summary.get("available")
            for summary in (
                product_performance,
                customer_performance,
                publishing_performance,
            )
        ):
            return BusinessPerformanceHealth.OPPORTUNITY
        return BusinessPerformanceHealth.UNKNOWN

    @staticmethod
    def _performance_trend(
        *,
        performance_health: BusinessPerformanceHealth,
        performance_signals: tuple[BusinessPerformanceSignal, ...],
        product_performance: Mapping[str, Any],
        customer_performance: Mapping[str, Any],
        commerce_performance: Mapping[str, Any],
        publishing_performance: Mapping[str, Any],
    ) -> BusinessPerformanceTrend:
        signal_types = {signal.signal_type for signal in performance_signals}
        negative = bool(
            signal_types
            & {"product_underperformance", "publishing_readiness", "customer_retention"}
        )
        positive = bool(
            signal_types
            & {
                "product_portfolio_opportunity",
                "experience_expansion",
                "vip_development",
                "bundle_expansion",
            }
        )
        if positive and negative:
            return BusinessPerformanceTrend.MIXED
        if performance_health == BusinessPerformanceHealth.AT_RISK:
            return BusinessPerformanceTrend.DECLINING
        if positive:
            return BusinessPerformanceTrend.IMPROVING
        if negative:
            return BusinessPerformanceTrend.DECLINING
        if any(
            summary.get("available")
            for summary in (
                product_performance,
                customer_performance,
                commerce_performance,
                publishing_performance,
            )
        ):
            return BusinessPerformanceTrend.STABLE
        return BusinessPerformanceTrend.UNKNOWN

    @staticmethod
    def _performance_confidence(
        *,
        product_performance: Mapping[str, Any],
        customer_performance: Mapping[str, Any],
        commerce_performance: Mapping[str, Any],
        publishing_performance: Mapping[str, Any],
        learning: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
    ) -> float:
        source_count = sum(
            1
            for summary in (
                product_performance,
                customer_performance,
                commerce_performance,
                publishing_performance,
                learning,
                product_strategy,
                commerce_strategy,
            )
            if summary.get("available")
        )
        confidence = 0.2 + (source_count * 0.1)
        confidence += min(float(product_strategy.get("confidence") or 0.0), 1.0) * 0.1
        confidence += min(float(commerce_strategy.get("confidence") or 0.0), 1.0) * 0.1
        return round(max(0.0, min(1.0, confidence)), 2)

    def _performance_recommendations(
        self,
        *,
        performance_signals: tuple[BusinessPerformanceSignal, ...],
        performance_health: BusinessPerformanceHealth,
        performance_trend: BusinessPerformanceTrend,
        performance_confidence: float,
    ) -> tuple[BusinessPerformanceRecommendation, ...]:
        ordered = sorted(
            performance_signals,
            key=lambda item: self._priority_rank(item.priority),
            reverse=True,
        )
        return tuple(
            BusinessPerformanceRecommendation(
                recommendation_type=signal.signal_type.upper(),
                priority=signal.priority,
                confidence=round(
                    max(signal.confidence, performance_confidence * 0.75), 2
                ),
                recommended_next_action=signal.detail,
                supporting_evidence={
                    "signal": signal.supporting_evidence,
                    "performance_health": performance_health.value,
                    "performance_trend": performance_trend.value,
                },
                metadata={
                    "read_only": True,
                    "aggregation_only": True,
                    "advisory_only": True,
                    "provider_neutral": True,
                },
            )
            for signal in ordered
        )

    @classmethod
    def _performance_signal(
        cls,
        signal_type: str,
        detail: str,
        priority: str,
        confidence: Any,
        evidence: Mapping[str, Any],
    ) -> BusinessPerformanceSignal:
        return BusinessPerformanceSignal(
            signal_type=signal_type,
            priority=cls._priority(priority),
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            detail=detail,
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
                "provider_neutral": True,
            },
        )

    def _strategy_signals(
        self,
        *,
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        product_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[BusinessStrategySignal, ...]:
        signals: list[BusinessStrategySignal] = []
        product_recommendations = int(product_strategy.get("recommendation_count") or 0)
        commerce_recommendations = int(
            commerce_strategy.get("recommendation_count") or 0
        )
        product_count = int(product_summary.get("product_count") or 0)
        customer_count = int(customer_summary.get("customer_count") or 0)
        objective_text = " ".join(
            tuple(product_strategy.get("recommendation_types") or ())
            + tuple(commerce_strategy.get("objectives") or ())
            + tuple(customer_summary.get("next_actions") or ())
        ).upper()
        if product_recommendations:
            signals.append(
                self._strategy_signal(
                    "product_strategy_available",
                    "Expand successful Product strategies",
                    "NORMAL",
                    product_strategy.get("confidence") or 0.6,
                    {"product_strategy": dict(product_strategy)},
                )
            )
        if product_count and not product_recommendations:
            signals.append(
                self._strategy_signal(
                    "product_strategy_gap",
                    "Improve Product sequencing",
                    "HIGH",
                    0.65,
                    {
                        "product_business": dict(product_summary),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if commerce_recommendations:
            signals.append(
                self._strategy_signal(
                    "commerce_strategy_available",
                    "Improve customer journey strategy",
                    "NORMAL",
                    commerce_strategy.get("confidence") or 0.6,
                    {"commerce_strategy": dict(commerce_strategy)},
                )
            )
        if customer_count and not commerce_recommendations:
            signals.append(
                self._strategy_signal(
                    "commerce_strategy_gap",
                    "Improve customer journey strategy",
                    "HIGH",
                    0.66,
                    {
                        "customer_business": dict(customer_summary),
                        "commerce_strategy": dict(commerce_strategy),
                    },
                )
            )
        if "FREE" in objective_text or "PREVIEW" in objective_text:
            signals.append(
                self._strategy_signal(
                    "free_preview_strategy",
                    "Improve FREE preview strategy",
                    "NORMAL",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.58,
                    {
                        "commerce_strategy": dict(commerce_strategy),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if "BUNDLE" in objective_text:
            signals.append(
                self._strategy_signal(
                    "bundle_strategy",
                    "Improve Bundle strategy",
                    "NORMAL",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.6,
                    {
                        "commerce_strategy": dict(commerce_strategy),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if "STORY" in objective_text:
            signals.append(
                self._strategy_signal(
                    "story_strategy",
                    "Improve Story strategy",
                    "NORMAL",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.58,
                    {
                        "commerce_strategy": dict(commerce_strategy),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if customer_summary.get("growth_opportunity_count"):
            signals.append(
                self._strategy_signal(
                    "experience_strategy",
                    "Expand successful Experiences",
                    "NORMAL",
                    0.62,
                    {"customer_business": dict(customer_summary)},
                )
            )
        if publishing.get("failed_count") or publishing.get("waiting_media_link_count"):
            signals.append(
                self._strategy_signal(
                    "publishing_strategy",
                    "Improve publishing strategy",
                    "HIGH",
                    0.72,
                    {"publishing": dict(publishing)},
                )
            )
        if learning.get("available"):
            signals.append(
                self._strategy_signal(
                    "learning_evidence",
                    "Use Business Learning evidence in strategy",
                    "LOW",
                    0.5,
                    {"business_learning": dict(learning)},
                )
            )
        if not signals:
            signals.append(
                self._strategy_signal(
                    "baseline",
                    "Gather strategy inputs",
                    "LOW",
                    0.3,
                    {
                        "product_strategy": dict(product_strategy),
                        "commerce_strategy": dict(commerce_strategy),
                    },
                )
            )
        return tuple(signals)

    def _strategy_opportunities(
        self,
        *,
        strategy_signals: tuple[BusinessStrategySignal, ...],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[BusinessStrategyOpportunity, ...]:
        opportunities: list[BusinessStrategyOpportunity] = []
        action_by_signal = {
            "product_strategy_available": "Expand successful Product strategies",
            "product_strategy_gap": "Improve Product sequencing",
            "commerce_strategy_available": "Improve customer journey strategy",
            "commerce_strategy_gap": "Improve customer journey strategy",
            "free_preview_strategy": "Improve FREE preview strategy",
            "bundle_strategy": "Improve Bundle strategy",
            "story_strategy": "Improve Story strategy",
            "experience_strategy": "Expand successful Experiences",
            "publishing_strategy": "Improve publishing strategy",
            "learning_evidence": "Use Business Learning evidence in strategy",
            "baseline": "Gather strategy inputs",
        }
        for signal in strategy_signals:
            opportunities.append(
                BusinessStrategyOpportunity(
                    opportunity_type=signal.signal_type,
                    priority=signal.priority,
                    confidence=signal.confidence,
                    recommended_action=action_by_signal.get(
                        signal.signal_type, signal.detail
                    ),
                    supporting_evidence={
                        "signal": signal.supporting_evidence,
                        "product_strategy": dict(product_strategy),
                        "commerce_strategy": dict(commerce_strategy),
                        "customer_business": dict(customer_summary),
                        "publishing": dict(publishing),
                        "business_learning": dict(learning),
                    },
                    metadata={
                        "read_only": True,
                        "aggregation_only": True,
                        "advisory_only": True,
                        "provider_neutral": True,
                    },
                )
            )
        return tuple(opportunities)

    @staticmethod
    def _strategy_health(
        *,
        strategy_signals: tuple[BusinessStrategySignal, ...],
        strategy_opportunities: tuple[BusinessStrategyOpportunity, ...],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
    ) -> BusinessStrategyHealth:
        priorities = {signal.priority for signal in strategy_signals}
        if BusinessOptimizationPriority.CRITICAL in priorities:
            return BusinessStrategyHealth.AT_RISK
        if publishing.get("failed_count"):
            return BusinessStrategyHealth.AT_RISK
        if BusinessOptimizationPriority.HIGH in priorities:
            return BusinessStrategyHealth.NEEDS_ATTENTION
        if (
            product_strategy.get("recommendation_count")
            and commerce_strategy.get("recommendation_count")
            and not publishing.get("waiting_media_link_count")
        ):
            return BusinessStrategyHealth.HEALTHY
        if strategy_opportunities:
            return BusinessStrategyHealth.OPPORTUNITY
        return BusinessStrategyHealth.UNKNOWN

    @staticmethod
    def _strategy_confidence(
        *,
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_summary: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> float:
        source_count = sum(
            1
            for summary in (
                product_strategy,
                commerce_strategy,
                customer_summary,
                product_summary,
                publishing,
                learning,
            )
            if summary.get("available")
        )
        confidence = 0.2 + (source_count * 0.1)
        confidence += min(float(product_strategy.get("confidence") or 0.0), 1.0) * 0.1
        confidence += min(float(commerce_strategy.get("confidence") or 0.0), 1.0) * 0.1
        return round(max(0.0, min(1.0, confidence)), 2)

    def _strategy_recommendations(
        self,
        *,
        strategy_opportunities: tuple[BusinessStrategyOpportunity, ...],
        strategy_health: BusinessStrategyHealth,
        strategy_confidence: float,
    ) -> tuple[BusinessStrategyRecommendation, ...]:
        ordered = sorted(
            strategy_opportunities,
            key=lambda item: self._priority_rank(item.priority),
            reverse=True,
        )
        return tuple(
            BusinessStrategyRecommendation(
                recommendation_type=opportunity.opportunity_type.upper(),
                priority=opportunity.priority,
                confidence=round(
                    max(opportunity.confidence, strategy_confidence * 0.75), 2
                ),
                recommended_next_action=opportunity.recommended_action,
                supporting_evidence={
                    "opportunity": opportunity.supporting_evidence,
                    "strategy_health": strategy_health.value,
                },
                metadata={
                    "read_only": True,
                    "aggregation_only": True,
                    "advisory_only": True,
                    "provider_neutral": True,
                },
            )
            for opportunity in ordered
        )

    @classmethod
    def _strategy_signal(
        cls,
        signal_type: str,
        detail: str,
        priority: str,
        confidence: Any,
        evidence: Mapping[str, Any],
    ) -> BusinessStrategySignal:
        return BusinessStrategySignal(
            signal_type=signal_type,
            priority=cls._priority(priority),
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            detail=detail,
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
                "provider_neutral": True,
            },
        )

    def _opportunity_signals(
        self,
        *,
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
        strategy_opportunities: tuple[BusinessStrategyOpportunity, ...],
        revenue_readiness: str,
    ) -> tuple[BusinessOpportunitySignal, ...]:
        signals: list[BusinessOpportunitySignal] = []
        product_count = int(product_summary.get("product_count") or 0)
        customer_count = int(customer_summary.get("customer_count") or 0)
        product_text = " ".join(
            tuple(product_strategy.get("recommendation_types") or ())
            + tuple(product_summary.get("next_actions") or ())
        ).upper()
        commerce_text = " ".join(
            tuple(commerce_strategy.get("objectives") or ())
            + tuple(customer_summary.get("next_actions") or ())
        ).upper()
        combined_text = f"{product_text} {commerce_text}"

        if not product_count:
            signals.append(
                self._business_opportunity_signal(
                    "missing_products",
                    BusinessOpportunityCategory.PRODUCT,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    0.7,
                    "Create missing Product",
                    {"product_business": dict(product_summary)},
                )
            )
        if "FREE" in combined_text or "PREVIEW" in combined_text:
            signals.append(
                self._business_opportunity_signal(
                    "missing_free_previews",
                    BusinessOpportunityCategory.REVENUE,
                    BusinessOpportunityImpact.MEDIUM,
                    "NORMAL",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.58,
                    "Add FREE preview",
                    {
                        "commerce_strategy": dict(commerce_strategy),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if "BUNDLE" in combined_text:
            signals.append(
                self._business_opportunity_signal(
                    "missing_bundles",
                    BusinessOpportunityCategory.REVENUE,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    commerce_strategy.get("confidence")
                    or product_strategy.get("confidence")
                    or 0.62,
                    "Add Bundle",
                    {
                        "commerce_strategy": dict(commerce_strategy),
                        "product_strategy": dict(product_strategy),
                    },
                )
            )
        if publishing.get("failed_count") or publishing.get("waiting_media_link_count"):
            action = (
                "Complete Media Link"
                if publishing.get("waiting_media_link_count")
                else "Improve publishing readiness"
            )
            signals.append(
                self._business_opportunity_signal(
                    "publishing_readiness",
                    BusinessOpportunityCategory.PUBLISHING,
                    BusinessOpportunityImpact.CRITICAL
                    if publishing.get("failed_count")
                    else BusinessOpportunityImpact.HIGH,
                    "CRITICAL" if publishing.get("failed_count") else "HIGH",
                    0.78,
                    action,
                    {"publishing": dict(publishing)},
                )
            )
        if customer_summary.get("growth_opportunity_count"):
            signals.append(
                self._business_opportunity_signal(
                    "customer_growth",
                    BusinessOpportunityCategory.CUSTOMER,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    0.68,
                    "Expand successful Experience",
                    {"customer_business": dict(customer_summary)},
                )
            )
        if customer_summary.get("retention_opportunity_count") or customer_summary.get(
            "at_risk_count"
        ):
            signals.append(
                self._business_opportunity_signal(
                    "customer_retention",
                    BusinessOpportunityCategory.CUSTOMER,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    0.72,
                    "Re-engage at-risk customer",
                    {"customer_business": dict(customer_summary)},
                )
            )
        if customer_summary.get("vip_count"):
            signals.append(
                self._business_opportunity_signal(
                    "vip_development",
                    BusinessOpportunityCategory.CUSTOMER,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    0.66,
                    "Prioritize VIP customer",
                    {"customer_business": dict(customer_summary)},
                )
            )
        if product_summary.get("needs_attention_count"):
            signals.append(
                self._business_opportunity_signal(
                    "product_refresh",
                    BusinessOpportunityCategory.PRODUCT,
                    BusinessOpportunityImpact.HIGH,
                    "HIGH",
                    0.7,
                    "Refresh underperforming Product",
                    {"product_business": dict(product_summary)},
                )
            )
        if strategy_opportunities:
            signals.append(
                self._business_opportunity_signal(
                    "strategy_improvement",
                    BusinessOpportunityCategory.STRATEGY,
                    BusinessOpportunityImpact.MEDIUM,
                    "NORMAL",
                    0.6,
                    "Improve customer journey",
                    {
                        "strategy_opportunities": tuple(
                            opportunity.opportunity_type
                            for opportunity in strategy_opportunities
                        )
                    },
                )
            )
        if revenue_readiness in {"ready", "warming", "needs_media_links"}:
            impact = (
                BusinessOpportunityImpact.HIGH
                if revenue_readiness == "ready"
                else BusinessOpportunityImpact.MEDIUM
            )
            signals.append(
                self._business_opportunity_signal(
                    "revenue_readiness",
                    BusinessOpportunityCategory.REVENUE,
                    impact,
                    "HIGH" if revenue_readiness == "ready" else "NORMAL",
                    0.64,
                    "Prioritize revenue readiness",
                    {"revenue_readiness": revenue_readiness},
                )
            )
        if telegram_summary.get("customer_count"):
            signals.append(
                self._business_opportunity_signal(
                    "telegram_storefront",
                    BusinessOpportunityCategory.TELEGRAM,
                    BusinessOpportunityImpact.MEDIUM,
                    "NORMAL",
                    0.52,
                    "Review Telegram storefront opportunities",
                    {"telegram_business": dict(telegram_summary)},
                )
            )
        if learning.get("available"):
            signals.append(
                self._business_opportunity_signal(
                    "learning_evidence",
                    BusinessOpportunityCategory.LEARNING,
                    BusinessOpportunityImpact.LOW,
                    "LOW",
                    0.45,
                    "Use Business Learning evidence",
                    {"business_learning": dict(learning)},
                )
            )
        if not signals:
            signals.append(
                self._business_opportunity_signal(
                    "baseline",
                    BusinessOpportunityCategory.UNKNOWN,
                    BusinessOpportunityImpact.LOW,
                    "LOW",
                    0.3,
                    "Gather opportunity inputs",
                    {
                        "product_business": dict(product_summary),
                        "customer_business": dict(customer_summary),
                        "publishing": dict(publishing),
                    },
                )
            )
        return tuple(signals)

    @staticmethod
    def _category_opportunities(
        opportunity_signals: tuple[BusinessOpportunitySignal, ...],
        category: BusinessOpportunityCategory,
    ) -> tuple[BusinessOpportunitySignal, ...]:
        return tuple(
            signal for signal in opportunity_signals if signal.category == category
        )

    @staticmethod
    def _opportunity_confidence(
        *,
        opportunity_signals: tuple[BusinessOpportunitySignal, ...],
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> float:
        source_count = sum(
            1
            for summary in (
                product_summary,
                telegram_summary,
                customer_summary,
                product_strategy,
                commerce_strategy,
                publishing,
                learning,
            )
            if summary.get("available")
        )
        signal_confidence = (
            sum(signal.confidence for signal in opportunity_signals)
            / len(opportunity_signals)
            if opportunity_signals
            else 0.0
        )
        confidence = 0.15 + (source_count * 0.08) + (signal_confidence * 0.35)
        return round(max(0.0, min(1.0, confidence)), 2)

    def _opportunity_recommendations(
        self,
        *,
        opportunity_signals: tuple[BusinessOpportunitySignal, ...],
        opportunity_confidence: float,
    ) -> tuple[BusinessOpportunityRecommendation, ...]:
        ordered = sorted(
            opportunity_signals,
            key=lambda item: (
                self._impact_rank(item.impact),
                self._priority_rank(item.priority),
                item.confidence,
            ),
            reverse=True,
        )
        return tuple(
            BusinessOpportunityRecommendation(
                recommendation_type=signal.opportunity_type.upper(),
                category=signal.category,
                impact=signal.impact,
                priority=signal.priority,
                confidence=round(max(signal.confidence, opportunity_confidence * 0.75), 2),
                recommended_next_action=signal.recommended_action,
                supporting_evidence={"opportunity": signal.supporting_evidence},
                metadata={
                    "read_only": True,
                    "aggregation_only": True,
                    "advisory_only": True,
                    "provider_neutral": True,
                },
            )
            for signal in ordered
        )

    @classmethod
    def _business_opportunity_signal(
        cls,
        opportunity_type: str,
        category: BusinessOpportunityCategory,
        impact: BusinessOpportunityImpact,
        priority: str,
        confidence: Any,
        action: str,
        evidence: Mapping[str, Any],
    ) -> BusinessOpportunitySignal:
        return BusinessOpportunitySignal(
            opportunity_type=opportunity_type,
            category=category,
            impact=impact,
            priority=cls._priority(priority),
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            recommended_action=action,
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
                "provider_neutral": True,
            },
        )

    def _recommendation_signals(
        self,
        *,
        opportunity_signals: tuple[BusinessOpportunitySignal, ...],
        performance_signals: tuple[BusinessPerformanceSignal, ...],
        strategy_opportunities: tuple[BusinessStrategyOpportunity, ...],
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[BusinessRecommendationSignal, ...]:
        signals: list[BusinessRecommendationSignal] = []
        for opportunity in opportunity_signals:
            signals.append(
                self._business_recommendation_signal(
                    signal_type=opportunity.opportunity_type,
                    category=self._recommendation_category(opportunity.category),
                    priority=self._recommendation_priority(
                        opportunity.priority, opportunity.impact
                    ),
                    confidence=opportunity.confidence,
                    action=self._recommendation_action(opportunity),
                    timeframe=self._recommendation_timeframe(
                        self._recommendation_priority(
                            opportunity.priority, opportunity.impact
                        )
                    ),
                    evidence={"opportunity": opportunity.supporting_evidence},
                )
            )
        for signal in performance_signals:
            if signal.signal_type == "baseline":
                continue
            signals.append(
                self._business_recommendation_signal(
                    signal_type=f"performance_{signal.signal_type}",
                    category=self._performance_recommendation_category(signal),
                    priority=self._recommendation_priority(signal.priority),
                    confidence=signal.confidence,
                    action=signal.detail,
                    timeframe=self._recommendation_timeframe(
                        self._recommendation_priority(signal.priority)
                    ),
                    evidence={"performance": signal.supporting_evidence},
                )
            )
        for opportunity in strategy_opportunities:
            if opportunity.opportunity_type == "baseline":
                continue
            signals.append(
                self._business_recommendation_signal(
                    signal_type=f"strategy_{opportunity.opportunity_type}",
                    category=BusinessRecommendationCategory.STRATEGY,
                    priority=self._recommendation_priority(opportunity.priority),
                    confidence=opportunity.confidence,
                    action="Review strategy opportunities",
                    timeframe=self._recommendation_timeframe(
                        self._recommendation_priority(opportunity.priority)
                    ),
                    evidence={"strategy": opportunity.supporting_evidence},
                )
            )
        if not signals:
            signals.append(
                self._business_recommendation_signal(
                    signal_type="baseline",
                    category=BusinessRecommendationCategory.UNKNOWN,
                    priority=BusinessRecommendationPriority.LOW,
                    confidence=0.3,
                    action="Gather business recommendation inputs",
                    timeframe="this_week",
                    evidence={
                        "product_business": dict(product_summary),
                        "telegram_business": dict(telegram_summary),
                        "customer_business": dict(customer_summary),
                        "product_strategy": dict(product_strategy),
                        "commerce_strategy": dict(commerce_strategy),
                        "publishing": dict(publishing),
                        "business_learning": dict(learning),
                    },
                )
            )
        return tuple(signals)

    def _prioritized_recommendations(
        self,
        *,
        recommendation_signals: tuple[BusinessRecommendationSignal, ...],
        opportunity_confidence: float,
        performance_confidence: float,
        strategy_confidence: float,
    ) -> tuple[BusinessRecommendationAction, ...]:
        confidence_floor = max(
            opportunity_confidence, performance_confidence, strategy_confidence
        ) * 0.65
        by_action: dict[str, BusinessRecommendationAction] = {}
        for signal in recommendation_signals:
            action = BusinessRecommendationAction(
                action_type=signal.signal_type.upper(),
                category=signal.category,
                priority=signal.priority,
                confidence=round(max(signal.confidence, confidence_floor), 2),
                recommended_action=signal.recommended_action,
                timeframe=signal.timeframe,
                supporting_evidence={"signal": signal.supporting_evidence},
                metadata={
                    "read_only": True,
                    "aggregation_only": True,
                    "advisory_only": True,
                    "provider_neutral": True,
                },
            )
            existing = by_action.get(action.recommended_action)
            if existing is None or self._recommendation_rank(action.priority) > self._recommendation_rank(existing.priority):
                by_action[action.recommended_action] = action
        return tuple(
            sorted(
                by_action.values(),
                key=lambda item: (
                    self._recommendation_rank(item.priority),
                    item.confidence,
                    item.recommended_action,
                ),
                reverse=True,
            )
        )

    @staticmethod
    def _recommendation_confidence(
        *,
        prioritized_recommendations: tuple[BusinessRecommendationAction, ...],
        opportunity_confidence: float,
        performance_confidence: float,
        strategy_confidence: float,
    ) -> float:
        if not prioritized_recommendations:
            return 0.0
        action_confidence = sum(
            action.confidence for action in prioritized_recommendations
        ) / len(prioritized_recommendations)
        aggregate_confidence = (
            opportunity_confidence + performance_confidence + strategy_confidence
        ) / 3
        return round(
            max(0.0, min(1.0, (action_confidence * 0.6) + (aggregate_confidence * 0.4))),
            2,
        )

    @classmethod
    def _business_recommendation_signal(
        cls,
        *,
        signal_type: str,
        category: BusinessRecommendationCategory,
        priority: BusinessRecommendationPriority,
        confidence: Any,
        action: str,
        timeframe: str,
        evidence: Mapping[str, Any],
    ) -> BusinessRecommendationSignal:
        return BusinessRecommendationSignal(
            signal_type=signal_type,
            category=category,
            priority=priority,
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            recommended_action=action,
            timeframe=timeframe,
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
                "provider_neutral": True,
            },
        )

    @staticmethod
    def _recommendation_action(signal: BusinessOpportunitySignal) -> str:
        action_map = {
            "publishing_readiness": (
                "Publish Products awaiting Media Links"
                if signal.recommended_action == "Complete Media Link"
                else "Improve publishing readiness"
            ),
            "missing_free_previews": "Create missing FREE previews",
            "missing_bundles": "Build missing Bundles",
            "customer_growth": "Expand successful Experiences",
            "vip_development": "Prioritize high-value customers",
            "customer_retention": "Re-engage dormant customers",
            "product_refresh": "Refresh underperforming Products",
            "strategy_improvement": "Improve customer journey",
            "missing_products": "Create missing Product",
            "revenue_readiness": "Prioritize revenue readiness",
        }
        return action_map.get(signal.opportunity_type, signal.recommended_action)

    @staticmethod
    def _recommendation_category(
        category: BusinessOpportunityCategory,
    ) -> BusinessRecommendationCategory:
        mapping = {
            BusinessOpportunityCategory.REVENUE: BusinessRecommendationCategory.REVENUE,
            BusinessOpportunityCategory.CUSTOMER: BusinessRecommendationCategory.CUSTOMER,
            BusinessOpportunityCategory.PRODUCT: BusinessRecommendationCategory.PRODUCT,
            BusinessOpportunityCategory.PUBLISHING: BusinessRecommendationCategory.PUBLISHING,
            BusinessOpportunityCategory.STRATEGY: BusinessRecommendationCategory.STRATEGY,
            BusinessOpportunityCategory.TELEGRAM: BusinessRecommendationCategory.TELEGRAM,
            BusinessOpportunityCategory.LEARNING: BusinessRecommendationCategory.LEARNING,
        }
        return mapping.get(category, BusinessRecommendationCategory.UNKNOWN)

    @staticmethod
    def _performance_recommendation_category(
        signal: BusinessPerformanceSignal,
    ) -> BusinessRecommendationCategory:
        if signal.signal_type in {"product_underperformance", "product_portfolio_opportunity"}:
            return BusinessRecommendationCategory.PRODUCT
        if signal.signal_type in {"customer_retention", "vip_development"}:
            return BusinessRecommendationCategory.CUSTOMER
        if signal.signal_type == "publishing_readiness":
            return BusinessRecommendationCategory.PUBLISHING
        if signal.signal_type in {"experience_expansion", "bundle_expansion"}:
            return BusinessRecommendationCategory.STRATEGY
        return BusinessRecommendationCategory.UNKNOWN

    @classmethod
    def _recommendation_priority(
        cls,
        priority: BusinessOptimizationPriority,
        impact: BusinessOpportunityImpact | None = None,
    ) -> BusinessRecommendationPriority:
        if impact == BusinessOpportunityImpact.CRITICAL:
            return BusinessRecommendationPriority.CRITICAL
        if impact == BusinessOpportunityImpact.HIGH:
            return BusinessRecommendationPriority.HIGH
        mapping = {
            BusinessOptimizationPriority.CRITICAL: BusinessRecommendationPriority.CRITICAL,
            BusinessOptimizationPriority.HIGH: BusinessRecommendationPriority.HIGH,
            BusinessOptimizationPriority.NORMAL: BusinessRecommendationPriority.MEDIUM,
            BusinessOptimizationPriority.LOW: BusinessRecommendationPriority.LOW,
        }
        return mapping.get(priority, BusinessRecommendationPriority.MEDIUM)

    @staticmethod
    def _recommendation_timeframe(priority: BusinessRecommendationPriority) -> str:
        if priority in {
            BusinessRecommendationPriority.CRITICAL,
            BusinessRecommendationPriority.HIGH,
        }:
            return "today"
        return "this_week"

    @staticmethod
    def _revenue_readiness(
        *,
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
    ) -> str:
        if publishing.get("failed_count"):
            return "blocked"
        if publishing.get("waiting_media_link_count"):
            return "needs_media_links"
        if (
            product_summary.get("product_count")
            and customer_summary.get("customer_count")
            and commerce_strategy.get("recommendation_count")
        ):
            return "ready"
        if product_summary.get("product_count") or telegram_summary.get("customer_count"):
            return "warming"
        return "unknown"

    def _business_risks(
        self,
        *,
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[Mapping[str, Any], ...]:
        risks: list[Mapping[str, Any]] = []
        if product_summary.get("needs_attention_count"):
            risks.append(self._risk("product_business", "Product Business needs attention", "HIGH"))
        if customer_summary.get("at_risk_count"):
            risks.append(self._risk("customer_business", "Customer Business has at-risk customers", "HIGH"))
        if telegram_summary.get("needs_attention_count"):
            risks.append(self._risk("telegram_business", "Telegram Business needs review", "NORMAL"))
        if publishing.get("failed_count"):
            risks.append(self._risk("publishing", "Publishing failures are blocking readiness", "CRITICAL"))
        if publishing.get("waiting_media_link_count"):
            risks.append(self._risk("publishing", "Media Links are waiting", "HIGH"))
        if not learning.get("available"):
            risks.append(self._risk("business_learning", "Business Learning evidence unavailable", "LOW"))
        return tuple(risks)

    @staticmethod
    def _risk(risk_type: str, detail: str, priority: str) -> Mapping[str, Any]:
        return {
            "risk_type": risk_type,
            "detail": detail,
            "priority": priority,
            "source": "BusinessOptimizationService",
        }

    @staticmethod
    def _health(
        *,
        revenue_readiness: str,
        risks: tuple[Mapping[str, Any], ...],
        product_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
    ) -> BusinessOptimizationHealth:
        priorities = {str(risk.get("priority") or "").upper() for risk in risks}
        if "CRITICAL" in priorities:
            return BusinessOptimizationHealth.AT_RISK
        if "HIGH" in priorities:
            return BusinessOptimizationHealth.NEEDS_ATTENTION
        if revenue_readiness == "ready":
            return BusinessOptimizationHealth.HEALTHY
        if (
            product_summary.get("available")
            or customer_summary.get("available")
            or telegram_summary.get("available")
        ):
            return BusinessOptimizationHealth.OPPORTUNITY
        return BusinessOptimizationHealth.UNKNOWN

    def _opportunities(
        self,
        *,
        health: BusinessOptimizationHealth,
        revenue_readiness: str,
        risks: tuple[Mapping[str, Any], ...],
        product_summary: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        customer_summary: Mapping[str, Any],
        product_strategy: Mapping[str, Any],
        commerce_strategy: Mapping[str, Any],
        publishing: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[BusinessOptimizationOpportunity, ...]:
        opportunities: list[BusinessOptimizationOpportunity] = []
        if publishing.get("waiting_media_link_count"):
            opportunities.append(self._opportunity("publishing", "Resolve Media Link readiness", "HIGH", 0.75, {"publishing": dict(publishing)}))
        if publishing.get("failed_count"):
            opportunities.append(self._opportunity("publishing", "Review publishing failures", "CRITICAL", 0.82, {"publishing": dict(publishing)}))
        if customer_summary.get("growth_opportunity_count"):
            opportunities.append(self._opportunity("customer_growth", "Review Customer growth opportunities", "HIGH", 0.68, {"customer_business": dict(customer_summary)}))
        if customer_summary.get("retention_opportunity_count") or customer_summary.get("at_risk_count"):
            opportunities.append(self._opportunity("customer_retention", "Review Customer retention opportunities", "HIGH", 0.7, {"customer_business": dict(customer_summary)}))
        if product_strategy.get("recommendation_count"):
            opportunities.append(self._opportunity("product_strategy", "Review Product Strategy recommendations", "NORMAL", product_strategy.get("confidence") or 0.55, {"product_strategy": dict(product_strategy)}))
        if commerce_strategy.get("recommendation_count"):
            opportunities.append(self._opportunity("commerce_strategy", "Review Commerce Strategy recommendations", "NORMAL", commerce_strategy.get("confidence") or 0.55, {"commerce_strategy": dict(commerce_strategy)}))
        if product_summary.get("opportunity_count"):
            opportunities.append(self._opportunity("product_business", "Review Product Business opportunities", "NORMAL", 0.55, {"product_business": dict(product_summary)}))
        if telegram_summary.get("customer_count"):
            opportunities.append(self._opportunity("telegram_business", "Review Telegram Business operations", "NORMAL", 0.52, {"telegram_business": dict(telegram_summary)}))
        if learning.get("available"):
            opportunities.append(self._opportunity("business_learning", "Use Business Learning evidence", "LOW", 0.45, {"business_learning": dict(learning)}))
        if not opportunities and health == BusinessOptimizationHealth.UNKNOWN:
            opportunities.append(self._opportunity("baseline", "Gather business optimization inputs", "LOW", 0.3, {"revenue_readiness": revenue_readiness, "risk_count": len(risks)}))
        return tuple(opportunities)

    def _recommendations(
        self,
        *,
        opportunities: tuple[BusinessOptimizationOpportunity, ...],
        health: BusinessOptimizationHealth,
        revenue_readiness: str,
    ) -> tuple[BusinessOptimizationRecommendation, ...]:
        if not opportunities:
            return (
                BusinessOptimizationRecommendation(
                    recommendation_type="NO_BUSINESS_OPTIMIZATION_ACTION",
                    priority=BusinessOptimizationPriority.LOW,
                    confidence=0.3,
                    recommended_next_action="No Business Optimization Action",
                    supporting_evidence={
                        "health": health.value,
                        "revenue_readiness": revenue_readiness,
                    },
                    metadata={"read_only": True, "aggregation_only": True, "advisory_only": True},
                ),
            )
        ordered = sorted(
            opportunities,
            key=lambda item: self._priority_rank(item.priority),
            reverse=True,
        )
        return tuple(
            BusinessOptimizationRecommendation(
                recommendation_type=opportunity.opportunity_type.upper(),
                priority=opportunity.priority,
                confidence=opportunity.confidence,
                recommended_next_action=opportunity.recommended_action,
                supporting_evidence={
                    "opportunity": opportunity.supporting_evidence,
                    "health": health.value,
                    "revenue_readiness": revenue_readiness,
                },
                metadata={"read_only": True, "aggregation_only": True, "advisory_only": True},
            )
            for opportunity in ordered
        )

    @staticmethod
    def _next_action(
        recommendations: tuple[BusinessOptimizationRecommendation, ...],
        opportunities: tuple[BusinessOptimizationOpportunity, ...],
    ) -> str:
        if recommendations:
            return recommendations[0].recommended_next_action
        if opportunities:
            return opportunities[0].recommended_action
        return "Review Business"

    @classmethod
    def _opportunity(
        cls,
        opportunity_type: str,
        action: str,
        priority: str,
        confidence: Any,
        evidence: Mapping[str, Any],
    ) -> BusinessOptimizationOpportunity:
        return BusinessOptimizationOpportunity(
            opportunity_type=opportunity_type,
            priority=cls._priority(priority),
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            recommended_action=action,
            supporting_evidence=dict(evidence),
            metadata={"read_only": True, "aggregation_only": True, "advisory_only": True},
        )

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "business_optimization",
            "owner": "BusinessOptimizationService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "advisory_only": True,
            "executes_telegram": False,
            "modifies_product_business": False,
            "modifies_customer_business": False,
            "modifies_business_learning": False,
            "modifies_product_strategy": False,
            "modifies_commerce_strategy": False,
            "modifies_publishing": False,
            "changes_decision_engine_behavior": False,
            "product_business_owner": "ProductBusinessService",
            "telegram_business_owner": "TelegramBusinessService",
            "customer_business_owner": "CustomerBusinessService",
            "product_strategy_owner": "ProductStrategyService",
            "commerce_strategy_owner": "CommerceStrategyService",
            "business_learning_owner": "BusinessLearningService",
            "publishing_owner": "PublishingService",
            "sources_consumed": {key: value is not None for key, value in sources.items()},
        }

    @staticmethod
    def _items(single: Any | None, many: Iterable[Any] | None) -> tuple[Any, ...]:
        values = []
        if single is not None:
            values.append(single)
        if many is not None:
            values.extend(item for item in many if item is not None)
        return tuple(values)

    @classmethod
    def _read(cls, value: Any, *names: str) -> Any:
        if value is None:
            return None
        current = value
        for name in names:
            if current is None:
                return None
            if isinstance(current, Mapping):
                current = current.get(name)
            else:
                current = getattr(current, name, None)
        return current

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        raw = getattr(value, "value", value)
        if raw in (None, ""):
            return None
        return str(raw)

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _text_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = (value,)
        else:
            try:
                values = tuple(value)
            except TypeError:
                values = (value,)
        return tuple(
            dict.fromkeys(
                text for item in values if (text := cls._safe_text(item)) is not None
            )
        )

    @staticmethod
    def _priority_rank(priority: BusinessOptimizationPriority) -> int:
        return {
            BusinessOptimizationPriority.LOW: 1,
            BusinessOptimizationPriority.NORMAL: 2,
            BusinessOptimizationPriority.HIGH: 3,
            BusinessOptimizationPriority.CRITICAL: 4,
        }.get(priority, 0)

    @staticmethod
    def _impact_rank(impact: BusinessOpportunityImpact) -> int:
        return {
            BusinessOpportunityImpact.UNKNOWN: 0,
            BusinessOpportunityImpact.LOW: 1,
            BusinessOpportunityImpact.MEDIUM: 2,
            BusinessOpportunityImpact.HIGH: 3,
            BusinessOpportunityImpact.CRITICAL: 4,
        }.get(impact, 0)

    @staticmethod
    def _recommendation_rank(priority: BusinessRecommendationPriority) -> int:
        return {
            BusinessRecommendationPriority.LOW: 1,
            BusinessRecommendationPriority.MEDIUM: 2,
            BusinessRecommendationPriority.HIGH: 3,
            BusinessRecommendationPriority.CRITICAL: 4,
        }.get(priority, 0)

    @classmethod
    def _priority(cls, value: Any) -> BusinessOptimizationPriority:
        raw = cls._safe_text(value) or BusinessOptimizationPriority.NORMAL.value
        try:
            return BusinessOptimizationPriority(raw)
        except ValueError:
            try:
                return BusinessOptimizationPriority(raw.upper())
            except ValueError:
                return BusinessOptimizationPriority.NORMAL

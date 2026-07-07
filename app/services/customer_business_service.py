"""Customer Business provider-neutral aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.customer_business import (
    CustomerBusinessHealth,
    CustomerBusinessLifecycleStage,
    CustomerBusinessOpportunity,
    CustomerBusinessPriority,
    CustomerBusinessRecommendation,
    CustomerBusinessSnapshot,
    CustomerBusinessSummary,
    CustomerGrowthOpportunity,
    CustomerGrowthRecommendation,
    CustomerGrowthSignal,
    CustomerGrowthStage,
    CustomerGrowthSummary,
    CustomerRetentionOpportunity,
    CustomerRetentionRecommendation,
    CustomerRetentionRisk,
    CustomerRetentionSignal,
    CustomerRetentionSummary,
    CustomerValueRecommendation,
    CustomerValueSignal,
    CustomerValueSummary,
    CustomerValueTier,
    CustomerValueTrend,
    CustomerJourneyMilestone,
    CustomerJourneyProgress,
    CustomerJourneyRecommendation,
    CustomerJourneyStage,
    CustomerJourneySummary,
)

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.customer_service import CustomerService
    from app.services.delivery_management_service import DeliveryManagementService
    from app.services.product_business_service import ProductBusinessService
    from app.services.relationship_management_service import RelationshipManagementService
    from app.services.sales_management_service import SalesManagementService
    from app.services.telegram_business_service import TelegramBusinessService


class CustomerBusinessService:
    """Build canonical Customer Business snapshots from existing read models.

    Customer Business aggregates and recommends only. It does not execute
    Telegram, mutate Customer Intelligence, modify Products, publish Products,
    record Business Learning, generate Commerce Strategy, or change
    DecisionEngine behavior.
    """

    def __init__(
        self,
        *,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        customer_service: "CustomerService | None" = None,
        telegram_business_service: "TelegramBusinessService | None" = None,
        product_business_service: "ProductBusinessService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
        relationship_management_service: "RelationshipManagementService | None" = None,
        sales_management_service: "SalesManagementService | None" = None,
        delivery_management_service: "DeliveryManagementService | None" = None,
    ) -> None:
        self._customer_intelligence = customer_intelligence_service
        self._customer_service = customer_service
        self._telegram_business = telegram_business_service
        self._product_business = product_business_service
        self._commerce_strategy = commerce_strategy_service
        self._business_learning = business_learning_service
        self._relationship_management = relationship_management_service
        self._sales_management = sales_management_service
        self._delivery_management = delivery_management_service

    @property
    def customer_intelligence(self) -> "CustomerIntelligenceService":
        if self._customer_intelligence is None:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceService,
            )

            self._customer_intelligence = CustomerIntelligenceService()
        return self._customer_intelligence

    def build_snapshot(
        self,
        customer_id: str | int | None = None,
        *,
        provider: str | None = None,
        customer_snapshot: Any | None = None,
        customer_read_model: Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        telegram_business_snapshot: Any | None = None,
        product_business_snapshot: Any | None = None,
        product_business_snapshots: Iterable[Any] | None = None,
        commerce_strategy_result: Any | None = None,
        business_learning_context: Any | None = None,
        business_learning_snapshot: Any | None = None,
        conversation_operation: Any | None = None,
        sales_management: Any | None = None,
        delivery_management: Any | None = None,
        relationship_management: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
        **context: Any,
    ) -> CustomerBusinessSnapshot:
        """Return a provider-neutral Customer Business snapshot."""

        resolved_customer_id = self._safe_text(customer_id)
        if customer_summary is None:
            customer_summary = self._customer_summary(
                customer_id=resolved_customer_id,
                provider=provider,
                context=context,
            )
        if customer_read_model is None:
            customer_read_model = self._customer_read_model(
                customer_id=resolved_customer_id,
                provider=provider,
                context=context,
            )
        if customer_snapshot is None:
            customer_snapshot = self._customer_intelligence_snapshot(
                customer_id=resolved_customer_id,
                provider=provider,
                customer_summary=customer_summary,
                context=context,
            )
        if resolved_customer_id is None:
            resolved_customer_id = self._first_text(
                (
                    self._read(customer_snapshot, "identity", "canonical_customer_id"),
                    self._read(customer_snapshot, "identity", "customer_id"),
                    self._read(customer_summary, "customer_id"),
                    self._read(customer_read_model, "customer_id"),
                    self._read(telegram_business_snapshot, "customer_id"),
                )
            )

        identity = self._identity(
            customer_id=resolved_customer_id,
            provider=provider,
            customer_snapshot=customer_snapshot,
            customer_read_model=customer_read_model,
            customer_summary=customer_summary,
        )
        relationship_stage = self._relationship_stage(
            customer_snapshot=customer_snapshot,
            customer_summary=customer_summary,
            customer_read_model=customer_read_model,
            telegram_business_snapshot=telegram_business_snapshot,
        )
        experience = self._experience_progress(
            customer_snapshot=customer_snapshot,
            customer_summary=customer_summary,
            customer_read_model=customer_read_model,
            telegram_business_snapshot=telegram_business_snapshot,
        )
        product_discovery = self._product_discovery(
            telegram_business_snapshot=telegram_business_snapshot,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            customer_snapshot=customer_snapshot,
            customer_read_model=customer_read_model,
        )
        commerce = self._commerce_readiness(
            customer_snapshot=customer_snapshot,
            customer_summary=customer_summary,
            customer_read_model=customer_read_model,
            telegram_business_snapshot=telegram_business_snapshot,
            commerce_strategy_result=commerce_strategy_result,
            sales_management=sales_management,
            delivery_management=delivery_management,
        )
        telegram_summary = self._telegram_business_summary(telegram_business_snapshot)
        sales = self._sales_signals(sales_management)
        delivery = self._delivery_signals(delivery_management)
        relationship = self._relationship_signals(
            relationship_management=relationship_management,
            customer_snapshot=customer_snapshot,
            relationship_stage=relationship_stage,
        )
        learning = self._learning_evidence(
            business_learning_context=business_learning_context,
            business_learning_snapshot=business_learning_snapshot,
            telegram_business_snapshot=telegram_business_snapshot,
        )
        journey = self._journey_summary(
            relationship_stage=relationship_stage,
            experience=experience,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
        )
        lifecycle = self._lifecycle_stage(
            relationship_stage=relationship_stage,
            journey=journey,
            experience=experience,
            commerce=commerce,
            relationship=relationship,
        )
        health = self._customer_health(
            lifecycle=lifecycle,
            relationship_stage=relationship_stage,
            journey=journey,
            commerce=commerce,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
        )
        customer_journey = self._customer_journey_summary(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            journey=journey,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
        )
        customer_value = self._customer_value_summary(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            commerce_strategy_result=commerce_strategy_result,
        )
        retention = self._customer_retention_summary(
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            experience=experience,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            commerce_strategy_result=commerce_strategy_result,
        )
        growth = self._customer_growth_summary(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            retention=retention,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            commerce_strategy_result=commerce_strategy_result,
        )
        opportunities = self._opportunities(
            health=health,
            lifecycle=lifecycle,
            relationship_stage=relationship_stage,
            journey=journey,
            experience=experience,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
        )
        recommendations = self._recommendations(
            opportunities=opportunities,
            health=health,
            lifecycle=lifecycle,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            journey=journey,
        )
        next_action = self._next_action(
            recommendations,
            opportunities,
            journey,
            customer_journey,
        )
        summary = CustomerBusinessSummary(
            customer_id=resolved_customer_id,
            display_name=self._safe_text(
                self._read(identity, "display_name")
                or self._read(customer_summary, "display_name")
            ),
            provider="provider_neutral",
            relationship_stage=relationship_stage,
            lifecycle_stage=lifecycle,
            health=health,
            current_journey=customer_journey.stage.value,
            current_experience_id=self._safe_text(
                self._read(experience, "current_experience_id")
            ),
            current_product_ids=self._text_tuple(
                self._read(product_discovery, "current_product_ids")
            ),
            active_offer_ids=self._text_tuple(
                self._read(commerce, "active_offer_ids")
            ),
            opportunity_count=len(opportunities),
            recommendation_count=len(recommendations),
            next_recommended_action=next_action,
            compatibility=self._compatibility(),
            metadata={"source": "customer_business_summary"},
        )
        return CustomerBusinessSnapshot(
            customer_id=resolved_customer_id,
            provider="provider_neutral",
            customer_identity=identity,
            relationship_stage=relationship_stage,
            lifecycle_stage=lifecycle,
            customer_health=health,
            current_journey=customer_journey,
            journey_stage=customer_journey.stage,
            completed_milestones=customer_journey.completed_milestones,
            next_milestone=customer_journey.next_milestone,
            current_experience_progress=customer_journey.current_experience_progress,
            recommended_next_experience=customer_journey.recommended_next_experience,
            recommended_next_product_discovery=(
                customer_journey.recommended_next_product_discovery
            ),
            journey_confidence=customer_journey.confidence,
            customer_value=customer_value,
            value_tier=customer_value.tier,
            value_trend=customer_value.trend,
            value_signals=customer_value.signals,
            lifetime_value_summary=customer_value.lifetime_value_summary,
            purchase_potential=customer_value.purchase_potential,
            vip_potential=customer_value.vip_potential,
            retention_risk=customer_value.retention_risk,
            retention_summary=retention,
            retention_signals=retention.signals,
            retention_opportunities=retention.opportunities,
            re_engagement_readiness=retention.re_engagement_readiness,
            last_engagement_summary=retention.last_engagement_summary,
            recommended_follow_up=retention.recommended_follow_up,
            retention_confidence=retention.confidence,
            growth_summary=growth,
            growth_stage=growth.stage,
            growth_opportunities=growth.opportunities,
            growth_signals=growth.signals,
            expansion_readiness=growth.expansion_readiness,
            upsell_readiness=growth.upsell_readiness,
            cross_sell_readiness=growth.cross_sell_readiness,
            vip_growth_readiness=growth.vip_growth_readiness,
            recommended_growth_action=growth.recommended_growth_action,
            growth_confidence=growth.confidence,
            experience_progress=experience,
            product_discovery=product_discovery,
            commerce_readiness=commerce,
            telegram_business=telegram_summary,
            sales_signals=sales,
            delivery_signals=delivery,
            relationship_signals=relationship,
            business_learning_evidence=learning,
            opportunities=opportunities,
            recommendations=recommendations,
            next_recommended_action=next_action,
            summary=summary,
            compatibility=self._compatibility(
                customer_snapshot=customer_snapshot,
                customer_read_model=customer_read_model,
                customer_summary=customer_summary,
                telegram_business_snapshot=telegram_business_snapshot,
                product_business_snapshot=product_business_snapshot,
                product_business_snapshots=product_business_snapshots,
                commerce_strategy_result=commerce_strategy_result,
                business_learning_context=business_learning_context,
                business_learning_snapshot=business_learning_snapshot,
                conversation_operation=conversation_operation,
                sales_management=sales_management,
                delivery_management=delivery_management,
                relationship_management=relationship_management,
            ),
            metadata={
                "source": "customer_business",
                "owner": "CustomerBusinessService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_summary(self, **context: Any) -> CustomerBusinessSummary:
        return self.build_snapshot(**context).summary

    def _customer_summary(
        self,
        *,
        customer_id: str | None,
        provider: str | None,
        context: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        if self._customer_service is None:
            return None
        getter = getattr(self._customer_service, "get_customer_summary", None)
        if not callable(getter):
            return None
        try:
            if provider and context.get("provider_customer_id") is not None:
                return getter(
                    provider=provider,
                    provider_customer_id=context.get("provider_customer_id"),
                    provider_account_id=context.get("provider_account_id"),
                )
            return getter(customer_id)
        except Exception:
            return None

    def _customer_read_model(
        self,
        *,
        customer_id: str | None,
        provider: str | None,
        context: Mapping[str, Any],
    ) -> Any | None:
        if self._customer_service is None:
            return None
        getter = getattr(self._customer_service, "get_customer", None)
        if not callable(getter):
            return None
        try:
            if provider and context.get("provider_customer_id") is not None:
                return getter(
                    provider=provider,
                    provider_customer_id=context.get("provider_customer_id"),
                    provider_account_id=context.get("provider_account_id"),
                )
            return getter(customer_id)
        except Exception:
            return None

    def _customer_intelligence_snapshot(
        self,
        *,
        customer_id: str | None,
        provider: str | None,
        customer_summary: Mapping[str, Any] | None,
        context: Mapping[str, Any],
    ) -> Any | None:
        try:
            return self.customer_intelligence.build_customer_snapshot(
                customer_id=customer_id,
                provider=provider or context.get("provider"),
                provider_customer_id=context.get("provider_customer_id"),
                customer_summary=customer_summary,
            )
        except Exception:
            return None

    def _identity(
        self,
        *,
        customer_id: str | None,
        provider: str | None,
        customer_snapshot: Any,
        customer_read_model: Any,
        customer_summary: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        identity = self._read(customer_snapshot, "identity")
        provider_identities = self._read(identity, "provider_identities")
        if not provider_identities:
            provider_identities = self._read(customer_read_model, "provider_identities")
        return {
            "customer_id": (
                customer_id
                or self._safe_text(self._read(identity, "customer_id"))
                or self._safe_text(self._read(customer_summary, "customer_id"))
            ),
            "canonical_customer_id": self._safe_text(
                self._read(identity, "canonical_customer_id")
            )
            or customer_id,
            "provider": provider or self._safe_text(self._read(identity, "provider")),
            "provider_customer_id": self._safe_text(
                self._read(identity, "provider_customer_id")
            ),
            "display_name": self._safe_text(
                self._read(customer_summary, "display_name")
                or self._read(customer_read_model, "display_name")
                or self._read(customer_snapshot, "profile", "display_name")
            ),
            "provider_identities": self._mapping_or_tuple(provider_identities),
        }

    def _relationship_stage(
        self,
        *,
        customer_snapshot: Any,
        customer_summary: Mapping[str, Any] | None,
        customer_read_model: Any,
        telegram_business_snapshot: Any,
    ) -> str:
        value = (
            self._read(customer_snapshot, "relationship_stage")
            or self._read(customer_snapshot, "relationship_intelligence", "stage")
            or self._read(telegram_business_snapshot, "summary", "relationship_stage")
            or self._read(telegram_business_snapshot, "relationship", "stage")
            or self._read(customer_summary, "relationship_status")
            or self._read(customer_read_model, "relationship", "status")
        )
        return self._safe_text(value) or "unknown"

    def _experience_progress(
        self,
        *,
        customer_snapshot: Any,
        customer_summary: Mapping[str, Any] | None,
        customer_read_model: Any,
        telegram_business_snapshot: Any,
    ) -> dict[str, Any]:
        progress = self._read(customer_snapshot, "experience_progress")
        return {
            "current_experience_id": self._safe_text(
                self._read(progress, "current_experience_id")
                or self._read(customer_summary, "current_experience_id")
                or self._read(customer_read_model, "progression", "current_experience_id")
                or self._read(telegram_business_snapshot, "summary", "current_experience_id")
            ),
            "current_product_id": self._safe_text(
                self._read(progress, "current_product_id")
                or self._read(telegram_business_snapshot, "experience", "current_product_id")
            ),
            "state": self._safe_text(
                self._read(telegram_business_snapshot, "experience", "experience_state")
                or self._read(customer_read_model, "progression", "current_position")
            )
            or "unknown",
            "progress_percentage": self._int(
                self._read(progress, "progress_percentage")
                or self._read(telegram_business_snapshot, "experience", "progress_percentage")
            ),
            "active": bool(
                self._read(progress, "current_experience_id")
                or self._read(customer_read_model, "progression", "active_session")
                or self._read(telegram_business_snapshot, "summary", "current_experience_id")
            ),
            "next_recommended_action": self._safe_text(
                self._read(progress, "next_recommended_experience_action")
                or self._read(
                    telegram_business_snapshot,
                    "experience",
                    "next_recommended_experience_action",
                )
            ),
        }

    def _product_discovery(
        self,
        *,
        telegram_business_snapshot: Any,
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
        customer_snapshot: Any,
        customer_read_model: Any,
    ) -> dict[str, Any]:
        products = self._products(
            telegram_business_snapshot=telegram_business_snapshot,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        current_product_ids = self._text_tuple(
            self._read(telegram_business_snapshot, "summary", "current_product_ids")
            or tuple(self._read(product, "product_id") for product in products)
            or self._read(customer_snapshot, "experience_progress", "current_product_id")
            or self._read(customer_read_model, "recommendation", "recent_product_ids")
        )
        return {
            "current_product_ids": current_product_ids,
            "product_count": len(products) or len(current_product_ids),
            "telegram_ready_count": sum(
                1
                for product in products
                if self._safe_text(self._read(product, "availability"))
                == "TELEGRAM_READY"
            ),
            "owned_product_ids": self._text_tuple(
                self._read(customer_read_model, "ownership", "owned_product_ids")
                or self._read(customer_snapshot, "commerce_memory", "products_purchased")
            ),
            "source": "ProductBusinessService",
        }

    def _commerce_readiness(
        self,
        *,
        customer_snapshot: Any,
        customer_summary: Mapping[str, Any] | None,
        customer_read_model: Any,
        telegram_business_snapshot: Any,
        commerce_strategy_result: Any,
        sales_management: Any,
        delivery_management: Any,
    ) -> dict[str, Any]:
        active_offer_ids = self._text_tuple(
            self._read(telegram_business_snapshot, "summary", "active_offer_ids")
            or tuple(
                self._read(item, "offer_id")
                for item in tuple(self._read(telegram_business_snapshot, "active_offers") or ())
            )
            or self._read(sales_management, "active_offer_ids")
            or self._read(delivery_management, "active_offer_ids")
        )
        purchases = self._int(
            self._read(customer_summary, "purchase_count")
            or self._read(customer_read_model, "relationship", "purchase_count")
            or self._read(
                customer_snapshot,
                "commerce_memory",
                "customer_spending_summary",
                "purchase_count",
            )
        )
        offers = self._int(
            self._read(customer_summary, "offer_count")
            or self._read(customer_read_model, "recommendation", "offer_count")
            or len(active_offer_ids)
        )
        strategy_recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations") or ()
        )
        return {
            "active_offer_ids": active_offer_ids,
            "active_offer_count": len(active_offer_ids),
            "purchase_count": purchases,
            "offer_count": offers,
            "commerce_maturity": self._safe_text(
                self._read(customer_snapshot, "relationship_intelligence", "commerce_maturity")
            )
            or ("buyer" if purchases else ("offer_aware" if offers else "unknown")),
            "ready_for_sales": bool(
                active_offer_ids
                or strategy_recommendations
                or self._read(sales_management, "recommendation")
            ),
            "ready_for_delivery": bool(
                self._read(delivery_management, "recommendation")
                or self._read(telegram_business_snapshot, "delivery_history", "delivery_pending")
            ),
            "strategy_recommendation_count": len(strategy_recommendations),
            "source": "CommerceStrategyService",
        }

    def _telegram_business_summary(self, snapshot: Any) -> dict[str, Any]:
        if snapshot is None:
            return {
                "available": False,
                "provider": "telegram",
                "business_health": "UNKNOWN",
                "operation_status": None,
                "next_recommended_action": None,
            }
        summary = self._read(snapshot, "summary")
        return {
            "available": True,
            "provider": self._safe_text(self._read(snapshot, "provider")) or "telegram",
            "business_health": self._safe_text(
                self._read(snapshot, "business_health")
                or self._read(summary, "business_health")
            )
            or "UNKNOWN",
            "operation_status": self._safe_text(
                self._read(snapshot, "operation_status")
                or self._read(summary, "operation_status")
            ),
            "next_recommended_action": self._safe_text(
                self._read(snapshot, "next_recommended_business_action")
                or self._read(summary, "next_recommended_action")
            ),
            "current_product_ids": self._text_tuple(
                self._read(summary, "current_product_ids")
            ),
            "active_offer_ids": self._text_tuple(
                self._read(summary, "active_offer_ids")
            ),
        }

    def _sales_signals(self, sales_management: Any) -> dict[str, Any]:
        recommendation = self._read(sales_management, "recommendation")
        return {
            "available": sales_management is not None,
            "recommendation_type": self._safe_text(
                self._read(recommendation, "recommendation_type")
            ),
            "priority": self._safe_text(self._read(recommendation, "priority")),
            "confidence": self._float(self._read(recommendation, "confidence")),
            "recommended_next_action": self._safe_text(
                self._read(recommendation, "recommended_next_action")
            ),
            "active_offer_ids": self._text_tuple(
                self._read(sales_management, "active_offer_ids")
            ),
        }

    def _delivery_signals(self, delivery_management: Any) -> dict[str, Any]:
        recommendation = self._read(delivery_management, "recommendation")
        return {
            "available": delivery_management is not None,
            "recommendation_type": self._safe_text(
                self._read(recommendation, "recommendation_type")
            ),
            "priority": self._safe_text(self._read(recommendation, "priority")),
            "confidence": self._float(self._read(recommendation, "confidence")),
            "recommended_next_action": self._safe_text(
                self._read(recommendation, "recommended_next_action")
            ),
            "delivery_history": dict(
                self._read(delivery_management, "delivery_history") or {}
            ),
        }

    def _relationship_signals(
        self,
        *,
        relationship_management: Any,
        customer_snapshot: Any,
        relationship_stage: str,
    ) -> dict[str, Any]:
        recommendation = self._read(relationship_management, "recommendation")
        intelligence = self._read(customer_snapshot, "relationship_intelligence")
        return {
            "available": relationship_management is not None
            or intelligence is not None,
            "management_available": relationship_management is not None,
            "relationship_health": self._safe_text(
                self._read(relationship_management, "relationship_health")
                or self._read(relationship_management, "health")
            ),
            "recommendation_type": self._safe_text(
                self._read(recommendation, "recommendation_type")
            ),
            "priority": self._safe_text(self._read(recommendation, "priority")),
            "confidence": self._float(self._read(recommendation, "confidence")),
            "recommended_next_action": self._safe_text(
                self._read(recommendation, "recommended_next_action")
                or self._read(intelligence, "primary_recommendation")
            ),
            "relationship_stage": relationship_stage,
            "engagement_level": self._safe_text(
                self._read(intelligence, "engagement_level")
            ),
        }

    def _learning_evidence(
        self,
        *,
        business_learning_context: Any,
        business_learning_snapshot: Any,
        telegram_business_snapshot: Any,
    ) -> dict[str, Any]:
        telegram_learning = self._read(telegram_business_snapshot, "business_learning")
        return {
            "available": bool(
                business_learning_context
                or business_learning_snapshot
                or telegram_learning
            ),
            "context_type": self._safe_text(
                self._read(business_learning_context, "context_type")
            ),
            "outcome_count": self._int(
                self._read(business_learning_snapshot, "summary", "total_outcomes")
                or self._read(telegram_learning, "outcome_count")
            ),
            "recommendation_count": self._int(
                self._read(business_learning_snapshot, "summary", "total_recommendations")
                or self._read(telegram_learning, "total_recommendations")
            ),
            "source": "BusinessLearningService",
        }

    @staticmethod
    def _journey_summary(
        *,
        relationship_stage: str,
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
    ) -> dict[str, Any]:
        stage = "relationship"
        if commerce.get("purchase_count"):
            stage = "customer"
        if experience.get("active"):
            stage = "experience"
        if commerce.get("active_offer_count"):
            stage = "offer"
        if delivery.get("recommendation_type") and (
            delivery.get("recommendation_type") != "NO_DELIVERY"
        ):
            stage = "delivery"
        if str(relationship_stage).lower() in {"dormant", "lapsed"}:
            stage = "retention"
        return {
            "stage": stage,
            "relationship_stage": relationship_stage,
            "telegram_available": bool(telegram_summary.get("available")),
            "sales_available": bool(sales.get("available")),
            "delivery_available": bool(delivery.get("available")),
            "commerce_maturity": commerce.get("commerce_maturity"),
        }

    @staticmethod
    def _lifecycle_stage(
        *,
        relationship_stage: str,
        journey: Mapping[str, Any],
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> CustomerBusinessLifecycleStage:
        stage = str(relationship_stage or "").lower()
        health = str(relationship.get("relationship_health") or "").upper()
        if stage == "vip" or health == "VIP_OPPORTUNITY":
            return CustomerBusinessLifecycleStage.VIP
        if stage in {"dormant", "lapsed"}:
            return CustomerBusinessLifecycleStage.DORMANT
        if commerce.get("purchase_count", 0) >= 2 or stage == "repeat_purchaser":
            return CustomerBusinessLifecycleStage.REPEAT_CUSTOMER
        if commerce.get("purchase_count", 0) >= 1 or stage == "purchaser":
            return CustomerBusinessLifecycleStage.CUSTOMER
        if commerce.get("active_offer_count"):
            return CustomerBusinessLifecycleStage.OFFER_ACTIVE
        if experience.get("active"):
            return CustomerBusinessLifecycleStage.EXPERIENCE_ACTIVE
        if stage in {"active", "engaged", "returning"}:
            return CustomerBusinessLifecycleStage.ACTIVE_RELATIONSHIP
        if stage in {"new", "unknown", ""}:
            return CustomerBusinessLifecycleStage.NEW
        if journey.get("stage") == "relationship":
            return CustomerBusinessLifecycleStage.DISCOVERY
        return CustomerBusinessLifecycleStage.UNKNOWN

    @staticmethod
    def _customer_health(
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        relationship_stage: str,
        journey: Mapping[str, Any],
        commerce: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> CustomerBusinessHealth:
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if lifecycle == CustomerBusinessLifecycleStage.VIP:
            return CustomerBusinessHealth.VIP
        if lifecycle == CustomerBusinessLifecycleStage.DORMANT:
            return CustomerBusinessHealth.DORMANT
        if relationship_health in {"AT_RISK", "DISENGAGED"}:
            return CustomerBusinessHealth.AT_RISK
        if str(sales.get("priority") or "").upper() == "CRITICAL":
            return CustomerBusinessHealth.NEEDS_ATTENTION
        if str(delivery.get("priority") or "").upper() in {"HIGH", "CRITICAL"}:
            return CustomerBusinessHealth.OPPORTUNITY
        if commerce.get("active_offer_count") or commerce.get("ready_for_sales"):
            return CustomerBusinessHealth.OPPORTUNITY
        if lifecycle in {
            CustomerBusinessLifecycleStage.ACTIVE_RELATIONSHIP,
            CustomerBusinessLifecycleStage.EXPERIENCE_ACTIVE,
            CustomerBusinessLifecycleStage.CUSTOMER,
            CustomerBusinessLifecycleStage.REPEAT_CUSTOMER,
        }:
            return CustomerBusinessHealth.HEALTHY
        if learning.get("available") and journey.get("telegram_available"):
            return CustomerBusinessHealth.HEALTHY
        if str(relationship_stage or "").lower() in {"new", "unknown"}:
            return CustomerBusinessHealth.UNKNOWN
        return CustomerBusinessHealth.UNKNOWN

    def _customer_journey_summary(
        self,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        journey: Mapping[str, Any],
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> CustomerJourneySummary:
        stage = self._customer_journey_stage(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            sales=sales,
            relationship=relationship,
        )
        milestones = self._journey_milestones(
            stage=stage,
            relationship_stage=relationship_stage,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            learning=learning,
        )
        completed = tuple(milestone for milestone in milestones if milestone.completed)
        next_milestone = next(
            (milestone for milestone in milestones if not milestone.completed),
            None,
        )
        confidence = self._journey_confidence(
            completed_count=len(completed),
            total_count=len(milestones),
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
        )
        recommendations = self._journey_recommendations(
            stage=stage,
            health=health,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            journey=journey,
            confidence=confidence,
        )
        progress_percentage = (
            int(round((len(completed) / len(milestones)) * 100))
            if milestones
            else 0
        )
        return CustomerJourneySummary(
            stage=stage,
            completed_milestones=completed,
            next_milestone=next_milestone,
            progress=CustomerJourneyProgress(
                stage=stage,
                completed_count=len(completed),
                total_count=len(milestones),
                progress_percentage=progress_percentage,
                confidence=confidence,
                metadata={
                    "read_only": True,
                    "aggregation_only": True,
                },
            ),
            current_experience_progress=dict(experience),
            recommended_next_experience=self._recommended_next_experience(
                experience,
                recommendations,
            ),
            recommended_next_product_discovery=(
                self._recommended_next_product_discovery(
                    product_discovery,
                    sales,
                    commerce,
                    recommendations,
                )
            ),
            recommendations=recommendations,
            confidence=confidence,
            compatibility={
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "customer_intelligence_owner": "CustomerIntelligenceService",
                "commerce_strategy_owner": "CommerceStrategyService",
                "telegram_business_owner": "TelegramBusinessService",
                "product_business_owner": "ProductBusinessService",
                "business_learning_owner": "BusinessLearningService",
            },
            metadata={
                "source": "customer_business_journey",
                "advisory_only": True,
            },
        )

    @staticmethod
    def _customer_journey_stage(
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        sales: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> CustomerJourneyStage:
        stage = str(relationship_stage or "").lower()
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if lifecycle == CustomerBusinessLifecycleStage.VIP:
            return CustomerJourneyStage.VIP_GROWTH
        if commerce.get("purchase_count", 0) >= 2:
            return CustomerJourneyStage.REPEAT_BUYER
        if commerce.get("purchase_count", 0) >= 1:
            return CustomerJourneyStage.ACTIVE_BUYER
        if health == CustomerBusinessHealth.AT_RISK or relationship_health in {
            "AT_RISK",
            "DISENGAGED",
        }:
            return CustomerJourneyStage.RETENTION
        if health == CustomerBusinessHealth.DORMANT or stage in {"dormant", "lapsed"}:
            return CustomerJourneyStage.RE_ENGAGEMENT
        if (
            commerce.get("active_offer_count")
            or product_discovery.get("current_product_ids")
            or sales.get("recommendation_type")
        ):
            return CustomerJourneyStage.PRODUCT_DISCOVERY
        if experience.get("active") or stage in {"active", "engaged", "returning"}:
            return CustomerJourneyStage.RELATIONSHIP_BUILDING
        return CustomerJourneyStage.NEW_CUSTOMER

    def _journey_milestones(
        self,
        *,
        stage: CustomerJourneyStage,
        relationship_stage: str,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[CustomerJourneyMilestone, ...]:
        relationship_started = str(relationship_stage or "").lower() not in {
            "",
            "unknown",
            "new",
        }
        milestones = (
            self._milestone(
                "identity_known",
                "Customer identity known",
                True,
                {"relationship_stage": relationship_stage},
            ),
            self._milestone(
                "relationship_started",
                "Relationship started",
                relationship_started,
                {"relationship_stage": relationship_stage},
            ),
            self._milestone(
                "experience_started",
                "Experience started",
                bool(experience.get("active")),
                {"experience": experience},
            ),
            self._milestone(
                "product_discovered",
                "Product discovered",
                bool(product_discovery.get("current_product_ids")),
                {"product_discovery": product_discovery},
            ),
            self._milestone(
                "offer_presented",
                "Offer presented",
                bool(commerce.get("active_offer_count") or commerce.get("offer_count")),
                {"commerce": commerce},
            ),
            self._milestone(
                "purchase_completed",
                "Purchase completed",
                commerce.get("purchase_count", 0) >= 1,
                {"commerce": commerce},
            ),
            self._milestone(
                "repeat_purchase",
                "Repeat purchase",
                commerce.get("purchase_count", 0) >= 2,
                {"commerce": commerce},
            ),
            self._milestone(
                "vip_identified",
                "VIP identified",
                stage == CustomerJourneyStage.VIP_GROWTH,
                {"learning": learning, "telegram_business": telegram_summary},
            ),
        )
        return milestones

    @staticmethod
    def _milestone(
        milestone_id: str,
        label: str,
        completed: bool,
        evidence: Mapping[str, Any],
    ) -> CustomerJourneyMilestone:
        return CustomerJourneyMilestone(
            milestone_id=milestone_id,
            label=label,
            completed=bool(completed),
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
            },
        )

    @classmethod
    def _journey_recommendations(
        cls,
        *,
        stage: CustomerJourneyStage,
        health: CustomerBusinessHealth,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        journey: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerJourneyRecommendation, ...]:
        if stage in {CustomerJourneyStage.RETENTION, CustomerJourneyStage.RE_ENGAGEMENT}:
            return (
                cls._journey_recommendation(
                    "RE_ENGAGE_CUSTOMER",
                    "Re-engage customer",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.68),
                    health,
                    journey,
                ),
            )
        sales_type = str(sales.get("recommendation_type") or "")
        sales_action = sales.get("recommended_next_action")
        if "DELAY" in sales_type:
            return (
                cls._journey_recommendation(
                    "DELAY_SELLING",
                    "Delay selling",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, sales.get("confidence") or 0.6),
                    health,
                    journey,
                ),
            )
        if sales_action:
            action_text = str(sales_action)
            recommendation_type = "RECOMMEND_PREMIUM_PRODUCT"
            if "free" in action_text.lower() or "preview" in action_text.lower():
                recommendation_type = "RECOMMEND_FREE_PREVIEW"
            return (
                cls._journey_recommendation(
                    recommendation_type,
                    action_text,
                    cls._priority(sales.get("priority")),
                    max(confidence, sales.get("confidence") or 0.62),
                    health,
                    journey,
                ),
            )
        if delivery.get("recommended_next_action"):
            return (
                cls._journey_recommendation(
                    "CONTINUE_CURRENT_EXPERIENCE",
                    str(delivery["recommended_next_action"]),
                    cls._priority(delivery.get("priority")),
                    max(confidence, delivery.get("confidence") or 0.58),
                    health,
                    journey,
                ),
            )
        if experience.get("active"):
            return (
                cls._journey_recommendation(
                    "CONTINUE_CURRENT_EXPERIENCE",
                    experience.get("next_recommended_action")
                    or "Continue current Experience",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.58),
                    health,
                    journey,
                ),
            )
        if product_discovery.get("current_product_ids") or commerce.get("ready_for_sales"):
            return (
                cls._journey_recommendation(
                    "RECOMMEND_FREE_PREVIEW",
                    "Recommend FREE preview",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.56),
                    health,
                    journey,
                ),
            )
        relationship_action = relationship.get("recommended_next_action")
        relationship_stage = str(journey.get("relationship_stage") or "").lower()
        if relationship_action and relationship_stage not in {"new", "unknown", ""}:
            return (
                cls._journey_recommendation(
                    "CONTINUE_RELATIONSHIP",
                    str(relationship_action),
                    cls._priority(relationship.get("priority")),
                    max(confidence, relationship.get("confidence") or 0.52),
                    health,
                    journey,
                ),
            )
        if stage == CustomerJourneyStage.NEW_CUSTOMER:
            return (
                cls._journey_recommendation(
                    "CONTINUE_RELATIONSHIP",
                    "Continue relationship",
                    CustomerBusinessPriority.LOW,
                    max(confidence, 0.4),
                    health,
                    journey,
                ),
            )
        return (
            cls._journey_recommendation(
                "INTRODUCE_NEXT_EXPERIENCE",
                "Introduce next Experience",
                CustomerBusinessPriority.NORMAL,
                max(confidence, 0.5),
                health,
                journey,
            ),
        )

    @staticmethod
    def _journey_confidence(
        *,
        completed_count: int,
        total_count: int,
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> float:
        confidence = 0.35
        if total_count:
            confidence += min(0.25, completed_count / total_count * 0.25)
        if telegram_summary.get("available"):
            confidence += 0.08
        if sales.get("available"):
            confidence += 0.08
        if delivery.get("available"):
            confidence += 0.06
        if relationship.get("available"):
            confidence += 0.06
        if learning.get("available"):
            confidence += 0.05
        return round(max(0.0, min(1.0, confidence)), 2)

    @staticmethod
    def _journey_recommendation(
        recommendation_type: str,
        action: Any,
        priority: CustomerBusinessPriority,
        confidence: float,
        health: CustomerBusinessHealth,
        journey: Mapping[str, Any],
    ) -> CustomerJourneyRecommendation:
        return CustomerJourneyRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_next_action=str(action),
            supporting_evidence={
                "health": health.value,
                "journey": dict(journey),
            },
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
            },
        )

    @classmethod
    def _recommended_next_experience(
        cls,
        experience: Mapping[str, Any],
        recommendations: tuple[CustomerJourneyRecommendation, ...],
    ) -> str | None:
        if experience.get("active"):
            return cls._safe_text(experience.get("next_recommended_action")) or (
                "Continue current Experience"
            )
        for recommendation in recommendations:
            if "EXPERIENCE" in recommendation.recommendation_type:
                return recommendation.recommended_next_action
        return None

    @classmethod
    def _recommended_next_product_discovery(
        cls,
        product_discovery: Mapping[str, Any],
        sales: Mapping[str, Any],
        commerce: Mapping[str, Any],
        recommendations: tuple[CustomerJourneyRecommendation, ...],
    ) -> str | None:
        if sales.get("recommended_next_action"):
            return cls._safe_text(sales.get("recommended_next_action"))
        for recommendation in recommendations:
            if "PRODUCT" in recommendation.recommendation_type or (
                "PREVIEW" in recommendation.recommendation_type
            ):
                return recommendation.recommended_next_action
        if product_discovery.get("current_product_ids") or commerce.get("ready_for_sales"):
            return "Recommend FREE preview"
        return None

    def _customer_value_summary(
        self,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
        commerce_strategy_result: Any,
    ) -> CustomerValueSummary:
        lifetime = self._lifetime_value_summary(
            commerce=commerce,
            delivery=delivery,
            learning=learning,
        )
        signals = self._value_signals(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            lifetime=lifetime,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            commerce_strategy_result=commerce_strategy_result,
        )
        tier = self._value_tier(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            commerce=commerce,
            relationship=relationship,
            lifetime=lifetime,
            signals=signals,
        )
        trend = self._value_trend(
            tier=tier,
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            commerce=commerce,
            sales=sales,
            relationship=relationship,
            learning=learning,
        )
        purchase_potential = self._purchase_potential(
            tier=tier,
            commerce=commerce,
            sales=sales,
            product_discovery=product_discovery,
        )
        vip_potential = self._vip_potential(
            tier=tier,
            commerce=commerce,
            relationship=relationship,
            lifetime=lifetime,
            sales=sales,
            learning=learning,
        )
        retention_risk = self._retention_risk(
            tier=tier,
            trend=trend,
            health=health,
            relationship_stage=relationship_stage,
            relationship=relationship,
        )
        growth = self._growth_opportunities(
            tier=tier,
            purchase_potential=purchase_potential,
            vip_potential=vip_potential,
            retention_risk=retention_risk,
            sales=sales,
            product_discovery=product_discovery,
            commerce=commerce,
        )
        confidence = self._value_confidence(
            signals=signals,
            telegram_summary=telegram_summary,
            learning=learning,
            sales=sales,
            relationship=relationship,
        )
        recommendations = self._value_recommendations(
            tier=tier,
            trend=trend,
            purchase_potential=purchase_potential,
            vip_potential=vip_potential,
            retention_risk=retention_risk,
            growth_opportunities=growth,
            sales=sales,
            confidence=confidence,
        )
        return CustomerValueSummary(
            tier=tier,
            trend=trend,
            signals=signals,
            lifetime_value_summary=lifetime,
            purchase_potential=purchase_potential,
            vip_potential=vip_potential,
            retention_risk=retention_risk,
            growth_opportunities=growth,
            recommendations=recommendations,
            confidence=confidence,
            compatibility={
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "advisory_only": True,
                "customer_intelligence_owner": "CustomerIntelligenceService",
                "business_learning_owner": "BusinessLearningService",
                "product_business_owner": "ProductBusinessService",
                "telegram_business_owner": "TelegramBusinessService",
                "commerce_strategy_owner": "CommerceStrategyService",
            },
            metadata={"source": "customer_business_value"},
        )

    @classmethod
    def _lifetime_value_summary(
        cls,
        *,
        commerce: Mapping[str, Any],
        delivery: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> dict[str, Any]:
        delivery_history = delivery.get("delivery_history") or {}
        return {
            "purchase_count": cls._int(commerce.get("purchase_count")),
            "offer_count": cls._int(commerce.get("offer_count")),
            "active_offer_count": cls._int(commerce.get("active_offer_count")),
            "delivery_count": cls._int(delivery_history.get("delivery_count")),
            "learning_outcome_count": cls._int(learning.get("outcome_count")),
            "learning_recommendation_count": cls._int(
                learning.get("recommendation_count")
            ),
        }

    def _value_signals(
        self,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        lifetime: Mapping[str, Any],
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
        commerce_strategy_result: Any,
    ) -> tuple[CustomerValueSignal, ...]:
        products = self._products(
            telegram_business_snapshot=None,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        strategy_recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations") or ()
        )
        return tuple(
            signal
            for signal in (
                self._value_signal(
                    "relationship_stage",
                    relationship_stage,
                    0.14,
                    {
                        "lifecycle": lifecycle.value,
                        "relationship_health": relationship.get(
                            "relationship_health"
                        ),
                    },
                ),
                self._value_signal(
                    "purchase_history",
                    lifetime.get("purchase_count"),
                    0.22,
                    {"commerce": dict(commerce)},
                ),
                self._value_signal(
                    "offer_activity",
                    lifetime.get("offer_count"),
                    0.1,
                    {"commerce": dict(commerce)},
                ),
                self._value_signal(
                    "journey_stage",
                    customer_journey.stage.value,
                    0.12,
                    {"journey_confidence": customer_journey.confidence},
                ),
                self._value_signal(
                    "experience_activity",
                    bool(experience.get("active")),
                    0.08,
                    {"experience": dict(experience)},
                ),
                self._value_signal(
                    "product_discovery",
                    product_discovery.get("product_count"),
                    0.08,
                    {
                        "product_count": product_discovery.get("product_count"),
                        "telegram_ready_count": product_discovery.get(
                            "telegram_ready_count"
                        ),
                        "product_business_snapshot_count": len(products),
                    },
                ),
                self._value_signal(
                    "sales_opportunity",
                    sales.get("recommendation_type"),
                    0.1,
                    {"sales": dict(sales)},
                ),
                self._value_signal(
                    "delivery_history",
                    lifetime.get("delivery_count"),
                    0.06,
                    {"delivery": dict(delivery)},
                ),
                self._value_signal(
                    "business_learning_evidence",
                    learning.get("outcome_count"),
                    0.05,
                    {"learning": dict(learning)},
                ),
                self._value_signal(
                    "commerce_strategy_signal",
                    len(strategy_recommendations),
                    0.05,
                    {"recommendation_count": len(strategy_recommendations)},
                ),
                self._value_signal(
                    "telegram_business_state",
                    telegram_summary.get("business_health"),
                    0.05,
                    {"telegram_business": dict(telegram_summary)},
                ),
                self._value_signal(
                    "customer_health",
                    health.value,
                    0.1,
                    {"health": health.value},
                ),
            )
            if signal is not None
        )

    @staticmethod
    def _value_signal(
        signal_type: str,
        value: Any,
        weight: float,
        evidence: Mapping[str, Any],
    ) -> CustomerValueSignal:
        return CustomerValueSignal(
            signal_type=signal_type,
            value=value,
            weight=round(max(0.0, min(1.0, float(weight or 0.0))), 2),
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
            },
        )

    @classmethod
    def _value_tier(
        cls,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        commerce: Mapping[str, Any],
        relationship: Mapping[str, Any],
        lifetime: Mapping[str, Any],
        signals: tuple[CustomerValueSignal, ...],
    ) -> CustomerValueTier:
        stage = str(relationship_stage or "").lower()
        purchase_count = cls._int(lifetime.get("purchase_count"))
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if health == CustomerBusinessHealth.DORMANT or stage in {"dormant", "lapsed"}:
            return CustomerValueTier.DORMANT
        if health == CustomerBusinessHealth.AT_RISK or relationship_health in {
            "AT_RISK",
            "DISENGAGED",
        }:
            return CustomerValueTier.AT_RISK
        if lifecycle == CustomerBusinessLifecycleStage.VIP or stage == "vip":
            return CustomerValueTier.VIP
        if purchase_count >= 3 or relationship_health == "VIP_OPPORTUNITY":
            return CustomerValueTier.VIP_POTENTIAL
        if purchase_count >= 2:
            return CustomerValueTier.REPEAT_BUYER
        if purchase_count >= 1 or stage == "purchaser":
            return CustomerValueTier.BUYER
        if commerce.get("active_offer_count") or commerce.get("ready_for_sales"):
            return CustomerValueTier.ENGAGED
        if stage in {"active", "engaged", "returning"}:
            return CustomerValueTier.ENGAGED
        if stage == "new":
            return CustomerValueTier.NEW
        return CustomerValueTier.UNKNOWN if not signals else CustomerValueTier.NEW

    @classmethod
    def _value_trend(
        cls,
        *,
        tier: CustomerValueTier,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        commerce: Mapping[str, Any],
        sales: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> CustomerValueTrend:
        stage = str(relationship_stage or "").lower()
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if tier == CustomerValueTier.DORMANT or health == CustomerBusinessHealth.DORMANT:
            return CustomerValueTrend.DORMANT
        if tier == CustomerValueTier.AT_RISK or relationship_health in {
            "AT_RISK",
            "DISENGAGED",
        }:
            return CustomerValueTrend.DECLINING
        if tier in {
            CustomerValueTier.VIP_POTENTIAL,
            CustomerValueTier.VIP,
            CustomerValueTier.HIGH_VALUE,
        }:
            return CustomerValueTrend.RISING
        if sales.get("recommendation_type") or commerce.get("active_offer_count"):
            return CustomerValueTrend.RISING
        if learning.get("available") or customer_journey.confidence >= 0.55:
            return CustomerValueTrend.STABLE
        if stage == "new" or tier == CustomerValueTier.NEW:
            return CustomerValueTrend.NEW
        return CustomerValueTrend.UNKNOWN

    @staticmethod
    def _purchase_potential(
        *,
        tier: CustomerValueTier,
        commerce: Mapping[str, Any],
        sales: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
    ) -> str:
        if tier in {CustomerValueTier.DORMANT, CustomerValueTier.AT_RISK}:
            return "low"
        if tier in {
            CustomerValueTier.BUYER,
            CustomerValueTier.REPEAT_BUYER,
            CustomerValueTier.HIGH_VALUE,
            CustomerValueTier.VIP_POTENTIAL,
            CustomerValueTier.VIP,
        }:
            return "high"
        if sales.get("recommendation_type") or commerce.get("active_offer_count"):
            return "medium"
        if product_discovery.get("current_product_ids"):
            return "medium"
        if tier == CustomerValueTier.ENGAGED:
            return "medium"
        return "unknown"

    @classmethod
    def _vip_potential(
        cls,
        *,
        tier: CustomerValueTier,
        commerce: Mapping[str, Any],
        relationship: Mapping[str, Any],
        lifetime: Mapping[str, Any],
        sales: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> bool:
        if tier in {CustomerValueTier.VIP, CustomerValueTier.VIP_POTENTIAL}:
            return True
        if cls._int(lifetime.get("purchase_count")) >= 3:
            return True
        if str(relationship.get("relationship_health") or "").upper() == "VIP_OPPORTUNITY":
            return True
        if sales.get("priority") == "HIGH" and learning.get("available"):
            return True
        return False

    @staticmethod
    def _retention_risk(
        *,
        tier: CustomerValueTier,
        trend: CustomerValueTrend,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        relationship: Mapping[str, Any],
    ) -> str:
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if tier == CustomerValueTier.DORMANT or trend == CustomerValueTrend.DORMANT:
            return "high"
        if tier == CustomerValueTier.AT_RISK or relationship_health in {
            "AT_RISK",
            "DISENGAGED",
        }:
            return "high"
        if health == CustomerBusinessHealth.NEEDS_ATTENTION:
            return "medium"
        if str(relationship_stage or "").lower() in {"dormant", "lapsed"}:
            return "high"
        if trend == CustomerValueTrend.DECLINING:
            return "medium"
        return "low"

    @staticmethod
    def _growth_opportunities(
        *,
        tier: CustomerValueTier,
        purchase_potential: str,
        vip_potential: bool,
        retention_risk: str,
        sales: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
    ) -> tuple[str, ...]:
        opportunities: list[str] = []
        if retention_risk == "high":
            opportunities.append("retention")
        if vip_potential:
            opportunities.append("vip_growth")
        if purchase_potential in {"medium", "high"}:
            opportunities.append("purchase_growth")
        if sales.get("recommendation_type"):
            opportunities.append("sales_follow_up")
        if product_discovery.get("current_product_ids"):
            opportunities.append("product_discovery")
        if commerce.get("active_offer_count"):
            opportunities.append("offer_conversion")
        if tier == CustomerValueTier.NEW:
            opportunities.append("relationship_building")
        return tuple(dict.fromkeys(opportunities))

    @classmethod
    def _value_recommendations(
        cls,
        *,
        tier: CustomerValueTier,
        trend: CustomerValueTrend,
        purchase_potential: str,
        vip_potential: bool,
        retention_risk: str,
        growth_opportunities: tuple[str, ...],
        sales: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerValueRecommendation, ...]:
        if retention_risk == "high" or tier == CustomerValueTier.DORMANT:
            return (
                cls._value_recommendation(
                    "RE_ENGAGE_DORMANT_CUSTOMER",
                    "Re-engage dormant customer",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.7),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        if vip_potential:
            return (
                cls._value_recommendation(
                    "NURTURE_VIP_POTENTIAL",
                    "Nurture VIP potential",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.68),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        sales_action = str(sales.get("recommended_next_action") or "")
        if "bundle" in sales_action.lower():
            return (
                cls._value_recommendation(
                    "RECOMMEND_BUNDLE",
                    "Recommend bundle",
                    cls._priority(sales.get("priority")),
                    max(confidence, sales.get("confidence") or 0.62),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        if purchase_potential == "high":
            return (
                cls._value_recommendation(
                    "INTRODUCE_PREMIUM_PRODUCT",
                    "Introduce premium Product",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.64),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        if purchase_potential == "medium":
            return (
                cls._value_recommendation(
                    "OFFER_FREE_PREVIEW",
                    "Offer FREE preview",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.58),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        if tier == CustomerValueTier.AT_RISK or trend == CustomerValueTrend.DECLINING:
            return (
                cls._value_recommendation(
                    "REDUCE_SALES_PRESSURE",
                    "Reduce sales pressure",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.6),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        if "sales_follow_up" in growth_opportunities:
            return (
                cls._value_recommendation(
                    "PRIORITIZE_FOLLOW_UP",
                    "Prioritize follow-up",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.56),
                    tier,
                    trend,
                    growth_opportunities,
                ),
            )
        return (
            cls._value_recommendation(
                "BUILD_RELATIONSHIP",
                "Build relationship",
                CustomerBusinessPriority.LOW,
                max(confidence, 0.4),
                tier,
                trend,
                growth_opportunities,
            ),
        )

    @staticmethod
    def _value_confidence(
        *,
        signals: tuple[CustomerValueSignal, ...],
        telegram_summary: Mapping[str, Any],
        learning: Mapping[str, Any],
        sales: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> float:
        confidence = min(0.45, sum(signal.weight for signal in signals) / 2)
        if telegram_summary.get("available"):
            confidence += 0.08
        if learning.get("available"):
            confidence += 0.07
        if sales.get("available"):
            confidence += 0.08
        if relationship.get("available"):
            confidence += 0.06
        return round(max(0.0, min(1.0, confidence)), 2)

    @staticmethod
    def _value_recommendation(
        recommendation_type: str,
        action: str,
        priority: CustomerBusinessPriority,
        confidence: float,
        tier: CustomerValueTier,
        trend: CustomerValueTrend,
        growth_opportunities: tuple[str, ...],
    ) -> CustomerValueRecommendation:
        return CustomerValueRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_next_action=action,
            supporting_evidence={
                "value_tier": tier.value,
                "value_trend": trend.value,
                "growth_opportunities": growth_opportunities,
            },
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
            },
        )

    def _customer_retention_summary(
        self,
        *,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        commerce_strategy_result: Any,
    ) -> CustomerRetentionSummary:
        last_engagement = self._last_engagement_summary(
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            experience=experience,
            commerce=commerce,
            telegram_summary=telegram_summary,
            delivery=delivery,
            relationship=relationship,
        )
        signals = self._retention_signals(
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            experience=experience,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            last_engagement=last_engagement,
            commerce_strategy_result=commerce_strategy_result,
        )
        risk = self._retention_state(
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            sales=sales,
            relationship=relationship,
        )
        readiness = self._re_engagement_readiness(
            risk=risk,
            customer_value=customer_value,
            sales=sales,
            relationship=relationship,
        )
        confidence = self._retention_confidence(
            signals=signals,
            telegram_summary=telegram_summary,
            learning=learning,
            relationship=relationship,
        )
        opportunities = self._retention_opportunities(
            risk=risk,
            readiness=readiness,
            customer_value=customer_value,
            customer_journey=customer_journey,
            experience=experience,
            sales=sales,
            confidence=confidence,
        )
        recommendations = self._retention_recommendations(
            risk=risk,
            readiness=readiness,
            customer_value=customer_value,
            customer_journey=customer_journey,
            experience=experience,
            sales=sales,
            confidence=confidence,
        )
        follow_up = (
            recommendations[0].recommended_next_action
            if recommendations
            else "Recommend follow-up"
        )
        return CustomerRetentionSummary(
            risk=risk,
            signals=signals,
            opportunities=opportunities,
            re_engagement_readiness=readiness,
            last_engagement_summary=last_engagement,
            recommended_follow_up=follow_up,
            recommendations=recommendations,
            confidence=confidence,
            compatibility={
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "advisory_only": True,
                "customer_intelligence_owner": "CustomerIntelligenceService",
                "relationship_management_owner": "RelationshipManagementService",
                "business_learning_owner": "BusinessLearningService",
                "commerce_strategy_owner": "CommerceStrategyService",
                "telegram_business_owner": "TelegramBusinessService",
            },
            metadata={"source": "customer_business_retention"},
        )

    @staticmethod
    def _last_engagement_summary(
        *,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "relationship_stage": relationship_stage,
            "journey_stage": customer_journey.stage.value,
            "value_tier": customer_value.tier.value,
            "value_trend": customer_value.trend.value,
            "experience_active": bool(experience.get("active")),
            "current_experience_id": experience.get("current_experience_id"),
            "purchase_count": commerce.get("purchase_count", 0),
            "offer_count": commerce.get("offer_count", 0),
            "delivery_count": (
                (delivery.get("delivery_history") or {}).get("delivery_count", 0)
            ),
            "telegram_operation_status": telegram_summary.get("operation_status"),
            "relationship_health": relationship.get("relationship_health"),
        }

    def _retention_signals(
        self,
        *,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        last_engagement: Mapping[str, Any],
        commerce_strategy_result: Any,
    ) -> tuple[CustomerRetentionSignal, ...]:
        strategy_recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations") or ()
        )
        return (
            self._retention_signal(
                "customer_health",
                health.value,
                0.14,
                {"health": health.value},
            ),
            self._retention_signal(
                "relationship_stage",
                relationship_stage,
                0.12,
                {"relationship": dict(relationship)},
            ),
            self._retention_signal(
                "journey_stage",
                customer_journey.stage.value,
                0.12,
                {"journey_confidence": customer_journey.confidence},
            ),
            self._retention_signal(
                "value_retention_risk",
                customer_value.retention_risk,
                0.16,
                {"value_tier": customer_value.tier.value},
            ),
            self._retention_signal(
                "experience_activity",
                bool(experience.get("active")),
                0.08,
                {"experience": dict(experience)},
            ),
            self._retention_signal(
                "sales_pressure",
                sales.get("recommendation_type"),
                0.08,
                {"sales": dict(sales)},
            ),
            self._retention_signal(
                "delivery_activity",
                (delivery.get("delivery_history") or {}).get("delivery_count"),
                0.06,
                {"delivery": dict(delivery)},
            ),
            self._retention_signal(
                "telegram_business_state",
                telegram_summary.get("business_health"),
                0.06,
                {"telegram_business": dict(telegram_summary)},
            ),
            self._retention_signal(
                "business_learning_evidence",
                learning.get("outcome_count"),
                0.05,
                {"learning": dict(learning)},
            ),
            self._retention_signal(
                "commerce_strategy_signal",
                len(strategy_recommendations),
                0.05,
                {"strategy_recommendation_count": len(strategy_recommendations)},
            ),
            self._retention_signal(
                "last_engagement",
                last_engagement.get("journey_stage"),
                0.08,
                {"last_engagement": dict(last_engagement)},
            ),
        )

    @staticmethod
    def _retention_signal(
        signal_type: str,
        value: Any,
        weight: float,
        evidence: Mapping[str, Any],
    ) -> CustomerRetentionSignal:
        return CustomerRetentionSignal(
            signal_type=signal_type,
            value=value,
            weight=round(max(0.0, min(1.0, float(weight or 0.0))), 2),
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
            },
        )

    @staticmethod
    def _retention_state(
        *,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        sales: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> CustomerRetentionRisk:
        stage = str(relationship_stage or "").lower()
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        sales_type = str(sales.get("recommendation_type") or "").upper()
        if customer_value.tier == CustomerValueTier.DORMANT or stage in {
            "dormant",
            "lapsed",
        }:
            return CustomerRetentionRisk.DORMANT
        if customer_journey.stage == CustomerJourneyStage.RE_ENGAGEMENT:
            return CustomerRetentionRisk.RE_ENGAGEMENT_CANDIDATE
        if customer_value.retention_risk == "high" or relationship_health in {
            "AT_RISK",
            "DISENGAGED",
        }:
            return CustomerRetentionRisk.AT_RISK
        if "DELAY" in sales_type:
            return CustomerRetentionRisk.COOLING_OFF
        if health == CustomerBusinessHealth.VIP or customer_value.vip_potential:
            return CustomerRetentionRisk.RETAINED
        if customer_value.retention_risk == "medium":
            return CustomerRetentionRisk.MONITOR
        if customer_journey.stage in {
            CustomerJourneyStage.ACTIVE_BUYER,
            CustomerJourneyStage.REPEAT_BUYER,
            CustomerJourneyStage.VIP_GROWTH,
        }:
            return CustomerRetentionRisk.HEALTHY
        return CustomerRetentionRisk.MONITOR

    @staticmethod
    def _re_engagement_readiness(
        *,
        risk: CustomerRetentionRisk,
        customer_value: CustomerValueSummary,
        sales: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> str:
        relationship_health = str(relationship.get("relationship_health") or "").upper()
        if risk in {
            CustomerRetentionRisk.DORMANT,
            CustomerRetentionRisk.RE_ENGAGEMENT_CANDIDATE,
        }:
            return "ready"
        if risk == CustomerRetentionRisk.AT_RISK:
            return "needs_soft_follow_up"
        if risk == CustomerRetentionRisk.COOLING_OFF:
            return "wait"
        if customer_value.vip_potential or relationship_health == "VIP_OPPORTUNITY":
            return "vip_nurture"
        if sales.get("recommendation_type"):
            return "monitor"
        return "not_needed"

    @staticmethod
    def _retention_confidence(
        *,
        signals: tuple[CustomerRetentionSignal, ...],
        telegram_summary: Mapping[str, Any],
        learning: Mapping[str, Any],
        relationship: Mapping[str, Any],
    ) -> float:
        confidence = min(0.45, sum(signal.weight for signal in signals) / 2)
        if telegram_summary.get("available"):
            confidence += 0.08
        if learning.get("available"):
            confidence += 0.06
        if relationship.get("available"):
            confidence += 0.08
        return round(max(0.0, min(1.0, confidence)), 2)

    def _retention_opportunities(
        self,
        *,
        risk: CustomerRetentionRisk,
        readiness: str,
        customer_value: CustomerValueSummary,
        customer_journey: CustomerJourneySummary,
        experience: Mapping[str, Any],
        sales: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerRetentionOpportunity, ...]:
        opportunities: list[CustomerRetentionOpportunity] = []
        if risk in {
            CustomerRetentionRisk.DORMANT,
            CustomerRetentionRisk.RE_ENGAGEMENT_CANDIDATE,
        }:
            opportunities.append(
                self._retention_opportunity(
                    "re_engagement",
                    "Re-engage customer",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.7),
                    {"risk": risk.value, "readiness": readiness},
                )
            )
        if risk == CustomerRetentionRisk.AT_RISK:
            opportunities.append(
                self._retention_opportunity(
                    "follow_up",
                    "Recommend follow-up",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.65),
                    {"risk": risk.value, "readiness": readiness},
                )
            )
        if risk == CustomerRetentionRisk.COOLING_OFF:
            opportunities.append(
                self._retention_opportunity(
                    "cooling_off",
                    "Wait before selling",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.58),
                    {"sales": dict(sales)},
                )
            )
        if experience.get("active"):
            opportunities.append(
                self._retention_opportunity(
                    "experience_resume",
                    "Resume current Experience",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.56),
                    {"experience": dict(experience)},
                )
            )
        if customer_value.vip_potential or (
            customer_journey.stage == CustomerJourneyStage.VIP_GROWTH
        ):
            opportunities.append(
                self._retention_opportunity(
                    "vip_nurture",
                    "Escalate to VIP nurture",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.68),
                    {"value_tier": customer_value.tier.value},
                )
            )
        if not opportunities:
            opportunities.append(
                self._retention_opportunity(
                    "monitor",
                    "Continue relationship building",
                    CustomerBusinessPriority.LOW,
                    max(confidence, 0.4),
                    {"risk": risk.value},
                )
            )
        return tuple(opportunities)

    @classmethod
    def _retention_recommendations(
        cls,
        *,
        risk: CustomerRetentionRisk,
        readiness: str,
        customer_value: CustomerValueSummary,
        customer_journey: CustomerJourneySummary,
        experience: Mapping[str, Any],
        sales: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerRetentionRecommendation, ...]:
        if risk in {
            CustomerRetentionRisk.DORMANT,
            CustomerRetentionRisk.RE_ENGAGEMENT_CANDIDATE,
        }:
            return (
                cls._retention_recommendation(
                    "RE_ENGAGE_CUSTOMER",
                    "Re-engage customer",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.7),
                    risk,
                    readiness,
                ),
            )
        if customer_value.vip_potential or (
            customer_journey.stage == CustomerJourneyStage.VIP_GROWTH
        ):
            return (
                cls._retention_recommendation(
                    "ESCALATE_TO_VIP_NURTURE",
                    "Escalate to VIP nurture",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.68),
                    risk,
                    readiness,
                ),
            )
        if risk == CustomerRetentionRisk.AT_RISK:
            return (
                cls._retention_recommendation(
                    "RECOMMEND_FOLLOW_UP",
                    "Recommend follow-up",
                    CustomerBusinessPriority.HIGH,
                    max(confidence, 0.65),
                    risk,
                    readiness,
                ),
            )
        sales_type = str(sales.get("recommendation_type") or "").upper()
        if risk == CustomerRetentionRisk.COOLING_OFF or "DELAY" in sales_type:
            return (
                cls._retention_recommendation(
                    "WAIT_BEFORE_SELLING",
                    "Wait before selling",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.58),
                    risk,
                    readiness,
                ),
            )
        if experience.get("active"):
            return (
                cls._retention_recommendation(
                    "RESUME_CURRENT_EXPERIENCE",
                    "Resume current Experience",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.56),
                    risk,
                    readiness,
                ),
            )
        if customer_value.purchase_potential == "medium":
            return (
                cls._retention_recommendation(
                    "SEND_FREE_PREVIEW",
                    "Send FREE preview",
                    CustomerBusinessPriority.NORMAL,
                    max(confidence, 0.55),
                    risk,
                    readiness,
                ),
            )
        if risk == CustomerRetentionRisk.RETAINED:
            return (
                cls._retention_recommendation(
                    "CONTINUE_RELATIONSHIP_BUILDING",
                    "Continue relationship building",
                    CustomerBusinessPriority.LOW,
                    max(confidence, 0.52),
                    risk,
                    readiness,
                ),
            )
        return (
            cls._retention_recommendation(
                "CONTINUE_RELATIONSHIP_BUILDING",
                "Continue relationship building",
                CustomerBusinessPriority.LOW,
                max(confidence, 0.4),
                risk,
                readiness,
            ),
        )

    @staticmethod
    def _retention_opportunity(
        opportunity_type: str,
        action: str,
        priority: CustomerBusinessPriority,
        confidence: float,
        evidence: Mapping[str, Any],
    ) -> CustomerRetentionOpportunity:
        return CustomerRetentionOpportunity(
            opportunity_type=opportunity_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_action=action,
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
            },
        )

    @staticmethod
    def _retention_recommendation(
        recommendation_type: str,
        action: str,
        priority: CustomerBusinessPriority,
        confidence: float,
        risk: CustomerRetentionRisk,
        readiness: str,
    ) -> CustomerRetentionRecommendation:
        return CustomerRetentionRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_next_action=action,
            supporting_evidence={
                "retention_risk": risk.value,
                "re_engagement_readiness": readiness,
            },
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
            },
        )

    def _customer_growth_summary(
        self,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
        commerce_strategy_result: Any,
    ) -> CustomerGrowthSummary:
        signals = self._growth_signals(
            lifecycle=lifecycle,
            health=health,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            retention=retention,
            experience=experience,
            product_discovery=product_discovery,
            commerce=commerce,
            telegram_summary=telegram_summary,
            sales=sales,
            delivery=delivery,
            relationship=relationship,
            learning=learning,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            commerce_strategy_result=commerce_strategy_result,
        )
        stage = self._growth_stage(
            lifecycle=lifecycle,
            relationship_stage=relationship_stage,
            customer_journey=customer_journey,
            customer_value=customer_value,
            retention=retention,
            commerce=commerce,
            product_discovery=product_discovery,
            sales=sales,
        )
        expansion = self._expansion_readiness(
            stage=stage,
            customer_value=customer_value,
            retention=retention,
            product_discovery=product_discovery,
            sales=sales,
        )
        upsell = self._upsell_readiness(
            customer_value=customer_value,
            retention=retention,
            sales=sales,
            commerce=commerce,
        )
        cross_sell = self._cross_sell_readiness(
            product_discovery=product_discovery,
            customer_value=customer_value,
            retention=retention,
            sales=sales,
        )
        vip = self._vip_growth_readiness(
            customer_value=customer_value,
            retention=retention,
            relationship=relationship,
        )
        confidence = self._growth_confidence(
            signals=signals,
            customer_value=customer_value,
            retention=retention,
            learning=learning,
            telegram_summary=telegram_summary,
        )
        opportunities = self._growth_opportunities_summary(
            stage=stage,
            expansion_readiness=expansion,
            upsell_readiness=upsell,
            cross_sell_readiness=cross_sell,
            vip_growth_readiness=vip,
            customer_value=customer_value,
            retention=retention,
            experience=experience,
            product_discovery=product_discovery,
            sales=sales,
            confidence=confidence,
        )
        recommendations = self._growth_recommendations(
            stage=stage,
            expansion_readiness=expansion,
            upsell_readiness=upsell,
            cross_sell_readiness=cross_sell,
            vip_growth_readiness=vip,
            customer_value=customer_value,
            retention=retention,
            experience=experience,
            sales=sales,
            confidence=confidence,
        )
        action = (
            recommendations[0].recommended_next_action
            if recommendations
            else "Continue nurturing"
        )
        return CustomerGrowthSummary(
            stage=stage,
            opportunities=opportunities,
            signals=signals,
            expansion_readiness=expansion,
            upsell_readiness=upsell,
            cross_sell_readiness=cross_sell,
            vip_growth_readiness=vip,
            recommended_growth_action=action,
            recommendations=recommendations,
            confidence=confidence,
            compatibility={
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "advisory_only": True,
                "customer_intelligence_owner": "CustomerIntelligenceService",
                "commerce_strategy_owner": "CommerceStrategyService",
                "product_business_owner": "ProductBusinessService",
                "telegram_business_owner": "TelegramBusinessService",
                "business_learning_owner": "BusinessLearningService",
            },
            metadata={"source": "customer_business_growth"},
        )

    def _growth_signals(
        self,
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        health: CustomerBusinessHealth,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
        commerce_strategy_result: Any,
    ) -> tuple[CustomerGrowthSignal, ...]:
        products = self._products(
            telegram_business_snapshot=None,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        strategy_recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations") or ()
        )
        return (
            self._growth_signal(
                "lifecycle_stage",
                lifecycle.value,
                0.1,
                {"health": health.value, "relationship_stage": relationship_stage},
            ),
            self._growth_signal(
                "journey_stage",
                customer_journey.stage.value,
                0.12,
                {"journey_confidence": customer_journey.confidence},
            ),
            self._growth_signal(
                "value_tier",
                customer_value.tier.value,
                0.16,
                {"purchase_potential": customer_value.purchase_potential},
            ),
            self._growth_signal(
                "retention_state",
                retention.risk.value,
                0.12,
                {"re_engagement_readiness": retention.re_engagement_readiness},
            ),
            self._growth_signal(
                "product_discovery",
                product_discovery.get("product_count"),
                0.1,
                {
                    "product_count": product_discovery.get("product_count"),
                    "product_business_snapshot_count": len(products),
                },
            ),
            self._growth_signal(
                "sales_recommendation",
                sales.get("recommendation_type"),
                0.12,
                {"sales": dict(sales)},
            ),
            self._growth_signal(
                "commerce_strategy",
                len(strategy_recommendations),
                0.08,
                {"recommendation_count": len(strategy_recommendations)},
            ),
            self._growth_signal(
                "experience_activity",
                bool(experience.get("active")),
                0.08,
                {"experience": dict(experience)},
            ),
            self._growth_signal(
                "delivery_activity",
                (delivery.get("delivery_history") or {}).get("delivery_count"),
                0.05,
                {"delivery": dict(delivery)},
            ),
            self._growth_signal(
                "telegram_business_state",
                telegram_summary.get("business_health"),
                0.05,
                {"telegram_business": dict(telegram_summary)},
            ),
            self._growth_signal(
                "relationship_health",
                relationship.get("relationship_health"),
                0.06,
                {"relationship": dict(relationship)},
            ),
            self._growth_signal(
                "business_learning_evidence",
                learning.get("outcome_count"),
                0.06,
                {"learning": dict(learning)},
            ),
            self._growth_signal(
                "purchase_count",
                commerce.get("purchase_count"),
                0.12,
                {"commerce": dict(commerce)},
            ),
        )

    @staticmethod
    def _growth_signal(
        signal_type: str,
        value: Any,
        weight: float,
        evidence: Mapping[str, Any],
    ) -> CustomerGrowthSignal:
        return CustomerGrowthSignal(
            signal_type=signal_type,
            value=value,
            weight=round(max(0.0, min(1.0, float(weight or 0.0))), 2),
            supporting_evidence=dict(evidence),
            metadata={"read_only": True, "aggregation_only": True},
        )

    @staticmethod
    def _growth_stage(
        *,
        lifecycle: CustomerBusinessLifecycleStage,
        relationship_stage: str,
        customer_journey: CustomerJourneySummary,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        commerce: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        sales: Mapping[str, Any],
    ) -> CustomerGrowthStage:
        if customer_value.tier == CustomerValueTier.VIP:
            return CustomerGrowthStage.MATURE_CUSTOMER
        if customer_value.vip_potential or customer_journey.stage == CustomerJourneyStage.VIP_GROWTH:
            return CustomerGrowthStage.VIP_DEVELOPMENT
        if commerce.get("purchase_count", 0) >= 2:
            return CustomerGrowthStage.REPEAT_BUYER
        if customer_value.tier in {CustomerValueTier.BUYER, CustomerValueTier.REPEAT_BUYER}:
            return CustomerGrowthStage.EXPANSION
        if retention.risk in {
            CustomerRetentionRisk.AT_RISK,
            CustomerRetentionRisk.DORMANT,
            CustomerRetentionRisk.RE_ENGAGEMENT_CANDIDATE,
        }:
            return CustomerGrowthStage.EARLY_RELATIONSHIP
        if sales.get("recommendation_type") or product_discovery.get("current_product_ids"):
            return CustomerGrowthStage.ACTIVE_GROWTH
        if customer_journey.stage == CustomerJourneyStage.PRODUCT_DISCOVERY:
            return CustomerGrowthStage.DISCOVERY
        if lifecycle in {
            CustomerBusinessLifecycleStage.ACTIVE_RELATIONSHIP,
            CustomerBusinessLifecycleStage.EXPERIENCE_ACTIVE,
        }:
            return CustomerGrowthStage.DISCOVERY
        if str(relationship_stage or "").lower() in {"active", "engaged", "returning"}:
            return CustomerGrowthStage.DISCOVERY
        return CustomerGrowthStage.EARLY_RELATIONSHIP

    @staticmethod
    def _expansion_readiness(
        *,
        stage: CustomerGrowthStage,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        product_discovery: Mapping[str, Any],
        sales: Mapping[str, Any],
    ) -> str:
        if retention.risk in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            return "blocked"
        if stage in {
            CustomerGrowthStage.EXPANSION,
            CustomerGrowthStage.REPEAT_BUYER,
            CustomerGrowthStage.VIP_DEVELOPMENT,
            CustomerGrowthStage.MATURE_CUSTOMER,
        }:
            return "ready"
        if sales.get("recommendation_type") or product_discovery.get("current_product_ids"):
            return "warming"
        if customer_value.purchase_potential == "medium":
            return "warming"
        return "not_ready"

    @staticmethod
    def _upsell_readiness(
        *,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        sales: Mapping[str, Any],
        commerce: Mapping[str, Any],
    ) -> str:
        sales_text = str(sales.get("recommendation_type") or "").upper()
        if retention.risk in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            return "blocked"
        if "UPSELL" in sales_text or customer_value.purchase_potential == "high":
            return "ready"
        if commerce.get("purchase_count", 0) >= 1:
            return "warming"
        return "not_ready"

    @staticmethod
    def _cross_sell_readiness(
        *,
        product_discovery: Mapping[str, Any],
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        sales: Mapping[str, Any],
    ) -> str:
        sales_text = str(sales.get("recommendation_type") or "").upper()
        if retention.risk in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            return "blocked"
        if "CROSS" in sales_text:
            return "ready"
        if product_discovery.get("product_count", 0) > 1 and customer_value.purchase_potential in {"medium", "high"}:
            return "ready"
        if product_discovery.get("current_product_ids"):
            return "warming"
        return "not_ready"

    @staticmethod
    def _vip_growth_readiness(
        *,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        relationship: Mapping[str, Any],
    ) -> str:
        if retention.risk in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            return "blocked"
        if customer_value.vip_potential or str(relationship.get("relationship_health") or "").upper() == "VIP_OPPORTUNITY":
            return "ready"
        if customer_value.tier in {CustomerValueTier.REPEAT_BUYER, CustomerValueTier.HIGH_VALUE}:
            return "warming"
        return "not_ready"

    @staticmethod
    def _growth_confidence(
        *,
        signals: tuple[CustomerGrowthSignal, ...],
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        learning: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
    ) -> float:
        confidence = min(0.45, sum(signal.weight for signal in signals) / 2)
        confidence += min(0.15, customer_value.confidence / 4)
        confidence += min(0.12, retention.confidence / 4)
        if learning.get("available"):
            confidence += 0.06
        if telegram_summary.get("available"):
            confidence += 0.06
        return round(max(0.0, min(1.0, confidence)), 2)

    def _growth_opportunities_summary(
        self,
        *,
        stage: CustomerGrowthStage,
        expansion_readiness: str,
        upsell_readiness: str,
        cross_sell_readiness: str,
        vip_growth_readiness: str,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        experience: Mapping[str, Any],
        product_discovery: Mapping[str, Any],
        sales: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerGrowthOpportunity, ...]:
        opportunities: list[CustomerGrowthOpportunity] = []
        if vip_growth_readiness == "ready":
            opportunities.append(self._growth_opportunity("vip_growth", "Develop VIP relationship", CustomerBusinessPriority.HIGH, max(confidence, 0.7), {"value_tier": customer_value.tier.value}))
        if upsell_readiness == "ready":
            opportunities.append(self._growth_opportunity("upsell", "Upsell premium offering", CustomerBusinessPriority.HIGH, max(confidence, 0.66), {"sales": dict(sales)}))
        if cross_sell_readiness == "ready":
            opportunities.append(self._growth_opportunity("cross_sell", "Cross-sell related Products", CustomerBusinessPriority.HIGH, max(confidence, 0.64), {"product_discovery": dict(product_discovery)}))
        if expansion_readiness == "ready":
            opportunities.append(self._growth_opportunity("expansion", "Recommend premium Product", CustomerBusinessPriority.HIGH, max(confidence, 0.63), {"stage": stage.value}))
        if experience.get("active"):
            opportunities.append(self._growth_opportunity("experience", "Maintain current progression", CustomerBusinessPriority.NORMAL, max(confidence, 0.55), {"experience": dict(experience)}))
        if not opportunities and retention.risk not in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            opportunities.append(self._growth_opportunity("nurture", "Continue nurturing", CustomerBusinessPriority.LOW, max(confidence, 0.4), {"stage": stage.value}))
        return tuple(opportunities)

    @classmethod
    def _growth_recommendations(
        cls,
        *,
        stage: CustomerGrowthStage,
        expansion_readiness: str,
        upsell_readiness: str,
        cross_sell_readiness: str,
        vip_growth_readiness: str,
        customer_value: CustomerValueSummary,
        retention: CustomerRetentionSummary,
        experience: Mapping[str, Any],
        sales: Mapping[str, Any],
        confidence: float,
    ) -> tuple[CustomerGrowthRecommendation, ...]:
        sales_action = str(sales.get("recommended_next_action") or "")
        if vip_growth_readiness == "ready":
            return (cls._growth_recommendation("DEVELOP_VIP_RELATIONSHIP", "Develop VIP relationship", CustomerBusinessPriority.HIGH, max(confidence, 0.7), stage),)
        if "bundle" in sales_action.lower():
            return (cls._growth_recommendation("RECOMMEND_BUNDLE", "Recommend bundle", cls._priority(sales.get("priority")), max(confidence, sales.get("confidence") or 0.64), stage),)
        if cross_sell_readiness == "ready":
            return (cls._growth_recommendation("CROSS_SELL_RELATED_PRODUCTS", "Cross-sell related Products", CustomerBusinessPriority.HIGH, max(confidence, 0.64), stage),)
        if upsell_readiness == "ready":
            return (cls._growth_recommendation("UPSELL_PREMIUM_OFFERING", "Upsell premium offering", CustomerBusinessPriority.HIGH, max(confidence, 0.66), stage),)
        if expansion_readiness in {"ready", "warming"}:
            return (cls._growth_recommendation("RECOMMEND_PREMIUM_PRODUCT", "Recommend premium Product", CustomerBusinessPriority.NORMAL, max(confidence, 0.58), stage),)
        if experience.get("active"):
            return (cls._growth_recommendation("MAINTAIN_CURRENT_PROGRESSION", "Maintain current progression", CustomerBusinessPriority.NORMAL, max(confidence, 0.55), stage),)
        if retention.risk in {CustomerRetentionRisk.AT_RISK, CustomerRetentionRisk.DORMANT}:
            return (cls._growth_recommendation("CONTINUE_NURTURING", "Continue nurturing", CustomerBusinessPriority.LOW, max(confidence, 0.42), stage),)
        return (cls._growth_recommendation("INTRODUCE_NEXT_EXPERIENCE", "Introduce next Experience", CustomerBusinessPriority.NORMAL, max(confidence, 0.5), stage),)

    @staticmethod
    def _growth_opportunity(
        opportunity_type: str,
        action: str,
        priority: CustomerBusinessPriority,
        confidence: float,
        evidence: Mapping[str, Any],
    ) -> CustomerGrowthOpportunity:
        return CustomerGrowthOpportunity(
            opportunity_type=opportunity_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_action=action,
            supporting_evidence=dict(evidence),
            metadata={"read_only": True, "aggregation_only": True, "advisory_only": True},
        )

    @staticmethod
    def _growth_recommendation(
        recommendation_type: str,
        action: str,
        priority: CustomerBusinessPriority,
        confidence: float,
        stage: CustomerGrowthStage,
    ) -> CustomerGrowthRecommendation:
        return CustomerGrowthRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, float(confidence or 0.0))), 2),
            recommended_next_action=action,
            supporting_evidence={"growth_stage": stage.value},
            metadata={"read_only": True, "aggregation_only": True, "advisory_only": True},
        )

    def _opportunities(
        self,
        *,
        health: CustomerBusinessHealth,
        lifecycle: CustomerBusinessLifecycleStage,
        relationship_stage: str,
        journey: Mapping[str, Any],
        experience: Mapping[str, Any],
        commerce: Mapping[str, Any],
        telegram_summary: Mapping[str, Any],
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        learning: Mapping[str, Any],
    ) -> tuple[CustomerBusinessOpportunity, ...]:
        opportunities: list[CustomerBusinessOpportunity] = []
        if sales.get("recommendation_type") and sales.get("recommendation_type") != "NO_SALES_ACTION":
            opportunities.append(
                self._opportunity(
                    "sales",
                    sales.get("recommended_next_action") or "Review Sales Opportunity",
                    sales.get("priority") or CustomerBusinessPriority.NORMAL,
                    sales.get("confidence") or 0.55,
                    {"sales": sales, "commerce": commerce},
                )
            )
        if delivery.get("recommendation_type") and delivery.get("recommendation_type") != "NO_DELIVERY":
            opportunities.append(
                self._opportunity(
                    "delivery",
                    delivery.get("recommended_next_action") or "Review Delivery",
                    delivery.get("priority") or CustomerBusinessPriority.NORMAL,
                    delivery.get("confidence") or 0.55,
                    {"delivery": delivery, "commerce": commerce},
                )
            )
        if relationship.get("recommended_next_action") and (
            relationship.get("management_available")
            or str(relationship_stage or "").lower()
            not in {"new", "unknown", ""}
        ):
            opportunities.append(
                self._opportunity(
                    "relationship",
                    relationship["recommended_next_action"],
                    relationship.get("priority") or CustomerBusinessPriority.NORMAL,
                    relationship.get("confidence") or 0.5,
                    {"relationship": relationship},
                )
            )
        if experience.get("active") and not commerce.get("active_offer_count"):
            opportunities.append(
                self._opportunity(
                    "experience",
                    experience.get("next_recommended_action") or "Continue Experience",
                    CustomerBusinessPriority.NORMAL,
                    0.55,
                    {"experience": experience},
                )
            )
        if health in {CustomerBusinessHealth.DORMANT, CustomerBusinessHealth.AT_RISK}:
            opportunities.append(
                self._opportunity(
                    "retention",
                    "Re-engage Customer",
                    CustomerBusinessPriority.HIGH,
                    0.7,
                    {
                        "health": health.value,
                        "relationship_stage": relationship_stage,
                        "journey": journey,
                    },
                )
            )
        if lifecycle == CustomerBusinessLifecycleStage.VIP:
            opportunities.append(
                self._opportunity(
                    "vip",
                    "Review VIP Opportunity",
                    CustomerBusinessPriority.HIGH,
                    0.72,
                    {"relationship": relationship, "learning": learning},
                )
            )
        if not opportunities and telegram_summary.get("available"):
            opportunities.append(
                self._opportunity(
                    "monitor",
                    telegram_summary.get("next_recommended_action")
                    or "Monitor Customer",
                    CustomerBusinessPriority.LOW,
                    0.35,
                    {"telegram_business": telegram_summary},
                )
            )
        return tuple(opportunities)

    def _recommendations(
        self,
        *,
        opportunities: tuple[CustomerBusinessOpportunity, ...],
        health: CustomerBusinessHealth,
        lifecycle: CustomerBusinessLifecycleStage,
        sales: Mapping[str, Any],
        delivery: Mapping[str, Any],
        relationship: Mapping[str, Any],
        journey: Mapping[str, Any],
    ) -> tuple[CustomerBusinessRecommendation, ...]:
        if not opportunities:
            return (
                CustomerBusinessRecommendation(
                    recommendation_type="NO_CUSTOMER_BUSINESS_ACTION",
                    priority=CustomerBusinessPriority.LOW,
                    confidence=0.3,
                    recommended_next_action="No Customer Business Action",
                    supporting_evidence={
                        "health": health.value,
                        "lifecycle_stage": lifecycle.value,
                        "journey": dict(journey),
                    },
                    metadata={"advisory_only": True, "read_only": True},
                ),
            )
        ordered = sorted(
            opportunities,
            key=lambda item: self._priority_rank(item.priority),
            reverse=True,
        )
        return tuple(
            CustomerBusinessRecommendation(
                recommendation_type=opportunity.opportunity_type.upper(),
                priority=opportunity.priority,
                confidence=opportunity.confidence,
                recommended_next_action=opportunity.recommended_action,
                supporting_evidence={
                    "opportunity": opportunity.supporting_evidence,
                    "health": health.value,
                    "lifecycle_stage": lifecycle.value,
                    "sales_signal": sales.get("recommendation_type"),
                    "delivery_signal": delivery.get("recommendation_type"),
                    "relationship_signal": relationship.get("recommendation_type"),
                },
                metadata={
                    "advisory_only": True,
                    "aggregation_only": True,
                    "read_only": True,
                },
            )
            for opportunity in ordered
        )

    @classmethod
    def _next_action(
        cls,
        recommendations: tuple[CustomerBusinessRecommendation, ...],
        opportunities: tuple[CustomerBusinessOpportunity, ...],
        journey: Mapping[str, Any],
        customer_journey: CustomerJourneySummary | None = None,
    ) -> str:
        if recommendations and (
            recommendations[0].recommendation_type != "NO_CUSTOMER_BUSINESS_ACTION"
        ):
            return recommendations[0].recommended_next_action
        if opportunities:
            return opportunities[0].recommended_action
        if customer_journey and customer_journey.recommendations:
            return customer_journey.recommendations[0].recommended_next_action
        if journey.get("stage") != "unknown":
            return "Monitor Customer"
        return "Review Customer"

    @classmethod
    def _opportunity(
        cls,
        opportunity_type: str,
        action: Any,
        priority: Any,
        confidence: Any,
        evidence: Mapping[str, Any],
    ) -> CustomerBusinessOpportunity:
        return CustomerBusinessOpportunity(
            opportunity_type=str(opportunity_type),
            priority=cls._priority(priority),
            confidence=round(max(0.0, min(1.0, cls._float(confidence))), 2),
            recommended_action=cls._safe_text(action) or "Review Customer",
            supporting_evidence=dict(evidence),
            metadata={
                "read_only": True,
                "aggregation_only": True,
                "advisory_only": True,
            },
        )

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "customer_business",
            "owner": "CustomerBusinessService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "advisory_only": True,
            "executes_telegram": False,
            "modifies_customer_intelligence": False,
            "modifies_products": False,
            "modifies_publishing": False,
            "records_business_learning": False,
            "changes_decision_engine_behavior": False,
            "generates_commerce_strategy": False,
            "customer_intelligence_owner": "CustomerIntelligenceService",
            "telegram_business_owner": "TelegramBusinessService",
            "product_business_owner": "ProductBusinessService",
            "business_learning_owner": "BusinessLearningService",
            "commerce_strategy_owner": "CommerceStrategyService",
            "sources_consumed": {key: value is not None for key, value in sources.items()},
        }

    @classmethod
    def _products(
        cls,
        *,
        telegram_business_snapshot: Any,
        product_business_snapshot: Any,
        product_business_snapshots: Iterable[Any] | None,
    ) -> tuple[Any, ...]:
        products: list[Any] = []
        if product_business_snapshot is not None:
            products.append(product_business_snapshot)
        if product_business_snapshots is not None:
            products.extend(item for item in product_business_snapshots if item is not None)
        products.extend(tuple(cls._read(telegram_business_snapshot, "products") or ()))
        return tuple(products)

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

    @classmethod
    def _first_text(cls, values: Iterable[Any]) -> str | None:
        for value in values:
            text = cls._safe_text(value)
            if text:
                return text
        return None

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
        elif isinstance(value, Mapping):
            values = value.values()
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
    def _priority_rank(priority: CustomerBusinessPriority) -> int:
        return {
            CustomerBusinessPriority.LOW: 1,
            CustomerBusinessPriority.NORMAL: 2,
            CustomerBusinessPriority.HIGH: 3,
            CustomerBusinessPriority.CRITICAL: 4,
        }.get(priority, 0)

    @classmethod
    def _priority(cls, value: Any) -> CustomerBusinessPriority:
        raw = cls._safe_text(value) or CustomerBusinessPriority.NORMAL.value
        try:
            return CustomerBusinessPriority(raw)
        except ValueError:
            try:
                return CustomerBusinessPriority(raw.upper())
            except ValueError:
                return CustomerBusinessPriority.NORMAL

    @staticmethod
    def _mapping_or_tuple(value: Any) -> Any:
        if value is None:
            return {}
        if isinstance(value, Mapping):
            return dict(value)
        try:
            return tuple(value)
        except TypeError:
            return value

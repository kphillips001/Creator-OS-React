"""Canonical Telegram Business read-model aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.telegram_business import (
    TelegramBusinessSnapshot,
    TelegramBusinessSummary,
)

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.customer_intelligence_service import CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService
    from app.services.product_business_service import ProductBusinessService
    from app.services.publishing_service import PublishingService
    from app.services.telegram_commerce_service import TelegramCommerceService


class TelegramBusinessService:
    """Build read-only Telegram Business snapshots from existing domains.

    This service is aggregation only. It does not send Telegram messages, publish
    Products, record learning outcomes, generate strategy, or mutate domain
    state.
    """

    def __init__(
        self,
        *,
        telegram_commerce_service: "TelegramCommerceService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        product_business_service: "ProductBusinessService | None" = None,
        publishing_service: "PublishingService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
        experience_service: Any | None = None,
    ) -> None:
        self._telegram_commerce = telegram_commerce_service
        self._customer_intelligence = customer_intelligence_service
        self._commerce_strategy = commerce_strategy_service
        self._product_business = product_business_service
        self._publishing = publishing_service
        self._business_learning = business_learning_service
        self._experience = experience_service

    @property
    def customer_intelligence(self) -> "CustomerIntelligenceService":
        if self._customer_intelligence is None:
            from app.services.customer_intelligence_service import (
                CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService,
            )

            self._customer_intelligence = CustomerIntelligenceService()
        return self._customer_intelligence

    @property
    def commerce_strategy(self) -> "CommerceStrategyService":
        if self._commerce_strategy is None:
            from app.services.commerce_strategy_service import CommerceStrategyService

            self._commerce_strategy = CommerceStrategyService()
        return self._commerce_strategy

    @property
    def product_business(self) -> "ProductBusinessService":
        if self._product_business is None:
            from app.services.product_business_service import ProductBusinessService

            self._product_business = ProductBusinessService()
        return self._product_business

    @property
    def publishing(self) -> "PublishingService":
        if self._publishing is None:
            from app.services.publishing_service import PublishingService

            self._publishing = PublishingService()
        return self._publishing

    @property
    def business_learning(self) -> "BusinessLearningService":
        if self._business_learning is None:
            from app.services.business_learning_service import BusinessLearningService

            self._business_learning = BusinessLearningService()
        return self._business_learning

    def build_snapshot(
        self,
        *,
        customer_id: str | int | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
        telegram_context: Mapping[str, Any] | None = None,
        customer_snapshot: Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
        telegram_commerce_result: Any | None = None,
        telegram_commerce_state: Any | None = None,
        conversation_state: Any | None = None,
        experience_progression: Any | None = None,
        product_business_snapshot: Any | None = None,
        product_business_snapshots: Iterable[Any] | None = None,
        commerce_strategy_result: Any | None = None,
        publishing_status: Any | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        learning_context: Any | None = None,
        learning_snapshot: Any | None = None,
        business_outcomes: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> TelegramBusinessSnapshot:
        resolved_telegram_state = self._resolve_telegram_state(
            telegram_commerce_result,
            telegram_commerce_state,
        )
        resolved_conversation = (
            conversation_state
            or self._read(telegram_commerce_result, "conversation_state")
            or self._read(resolved_telegram_state, "telegram_conversation_state")
        )
        resolved_progression = (
            experience_progression
            or self._read(telegram_commerce_result, "experience_progression")
            or self._read(resolved_telegram_state, "experience_progression")
        )
        resolved_customer = customer_snapshot or self.customer_intelligence.build_customer_snapshot(
            customer_id=customer_id,
            provider="telegram",
            provider_customer_id=provider_customer_id,
            provider_account_id=provider_account_id,
            telegram_context=telegram_context,
            customer_summary=customer_summary,
            commerce_summary=commerce_summary,
            commerce_memory=self._read(telegram_commerce_result, "commerce_memory"),
            conversation_state=resolved_conversation,
            experience_progression=resolved_progression,
            learning_context=learning_context,
        )
        resolved_learning = self._resolve_learning(
            learning_context=learning_context,
            learning_snapshot=learning_snapshot,
            business_outcomes=business_outcomes,
            customer_id=customer_id,
        )
        product_snapshots = self._product_snapshots(
            product_business_snapshot,
            product_business_snapshots,
        )
        if not product_snapshots and self._current_product_id(
            resolved_customer,
            resolved_conversation,
            resolved_progression,
            resolved_telegram_state,
        ):
            product_snapshots = (
                self.product_business.build_snapshot(
                    customer_snapshot=resolved_customer,
                    learning_context=learning_context,
                    learning_snapshot=learning_snapshot,
                    business_outcomes=business_outcomes,
                    commerce_strategy_result=commerce_strategy_result,
                ),
            )
        resolved_publishing = self._publishing_summary(
            publishing_status=publishing_status,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
        )
        relationship = self._relationship_summary(resolved_customer)
        conversation = self._conversation_summary(
            resolved_conversation,
            resolved_telegram_state,
            telegram_commerce_result,
        )
        experience = self._experience_summary(
            resolved_progression,
            resolved_customer,
            resolved_conversation,
        )
        products = tuple(
            self._product_summary(item)
            for item in product_snapshots
        )
        active_offers = self._active_offers(
            resolved_customer,
            resolved_conversation,
            telegram_commerce_result,
            resolved_telegram_state,
        )
        delivery_history = self._delivery_history(
            resolved_customer,
            telegram_commerce_result,
            resolved_telegram_state,
        )
        commerce_strategy = self._commerce_strategy_summary(
            commerce_strategy_result
        )
        product_business = self._product_business_summary(products)
        business_learning = self._business_learning_summary(resolved_learning)
        telegram_commerce = self._telegram_commerce_summary(
            telegram_commerce_result,
            resolved_telegram_state,
        )
        business_health = self._business_health(
            product_business,
            resolved_publishing,
            business_learning,
            delivery_history,
        )
        operation_status = self._operation_status(
            telegram_commerce,
            delivery_history,
            resolved_publishing,
        )
        next_action = self._next_action(
            relationship=relationship,
            conversation=conversation,
            experience=experience,
            products=products,
            active_offers=active_offers,
            publishing=resolved_publishing,
            business_learning=business_learning,
            telegram_commerce=telegram_commerce,
            business_health=business_health,
            operation_status=operation_status,
        )
        current_product_ids = self._current_product_ids(
            products,
            resolved_customer,
            resolved_conversation,
            resolved_progression,
            resolved_telegram_state,
        )
        active_offer_ids = tuple(
            dict.fromkeys(
                offer["offer_id"]
                for offer in active_offers
                if offer.get("offer_id")
            )
        )
        summary = TelegramBusinessSummary(
            relationship_stage=relationship.get("stage"),
            conversation_state=conversation.get("state"),
            current_experience_id=experience.get("current_experience_id"),
            current_product_ids=current_product_ids,
            active_offer_ids=active_offer_ids,
            delivery_count=self._int(delivery_history.get("delivery_count")),
            business_health=business_health,
            operation_status=operation_status,
            next_recommended_action=next_action,
            metadata={
                "source": "telegram_business",
                "aggregation_only": True,
            },
        )
        identity = self._identity_summary(resolved_customer)
        return TelegramBusinessSnapshot(
            customer_id=(
                self._safe_text(customer_id)
                or identity.get("customer_id")
                or identity.get("canonical_customer_id")
            ),
            provider="telegram",
            customer_identity=identity,
            relationship=relationship,
            conversation=conversation,
            experience=experience,
            products=products,
            active_offers=active_offers,
            delivery_history=delivery_history,
            commerce_strategy=commerce_strategy,
            product_business=product_business,
            publishing=resolved_publishing,
            business_learning=business_learning,
            telegram_commerce=telegram_commerce,
            operation_status=operation_status,
            business_health=business_health,
            next_recommended_business_action=next_action,
            summary=summary,
            compatibility=self._compatibility(
                customer_snapshot=resolved_customer,
                product_snapshots=product_snapshots,
                commerce_strategy_result=commerce_strategy_result,
                publishing_status=publishing_status or publishing_projection or publishing_job,
                learning_context=resolved_learning,
                telegram_commerce_result=telegram_commerce_result,
            ),
            metadata={
                "source": "telegram_business",
                "owner": "TelegramBusinessService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_summary(self, **context: Any) -> TelegramBusinessSummary:
        return self.build_snapshot(**context).summary

    @staticmethod
    def _resolve_telegram_state(
        telegram_commerce_result: Any | None,
        telegram_commerce_state: Any | None,
    ) -> Any | None:
        return telegram_commerce_state or TelegramBusinessService._read(
            telegram_commerce_result,
            "state",
        )

    def _resolve_learning(
        self,
        *,
        learning_context: Any | None,
        learning_snapshot: Any | None,
        business_outcomes: Any | None,
        customer_id: str | int | None,
    ) -> Any | None:
        if learning_context is not None:
            return learning_context
        if learning_snapshot is not None:
            return self.business_learning.build_customer_learning_context(
                snapshot=learning_snapshot,
                customer_reference=self._safe_text(customer_id),
            )
        if business_outcomes:
            return self.business_learning.build_customer_learning_context(
                outcomes=business_outcomes,
                customer_reference=self._safe_text(customer_id),
            )
        return None

    @staticmethod
    def _product_snapshots(*values: Any) -> tuple[Any, ...]:
        snapshots: list[Any] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (str, bytes, Mapping)):
                snapshots.append(value)
                continue
            try:
                snapshots.extend(item for item in value if item is not None)
            except TypeError:
                snapshots.append(value)
        return tuple(snapshots)

    def _publishing_summary(
        self,
        *,
        publishing_status: Any | None,
        publishing_projection: Any | None,
        publishing_job: Any | None,
    ) -> dict[str, Any]:
        status = publishing_status or publishing_projection
        if status is None and publishing_job is not None:
            try:
                status = self.publishing.project_publishing_status(publishing_job)
            except Exception:
                status = None
        return {
            "source": "PublishingService",
            "status": self._safe_text(
                self._read(status, "publishing_status")
                or self._read(status, "status")
                or self._read(status, "state")
            ),
            "media_link_status": self._safe_text(
                self._read(status, "media_link_status")
            ),
            "provider": self._safe_text(
                self._read(status, "provider")
                or self._read(publishing_job, "provider")
            ),
            "provider_output_url": self._safe_text(
                self._read(status, "provider_output_url")
                or self._read(status, "output_url")
                or self._read(publishing_job, "provider_output_url")
            ),
            "attention_required": bool(
                self._read(status, "attention_required")
                or self._read(status, "failure_reason")
                or self._read(status, "provider_error")
            ),
            "telegram_ready": bool(
                self._read(status, "telegram_ready")
                or self._read(status, "ready_for_telegram")
            ),
            "read_only": True,
        }

    def _identity_summary(self, customer_snapshot: Any) -> dict[str, Any]:
        identity = self._read(customer_snapshot, "identity")
        return {
            "source": "CustomerIntelligenceCompatibilityAdapter",
            "canonical_customer_id": self._safe_text(
                self._read(identity, "canonical_customer_id")
            ),
            "customer_id": self._safe_text(self._read(identity, "customer_id")),
            "provider": self._safe_text(self._read(identity, "provider")) or "telegram",
            "provider_customer_id": self._safe_text(
                self._read(identity, "provider_customer_id")
            ),
            "provider_account_id": self._safe_text(
                self._read(identity, "provider_account_id")
            ),
            "telegram_identifier": self._safe_text(
                self._read(identity, "telegram_identifier")
            ),
            "platform_identifiers": dict(
                self._read(identity, "platform_identifiers") or {}
            ),
        }

    def _relationship_summary(self, customer_snapshot: Any) -> dict[str, Any]:
        relationship = self._read(customer_snapshot, "relationship_intelligence")
        stage = self._read(customer_snapshot, "relationship_stage")
        return {
            "source": "CustomerIntelligenceCompatibilityAdapter",
            "stage": self._enum_value(stage),
            "engagement_level": self._safe_text(
                self._read(relationship, "engagement_level")
            ),
            "engagement_score": self._int(
                self._read(relationship, "engagement_score")
            ),
            "commerce_maturity": self._safe_text(
                self._read(relationship, "commerce_maturity")
            ),
            "primary_recommendation": self._safe_text(
                self._read(relationship, "primary_recommendation")
            ),
            "recommendations": self._text_tuple(
                self._read(relationship, "recommendations")
            ),
        }

    def _conversation_summary(
        self,
        conversation_state: Any,
        telegram_state: Any,
        telegram_commerce_result: Any,
    ) -> dict[str, Any]:
        return {
            "source": "TelegramCommerceService",
            "state": self._safe_text(
                self._read(conversation_state, "conversation_mode")
                or self._read(conversation_state, "conversation_state")
                or self._read(telegram_state, "conversation_state")
            ),
            "commerce_state": self._safe_text(
                self._read(conversation_state, "commerce_state")
            ),
            "current_offer_id": self._safe_text(
                self._read(conversation_state, "current_offer_id")
            ),
            "current_offer_kind": self._safe_text(
                self._read(conversation_state, "current_offer_kind")
            ),
            "next_recommended_action": self._safe_text(
                self._read(conversation_state, "next_recommended_action")
                or self._read(telegram_commerce_result, "delivery_payload", "next_suggested_action")
            ),
            "read_only": True,
        }

    def _experience_summary(
        self,
        progression: Any,
        customer_snapshot: Any,
        conversation_state: Any,
    ) -> dict[str, Any]:
        customer_progress = self._read(customer_snapshot, "experience_progress")
        return {
            "source": "ExperienceService/TelegramCommerceService",
            "current_experience_id": self._safe_text(
                self._read(progression, "current_experience_id")
                or self._read(customer_progress, "current_experience_id")
                or self._read(conversation_state, "current_experience_id")
            ),
            "experience_state": self._safe_text(
                self._read(progression, "experience_state")
            ),
            "current_position": self._safe_text(
                self._read(customer_progress, "current_position")
                or self._read(progression, "current_story_position")
                or self._read(progression, "current_asset_position")
            ),
            "current_product_id": self._safe_text(
                self._read(progression, "current_product_id")
                or self._read(customer_progress, "current_product_id")
                or self._read(conversation_state, "current_product_id")
            ),
            "progress_percentage": self._int(
                self._read(progression, "progress_percentage")
                or self._read(customer_progress, "progress_percentage")
            ),
            "next_recommended_experience_action": self._safe_text(
                self._read(progression, "next_recommended_experience_action")
            ),
            "read_only": True,
        }

    def _product_summary(self, product_snapshot: Any) -> dict[str, Any]:
        return {
            "source": "ProductBusinessService",
            "product_id": self._safe_text(self._read(product_snapshot, "product_id")),
            "product_name": self._safe_text(
                self._read(product_snapshot, "product_name")
            ),
            "product_type": self._safe_text(
                self._read(product_snapshot, "product_type")
            ),
            "delivery_type": self._safe_text(
                self._read(product_snapshot, "delivery_type")
            ),
            "availability": self._enum_value(
                self._read(product_snapshot, "availability")
            ),
            "product_health": self._enum_value(
                self._read(product_snapshot, "product_health")
            ),
            "next_recommended_action": self._safe_text(
                self._read(product_snapshot, "next_recommended_business_action")
                or self._read(
                    self._read(product_snapshot, "next_business_recommendation"),
                    "label",
                )
            ),
        }

    def _active_offers(
        self,
        customer_snapshot: Any,
        conversation_state: Any,
        telegram_commerce_result: Any,
        telegram_state: Any,
    ) -> tuple[dict[str, Any], ...]:
        memory = self._read(customer_snapshot, "commerce_memory")
        offers: list[dict[str, Any]] = []
        current_offer = self._safe_text(self._read(conversation_state, "current_offer_id"))
        if current_offer:
            offers.append(
                {
                    "offer_id": current_offer,
                    "offer_kind": self._safe_text(
                        self._read(conversation_state, "current_offer_kind")
                    ),
                    "source": "TelegramCommerceService",
                    "active": True,
                }
            )
        delivery_decision = (
            self._read(telegram_commerce_result, "delivery_decision")
            or self._read(telegram_state, "delivery_decision")
        )
        product_id = self._safe_text(
            self._read(delivery_decision, "current_product_id")
        )
        if product_id and not any(item.get("product_id") == product_id for item in offers):
            offers.append(
                {
                    "offer_id": current_offer,
                    "product_id": product_id,
                    "delivery_method": self._safe_text(
                        self._read(delivery_decision, "delivery_method")
                    ),
                    "source": "TelegramCommerceService",
                    "active": bool(self._read(delivery_decision, "offer_authorized")),
                }
            )
        for offer in self._text_tuple(self._read(memory, "previous_offers")):
            if not any(item.get("offer_id") == offer for item in offers):
                offers.append(
                    {
                        "offer_id": offer,
                        "source": "CustomerIntelligenceCompatibilityAdapter",
                        "active": False,
                    }
                )
        return tuple(offers)

    def _delivery_history(
        self,
        customer_snapshot: Any,
        telegram_commerce_result: Any,
        telegram_state: Any,
    ) -> dict[str, Any]:
        memory = self._read(customer_snapshot, "commerce_memory")
        commerce_memory = (
            self._read(telegram_commerce_result, "commerce_memory")
            or self._read(telegram_state, "commerce_memory")
        )
        free = self._merge_text_tuples(
            self._read(memory, "free_assets_delivered"),
            self._read(commerce_memory, "free_assets_delivered"),
        )
        paid = self._merge_text_tuples(
            self._read(memory, "paid_products_delivered"),
            self._read(memory, "delivered_paid_products"),
            self._read(commerce_memory, "paid_media_links_delivered"),
        )
        last_delivery = (
            self._read(commerce_memory, "last_delivery")
            or self._read(memory, "last_delivery")
            or {}
        )
        return {
            "source": "CustomerIntelligenceCompatibilityAdapter/TelegramCommerceService",
            "free_assets_delivered": free,
            "paid_deliveries": paid,
            "delivery_count": len(free) + len(paid),
            "last_delivery": dict(last_delivery) if isinstance(last_delivery, Mapping) else {},
            "duplicate_prevention_signals": self._text_tuple(
                self._read(memory, "duplicate_prevention_signals")
            ),
            "read_only": True,
        }

    def _commerce_strategy_summary(self, commerce_strategy_result: Any) -> dict[str, Any]:
        recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations") or ()
        )
        return {
            "source": "CommerceStrategyService",
            "consumed": commerce_strategy_result is not None,
            "recommendation_count": len(recommendations),
            "confidence": self._float(self._read(commerce_strategy_result, "confidence")),
            "recommended_objectives": tuple(
                self._safe_text(self._read(item, "recommended_objective"))
                for item in recommendations
                if self._safe_text(self._read(item, "recommended_objective"))
            ),
            "generates_strategy": False,
        }

    @staticmethod
    def _product_business_summary(products: tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
        health_values = tuple(item.get("product_health") for item in products if item.get("product_health"))
        return {
            "source": "ProductBusinessService",
            "product_count": len(products),
            "health_values": health_values,
            "telegram_ready_count": sum(
                1 for item in products if item.get("availability") == "TELEGRAM_READY"
            ),
            "attention_required": any(
                value in {"NEEDS_ATTENTION", "UNDERPERFORMING"}
                for value in health_values
            ),
        }

    def _business_learning_summary(self, learning: Any) -> dict[str, Any]:
        performance = self._read(learning, "performance_snapshot")
        learning_summary = self._read(learning, "learning_summary")
        return {
            "source": "BusinessLearningService",
            "consumed": learning is not None,
            "context_type": self._safe_text(self._read(learning, "context_type")),
            "subject_reference": self._safe_text(
                self._read(learning, "subject_reference")
            ),
            "metric_count": len(tuple(self._read(performance, "metrics") or ())),
            "total_insights": self._int(self._read(learning_summary, "total_insights")),
            "total_recommendations": self._int(
                self._read(learning_summary, "total_recommendations")
            ),
            "records_business_learning": False,
        }

    def _telegram_commerce_summary(
        self,
        telegram_commerce_result: Any,
        telegram_state: Any,
    ) -> dict[str, Any]:
        payload = self._read(telegram_commerce_result, "delivery_payload")
        decision = (
            self._read(telegram_commerce_result, "delivery_decision")
            or self._read(telegram_state, "delivery_decision")
        )
        return {
            "source": "TelegramCommerceService",
            "consumed": telegram_commerce_result is not None or telegram_state is not None,
            "delivery_method": self._safe_text(
                self._read(payload, "delivery_method")
                or self._read(decision, "delivery_method")
            ),
            "blocked": bool(
                self._read(telegram_commerce_result, "blocked")
                or self._read(decision, "blocked")
            ),
            "error_code": self._safe_text(
                self._read(telegram_commerce_result, "error_code")
            ),
            "execution_status": self._safe_text(
                self._read(
                    self._read(telegram_commerce_result, "commerce_execution_result"),
                    "status",
                )
            ),
            "orchestration_only": True,
        }

    @staticmethod
    def _business_health(
        product_business: Mapping[str, Any],
        publishing: Mapping[str, Any],
        business_learning: Mapping[str, Any],
        delivery_history: Mapping[str, Any],
    ) -> str:
        if publishing.get("attention_required") or product_business.get("attention_required"):
            return "NEEDS_ATTENTION"
        if business_learning.get("consumed") and business_learning.get("metric_count", 0) > 0:
            return "LEARNING_READY"
        if product_business.get("telegram_ready_count", 0) > 0:
            return "TELEGRAM_READY"
        if delivery_history.get("delivery_count", 0) > 0:
            return "ACTIVE"
        return "UNKNOWN"

    @staticmethod
    def _operation_status(
        telegram_commerce: Mapping[str, Any],
        delivery_history: Mapping[str, Any],
        publishing: Mapping[str, Any],
    ) -> str:
        if telegram_commerce.get("blocked"):
            return "BLOCKED"
        if telegram_commerce.get("execution_status"):
            return str(telegram_commerce["execution_status"]).upper()
        if publishing.get("telegram_ready"):
            return "READY"
        if delivery_history.get("delivery_count", 0) > 0:
            return "ACTIVE"
        if telegram_commerce.get("consumed"):
            return "OBSERVED"
        return "IDLE"

    @staticmethod
    def _next_action(
        *,
        relationship: Mapping[str, Any],
        conversation: Mapping[str, Any],
        experience: Mapping[str, Any],
        products: tuple[Mapping[str, Any], ...],
        active_offers: tuple[Mapping[str, Any], ...],
        publishing: Mapping[str, Any],
        business_learning: Mapping[str, Any],
        telegram_commerce: Mapping[str, Any],
        business_health: str,
        operation_status: str,
    ) -> str:
        if operation_status == "BLOCKED":
            return "Review Blocked Telegram Delivery"
        if publishing.get("attention_required"):
            return "Review Publishing Issue"
        if business_health == "NEEDS_ATTENTION":
            return "Review Product Business Issue"
        for product in products:
            action = product.get("next_recommended_action")
            if action and action != "No Product Business Action":
                return str(action)
        if conversation.get("next_recommended_action"):
            return str(conversation["next_recommended_action"])
        if active_offers:
            return "Review Active Telegram Offer"
        if experience.get("next_recommended_experience_action"):
            return str(experience["next_recommended_experience_action"])
        if business_learning.get("consumed"):
            return "Review Business Learning Evidence"
        if relationship.get("primary_recommendation"):
            return str(relationship["primary_recommendation"])
        if telegram_commerce.get("consumed"):
            return "Monitor Telegram Commerce"
        return "Review Telegram Business Context"

    def _current_product_ids(
        self,
        products: tuple[Mapping[str, Any], ...],
        customer_snapshot: Any,
        conversation_state: Any,
        progression: Any,
        telegram_state: Any,
    ) -> tuple[str, ...]:
        values = [item.get("product_id") for item in products]
        values.append(
            self._current_product_id(
                customer_snapshot,
                conversation_state,
                progression,
                telegram_state,
            )
        )
        return tuple(dict.fromkeys(item for item in values if item))

    def _current_product_id(
        self,
        customer_snapshot: Any,
        conversation_state: Any,
        progression: Any,
        telegram_state: Any,
    ) -> str | None:
        customer_progress = self._read(customer_snapshot, "experience_progress")
        return self._safe_text(
            self._read(conversation_state, "current_product_id")
            or self._read(progression, "current_product_id")
            or self._read(customer_progress, "current_product_id")
            or self._read(telegram_state, "current_product_id")
        )

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "telegram_business",
            "owner": "TelegramBusinessService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "executes_telegram": False,
            "sends_messages": False,
            "publishes_products": False,
            "records_business_learning": False,
            "modifies_customer_intelligence": False,
            "generates_commerce_strategy": False,
            "generates_product_strategy": False,
            "modifies_products": False,
            "telegram_runtime_owner": "Telegram runtime",
            "decision_owner": "DecisionEngine",
            "customer_intelligence_owner": "CustomerIntelligenceCompatibilityAdapter",
            "commerce_strategy_owner": "CommerceStrategyService",
            "product_business_owner": "ProductBusinessService",
            "publishing_owner": "PublishingService",
            "business_learning_owner": "BusinessLearningService",
            "telegram_commerce_owner": "TelegramCommerceService",
            "sources_consumed": {
                key: value is not None for key, value in sources.items()
            },
        }

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
    def _enum_value(value: Any) -> str | None:
        if value is None:
            return None
        raw = getattr(value, "value", value)
        return str(raw) if raw not in (None, "") else None

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        raw = getattr(value, "value", value)
        if raw in (None, ""):
            return None
        return str(raw)

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

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

    @classmethod
    def _merge_text_tuples(cls, *values: Any) -> tuple[str, ...]:
        merged: list[str] = []
        for value in values:
            for item in cls._text_tuple(value):
                if item not in merged:
                    merged.append(item)
        return tuple(merged)

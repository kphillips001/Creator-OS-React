"""Sales Management read-model recommendation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.conversation_operations import (
    ConversationOperation,
    ConversationOperationStatus,
)
from app.models.sales_management import (
    SalesManagement,
    SalesPriority,
    SalesRecommendation,
    SalesRecommendationType,
)
from app.models.telegram_business import TelegramBusinessSnapshot

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.commerce_strategy_service import CommerceStrategyService
    from app.services.conversation_operations_service import ConversationOperationsService
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.product_business_service import ProductBusinessService
    from app.services.telegram_business_service import TelegramBusinessService


class SalesManagementService:
    """Recommend the next sales action from existing Creator OS intelligence.

    This service is read-only and recommendation-only. It does not execute
    Telegram, generate responses, mutate Products, generate Product Strategy,
    generate Commerce Strategy, publish Products, or record Business Learning.
    """

    def __init__(
        self,
        *,
        telegram_business_service: "TelegramBusinessService | None" = None,
        conversation_operations_service: "ConversationOperationsService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        commerce_strategy_service: "CommerceStrategyService | None" = None,
        product_business_service: "ProductBusinessService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
    ) -> None:
        self._telegram_business = telegram_business_service
        self._conversation_operations = conversation_operations_service
        self._customer_intelligence = customer_intelligence_service
        self._commerce_strategy = commerce_strategy_service
        self._product_business = product_business_service
        self._business_learning = business_learning_service

    @property
    def telegram_business(self) -> "TelegramBusinessService":
        if self._telegram_business is None:
            from app.services.telegram_business_service import TelegramBusinessService

            self._telegram_business = TelegramBusinessService(
                customer_intelligence_service=self._customer_intelligence,
                commerce_strategy_service=self._commerce_strategy,
                product_business_service=self._product_business,
                business_learning_service=self._business_learning,
            )
        return self._telegram_business

    @property
    def conversation_operations(self) -> "ConversationOperationsService":
        if self._conversation_operations is None:
            from app.services.conversation_operations_service import (
                ConversationOperationsService,
            )

            self._conversation_operations = ConversationOperationsService(
                telegram_business_service=self.telegram_business,
                customer_intelligence_service=self._customer_intelligence,
            )
        return self._conversation_operations

    def build_management(
        self,
        *,
        customer_id: str | int | None = None,
        telegram_business_snapshot: TelegramBusinessSnapshot | Mapping[str, Any] | None = None,
        conversation_operation: ConversationOperation | Mapping[str, Any] | None = None,
        customer_snapshot: Any | None = None,
        commerce_strategy_result: Any | None = None,
        product_business_snapshot: Any | None = None,
        product_business_snapshots: Iterable[Any] | None = None,
        learning_context: Any | None = None,
        business_outcomes: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
        **telegram_business_context: Any,
    ) -> SalesManagement:
        """Return the canonical read-only sales state for one customer."""

        snapshot = telegram_business_snapshot or self.telegram_business.build_snapshot(
            customer_id=customer_id,
            customer_snapshot=customer_snapshot,
            commerce_strategy_result=commerce_strategy_result,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            learning_context=learning_context,
            business_outcomes=business_outcomes,
            metadata=metadata,
            **telegram_business_context,
        )
        operation = self._operation(
            conversation_operation=conversation_operation,
            snapshot=snapshot,
            customer_id=customer_id,
        )
        evidence = self._evidence(
            snapshot=snapshot,
            operation=operation,
            customer_snapshot=customer_snapshot,
            commerce_strategy_result=commerce_strategy_result,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            learning_context=learning_context,
            business_outcomes=business_outcomes,
        )
        recommendation = self._recommend(evidence)
        return SalesManagement(
            customer_id=(
                self._safe_text(customer_id)
                or self._safe_text(self._read(snapshot, "customer_id"))
                or self._safe_text(self._read(snapshot, "customer_identity", "customer_id"))
                or self._safe_text(
                    self._read(snapshot, "customer_identity", "canonical_customer_id")
                )
            ),
            provider=self._safe_text(self._read(snapshot, "provider")) or "telegram",
            relationship_stage=self._safe_text(
                self._read(snapshot, "relationship", "stage")
                or self._read(snapshot, "summary", "relationship_stage")
            ),
            conversation_status=self._safe_text(self._read(operation, "status")),
            business_health=self._safe_text(self._read(snapshot, "business_health"))
            or "UNKNOWN",
            current_product_ids=self._text_tuple(
                self._read(snapshot, "summary", "current_product_ids")
                or self._read(snapshot, "current_product_ids")
            ),
            active_offer_ids=self._text_tuple(
                self._read(snapshot, "summary", "active_offer_ids")
                or tuple(
                    self._read(item, "offer_id")
                    for item in tuple(self._read(snapshot, "active_offers") or ())
                )
            ),
            recommendation=recommendation,
            recommendations=(recommendation,),
            compatibility=self._compatibility(
                snapshot=snapshot,
                operation=operation,
                commerce_strategy_result=commerce_strategy_result,
                product_business_snapshot=product_business_snapshot,
                product_business_snapshots=product_business_snapshots,
                learning_context=learning_context,
                business_outcomes=business_outcomes,
            ),
            metadata={
                "source": "sales_management",
                "owner": "SalesManagementService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_recommendation(self, **context: Any) -> SalesRecommendation:
        return self.build_management(**context).recommendation

    def _operation(
        self,
        *,
        conversation_operation: ConversationOperation | Mapping[str, Any] | None,
        snapshot: TelegramBusinessSnapshot | Mapping[str, Any],
        customer_id: str | int | None,
    ) -> ConversationOperation | Mapping[str, Any]:
        if conversation_operation is not None:
            return conversation_operation
        return self.conversation_operations.build_operation(
            customer_id=customer_id,
            telegram_business_snapshot=snapshot,
        )

    def _evidence(
        self,
        *,
        snapshot: Any,
        operation: Any,
        customer_snapshot: Any | None,
        commerce_strategy_result: Any | None,
        product_business_snapshot: Any | None,
        product_business_snapshots: Iterable[Any] | None,
        learning_context: Any | None,
        business_outcomes: Any | None,
    ) -> dict[str, Any]:
        strategy_recommendations = tuple(
            self._read(commerce_strategy_result, "recommendations")
            or self._read(snapshot, "commerce_strategy", "recommendations")
            or ()
        )
        strategy_objectives = self._text_tuple(
            self._read(snapshot, "commerce_strategy", "recommended_objectives")
        )
        if not strategy_objectives:
            strategy_objectives = self._text_tuple(
                self._read(item, "recommended_objective")
                for item in strategy_recommendations
            )
        products = self._products(
            snapshot=snapshot,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        active_offers = tuple(self._read(snapshot, "active_offers") or ())
        delivery_history = self._read(snapshot, "delivery_history") or {}
        business_learning = self._read(snapshot, "business_learning") or {}
        return {
            "customer_id": self._safe_text(
                self._read(snapshot, "customer_id")
                or self._read(snapshot, "customer_identity", "customer_id")
            ),
            "relationship_stage": self._safe_text(
                self._read(snapshot, "relationship", "stage")
                or self._read(customer_snapshot, "relationship_stage")
            ),
            "relationship_recommendation": self._safe_text(
                self._read(snapshot, "relationship", "primary_recommendation")
                or self._read(
                    self._read(customer_snapshot, "relationship_intelligence"),
                    "primary_recommendation",
                )
            ),
            "operation_status": self._safe_text(self._read(operation, "status")),
            "operation_next_action": self._safe_text(
                self._read(operation, "next_operational_action")
            ),
            "business_health": self._safe_text(self._read(snapshot, "business_health")),
            "current_experience_id": self._safe_text(
                self._read(snapshot, "summary", "current_experience_id")
                or self._read(operation, "current_experience_id")
            ),
            "experience_state": self._safe_text(
                self._read(snapshot, "experience", "experience_state")
                or self._read(operation, "experience_state")
            ),
            "active_offer_count": len(
                tuple(item for item in active_offers if self._read(item, "active") is not False)
            ),
            "active_offer_ids": self._text_tuple(
                self._read(snapshot, "summary", "active_offer_ids")
                or tuple(self._read(item, "offer_id") for item in active_offers)
            ),
            "pending_delivery_methods": self._text_tuple(
                self._read(operation, "pending_delivery_methods")
            ),
            "delivery_count": self._int(self._read(delivery_history, "delivery_count")),
            "duplicate_prevention_signals": self._text_tuple(
                self._read(delivery_history, "duplicate_prevention_signals")
            ),
            "products": products,
            "commerce_strategy_recommendations": strategy_recommendations,
            "commerce_strategy_objectives": strategy_objectives,
            "commerce_strategy_confidence": self._float(
                self._read(commerce_strategy_result, "confidence")
                or self._read(snapshot, "commerce_strategy", "confidence")
            ),
            "learning_consumed": bool(
                learning_context
                or business_outcomes
                or self._read(business_learning, "consumed")
            ),
            "learning_metric_count": self._int(
                self._read(business_learning, "metric_count")
                or self._read(
                    self._read(learning_context, "performance_snapshot"),
                    "metrics",
                    "count",
                )
            ),
        }

    def _recommend(self, evidence: Mapping[str, Any]) -> SalesRecommendation:
        status = str(evidence.get("operation_status") or "").upper()
        objective_text = " ".join(
            item.lower()
            for item in self._text_tuple(evidence.get("commerce_strategy_objectives"))
        )
        product = self._primary_product(evidence)
        product_type = self._safe_text(self._read(product, "product_type")) or ""
        delivery_type = self._safe_text(self._read(product, "delivery_type")) or ""

        if status == ConversationOperationStatus.COMPLETED.value:
            return self._make(
                SalesRecommendationType.NO_SALES_ACTION,
                SalesPriority.LOW,
                evidence,
                "No Sales Action",
                confidence=0.4,
            )
        if status in {
            ConversationOperationStatus.WAITING_FOR_CUSTOMER.value,
            ConversationOperationStatus.STALLED.value,
        }:
            return self._make(
                SalesRecommendationType.DELAY_SELLING,
                SalesPriority.NORMAL,
                evidence,
                "Delay Selling",
                confidence=self._confidence(evidence, fallback=0.6),
            )
        if status == ConversationOperationStatus.PAUSED.value:
            return self._make(
                SalesRecommendationType.CONTINUE_EXPERIENCE,
                SalesPriority.NORMAL,
                evidence,
                "Continue Experience",
                confidence=self._confidence(evidence, fallback=0.58),
            )
        strategy_type = self._recommendation_from_text(objective_text)
        if strategy_type is not None:
            return self._make(
                strategy_type,
                self._priority(strategy_type, status),
                evidence,
                self._label(strategy_type),
                confidence=self._confidence(evidence, fallback=0.72),
            )
        product_type_result = self._recommendation_from_text(product_type)
        if product_type_result is not None:
            return self._make(
                product_type_result,
                self._priority(product_type_result, status),
                evidence,
                self._label(product_type_result),
                confidence=self._confidence(evidence, fallback=0.66),
            )
        if delivery_type.upper() == "FREE":
            return self._make(
                SalesRecommendationType.OFFER_FREE_PRODUCT,
                SalesPriority.NORMAL,
                evidence,
                "Offer FREE Product",
                confidence=self._confidence(evidence, fallback=0.62),
            )
        if delivery_type.upper() == "PAID":
            return self._make(
                SalesRecommendationType.OFFER_PREMIUM_PRODUCT,
                self._priority(SalesRecommendationType.OFFER_PREMIUM_PRODUCT, status),
                evidence,
                "Offer Premium Product",
                confidence=self._confidence(evidence, fallback=0.66),
            )
        if status == ConversationOperationStatus.EXPERIENCE_ACTIVE.value:
            return self._make(
                SalesRecommendationType.CONTINUE_EXPERIENCE,
                SalesPriority.NORMAL,
                evidence,
                "Continue Experience",
                confidence=self._confidence(evidence, fallback=0.58),
            )
        if evidence.get("relationship_recommendation"):
            return self._make(
                SalesRecommendationType.CONTINUE_RELATIONSHIP,
                SalesPriority.NORMAL,
                evidence,
                "Continue Relationship",
                confidence=self._confidence(evidence, fallback=0.55),
            )
        return self._make(
            SalesRecommendationType.NO_SALES_ACTION,
            SalesPriority.LOW,
            evidence,
            "No Sales Action",
            confidence=0.35,
        )

    def _make(
        self,
        recommendation_type: SalesRecommendationType,
        priority: SalesPriority,
        evidence: Mapping[str, Any],
        action: str,
        *,
        confidence: float,
    ) -> SalesRecommendation:
        product = self._primary_product(evidence)
        return SalesRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, confidence)), 2),
            recommended_next_action=action,
            supporting_evidence={
                "source": "SalesManagementService",
                "customer_intelligence": {
                    "relationship_stage": evidence.get("relationship_stage"),
                    "relationship_recommendation": evidence.get(
                        "relationship_recommendation"
                    ),
                },
                "commerce_strategy": {
                    "objectives": self._text_tuple(
                        evidence.get("commerce_strategy_objectives")
                    ),
                    "confidence": evidence.get("commerce_strategy_confidence"),
                    "generated_by_sales_management": False,
                },
                "product_business": {
                    "product_id": self._read(product, "product_id"),
                    "product_type": self._read(product, "product_type"),
                    "delivery_type": self._read(product, "delivery_type"),
                    "product_health": self._read(product, "product_health"),
                },
                "conversation_operations": {
                    "status": evidence.get("operation_status"),
                    "next_operational_action": evidence.get("operation_next_action"),
                },
                "business_learning": {
                    "consumed": evidence.get("learning_consumed"),
                    "metric_count": evidence.get("learning_metric_count"),
                },
                "duplicate_offer_prevention": {
                    "active_offer_ids": self._text_tuple(
                        evidence.get("active_offer_ids")
                    ),
                    "duplicate_prevention_signals": self._text_tuple(
                        evidence.get("duplicate_prevention_signals")
                    ),
                },
            },
            product_reference=self._safe_text(self._read(product, "product_id")),
            offer_reference=self._first_text(evidence.get("active_offer_ids")),
            experience_reference=self._safe_text(evidence.get("current_experience_id")),
            customer_reference=self._safe_text(evidence.get("customer_id")),
            metadata={
                "recommendation_only": True,
                "aggregation_only": True,
                "read_only": True,
            },
        )

    @staticmethod
    def _recommendation_from_text(text: str) -> SalesRecommendationType | None:
        lowered = text.lower()
        if "upsell" in lowered:
            return SalesRecommendationType.UPSELL
        if "cross" in lowered:
            return SalesRecommendationType.CROSS_SELL
        if "delay" in lowered or "wait" in lowered:
            return SalesRecommendationType.DELAY_SELLING
        if "free" in lowered or "preview" in lowered:
            return SalesRecommendationType.OFFER_FREE_PRODUCT
        if "bundle" in lowered or "collection" in lowered:
            return SalesRecommendationType.OFFER_BUNDLE
        if "story" in lowered:
            return SalesRecommendationType.OFFER_STORY
        if "photoshoot" in lowered or "photo_shoot" in lowered:
            return SalesRecommendationType.OFFER_PHOTOSHOOT
        if "premium" in lowered or "paid" in lowered:
            return SalesRecommendationType.OFFER_PREMIUM_PRODUCT
        return None

    @staticmethod
    def _priority(
        recommendation_type: SalesRecommendationType,
        operation_status: str,
    ) -> SalesPriority:
        if recommendation_type in {
            SalesRecommendationType.UPSELL,
            SalesRecommendationType.CROSS_SELL,
            SalesRecommendationType.OFFER_BUNDLE,
            SalesRecommendationType.OFFER_STORY,
            SalesRecommendationType.OFFER_PHOTOSHOOT,
            SalesRecommendationType.OFFER_PREMIUM_PRODUCT,
        }:
            return SalesPriority.HIGH
        if recommendation_type == SalesRecommendationType.NO_SALES_ACTION:
            return SalesPriority.LOW
        if operation_status == ConversationOperationStatus.STALLED.value:
            return SalesPriority.HIGH
        return SalesPriority.NORMAL

    @staticmethod
    def _label(recommendation_type: SalesRecommendationType) -> str:
        return {
            SalesRecommendationType.CONTINUE_RELATIONSHIP: "Continue Relationship",
            SalesRecommendationType.OFFER_FREE_PRODUCT: "Offer FREE Product",
            SalesRecommendationType.OFFER_PREMIUM_PRODUCT: "Offer Premium Product",
            SalesRecommendationType.OFFER_BUNDLE: "Offer Bundle",
            SalesRecommendationType.OFFER_STORY: "Offer Story",
            SalesRecommendationType.OFFER_PHOTOSHOOT: "Offer Photoshoot",
            SalesRecommendationType.UPSELL: "Upsell",
            SalesRecommendationType.CROSS_SELL: "Cross-sell",
            SalesRecommendationType.DELAY_SELLING: "Delay Selling",
            SalesRecommendationType.CONTINUE_EXPERIENCE: "Continue Experience",
            SalesRecommendationType.NO_SALES_ACTION: "No Sales Action",
        }[recommendation_type]

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "sales_management",
            "owner": "SalesManagementService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "recommendation_only": True,
            "executes_telegram": False,
            "generates_responses": False,
            "modifies_products": False,
            "generates_product_strategy": False,
            "generates_commerce_strategy": False,
            "publishes_products": False,
            "records_business_learning": False,
            "modifies_customer_intelligence": False,
            "telegram_runtime_owner": "Telegram runtime",
            "telegram_business_owner": "TelegramBusinessService",
            "conversation_operations_owner": "ConversationOperationsService",
            "commerce_strategy_owner": "CommerceStrategyService",
            "customer_intelligence_owner": "CustomerIntelligenceService",
            "product_business_owner": "ProductBusinessService",
            "business_learning_owner": "BusinessLearningService",
            "sources_consumed": {key: value is not None for key, value in sources.items()},
        }

    @classmethod
    def _products(
        cls,
        *,
        snapshot: Any,
        product_business_snapshot: Any | None,
        product_business_snapshots: Iterable[Any] | None,
    ) -> tuple[Any, ...]:
        values: list[Any] = []
        if product_business_snapshot is not None:
            values.append(product_business_snapshot)
        if product_business_snapshots is not None:
            values.extend(item for item in product_business_snapshots if item is not None)
        values.extend(tuple(cls._read(snapshot, "products") or ()))
        return tuple(values)

    @classmethod
    def _primary_product(cls, evidence: Mapping[str, Any]) -> Any | None:
        products = tuple(evidence.get("products") or ())
        if not products:
            return None
        for product in products:
            if cls._read(product, "availability") == "TELEGRAM_READY":
                return product
        return products[0]

    @classmethod
    def _confidence(cls, evidence: Mapping[str, Any], *, fallback: float) -> float:
        strategy_confidence = cls._float(evidence.get("commerce_strategy_confidence"))
        if strategy_confidence:
            return strategy_confidence
        if evidence.get("learning_consumed"):
            return max(fallback, 0.64)
        return fallback

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
    def _first_text(cls, value: Any) -> str | None:
        values = cls._text_tuple(value)
        return values[0] if values else None

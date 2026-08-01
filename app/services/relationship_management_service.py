"""Relationship Management read-model recommendation service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.conversation_operations import (
    ConversationOperation,
    ConversationOperationStatus,
)
from app.models.delivery_management import DeliveryManagement
from app.models.relationship_management import (
    RelationshipHealth,
    RelationshipManagement,
    RelationshipPriority,
    RelationshipRecommendation,
    RelationshipRecommendationType,
)
from app.models.sales_management import SalesManagement
from app.models.telegram_business import TelegramBusinessSnapshot

if TYPE_CHECKING:
    from app.services.business_learning_service import BusinessLearningService
    from app.services.conversation_operations_service import ConversationOperationsService
    from app.services.customer_intelligence_service import CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService
    from app.services.delivery_management_service import DeliveryManagementService
    from app.services.sales_management_service import SalesManagementService
    from app.services.telegram_business_service import TelegramBusinessService


class RelationshipManagementService:
    """Recommend long-term relationship actions from existing intelligence."""

    def __init__(
        self,
        *,
        telegram_business_service: "TelegramBusinessService | None" = None,
        conversation_operations_service: "ConversationOperationsService | None" = None,
        sales_management_service: "SalesManagementService | None" = None,
        delivery_management_service: "DeliveryManagementService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        business_learning_service: "BusinessLearningService | None" = None,
    ) -> None:
        self._telegram_business = telegram_business_service
        self._conversation_operations = conversation_operations_service
        self._sales_management = sales_management_service
        self._delivery_management = delivery_management_service
        self._customer_intelligence = customer_intelligence_service
        self._business_learning = business_learning_service

    @property
    def telegram_business(self) -> "TelegramBusinessService":
        if self._telegram_business is None:
            from app.services.telegram_business_service import TelegramBusinessService

            self._telegram_business = TelegramBusinessService(
                customer_intelligence_service=self._customer_intelligence,
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

    @property
    def sales_management(self) -> "SalesManagementService":
        if self._sales_management is None:
            from app.services.sales_management_service import SalesManagementService

            self._sales_management = SalesManagementService(
                telegram_business_service=self.telegram_business,
                conversation_operations_service=self.conversation_operations,
                customer_intelligence_service=self._customer_intelligence,
                business_learning_service=self._business_learning,
            )
        return self._sales_management

    @property
    def delivery_management(self) -> "DeliveryManagementService":
        if self._delivery_management is None:
            from app.services.delivery_management_service import DeliveryManagementService

            self._delivery_management = DeliveryManagementService(
                telegram_business_service=self.telegram_business,
                conversation_operations_service=self.conversation_operations,
                sales_management_service=self.sales_management,
                customer_intelligence_service=self._customer_intelligence,
            )
        return self._delivery_management

    def build_management(
        self,
        *,
        customer_id: str | int | None = None,
        telegram_business_snapshot: TelegramBusinessSnapshot | Mapping[str, Any] | None = None,
        conversation_operation: ConversationOperation | Mapping[str, Any] | None = None,
        sales_management: SalesManagement | Mapping[str, Any] | None = None,
        delivery_management: DeliveryManagement | Mapping[str, Any] | None = None,
        customer_snapshot: Any | None = None,
        learning_context: Any | None = None,
        business_outcomes: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
        **telegram_business_context: Any,
    ) -> RelationshipManagement:
        """Return the canonical read-only relationship state."""

        snapshot = telegram_business_snapshot or self.telegram_business.build_snapshot(
            customer_id=customer_id,
            customer_snapshot=customer_snapshot,
            learning_context=learning_context,
            business_outcomes=business_outcomes,
            metadata=metadata,
            **telegram_business_context,
        )
        operation = conversation_operation or self.conversation_operations.build_operation(
            customer_id=customer_id,
            telegram_business_snapshot=snapshot,
        )
        sales = sales_management or self.sales_management.build_management(
            customer_id=customer_id,
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            customer_snapshot=customer_snapshot,
            learning_context=learning_context,
            business_outcomes=business_outcomes,
        )
        delivery = delivery_management or self.delivery_management.build_management(
            customer_id=customer_id,
            telegram_business_snapshot=snapshot,
            conversation_operation=operation,
            sales_management=sales,
            customer_snapshot=customer_snapshot,
        )
        evidence = self._evidence(
            snapshot=snapshot,
            operation=operation,
            sales=sales,
            delivery=delivery,
            customer_snapshot=customer_snapshot,
            learning_context=learning_context,
            business_outcomes=business_outcomes,
        )
        health = self._health(evidence)
        recommendation = self._recommend(health, evidence)
        return RelationshipManagement(
            customer_id=(
                self._safe_text(customer_id)
                or self._safe_text(self._read(snapshot, "customer_id"))
                or self._safe_text(self._read(snapshot, "customer_identity", "customer_id"))
                or self._safe_text(
                    self._read(snapshot, "customer_identity", "canonical_customer_id")
                )
            ),
            provider=self._safe_text(self._read(snapshot, "provider")) or "telegram",
            relationship_stage=self._safe_text(evidence.get("relationship_stage")),
            relationship_health=health,
            engagement_score=self._int(evidence.get("engagement_score")),
            engagement_level=self._safe_text(evidence.get("engagement_level")),
            commerce_maturity=self._safe_text(evidence.get("commerce_maturity")),
            recommendation=recommendation,
            recommendations=(recommendation,),
            compatibility=self._compatibility(
                snapshot=snapshot,
                operation=operation,
                sales=sales,
                delivery=delivery,
                customer_snapshot=customer_snapshot,
                learning_context=learning_context,
                business_outcomes=business_outcomes,
            ),
            metadata={
                "source": "relationship_management",
                "owner": "RelationshipManagementService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_recommendation(self, **context: Any) -> RelationshipRecommendation:
        return self.build_management(**context).recommendation

    def _evidence(
        self,
        *,
        snapshot: Any,
        operation: Any,
        sales: Any,
        delivery: Any,
        customer_snapshot: Any | None,
        learning_context: Any | None,
        business_outcomes: Any | None,
    ) -> dict[str, Any]:
        relationship = self._read(snapshot, "relationship") or {}
        memory = self._read(customer_snapshot, "commerce_memory")
        profile = self._read(customer_snapshot, "profile")
        progress = self._read(customer_snapshot, "experience_progress")
        sales_recommendation = self._read(sales, "recommendation")
        delivery_recommendation = self._read(delivery, "recommendation")
        business_learning = self._read(snapshot, "business_learning") or {}
        return {
            "customer_id": self._safe_text(
                self._read(snapshot, "customer_id")
                or self._read(snapshot, "customer_identity", "customer_id")
            ),
            "relationship_stage": self._safe_text(
                self._read(relationship, "stage")
                or self._read(customer_snapshot, "relationship_stage")
            ),
            "engagement_score": self._int(
                self._read(relationship, "engagement_score")
                or self._read(
                    self._read(customer_snapshot, "relationship_intelligence"),
                    "engagement_score",
                )
            ),
            "engagement_level": self._safe_text(
                self._read(relationship, "engagement_level")
                or self._read(
                    self._read(customer_snapshot, "relationship_intelligence"),
                    "engagement_level",
                )
            ),
            "commerce_maturity": self._safe_text(
                self._read(relationship, "commerce_maturity")
                or self._read(
                    self._read(customer_snapshot, "relationship_intelligence"),
                    "commerce_maturity",
                )
            ),
            "relationship_recommendation": self._safe_text(
                self._read(relationship, "primary_recommendation")
                or self._read(
                    self._read(customer_snapshot, "relationship_intelligence"),
                    "primary_recommendation",
                )
            ),
            "customer_segments": self._text_tuple(
                self._read(profile, "customer_segments")
            ),
            "tags": self._text_tuple(self._read(profile, "tags")),
            "operation_status": self._safe_text(self._read(operation, "status")),
            "operation_next_action": self._safe_text(
                self._read(operation, "next_operational_action")
            ),
            "current_experience_id": self._safe_text(
                self._read(snapshot, "summary", "current_experience_id")
                or self._read(operation, "current_experience_id")
                or self._read(progress, "current_experience_id")
            ),
            "progress_percentage": self._int(
                self._read(snapshot, "experience", "progress_percentage")
                or self._read(progress, "progress_percentage")
            ),
            "sales_recommendation_type": self._safe_text(
                self._read(sales_recommendation, "recommendation_type")
            ),
            "sales_priority": self._safe_text(
                self._read(sales_recommendation, "priority")
            ),
            "sales_confidence": self._float(
                self._read(sales_recommendation, "confidence")
            ),
            "delivery_recommendation_type": self._safe_text(
                self._read(delivery_recommendation, "recommendation_type")
            ),
            "delivery_priority": self._safe_text(
                self._read(delivery_recommendation, "priority")
            ),
            "delivery_count": self._int(
                self._read(snapshot, "delivery_history", "delivery_count")
            ),
            "purchase_count": len(
                self._merge_text_tuples(
                    self._read(memory, "products_purchased"),
                    self._read(memory, "previous_purchases"),
                    self._read(memory, "purchased_bundles"),
                    self._read(memory, "purchased_photoshoots"),
                    self._read(memory, "purchased_stories"),
                )
            ),
            "declined_offer_count": len(
                self._text_tuple(self._read(memory, "declined_offers"))
            ),
            "spend_cents": self._int(
                self._read(memory, "customer_spending_summary", "total_spend_cents")
                or self._read(memory, "customer_spending_summary", "lifetime_value_cents")
            ),
            "business_health": self._safe_text(self._read(snapshot, "business_health")),
            "learning_consumed": bool(
                learning_context
                or business_outcomes
                or self._read(business_learning, "consumed")
            ),
            "learning_metric_count": self._int(
                self._read(business_learning, "metric_count")
            ),
        }

    def _health(self, evidence: Mapping[str, Any]) -> RelationshipHealth:
        stage = str(evidence.get("relationship_stage") or "").lower()
        operation_status = str(evidence.get("operation_status") or "").upper()
        engagement = str(evidence.get("engagement_level") or "").lower()
        segments = {item.lower() for item in self._text_tuple(evidence.get("customer_segments"))}
        tags = {item.lower() for item in self._text_tuple(evidence.get("tags"))}
        if (
            stage == "vip"
            or "vip" in segments
            or "vip" in tags
            or self._int(evidence.get("purchase_count")) >= 3
            or self._int(evidence.get("spend_cents")) >= 50000
        ):
            return RelationshipHealth.VIP_OPPORTUNITY
        if stage == "dormant" or engagement in {"none", "dormant", "inactive"}:
            return RelationshipHealth.DISENGAGED
        if (
            operation_status == ConversationOperationStatus.STALLED.value
            or self._int(evidence.get("declined_offer_count")) >= 2
            or str(evidence.get("business_health") or "").upper() == "NEEDS_ATTENTION"
        ):
            return RelationshipHealth.AT_RISK
        if stage in {"new", "returning"}:
            return RelationshipHealth.TRUST_BUILDING
        if str(evidence.get("commerce_maturity") or "").lower() in {
            "offer_ready",
            "buyer_ready",
            "purchase_ready",
        }:
            return RelationshipHealth.SELLING_READY
        if stage in {"active", "engaged", "purchaser", "repeat_purchaser"}:
            return RelationshipHealth.HEALTHY
        return RelationshipHealth.UNKNOWN

    def _recommend(
        self,
        health: RelationshipHealth,
        evidence: Mapping[str, Any],
    ) -> RelationshipRecommendation:
        operation_status = str(evidence.get("operation_status") or "").upper()
        sales_type = str(evidence.get("sales_recommendation_type") or "")
        delivery_type = str(evidence.get("delivery_recommendation_type") or "")
        if health == RelationshipHealth.VIP_OPPORTUNITY:
            return self._make(
                RelationshipRecommendationType.VIP_OPPORTUNITY,
                health,
                RelationshipPriority.HIGH,
                evidence,
                "VIP Opportunity",
                confidence=self._confidence(evidence, fallback=0.82),
            )
        if health == RelationshipHealth.DISENGAGED:
            return self._make(
                RelationshipRecommendationType.RE_ENGAGE_CUSTOMER,
                health,
                RelationshipPriority.HIGH,
                evidence,
                "Re-engage Customer",
                confidence=self._confidence(evidence, fallback=0.72),
            )
        if health == RelationshipHealth.AT_RISK:
            recommendation_type = (
                RelationshipRecommendationType.FOLLOW_UP
                if operation_status == ConversationOperationStatus.STALLED.value
                else RelationshipRecommendationType.DELAY_SELLING
            )
            return self._make(
                recommendation_type,
                health,
                RelationshipPriority.HIGH,
                evidence,
                "Follow Up" if recommendation_type == RelationshipRecommendationType.FOLLOW_UP else "Delay Selling",
                confidence=self._confidence(evidence, fallback=0.7),
            )
        if health == RelationshipHealth.TRUST_BUILDING:
            return self._make(
                RelationshipRecommendationType.BUILD_TRUST,
                health,
                RelationshipPriority.NORMAL,
                evidence,
                "Build Trust",
                confidence=self._confidence(evidence, fallback=0.62),
            )
        if (
            operation_status == ConversationOperationStatus.EXPERIENCE_ACTIVE.value
            or evidence.get("current_experience_id")
            and sales_type.endswith("CONTINUE_EXPERIENCE")
        ):
            return self._make(
                RelationshipRecommendationType.CONTINUE_EXPERIENCE,
                health,
                RelationshipPriority.NORMAL,
                evidence,
                "Continue Experience",
                confidence=self._confidence(evidence, fallback=0.66),
            )
        if (
            health == RelationshipHealth.SELLING_READY
            and (
                "OFFER_" in sales_type
                or sales_type.endswith("UPSELL")
                or sales_type.endswith("CROSS_SELL")
            )
            and not delivery_type.endswith("PREVENT_DUPLICATE_DELIVERY")
        ):
            return self._make(
                RelationshipRecommendationType.INCREASE_SELLING,
                health,
                RelationshipPriority.HIGH,
                evidence,
                "Increase Selling",
                confidence=self._confidence(evidence, fallback=0.74),
            )
        if evidence.get("relationship_recommendation"):
            return self._make(
                RelationshipRecommendationType.CONTINUE_RELATIONSHIP,
                health,
                RelationshipPriority.NORMAL,
                evidence,
                "Continue Relationship",
                confidence=self._confidence(evidence, fallback=0.58),
            )
        return self._make(
            RelationshipRecommendationType.NO_RELATIONSHIP_ACTION,
            health,
            RelationshipPriority.LOW,
            evidence,
            "No Relationship Action",
            confidence=0.35,
        )

    def _make(
        self,
        recommendation_type: RelationshipRecommendationType,
        health: RelationshipHealth,
        priority: RelationshipPriority,
        evidence: Mapping[str, Any],
        action: str,
        *,
        confidence: float,
    ) -> RelationshipRecommendation:
        return RelationshipRecommendation(
            recommendation_type=recommendation_type,
            relationship_health=health,
            priority=priority,
            confidence=round(max(0.0, min(1.0, confidence)), 2),
            recommended_next_action=action,
            supporting_evidence={
                "source": "RelationshipManagementService",
                "customer_intelligence": {
                    "relationship_stage": evidence.get("relationship_stage"),
                    "engagement_score": evidence.get("engagement_score"),
                    "engagement_level": evidence.get("engagement_level"),
                    "commerce_maturity": evidence.get("commerce_maturity"),
                    "purchase_count": evidence.get("purchase_count"),
                    "declined_offer_count": evidence.get("declined_offer_count"),
                    "spend_cents": evidence.get("spend_cents"),
                },
                "telegram_business": {
                    "business_health": evidence.get("business_health"),
                    "delivery_count": evidence.get("delivery_count"),
                },
                "conversation_operations": {
                    "status": evidence.get("operation_status"),
                    "next_operational_action": evidence.get("operation_next_action"),
                },
                "sales_management": {
                    "recommendation_type": evidence.get("sales_recommendation_type"),
                    "priority": evidence.get("sales_priority"),
                    "confidence": evidence.get("sales_confidence"),
                },
                "delivery_management": {
                    "recommendation_type": evidence.get("delivery_recommendation_type"),
                    "priority": evidence.get("delivery_priority"),
                },
                "business_learning": {
                    "consumed": evidence.get("learning_consumed"),
                    "metric_count": evidence.get("learning_metric_count"),
                },
            },
            customer_reference=self._safe_text(evidence.get("customer_id")),
            experience_reference=self._safe_text(evidence.get("current_experience_id")),
            metadata={
                "recommendation_only": True,
                "aggregation_only": True,
                "read_only": True,
            },
        )

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "relationship_management",
            "owner": "RelationshipManagementService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "recommendation_only": True,
            "executes_telegram": False,
            "generates_responses": False,
            "modifies_customer_intelligence": False,
            "publishes_products": False,
            "modifies_products": False,
            "records_business_learning": False,
            "telegram_runtime_owner": "Telegram runtime",
            "telegram_business_owner": "TelegramBusinessService",
            "conversation_operations_owner": "ConversationOperationsService",
            "sales_management_owner": "SalesManagementService",
            "delivery_management_owner": "DeliveryManagementService",
            "customer_intelligence_owner": "CustomerIntelligenceCompatibilityAdapter",
            "business_learning_owner": "BusinessLearningService",
            "sources_consumed": {key: value is not None for key, value in sources.items()},
        }

    @classmethod
    def _confidence(cls, evidence: Mapping[str, Any], *, fallback: float) -> float:
        sales_confidence = cls._float(evidence.get("sales_confidence"))
        if sales_confidence:
            return max(fallback, sales_confidence)
        if evidence.get("learning_consumed"):
            return max(fallback, 0.64)
        if cls._int(evidence.get("engagement_score")):
            return max(fallback, min(0.9, cls._int(evidence.get("engagement_score")) / 100))
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
    def _merge_text_tuples(cls, *values: Any) -> tuple[str, ...]:
        merged: list[str] = []
        for value in values:
            for item in cls._text_tuple(value):
                if item not in merged:
                    merged.append(item)
        return tuple(merged)

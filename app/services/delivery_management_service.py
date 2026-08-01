"""Delivery Management read-model recommendation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.conversation_operations import (
    ConversationOperation,
    ConversationOperationStatus,
)
from app.models.delivery_management import (
    DeliveryManagement,
    DeliveryPriority,
    DeliveryRecommendation,
    DeliveryRecommendationType,
)
from app.models.product_availability import (
    ProductAvailability,
    ProductAvailabilityStatus,
)
from app.models.sales_management import SalesManagement
from app.models.telegram_business import TelegramBusinessSnapshot

if TYPE_CHECKING:
    from app.services.commerce_execution_service import CommerceExecutionService
    from app.services.conversation_operations_service import ConversationOperationsService
    from app.services.customer_intelligence_service import CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService
    from app.services.product_availability_service import ProductAvailabilityService
    from app.services.publishing_service import PublishingService
    from app.services.sales_management_service import SalesManagementService
    from app.services.telegram_business_service import TelegramBusinessService


class DeliveryManagementService:
    """Recommend Telegram delivery actions without executing delivery."""

    def __init__(
        self,
        *,
        telegram_business_service: "TelegramBusinessService | None" = None,
        conversation_operations_service: "ConversationOperationsService | None" = None,
        sales_management_service: "SalesManagementService | None" = None,
        product_availability_service: "ProductAvailabilityService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        publishing_service: "PublishingService | None" = None,
        commerce_execution_service: "CommerceExecutionService | None" = None,
    ) -> None:
        self._telegram_business = telegram_business_service
        self._conversation_operations = conversation_operations_service
        self._sales_management = sales_management_service
        self._product_availability = product_availability_service
        self._customer_intelligence = customer_intelligence_service
        self._publishing = publishing_service
        self._commerce_execution = commerce_execution_service

    @property
    def telegram_business(self) -> "TelegramBusinessService":
        if self._telegram_business is None:
            from app.services.telegram_business_service import TelegramBusinessService

            self._telegram_business = TelegramBusinessService(
                customer_intelligence_service=self._customer_intelligence,
                publishing_service=self._publishing,
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
                commerce_execution_service=self._commerce_execution,
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
            )
        return self._sales_management

    @property
    def product_availability(self) -> "ProductAvailabilityService":
        if self._product_availability is None:
            from app.services.product_availability_service import (
                ProductAvailabilityService,
            )

            self._product_availability = ProductAvailabilityService()
        return self._product_availability

    def build_management(
        self,
        *,
        customer_id: str | int | None = None,
        telegram_business_snapshot: TelegramBusinessSnapshot | Mapping[str, Any] | None = None,
        conversation_operation: ConversationOperation | Mapping[str, Any] | None = None,
        sales_management: SalesManagement | Mapping[str, Any] | None = None,
        product_availability: ProductAvailability | Mapping[str, Any] | None = None,
        product_availabilities: Iterable[ProductAvailability | Mapping[str, Any]] | None = None,
        product_business_snapshot: Any | None = None,
        product_business_snapshots: Iterable[Any] | None = None,
        customer_snapshot: Any | None = None,
        commerce_execution_result: Any | None = None,
        publishing_status: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
        **telegram_business_context: Any,
    ) -> DeliveryManagement:
        """Return the canonical read-only delivery state for one customer."""

        snapshot = telegram_business_snapshot or self.telegram_business.build_snapshot(
            customer_id=customer_id,
            customer_snapshot=customer_snapshot,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
            publishing_status=publishing_status,
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
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        availabilities = self._availability_items(
            product_availability=product_availability,
            product_availabilities=product_availabilities,
            snapshot=snapshot,
            product_business_snapshot=product_business_snapshot,
            product_business_snapshots=product_business_snapshots,
        )
        evidence = self._evidence(
            snapshot=snapshot,
            operation=operation,
            sales=sales,
            availabilities=availabilities,
            customer_snapshot=customer_snapshot,
            commerce_execution_result=commerce_execution_result,
        )
        recommendation = self._recommend(evidence)
        return DeliveryManagement(
            customer_id=(
                self._safe_text(customer_id)
                or self._safe_text(self._read(snapshot, "customer_id"))
                or self._safe_text(self._read(snapshot, "customer_identity", "customer_id"))
                or self._safe_text(
                    self._read(snapshot, "customer_identity", "canonical_customer_id")
                )
            ),
            provider=self._safe_text(self._read(snapshot, "provider")) or "telegram",
            business_health=self._safe_text(self._read(snapshot, "business_health"))
            or "UNKNOWN",
            operation_status=self._safe_text(self._read(operation, "status")),
            current_product_ids=self._text_tuple(
                self._read(snapshot, "summary", "current_product_ids")
                or self._read(snapshot, "current_product_ids")
            ),
            active_offer_ids=self._text_tuple(
                self._read(snapshot, "summary", "active_offer_ids")
                or evidence.get("active_offer_ids")
            ),
            delivery_history=dict(self._read(snapshot, "delivery_history") or {}),
            recommendation=recommendation,
            recommendations=(recommendation,),
            compatibility=self._compatibility(
                snapshot=snapshot,
                operation=operation,
                sales=sales,
                product_availability=product_availability,
                product_availabilities=product_availabilities,
                commerce_execution_result=commerce_execution_result,
            ),
            metadata={
                "source": "delivery_management",
                "owner": "DeliveryManagementService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_recommendation(self, **context: Any) -> DeliveryRecommendation:
        return self.build_management(**context).recommendation

    def _availability_items(
        self,
        *,
        product_availability: ProductAvailability | Mapping[str, Any] | None,
        product_availabilities: Iterable[ProductAvailability | Mapping[str, Any]] | None,
        snapshot: Any,
        product_business_snapshot: Any | None,
        product_business_snapshots: Iterable[Any] | None,
    ) -> tuple[Any, ...]:
        items: list[Any] = []
        if product_availability is not None:
            items.append(product_availability)
        if product_availabilities is not None:
            items.extend(item for item in product_availabilities if item is not None)
        if items:
            return tuple(items)
        product_snapshots = []
        if product_business_snapshot is not None:
            product_snapshots.append(product_business_snapshot)
        if product_business_snapshots is not None:
            product_snapshots.extend(
                item for item in product_business_snapshots if item is not None
            )
        product_snapshots.extend(tuple(self._read(snapshot, "products") or ()))
        return tuple(
            self.product_availability.build_availability(
                product_business_snapshot=product
            )
            for product in product_snapshots
        )

    def _evidence(
        self,
        *,
        snapshot: Any,
        operation: Any,
        sales: Any,
        availabilities: tuple[Any, ...],
        customer_snapshot: Any | None,
        commerce_execution_result: Any | None,
    ) -> dict[str, Any]:
        active_offers = tuple(self._read(snapshot, "active_offers") or ())
        products = tuple(self._read(snapshot, "products") or ())
        delivery_history = self._read(snapshot, "delivery_history") or {}
        telegram_commerce = self._read(snapshot, "telegram_commerce") or {}
        sales_recommendation = self._read(sales, "recommendation")
        product = self._primary_product(products, availabilities, sales_recommendation)
        availability = self._availability_for_product(
            availabilities,
            self._safe_text(self._read(product, "product_id"))
            or self._safe_text(self._read(sales_recommendation, "product_reference")),
        )
        delivery_method = (
            self._safe_text(self._read(telegram_commerce, "delivery_method"))
            or self._first_text(self._read(operation, "pending_delivery_methods"))
            or self._safe_text(self._read(sales_recommendation, "delivery_method"))
        )
        product_reference = (
            self._safe_text(self._read(sales_recommendation, "product_reference"))
            or self._safe_text(self._read(product, "product_id"))
            or self._first_text(self._read(snapshot, "summary", "current_product_ids"))
        )
        delivered_refs = self._delivery_refs(delivery_history, customer_snapshot)
        duplicate_signals = self._text_tuple(
            self._read(delivery_history, "duplicate_prevention_signals")
            or self._read(self._read(customer_snapshot, "commerce_memory"), "duplicate_prevention_signals")
        )
        return {
            "customer_id": self._safe_text(
                self._read(snapshot, "customer_id")
                or self._read(snapshot, "customer_identity", "customer_id")
            ),
            "operation_status": self._safe_text(self._read(operation, "status")),
            "operation_next_action": self._safe_text(
                self._read(operation, "next_operational_action")
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
            "product": product,
            "product_reference": product_reference,
            "product_type": self._safe_text(self._read(product, "product_type")),
            "delivery_type": self._safe_text(self._read(product, "delivery_type")),
            "availability": availability,
            "availability_status": self._safe_text(self._read(availability, "status")),
            "available_for_customers": bool(
                self._read(availability, "available_for_customers")
            ),
            "telegram_ready": bool(self._read(availability, "telegram_ready")),
            "delivery_method": delivery_method,
            "active_offer_ids": self._text_tuple(
                self._read(snapshot, "summary", "active_offer_ids")
                or tuple(self._read(item, "offer_id") for item in active_offers)
            ),
            "offer_reference": self._safe_text(
                self._read(sales_recommendation, "offer_reference")
            )
            or self._first_text(
                tuple(self._read(item, "offer_id") for item in active_offers)
            ),
            "experience_reference": self._safe_text(
                self._read(sales_recommendation, "experience_reference")
                or self._read(snapshot, "summary", "current_experience_id")
            ),
            "delivery_count": self._int(self._read(delivery_history, "delivery_count")),
            "delivered_refs": delivered_refs,
            "duplicate_prevention_signals": duplicate_signals,
            "duplicate_delivery": self._duplicate_delivery(
                product_reference,
                delivered_refs,
                duplicate_signals,
            ),
            "commerce_execution_status": self._safe_text(
                self._read(commerce_execution_result, "status")
            ),
            "commerce_execution_executed": bool(
                self._read(commerce_execution_result, "executed")
            ),
            "business_learning": self._read(snapshot, "business_learning") or {},
        }

    def _recommend(self, evidence: Mapping[str, Any]) -> DeliveryRecommendation:
        if evidence.get("duplicate_delivery"):
            return self._make(
                DeliveryRecommendationType.PREVENT_DUPLICATE_DELIVERY,
                DeliveryPriority.CRITICAL,
                evidence,
                "Prevent Duplicate Delivery",
                confidence=0.95,
            )
        status = str(evidence.get("operation_status") or "").upper()
        if status in {
            ConversationOperationStatus.WAITING_FOR_CUSTOMER.value,
            ConversationOperationStatus.STALLED.value,
            ConversationOperationStatus.PAUSED.value,
        }:
            return self._make(
                DeliveryRecommendationType.WAIT,
                DeliveryPriority.NORMAL,
                evidence,
                "Wait",
                confidence=self._confidence(evidence, fallback=0.62),
            )
        availability_status = str(evidence.get("availability_status") or "").upper()
        if availability_status and availability_status != ProductAvailabilityStatus.AVAILABLE.value:
            return self._make(
                DeliveryRecommendationType.WAIT,
                DeliveryPriority.NORMAL,
                evidence,
                self._availability_wait_action(availability_status),
                confidence=self._confidence(evidence, fallback=0.6),
            )
        if evidence.get("delivery_method") == "paid_media_link":
            return self._make(
                DeliveryRecommendationType.SEND_MEDIA_LINK,
                DeliveryPriority.HIGH,
                evidence,
                "Send Media Link",
                confidence=self._confidence(evidence, fallback=0.78),
            )
        recommendation_type = self._type_from_product(evidence)
        if recommendation_type is not None:
            return self._make(
                recommendation_type,
                self._priority(recommendation_type),
                evidence,
                self._label(recommendation_type),
                confidence=self._confidence(evidence, fallback=0.72),
            )
        if status == ConversationOperationStatus.DELIVERY_PENDING.value:
            return self._make(
                DeliveryRecommendationType.DELIVER_PREMIUM_PRODUCT,
                DeliveryPriority.HIGH,
                evidence,
                "Deliver Premium Product",
                confidence=self._confidence(evidence, fallback=0.68),
            )
        return self._make(
            DeliveryRecommendationType.NO_DELIVERY,
            DeliveryPriority.LOW,
            evidence,
            "No Delivery",
            confidence=0.35,
        )

    def _make(
        self,
        recommendation_type: DeliveryRecommendationType,
        priority: DeliveryPriority,
        evidence: Mapping[str, Any],
        action: str,
        *,
        confidence: float,
    ) -> DeliveryRecommendation:
        return DeliveryRecommendation(
            recommendation_type=recommendation_type,
            priority=priority,
            confidence=round(max(0.0, min(1.0, confidence)), 2),
            recommended_next_action=action,
            supporting_evidence={
                "source": "DeliveryManagementService",
                "telegram_business": {
                    "delivery_count": evidence.get("delivery_count"),
                    "business_learning": evidence.get("business_learning"),
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
                "product_availability": {
                    "status": evidence.get("availability_status"),
                    "available_for_customers": evidence.get("available_for_customers"),
                    "telegram_ready": evidence.get("telegram_ready"),
                },
                "customer_intelligence": {
                    "duplicate_prevention_signals": self._text_tuple(
                        evidence.get("duplicate_prevention_signals")
                    ),
                    "delivered_refs": self._text_tuple(evidence.get("delivered_refs")),
                },
                "commerce_execution": {
                    "status": evidence.get("commerce_execution_status"),
                    "executed": evidence.get("commerce_execution_executed"),
                    "owner_preserved": True,
                },
            },
            product_reference=self._safe_text(evidence.get("product_reference")),
            offer_reference=self._safe_text(evidence.get("offer_reference")),
            experience_reference=self._safe_text(evidence.get("experience_reference")),
            delivery_method=self._safe_text(evidence.get("delivery_method")),
            metadata={
                "recommendation_only": True,
                "orchestration_only": True,
                "read_only": True,
            },
        )

    @staticmethod
    def _compatibility(**sources: Any) -> dict[str, Any]:
        return {
            "source": "delivery_management",
            "owner": "DeliveryManagementService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "recommendation_only": True,
            "orchestration_only": True,
            "executes_telegram": False,
            "sends_media": False,
            "sends_media_links": False,
            "publishes_products": False,
            "modifies_products": False,
            "modifies_customer_intelligence": False,
            "records_business_learning": False,
            "telegram_runtime_owner": "Telegram runtime",
            "telegram_business_owner": "TelegramBusinessService",
            "conversation_operations_owner": "ConversationOperationsService",
            "sales_management_owner": "SalesManagementService",
            "product_availability_owner": "ProductAvailabilityService",
            "commerce_execution_owner": "CommerceExecutionService",
            "publishing_owner": "PublishingService",
            "customer_intelligence_owner": "CustomerIntelligenceCompatibilityAdapter",
            "sources_consumed": {key: value is not None for key, value in sources.items()},
        }

    @staticmethod
    def _type_from_product(evidence: Mapping[str, Any]) -> DeliveryRecommendationType | None:
        product_type = str(evidence.get("product_type") or "").lower()
        delivery_type = str(evidence.get("delivery_type") or "").upper()
        sales_type = str(evidence.get("sales_recommendation_type") or "")
        if "bundle" in product_type or sales_type.endswith("OFFER_BUNDLE"):
            return DeliveryRecommendationType.DELIVER_BUNDLE
        if "story" in product_type or sales_type.endswith("OFFER_STORY"):
            return DeliveryRecommendationType.DELIVER_STORY
        if delivery_type == "FREE" or sales_type.endswith("OFFER_FREE_PRODUCT"):
            return DeliveryRecommendationType.DELIVER_FREE_PRODUCT
        if delivery_type == "PAID" or sales_type.endswith("OFFER_PREMIUM_PRODUCT"):
            return DeliveryRecommendationType.DELIVER_PREMIUM_PRODUCT
        return None

    @staticmethod
    def _priority(recommendation_type: DeliveryRecommendationType) -> DeliveryPriority:
        if recommendation_type in {
            DeliveryRecommendationType.SEND_MEDIA_LINK,
            DeliveryRecommendationType.DELIVER_PREMIUM_PRODUCT,
            DeliveryRecommendationType.DELIVER_BUNDLE,
            DeliveryRecommendationType.DELIVER_STORY,
        }:
            return DeliveryPriority.HIGH
        if recommendation_type == DeliveryRecommendationType.NO_DELIVERY:
            return DeliveryPriority.LOW
        if recommendation_type == DeliveryRecommendationType.PREVENT_DUPLICATE_DELIVERY:
            return DeliveryPriority.CRITICAL
        return DeliveryPriority.NORMAL

    @staticmethod
    def _label(recommendation_type: DeliveryRecommendationType) -> str:
        return {
            DeliveryRecommendationType.DELIVER_FREE_PRODUCT: "Deliver FREE Product",
            DeliveryRecommendationType.DELIVER_PREMIUM_PRODUCT: "Deliver Premium Product",
            DeliveryRecommendationType.DELIVER_BUNDLE: "Deliver Bundle",
            DeliveryRecommendationType.DELIVER_STORY: "Deliver Story",
            DeliveryRecommendationType.SEND_MEDIA_LINK: "Send Media Link",
            DeliveryRecommendationType.PREVENT_DUPLICATE_DELIVERY: "Prevent Duplicate Delivery",
            DeliveryRecommendationType.WAIT: "Wait",
            DeliveryRecommendationType.NO_DELIVERY: "No Delivery",
        }[recommendation_type]

    @staticmethod
    def _availability_wait_action(status: str) -> str:
        if status == ProductAvailabilityStatus.WAITING_FOR_MEDIA_LINK.value:
            return "Wait for Media Link"
        if status == ProductAvailabilityStatus.PUBLISHING.value:
            return "Wait for Publishing"
        if status == ProductAvailabilityStatus.NEEDS_ATTENTION.value:
            return "Resolve Delivery Readiness"
        return "Wait"

    @classmethod
    def _primary_product(
        cls,
        products: tuple[Any, ...],
        availabilities: tuple[Any, ...],
        sales_recommendation: Any,
    ) -> Any | None:
        target = cls._safe_text(cls._read(sales_recommendation, "product_reference"))
        for product in products:
            if target and cls._safe_text(cls._read(product, "product_id")) == target:
                return product
        if products:
            return products[0]
        for availability in availabilities:
            product = cls._read(availability, "product_business_snapshot")
            if product is not None:
                return product
        return None

    @classmethod
    def _availability_for_product(
        cls,
        availabilities: tuple[Any, ...],
        product_id: str | None,
    ) -> Any | None:
        if not availabilities:
            return None
        if product_id:
            for availability in availabilities:
                if cls._safe_text(cls._read(availability, "product_id")) == product_id:
                    return availability
        return availabilities[0]

    @classmethod
    def _delivery_refs(cls, delivery_history: Any, customer_snapshot: Any | None) -> tuple[str, ...]:
        memory = cls._read(customer_snapshot, "commerce_memory")
        return cls._merge_text_tuples(
            cls._read(delivery_history, "free_assets_delivered"),
            cls._read(delivery_history, "paid_deliveries"),
            cls._read(memory, "free_assets_delivered"),
            cls._read(memory, "paid_products_delivered"),
        )

    @classmethod
    def _duplicate_delivery(
        cls,
        product_reference: str | None,
        delivered_refs: tuple[str, ...],
        duplicate_signals: tuple[str, ...],
    ) -> bool:
        if not product_reference:
            return False
        normalized = product_reference.lower()
        if normalized in {item.lower() for item in delivered_refs}:
            return True
        signal_values = {item.lower() for item in duplicate_signals}
        return (
            f"product:{normalized}" in signal_values
            or f"delivery:{normalized}" in signal_values
            or f"offer:{normalized}" in signal_values
        )

    @classmethod
    def _confidence(cls, evidence: Mapping[str, Any], *, fallback: float) -> float:
        sales_confidence = cls._float(evidence.get("sales_confidence"))
        if sales_confidence:
            return max(fallback, sales_confidence)
        if evidence.get("available_for_customers") or evidence.get("telegram_ready"):
            return max(fallback, 0.7)
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

    @classmethod
    def _first_text(cls, value: Any) -> str | None:
        values = cls._text_tuple(value)
        return values[0] if values else None

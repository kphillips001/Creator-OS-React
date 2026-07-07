"""Conversation Operations read-model aggregation service."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, TYPE_CHECKING

from app.models.conversation_operations import (
    ConversationOperation,
    ConversationOperationStatus,
    ConversationOperationSummary,
)
from app.models.telegram_business import TelegramBusinessSnapshot

if TYPE_CHECKING:
    from app.services.customer_intelligence_service import CustomerIntelligenceService
    from app.services.telegram_business_service import TelegramBusinessService
    from app.services.telegram_commerce_service import TelegramCommerceService


class ConversationOperationsService:
    """Build read-only operational state for Telegram conversations."""

    def __init__(
        self,
        *,
        telegram_business_service: "TelegramBusinessService | None" = None,
        telegram_commerce_service: "TelegramCommerceService | None" = None,
        customer_intelligence_service: "CustomerIntelligenceService | None" = None,
        experience_service: Any | None = None,
        commerce_execution_service: Any | None = None,
    ) -> None:
        self._telegram_business = telegram_business_service
        self._telegram_commerce = telegram_commerce_service
        self._customer_intelligence = customer_intelligence_service
        self._experience = experience_service
        self._commerce_execution = commerce_execution_service

    @property
    def telegram_business(self) -> "TelegramBusinessService":
        if self._telegram_business is None:
            from app.services.telegram_business_service import TelegramBusinessService

            self._telegram_business = TelegramBusinessService(
                telegram_commerce_service=self._telegram_commerce,
                customer_intelligence_service=self._customer_intelligence,
                experience_service=self._experience,
            )
        return self._telegram_business

    def build_operation(
        self,
        *,
        telegram_business_snapshot: TelegramBusinessSnapshot | Mapping[str, Any] | None = None,
        telegram_commerce_result: Any | None = None,
        telegram_commerce_state: Any | None = None,
        customer_snapshot: Any | None = None,
        conversation_state: Any | None = None,
        experience_progression: Any | None = None,
        customer_id: str | int | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
        metadata: Mapping[str, Any] | None = None,
        **telegram_business_context: Any,
    ) -> ConversationOperation:
        """Return a canonical read-only operation for one conversation."""

        snapshot = telegram_business_snapshot or self.telegram_business.build_snapshot(
            customer_id=customer_id,
            provider_customer_id=provider_customer_id,
            provider_account_id=provider_account_id,
            customer_snapshot=customer_snapshot,
            telegram_commerce_result=telegram_commerce_result,
            telegram_commerce_state=telegram_commerce_state,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
            metadata=metadata,
            **telegram_business_context,
        )
        evidence = self._evidence(
            snapshot=snapshot,
            telegram_commerce_result=telegram_commerce_result,
            telegram_commerce_state=telegram_commerce_state,
            conversation_state=conversation_state,
            experience_progression=experience_progression,
        )
        status = self._status(evidence)
        next_action = self._next_action(status, evidence)
        resolved_customer_id = (
            self._safe_text(customer_id)
            or self._safe_text(self._read(snapshot, "customer_id"))
            or self._safe_text(
                self._read(snapshot, "customer_identity", "customer_id")
            )
            or self._safe_text(
                self._read(snapshot, "customer_identity", "canonical_customer_id")
            )
        )
        return ConversationOperation(
            operation_id=self._operation_id(snapshot, resolved_customer_id),
            customer_id=resolved_customer_id,
            provider=self._safe_text(self._read(snapshot, "provider")) or "telegram",
            status=status,
            relationship_stage=self._safe_text(
                self._read(snapshot, "relationship", "stage")
                or self._read(snapshot, "relationship_stage")
            ),
            conversation_state=self._safe_text(
                evidence.get("conversation_state")
            ),
            commerce_state=self._safe_text(evidence.get("commerce_state")),
            current_experience_id=self._safe_text(
                evidence.get("current_experience_id")
            ),
            experience_state=self._safe_text(evidence.get("experience_state")),
            progress_percentage=self._int(evidence.get("progress_percentage")),
            current_product_ids=self._text_tuple(
                self._read(snapshot, "current_product_ids")
                or self._read(snapshot, "summary", "current_product_ids")
            ),
            pending_offer_ids=self._pending_offer_ids(snapshot, evidence),
            pending_delivery_methods=self._pending_delivery_methods(evidence),
            delivery_count=self._int(
                self._read(snapshot, "delivery_history", "delivery_count")
            ),
            next_operational_action=next_action,
            business_health=self._safe_text(
                self._read(snapshot, "business_health")
            )
            or "UNKNOWN",
            evidence=evidence,
            compatibility=self._compatibility(snapshot),
            metadata={
                "source": "conversation_operations",
                "owner": "ConversationOperationsService",
                "provider_neutral": True,
                "read_only": True,
                **dict(metadata or {}),
            },
        )

    def build_summary(
        self,
        operations: Iterable[ConversationOperation | Mapping[str, Any]] | None = None,
        *,
        telegram_business_snapshots: Iterable[
            TelegramBusinessSnapshot | Mapping[str, Any]
        ]
        | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> ConversationOperationSummary:
        items = tuple(
            item
            if isinstance(item, ConversationOperation)
            else self.build_operation(telegram_business_snapshot=item)
            for item in tuple(operations or ())
        )
        if telegram_business_snapshots is not None:
            items = items + tuple(
                self.build_operation(telegram_business_snapshot=snapshot)
                for snapshot in telegram_business_snapshots
            )
        status_counts = self._status_counts(items)
        return ConversationOperationSummary(
            total_operations=len(items),
            active_count=sum(1 for item in items if item.is_active),
            paused_count=status_counts.get(ConversationOperationStatus.PAUSED.value, 0),
            waiting_for_customer_count=status_counts.get(
                ConversationOperationStatus.WAITING_FOR_CUSTOMER.value,
                0,
            ),
            waiting_for_creator_os_count=status_counts.get(
                ConversationOperationStatus.WAITING_FOR_CREATOR_OS.value,
                0,
            ),
            stalled_count=status_counts.get(ConversationOperationStatus.STALLED.value, 0),
            offer_pending_count=status_counts.get(
                ConversationOperationStatus.OFFER_PENDING.value,
                0,
            ),
            delivery_pending_count=status_counts.get(
                ConversationOperationStatus.DELIVERY_PENDING.value,
                0,
            ),
            experience_active_count=status_counts.get(
                ConversationOperationStatus.EXPERIENCE_ACTIVE.value,
                0,
            ),
            completed_count=status_counts.get(
                ConversationOperationStatus.COMPLETED.value,
                0,
            ),
            next_actions=self._count_values(
                item.next_operational_action for item in items
            ),
            operations=items,
            compatibility={
                "source": "conversation_operations",
                "owner": "ConversationOperationsService",
                "read_only": True,
                "provider_neutral": True,
                "aggregation_only": True,
                "executes_telegram": False,
                "generates_responses": False,
                "modifies_customer_intelligence": False,
                "modifies_telegram_commerce": False,
                "modifies_experiences": False,
                "publishes_products": False,
            },
            metadata={
                "source": "conversation_operations",
                "owner": "ConversationOperationsService",
                **dict(metadata or {}),
            },
        )

    def _evidence(
        self,
        *,
        snapshot: Any,
        telegram_commerce_result: Any | None,
        telegram_commerce_state: Any | None,
        conversation_state: Any | None,
        experience_progression: Any | None,
    ) -> dict[str, Any]:
        conversation = self._read(snapshot, "conversation") or {}
        experience = self._read(snapshot, "experience") or {}
        telegram_commerce = self._read(snapshot, "telegram_commerce") or {}
        delivery_history = self._read(snapshot, "delivery_history") or {}
        summary = self._read(snapshot, "summary")
        active_offers = tuple(self._read(snapshot, "active_offers") or ())
        delivery_method = (
            self._read(telegram_commerce, "delivery_method")
            or self._read(
                self._read(telegram_commerce_result, "delivery_payload"),
                "delivery_method",
            )
            or self._read(
                self._read(telegram_commerce_result, "delivery_decision"),
                "delivery_method",
            )
        )
        operation_status = self._safe_text(
            self._read(snapshot, "operation_status")
            or self._read(summary, "operation_status")
        )
        progress_percentage = self._int(
            self._read(experience, "progress_percentage")
            or self._read(experience_progression, "progress_percentage")
        )
        return {
            "conversation_state": self._safe_text(
                self._read(conversation, "state")
                or self._read(conversation_state, "conversation_mode")
                or self._read(conversation_state, "conversation_state")
            ),
            "commerce_state": self._safe_text(
                self._read(conversation, "commerce_state")
                or self._read(conversation_state, "commerce_state")
            ),
            "current_experience_id": self._safe_text(
                self._read(experience, "current_experience_id")
                or self._read(experience_progression, "current_experience_id")
            ),
            "experience_state": self._safe_text(
                self._read(experience, "experience_state")
                or self._read(experience_progression, "experience_state")
            ),
            "progress_percentage": progress_percentage,
            "next_conversation_action": self._safe_text(
                self._read(conversation, "next_recommended_action")
            ),
            "next_experience_action": self._safe_text(
                self._read(experience, "next_recommended_experience_action")
            ),
            "business_next_action": self._safe_text(
                self._read(snapshot, "next_recommended_business_action")
                or self._read(summary, "next_recommended_action")
            ),
            "active_offer_count": len(
                tuple(item for item in active_offers if self._read(item, "active") is not False)
            ),
            "active_offer_ids": tuple(
                self._safe_text(self._read(item, "offer_id"))
                for item in active_offers
                if self._safe_text(self._read(item, "offer_id"))
            ),
            "delivery_method": self._safe_text(delivery_method),
            "delivery_count": self._int(self._read(delivery_history, "delivery_count")),
            "operation_status": operation_status,
            "telegram_blocked": bool(self._read(telegram_commerce, "blocked")),
            "execution_status": self._safe_text(
                self._read(telegram_commerce, "execution_status")
            ),
            "stalled": bool(
                self._read(snapshot, "metadata", "stalled")
                or self._read(conversation, "stalled")
            ),
            "waiting_for_customer": bool(
                self._read(snapshot, "metadata", "waiting_for_customer")
                or self._read(conversation, "waiting_for_customer")
            ),
            "waiting_for_creator_os": bool(
                self._read(snapshot, "metadata", "waiting_for_creator_os")
                or self._read(conversation, "waiting_for_creator_os")
            ),
            "source": "ConversationOperationsService",
        }

    @staticmethod
    def _status(evidence: Mapping[str, Any]) -> ConversationOperationStatus:
        operation_status = str(evidence.get("operation_status") or "").upper()
        commerce_state = str(evidence.get("commerce_state") or "").lower()
        conversation_state = str(evidence.get("conversation_state") or "").lower()
        experience_state = str(evidence.get("experience_state") or "").lower()
        next_action = str(evidence.get("business_next_action") or "").lower()
        delivery_method = str(evidence.get("delivery_method") or "").lower()

        if (
            operation_status == "COMPLETED"
            or commerce_state in {"completed", "complete"}
            or evidence.get("progress_percentage") == 100
        ):
            return ConversationOperationStatus.COMPLETED
        if evidence.get("stalled") or operation_status == "STALLED":
            return ConversationOperationStatus.STALLED
        if experience_state == "paused" or conversation_state == "paused":
            return ConversationOperationStatus.PAUSED
        if delivery_method in {"free_asset", "paid_media_link"} and operation_status in {
            "DEFERRED",
            "READY",
            "OBSERVED",
            "IDLE",
            "",
        }:
            return ConversationOperationStatus.DELIVERY_PENDING
        if evidence.get("active_offer_count", 0) > 0 or "offer" in next_action:
            return ConversationOperationStatus.OFFER_PENDING
        if evidence.get("waiting_for_creator_os") or evidence.get("telegram_blocked"):
            return ConversationOperationStatus.WAITING_FOR_CREATOR_OS
        if evidence.get("waiting_for_customer") or "wait" in next_action:
            return ConversationOperationStatus.WAITING_FOR_CUSTOMER
        if evidence.get("current_experience_id") and experience_state in {
            "active",
            "",
        }:
            return ConversationOperationStatus.EXPERIENCE_ACTIVE
        return ConversationOperationStatus.ACTIVE

    @staticmethod
    def _next_action(
        status: ConversationOperationStatus,
        evidence: Mapping[str, Any],
    ) -> str:
        if status == ConversationOperationStatus.COMPLETED:
            return "No Action Required"
        if status == ConversationOperationStatus.STALLED:
            return "Follow Up"
        if status == ConversationOperationStatus.PAUSED:
            return "Resume Experience"
        if status == ConversationOperationStatus.DELIVERY_PENDING:
            return "Deliver Product"
        if status == ConversationOperationStatus.OFFER_PENDING:
            return "Follow Up"
        if status == ConversationOperationStatus.WAITING_FOR_CREATOR_OS:
            action = evidence.get("business_next_action")
            return str(action or "Continue Conversation")
        if status == ConversationOperationStatus.WAITING_FOR_CUSTOMER:
            return "Wait"
        if status == ConversationOperationStatus.EXPERIENCE_ACTIVE:
            action = evidence.get("next_experience_action")
            if action:
                return str(action)
            return "Continue Conversation"
        return "Continue Conversation"

    @classmethod
    def _pending_offer_ids(
        cls,
        snapshot: Any,
        evidence: Mapping[str, Any],
    ) -> tuple[str, ...]:
        if cls._status(evidence) not in {
            ConversationOperationStatus.OFFER_PENDING,
            ConversationOperationStatus.DELIVERY_PENDING,
        }:
            return ()
        return cls._text_tuple(
            evidence.get("active_offer_ids")
            or cls._read(snapshot, "summary", "active_offer_ids")
        )

    @classmethod
    def _pending_delivery_methods(
        cls,
        evidence: Mapping[str, Any],
    ) -> tuple[str, ...]:
        status = cls._status(evidence)
        if status != ConversationOperationStatus.DELIVERY_PENDING:
            return ()
        method = cls._safe_text(evidence.get("delivery_method"))
        return (method,) if method else ()

    @staticmethod
    def _operation_id(snapshot: Any, customer_id: str | None) -> str | None:
        explicit = ConversationOperationsService._read(snapshot, "operation_id")
        if explicit:
            return str(explicit)
        if customer_id:
            return f"telegram_conversation:{customer_id}"
        return None

    @staticmethod
    def _compatibility(snapshot: Any) -> dict[str, Any]:
        return {
            "source": "conversation_operations",
            "owner": "ConversationOperationsService",
            "read_only": True,
            "provider_neutral": True,
            "aggregation_only": True,
            "executes_telegram": False,
            "generates_responses": False,
            "modifies_customer_intelligence": False,
            "modifies_telegram_commerce": False,
            "modifies_experiences": False,
            "publishes_products": False,
            "telegram_business_consumed": snapshot is not None,
            "telegram_runtime_owner": "Telegram runtime",
            "telegram_commerce_owner": "TelegramCommerceService",
            "customer_intelligence_owner": "CustomerIntelligenceService",
        }

    @staticmethod
    def _status_counts(
        operations: tuple[ConversationOperation, ...],
    ) -> dict[str, int]:
        return ConversationOperationsService._count_values(
            item.status.value for item in operations
        )

    @staticmethod
    def _count_values(values: Iterable[Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            text = str(getattr(value, "value", value) or "")
            if not text:
                continue
            counts[text] = counts.get(text, 0) + 1
        return counts

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

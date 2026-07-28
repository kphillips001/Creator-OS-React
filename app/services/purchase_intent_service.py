"""Purchase Intent orchestration without matching, ownership, or recommendations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID
import logging

from app.models.purchase_intent import (
    PurchaseIntent,
    PurchaseIntentStatus,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.commercial_asset_eligibility_service import CommercialAssetEligibilityService

logger = logging.getLogger("commerce-learning")

class PurchaseIntentService:
    def __init__(
        self, repository: PurchaseIntentRepository | None = None,
        learning_service=None, commercial_eligibility=None,
        clock=lambda: datetime.now(timezone.utc),
    ) -> None:
        self.repository = repository or PurchaseIntentRepository()
        self.commercial_eligibility = (
            commercial_eligibility or CommercialAssetEligibilityService()
        )
        self.clock = clock
        if learning_service is None:
            from app.services.commerce_learning_service import CommerceLearningService
            learning_service = CommerceLearningService()
        self.learning = learning_service

    def create_before_presentation(self, **values: Any) -> PurchaseIntent:
        self._validate_create(values)
        self.commercial_eligibility.require_offering_id(
            values["commercial_offering_id"],
            creator_profile_id=values["creator_profile_id"],
        )
        active = self.repository.get_active_for_buyer(
            creator_profile_id=values["creator_profile_id"],
            fanvue_account_id=values["fanvue_account_id"],
            telegram_user_id=values["telegram_user_id"],
        )
        if active is not None:
            raise ValueError(
                "An active Purchase Intent already exists; use "
                "replace_active_intent()."
            )
        return self.repository.create(**values)

    def replace_active_intent(self, **values: Any) -> PurchaseIntent:
        self._validate_create(values)
        self.commercial_eligibility.require_offering_id(
            values["commercial_offering_id"],
            creator_profile_id=values["creator_profile_id"],
        )
        return self.repository.replace_active(**values)

    def confirm_presented(
        self, intent_id: UUID, *, telegram_message_id: int | None = None,
        presented_at: datetime | None = None,
    ) -> PurchaseIntent:
        if telegram_message_id is not None and telegram_message_id <= 0:
            raise ValueError("telegram_message_id must be positive.")
        intent = self._require(intent_id)
        self._require_transition(intent.status, PurchaseIntentStatus.PRESENTED)
        result = self.repository.mark_presented(
            intent_id, at=presented_at or self.clock(),
            telegram_message_id=telegram_message_id,
        )
        self.observe(result, "PRESENTED")
        return result

    def mark_abandoned(
        self, intent_id: UUID, *, abandoned_at: datetime | None = None,
    ) -> PurchaseIntent:
        intent = self._require(intent_id)
        self._require_transition(intent.status, PurchaseIntentStatus.ABANDONED)
        result = self.repository.mark_abandoned(
            intent_id, at=abandoned_at or self.clock(),
        )
        self.observe(result, "ABANDONED")
        return result

    def record_click(
        self, intent_id: UUID, *, clicked_at: datetime | None = None,
    ) -> PurchaseIntent:
        intent = self._require(intent_id)
        self._require_transition(intent.status, PurchaseIntentStatus.CLICKED)
        result = self.repository.mark_clicked(
            intent_id, at=clicked_at or self.clock(),
        )
        self.observe(result, "OPENED")
        return result

    def expire_due(self) -> list[PurchaseIntent]:
        results = self.repository.expire_due(now=self.clock())
        for result in results:
            self.observe(result, "EXPIRED")
        return results

    def observe(self, intent, outcome_type, *, source_event_key=None):
        try:
            return self.learning.observe_purchase_intent(
                intent, outcome_type,
                source_event_key=(
                    source_event_key
                    or f"purchase_intent:{intent.purchase_intent_id}:{outcome_type}"
                ),
            )
        except Exception as error:
            logger.warning(
                "event=commerce_learning_observation_failed outcome_type=%s "
                "error_type=%s",
                outcome_type, type(error).__name__,
            )
            return None

    def get_unacknowledged_purchase(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int,
    ) -> PurchaseIntent | None:
        return self.repository.get_unacknowledged_purchase(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )

    def acknowledge_purchase(self, intent_id: UUID) -> PurchaseIntent:
        return self.repository.mark_purchase_acknowledged(
            intent_id, at=self.clock()
        )

    def record_payment_reference(
        self, intent_id: UUID, *, transaction_order_id: str | None = None,
        payment_id: str | None = None, event_id: str | None = None,
    ) -> PurchaseIntent:
        if not any((transaction_order_id, payment_id, event_id)):
            raise ValueError("At least one provider payment reference is required.")
        intent = self._require(intent_id)
        requested = {
            "provider_transaction_order_id": transaction_order_id,
            "provider_payment_id": payment_id,
            "provider_event_id": event_id,
        }
        changes: dict[str, str] = {}
        for field, value in requested.items():
            current = getattr(intent, field)
            if value is None:
                continue
            normalized = value.strip()
            if not normalized:
                raise ValueError("Provider references cannot be blank.")
            if current is not None and current != normalized:
                raise ValueError(f"{field} is already associated with another value.")
            if current is None:
                changes[field] = normalized
        return self.repository.update(intent_id, **changes) if changes else intent

    def mark_unknown(self, intent_id: UUID, *, reason: str) -> PurchaseIntent:
        if not reason.strip():
            raise ValueError("An attribution reason is required.")
        intent = self._require(intent_id)
        if intent.status is PurchaseIntentStatus.PURCHASED:
            raise ValueError("A purchased Purchase Intent cannot become UNKNOWN.")
        return self.repository.mark_unknown(intent_id, reason=reason.strip())

    def _require(self, intent_id: UUID) -> PurchaseIntent:
        intent = self.repository.get(intent_id)
        if intent is None:
            raise LookupError("Purchase Intent was not found.")
        return intent

    @staticmethod
    def _require_transition(
        current: PurchaseIntentStatus, target: PurchaseIntentStatus,
    ) -> None:
        allowed = {
            PurchaseIntentStatus.CREATED: {
                PurchaseIntentStatus.PRESENTED,
                PurchaseIntentStatus.EXPIRED,
                PurchaseIntentStatus.ABANDONED,
                PurchaseIntentStatus.UNKNOWN,
                PurchaseIntentStatus.SUPERSEDED,
            },
            PurchaseIntentStatus.PRESENTED: {
                PurchaseIntentStatus.CLICKED,
                PurchaseIntentStatus.PURCHASED,
                PurchaseIntentStatus.EXPIRED,
                PurchaseIntentStatus.ABANDONED,
                PurchaseIntentStatus.UNKNOWN,
                PurchaseIntentStatus.SUPERSEDED,
            },
            PurchaseIntentStatus.CLICKED: {
                PurchaseIntentStatus.PURCHASED,
                PurchaseIntentStatus.EXPIRED,
                PurchaseIntentStatus.ABANDONED,
                PurchaseIntentStatus.UNKNOWN,
                PurchaseIntentStatus.SUPERSEDED,
            },
        }
        if target not in allowed.get(current, set()):
            raise ValueError(f"Invalid Purchase Intent transition: {current} -> {target}.")

    def _validate_create(self, values: dict[str, Any]) -> None:
        required_positive = (
            "creator_profile_id", "fanvue_account_id",
            "telegram_identity_mapping_id", "telegram_user_id",
        )
        if any(int(values.get(field, 0)) <= 0 for field in required_positive):
            raise ValueError("Creator, account, identity, and Telegram user are required.")
        if int(values.get("telegram_chat_id", 0)) == 0:
            raise ValueError("telegram_chat_id cannot be zero.")
        if int(values.get("expected_price_minor", -1)) < 0:
            raise ValueError("expected_price_minor cannot be negative.")
        currency = str(values.get("expected_currency", "")).upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValueError("expected_currency must be a three-letter code.")
        values["expected_currency"] = currency
        if values.get("provider") != "FANVUE":
            raise ValueError("Only the FANVUE provider is supported.")
        for field in ("provider_resource_id", "delivery_url"):
            if not str(values.get(field, "")).strip():
                raise ValueError(f"{field} is required.")
        expires_at = values.get("expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= self.clock():
            raise ValueError("expires_at must be in the future.")

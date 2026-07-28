"""Customer commerce intelligence without offering or recommendation logic."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.models.customer_commerce import (
    CustomerCommerceProfile,
    CustomerCommerceProfileState,
)
from app.repositories.customer_commerce_repository import (
    CustomerCommerceRepository,
)


@dataclass(frozen=True)
class VerifiedPurchaseResult:
    profile: CustomerCommerceProfile
    transaction_recorded: bool


class CustomerCommerceService:
    def __init__(self, repository=None) -> None:
        self.repository = repository or CustomerCommerceRepository()

    def record_verified_purchase(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID | str, gross_minor: int,
        net_minor: int, transaction_order_id: str, payment_status: str,
        purchase_source: str, payment_timestamp: datetime,
        display_name: str | None = None, handle: str | None = None,
    ) -> VerifiedPurchaseResult:
        buyer_uuid = self._uuid(external_fanvue_user_uuid)
        timestamp = self._datetime(payment_timestamp)
        gross = self._minor("gross_minor", gross_minor)
        net = self._minor("net_minor", net_minor)
        transaction_id = self._text(
            "transaction_order_id", transaction_order_id
        )
        status = self._text("payment_status", payment_status)
        source = self._text("purchase_source", purchase_source)
        self._positive("creator_profile_id", creator_profile_id)
        self._positive("fanvue_account_id", fanvue_account_id)
        profile = self.repository.get_or_create(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=buyer_uuid,
            seen_at=timestamp,
            display_name=self._optional(display_name),
            handle=self._optional(handle),
        )
        profile, recorded = self.repository.record_purchase(
            profile_id=profile.customer_commerce_profile_id,
            fanvue_account_id=fanvue_account_id,
            transaction_order_id=transaction_id,
            gross_minor=gross,
            net_minor=net,
            payment_status=status,
            purchase_source=source,
            payment_timestamp=timestamp,
        )
        return VerifiedPurchaseResult(profile, recorded)

    def record_customer_seen(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID | str,
        seen_at: datetime | None = None, display_name: str | None = None,
        handle: str | None = None,
    ) -> CustomerCommerceProfile:
        self._positive("creator_profile_id", creator_profile_id)
        self._positive("fanvue_account_id", fanvue_account_id)
        return self.repository.get_or_create(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=self._uuid(
                external_fanvue_user_uuid
            ),
            seen_at=self._datetime(seen_at or datetime.now(timezone.utc)),
            display_name=self._optional(display_name),
            handle=self._optional(handle),
        )

    def update_identity(
        self, profile_id: UUID | str, *,
        creator_profile_id: int,
        telegram_identity_mapping_id: int | None,
        telegram_user_id: int | None,
    ) -> CustomerCommerceProfile:
        self._positive("creator_profile_id", creator_profile_id)
        profile = self.repository.get_by_id(
            self._uuid(profile_id),
            creator_profile_id=creator_profile_id,
        )
        if profile is None:
            raise LookupError("Customer commerce profile was not found.")
        if telegram_identity_mapping_id is not None:
            self._positive(
                "telegram_identity_mapping_id",
                telegram_identity_mapping_id,
            )
        if telegram_user_id is not None:
            self._positive("telegram_user_id", telegram_user_id)
        return self.repository.update_profile(
            profile.customer_commerce_profile_id,
            display_name=profile.display_name,
            handle=profile.handle,
            profile_state=profile.profile_state,
            telegram_identity_mapping_id=telegram_identity_mapping_id,
            telegram_user_id=telegram_user_id,
        )

    def refresh_statistics(
        self, profile_id: UUID | str,
    ) -> CustomerCommerceProfile:
        return self.repository.refresh_statistics(self._uuid(profile_id))

    def update_profile(
        self, profile_id: UUID | str, *, display_name: str | None,
        handle: str | None, profile_state: CustomerCommerceProfileState | str,
        creator_profile_id: int,
    ) -> CustomerCommerceProfile:
        self._positive("creator_profile_id", creator_profile_id)
        state = (
            profile_state
            if isinstance(profile_state, CustomerCommerceProfileState)
            else CustomerCommerceProfileState(str(profile_state).upper())
        )
        profile_uuid = self._uuid(profile_id)
        current = self.repository.get_by_id(
            profile_uuid, creator_profile_id=creator_profile_id
        )
        if current is None:
            raise LookupError("Customer commerce profile was not found.")
        return self.repository.update_profile(
            profile_uuid,
            display_name=self._optional(display_name),
            handle=self._optional(handle),
            profile_state=state,
            telegram_identity_mapping_id=current.telegram_identity_mapping_id,
            telegram_user_id=current.telegram_user_id,
        )

    @staticmethod
    def _uuid(value) -> UUID:
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError("A valid UUID is required.") from error

    @staticmethod
    def _datetime(value: datetime) -> datetime:
        if not isinstance(value, datetime):
            raise ValueError("payment timestamp must be a datetime.")
        if value.tzinfo is None:
            raise ValueError("payment timestamp must include a timezone.")
        return value

    @staticmethod
    def _minor(name: str, value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer.")
        return value

    @staticmethod
    def _positive(name: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive integer.")

    @staticmethod
    def _text(name: str, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{name} is required.")
        return normalized

    @staticmethod
    def _optional(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

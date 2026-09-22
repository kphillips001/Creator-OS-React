"""Cheap server-owned projection of a current customer-visible sales opportunity."""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.purchase_intent import PurchaseIntentStatus
from app.repositories.purchase_intent_repository import PurchaseIntentRepository


class ActiveSalesOpportunityService:
    QUALIFYING = frozenset({
        PurchaseIntentStatus.PRESENTED, PurchaseIntentStatus.CLICKED,
    })

    def __init__(self, *, intents=None, offerings=None, clock=lambda: datetime.now(timezone.utc)):
        self.intents = intents or PurchaseIntentRepository()
        if offerings is None:
            from app.repositories.commercial_offering_repository import CommercialOfferingRepository
            offerings = CommercialOfferingRepository()
        self.offerings = offerings
        self.clock = clock

    def project(self, **scope) -> dict:
        intent = self.intents.get_active_for_buyer(
            creator_profile_id=scope["creator_profile_id"],
            fanvue_account_id=scope["fanvue_account_id"],
            telegram_user_id=scope["telegram_user_id"],
        )
        active = bool(intent and self._qualifies(intent, scope))
        offering = self.offerings.get(intent.commercial_offering_id, creator_profile_id=intent.creator_profile_id) if active else None
        return {
            "active": active,
            "authority": "PERSISTED_PURCHASE_INTENT",
            "purchase_intent_id": str(intent.purchase_intent_id) if active else None,
            "offer_status": intent.status.value if active else None,
            "offering_id": str(intent.commercial_offering_id) if active else None,
            "offer_title": str(offering.title) if offering is not None else None,
            "configured_price_minor": (
                int(intent.configured_base_price_minor or intent.expected_price_minor)
                if active else None
            ),
            "currency": intent.expected_currency if active else None,
            "expires_at": intent.expires_at.isoformat() if active else None,
        }

    def _qualifies(self, intent, scope) -> bool:
        if intent.status not in self.QUALIFYING:
            return False
        expires = intent.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires <= self.clock().astimezone(timezone.utc):
            return False
        return bool(
            intent.creator_profile_id == scope["creator_profile_id"]
            and intent.fanvue_account_id == scope["fanvue_account_id"]
            and intent.telegram_user_id == scope["telegram_user_id"]
            and intent.telegram_chat_id == scope["telegram_chat_id"]
            and intent.purchased_at is None
            and intent.provider_transaction_order_id is None
            and intent.provider_payment_id is None
            and intent.provider_event_id is None
        )

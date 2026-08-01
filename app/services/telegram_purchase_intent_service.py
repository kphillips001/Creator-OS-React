"""Create and advance Purchase Intents around Telegram Media Link delivery."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5, NAMESPACE_URL

from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig


logger = logging.getLogger("commerce-signal")


class TelegramPurchaseIntentService:
    def __init__(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        identity_repository=None, purchase_intent_service=None,
        sales_session_service=None,
        clock=lambda: datetime.now(timezone.utc),
    ):
        self.creator_profile_id = creator_profile_id
        self.fanvue_account_id = fanvue_account_id
        self.identities = identity_repository or TelegramIdentityRepository()
        self.intents = purchase_intent_service or PurchaseIntentService()
        if sales_session_service is None:
            from app.services.sales_session_service import SalesSessionService
            sales_session_service = SalesSessionService()
        self.sales_sessions = sales_session_service
        self.clock = clock

    def create_before_delivery(self, result, payload):
        diagnostics = result.diagnostic_metadata or {}
        if not (
            diagnostics.get("final_offer_authorized") is True
            and diagnostics.get("customer_sales_brain_evaluated") is True
            and diagnostics.get("offering_selected")
            and diagnostics.get("delivery_url")
            and diagnostics.get("provider_resource_id")
            and diagnostics.get("publication_id")
        ):
            return None
        identity = self.identities.get_by_telegram_user_id(
            payload.telegram_user_id
        )
        if identity is None or identity.fanvue_account_id != self.fanvue_account_id:
            logger.info(
                "event=identity_resolved resolved=false telegram_user_id=%s",
                payload.telegram_user_id,
            )
            return None
        logger.info(
            "event=identity_resolved resolved=true telegram_user_id=%s",
            payload.telegram_user_id,
        )
        config = CustomerSalesBrainConfig.from_environment()
        ttl_minutes = max(1, int(
            config.offer_expiration.total_seconds() // 60
        ))
        now = self.clock()
        correlation = str(result.correlation_id)
        intent = self.intents.replace_active_intent(
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_identity_mapping_id=identity.id,
            telegram_user_id=identity.telegram_user_id,
            telegram_chat_id=identity.telegram_chat_id,
            external_fanvue_user_uuid=identity.external_fanvue_user_uuid,
            commercial_offering_id=UUID(str(diagnostics["offering_id"])),
            commercial_publication_id=UUID(str(diagnostics["publication_id"])),
            provider=str(diagnostics["provider"]),
            provider_resource_id=str(diagnostics["provider_resource_id"]),
            delivery_url=str(diagnostics["delivery_url"]),
            conversation_id=correlation,
            correlation_id=uuid5(NAMESPACE_URL, correlation),
            expected_price_minor=int(diagnostics["price_minor"]),
            expected_currency=str(diagnostics["currency"]),
            expires_at=now + timedelta(minutes=ttl_minutes),
            created_metadata={
                "source": "TELEGRAM_COMMERCE",
                "inbound_message_id": payload.message_id,
                "recommendation_trace": {
                    **dict(
                        diagnostics.get("recommendation_diagnostics") or {}
                    ),
                    "rankedCandidates": diagnostics.get(
                        "recommendation_trace", []
                    ),
                },
                "commercial_intelligence": dict(
                    diagnostics.get("commercial_intelligence") or {}
                ),
            },
        )
        intelligence = dict(
            diagnostics.get("commercial_intelligence") or {}
        )
        session_context = dict(
            intelligence.get("salesSessionContext") or {}
        )
        session_id = session_context.get("salesSessionId")
        if intelligence.get("strategy") == "SESSION_SELLING" and session_id:
            try:
                self.sales_sessions.associate_purchase_intent(
                    session_id=session_id,
                    creator_profile_id=self.creator_profile_id,
                    purchase_intent_id=intent.purchase_intent_id,
                    actor_type="SYSTEM",
                    actor_identifier="TelegramPurchaseIntentService",
                    reason="Authorized Session Selling presentation.",
                )
            except Exception as error:
                logger.warning(
                    "event=sales_session_purchase_intent_association_failed "
                    "purchase_intent_id=%s error_type=%s",
                    intent.purchase_intent_id, type(error).__name__,
                )
        return intent

    def confirm_delivery(self, intent, *, telegram_message_id=None):
        if intent is None:
            return None
        return self.intents.confirm_presented(
            intent.purchase_intent_id,
            telegram_message_id=telegram_message_id,
        )

    def abandon_delivery(self, intent):
        if intent is None:
            return None
        return self.intents.mark_abandoned(intent.purchase_intent_id)

    def get_unacknowledged_purchase(self, **lookup):
        return self.intents.get_unacknowledged_purchase(**lookup)

    def acknowledge_purchase(self, intent_id):
        return self.intents.acknowledge_purchase(UUID(str(intent_id)))

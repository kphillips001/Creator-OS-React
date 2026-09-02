"""Fail-closed first-purchase mapping from one confirmed price reservation."""
from __future__ import annotations

from uuid import UUID

from app.repositories.private_chat_fingerprint_repository import PrivateChatFingerprintRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.repositories.user_repository import get_user_by_account_and_fanvue_uuid
from app.database import get_db_connection


class FingerprintPurchaseAttributionService:
    PROVENANCE = "PRIVATE_CHAT_FINGERPRINT_PURCHASE"
    SUPPORTED_SOURCES = frozenset({"medialink", "media_link", "media"})

    def __init__(self, *, repository=None, intents=None, identities=None,
                 fanvue_user_resolver=get_user_by_account_and_fanvue_uuid,
                 provisional_session_service=None,
                 prospect_service=None, settlement_service=None,
                 connection_factory=get_db_connection):
        self.repository = repository or PrivateChatFingerprintRepository()
        self.intents = intents or PurchaseIntentRepository()
        self.identities = identities or TelegramIdentityRepository()
        self.fanvue_user_resolver = fanvue_user_resolver
        self.provisional_sessions = provisional_session_service
        self.prospects = prospect_service
        self.settlement = settlement_service
        self.connection_factory = connection_factory

    def attribute(
        self, *, fanvue_account_id: int, currency: str, gross_minor: int,
        source: str, buyer_uuid: UUID, transaction_id: str,
        payment_id: str, event_id: str, purchased_at,
    ):
        if str(source).lower() not in self.SUPPORTED_SOURCES:
            return None
        if self.settlement is None:
            from app.services.private_chat_purchase_settlement_service import PrivateChatPurchaseSettlementService
            self.settlement = PrivateChatPurchaseSettlementService()
        user = self.fanvue_user_resolver(fanvue_account_id, str(buyer_uuid))
        if user is None:
            with self.connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute("""INSERT INTO fanvue_users(
                        fanvue_account_id,fanvue_user_uuid,username,display_name)
                        VALUES (%s,%s,NULL,NULL)
                        ON CONFLICT(fanvue_account_id,fanvue_user_uuid)
                        DO UPDATE SET fanvue_user_uuid=EXCLUDED.fanvue_user_uuid
                        RETURNING *""", (fanvue_account_id, buyer_uuid))
                    user = dict(cursor.fetchone())
        if user is None:
            raise LookupError("Authenticated Fanvue purchaser is not locally synchronized.")
        return self.settlement.settle(
            fanvue_account_id=fanvue_account_id, currency=currency,
            gross_minor=gross_minor, source=source, buyer_uuid=buyer_uuid,
            local_fanvue_user_id=int(user["id"]), transaction_id=transaction_id,
            payment_id=payment_id, event_id=event_id, purchased_at=purchased_at,
        )

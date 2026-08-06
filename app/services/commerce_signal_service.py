"""Deterministic Fanvue payment convergence and bot-facing signal projection."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from app.repositories.commerce_signal_repository import CommerceSignalRepository
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.fanvue_account_repository import (
    get_account_by_creator_uuid,
    get_account_by_fanvue_user_uuid,
    get_account_by_id,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.customer_commerce_service import CustomerCommerceService
from app.services.fanvue_official_client import FanvueOfficialClient
from app.services.purchase_intent_service import PurchaseIntentService


logger = logging.getLogger("commerce-signal")


@dataclass(frozen=True)
class CommerceSignal:
    buyer_uuid: str
    telegram_user_id: int | None
    identity_resolved: bool
    lifetime_spend_minor: int
    purchase_count: int
    last_purchase_at: datetime | None
    current_active_offer_id: str | None
    current_offer_status: str | None
    conversion_state: str
    latest_transaction: str | None
    attribution_state: str
    reconciliation_state: str | None


class CommerceSignalService:
    SUPPORTED_EVENTS = frozenset({"purchase_new", "creator_payment_succeeded"})

    def __init__(
        self, *, repository=None, identity_repository=None,
        customer_service=None, purchase_intent_service=None,
        purchase_intent_repository=None, photoshoot_lifecycle_service=None,
        client_factory=FanvueOfficialClient,
    ):
        self.repository = repository or CommerceSignalRepository()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.customers = customer_service or CustomerCommerceService()
        self.intents = purchase_intent_service or PurchaseIntentService()
        self.intent_repository = (
            purchase_intent_repository or PurchaseIntentRepository()
        )
        if photoshoot_lifecycle_service is None:
            from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
            photoshoot_lifecycle_service = CustomerPhotoshootLifecycleService()
        self.photoshoot_lifecycles = photoshoot_lifecycle_service
        self.client_factory = client_factory

    def process_webhook(self, event: dict) -> dict:
        event_type = str(event.get("event_type") or "")
        if event_type not in self.SUPPORTED_EVENTS:
            raise ValueError(f"Unsupported Commerce Signal event: {event_type}")
        payload = event.get("payload") or {}
        fields = self._webhook_fields(event_type, payload, event)
        account = self._account(fields["creator_uuid"], event.get("fanvue_account_id"))
        account_id = int(account["id"])
        creator = get_active_creator_profile(str(account_id))
        if not creator:
            raise LookupError("Active creator profile was not found.")
        provider_event_id = str(
            event.get("external_event_id") or fields["provider_event_id"] or ""
        ).strip()
        if not provider_event_id:
            raise ValueError("Fanvue provider event ID is required.")
        logger.info(
            "event=webhook_received topic=%s provider_event_id=%s",
            event_type, provider_event_id,
        )
        reconciliation, created = self.repository.get_or_create_reconciliation(
            fanvue_account_id=account_id,
            creator_profile_id=int(creator["id"]),
            provider_event_id=provider_event_id,
            source_event_type=event_type,
            observed_transaction_id=fields["transaction_id"],
            external_fanvue_user_uuid=fields["buyer_uuid"],
            purchase_type=fields["purchase_type"],
            expected_amount_minor=fields["amount_minor"],
        )
        if not created and reconciliation["state"] == "VERIFIED":
            logger.info(
                "event=duplicate_ignored provider_event_id=%s", provider_event_id
            )
            return {"success": True, "duplicate": True, "state": "VERIFIED"}
        return self._reconcile(reconciliation, fields=fields)

    def retry_pending(self, *, limit: int = 25) -> list[dict]:
        return [self._reconcile(row) for row in self.repository.list_due(limit=limit)]

    def _reconcile(self, reconciliation: dict, *, fields: dict | None = None) -> dict:
        reconciliation_id = UUID(str(reconciliation["reconciliation_id"]))
        transaction_id = reconciliation["observed_transaction_id"]
        account_id = int(reconciliation["fanvue_account_id"])
        try:
            response = self.client_factory(account_id).get_earnings_by_transaction(
                transaction_id
            )
            records = response.get("data") if isinstance(response, dict) else None
            records = records if isinstance(records, list) else []
            matches = [
                item for item in records if isinstance(item, dict)
                and str(item.get("transactionOrderId") or "") == transaction_id
            ]
            if len(matches) != 1:
                raise LookupError(
                    f"Expected one earnings record; received {len(matches)}."
                )
            earning = matches[0]
            buyer_uuid = self._uuid(
                (fields or {}).get("buyer_uuid")
                or reconciliation.get("external_fanvue_user_uuid")
            )
            gross = self._money(earning, "gross", "amount")
            net = self._money(earning, "net", "earnings", default=gross)
            timestamp = self._timestamp(
                earning.get("date") or earning.get("timestamp")
            )
            source = str(earning.get("source") or "unknown")
            status = str(
                earning.get("status")
                or (fields or {}).get("payment_status")
                or "verified"
            )
            purchase_type = str(
                (fields or {}).get("purchase_type")
                or reconciliation.get("purchase_type")
                or ""
            )
            identity = self.identities.get_by_external_fanvue_user_uuid(
                account_id, buyer_uuid
            )
            logger.info(
                "event=identity_resolved resolved=%s buyer_uuid=%s",
                identity is not None, buyer_uuid,
            )
            customer = self.customers.record_verified_purchase(
                creator_profile_id=int(reconciliation["creator_profile_id"]),
                fanvue_account_id=account_id,
                external_fanvue_user_uuid=buyer_uuid,
                gross_minor=gross, net_minor=net,
                transaction_order_id=transaction_id,
                payment_status=status, purchase_source=source,
                payment_timestamp=timestamp,
                display_name=(fields or {}).get("display_name"),
                handle=(fields or {}).get("handle"),
            )
            if identity is not None:
                self.customers.update_identity(
                    customer.profile.customer_commerce_profile_id,
                    creator_profile_id=int(reconciliation["creator_profile_id"]),
                    telegram_identity_mapping_id=identity.id,
                    telegram_user_id=identity.telegram_user_id,
                )
            attribution = self._attribute(
                creator_profile_id=int(reconciliation["creator_profile_id"]),
                fanvue_account_id=account_id, buyer_uuid=buyer_uuid,
                amount_minor=gross, payment_timestamp=timestamp,
                transaction_id=transaction_id,
                payment_id=(
                    (fields or {}).get("payment_id")
                    or reconciliation["observed_transaction_id"]
                ),
                event_id=reconciliation["provider_event_id"],
                customer_commerce_profile_id=customer.profile.customer_commerce_profile_id,
                media_link_purchase=(
                    source.lower() in {"medialink", "media_link"}
                    or purchase_type.lower() in {"media", "medialink", "media_link"}
                ),
            )
            self.repository.mark_verified(
                reconciliation_id, transaction_order_id=transaction_id,
                external_fanvue_user_uuid=buyer_uuid, earnings_record=earning,
            )
            logger.info(
                "event=transaction_merged transaction_id=%s duplicate=%s",
                transaction_id, not customer.transaction_recorded,
            )
            logger.info(
                "event=customer_updated buyer_uuid=%s recorded=%s",
                buyer_uuid, customer.transaction_recorded,
            )
            logger.info(
                "event=earnings_reconciliation transaction_id=%s state=VERIFIED",
                transaction_id,
            )
            return {
                "success": True, "duplicate": not customer.transaction_recorded,
                "state": "VERIFIED", "transactionOrderId": transaction_id,
                "identityResolved": identity is not None,
                "attribution": attribution,
            }
        except Exception as error:
            self.repository.mark_pending(
                reconciliation_id,
                error=f"{type(error).__name__}: {error}",
            )
            logger.warning(
                "event=earnings_reconciliation transaction_id=%s state=PENDING "
                "error_type=%s",
                transaction_id, type(error).__name__,
            )
            return {
                "success": False, "state": "PENDING",
                "error": type(error).__name__,
            }

    def _attribute(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        buyer_uuid: UUID, amount_minor: int, payment_timestamp: datetime,
        transaction_id: str, payment_id: str, event_id: str,
        customer_commerce_profile_id: UUID,
        media_link_purchase: bool,
    ) -> dict:
        if not media_link_purchase:
            return {"state": "UNKNOWN", "reason": "NOT_MEDIA_LINK_PURCHASE"}
        candidates = self.intent_repository.list_candidates(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=buyer_uuid,
        )
        previously_attributed = [
            item for item in candidates
            if item.provider_transaction_order_id == transaction_id
            and item.status.value == "PURCHASED"
            and item.attribution_result.value == "ATTRIBUTED"
        ]
        if len(previously_attributed) == 1:
            lifecycle_result = self.photoshoot_lifecycles.synchronize_attributed_purchase(
                intent=previously_attributed[0],
                customer_commerce_profile_id=customer_commerce_profile_id,
            )
            return {
                "state": "ATTRIBUTED", "candidateCount": 1,
                "lifecycleSynchronized": lifecycle_result is not None,
            }
        survivors = [
            item for item in candidates
            if item.expected_price_minor == amount_minor
            and item.presented_at is not None
            and item.presented_at <= payment_timestamp <= item.expires_at
            and item.status.value in {"PRESENTED", "CLICKED"}
        ]
        logger.info(
            "event=purchase_intent_candidates buyer_uuid=%s count=%s",
            buyer_uuid, len(survivors),
        )
        if len(survivors) == 1:
            item = survivors[0]
            self.intents.record_payment_reference(
                item.purchase_intent_id,
                transaction_order_id=transaction_id,
                payment_id=payment_id, event_id=event_id,
            )
            purchased_intent = self.intent_repository.mark_purchased(
                item.purchase_intent_id, at=payment_timestamp,
                attribution_reason=(
                    "Exact buyer, account, creator, price, attribution window, "
                    "and single-candidate match."
                ),
            )
            lifecycle_result = self.photoshoot_lifecycles.synchronize_attributed_purchase(
                intent=purchased_intent,
                customer_commerce_profile_id=customer_commerce_profile_id,
            )
            observer = getattr(self.intents, "observe", None)
            if callable(observer):
                observer(
                    purchased_intent, "PURCHASED",
                    source_event_key=(
                        f"provider_transaction:{transaction_id}:PURCHASED"
                    ),
                )
            logger.info(
                "event=attributed purchase_intent_id=%s", item.purchase_intent_id
            )
            return {
                "state": "ATTRIBUTED", "candidateCount": 1,
                "lifecycleSynchronized": lifecycle_result is not None,
            }
        reason = (
            "NO_HARD_MATCHING_CANDIDATE"
            if not survivors else "MULTIPLE_HARD_MATCHING_CANDIDATES"
        )
        for item in survivors:
            self.intents.mark_unknown(item.purchase_intent_id, reason=reason)
        logger.info("event=unknown reason=%s count=%s", reason, len(survivors))
        return {"state": "UNKNOWN", "reason": reason,
                "candidateCount": len(survivors)}

    def get_signal(self, **lookup) -> CommerceSignal | None:
        row = self.repository.get_signal(**lookup)
        if row is None:
            return None
        status = row.get("current_offer_status")
        attribution = row.get("attribution_result") or "UNKNOWN"
        reconciliation = row.get("reconciliation_state")
        conversion = self._conversion(status, attribution, reconciliation)
        return CommerceSignal(
            buyer_uuid=str(row["external_fanvue_user_uuid"]),
            telegram_user_id=row.get("telegram_user_id"),
            identity_resolved=bool(row.get("identity_resolved")),
            lifetime_spend_minor=int(row.get("lifetime_gross_minor") or 0),
            purchase_count=int(row.get("purchase_count") or 0),
            last_purchase_at=row.get("last_purchase_at"),
            current_active_offer_id=(
                str(row["commercial_offering_id"])
                if row.get("commercial_offering_id") else None
            ),
            current_offer_status=status,
            conversion_state=conversion,
            latest_transaction=row.get("last_transaction_order_id"),
            attribution_state=attribution,
            reconciliation_state=reconciliation,
        )

    @staticmethod
    def _conversion(status, attribution, reconciliation):
        if status is None:
            return "NO_ACTIVE_OFFER"
        if attribution == "ATTRIBUTED" or status == "PURCHASED":
            return "PURCHASED"
        if status == "UNKNOWN" or attribution == "UNKNOWN":
            return "UNKNOWN"
        if status == "EXPIRED":
            return "EXPIRED"
        if reconciliation == "PENDING":
            return "PAYMENT_PENDING"
        if status in {"PRESENTED", "CLICKED"}:
            return "OFFER_PRESENTED"
        if status in {"ABANDONED", "SUPERSEDED"}:
            return "NOT_PURCHASED_YET"
        return "NO_ACTIVE_OFFER"

    @staticmethod
    def _account(creator_uuid, normalized_account):
        if creator_uuid:
            account = get_account_by_creator_uuid(str(creator_uuid))
            if not account:
                account = get_account_by_fanvue_user_uuid(str(creator_uuid))
            if account:
                return account
        try:
            account = get_account_by_id(int(normalized_account))
        except (TypeError, ValueError):
            account = None
        if not account:
            raise LookupError("Fanvue account was not found.")
        return account

    @classmethod
    def _webhook_fields(cls, event_type, payload, event):
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        sender = payload.get("sender") if isinstance(payload.get("sender"), dict) else {}
        purchaser = data.get("purchaser") if isinstance(data.get("purchaser"), dict) else {}
        buyer = (
            sender.get("uuid") or purchaser.get("uuid")
            or data.get("purchaserUuid") or data.get("buyerUuid")
            or event.get("fanvue_user_id")
        )
        transaction = (
            payload.get("transactionOrderId") if event_type == "purchase_new"
            else data.get("id")
        )
        return {
            "provider_event_id": payload.get("eventId") or data.get("eventId"),
            "creator_uuid": (
                payload.get("recipientUuid") or data.get("creatorUuid")
                or (
                    data.get("creator", {}).get("uuid")
                    if isinstance(data.get("creator"), dict) else None
                )
            ),
            "buyer_uuid": cls._uuid(buyer),
            "transaction_id": cls._required(transaction, "transaction ID"),
            "payment_id": data.get("id"),
            "amount_minor": cls._optional_int(
                payload.get("price") or data.get("gross") or data.get("amount")
            ),
            "purchase_type": payload.get("purchaseType") or data.get("type"),
            "payment_status": (
                payload.get("transactionOrderStatus") or data.get("status")
            ),
            "display_name": sender.get("displayName") or purchaser.get("displayName"),
            "handle": sender.get("handle") or purchaser.get("handle"),
        }

    @staticmethod
    def _money(row, *names, default=None):
        value = next((row.get(name) for name in names if row.get(name) is not None), default)
        if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
            raise ValueError(f"Earnings field {names[0]} is missing or not minor units.")
        return int(value)

    @staticmethod
    def _timestamp(value):
        if isinstance(value, datetime):
            result = value
        else:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("Earnings timestamp must include a timezone.")
        return result

    @staticmethod
    def _uuid(value):
        try:
            return value if isinstance(value, UUID) else UUID(str(value))
        except (ValueError, TypeError, AttributeError) as error:
            raise ValueError("A verified Fanvue buyer UUID is required.") from error

    @staticmethod
    def _required(value, label):
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{label} is required.")
        return normalized

    @staticmethod
    def _optional_int(value):
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

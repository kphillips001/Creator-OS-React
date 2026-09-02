"""Deterministic Fanvue payment convergence and bot-facing signal projection."""
from __future__ import annotations

import logging
import hashlib
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
        telegram_delivery_service=None,
        fingerprint_attribution_service=None,
    ):
        self.repository = repository or CommerceSignalRepository()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.customers = customer_service or CustomerCommerceService()
        self.intents = purchase_intent_service or PurchaseIntentService()
        self.intent_repository = (
            purchase_intent_repository or PurchaseIntentRepository()
        )
        if telegram_delivery_service is None:
            from app.repositories.chat_message_repository import save_chat_message
            from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService
            telegram_delivery_service = TelegramSalesDeliveryService(
                purchase_intent_service=self.intents,
                conversation_message_saver=save_chat_message,
            )
        self.telegram_deliveries = telegram_delivery_service
        if photoshoot_lifecycle_service is None:
            from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
            photoshoot_lifecycle_service = CustomerPhotoshootLifecycleService()
        self.photoshoot_lifecycles = photoshoot_lifecycle_service
        self.client_factory = client_factory
        if fingerprint_attribution_service is None:
            from app.services.fingerprint_purchase_attribution_service import FingerprintPurchaseAttributionService
            fingerprint_attribution_service = FingerprintPurchaseAttributionService(
                intents=self.intent_repository, identities=self.identities,
            )
        self.fingerprint_attribution = fingerprint_attribution_service

    def process_webhook(self, event: dict, *, mode: str = "LIVE") -> dict:
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
            transaction_family_key=self.repository.transaction_family_key(
                account_id, fields["transaction_id"]
            ) if hasattr(self.repository, "transaction_family_key") else None,
            reconciliation_mode=mode,
            webhook_event_id=event.get("id"),
            payload_sha256=hashlib.sha256(
                str(event.get("payload") or {}).encode()
            ).hexdigest(),
        )
        if not created and reconciliation["state"] == "VERIFIED":
            logger.info(
                "event=duplicate_ignored provider_event_id=%s", provider_event_id
            )
            return {"success": True, "duplicate": True, "state": "VERIFIED"}
        return self._reconcile(reconciliation, fields=fields)

    def retry_pending(self, *, limit: int = 25) -> list[dict]:
        import uuid
        worker_id = f"commerce-signal-{uuid.uuid4()}"
        claim = getattr(self.repository, "claim_due", None)
        rows = claim(worker_instance_id=worker_id, limit=limit) if callable(claim) else self.repository.list_due(limit=limit)
        return [self._reconcile(row) for row in rows]

    def recover_reconciliation(self, reconciliation_id: UUID) -> dict:
        """Idempotently re-evaluate one existing reconciliation from durable evidence."""
        row = self.repository.get_reconciliation(reconciliation_id)
        if row is None:
            raise LookupError("Commerce signal reconciliation was not found.")
        return self._reconcile(row)

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
            currency_result = self._resolve_transaction_currency(
                reconciliation=reconciliation, earning=earning,
                buyer_uuid=buyer_uuid, gross_minor=gross,
            )
            if currency_result["state"] != "RESOLVED":
                reason = currency_result["reason"]
                marker = (
                    self.repository.mark_evidence_conflict
                    if reason == "CURRENCY_EVIDENCE_CONFLICT"
                    else self.repository.mark_evidence_pending
                )
                marker(
                    reconciliation_id, transaction_order_id=transaction_id,
                    external_fanvue_user_uuid=buyer_uuid,
                    earnings_record=earning, reason=reason,
                )
                return {
                    "success": False,
                    "state": "FAILED" if reason == "CURRENCY_EVIDENCE_CONFLICT" else "PENDING",
                    "attribution": {"state": "UNKNOWN", "reason": reason,
                                    "candidateCount": 0},
                }
            currency = currency_result["currency"]
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
            reader = getattr(
                self.identities,
                "get_verified_by_external_fanvue_user_uuid",
                self.identities.get_by_external_fanvue_user_uuid,
            )
            identity = reader(account_id, buyer_uuid)
            fingerprint_result = None
            historical = reconciliation.get("reconciliation_mode") == "HISTORICAL_RECOVERY"
            media_link_purchase = (
                source.lower() in {"medialink", "media_link"}
                or purchase_type.lower() in {"media", "medialink", "media_link"}
            )
            from app.services.private_chat_unlock_gateway_service import fingerprint_bootstrap_enabled
            if (not historical and identity is None and media_link_purchase
                    and fingerprint_bootstrap_enabled()):
                fingerprint_result = self.fingerprint_attribution.attribute(
                    fanvue_account_id=account_id, currency=currency,
                    gross_minor=gross, source=source, buyer_uuid=buyer_uuid,
                    transaction_id=transaction_id,
                    payment_id=((fields or {}).get("payment_id") or transaction_id),
                    event_id=reconciliation["provider_event_id"],
                    purchased_at=timestamp,
                )
                if fingerprint_result is not None:
                    identity = fingerprint_result["mapping"]
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
            attribution = ({
                "state": "UNKNOWN",
                "reason": "HISTORICAL_FINANCIAL_ONLY",
                "candidateCount": 0,
            } if historical else self._attribute(
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
                media_link_purchase=media_link_purchase,
                provider_resource_id=self._provider_resource_id(
                    earning, fields or {}
                ),
                transaction_currency=currency,
            ))
            ownership_count = self._project_exact_ownership(
                creator_profile_id=int(reconciliation["creator_profile_id"]),
                fanvue_account_id=account_id, buyer_uuid=buyer_uuid,
                transaction_id=transaction_id, provider_resource_id=self._provider_resource_id(
                    earning, fields or {}
                ), purchased_at=timestamp,
            )
            self.repository.mark_verified(
                reconciliation_id, transaction_order_id=transaction_id,
                external_fanvue_user_uuid=buyer_uuid, earnings_record=earning,
                attribution_state=attribution.get("state"),
                attribution_reason=attribution.get("reason"),
                attributed_purchase_intent_id=attribution.get(
                    "purchaseIntentId"
                ),
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
                "exactOwnershipCount": ownership_count,
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

    def _project_exact_ownership(self, *, creator_profile_id, fanvue_account_id,
                                 buyer_uuid, transaction_id,
                                 provider_resource_id, purchased_at):
        if not provider_resource_id:
            return 0
        connection_factory = getattr(self.repository, "connection_factory", None)
        if connection_factory is None:
            return 0
        from uuid import uuid4
        with connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT member.asset_id
                    FROM commercial_publications publication
                    JOIN commercial_offerings offering
                      ON offering.offering_id=publication.commercial_offering_id
                    JOIN commercial_offering_assets member
                      ON member.offering_id=offering.offering_id
                    WHERE offering.creator_profile_id=%s
                      AND publication.external_product_id=%s
                      AND publication.status='LIVE'""",
                    (creator_profile_id, provider_resource_id))
                assets = [int(row["asset_id"]) for row in cursor.fetchall()]
                for asset_id in assets:
                    cursor.execute("""INSERT INTO provider_purchase_asset_ownership(
                        ownership_id,creator_profile_id,fanvue_account_id,
                        external_fanvue_user_uuid,provider_transaction_id,
                        provider_resource_id,content_item_id,purchase_timestamp,evidence)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,
                        '{"authority":"FANVUE_PUBLICATION_RESOURCE"}'::jsonb)
                        ON CONFLICT(fanvue_account_id,provider_transaction_id,content_item_id)
                        DO NOTHING""", (uuid4(), creator_profile_id, fanvue_account_id,
                        buyer_uuid, transaction_id, provider_resource_id, asset_id, purchased_at))
        return len(assets)

    def _attribute(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        buyer_uuid: UUID, amount_minor: int, payment_timestamp: datetime,
        transaction_id: str, payment_id: str, event_id: str,
        customer_commerce_profile_id: UUID,
        media_link_purchase: bool,
        provider_resource_id: str | None = None,
        transaction_currency: str | None = None,
    ) -> dict:
        if not media_link_purchase:
            return {"state": "UNKNOWN", "reason": "NOT_MEDIA_LINK_PURCHASE"}
        canonical_currency = self._canonical_currency(transaction_currency)
        if canonical_currency is None:
            return {
                "state": "UNKNOWN",
                "reason": "MISSING_AUTHORITATIVE_CURRENCY",
                "candidateCount": 0,
            }
        # Repair only provider-proven accepted sends before applying the existing
        # fail-closed candidate policy. Ambiguous operations remain excluded.
        self.telegram_deliveries.recover_accepted(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=buyer_uuid,
        )
        candidates = self.intent_repository.list_candidates(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=buyer_uuid,
        )
        context_reader = getattr(
            self.intent_repository, "get_attribution_contexts", None
        )
        contexts = (
            context_reader([item.purchase_intent_id for item in candidates])
            if callable(context_reader) else {}
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
                "purchaseIntentId": previously_attributed[0].purchase_intent_id,
                "lifecycleSynchronized": lifecycle_result is not None,
            }
        survivors = []
        for item in candidates:
            context = contexts.get(item.purchase_intent_id, {})
            persistent = self._persistent_ppv(context)
            canonical_resource_id = str(
                context.get("external_product_id")
                or item.provider_resource_id or ""
            ).strip()
            resource_matches = (
                provider_resource_id is None
                or canonical_resource_id == provider_resource_id
            )
            status_allowed = item.status.value in (
                {"PRESENTED", "CLICKED", "EXPIRED", "SUPERSEDED", "ADMIN_CLOSED", "UNKNOWN"}
                if persistent else {"PRESENTED", "CLICKED"}
            )
            window_matches = (
                item.presented_at <= payment_timestamp
                and (persistent or payment_timestamp <= item.expires_at)
            ) if item.presented_at is not None else False
            if (
                item.expected_price_minor == amount_minor
                and self._canonical_currency(item.expected_currency)
                == canonical_currency
                and resource_matches and status_allowed and window_matches
            ):
                survivors.append(item)
        survivors = self._prefer_latest_canonical_presentation(survivors)
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
                    "Exact buyer, account, creator, price, product policy, "
                    "currency, available Media Link evidence, and "
                    "single-candidate match."
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
                "purchaseIntentId": item.purchase_intent_id,
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

    @staticmethod
    def _currency(earning: dict) -> str | None:
        for key in ("currency", "currencyCode", "currency_code"):
            value = CommerceSignalService._canonical_currency(earning.get(key))
            if value is not None:
                return value
        return None

    def _resolve_transaction_currency(
        self, *, reconciliation: dict, earning: dict,
        buyer_uuid: UUID, gross_minor: int,
    ) -> dict:
        """Converge genuine same-family provider currency without defaulting it."""
        earnings_currency = self._currency(earning)
        webhook_currencies: set[str] = set()
        transaction_id = str(reconciliation["observed_transaction_id"])
        account_id = int(reconciliation["fanvue_account_id"])
        evidence_reader = getattr(
            self.repository, "list_transaction_family_evidence", None,
        )
        evidence = evidence_reader(reconciliation["reconciliation_id"]) if callable(evidence_reader) else []
        for item in evidence:
            event_type = str(item.get("event_type") or item.get("source_event_type") or "")
            if event_type not in self.SUPPORTED_EVENTS:
                continue
            headers = item.get("headers") or {}
            if not any(
                "signature" in str(key).lower() and bool(value)
                for key, value in headers.items()
            ):
                continue
            payload = item.get("payload") or {}
            try:
                fields = self._webhook_fields(event_type, payload, item)
            except (TypeError, ValueError):
                continue
            if fields["transaction_id"] != transaction_id:
                continue
            try:
                evidence_account = self._account(
                    fields.get("creator_uuid"), item.get("webhook_account_id"),
                )
            except LookupError:
                continue
            if int(evidence_account["id"]) != account_id:
                continue
            if fields["buyer_uuid"] != buyer_uuid:
                return {"state": "CONFLICT", "reason": "CURRENCY_EVIDENCE_CONFLICT"}
            if fields.get("amount_minor") not in (None, gross_minor):
                return {"state": "CONFLICT", "reason": "CURRENCY_EVIDENCE_CONFLICT"}
            raw_currency = fields.get("currency")
            if raw_currency is None:
                continue
            currency = self._canonical_currency(raw_currency)
            if currency is None:
                return {"state": "CONFLICT", "reason": "CURRENCY_EVIDENCE_CONFLICT"}
            webhook_currencies.add(currency)
        if len(webhook_currencies) > 1:
            return {"state": "CONFLICT", "reason": "CURRENCY_EVIDENCE_CONFLICT"}
        webhook_currency = next(iter(webhook_currencies), None)
        if earnings_currency and webhook_currency and earnings_currency != webhook_currency:
            return {"state": "CONFLICT", "reason": "CURRENCY_EVIDENCE_CONFLICT"}
        resolved = earnings_currency or webhook_currency
        if resolved is None:
            return {"state": "MISSING", "reason": "MISSING_AUTHORITATIVE_CURRENCY"}
        return {"state": "RESOLVED", "currency": resolved,
                "source": "EARNINGS" if earnings_currency else "SIGNED_TRANSACTION_FAMILY_WEBHOOK"}

    @staticmethod
    def _canonical_currency(value) -> str | None:
        normalized = str(value or "").strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            return None
        return normalized

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
        if status in {"ABANDONED", "SUPERSEDED", "ADMIN_CLOSED"}:
            return "NOT_PURCHASED_YET"
        return "NO_ACTIVE_OFFER"

    @staticmethod
    def _persistent_ppv(context: dict) -> bool:
        offering_type = str(context.get("offering_type") or "").upper()
        source_id = context.get("source_photoshoot_deliverable_id")
        selling_mode = str(context.get("selling_mode") or "").upper()
        channel = str(context.get("bundle_sales_channel") or "").upper()
        if offering_type == "BUNDLE":
            return selling_mode == "BUNDLE" and channel == "CHAT"
        return offering_type == "SINGLE_IMAGE" and source_id is None

    @staticmethod
    def _prefer_latest_canonical_presentation(candidates):
        if len(candidates) <= 1:
            return candidates
        identities = {
            (
                item.commercial_offering_id,
                item.commercial_publication_id,
                item.provider_resource_id,
            )
            for item in candidates
        }
        if len(identities) != 1:
            return candidates
        return [max(
            candidates,
            key=lambda item: (
                item.presented_at or item.created_at,
                item.created_at,
                str(item.purchase_intent_id),
            ),
        )]

    @staticmethod
    def _provider_resource_id(*sources: dict) -> str | None:
        aliases = (
            "provider_resource_id", "mediaLinkUuid", "mediaLinkId", "media_link_uuid",
            "media_link_id", "externalProductId", "external_product_id",
        )
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in aliases:
                value = str(source.get(key) or "").strip()
                if value:
                    return value
        return None

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
            "provider_resource_id": cls._provider_resource_id(payload, data),
            "payment_status": (
                payload.get("transactionOrderStatus") or data.get("status")
            ),
            "currency": data.get("currency") or payload.get("currency"),
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

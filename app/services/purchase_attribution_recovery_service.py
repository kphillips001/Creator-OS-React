"""Operator review and fail-closed manual attribution of verified purchases."""
from __future__ import annotations

from uuid import UUID

from app.repositories.purchase_attribution_recovery_repository import PurchaseAttributionRecoveryRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.purchase_intent_service import PurchaseIntentService


class PurchaseAttributionRecoveryService:
    def __init__(self, *, repository=None, intent_repository=None,
                 intent_service=None, photoshoot_lifecycle_service=None):
        self.repository = repository or PurchaseAttributionRecoveryRepository()
        self.intent_repository = intent_repository or PurchaseIntentRepository()
        self.intents = intent_service or PurchaseIntentService(
            repository=self.intent_repository
        )
        if photoshoot_lifecycle_service is None:
            from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
            photoshoot_lifecycle_service = CustomerPhotoshootLifecycleService()
        self.lifecycles = photoshoot_lifecycle_service

    def queue(self, *, creator_profile_id: int):
        return {"items": [self._summary(row) for row in self.repository.list_unresolved(
            creator_profile_id=creator_profile_id
        )]}

    def detail(self, *, creator_profile_id: int, reconciliation_id):
        item = self.repository.get_unresolved(
            creator_profile_id=creator_profile_id,
            reconciliation_id=UUID(str(reconciliation_id)),
        )
        if item is None:
            raise LookupError("Unresolved purchase was not found.")
        candidates = []
        if item.get("gross_minor") is not None and item.get("payment_timestamp") is not None:
            rows = self.repository.list_candidates(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=int(item["fanvue_account_id"]),
                buyer_uuid=UUID(str(item["external_fanvue_user_uuid"])),
                amount_minor=int(item["gross_minor"]),
                purchased_at=item["payment_timestamp"],
                provider_resource_id=self._resource(
                    dict(item.get("earnings_record") or {})
                ),
            )
            candidates = [self._candidate(row, item) for row in rows]
        return {**self._summary(item), "candidates": candidates,
                "canManuallyAttribute": item.get("state") == "VERIFIED"}

    def attribute(self, *, creator_profile_id: int, reconciliation_id,
                  purchase_intent_id, operator_note=None,
                  operator_source="CREATOR_OS_OPERATIONS"):
        reconciliation_uuid = UUID(str(reconciliation_id))
        intent_uuid = UUID(str(purchase_intent_id))
        review = self.repository.get_unresolved(
            creator_profile_id=creator_profile_id,
            reconciliation_id=reconciliation_uuid,
        )
        if review is None:
            # Idempotent repository lookup handles an already-resolved retry.
            review = {"customer_commerce_profile_id": None}
        note = str(operator_note or "").strip() or None
        if note and len(note) > 500:
            raise ValueError("Operator note must be 500 characters or fewer.")
        audit, replay = self.repository.commit_manual(
            creator_profile_id=creator_profile_id,
            reconciliation_id=reconciliation_uuid,
            purchase_intent_id=intent_uuid,
            operator_source=str(operator_source or "CREATOR_OS_OPERATIONS")[:100],
            operator_note=note,
        )
        intent = self.intent_repository.get(intent_uuid)
        if intent is None:
            raise LookupError("Resolved Purchase Intent was not found.")
        if audit.get("downstream_completed_at") is None:
            customer_profile_id = review.get("customer_commerce_profile_id")
            if customer_profile_id is not None:
                self.lifecycles.synchronize_attributed_purchase(
                    intent=intent,
                    customer_commerce_profile_id=customer_profile_id,
                )
            observer = getattr(self.intents, "observe", None)
            if callable(observer):
                observer(
                    intent, "PURCHASED",
                    source_event_key=f"manual_attribution:{audit['resolution_id']}:PURCHASED",
                )
            marker = getattr(self.repository, "mark_downstream_completed", None)
            if callable(marker):
                audit = marker(audit["resolution_id"])
        return {
            "success": True, "idempotentReplay": replay,
            "resolutionId": str(audit["resolution_id"]),
            "reconciliationId": str(audit["reconciliation_id"]),
            "purchaseIntentId": str(audit["purchase_intent_id"]),
            "transactionOrderId": audit["transaction_order_id"],
            "attributionState": "MANUALLY_ATTRIBUTED",
        }

    @staticmethod
    def _summary(row):
        earnings = dict(row.get("earnings_record") or {})
        return {
            "reconciliationId": str(row["reconciliation_id"]),
            "state": row.get("state"),
            "attributionState": row.get("attribution_state") or "PENDING",
            "reason": row.get("attribution_reason") or row.get("last_error"),
            "customer": row.get("display_name") or row.get("handle") or "Unknown customer",
            "telegramUserId": row.get("telegram_user_id"),
            "fanvueBuyerId": str(row.get("external_fanvue_user_uuid") or ""),
            "transactionOrderId": row.get("transaction_order_id"),
            "paymentTimestamp": row.get("payment_timestamp"),
            "amountMinor": row.get("gross_minor") if row.get("gross_minor") is not None else row.get("expected_amount_minor"),
            "currency": (
                earnings.get("currency")
                or earnings.get("currencyCode")
                or earnings.get("currency_code")
                or "Unavailable"
            ),
            "providerResourceId": PurchaseAttributionRecoveryService._resource(earnings),
            "purchaseSource": row.get("purchase_source") or row.get("purchase_type"),
        }

    @staticmethod
    def _candidate(row, review):
        resource = PurchaseAttributionRecoveryService._resource(
            dict(review.get("earnings_record") or {})
        )
        candidate_resource = str(row.get("external_product_id") or row.get("provider_resource_id") or "")
        delivery_state = row.get("telegram_delivery_state")
        reasons = ["Same customer", "Same creator and Fanvue account",
                   "Exact price match", "Presented before purchase"]
        if resource and resource == candidate_resource:
            reasons.append("Same Fanvue provider resource")
        if delivery_state in ("TELEGRAM_ACCEPTED", "CONFIRMED"):
            reasons.append("Telegram message confirmed")
        warnings = []
        if resource and resource != candidate_resource:
            warnings.append("Provider resource does not match")
        presentation_proven = delivery_state in (
            "TELEGRAM_ACCEPTED", "CONFIRMED"
        )
        if not presentation_proven:
            warnings.append(
                "Cannot attribute: No confirmed Telegram presentation evidence."
            )
        return {
            "purchaseIntentId": str(row["purchase_intent_id"]),
            "offeringId": str(row["commercial_offering_id"]),
            "publicationId": str(row["commercial_publication_id"]),
            "offeringTitle": row.get("offering_title") or "Untitled offering",
            "offeringType": row.get("offering_type"),
            "expectedPriceMinor": row.get("expected_price_minor"),
            "currency": row.get("expected_currency"),
            "providerResourceId": candidate_resource or None,
            "mediaLink": row.get("publication_delivery_url") or row.get("delivery_url"),
            "presentedAt": row.get("presented_at"),
            "telegramMessageId": row.get("outbound_telegram_message_id") or row.get("telegram_message_id"),
            "telegramDeliveryState": delivery_state,
            "canManuallyAttribute": presentation_proven,
            "salesSessionId": str(row.get("sales_session_id") or "") or None,
            "photoshootRelationship": str(row.get("source_photoshoot_deliverable_id") or "") or None,
            "supportingEvidence": reasons, "warnings": warnings,
        }

    @staticmethod
    def _resource(earning):
        for key in ("mediaLinkUuid", "mediaLinkId", "media_link_uuid",
                    "media_link_id", "externalProductId", "external_product_id"):
            value = earning.get(key)
            if value:
                return str(value)
        return None

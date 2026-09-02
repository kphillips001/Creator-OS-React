"""Crash-safe orchestration state for commercial Telegram deliveries."""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from app.models.telegram_sales_delivery_operation import TelegramSalesDeliveryState
from app.repositories.telegram_sales_delivery_repository import TelegramSalesDeliveryRepository


class TelegramSalesDeliveryService:
    TERMINAL_NO_SEND = frozenset({
        TelegramSalesDeliveryState.TELEGRAM_ACCEPTED,
        TelegramSalesDeliveryState.CONFIRMED,
        TelegramSalesDeliveryState.FAILED,
        TelegramSalesDeliveryState.AMBIGUOUS,
        TelegramSalesDeliveryState.SENDING,
    })

    def __init__(self, *, repository=None, purchase_intent_service=None,
                 conversation_message_saver=None):
        self.repository = repository or TelegramSalesDeliveryRepository()
        self.purchase_intents = purchase_intent_service
        self.message_saver = conversation_message_saver

    def prepare(self, *, intent, result, payload):
        if intent is None:
            return None, False
        diagnostics = dict(result.diagnostic_metadata or {})
        required = ("conversation_thread_id", "conversation_fanvue_account_id",
                    "conversation_fanvue_user_id")
        if any(diagnostics.get(key) is None for key in required):
            if diagnostics.get("telegram_identity_eligibility") == "UNMAPPED_BOOTSTRAP":
                # Numeric-only prospects have no canonical Fanvue conversation yet.
                # Their already-durable ordinary operation owns the first commercial
                # send until settlement creates the verified identity mapping.
                return None, False
            raise ValueError("Canonical commercial delivery metadata is incomplete.")
        return self.repository.get_or_create(
            correlation_id=str(result.correlation_id),
            creator_profile_id=int(intent.creator_profile_id),
            fanvue_account_id=int(diagnostics["conversation_fanvue_account_id"]),
            conversation_thread_id=int(diagnostics["conversation_thread_id"]),
            fanvue_user_id=int(diagnostics["conversation_fanvue_user_id"]),
            telegram_chat_id=int(payload.telegram_chat_id),
            inbound_telegram_message_id=int(payload.message_id),
            purchase_intent_id=intent.purchase_intent_id,
            commercial_offering_id=intent.commercial_offering_id,
            commercial_publication_id=intent.commercial_publication_id,
            response_text=result.response_text,
            delivery_payload=dict(result.delivery_payload or {}),
        )

    def get(self, correlation_id):
        return self.repository.get_by_correlation(str(correlation_id))

    def claim(self, operation):
        if operation is None or operation.state not in {
            TelegramSalesDeliveryState.CREATED,
            TelegramSalesDeliveryState.RETRYABLE,
        }:
            return None
        return self.repository.claim_created(operation.operation_id)

    def accepted(self, operation, telegram_message_id):
        if telegram_message_id is None:
            raise ValueError("Telegram acceptance requires a provider message ID.")
        return self.repository.mark_accepted(operation.operation_id, int(telegram_message_id))

    def record_provider_evidence(self, operation, evidence):
        return self.repository.record_provider_evidence(
            operation.operation_id, evidence,
        )

    def failed(self, operation, error):
        reason = f"{type(error).__name__}: {str(error)[:300]}"
        if self._recoverable(error):
            marker = getattr(self.repository, "mark_retryable", None)
            if callable(marker):
                return marker(operation.operation_id, reason)
        if self._ambiguous(error):
            marker = getattr(self.repository, "mark_ambiguous", None)
            if callable(marker):
                return marker(operation.operation_id, reason)
            return None
        return self.repository.mark_failed(operation.operation_id, reason)

    def confirm(self, operation):
        if operation is None:
            return None
        if operation.state not in {
            TelegramSalesDeliveryState.TELEGRAM_ACCEPTED,
            TelegramSalesDeliveryState.CONFIRMED,
        }:
            return operation
        if self.purchase_intents is not None:
            intent = self._intent(operation.purchase_intent_id)
            status = getattr(getattr(intent, "status", None), "value",
                             getattr(intent, "status", None))
            if status in (None, "CREATED"):
                confirm_delivery = getattr(self.purchase_intents, "confirm_delivery", None)
                if callable(confirm_delivery):
                    confirm_delivery(
                        intent,
                        telegram_message_id=operation.outbound_telegram_message_id,
                        presented_at=operation.telegram_accepted_at,
                    )
                else:
                    self.purchase_intents.confirm_presented(
                        operation.purchase_intent_id,
                        telegram_message_id=operation.outbound_telegram_message_id,
                        presented_at=operation.telegram_accepted_at,
                    )
        self._save_transcript(operation)
        metadata = dict((operation.delivery_payload or {}).get("metadata") or {})
        if metadata.get("message_purpose") == "PURCHASE_ACKNOWLEDGEMENT":
            atomic_confirm = getattr(
                self.repository, "confirm_purchase_acknowledgement", None,
            )
            if callable(atomic_confirm):
                return atomic_confirm(operation.operation_id)
        return self.repository.mark_confirmed(operation.operation_id)

    def recover_accepted(self, **filters):
        recovered = []
        for operation in self.repository.list_accepted(**filters):
            recovered.append(self.confirm(operation))
        return recovered

    def recover_startup(self):
        # An orphaned SENDING claim has an unknowable provider outcome.
        recovered = list(self.repository.mark_sending_ambiguous())
        reader = getattr(
            self.repository,
            "list_confirmed_unacknowledged_acknowledgements",
            None,
        )
        if callable(reader):
            recovered.extend(self.confirm(operation) for operation in reader())
        return recovered

    def _intent(self, intent_id):
        getter = getattr(self.purchase_intents, "get", None)
        if callable(getter):
            return getter(intent_id)
        repository = getattr(self.purchase_intents, "repository", None)
        if repository is None:
            repository = getattr(self.purchase_intents, "intents", None)
            repository = getattr(repository, "repository", repository)
        getter = getattr(repository, "get", None)
        return getter(intent_id) if callable(getter) else type(
            "IntentReference", (), {"purchase_intent_id": intent_id}
        )()

    def _save_transcript(self, operation):
        if self.message_saver is None:
            return
        message_uuid = uuid5(
            NAMESPACE_URL,
            f"telegram:{operation.telegram_chat_id}:outbound:{operation.outbound_telegram_message_id}",
        )
        payload = dict(operation.delivery_payload or {})
        delivery_metadata = dict(payload.get("metadata") or {})
        self.message_saver(
            fanvue_account_id=operation.fanvue_account_id,
            thread_id=operation.conversation_thread_id,
            fanvue_user_id=operation.fanvue_user_id,
            direction="outbound", sender_type="bot", text=operation.response_text,
            fanvue_message_uuid=message_uuid,
            raw_payload={
                "provider": "TELEGRAM", "channel": "PRIVATE_CHAT",
                "telegram_chat_id": operation.telegram_chat_id,
                "telegram_message_id": operation.outbound_telegram_message_id,
                "correlation_id": operation.correlation_id,
                "purchase_intent_id": str(operation.purchase_intent_id),
                "sales_delivery_operation_id": str(operation.operation_id),
                "commercial_offering_id": str(operation.commercial_offering_id),
                "commercial_publication_id": str(operation.commercial_publication_id),
                "content_type": payload.get("delivery_type"),
                "delivery_kind": payload.get("delivery_reason"),
                "price_minor": delivery_metadata.get("price_minor"),
                "currency": delivery_metadata.get("currency"),
                "session_step": delivery_metadata.get("session_step"),
                "session_role": delivery_metadata.get("session_role"),
                "session_id": delivery_metadata.get("session_id"),
                "session_asset_id": delivery_metadata.get("session_asset_id"),
                "message_purpose": delivery_metadata.get("message_purpose"),
                "purchase_kind": delivery_metadata.get("purchase_kind"),
                "attached_media_kind": (
                    "BUNDLE_PROMOTIONAL_TEASER"
                    if delivery_metadata.get("bundle_teaser_delivery")
                    else None
                ),
            },
        )

    @staticmethod
    def _ambiguous(error):
        return isinstance(error, (TimeoutError, ConnectionError, OSError))

    @staticmethod
    def _recoverable(error):
        code = str(getattr(error, "code", "") or "")
        text = str(error)
        return code in {
            "BUSINESS_CONNECTION_UNAVAILABLE", "BUSINESS_CONNECTION_DISABLED",
            "BUSINESS_REPLY_NOT_ALLOWED", "BUSINESS_PEER_USAGE_MISSING",
        } or any(marker in text for marker in (
            "PUBLIC_COMMERCE_ORIGIN_UNAVAILABLE",
            "INVALID_CUSTOMER_FACING_DESTINATION",
        ))

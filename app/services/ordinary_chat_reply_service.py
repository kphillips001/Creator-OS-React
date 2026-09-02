"""Crash-safe orchestration for non-commercial Telegram text replies."""
from __future__ import annotations

import hashlib
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository


class OrdinaryChatReplyService:
    ACCOUNT_SCOPE = "AVA_TELETHON_PRIVATE"
    RECENT_PROSPECT_EXCHANGE_LIMIT = 6
    NO_SEND = frozenset({OrdinaryChatReplyState.SENT_CONFIRMED,
        OrdinaryChatReplyState.SEND_UNCERTAIN, OrdinaryChatReplyState.TERMINAL_FAILED,
        OrdinaryChatReplyState.SUPPRESSED, OrdinaryChatReplyState.SENDING})

    def __init__(self, *, repository=None, worker_id=None,
                 prospect_service=None, sales_session_service=None):
        self.repository = repository or OrdinaryChatReplyRepository()
        self.worker_id = worker_id or f"ordinary-reply-{uuid4()}"
        self._prospect_service = prospect_service
        self._sales_session_service = sales_session_service

    def begin(self, payload):
        correlation = f"ordinary_reply:{self.ACCOUNT_SCOPE}:{payload.telegram_chat_id}:{payload.message_id}"
        return self.repository.get_or_create(account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(payload.telegram_chat_id), inbound_message_id=int(payload.message_id),
            sender_user_id=int(payload.telegram_user_id), correlation_id=correlation,
            inbound_message_text=payload.message_text,
            inbound_received_at=payload.received_at)

    def claim_generation(self, operation):
        return self.repository.claim_generation(operation.operation_id, owner=self.worker_id)

    def generated(self, operation, result):
        payload = asdict(result)
        text = str(result.response_text or "")
        diagnostics = dict(result.diagnostic_metadata or {})
        thread_id = diagnostics.get("conversation_thread_id")
        content_sha256 = hashlib.sha256(text.encode()).hexdigest()
        if not text.strip() and result.blocked is True:
            reason = str(
                result.error_code
                or diagnostics.get("paid_presentation_block_reason")
                or diagnostics.get("lifecycle_presentation_block_reason")
                or "authoritative_generation_suppressed"
            )
            return self.repository.store_suppressed_generation(
                operation.operation_id, owner=self.worker_id,
                response_payload=payload, response_text=text,
                content_sha256=content_sha256,
                delivery_payload=dict(result.delivery_payload or {}),
                reason=f"intentional_suppression:{reason}",
                conversation_thread_id=thread_id,
            )
        return self.repository.store_generated(operation.operation_id, owner=self.worker_id,
            response_payload=payload,response_text=text,
            content_sha256=content_sha256,
            delivery_payload=dict(result.delivery_payload or {}),
            conversation_thread_id=thread_id)

    def generation_failed(self, operation, error):
        return self.repository.fail_generation(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}")

    def result(self, operation):
        return TelegramInboundResult(**dict(operation.response_payload)) if operation.response_payload else None

    def suppress_commercial(self, operation):
        return self.repository.suppress(operation.operation_id,
            reason="commercial_delivery_namespace")

    def enrich_commercial(self, operation, result, intent):
        """Bind unmapped commercial bootstrap state to its durable send record."""
        diagnostics = result.diagnostic_metadata
        diagnostics.update({
            "purchase_intent_created": bool(
                diagnostics.get("purchase_intent_created")
            ),
            "purchase_intent_id": str(intent.purchase_intent_id),
            "commercial_payload_composed": True,
            "commercial_link_attachment_mode": (
                "TELEGRAM_INLINE_BUTTON"
                if dict(result.delivery_payload.get("metadata") or {}).get(
                    "private_chat_unlock_button"
                ) else "MESSAGE_TEXT"
            ),
            "final_customer_facing_offer_text": result.response_text,
            "outbound_dispatch_attempted": True,
            "outbound_dispatch_path": "ORDINARY_REPLY_UNMAPPED_COMMERCIAL",
            "outbound_dispatch_idempotency_key": operation.correlation_id,
            "outbound_retry_eligible": True,
        })
        return self.repository.update_generated_payload(
            operation.operation_id,
            response_payload=asdict(result),
            delivery_payload=dict(result.delivery_payload or {}),
        )

    def requeue_empty_generation(self, operation, *, reason):
        return self.repository.requeue_empty_generation(
            operation.operation_id, reason=reason,
        )

    def requeue_suppressed_engine_exception(self, operation, *, reason):
        return self.repository.requeue_suppressed_engine_exception(
            operation.operation_id, reason=reason,
        )

    def retry_payload(self, operation):
        """Reconstruct the original normalized inbound for a durable retry."""
        from app.models.telegram_inbound import TelegramInboundPayload
        return TelegramInboundPayload(
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            telegram_chat_id=operation.telegram_chat_id,
            message_text=operation.inbound_message_text or "",
            message_id=operation.inbound_telegram_message_id,
            received_at=operation.inbound_received_at,
        )

    def commercial_bootstrap_failed(self, operation, error):
        return self.repository.fail_generated_before_send(
            operation.operation_id,
            reason=f"commercial_bootstrap:{type(error).__name__}: {str(error)[:850]}",
        )

    def claim_send(self, operation):
        return self.repository.claim_send(operation.operation_id, owner=self.worker_id)

    def confirmed(self, operation, telegram_message_id):
        if telegram_message_id is None:
            return self.uncertain(operation, ConnectionError(
                "Telegram acceptance lacked a provider message ID"))
        confirmed = self.repository.confirm_sent(
            operation.operation_id, owner=self.worker_id,
            telegram_message_id=int(telegram_message_id),
        )
        if confirmed is not None:
            self._finalize_confirmed_supporter_boundary(
                confirmed, telegram_message_id=int(telegram_message_id),
            )
            self._finalize_confirmed_tease_progression(confirmed)
            self._finalize_confirmed_session_proposal(
                confirmed, telegram_message_id=int(telegram_message_id),
            )
        return confirmed

    def _finalize_confirmed_supporter_boundary(self, operation, *, telegram_message_id):
        diagnostics = dict(
            dict(operation.response_payload or {}).get("diagnostic_metadata") or {}
        )
        if not diagnostics.get("supporter_attention_boundary_pending_confirmation"):
            return
        scope = dict(
            diagnostics.get("pending_supporter_attention_boundary_context") or {}
        )
        if not all(scope.get(key) is not None for key in (
            "creator_profile_id", "fanvue_account_id", "telegram_user_id"
        )):
            raise RuntimeError("Confirmed supporter boundary is missing prospect scope")
        if self._prospect_service is None:
            from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
            self._prospect_service = UnmappedTelegramProspectService()
        self._prospect_service.record_supporter_boundary_delivery(
            creator_profile_id=int(scope["creator_profile_id"]),
            fanvue_account_id=int(scope["fanvue_account_id"]),
            telegram_user_id=int(scope["telegram_user_id"]),
            correlation_id=scope.get("correlation_id") or operation.correlation_id,
            provider_message_id=telegram_message_id,
        )

    def _finalize_confirmed_session_proposal(
        self, operation, *, telegram_message_id,
    ):
        """Persist only provider-confirmed, customer-visible Session proposals."""
        diagnostics = dict(
            dict(operation.response_payload or {}).get("diagnostic_metadata") or {}
        )
        if not diagnostics.get(
            "session_proposal_delivery_pending_confirmation"
        ):
            return
        proposal = dict(diagnostics.get("pending_session_proposal") or {})
        scope = dict(diagnostics.get("pending_session_proposal_context") or {})
        required = ("creator_profile_id", "fanvue_account_id", "telegram_user_id")
        if not all(scope.get(item) is not None for item in required):
            raise RuntimeError("Confirmed Session proposal is missing prospect scope")
        if self._prospect_service is None:
            from app.services.unmapped_telegram_prospect_service import (
                UnmappedTelegramProspectService,
            )
            self._prospect_service = UnmappedTelegramProspectService()
        self._prospect_service.record_session_proposal(
            creator_profile_id=int(scope["creator_profile_id"]),
            fanvue_account_id=int(scope["fanvue_account_id"]),
            telegram_user_id=int(scope["telegram_user_id"]),
            correlation_id=scope.get("correlation_id") or operation.correlation_id,
            source_inbound=scope.get("correlation_id") or operation.correlation_id,
            delivery_correlation_id=operation.correlation_id,
            delivery_provider_message_id=telegram_message_id,
            session_offering_id=proposal.get("offeringId"),
        )

    def _finalize_confirmed_tease_progression(self, operation):
        """Persist TEASE only after Telegram confirms customer-visible delivery."""
        diagnostics = dict(
            dict(operation.response_payload or {}).get("diagnostic_metadata") or {}
        )
        if not diagnostics.get("progression_finalized_after_delivery"):
            return
        progression = diagnostics.get("pending_sales_progression")
        scope = dict(diagnostics.get("pending_sales_progression_context") or {})
        if not isinstance(progression, dict) or not progression:
            return
        if scope.get("sales_session_id"):
            if self._sales_session_service is None:
                from app.services.sales_session_service import SalesSessionService
                self._sales_session_service = SalesSessionService()
            self._sales_session_service.record_conversational_progression(
                session_id=scope["sales_session_id"],
                creator_profile_id=int(scope["creator_profile_id"]),
                progression=progression,
            )
            return
        required = ("creator_profile_id", "fanvue_account_id", "telegram_user_id")
        if not all(scope.get(item) is not None for item in required):
            raise RuntimeError("Confirmed tease is missing prospect progression scope")
        if self._prospect_service is None:
            from app.services.unmapped_telegram_prospect_service import (
                UnmappedTelegramProspectService,
            )
            self._prospect_service = UnmappedTelegramProspectService()
        self._prospect_service.record_sales_progression(
            creator_profile_id=int(scope["creator_profile_id"]),
            fanvue_account_id=int(scope["fanvue_account_id"]),
            telegram_user_id=int(scope["telegram_user_id"]),
            progression=progression,
            correlation_id=scope.get("correlation_id") or operation.correlation_id,
        )

    def record_provider_evidence(self, operation, evidence):
        return self.repository.record_provider_evidence(
            operation.operation_id, owner=self.worker_id, evidence=evidence,
        )

    def failed(self, operation, error, *, definitive=False, terminal=False,
               recoverable=False):
        terminal = False if recoverable else (
            terminal or isinstance(error, (PermissionError, ValueError))
        )
        ambiguous = not definitive and isinstance(error, (TimeoutError, ConnectionError, OSError))
        if recoverable:
            ambiguous = False
        return self.repository.fail_send(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}", ambiguous=ambiguous,
            terminal=terminal)

    def uncertain(self, operation, error):
        return self.repository.fail_send(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}", ambiguous=True)

    def recover_startup(self):
        return self.repository.recover_orphaned_sends()

    def sleep_context(self, operation, *, sleep_service):
        cycle, _, _ = sleep_service.schedule()
        confirmed = self.repository.has_confirmed_sleep_signoff(
            account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(operation.telegram_chat_id), cycle_id=cycle,
        )
        active = self.repository.has_recent_confirmed_conversation(
            account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(operation.telegram_chat_id),
            sender_user_id=int(operation.inbound_sender_telegram_user_id),
            since=sleep_service._local(None) - timedelta(minutes=20),
        )
        return sleep_service.evaluate(
            active_conversation=active, signoff_delivered=confirmed,
        )

    def defer_for_sleep(self, operation, decision):
        return self.repository.defer_for_sleep(
            operation.operation_id, wake_time=decision.wake_time,
            cycle_id=decision.cycle_id,
        )

    def due_sleep_payloads(self, *, now):
        operations = self.repository.release_due_sleep_deferred(
            account_scope=self.ACCOUNT_SCOPE, now=now,
        )
        from app.models.telegram_inbound import TelegramInboundPayload
        return [TelegramInboundPayload(
            telegram_user_id=item.inbound_sender_telegram_user_id,
            telegram_chat_id=item.telegram_chat_id,
            message_text=item.inbound_message_text or "",
            message_id=item.inbound_telegram_message_id,
            received_at=item.inbound_received_at,
        ) for item in operations]

    def recent_confirmed_history(
        self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
        telegram_chat_id, exclude_inbound_message_id=None,
    ):
        operations = self.repository.list_confirmed_recent_for_prospect(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            account_scope=self.ACCOUNT_SCOPE,
            exclude_inbound_message_id=exclude_inbound_message_id,
            limit=self.RECENT_PROSPECT_EXCHANGE_LIMIT,
        )
        unique = {}
        for operation in operations:
            if (
                operation.state is not OrdinaryChatReplyState.SENT_CONFIRMED
                or operation.outbound_telegram_message_id is None
                or not str(operation.inbound_message_text or "").strip()
                or not str(operation.response_text or "").strip()
                or (
                    exclude_inbound_message_id is not None
                    and int(operation.inbound_telegram_message_id)
                    == int(exclude_inbound_message_id)
                )
            ):
                continue
            unique.setdefault(
                int(operation.inbound_telegram_message_id), operation
            )
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                item.inbound_received_at or item.created_at,
                item.inbound_telegram_message_id,
            ),
        )[-self.RECENT_PROSPECT_EXCHANGE_LIMIT:]
        history = []
        for operation in ordered:
            history.extend((
                {"role": "user", "content": operation.inbound_message_text},
                {"role": "assistant", "content": operation.response_text},
            ))
        return history

"""Crash-safe orchestration for non-commercial Telegram text replies."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import date, datetime, timedelta
from enum import Enum
from uuid import UUID, uuid4

from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository


def durable_plain_data(value):
    """Copy a runtime value into an independent JSON-safe durable payload.

    ``dataclasses.asdict`` delegates unknown nested values to ``deepcopy``.
    That is incompatible with immutable mapping views such as mappingproxy,
    which are valid in canonical commerce projections.  Walk fields and
    containers explicitly so immutability remains a runtime concern while the
    persistence boundary receives ordinary data.
    """
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: durable_plain_data(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(durable_plain_data(key)): durable_plain_data(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [durable_plain_data(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [durable_plain_data(item) for item in sorted(
            value, key=lambda item: str(item),
        )]
    if isinstance(value, Enum):
        return durable_plain_data(value.value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(
        f"Unsupported durable ordinary-reply payload type: {type(value).__name__}"
    )


class OrdinaryChatReplyService:
    ACCOUNT_SCOPE = "AVA_TELETHON_PRIVATE"
    RECENT_PROSPECT_EXCHANGE_LIMIT = 6
    NO_SEND = frozenset({OrdinaryChatReplyState.SENT_CONFIRMED,
        OrdinaryChatReplyState.SEND_UNCERTAIN, OrdinaryChatReplyState.TERMINAL_FAILED,
        OrdinaryChatReplyState.SUPPRESSED, OrdinaryChatReplyState.SENDING})
    CORRECTABLE_QUALITY_REASONS = frozenset({
        "CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED",
    })

    def __init__(self, *, repository=None, worker_id=None,
                 prospect_service=None, sales_session_service=None,
                 image_boundary_repository=None, delivery_quality_gate=None,
                 attention_service=None, creator_profile_id=None,
                 fanvue_account_id=None, pre_generation_commercial=None,
                 market_resource_gate=None):
        self.repository = repository or OrdinaryChatReplyRepository()
        self.worker_id = worker_id or f"ordinary-reply-{uuid4()}"
        self.creator_profile_id = creator_profile_id
        self.fanvue_account_id = fanvue_account_id
        self._pre_generation_commercial = pre_generation_commercial
        self._market_resource_gate = market_resource_gate
        self._prospect_service = prospect_service
        self._sales_session_service = sales_session_service
        self._image_boundary_repository = image_boundary_repository
        if delivery_quality_gate is None:
            from app.services.ordinary_reply_delivery_quality_gate import OrdinaryReplyDeliveryQualityGate
            delivery_quality_gate = OrdinaryReplyDeliveryQualityGate()
        self._delivery_quality_gate = delivery_quality_gate
        if attention_service is None:
            from app.services.ava_attention_investment_service import AvaAttentionInvestmentService
            attention_service=AvaAttentionInvestmentService()
        self._attention=attention_service
        from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
        self._natural_conversation=AvaNaturalConversationPolicy()

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
        if (not str(result.response_text or "").strip()
                and str(result.error_code or "") == "decision_engine_exception"):
            diagnostics = dict(result.diagnostic_metadata or {})
            diagnostics["generation_fallback"] = {"applied": True, "reason": "DECISION_ENGINE_EXCEPTION", "authority": "OrdinaryChatReplyService"}
            fallback = "I hit a snag answering that properly—give me a moment and try me again."
            result = replace(result, response_text=fallback, blocked=False, error_code=None,
                diagnostic_metadata=diagnostics,
                delivery_payload={"type": "MESSAGE_TEXT", "message_text": fallback})
        elif not str(result.response_text or "").strip() and result.blocked is not True:
            diagnostics = dict(result.diagnostic_metadata or {})
            diagnostics["generation_fallback"] = {"applied": True, "reason": "EMPTY_GENERATION", "authority": "OrdinaryChatReplyService"}
            fallback = "I don’t want to give you a half-answer—give me a moment and try me again."
            result = replace(result, response_text=fallback, diagnostic_metadata=diagnostics,
                delivery_payload={"type": "MESSAGE_TEXT", "message_text": fallback})
        diagnostics = dict(result.diagnostic_metadata or {})
        try:
            recent = self.repository.recent_ava_responses(operation)
        except (AttributeError, TypeError):
            recent = diagnostics.get("recentAvaResponses") or ()
        if not isinstance(recent, (list, tuple)):
            recent = diagnostics.get("recentAvaResponses") or ()
        operation_delivery = getattr(operation, "delivery_payload", None) or {}
        attention = str(dict(
            operation_delivery.get("attentionInvestment") or {}
        ).get("investment") or "NORMAL")
        natural = self._natural_conversation.evaluate(
            customer_text=str(getattr(operation, "inbound_message_text", "") or ""),
            candidate=str(result.response_text or ""), diagnostics=diagnostics,
            recent_ava_responses=recent, attention=attention,
        )
        diagnostics["naturalConversation"] = natural.diagnostics()
        if natural.repaired:
            delivery = dict(result.delivery_payload or {})
            if delivery.get("type") == "MESSAGE_TEXT":
                delivery["message_text"] = natural.text
            result = replace(result, response_text=natural.text,
                             delivery_payload=delivery)
        result = replace(result, diagnostic_metadata=diagnostics)
        gate = self._delivery_quality_gate.evaluate(result)
        result.diagnostic_metadata["delivery_quality_gate"] = {
            "authority": "OrdinaryReplyDeliveryQualityGate", "disposition": gate.disposition,
            "blockingReasons": list(gate.reasons),
        }
        if not gate.allowed:
            result.diagnostic_metadata["conversationQualityDisposition"] = "BLOCKED_BEFORE_DELIVERY"
            text = str(result.response_text or "")
            reasons = frozenset(gate.reasons)
            attempt = int(getattr(operation, "generation_attempt_count", 1) or 1)
            if (reasons and reasons.issubset(self.CORRECTABLE_QUALITY_REASONS)
                    and attempt == 1
                    and int(getattr(operation, "send_attempt_count", 0) or 0) == 0
                    and getattr(operation, "outbound_telegram_message_id", None) is None):
                return self.repository.schedule_quality_correction(
                    operation.operation_id, owner=self.worker_id,
                    response_payload=durable_plain_data(result),
                    delivery_payload=durable_plain_data(result.delivery_payload or {}),
                    reasons=tuple(sorted(reasons)),
                )
            terminal_reason = (
                "quality_corrective_retry_exhausted:"
                if reasons and reasons.issubset(self.CORRECTABLE_QUALITY_REASONS)
                   and attempt >= 2
                else "quality_blocked_before_delivery:"
            )
            return self.repository.store_suppressed_generation(
                operation.operation_id, owner=self.worker_id,
                response_payload=durable_plain_data(result), response_text=text,
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                delivery_payload=durable_plain_data(result.delivery_payload or {}),
                reason=terminal_reason + ",".join(gate.reasons),
                conversation_thread_id=result.diagnostic_metadata.get("conversation_thread_id"))
        payload = durable_plain_data(result)
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
                delivery_payload=durable_plain_data(
                    result.delivery_payload or {}
                ),
                reason=f"intentional_suppression:{reason}",
                conversation_thread_id=thread_id,
            )
        if not text.strip():
            # An unblocked empty candidate is a generation failure, never a
            # send-ready ordinary reply.  This keeps durable state truthful and
            # allows the existing retry/idempotency path to recover it.
            return self.repository.fail_empty_generation(
                operation.operation_id, owner=self.worker_id,
                reason="EmptyOrdinaryReply: unblocked generation produced no text",
            )
        return self.repository.store_generated(operation.operation_id, owner=self.worker_id,
            response_payload=payload,response_text=text,
            content_sha256=content_sha256,
            delivery_payload=durable_plain_data(result.delivery_payload or {}),
            conversation_thread_id=thread_id)

    def generation_failed(self, operation, error):
        return self.repository.fail_generation(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}")

    def exception_fallback(self, operation, payload, error):
        """Return bounded customer-safe copy for a definitive pre-send engine failure."""
        from app.models.telegram_inbound import TelegramInboundResult
        fallback = "I hit a snag answering that properly—give me a moment and try me again."
        return TelegramInboundResult(
            correlation_id=operation.correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=f"telegram:{payload.telegram_user_id}",
            response_text=fallback, offer_authorized=False, offer_link=None,
            blocked=False, error_code=None, delivery_payload={},
            diagnostic_metadata={"generation_fallback": {
                "applied": True, "reason": "DECISION_ENGINE_EXCEPTION",
                "errorType": type(error).__name__,
                "authority": "OrdinaryChatReplyService",
            }},
        )

    def result(self, operation):
        return TelegramInboundResult(**dict(operation.response_payload)) if operation.response_payload else None

    def suppress_commercial(self, operation):
        return self.repository.suppress(operation.operation_id,
            reason="commercial_delivery_namespace")

    def suppress_relationship_control(self, operation):
        return self.repository.suppress(operation.operation_id,
            reason="RELATIONSHIP_HUMAN_OPERATOR_ACTIVE")

    def suppress_ignored(self, operation):
        return self.repository.suppress(operation.operation_id,
            reason="RELATIONSHIP_IGNORED")

    def relationship_ignored(self, operation):
        from app.services.telegram_relationship_control_service import TelegramRelationshipControlService
        if not self.creator_profile_id or not self.fanvue_account_id:
            return False
        control = TelegramRelationshipControlService().get(
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            telegram_chat_id=operation.telegram_chat_id)
        return control.ignored

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
            response_payload=durable_plain_data(result),
            delivery_payload=durable_plain_data(result.delivery_payload or {}),
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
            quality_correction_context=dict(
                dict(operation.delivery_payload or {}).get(
                    "qualityCorrectiveRetry"
                ) or {}
            ),
        )

    def commercial_bootstrap_failed(self, operation, error):
        return self.repository.fail_generated_before_send(
            operation.operation_id,
            reason=f"commercial_bootstrap:{type(error).__name__}: {str(error)[:850]}",
        )

    def claim_send(self, operation):
        return self.repository.claim_send(operation.operation_id, owner=self.worker_id)

    def suppress_if_stale(self, operation):
        if self.repository.has_newer_unresolved_inbound(operation.operation_id):
            return self.repository.suppress(
                operation.operation_id, reason="stale_response_suppressed_before_send",
            )
        return None

    def confirmed(self, operation, telegram_message_id):
        if telegram_message_id is None:
            return self.uncertain(operation, ConnectionError(
                "Telegram acceptance lacked a provider message ID"))
        confirmed = self.repository.confirm_sent(
            operation.operation_id, owner=self.worker_id,
            telegram_message_id=int(telegram_message_id),
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            resource_classification=self._resource_classification(operation),
        )
        if confirmed is not None:
            self._finalize_confirmed_image_boundary(confirmed)
            self._finalize_confirmed_supporter_boundary(
                confirmed, telegram_message_id=int(telegram_message_id),
            )
            self._finalize_confirmed_tease_progression(confirmed)
            self._finalize_confirmed_session_proposal(
                confirmed, telegram_message_id=int(telegram_message_id),
            )
        return confirmed

    @staticmethod
    def _resource_classification(operation):
        diagnostics = dict(dict(getattr(operation, "response_payload", None) or {}).get(
            "diagnostic_metadata") or {})
        visual = dict(diagnostics.get("current_turn_visual_context") or {})
        excluded = bool(
            diagnostics.get("commercial_tease_delivery_pending_confirmation")
            or diagnostics.get("session_proposal_delivery_pending_confirmation")
            or diagnostics.get("pending_sales_progression")
            or diagnostics.get("pending_session_proposal")
            or visual.get("response_policy") in {
                "POLITE_EXPLICIT_BOUNDARY", "FIRM_EXPLICIT_BOUNDARY",
                "AMBIGUOUS_VISUAL_FALLBACK", "SAFETY_ACKNOWLEDGEMENT",
            }
        )
        return "EXCLUDED_NONORDINARY" if excluded else "ORDINARY_NONCOMMERCIAL"

    def finalize_confirmed(self, operation):
        if operation.state is not OrdinaryChatReplyState.SENT_CONFIRMED:
            return operation
        self._finalize_confirmed_image_boundary(operation)
        return operation

    def _finalize_confirmed_image_boundary(self,operation):
        diagnostics=dict(dict(operation.response_payload or {}).get(
            'diagnostic_metadata') or {})
        context=dict(diagnostics.get('current_turn_visual_context') or {})
        policy=str(context.get('response_policy') or '')
        if policy not in {'POLITE_EXPLICIT_BOUNDARY','FIRM_EXPLICIT_BOUNDARY'}:
            return
        required=('operation_id','creator_profile_id','fanvue_account_id','telegram_user_id')
        if not all(context.get(key) is not None for key in required):
            raise RuntimeError('Confirmed image boundary is missing media scope')
        if self._image_boundary_repository is None:
            from app.repositories.customer_inbound_image_safety_repository import CustomerInboundImageSafetyRepository
            self._image_boundary_repository=CustomerInboundImageSafetyRepository()
        self._image_boundary_repository.record_boundary_delivered(
            operation_id=context['operation_id'],
            creator_profile_id=int(context['creator_profile_id']),
            fanvue_account_id=int(context['fanvue_account_id']),
            telegram_user_id=int(context['telegram_user_id']),policy=policy,
            delivered_at=operation.sent_confirmed_at,
        )

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

    def defer_for_availability(self, operation, decision):
        return self.repository.defer_for_availability(
            operation.operation_id, available_at=decision.available_at,
            diagnostics=decision.diagnostics(),
        )

    def suppress_historical_retryable(self, operation, *, reason, disposition_at):
        return self.repository.suppress_historical_retryable(
            operation.operation_id, reason=reason, disposition_at=disposition_at,
        )

    def due_availability_payloads(self, *, now):
        operations = self.repository.release_due_availability(
            account_scope=self.ACCOUNT_SCOPE, now=now,
        )
        tier_reader = getattr(self.repository, "market_tier_priority_buckets", None)
        if (callable(tier_reader) and self.creator_profile_id is not None
                and self.fanvue_account_id is not None):
            buckets = tier_reader(operations,
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id)
        else:
            priority_reader = getattr(self.repository, "high_value_priority_keys", None)
            priority = priority_reader(operations) if callable(priority_reader) else set()
            buckets = {key: 0 for key in priority}
        # Ranking changes preference only after eligibility. Every due operation
        # remains in this batch and due/inbound order is stable within a bucket.
        operations.sort(key=lambda item: (
            buckets.get((int(item.inbound_sender_telegram_user_id),
                         int(item.telegram_chat_id)), 3),
            item.inbound_received_at, item.inbound_telegram_message_id,
        ))
        from dataclasses import replace
        payloads = []
        for item in operations:
            projection = None
            recorder = getattr(self.repository,
                "record_pre_generation_commercial_decision", None)
            if (callable(recorder) and self.creator_profile_id is not None
                    and self.fanvue_account_id is not None):
                if self._pre_generation_commercial is None:
                    from app.services.pre_generation_commercial_decision_service import PreGenerationCommercialDecisionService
                    self._pre_generation_commercial = PreGenerationCommercialDecisionService()
                projection = self._pre_generation_commercial.project(
                    customer_text=getattr(item, "inbound_message_text", ""),
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id,
                    telegram_user_id=item.inbound_sender_telegram_user_id)
                recorder(item.operation_id, projection.diagnostics())
                if self._market_resource_gate is None:
                    from app.services.market_tier_resource_gate_service import MarketTierResourceGateService
                    self._market_resource_gate=MarketTierResourceGateService()
                buyer=self.repository.buyer_attention_context(
                    telegram_user_id=item.inbound_sender_telegram_user_id)
                profile=self.relationship_scheduling_profile(
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id,
                    telegram_user_id=item.inbound_sender_telegram_user_id,
                    telegram_chat_id=item.telegram_chat_id)
                gate=self._market_resource_gate.evaluate(
                    operation_id=item.operation_id,commercial_decision=projection,
                    verified_buyer=bool(buyer.get('verified_buyer')),
                    high_value_prospect=profile['high_value_prospect'],
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id,
                    telegram_user_id=item.inbound_sender_telegram_user_id,
                    telegram_chat_id=item.telegram_chat_id)
                if not gate.allowed:
                    self.repository.suppress_for_market_limit(item.operation_id,
                        reason=gate.reason,evidence=gate.evidence)
                    continue
            payload = self.retry_payload(item)
            burst = self.repository.coalesced_burst_messages(item, now=now)
            buyer=self.repository.buyer_attention_context(
                telegram_user_id=item.inbound_sender_telegram_user_id)
            attention=self._attention.evaluate(
                self.repository.recent_attention_messages(item), **buyer)
            self.repository.record_attention(item.operation_id,attention.diagnostics())
            if attention.outcome=="NO_RESPONSE_REQUIRED":
                self.repository.suppress(
                    item.operation_id,reason="NO_RESPONSE_REQUIRED")
                continue
            contextual = [
                {"role": "user", "content": entry["text"],
                 "telegram_message_id": entry["message_id"]}
                for entry in burst
                if entry["message_id"] != item.inbound_telegram_message_id
            ]
            payloads.append(replace(
                payload, chat_history=contextual,
            ))
        return payloads

    def relationship_scheduling_profile(self, *, creator_profile_id,
                                        fanvue_account_id, telegram_user_id,
                                        telegram_chat_id):
        """Read-only relationship resource profile; commercial state is untouched."""
        from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository
        from app.services.relationship_value_override_service import RelationshipValueOverrideService
        scope = dict(creator_profile_id=creator_profile_id,
                     fanvue_account_id=fanvue_account_id,
                     telegram_user_id=telegram_user_id,
                     telegram_chat_id=telegram_chat_id)
        buyer = self.repository.buyer_attention_context(
            telegram_user_id=telegram_user_id)
        verified_buyer = bool(buyer.get("verified_buyer"))
        tier = RelationshipMarketTierRepository().active(**scope)
        return {
            "market_tier": (tier.market_tier.value if tier and not verified_buyer
                            else "UNCLASSIFIED"),
            "high_value_prospect": bool(RelationshipValueOverrideService().active(**scope)),
            "verified_buyer": verified_buyer,
        }

    def pending_backlog_payloads(self):
        return [self.retry_payload(item) for item in self.repository.pending_backlog(
            account_scope=self.ACCOUNT_SCOPE)]

    def due_generated_send_payloads(self, *, now):
        return [self.retry_payload(item) for item in
                self.repository.due_generated_send_retries(
                    account_scope=self.ACCOUNT_SCOPE, now=now)]

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

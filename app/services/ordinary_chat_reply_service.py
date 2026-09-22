"""Crash-safe orchestration for non-commercial Telegram text replies."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.services.contextual_customer_tone_service import ContextualCustomerToneService


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
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise TypeError("Non-finite Decimal is not a durable numeric value")
        # Exact base-10 text preserves precision and scale; never round via float.
        # Snapshot prompts already consume numeric memory as text.
        return str(value)
    if isinstance(value, (datetime, date, time)):
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
        "FINAL_TURN_OBLIGATION_FAILURE",
        "FINAL_REPETITION_FAILURE", "MANUFACTURED_ENGAGEMENT_QUESTION",
        "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION",
        "UNNECESSARY_POLICY_NARRATION",
    })
    COMMERCIAL_AUTHORITY_CORRECTIVE_REASON = (
        "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY"
    )

    @classmethod
    def _has_durable_ordinary_obligation(cls, operation) -> bool:
        from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService
        return OrdinaryResponseObligationService.decide(operation)['required']

    @classmethod
    def _corrective_reasons_allowed(cls, operation, reasons, *, obligation=None) -> bool:
        reasons = frozenset(str(item) for item in reasons if str(item).strip())
        allowed = cls.CORRECTABLE_QUALITY_REASONS | {
            cls.COMMERCIAL_AUTHORITY_CORRECTIVE_REASON
        }
        from app.services.ordinary_quality_rejection import PROGRESSION_REASONS
        allowed = allowed | PROGRESSION_REASONS
        if not reasons or not reasons.issubset(allowed):
            return False
        return bool(obligation['required']) if obligation is not None else cls._has_durable_ordinary_obligation(operation)

    @staticmethod
    def _remove_denied_optional_nudge_authority(projection):
        """Keep ordinary chat alive when only an optional offer nudge is denied."""
        optional_denial = bool(
            projection.active_offer_nudge_candidate
            and not projection.active_offer_reservation_authorized
            and not projection.fresh_direct_intent
            and not projection.current_commercial_interest
            and str(projection.commercial_interest_type or "NONE") == "NONE"
        )
        if not optional_denial:
            return projection, False
        return replace(
            projection,
            active_offer_nudge_candidate=False,
            active_offer_reservation_reason=(
                "OPTIONAL_NUDGE_AUTHORITY_DENIED_FALLTHROUGH"
            ),
        ), True

    def __init__(self, *, repository=None, worker_id=None,
                 prospect_service=None, sales_session_service=None,
                 image_boundary_repository=None, delivery_quality_gate=None,
                 attention_service=None, creator_profile_id=None,
                 fanvue_account_id=None, pre_generation_commercial=None,
                 market_resource_gate=None, post_nudge_nonconversion=None,
                 effective_permissions=None, post_nudge_conversation_policy=None, generation_authorizer=None):
        self.repository = repository or OrdinaryChatReplyRepository()
        self.worker_id = worker_id or f"ordinary-reply-{uuid4()}"
        self.creator_profile_id = creator_profile_id
        self.fanvue_account_id = fanvue_account_id
        self._pre_generation_commercial = pre_generation_commercial
        self._market_resource_gate = market_resource_gate
        self._post_nudge_nonconversion=post_nudge_nonconversion
        self._post_nudge_conversation_policy=post_nudge_conversation_policy
        self._effective_permissions=effective_permissions
        self._generation_authorizer=generation_authorizer
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
        from app.services.english_only_conversation_policy import EnglishOnlyConversationPolicy
        self._english_only=EnglishOnlyConversationPolicy()

    def begin(self, payload):
        bound_operation_id = getattr(payload, "ordinary_reply_operation_id", None)
        if bound_operation_id:
            operation = self.repository.get(bound_operation_id)
            if operation is None:
                raise LookupError("Bound ordinary-reply operation was not found.")
            if (
                operation.telegram_account_scope != self.ACCOUNT_SCOPE
                or int(operation.telegram_chat_id) != int(payload.telegram_chat_id)
                or int(operation.inbound_sender_telegram_user_id)
                    != int(payload.telegram_user_id)
                or int(operation.inbound_telegram_message_id) != int(payload.message_id)
                or str(operation.inbound_message_text or "")
                    != str(payload.message_text or "")
            ):
                raise PermissionError(
                    "Bound ordinary-reply operation does not match the inbound identity."
                )
            return operation, False
        correlation = f"ordinary_reply:{self.ACCOUNT_SCOPE}:{payload.telegram_chat_id}:{payload.message_id}"
        from app.services.gpt_service import GPTService
        return self.repository.get_or_create(account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(payload.telegram_chat_id), inbound_message_id=int(payload.message_id),
            sender_user_id=int(payload.telegram_user_id), correlation_id=correlation,
            inbound_message_text=payload.message_text,
            inbound_received_at=payload.received_at,
            turn_obligations=GPTService.authoritative_turn_obligations(
                payload.message_text or "", new_relationship=False,
            ))

    def claim_generation(self, operation):
        return self.repository.claim_generation(operation.operation_id, owner=self.worker_id)

    def defer_if_global_delivery_prohibited(self, operation):
        """Return a durable deferral only for deterministic global readiness."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            return None
        permissions = self._effective_permissions
        if permissions is None:
            from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
            permissions = CustomerEffectivePermissionsService()
            self._effective_permissions = permissions
        projection = permissions.read(
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_user_id=int(operation.inbound_sender_telegram_user_id),
            telegram_chat_id=int(operation.telegram_chat_id),
        )
        effective = dict(projection.get("effective") or {})
        if (effective.get("chatAllowed") is False
                and effective.get("chatReason") == "GLOBAL_AVA_BOT_ATTENTION"):
            return self.repository.defer_for_global_readiness(
                operation.operation_id, reason="GLOBAL_AVA_BOT_ATTENTION")
        return None

    def apply_english_only_policy(self, operation):
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            from app.services.english_only_conversation_policy import (
                EnglishOnlyDisposition,
            )
            assessment = self._english_only.classify(operation.inbound_message_text)
            return EnglishOnlyDisposition("NORMAL_PROCESSING", operation, assessment)
        return self._english_only.evaluate(
            operation, self.repository,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
        )

    def english_only_notice_result(self, operation, payload):
        text = self._english_only.NOTICE_TEXT
        return TelegramInboundResult(
            correlation_id=operation.correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=f"telegram:{payload.telegram_user_id}",
            response_text=text, offer_authorized=False, offer_link=None,
            blocked=False, error_code=None,
            delivery_type="MESSAGE_TEXT", delivery_mode="ENGLISH_ONLY_NOTICE",
            delivery_requires_payment=False,
            delivery_payload={"type": "MESSAGE_TEXT", "message_text": text,
                "englishOnlyConversationPolicy": {"policy": self._english_only.POLICY,
                    "noticeReserved": True, "deterministic": True}},
            diagnostic_metadata={"english_only_conversation_policy": {
                "policy": self._english_only.POLICY, "firstNotice": True,
                "deterministic": True, "providerCalls": 0,
                "salesBrainGenerationCalls": 0}},
        )

    def post_nudge_policy_result(self, operation, payload):
        policy=dict((operation.delivery_payload or {}).get('postNudgeConversationPolicy') or {})
        purpose=str(policy.get('responsePurpose') or '')
        if policy.get('providerAllowed') is not False:return None
        variants={'SUPPORTER_BOUNDARY':("I keep that side of me for the people who support me, but we can still talk normally.","That more intimate side of me is for supporters. I’m still happy to keep things casual with you."),'NONSEXUAL_REDIRECT':("You’re persistent 😄 Let’s keep it nonsexual—how has your day been?","I’m keeping that boundary in place. Tell me what you’ve been up to today instead.")}
        choices=variants.get(purpose)
        if not choices:return None
        text=choices[int(operation.inbound_telegram_message_id)%len(choices)]
        return TelegramInboundResult(correlation_id=operation.correlation_id,telegram_chat_id=payload.telegram_chat_id,telegram_user_id=payload.telegram_user_id,message_id=payload.message_id,engine_user_id=f'telegram:{payload.telegram_user_id}',response_text=text,offer_authorized=False,offer_link=None,blocked=False,error_code=None,delivery_type='MESSAGE_TEXT',delivery_mode=purpose,delivery_requires_payment=False,delivery_payload={'type':'MESSAGE_TEXT','message_text':text},diagnostic_metadata={'post_nudge_conversation_policy':{**policy,'responsePurpose':purpose,'deterministic':True,'providerCalls':0,'sexualOutgoingAllowed':False}})

    def store_english_only_notice(self, operation, result):
        text = str(result.response_text)
        return self.repository.store_english_only_notice(
            operation.operation_id,
            response_payload=durable_plain_data(result), response_text=text,
            content_sha256=hashlib.sha256(text.encode()).hexdigest(),
            delivery_payload=durable_plain_data(result.delivery_payload),
        )

    def validate_follow_through_before_generation(self, operation):
        decision=dict(dict(operation.delivery_payload or {}).get(
            "preGenerationCommercialDecision") or {})
        if not decision.get("active_offer_nudge_candidate"):
            return True
        from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
        valid=ActiveOfferFollowThroughRepository().validate_before_generation(
            operation.operation_id)
        if valid is not None:
            return True
        self.repository.store_suppressed_generation(operation.operation_id,
            owner=self.worker_id,response_payload={},response_text="",
            content_sha256=hashlib.sha256(b"").hexdigest(),delivery_payload={},
            reason="active_offer_reservation_invalidated_before_generation",
            conversation_thread_id=None)
        return False

    def generate(self, operation, payload, *, initial):
        from app.repositories.ordinary_generation_budget_repository import OrdinaryGenerationBudgetRepository
        from app.services.ordinary_reply_generation_service import OrdinaryReplyGenerationService
        return OrdinaryReplyGenerationService(
            OrdinaryGenerationBudgetRepository(self.repository.connection_factory),
            authorize=self._generation_authorizer or self._authorize_generation,
        ).execute(operation, payload, owner=self.worker_id, initial=initial)

    def _authorize_generation(self, operation, diagnostics):
        from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
        from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService
        permissions = self._effective_permissions or CustomerEffectivePermissionsService()
        projection = permissions.read(creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            telegram_chat_id=operation.telegram_chat_id)
        if dict(projection.get('effective') or {}).get('chatAllowed') is not True:
            raise PermissionError('ORDINARY_GENERATION_CURRENT_PERMISSION_DENIED')
        customer = dict(projection.get('identity') or {}).get('localFanvueUserId')
        if customer is not None:
            safety = CustomerInteractionSafetyService().decide(
                creator_profile_id=self.creator_profile_id, fanvue_account_id=self.fanvue_account_id,
                fanvue_user_id=customer)
            if not safety.allowed:
                raise PermissionError(safety.code)
        # Correction is conversation-only. Existing commercial revocation and
        # transport/control guards still run before any send.
        if not self.validate_follow_through_before_generation(operation):
            raise PermissionError('CURRENT_COMMERCIAL_AUTHORITY_REVOKED')

    def generated(self, operation, result):
        from app.services.ordinary_quality_rejection import normalize
        result = normalize(result)
        if (not str(result.response_text or "").strip()
                and str(result.error_code or "").startswith("decision_engine_")):
            failure = dict(dict(result.diagnostic_metadata or {}).get(
                "internal_generation_failure") or {})
            error_type = str(failure.get("errorType") or "UNKNOWN")
            error_type = "".join(
                character for character in error_type
                if character.isalnum() or character in {"_", "."}
            )[:120] or "UNKNOWN"
            return self.repository.fail_generation(
                operation.operation_id, owner=self.worker_id,
                reason=(f"{str(result.error_code).upper()}:{error_type}: "
                        "Automatic reply could not be completed."),
                evidence={"generationFailureDiagnostics": {
                    key: durable_plain_data(value)
                    for key, value in dict(result.diagnostic_metadata or {}).items()
                    if key in {
                        "currentTurnSemanticClassification",
                        "conversationProgressionFailure",
                    }
                }},
            )
        elif not str(result.response_text or "").strip() and result.blocked is not True:
            return self.repository.fail_empty_generation(
                operation.operation_id, owner=self.worker_id,
                reason="EMPTY_GENERATION: Automatic reply could not be completed.",
            )
        from app.services.recovery_execution_constraint_service import (
            RecoveryExecutionConstraintService,
        )
        constraint_allowed, constraint_reason = (
            RecoveryExecutionConstraintService.validate_result(operation, result))
        if not constraint_allowed:
            return self.repository.store_suppressed_generation(
                operation.operation_id, owner=self.worker_id,
                response_payload=durable_plain_data(result),
                response_text=str(result.response_text or ""),
                content_sha256=hashlib.sha256(
                    str(result.response_text or "").encode()).hexdigest(),
                delivery_payload=self._durable_delivery_payload(operation, result),
                reason=f"recovery_execution_constraint_violation:{constraint_reason}",
                conversation_thread_id=None,
            )
        diagnostics = dict(result.diagnostic_metadata or {})
        if dict(getattr(operation, 'delivery_payload', None) or {}).get('controlledFreshResponse'):
            from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService
            if 'ACKNOWLEDGE_SELF_PHOTO' not in OrdinaryResponseObligationService.decide(operation, diagnostics)['obligations']:
                return self.repository.fail_generation(operation.operation_id, owner=self.worker_id,
                    reason='SELF_PHOTO_EVIDENCE_NOT_ESTABLISHED')
        delivery = dict(result.delivery_payload or {})
        # Commercial media is never authorized by the generated payload itself.
        # The durable, current-turn pre-generation decision is the authority.
        # This prevents stale/historical offer payloads (or a model-produced
        # unlock button) from crossing into the commercial transport.
        decision = dict((getattr(operation, "delivery_payload", None) or {}).get(
            "preGenerationCommercialDecision") or {})
        private_button = dict(delivery.get("private_chat_unlock_button") or {})
        commercial_media = bool(
            getattr(result, "delivery_requires_payment", False)
            or private_button
            or (delivery.get("asset_path") and (
                delivery.get("delivery_requires_payment") is True
                or delivery.get("requires_payment") is True
            ))
        )
        commercial_authorized = bool(
            decision.get("commercial_bypass_eligible") is True
            or decision.get("active_offer_reservation_authorized") is True
        )
        if commercial_media and not commercial_authorized:
            reasons = list(diagnostics.get("conversationQualityReasons") or ())
            if "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY" not in reasons:
                reasons.append("COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY")
            diagnostics["conversationQualityReasons"] = reasons
            diagnostics["commercialMediaAuthorityGate"] = {
                "authority": "PRE_GENERATION_COMMERCIAL_DECISION",
                "authorized": False,
                "reason": "NO_CURRENT_DETERMINISTIC_COMMERCIAL_AUTHORITY",
            }
        delivered_text = str(delivery.get("message_text") or "")
        if delivered_text.strip() and delivered_text != str(result.response_text or ""):
            diagnostics["customerVisibleTextNormalization"] = {
                "authority": "DELIVERY_PAYLOAD_MESSAGE_TEXT",
                "normalized": True,
            }
            result = replace(result, response_text=delivered_text)
        try:
            recent = self.repository.recent_ava_responses(operation)
        except (AttributeError, TypeError):
            recent = diagnostics.get("recentAvaResponses") or ()
        if not isinstance(recent, (list, tuple)):
            recent = diagnostics.get("recentAvaResponses") or ()
        post_nudge = dict((getattr(operation, "delivery_payload", None) or {}).get(
            "postNudgeConversationPolicy") or {})
        if (post_nudge.get("active") is True
                and post_nudge.get("sexualAccessGated") is True
                and post_nudge.get("commercialReentry") is not True):
            purpose = str(post_nudge.get("responsePurpose") or "")
            candidate_lower = str(result.response_text or "").lower()
            outgoing_tone = ContextualCustomerToneService().classify(
                message=str(result.response_text or ""))
            if (outgoing_tone.get("sexualOrProvocative") is True
                    or self._natural_conversation.SEXUAL_ELABORATION.search(
                        str(result.response_text or ""))
                    or (purpose == "ACTIVE_PRESENTATION_BRIDGE" and any(
                        token in candidate_lower for token in (
                            "supporter", "unlock", "buy it", "send the link",
                        )
                    ))):
                if purpose == "ACTIVE_PRESENTATION_BRIDGE":
                    variants = (
                        "Someone's imagination is working overtime today 😏",
                        "You're definitely feeling bold today 😏",
                        "You really know how to turn up the heat 😄",
                    )
                    recent_text = {str(item).strip().lower() for item in recent} \
                        if isinstance(recent, (list, tuple)) else set()
                    offset = int(operation.inbound_telegram_message_id) % len(variants)
                    ordered = variants[offset:] + variants[:offset]
                    replacement = next((item for item in ordered
                        if item.lower() not in recent_text), ordered[0])
                else:
                    replacement = (
                    "I'm keeping that boundary in place, but we can still talk normally."
                    if purpose in {"SUPPORTER_BOUNDARY", "NONSEXUAL_REDIRECT"}
                    else "I'm keeping things casual here. How has your day been?"
                    )
                delivery = dict(result.delivery_payload or {})
                if delivery.get("type") == "MESSAGE_TEXT":
                    delivery["message_text"] = replacement
                diagnostics["postNudgeConversationQualityGate"] = {
                    "authority": "PostNudgeConversationPolicyService",
                    "disposition": "REPAIRED_BEFORE_DELIVERY",
                    "reason": "SEXUAL_ACCESS_GATED",
                    "responsePurpose": purpose,
                    "bridgeConversationalFunction": post_nudge.get(
                        "bridgeConversationalFunction"
                    ),
                }
                result = replace(result, response_text=replacement,
                                 delivery_payload=delivery)
        if post_nudge.get("activePresentationBridge") is True:
            diagnostics["activePresentationBridge"] = {
                key: post_nudge.get(key) for key in (
                    "activePresentationBridge", "activePresentationId",
                    "activePresentationState", "activePresentationBridgeReason",
                    "sexualSignalClass", "bridgeConversationalFunction",
                    "commercialSignalOverride", "supporterBoundaryEligible",
                    "supporterBoundarySuppressionReason",
                )
            }
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
        from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService
        diagnostics['conversationStyle'] = OrdinaryResponseObligationService.validate_self_photo(
            diagnostics.get('conversationStyle') or {}, result.response_text,
            OrdinaryResponseObligationService.decide(operation, diagnostics))
        result = replace(result, diagnostic_metadata=diagnostics)
        gate = self._delivery_quality_gate.evaluate(
            result,
            customer_text=str(getattr(operation, "inbound_message_text", "") or ""),
            recent_context=diagnostics.get("immediatelyRelevantConversationContext") or (),
        )
        offline_validation = dict(
            result.diagnostic_metadata.get("offlineAccessValidation") or {}
        )
        offline_validation["correctiveAttempt"] = int(
            getattr(operation, "generation_attempt_count", 1) or 1
        )
        result.diagnostic_metadata["offlineAccessValidation"] = offline_validation
        result.diagnostic_metadata["delivery_quality_gate"] = {
            "authority": "OrdinaryReplyDeliveryQualityGate", "disposition": gate.disposition,
            "blockingReasons": list(gate.reasons),
        }
        style = dict(result.diagnostic_metadata.get("conversationStyle") or {})
        from app.services.ordinary_response_obligation_service import OrdinaryResponseObligationService
        obligation = OrdinaryResponseObligationService.decide(operation, result.diagnostic_metadata)
        result.diagnostic_metadata['ordinaryResponseObligation'] = obligation
        generation_evidence = result.diagnostic_metadata.get('ordinaryGeneration')
        if generation_evidence:
            generation_evidence['finalCandidateDisposition'] = gate.disposition
            generation_evidence['correctionRequested'] = bool(
                generation_evidence.get('correctionRequested') or (
                    not gate.allowed and obligation['required']
                    and generation_evidence['customerFacingCandidates'] == 1
                    and self._corrective_reasons_allowed(operation, gate.reasons, obligation=obligation)))
            if generation_evidence['correctionRequested']:
                generation_evidence['correctionReasons'] = list(gate.reasons)
        if result.diagnostic_metadata.get('ordinaryGeneration'):
            from app.repositories.ordinary_generation_budget_repository import OrdinaryGenerationBudgetRepository
            OrdinaryGenerationBudgetRepository(self.repository.connection_factory).save(
                operation.operation_id, self.worker_id, result=durable_plain_data(result), obligation=obligation,
                event={'kind': 'FINAL_DISPOSITION', 'disposition': gate.disposition,
                       'reasons': list(gate.reasons), 'correctionRequested': generation_evidence['correctionRequested'],
                       'candidateNumber': generation_evidence['customerFacingCandidates']})
        recorder = getattr(self.repository, "record_generation_attempt", None)
        if recorder is not None:
            recorder(
                operation,
                provider=(result.diagnostic_metadata.get("selected_provider")
                          or dict(result.diagnostic_metadata.get("provider_preview") or {}).get("selected_provider")
                          or result.diagnostic_metadata.get("provider")),
                candidate_text=str(result.response_text or ""),
                quality_disposition=(
                    "ALLOWED_BEFORE_DELIVERY" if gate.allowed
                    else "BLOCKED_BEFORE_DELIVERY"
                ),
                quality_reasons=gate.reasons,
                turn_obligations=style.get("turnObligations") or (),
                satisfied_obligations=style.get("satisfiedTurnObligations") or (),
                unsatisfied_obligations=style.get("unsatisfiedTurnObligations") or (),
                repair_outcome=(style.get("combinedObligationRepairOutcome")
                                or style.get("styleRewriteOutcome")),
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id,
            )
        if not gate.allowed:
            result.diagnostic_metadata["conversationQualityDisposition"] = "BLOCKED_BEFORE_DELIVERY"
            text = str(result.response_text or "")
            reasons = frozenset(gate.reasons)
            attempt = int(dict(result.diagnostic_metadata.get('ordinaryGeneration') or {}).get(
                'customerFacingCandidates') or getattr(operation, "generation_attempt_count", 1) or 1)
            existing_correction = dict(
                dict(getattr(operation, "delivery_payload", None) or {}).get(
                    "qualityCorrectiveRetry"
                ) or {}
            )
            corrective_allowed = self._corrective_reasons_allowed(operation, reasons, obligation=obligation)
            if (corrective_allowed
                    and attempt == 1
                    and existing_correction.get("required") is not True
                    and int(getattr(operation, "send_attempt_count", 0) or 0) == 0
                    and getattr(operation, "outbound_telegram_message_id", None) is None):
                return self.repository.schedule_quality_correction(
                    operation.operation_id, owner=self.worker_id,
                    response_payload=durable_plain_data(result),
                    delivery_payload=self._durable_delivery_payload(operation, result),
                    reasons=tuple(sorted(reasons)),
                    recent_ava_responses=tuple(str(item) for item in recent),
                )
            terminal_reason = (
                "quality_corrective_retry_exhausted:"
                if corrective_allowed
                   and attempt >= 2
                else "quality_blocked_before_delivery:"
            )
            return self.repository.store_suppressed_generation(
                operation.operation_id, owner=self.worker_id,
                response_payload=durable_plain_data(result), response_text=text,
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                delivery_payload=self._durable_delivery_payload(operation, result),
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
                delivery_payload=self._durable_delivery_payload(operation, result),
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
            delivery_payload=self._durable_delivery_payload(operation, result),
            conversation_thread_id=thread_id)

    @staticmethod
    def _durable_delivery_payload(operation, result):
        """Preserve immutable recovery authority across every lifecycle write."""
        delivery = durable_plain_data(result.delivery_payload or {})
        existing = dict(getattr(operation, "delivery_payload", None) or {})
        for key in (
            "attentionInvestment", "qualityFailureRecoveryHistory",
            "approvedHistoricalCorrection", "canonicalNotDeliveredCorrection",
            "qualityCorrectiveRetry", "recoveryExecutionConstraint",
        ):
            if key in existing:
                delivery[key] = durable_plain_data(existing[key])
        return delivery

    def generation_failed(self, operation, error):
        return self.repository.fail_generation(operation.operation_id, owner=self.worker_id,
            reason=f"GENERATION_FAILURE:{type(error).__name__}: {str(error)[:850]}",
            evidence={'generationFailurePolicy': {'version': 'ORDINARY_RECOVERY_V1',
                'fullPipelineRetry': False, 'errorType': type(error).__name__}})

    def exception_fallback(self, operation, payload, error):
        """Represent an internal engine failure structurally; never as Ava dialogue."""
        from app.models.telegram_inbound import TelegramInboundResult
        return TelegramInboundResult(
            correlation_id=operation.correlation_id,
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=f"telegram:{payload.telegram_user_id}",
            response_text="", offer_authorized=False, offer_link=None,
            blocked=True, error_code="internal_generation_failure", delivery_payload={},
            diagnostic_metadata={"internal_generation_failure": {
                "customerVisible": False, "reason": "DECISION_ENGINE_EXCEPTION",
                "errorType": type(error).__name__,
                "authority": "OrdinaryChatReplyService",
            }},
        )

    def authorize_customer_visible_delivery(self, operation) -> bool:
        """Final affirmative authorization for an ordinary customer-visible payload."""
        text = str(getattr(operation, "response_text", "") or "").strip()
        payload = dict(getattr(operation, "response_payload", None) or {})
        diagnostics = dict(payload.get("diagnostic_metadata") or {})
        delivery = dict(getattr(operation, "delivery_payload", None) or {})
        quality = dict(diagnostics.get("delivery_quality_gate") or {})
        deterministic = bool(
            diagnostics.get("english_only_conversation_policy")
            or diagnostics.get("post_nudge_conversation_policy")
        )
        from app.services.recovery_execution_constraint_service import (
            RecoveryExecutionConstraintService,
        )
        constraint_allowed, _ = (
            RecoveryExecutionConstraintService.validate_persisted_delivery(operation))
        from types import SimpleNamespace
        final_text = str(delivery.get("message_text") or text).strip()
        final_gate = self._delivery_quality_gate.evaluate(
            SimpleNamespace(
                response_text=final_text,
                diagnostic_metadata=diagnostics,
                error_code=payload.get("error_code"),
            ),
            customer_text=str(getattr(operation, "inbound_message_text", "") or ""),
        )
        payload_text = str(delivery.get("message_text") or text).strip()
        authorized = bool(
            text and not payload.get("error_code")
            and not diagnostics.get("generation_fallback")
            and not diagnostics.get("internal_generation_failure")
            and str(diagnostics.get("status") or "").lower() != "engine_exception"
            and (quality.get("disposition") == "ALLOWED" or deterministic)
            and payload_text == text
            and constraint_allowed
            and final_gate.allowed
        )
        if authorized:
            return True
        deterministic_reason = None
        if text and payload_text != text:
            deterministic_reason = "IMMUTABLE_DELIVERY_PAYLOAD_TEXT_MISMATCH"
        elif not text:
            deterministic_reason = "IMMUTABLE_EMPTY_AUTHORITATIVE_RESPONSE"
        elif payload.get("error_code"):
            deterministic_reason = "PERSISTED_RESPONSE_ERROR_NOT_DELIVERABLE"
        elif (diagnostics.get("generation_fallback")
              or diagnostics.get("internal_generation_failure")
              or str(diagnostics.get("status") or "").lower() == "engine_exception"):
            deterministic_reason = "PERSISTED_INTERNAL_RESPONSE_NOT_DELIVERABLE"
        elif not constraint_allowed:
            deterministic_reason = "PERSISTED_RECOVERY_CONSTRAINT_NOT_AUTHORIZED"
        elif not final_gate.allowed:
            deterministic_reason = "PERSISTED_FINAL_QUALITY_NOT_AUTHORIZED"
        if deterministic_reason:
            terminalize = getattr(
                self.repository,
                "terminalize_deterministic_authorization_failure",
                None,
            )
            if callable(terminalize):
                terminalize(operation.operation_id, reason=deterministic_reason)
                return False
        self.repository.fail_generated_before_send(
            operation.operation_id,
            reason="customer_visible_payload_not_affirmatively_authorized",
        )
        return False

    def result(self, operation):
        return TelegramInboundResult(**dict(operation.response_payload)) if operation.response_payload else None

    def suppress_commercial(self, operation):
        return self.repository.suppress(operation.operation_id,
            reason="commercial_delivery_namespace")

    def invalidate_commercial_authority(
        self, *, operation_id, inbound_message_id, purchase_intent_id,
        revalidation_evidence,
    ):
        """Retire only an unsent persisted offer explicitly denied now."""
        return self.repository.invalidate_commercial_authority(
            operation_id=operation_id,
            inbound_message_id=inbound_message_id,
            purchase_intent_id=purchase_intent_id,
            revalidation_evidence=revalidation_evidence,
        )

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

    def recover_denied_optional_active_offer(self, operation):
        """Authorize only the bounded historical optional-nudge recovery."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            raise ValueError("Creator/account scope is required for recovery.")
        from app.services.global_automation_safety_service import GlobalAutomationSafetyService
        safety_service = GlobalAutomationSafetyService()
        safety_service.refresh()
        safety = safety_service.check_global_safety()
        permissions = self._effective_permissions
        if permissions is None:
            from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
            permissions = CustomerEffectivePermissionsService()
            self._effective_permissions = permissions
        projection = permissions.read(
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_user_id=int(operation.inbound_sender_telegram_user_id),
            telegram_chat_id=int(operation.telegram_chat_id),
        )
        effective = dict(projection.get("effective") or {})
        communication = dict(projection.get("communication") or {})
        authorized = bool(
            safety.get("allowed") is True
            and effective.get("chatAllowed") is True
            and communication.get("ignored") is not True
            and communication.get("disposition", "ACTIVE") == "ACTIVE"
        )
        return self.repository.recover_denied_optional_active_offer(
            operation_id=operation.operation_id,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            global_reply_authorized=authorized,
            safety_authorized=authorized,
        )

    def retry_payload(self, operation):
        """Reconstruct the original normalized inbound for a durable retry."""
        from app.models.telegram_inbound import TelegramInboundPayload
        delivery = dict(operation.delivery_payload or {})
        correction = dict(delivery.get("qualityCorrectiveRetry") or {})
        commercial_decision = dict(
            delivery.get("preGenerationCommercialDecision") or {}
        )
        if commercial_decision:
            correction["preGenerationCommercialDecision"] = commercial_decision
        availability = dict(delivery.get("availability") or {})
        peak_engagement = dict(availability.get("peakEngagement") or {})
        if peak_engagement:
            # Consume the exact durable Phase 1 decision. Generation must not
            # independently recalculate clocks, windows, grace, or eligibility.
            correction["peakEngagement"] = peak_engagement
        from app.services.recovery_execution_constraint_service import (
            RecoveryExecutionConstraintService,
        )
        if RecoveryExecutionConstraintService.constrained(operation):
            correction = RecoveryExecutionConstraintService.apply_generation_context(
                correction)
        bridge = dict(delivery.get("postNudgeConversationPolicy") or {})
        if bridge.get("activePresentationBridge") is True:
            correction["activePresentationBridge"] = bridge
        elif bridge.get("nonconversionScope") == "PRESENTATION_SPECIFIC":
            correction["postPpvNonconversionConversation"] = bridge
        reconciliation = dict(delivery.get("historicalSurvivorReconciliation") or {})
        if reconciliation.get("disposition") == "CURRENT_OBLIGATION_SURVIVES":
            correction["historicalSurvivorReconciliation"] = reconciliation
            correction["excludedExactResponses"] = list(dict.fromkeys((
                *(correction.get("excludedExactResponses") or ()),
                *(reconciliation.get("excludedExactResponses") or ()),
            )))[:7]
        if getattr(operation, "conversation_burst_id", None) is not None:
            correction["conversationBurst"] = {
                "burstId": str(operation.conversation_burst_id),
                "survivorOperationId": str(
                    getattr(operation, "burst_survivor_operation_id", None)
                    or operation.operation_id
                ),
                "freshnessMessageId": int(
                    getattr(operation, "burst_freshness_telegram_message_id", None)
                    or operation.inbound_telegram_message_id
                ),
                "obligations": list(
                    getattr(operation, "burst_obligations", None) or ()
                ),
            }
        from app.models.telegram_media_turn_input import TelegramMediaTurnInput
        visual = dict(delivery.get('current_turn_visual_context') or {})
        media_input = (TelegramMediaTurnInput.from_context(visual,
            operation_id=operation.operation_id,
            user_id=operation.inbound_sender_telegram_user_id,
            chat_id=operation.telegram_chat_id,
            message_id=operation.inbound_telegram_message_id)
            if visual.get('turn_authority') else None)
        return TelegramInboundPayload(
            media_turn_input=media_input,
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            telegram_chat_id=operation.telegram_chat_id,
            message_text=operation.inbound_message_text or "",
            message_id=operation.inbound_telegram_message_id,
            received_at=operation.inbound_received_at,
            quality_correction_context=correction,
            current_turn_visual_context=dict(delivery.get('current_turn_visual_context') or {}),
            ordinary_reply_operation_id=str(operation.operation_id),
        )

    @staticmethod
    def purchase_intent_allowed(operation) -> bool:
        from app.services.recovery_execution_constraint_service import (
            RecoveryExecutionConstraintService,
        )
        return not RecoveryExecutionConstraintService.constrained(operation)

    def commercial_bootstrap_failed(self, operation, error):
        return self.repository.fail_generated_before_send(
            operation.operation_id,
            reason=f"commercial_bootstrap:{type(error).__name__}: {str(error)[:850]}",
        )

    def claim_send(self, operation):
        return self.repository.claim_send(operation.operation_id, owner=self.worker_id)

    @staticmethod
    def awaiting_scheduled_delivery(operation, *, now):
        """True only for a durably prepared response before its delivery time."""
        return bool(
            operation is not None
            and operation.state is OrdinaryChatReplyState.RETRYABLE
            and operation.response_payload is not None
            and str(operation.response_text or "").strip()
            and operation.last_error == "prepared_for_scheduled_delivery"
            and operation.scheduled_delivery_at is not None
            and operation.next_retry_at == operation.scheduled_delivery_at
            and operation.next_retry_at > now
            and operation.send_attempt_count == 0
            and operation.outbound_telegram_message_id is None
        )

    def suppress_settled_follow_through_before_send(self, operation):
        return self.repository.suppress_settled_follow_through_before_send(
            operation.operation_id)

    def suppress_if_stale(self, operation):
        freshness_reader = getattr(self.repository, "archive_freshness", None)
        freshness = (
            freshness_reader(operation.operation_id)
            if callable(freshness_reader) else None
        )
        stale = (
            not freshness.get("archiveFreshnessSatisfied", False)
            if freshness is not None
            else self.repository.has_newer_unresolved_inbound(
                operation.operation_id)
        )
        if stale:
            return self.repository.suppress(
                operation.operation_id, reason="stale_response_suppressed_before_send",
                **({"evidence": {"archivePreSendFreshness": freshness}}
                   if freshness is not None else {}),
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
            or dict(diagnostics.get("english_only_conversation_policy") or {}).get(
                "firstNotice") is True
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
        certainty = getattr(error, "certainty", None)
        ambiguous = (certainty in {"UNKNOWN", "ACCEPTED"} or (
            certainty is None and not definitive
            and isinstance(error, (TimeoutError, ConnectionError, OSError))))
        if recoverable and certainty not in {"UNKNOWN", "ACCEPTED"}:
            ambiguous = False
        if ambiguous:
            terminal = False
        rejection_evidence = {}
        provider_evidence = getattr(error, "provider_evidence", None)
        if provider_evidence:
            self.repository.record_provider_evidence(operation.operation_id,
                owner=self.worker_id, evidence=dict(provider_evidence))
        if definitive:
            rejection_evidence = {"telegramDefinitiveRejection": {
                "classification": "DEFINITIVE_NOT_DELIVERED",
                "errorType": type(error).__name__,
                "errorCode": str(getattr(error, "code", "") or "") or None,
                "httpStatus": getattr(error, "http_status", None),
                "telegramErrorCode": getattr(error, "telegram_error_code", None),
                "telegramDescription": getattr(error, "telegram_description", None),
                "peerIdInvalid": bool(getattr(error, "peer_id_invalid", False)),
                "automaticRetryAllowed": not terminal,
            }}
        return self.repository.fail_send(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}", ambiguous=ambiguous,
            terminal=terminal, evidence=rejection_evidence)

    def deterministic_delivery_blocked(self, operation, *, reason, metadata=None):
        return self.repository.record_deterministic_delivery_block(
            operation.operation_id, owner=self.worker_id,
            reason=reason, metadata=metadata,
        )

    def uncertain(self, operation, error):
        return self.repository.fail_send(operation.operation_id, owner=self.worker_id,
            reason=f"{type(error).__name__}: {str(error)[:900]}", ambiguous=True)

    def recover_startup(self):
        recovered = list(self.repository.recover_orphaned_sends())
        quarantine = getattr(
            self.repository, "quarantine_legacy_ambiguous_media_retries", None,
        )
        if callable(quarantine):
            recovered.extend(quarantine())
        return recovered

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

    def peak_engagement_context(self, operation):
        """Read stronger authorities before the initial availability decision."""
        latest=self.repository.latest_confirmed_exchange_at(
            account_scope=self.ACCOUNT_SCOPE,
            chat_id=int(operation.telegram_chat_id),
            sender_user_id=int(operation.inbound_sender_telegram_user_id))
        buyer=self.repository.buyer_attention_context(
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id)
        if self._pre_generation_commercial is None:
            from app.services.pre_generation_commercial_decision_service import PreGenerationCommercialDecisionService
            self._pre_generation_commercial=PreGenerationCommercialDecisionService()
        commercial=self._pre_generation_commercial.project(
            customer_text=operation.inbound_message_text or "",
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_user_id=operation.inbound_sender_telegram_user_id)
        return {"confirmed_exchange_at":latest,
            "commercial_authority":bool(commercial.current_commercial_interest
                or commercial.fresh_direct_intent or commercial.active_offer_nudge_candidate),
            "verified_buyer":bool(buyer.get("verified_buyer"))}

    def suppress_historical_retryable(self, operation, *, reason, disposition_at):
        return self.repository.suppress_historical_retryable(
            operation.operation_id, reason=reason, disposition_at=disposition_at,
        )

    def due_availability_payloads(self, *, now):
        operations = self.repository.release_due_availability(
            account_scope=self.ACCOUNT_SCOPE, now=now,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
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
            if (self.creator_profile_id is not None and self.fanvue_account_id is not None):
                if self._post_nudge_nonconversion is None:
                    from app.services.post_nudge_nonconversion_service import PostNudgeNonconversionService
                    self._post_nudge_nonconversion=PostNudgeNonconversionService()
                self._post_nudge_nonconversion.observe(item,
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id)
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
                    telegram_user_id=item.inbound_sender_telegram_user_id,
                    operation_id=item.operation_id)
                projection, _ = self._remove_denied_optional_nudge_authority(
                    projection
                )
                updated = recorder(item.operation_id, projection.diagnostics())
                if updated is not None:
                    item = updated
                if (projection.active_offer_nudge_candidate
                        and not projection.active_offer_reservation_authorized):
                    self.repository.suppress_for_market_limit(item.operation_id,
                        reason="ACTIVE_OFFER_NUDGE_RESERVATION_DENIED",
                        evidence=projection.diagnostics())
                    continue
                if self._post_nudge_conversation_policy is None:
                    from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
                    from app.services.market_tier_reply_accounting_service import MarketTierReplyAccountingService
                    from app.services.post_nudge_conversation_policy_service import PostNudgeConversationPolicyService
                    self._post_nudge_conversation_policy=PostNudgeConversationPolicyService(
                        ledger=ActiveOfferFollowThroughRepository(),operations=self.repository,
                        accounting=MarketTierReplyAccountingService())
                buyer=self.repository.buyer_attention_context(
                    telegram_user_id=item.inbound_sender_telegram_user_id)
                policy=self._post_nudge_conversation_policy.evaluate(
                    operation=item,commercial_decision=projection,
                    verified_buyer=bool(buyer.get('verified_buyer')),
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id)
                recorder_policy=getattr(self.repository,'record_post_nudge_conversation_policy',None)
                if callable(recorder_policy):
                    updated=recorder_policy(item.operation_id,policy.diagnostics())
                    if updated is not None:item=updated
                if policy.suppress_optional_reply:
                    self.repository.suppress_for_market_limit(item.operation_id,
                        reason='POST_NUDGE_TIME_WASTER_DAILY_LIMIT',evidence=policy.diagnostics())
                    continue
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
            coherence = None
            unresolved_reader = getattr(
                self.repository, "immediately_preceding_unresolved_semantics", None
            )
            if callable(unresolved_reader):
                from app.services.conversation_coherence_service import (
                    ConversationCoherenceService,
                )
                antecedent = unresolved_reader(item)
                if antecedent is None:
                    earlier_burst = [
                        entry for entry in burst
                        if entry["message_id"] != item.inbound_telegram_message_id
                    ]
                    if earlier_burst and "?" in earlier_burst[-1]["text"]:
                        antecedent = {
                            "operation_id": earlier_burst[-1]["operation_id"],
                            "inbound_message_text": earlier_burst[-1]["text"],
                            "inbound_received_at": item.inbound_received_at or now,
                            "unsatisfied_obligations": ["ANSWER_DIRECT_QUESTION"],
                        }
                projection = ConversationCoherenceService.resolve(
                    current_text=item.inbound_message_text or "",
                    antecedent=antecedent,
                    now=(item.inbound_received_at or now),
                )
                coherence = projection.diagnostics(
                    operation_id=(str(antecedent["operation_id"])
                                  if antecedent else None),
                )
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
            correction = dict(getattr(payload, "quality_correction_context", {}) or {})
            if coherence and coherence.get("clarificationResolved"):
                correction["conversationCoherence"] = coherence
                payloads.append(replace(
                    payload, chat_history=contextual,
                    quality_correction_context=correction,
                ))
            else:
                payloads.append(replace(payload, chat_history=contextual))
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
            telegram_user_id=telegram_user_id,
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id)
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

    def reclaim_stranded_pending_payloads(self, *, now):
        """Reserve safe live PENDING_GENERATION debt for normal availability."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            return []
        operations = self.repository.reclaim_stranded_pending_generation(
            account_scope=self.ACCOUNT_SCOPE,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            owner=self.worker_id,
            now=now,
        )
        return [self.retry_payload(item) for item in operations]

    def maintain_stranded_lifecycle(self, *, now, limit=25):
        """Run bounded durable maintenance and expose current work for normal routing."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            return {
                "expiredGeneratingFound": 0,
                "expiredGeneratingReclaimed": 0,
                "expiredGeneratingSuperseded": 0,
                "pendingSupersededFinalized": 0,
                "unscheduledRetryableFound": 0,
                "unscheduledRetryableFinalizedOrRescheduled": 0,
                "payloads": [],
            }
        result = self.repository.maintain_stranded_lifecycle(
            account_scope=self.ACCOUNT_SCOPE,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            now=now, limit=limit,
        )
        operations = list(result.pop("reclaimable", ()))
        result["payloads"] = [self.retry_payload(item) for item in operations]
        # Discovery deliberately does not pre-claim.  The routed handler calls
        # the existing atomic claim_generation transition; this diagnostic is
        # the number handed to that single-winner authority.
        result["expiredGeneratingReclaimed"] = len(result["payloads"])
        return result

    def due_generated_send_payloads(self, *, now):
        return [self.retry_payload(item) for item in
                self.repository.due_generated_send_retries(
                    account_scope=self.ACCOUNT_SCOPE, now=now)]

    def recover_stranded_generated(self, *, now):
        """Re-enter only current, definitively-unsent generated work."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            return []
        return self.repository.recover_stranded_generated(
            account_scope=self.ACCOUNT_SCOPE,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            now=now,
        )

    def recover_attested_not_delivered(self, operation):
        """Authorize only same-payload retry after durable NOT_DELIVERED evidence."""
        if self.creator_profile_id is None or self.fanvue_account_id is None:
            raise ValueError("Creator/account scope is required for recovery.")
        from app.services.global_automation_safety_service import GlobalAutomationSafetyService
        safety = GlobalAutomationSafetyService()
        safety.refresh()
        result = safety.check_global_safety()
        if not result.get("allowed", False):
            raise PermissionError("Global automation safety blocks recovery.")
        return self.repository.recover_attested_not_delivered(
            operation_id=operation.operation_id,
            creator_profile_id=self.creator_profile_id,
            fanvue_account_id=self.fanvue_account_id,
            telegram_account_scope=operation.telegram_account_scope,
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            telegram_chat_id=operation.telegram_chat_id,
            inbound_message_id=operation.inbound_telegram_message_id,
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

    def recent_confirmed_events(
        self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
        telegram_chat_id, exclude_inbound_message_id=None, limit=20,
    ):
        operations = self.repository.list_confirmed_recent_for_prospect(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            account_scope=self.ACCOUNT_SCOPE,
            exclude_inbound_message_id=exclude_inbound_message_id,
            limit=max(1, int(limit)),
        )
        events = []
        for operation in operations:
            if (
                operation.state is not OrdinaryChatReplyState.SENT_CONFIRMED
                or operation.outbound_telegram_message_id is None
                or not str(operation.inbound_message_text or "").strip()
                or not str(operation.response_text or "").strip()
            ):
                continue
            operation_id = str(operation.operation_id)
            events.extend(({
                "event_id":f"ordinary:{operation_id}:inbound",
                "occurred_at":operation.inbound_received_at or operation.created_at,
                "telegram_chat_id":int(operation.telegram_chat_id),
                "telegram_message_id":int(operation.inbound_telegram_message_id),
                "role":"user","text":operation.inbound_message_text,
                "origin":"CUSTOMER",
            }, {
                "event_id":f"ordinary:{operation_id}:outbound",
                "occurred_at":operation.sent_confirmed_at or operation.updated_at,
                "telegram_chat_id":int(operation.telegram_chat_id),
                "telegram_message_id":int(operation.outbound_telegram_message_id),
                "role":"assistant","text":operation.response_text,
                "origin":"AI",
            }))
        return events

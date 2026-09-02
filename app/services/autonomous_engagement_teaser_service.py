"""Orchestrates policy -> selector -> intelligence caption -> durable delivery."""
from types import SimpleNamespace
from app.models.free_engagement_teaser import SEND_FREE_ENGAGEMENT_TEASER
from app.services.free_engagement_teaser_caption_service import FreeEngagementTeaserCaptionError
from app.models.customer_contact import ContactPolicyResult, ContactPurpose
from app.services.customer_contact_authority_service import CustomerContactAuthorityService


class AutonomousEngagementTeaserService:
    def __init__(self, *, policy_service, delivery_service, caption_service,
                 policy_repository=None, contact_authority=None):
        self.policy = policy_service
        self.delivery = delivery_service
        self.captions = caption_service
        self.policy_repository = policy_repository or getattr(policy_service, "repository", None)
        self.contact_authority = contact_authority or CustomerContactAuthorityService()

    async def handle_active_inbound(self, *, result, payload, transport,
                                    trigger_type="ACTIVE_INBOUND"):
        metadata = dict(result.diagnostic_metadata or {})
        required = ("creator_profile_id", "fanvue_account_id", "fanvue_user_id",
                    "conversation_thread_id")
        if any(metadata.get(key) is None for key in required):
            return {"status": "SEND_NONE", "reason": "IDENTITY_UNRESOLVED"}
        suppression = self._commercial_suppression(result)
        contact = self.contact_authority.decide(
            purpose=(ContactPurpose.RE_ENGAGEMENT if trigger_type == "SCHEDULED_REENGAGEMENT"
                     else ContactPurpose.FREE_ENGAGEMENT),
            evidence=self._contact_evidence(result),
        )
        metadata["customerContactPolicy"] = dict(contact.to_mapping())
        if contact.result is not ContactPolicyResult.ALLOW:
            return {"status": "SEND_NONE", "reason": contact.reason,
                    "contact_policy": contact}
        decision = self.policy.evaluate(
            creator_profile_id=metadata["creator_profile_id"],
            fanvue_account_id=metadata["fanvue_account_id"],
            fanvue_user_id=metadata["fanvue_user_id"],
            conversation_thread_id=metadata["conversation_thread_id"],
            correlation_id=f"{result.correlation_id}:engagement",
            trigger_type=trigger_type, authoritative_suppression=suppression)
        if decision.decision != SEND_FREE_ENGAGEMENT_TEASER:
            return {"status": "SEND_NONE", "reason": decision.reason_code, "decision": decision}
        contact, reservation = self.contact_authority.authorize_proactive(
            purpose=(ContactPurpose.RE_ENGAGEMENT if trigger_type == "SCHEDULED_REENGAGEMENT"
                     else ContactPurpose.FREE_ENGAGEMENT),
            fanvue_account_id=int(metadata["fanvue_account_id"]),
            customer_scope=f"fanvue:{int(metadata['fanvue_user_id'])}",
            owner_id=f"engagement:{result.correlation_id}",
            creator_profile_id=int(metadata["creator_profile_id"]),
            correlation_id=f"{result.correlation_id}:engagement",
            evidence=self._contact_evidence(result),
        )
        metadata["customerContactPolicy"] = dict(contact.to_mapping())
        if reservation is None:
            return {"status": "SEND_NONE", "reason": contact.reason,
                    "contact_policy": contact, "decision": decision}
        prepared = self.delivery.prepare(
            creator_profile_id=metadata["creator_profile_id"],
            fanvue_account_id=metadata["fanvue_account_id"],
            fanvue_user_id=metadata["fanvue_user_id"],
            telegram_user_id=payload.telegram_user_id,
            telegram_chat_id=payload.telegram_chat_id,
            conversation_thread_id=metadata["conversation_thread_id"],
            correlation_id=f"{result.correlation_id}:engagement-delivery",
            inbound_telegram_message_id=payload.message_id, caption="",
            engagement_strategy=decision.strategy.value,
            decision_reason_code=decision.reason_code,
            decision_evidence=decision.evidence,
            policy_version=decision.policy_version)
        if prepared.operation is None:
            self.contact_authority.finalize_reservation(
                reservation, outcome="RELEASED", error=prepared.reason or prepared.status)
            return {"status": "SEND_NONE", "reason": prepared.reason or prepared.status,
                    "decision": decision}
        try:
            caption = self.captions.generate(asset_id=prepared.operation.teaser_asset_id,
                strategy=decision.strategy.value,
                creator_profile_id=metadata["creator_profile_id"],
                fanvue_account_id=metadata["fanvue_account_id"],
                recent_conversation=payload.chat_history,
                customer_context={"engagementPurpose": decision.strategy.value,
                    "policyEvidence": decision.evidence})
        except FreeEngagementTeaserCaptionError as error:
            self.delivery.repository.failed(prepared.operation.operation_id, str(error))
            self.contact_authority.finalize_reservation(
                reservation, outcome="FAILED", error=str(error))
            return {"status": "SEND_NONE", "reason": str(error), "decision": decision}
        operation = self.delivery.repository.update_caption(prepared.operation.operation_id, caption)
        if operation is None:
            self.contact_authority.finalize_reservation(
                reservation, outcome="FAILED", error="CAPTION_PERSISTENCE_FAILED")
            return {"status": "SEND_NONE", "reason": "CAPTION_PERSISTENCE_FAILED", "decision": decision}
        executed = await self.delivery.execute_async(operation.operation_id, transport=transport)
        execution_status = str(executed.status or "").upper()
        reservation_outcome = (
            "CONFIRMED" if execution_status in {"CONFIRMED", "TELEGRAM_ACCEPTED"}
            else "SEND_UNCERTAIN" if execution_status in {"AMBIGUOUS", "SEND_UNCERTAIN"}
            else "FAILED"
        )
        execution = getattr(executed, "execution", None)
        provider_id = (
            getattr(execution, "provider_message_id", None)
            or getattr(executed, "provider_message_id", None)
        )
        self.contact_authority.finalize_reservation(
            reservation, outcome=reservation_outcome,
            delivery_reference=str(provider_id) if provider_id is not None else None,
            error=None if reservation_outcome == "CONFIRMED" else execution_status,
        )
        if self.policy_repository is not None:
            self.policy_repository.persist_decision(decision,
                correlation_id=f"{result.correlation_id}:engagement",
                creator_profile_id=metadata["creator_profile_id"],
                fanvue_account_id=metadata["fanvue_account_id"],
                fanvue_user_id=metadata["fanvue_user_id"],
                conversation_thread_id=metadata["conversation_thread_id"],
                trigger_type=trigger_type, selected_asset_id=operation.teaser_asset_id,
                operation_id=operation.operation_id)
        return {"status": executed.status, "execution": executed, "decision": decision}

    async def handle_scheduled_reengagement(self, *, queue_item, transport):
        result = SimpleNamespace(correlation_id=f"outreach:{queue_item['id']}",
            diagnostic_metadata={"creator_profile_id": queue_item["creator_profile_id"],
                "fanvue_account_id": queue_item["fanvue_account_id"],
                "fanvue_user_id": queue_item["fanvue_user_id"],
                "conversation_thread_id": queue_item["conversation_thread_id"]},
            blocked=False, error_code=None, offer_authorized=False, offer_link=None,
            delivery_requires_payment=False)
        payload = SimpleNamespace(telegram_user_id=queue_item["telegram_user_id"],
            telegram_chat_id=queue_item["telegram_chat_id"], message_id=None,
            chat_history=[])
        return await self.handle_active_inbound(result=result, payload=payload,
            transport=transport, trigger_type="SCHEDULED_REENGAGEMENT")

    @staticmethod
    def _commercial_suppression(result):
        if result.blocked: return result.error_code or "CONVERSATION_BLOCKED"
        if result.offer_authorized or result.offer_link or result.delivery_requires_payment:
            return "AUTHORITATIVE_COMMERCIAL_ACTION_ACTIVE"
        decision = str((result.diagnostic_metadata or {}).get("customer_sales_decision") or "")
        if decision in {"PRESENT_OFFER","DELIVER_PURCHASE","CONGRATULATE_PURCHASE"}:
            return f"CUSTOMER_SALES_DECISION_{decision}"
        return None

    @staticmethod
    def _contact_evidence(result):
        metadata = dict(result.diagnostic_metadata or {})
        value = dict(metadata.get("customerValueAttention") or
                     metadata.get("customer_value_attention") or {})
        decision = str(metadata.get("customer_sales_decision") or "").upper()
        return {
            "safety_blocked": bool(result.blocked),
            "active_offer": bool(result.offer_authorized or result.offer_link
                                  or decision in {"WAIT", "NUDGE_ACTIVE_OFFER", "PRESENT_OFFER"}),
            "active_session": bool(metadata.get("active_sales_session") or
                                   metadata.get("sales_session_id")),
            "back_off": decision == "BACK_OFF" or bool(value.get("backOff")),
            "attention_mode": value.get("effortMode") or value.get("attentionTier"),
            "buyer_value_tier": value.get("valueTier"),
            "recent_purchase": bool(value.get("purchaseCount") and
                                    value.get("purchaseRecencyDays") is not None and
                                    float(value["purchaseRecencyDays"]) <= 2),
            "pending_delivery": bool(metadata.get("pending_delivery")),
            "uncertain_delivery": bool(metadata.get("send_uncertain")),
            "active_conversation": bool(metadata.get("active_conversation")),
            "recent_ppv": bool(metadata.get("recent_ppv")),
            "recent_free_teaser": bool(metadata.get("recent_free_teaser")),
            "cooldown_active": bool(metadata.get("contact_cooldown_active")),
        }

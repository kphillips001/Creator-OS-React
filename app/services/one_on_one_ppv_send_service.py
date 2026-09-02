"""Canonical one-on-one PPV orchestration.

The service transports a Customer Sales Brain-authorized Commercial Offering.
It does not own Session pacing, Offering selection, or sales authorization.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID, NAMESPACE_URL, uuid5

from app.repositories.chat_message_repository import get_or_create_chat_thread
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.customer_repository import get_user_by_account_and_id
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.content_delivery_guard_service import ContentDeliveryGuardService
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.fanvue_api_service import FanvueAPIService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.global_send_execution_guard_service import GlobalSendExecutionGuardService
from app.services.payload_builder_service import PayloadBuilderService
from app.services.ppv_caption_service import PPVCaptionService
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.sales_session_service import SalesSessionService
from app.models.customer_contact import ContactPolicyResult, ContactPurpose
from app.services.customer_contact_authority_service import CustomerContactAuthorityService


class OneOnOnePPVSendService:
    def __init__(
        self, fanvue_account_id: int | None = None, *,
        sales_session_service=None, customer_sales_brain_service=None,
        purchase_intent_service=None, identity_repository=None,
        creator_profile_resolver=get_active_creator_profile,
        customer_fetcher=get_user_by_account_and_id,
        thread_resolver=get_or_create_chat_thread,
        caption_service=None, payload_builder=None, content_guard=None,
        global_safety=None, global_execution_guard=None, fanvue_api=None,
        clock=lambda: datetime.now(timezone.utc),
    ):
        self.fanvue_account_id = fanvue_account_id
        self.sales_sessions = sales_session_service or SalesSessionService()
        self.customer_sales_brain = (
            customer_sales_brain_service or CustomerSalesBrainService()
        )
        self.purchase_intents = purchase_intent_service or PurchaseIntentService()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.creator_profile_resolver = creator_profile_resolver
        self.customer_fetcher = customer_fetcher
        self.thread_resolver = thread_resolver
        self.clock = clock
        self.caption_service = caption_service or PPVCaptionService()
        self.payload_builder = payload_builder or PayloadBuilderService()
        self.content_guard = content_guard or ContentDeliveryGuardService()
        self.global_safety = global_safety or GlobalAutomationSafetyService()
        self.global_execution_guard = (
            global_execution_guard or GlobalSendExecutionGuardService()
        )
        self.fanvue_api = fanvue_api or (
            FanvueAPIService(fanvue_account_id=fanvue_account_id)
            if fanvue_account_id is not None else None
        )
        self.contact_authority = CustomerContactAuthorityService()

    def send_ppv_to_user(
        self, fanvue_account_id: int, fanvue_user_uuid: int,
        thread_id: str, content_item: dict, price: float,
        dry_run: bool = True,
    ) -> dict:
        if (
            self.fanvue_account_id is not None
            and int(fanvue_account_id) != int(self.fanvue_account_id)
        ):
            return self._blocked("fanvue_account_id_mismatch")
        safety = self.global_safety.can_send_monetization()
        execution = self.global_execution_guard.validate_execution(
            execution_type="one_on_one_ppv", safety_result=safety,
            dry_run=dry_run,
        )
        if execution.get("blocked"):
            return self._blocked(
                execution.get("reason") or "execution_blocked",
                safety_result=safety, execution_guard_result=execution,
            )

        customer = self.customer_fetcher(
            int(fanvue_account_id), int(fanvue_user_uuid)
        )
        if customer is None:
            return self._blocked("canonical_customer_not_found")
        creator = self.creator_profile_resolver(str(fanvue_account_id)) or {}
        creator_profile_id = int(creator.get("id") or 0)
        if not creator_profile_id:
            return self._blocked("creator_scope_unavailable")
        thread = self.thread_resolver(
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_id=int(fanvue_user_uuid),
            fanvue_chat_uuid=str(thread_id),
        )
        conversation_thread_id = int(thread["id"])
        identity = self.identities.get_by_local_user_id(
            int(fanvue_account_id), int(fanvue_user_uuid)
        )
        if identity is None:
            return self._blocked("canonical_identity_unresolved")

        session = self.sales_sessions.resolve_active_conversation(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_id=int(fanvue_user_uuid),
            telegram_user_id=identity.telegram_user_id,
            conversation_thread_id=conversation_thread_id,
        )
        session_id = str(session.sales_session_id) if session is not None else None
        decision = self.customer_sales_brain.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=int(fanvue_account_id),
            external_fanvue_buyer_uuid=UUID(str(customer["fanvue_user_uuid"])),
            telegram_user_id=identity.telegram_user_id,
            identity_resolved=True,
            conversation_context={
                "conversation_thread_id": conversation_thread_id,
                "sales_session_id": session_id,
                "latest_message": "one-on-one PPV request",
            },
        )
        if not decision.sell_allowed or decision.recommended_offering_id is None:
            return {
                "success": True, "status": "skipped", "blocked": False,
                "reason": decision.reason_code.value,
                "sales_session_id": session_id,
                "customer_sales_decision": decision.decision.value,
            }
        contact_policy = self.contact_authority.decide(
            purpose=ContactPurpose.REACTIVE_COMMERCIAL,
            evidence={"active_session": session is not None},
        )
        if contact_policy.result is not ContactPolicyResult.ALLOW:
            return self._blocked(
                contact_policy.reason,
                contact_policy=dict(contact_policy.to_mapping()),
            )

        offering_id = self._value(content_item, "commercial_offering_id", "commercialOfferingId")
        if str(offering_id or "") != str(decision.recommended_offering_id):
            return self._blocked("canonical_offering_mismatch")
        publication_id = self._value(content_item, "commercial_publication_id", "commercialPublicationId")
        provider_resource_id = self._value(content_item, "provider_resource_id", "providerResourceId")
        delivery_url = self._value(content_item, "delivery_url", "deliveryUrl")
        if not publication_id or not provider_resource_id or not delivery_url:
            return self._blocked("canonical_publication_required")

        guard = self.content_guard.can_deliver_content(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_uuid,
            content_record=content_item,
            requested_delivery="chat_ppv",
        )
        if not guard.get("allowed"):
            return self._blocked(
                guard.get("reason") or "content_delivery_blocked",
                content_guard_result=guard,
            )
        caption = self.caption_service.generate_context_aware_caption(
            chat_history=[], content_metadata=content_item,
        )
        price_minor = int(decision.recommended_offering_price_minor or 0)
        sending_message_uuid = str(uuid.uuid4())
        payload = self.payload_builder.build_paid_ppv_payload(
            fanvue_account_id, fanvue_user_uuid, content_item, caption,
            price_minor / 100, sending_message_uuid,
        )
        if payload is None:
            return self._blocked("duplicate")

        if dry_run:
            return {
                "success": True, "status": "dry_run", "blocked": False,
                "payload": payload, "purchase_intent_planned": True,
                "sales_session_id": session_id,
                "execution_guard_result": execution,
                "content_guard_result": guard, "safety_result": safety,
            }

        now = self.clock()
        config = CustomerSalesBrainConfig.from_environment()
        intent = self.purchase_intents.replace_active_intent(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=int(fanvue_account_id),
            telegram_identity_mapping_id=identity.id,
            telegram_user_id=identity.telegram_user_id,
            telegram_chat_id=identity.telegram_chat_id,
            external_fanvue_user_uuid=identity.external_fanvue_user_uuid,
            commercial_offering_id=UUID(str(decision.recommended_offering_id)),
            commercial_publication_id=UUID(str(publication_id)),
            provider=str(content_item.get("provider") or "FANVUE"),
            provider_resource_id=str(provider_resource_id),
            delivery_url=str(delivery_url),
            conversation_id=str(conversation_thread_id),
            correlation_id=uuid5(NAMESPACE_URL, sending_message_uuid),
            expected_price_minor=price_minor,
            expected_currency=str(decision.recommended_offering_currency or "USD"),
            expires_at=now + config.offer_expiration,
            created_metadata={
                "source": "ONE_ON_ONE_PPV",
                "sales_session_id": session_id,
                "customer_sales_decision_id": str(decision.decision_id),
            },
        )
        if session is not None:
            self.sales_sessions.associate_purchase_intent(
                session_id=session.sales_session_id,
                creator_profile_id=creator_profile_id,
                purchase_intent_id=intent.purchase_intent_id,
                actor_type="AI",
                actor_identifier="OneOnOnePPVSendService",
                reason="Customer Sales Brain authorized one-on-one PPV.",
            )
        api = self.fanvue_api or FanvueAPIService(
            fanvue_account_id=int(fanvue_account_id)
        )
        result = api.send_chat_message(
            user_uuid=fanvue_user_uuid, payload=payload,
        )
        return {
            **result, "purchase_intent_id": str(intent.purchase_intent_id),
            "sales_session_id": session_id,
        }

    @staticmethod
    def _value(source, *names):
        return next((source.get(name) for name in names if source.get(name) is not None), None)

    @staticmethod
    def _blocked(reason, **details):
        return {
            "success": False, "blocked": True, "status": "blocked",
            "reason": reason, **details,
        }

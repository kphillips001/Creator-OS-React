"""Create and advance Purchase Intents around Telegram Media Link delivery."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid5, NAMESPACE_URL
from psycopg.errors import UniqueViolation
from fastapi.encoders import jsonable_encoder

from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.purchase_intent_service import PurchaseIntentService
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig


logger = logging.getLogger("commerce-signal")


class TelegramPurchaseIntentService:
    def __init__(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        identity_repository=None, purchase_intent_service=None,
        sales_session_service=None,
        unlock_gateway_service=None,
        provisional_session_service=None,
        deferred_continuation_service=None,
        clock=lambda: datetime.now(timezone.utc),
    ):
        self.creator_profile_id = creator_profile_id
        self.fanvue_account_id = fanvue_account_id
        self.identities = identity_repository or TelegramIdentityRepository()
        self.intents = purchase_intent_service or PurchaseIntentService()
        if sales_session_service is None:
            from app.services.sales_session_service import SalesSessionService
            sales_session_service = SalesSessionService()
        self.sales_sessions = sales_session_service
        self.unlock_gateway = unlock_gateway_service
        self.provisional_sessions = provisional_session_service
        if deferred_continuation_service is None:
            from app.services.unmapped_telegram_prospect_service import UnmappedTelegramProspectService
            deferred_continuation_service = UnmappedTelegramProspectService()
        self.deferred_continuations = deferred_continuation_service
        self.clock = clock

    def create_before_delivery(self, result, payload):
        diagnostics = result.diagnostic_metadata or {}
        decision = str(diagnostics.get("customer_sales_decision") or "")
        existing_intent_id = (
            diagnostics.get("purchase_acknowledgement_intent_id")
            if decision == "CONGRATULATE_PURCHASE"
            else diagnostics.get("active_purchase_intent_id")
            if decision == "NUDGE_ACTIVE_OFFER" else None
        )
        if existing_intent_id:
            return self.get(existing_intent_id)
        if not (
            diagnostics.get("final_offer_authorized") is True
            and diagnostics.get("customer_sales_brain_evaluated") is True
            and diagnostics.get("offering_selected")
            and diagnostics.get("delivery_url")
            and diagnostics.get("provider_resource_id")
            and diagnostics.get("publication_id")
        ):
            return None
        reader = getattr(
            self.identities, "get_verified_by_telegram_user_id",
            self.identities.get_by_telegram_user_id,
        )
        identity = reader(payload.telegram_user_id)
        from app.services.private_chat_unlock_gateway_service import fingerprint_bootstrap_enabled
        bootstrap_enabled = fingerprint_bootstrap_enabled()
        if identity is None and not bootstrap_enabled:
            logger.info(
                "event=identity_resolved resolved=false telegram_user_id=%s",
                payload.telegram_user_id,
            )
            return None
        if identity is not None and identity.fanvue_account_id != self.fanvue_account_id:
            logger.info(
                "event=identity_resolved resolved=false telegram_user_id=%s",
                payload.telegram_user_id,
            )
            return None
        logger.info(
            "event=identity_resolved resolved=true telegram_user_id=%s",
            payload.telegram_user_id,
        )
        config = CustomerSalesBrainConfig.from_environment()
        ttl_minutes = max(1, int(
            config.offer_expiration.total_seconds() // 60
        ))
        now = self.clock()
        correlation = str(result.correlation_id)
        correlation_uuid = uuid5(NAMESPACE_URL, correlation)
        deferred = dict(diagnostics.get("deferred_continuation") or {})
        if deferred.get("state") in {"READY", "CLAIMED"}:
            claimed = self.deferred_continuations.claim_deferred_continuation(
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id,
                telegram_user_id=payload.telegram_user_id,
                correlation_id=correlation,
            )
            if claimed is None:
                result.diagnostic_metadata[
                    "deferred_continuation_claimed"
                ] = False
                return None
            deferred = {
                **deferred,
                "state": "CLAIMED",
                "claimCorrelationId": correlation,
            }
            result.diagnostic_metadata["deferred_continuation"] = deferred
            result.diagnostic_metadata["deferred_continuation_claimed"] = True
        repository = getattr(self.intents, "repository", None)
        correlation_reader = getattr(repository, "get_by_correlation", None)
        intent = (
            correlation_reader(correlation_uuid)
            if callable(correlation_reader) else None
        )
        intent_reused = intent is not None
        try:
            if intent is None:
                intent = self.intents.replace_active_intent(
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id,
                telegram_identity_mapping_id=(identity.id if identity else None),
                telegram_user_id=(identity.telegram_user_id if identity else payload.telegram_user_id),
                telegram_chat_id=(identity.telegram_chat_id if identity else payload.telegram_chat_id),
                external_fanvue_user_uuid=(identity.external_fanvue_user_uuid if identity else None),
                commercial_offering_id=UUID(str(diagnostics["offering_id"])),
                commercial_publication_id=UUID(str(diagnostics["publication_id"])),
                provider=str(diagnostics["provider"]),
                provider_resource_id=str(diagnostics["provider_resource_id"]),
                delivery_url=str(diagnostics["delivery_url"]),
                conversation_id=correlation,
                correlation_id=correlation_uuid,
                expected_price_minor=int(diagnostics["price_minor"]),
                expected_currency=str(diagnostics["currency"]),
                expires_at=now + timedelta(minutes=ttl_minutes),
                created_metadata=jsonable_encoder({
                    "source": "TELEGRAM_COMMERCE",
                    "inbound_message_id": payload.message_id,
                    "recommendation_trace": {
                        **dict(
                            diagnostics.get("recommendation_diagnostics") or {}
                        ),
                        "rankedCandidates": diagnostics.get(
                            "recommendation_trace", []
                        ),
                    },
                    "commercial_intelligence": dict(
                        diagnostics.get("commercial_intelligence") or {}
                    ),
                    "photoshoot_bundle": dict(
                        diagnostics.get("bundle_sales_context") or {}
                    ),
                }),
                )
        except UniqueViolation:
            intent = self.intents.repository.get_by_correlation(correlation_uuid)
            if intent is None:
                raise
            intent_reused = True
        if bootstrap_enabled:
            if self.unlock_gateway is None:
                from app.services.private_chat_unlock_gateway_service import PrivateChatUnlockGatewayService
                self.unlock_gateway = PrivateChatUnlockGatewayService()
            _, gateway_url = self.unlock_gateway.issue(intent)
            result.delivery_payload["media_link"] = gateway_url
            result.delivery_payload["delivery_url"] = gateway_url
            result.delivery_payload.setdefault("metadata", {})[
                "private_chat_unlock_button"
            ] = {"label": "🔓 Unlock", "url": gateway_url}
            result.diagnostic_metadata["delivery_url"] = gateway_url
        if identity is None and bootstrap_enabled:
            result.diagnostic_metadata["telegram_identity_eligibility"] = "UNMAPPED_BOOTSTRAP"
            experience = dict(diagnostics.get("recommended_photoshoot_experience") or {})
            product_context = dict(diagnostics.get("recommended_product_context") or {})
            selling_mode = str(product_context.get("sellingMode") or "").upper()
            if experience.get("photoshoot_id") or selling_mode == "SESSION":
                if self.provisional_sessions is None:
                    from app.services.telegram_provisional_sales_session_service import TelegramProvisionalSalesSessionService
                    self.provisional_sessions = TelegramProvisionalSalesSessionService()
                provisional = self.provisional_sessions.create_or_get(
                    creator_profile_id=self.creator_profile_id,
                    fanvue_account_id=self.fanvue_account_id,
                    telegram_user_id=payload.telegram_user_id,
                    telegram_chat_id=payload.telegram_chat_id,
                    photoshoot_reference=str(experience.get("photoshoot_id") or
                                              product_context.get("photoshootId")),
                    session_strategy=str(product_context.get("sessionStrategy") or
                                         "CANONICAL_SESSION"),
                    configured_base_price_minor=int(diagnostics["price_minor"]),
                    commercial_context={"productContext": product_context,
                                        "experience": experience},
                )
                self.provisional_sessions.associate_intent(
                    provisional.provisional_session_id, intent.purchase_intent_id)
                result.diagnostic_metadata["provisional_session_id"] = str(
                    provisional.provisional_session_id)
        result.diagnostic_metadata.update({
            "purchase_intent_created": not intent_reused,
            "purchase_intent_reused": intent_reused,
            "purchase_intent_id": str(intent.purchase_intent_id),
            "purchase_intent_state": getattr(
                getattr(intent, "status", None), "value",
                getattr(intent, "status", "CREATED"),
            ),
        })
        if (
            deferred.get("state") == "CLAIMED"
            and deferred.get("claimCorrelationId") == correlation
        ):
            consumed = self.deferred_continuations.consume_deferred_continuation(
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id,
                telegram_user_id=payload.telegram_user_id,
                correlation_id=correlation,
            )
            result.diagnostic_metadata["deferred_continuation_consumed"] = bool(
                consumed
            )
        intelligence = dict(
            diagnostics.get("commercial_intelligence") or {}
        )
        session_context = dict(
            intelligence.get("salesSessionContext") or {}
        )
        session_id = session_context.get("salesSessionId")
        if intelligence.get("strategy") == "SESSION_SELLING" and session_id:
            try:
                self.sales_sessions.associate_purchase_intent(
                    session_id=session_id,
                    creator_profile_id=self.creator_profile_id,
                    purchase_intent_id=intent.purchase_intent_id,
                    actor_type="SYSTEM",
                    actor_identifier="TelegramPurchaseIntentService",
                    reason="Authorized Session Selling presentation.",
                )
                self._advance_linked_session(
                    intent, target="OFFERING",
                    reason="Session PurchaseIntent created before presentation.",
                )
            except Exception as error:
                logger.warning(
                    "event=sales_session_purchase_intent_association_failed "
                    "purchase_intent_id=%s error_type=%s",
                    intent.purchase_intent_id, type(error).__name__,
                )
        return intent

    def confirm_delivery(
        self, intent, *, telegram_message_id=None, presented_at=None,
    ):
        if intent is None:
            return None
        confirmed = self.intents.confirm_presented(
            intent.purchase_intent_id,
            telegram_message_id=telegram_message_id,
            presented_at=presented_at,
        )
        # Compatibility repositories may perform the durable update without
        # returning the refreshed row. Session synchronization still needs the
        # authoritative intent identity and must not turn a confirmed delivery
        # into a post-send exception.
        confirmed = confirmed or intent
        self._advance_linked_session(
            confirmed, target="AWAITING_PAYMENT",
            reason="Session offer delivery confirmed.",
        )
        return confirmed

    def get(self, intent_id):
        return self.intents.repository.get(UUID(str(intent_id)))

    def abandon_delivery(self, intent):
        if intent is None:
            return None
        abandoned = self.intents.mark_abandoned(intent.purchase_intent_id)
        self._advance_linked_session(
            abandoned, target="CONTINUING",
            reason="Session offer abandoned; return to coordinated continuation.",
        )
        return abandoned

    def fail_delivery(self, intent):
        if intent is None:
            return None
        failed = self.intents.mark_delivery_failed(intent.purchase_intent_id)
        self._advance_linked_session(
            failed, target="CONTINUING",
            reason="Session delivery failed; release offering state.",
        )
        return failed

    def get_unacknowledged_purchase(self, **lookup):
        return self.intents.get_unacknowledged_purchase(**lookup)

    def acknowledge_purchase(self, intent_id):
        acknowledged = self.intents.acknowledge_purchase(UUID(str(intent_id)))
        if acknowledged is not None and getattr(
            acknowledged, "telegram_user_id", None
        ) is not None:
            self.deferred_continuations.ready_deferred_continuation(
                creator_profile_id=self.creator_profile_id,
                fanvue_account_id=self.fanvue_account_id,
                telegram_user_id=acknowledged.telegram_user_id,
            )
        self._advance_linked_session(
            acknowledged, target="CONTINUING",
            reason="Verified Session purchase acknowledged; continue to next step.",
        )
        return acknowledged

    def _advance_linked_session(self, intent, *, target: str, reason: str):
        """Synchronize canonical Session state from durable intent milestones.

        Photoshoot lifecycle remains authoritative for which content comes next;
        this only keeps the SalesSession envelope from disagreeing with it.
        """
        repository = getattr(self.sales_sessions, "repository", None)
        association_reader = getattr(repository, "purchase_intent_association", None)
        getter = getattr(self.sales_sessions, "get", None)
        advance = getattr(self.sales_sessions, "advance", None)
        if not callable(association_reader) or not callable(getter) or not callable(advance):
            return None
        association = association_reader(intent.purchase_intent_id)
        if association is None:
            return None
        session_id, _sequence = association
        try:
            session = getter(
                session_id=session_id, creator_profile_id=self.creator_profile_id)
            if getattr(getattr(session, "state", None), "value", None) == target:
                return session
            allowed_sources = {
                "OFFERING": {"ACTIVE", "CONTINUING"},
                "AWAITING_PAYMENT": {"OFFERING"},
                "CONTINUING": {"OFFERING", "AWAITING_PAYMENT"},
            }
            current = getattr(getattr(session, "state", None), "value", None)
            if current not in allowed_sources.get(target, set()):
                return session
            return advance(
                session_id=session_id, creator_profile_id=self.creator_profile_id,
                state=target, actor_type="SYSTEM",
                actor_identifier="TelegramPurchaseIntentService", reason=reason,
            )
        except Exception as error:
            logger.warning(
                "event=sales_session_intent_state_sync_failed "
                "purchase_intent_id=%s target=%s error_type=%s",
                intent.purchase_intent_id, target, type(error).__name__,
            )
            return None

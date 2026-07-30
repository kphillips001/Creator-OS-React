"""Deterministic commercial action evaluator; no AI and no side effects."""
from __future__ import annotations
from dataclasses import replace

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.repositories.customer_commerce_repository import CustomerCommerceRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.sales_session_repository import SalesSessionRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.commerce_signal_service import CommerceSignalService
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig


logger = logging.getLogger("customer-sales-brain")


class CustomerSalesBrainService:
    def __init__(
        self, *, customer_repository=None, identity_repository=None,
        intent_repository=None, commerce_signal_service=None,
        offering_selector_service=None, config=None,
        sales_session_repository=None,
        clock=lambda: datetime.now(timezone.utc),
    ):
        self.customers = customer_repository or CustomerCommerceRepository()
        self.identities = identity_repository or TelegramIdentityRepository()
        self.intents = intent_repository or PurchaseIntentRepository()
        self.signals = commerce_signal_service or CommerceSignalService()
        self.offering_selector = (
            offering_selector_service or CommercialOfferingSelectorService()
        )
        self.sales_sessions = (
            sales_session_repository or SalesSessionRepository()
        )
        self.config = config or CustomerSalesBrainConfig.from_environment()
        self.clock = clock

    def evaluate_for_telegram_user(
        self, *, creator_profile_id: int, telegram_user_id: int,
        conversation_context: dict | None = None,
    ) -> CustomerSalesDecision:
        started = time.perf_counter()
        now = self.clock()
        identity = self.identities.get_by_telegram_user_id(telegram_user_id)
        if identity is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=0, buyer_uuid=None,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.IDENTITY_UNRESOLVED,
                summary="Telegram identity has no canonical Fanvue buyer mapping.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        return self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=identity.fanvue_account_id,
            external_fanvue_buyer_uuid=identity.external_fanvue_user_uuid,
            telegram_user_id=identity.telegram_user_id,
            identity_resolved=True,
            conversation_context=conversation_context,
            _started=started,
        )

    def evaluate_for_buyer(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_buyer_uuid: UUID,
        telegram_user_id: int | None, identity_resolved: bool,
        conversation_context: dict | None = None, _started=None,
    ) -> CustomerSalesDecision:
        started = _started if _started is not None else time.perf_counter()
        now = self.clock()
        context = dict(conversation_context or {})
        context.update(self._active_sales_session_context(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=external_fanvue_buyer_uuid,
        ))
        if not identity_resolved or telegram_user_id is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                buyer_uuid=external_fanvue_buyer_uuid,
                telegram_user_id=telegram_user_id, identity_resolved=False,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.IDENTITY_UNRESOLVED,
                summary="Buyer identity is not linked to Telegram.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        profile = self.customers.get_by_buyer_uuid(
            creator_profile_id=creator_profile_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
        )
        if profile is None and hasattr(self.customers, "get_or_create"):
            profile = self.customers.get_or_create(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                external_fanvue_user_uuid=external_fanvue_buyer_uuid,
                seen_at=now,
                display_name=None,
                handle=None,
            )
            if hasattr(self.customers, "update_profile"):
                profile = self.customers.update_profile(
                    profile.customer_commerce_profile_id,
                    display_name=profile.display_name,
                    handle=profile.handle,
                    profile_state=profile.profile_state,
                    telegram_identity_mapping_id=(
                        self.identities.get_by_telegram_user_id(
                            telegram_user_id
                        ).id
                    ),
                    telegram_user_id=telegram_user_id,
                )
            logger.info(
                "event=customer_commerce_prospect_onboarded "
                "creator_profile_id=%s telegram_user_id=%s",
                creator_profile_id, telegram_user_id,
            )
        if profile is None:
            return self._finish(
                started, now, creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                buyer_uuid=external_fanvue_buyer_uuid,
                telegram_user_id=telegram_user_id, identity_resolved=True,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.NO_COMMERCE_PROFILE,
                summary="No Customer Commerce profile exists for this buyer.",
                stage=CustomerBuyerStage.UNKNOWN,
            )
        stage = self.buyer_stage(profile.purchase_count)
        signal = self.signals.get_signal(
            creator_profile_id=creator_profile_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
        )
        signal_data = self._signal(signal)
        latest = self.intents.get_latest_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        active = self.intents.get_active_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        common = dict(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            buyer_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            identity_resolved=True, stage=stage,
            signal=signal_data, active=active, latest=latest,
        )

        # Priority 2: verified provider payment is still reconciling.
        if signal and signal.reconciliation_state == "PENDING":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.PAYMENT_PENDING,
                reason=CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING,
                summary="A provider payment is awaiting earnings reconciliation.",
            )
        # Priority 3: deterministic payment evidence was ambiguous.
        if (
            (signal and signal.attribution_state == "UNKNOWN")
            or (latest and latest.attribution_result.value == "UNKNOWN")
        ):
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.MANUAL_REVIEW,
                reason=CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN,
                summary="Payment attribution did not produce one hard match.",
            )
        # Priority 4: acknowledgement is explicit deterministic context.
        if latest and latest.status.value == "PURCHASED" and context.get(
            "purchase_acknowledgement_pending"
        ) is True:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
                reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
                summary="A verified purchase is awaiting acknowledgement.",
                congratulate_allowed=True,
            )
        # Priority 5: recent purchase cooldown.
        if profile.last_purchase_at:
            cooldown = profile.last_purchase_at + self.config.purchase_cooldown
            if now < cooldown:
                return self._finish(
                    started, now, **common,
                    decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                    reason=CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN,
                    summary="Recent purchase cooldown prevents another sale.",
                    cooldown_until=cooldown,
                )
        # Priority 6/7: active offer wait then nudge.
        if active:
            presented = active.presented_at or active.created_at
            nudge_at = presented + self.config.offer_nudge_delay
            if now < nudge_at:
                return self._finish(
                    started, now, **common,
                    decision=CustomerSalesDecisionType.WAIT,
                    reason=(
                        CustomerSalesReasonCode
                        .ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE
                    ),
                    summary="The active offer is still in its waiting period.",
                    cooldown_until=nudge_at,
                )
            selection = self.offering_selector.select(
                creator_profile_id=creator_profile_id,
                telegram_user_id=telegram_user_id,
                customer_profile=profile,
                commerce_signal=signal,
                active_purchase_intent=active,
                conversation_context={
                    **context, "primary_sales_channel": "AI_CHAT",
                },
            )
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
                reason=CustomerSalesReasonCode.ACTIVE_OFFER_NUDGE_ELIGIBLE,
                summary="The active offer is eligible for deterministic follow-up.",
                nudge_allowed=True, recommendation=selection,
                selector_result=selection,
            )
        # Priority 8: explicit expired intent.
        if latest and latest.status.value == "EXPIRED":
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
                reason=CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED,
                summary="The latest offer expired without a verified purchase.",
            )
        # Priority 9/10: deterministic selector chooses one offering or none.
        selection = self.offering_selector.select(
            creator_profile_id=creator_profile_id,
            telegram_user_id=telegram_user_id,
            customer_profile=profile,
            commerce_signal=signal,
            active_purchase_intent=active,
            conversation_context={
                **context, "primary_sales_channel": "AI_CHAT",
            },
        )
        if selection.offering_id:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.PRESENT_OFFER,
                reason=CustomerSalesReasonCode.NO_ACTIVE_OFFER,
                summary=(
                    "No offer is active and the deterministic selector "
                    "found one live offering."
                ),
                recommendation=selection, selector_result=selection,
                sell_allowed=True,
            )
        return self._finish(
            started, now, **common,
            decision=CustomerSalesDecisionType.NO_SALE,
            reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
            summary="No active, live, deliverable offering is available.",
            selector_result=selection,
        )

    def _active_sales_session_context(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_buyer_uuid,
    ) -> dict:
        try:
            identity = (
                self.identities.get_by_external_fanvue_user_uuid(
                    fanvue_account_id, external_fanvue_buyer_uuid
                )
            )
            if identity is None:
                return {}
            session = self.sales_sessions.get_active_for_customer(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=identity.local_fanvue_user_id,
            )
        except Exception as error:
            logger.warning(
                "event=sales_session_context_unavailable error_type=%s",
                type(error).__name__,
            )
            return {}
        if session is None:
            return {}
        return {
            "sales_session_id": str(session.sales_session_id),
            "sales_session_state": session.state.value,
            "sales_session_progression": session.progression_stage.value,
            "sales_session_foundation": (
                session.commercial_foundation_reference
            ),
        }

    @staticmethod
    def refine_for_readiness(
        decision: CustomerSalesDecision,
        readiness: dict | None,
    ) -> CustomerSalesDecision:
        """Refine one immutable evaluation without another database read."""
        flags = dict(readiness or {})
        ready = flags.get("conversation_ready_for_offer") is True
        if (
            decision.decision is CustomerSalesDecisionType.PRESENT_OFFER
            and not ready
        ):
            return replace(
                decision,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason_code=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
                reason_summary=(
                    "Current deterministic conversation flags do not "
                    "authorize presenting a paid offer."
                ),
                sell_allowed=False,
            )
        return decision

    @staticmethod
    def buyer_stage(purchase_count: int) -> CustomerBuyerStage:
        if purchase_count <= 0:
            return CustomerBuyerStage.PROSPECT
        if purchase_count == 1:
            return CustomerBuyerStage.FIRST_TIME_BUYER
        return CustomerBuyerStage.REPEAT_BUYER

    def list_decisions(
        self, *, creator_profile_id: int, search: str | None,
        page: int, page_size: int,
    ):
        profiles, total, current_page = self.customers.list_profiles(
            creator_profile_id=creator_profile_id, search=search,
            page=page, page_size=page_size,
        )
        items = tuple(self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=item.fanvue_account_id,
            external_fanvue_buyer_uuid=item.external_fanvue_user_uuid,
            telegram_user_id=item.telegram_user_id,
            identity_resolved=item.telegram_identity_mapping_id is not None,
        ) for item in profiles)
        return items, total, current_page

    def statistics(self, *, creator_profile_id: int):
        profiles, _, _ = self.customers.list_profiles(
            creator_profile_id=creator_profile_id, search=None,
            page=1, page_size=1000,
        )
        decisions = [self.evaluate_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=item.fanvue_account_id,
            external_fanvue_buyer_uuid=item.external_fanvue_user_uuid,
            telegram_user_id=item.telegram_user_id,
            identity_resolved=item.telegram_identity_mapping_id is not None,
        ) for item in profiles]
        distribution = {}
        stages = {}
        for item in decisions:
            distribution[item.decision.value] = distribution.get(
                item.decision.value, 0
            ) + 1
            stages[item.buyer_stage.value] = stages.get(
                item.buyer_stage.value, 0
            ) + 1
        return {
            "total": len(decisions), "decisionDistribution": distribution,
            "buyerStageDistribution": stages,
            "currentActiveOffers": sum(
                item.active_purchase_intent_id is not None for item in decisions
            ),
            "pendingPayments": sum(
                item.decision is CustomerSalesDecisionType.PAYMENT_PENDING
                for item in decisions
            ),
            "unknownAttributions": sum(
                item.reason_code
                is CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN
                for item in decisions
            ),
        }

    def _finish(
        self, started, now, *, creator_profile_id, fanvue_account_id,
        buyer_uuid, telegram_user_id, identity_resolved, decision, reason,
        summary, stage, signal=None, active=None, latest=None,
        recommendation=None, sell_allowed=False, nudge_allowed=False,
        congratulate_allowed=False, cooldown_until=None,
        selector_result=None,
    ):
        lifecycle = active
        conversion = (
            signal.get("conversionState") if signal else "NO_ACTIVE_OFFER"
        )
        result = CustomerSalesDecision(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=buyer_uuid,
            telegram_user_id=telegram_user_id,
            identity_resolved=identity_resolved,
            decision=decision, reason_code=reason, reason_summary=summary,
            buyer_stage=stage, commerce_signal=immutable_mapping(signal),
            active_purchase_intent_id=(
                lifecycle.purchase_intent_id if lifecycle else None
            ),
            active_offering_id=(
                lifecycle.commercial_offering_id if lifecycle else None
            ),
            active_offer_status=(
                lifecycle.status.value if lifecycle else None
            ),
            active_offer_conversion_state=conversion,
            recommended_offering_id=(
                recommendation.offering_id if recommendation else None
            ),
            recommended_publication_id=(
                recommendation.publication_id if recommendation else None
            ),
            recommended_delivery_url=(
                recommendation.delivery_url if recommendation else None
            ),
            sell_allowed=sell_allowed, nudge_allowed=nudge_allowed,
            upsell_allowed=False, cross_sell_allowed=False,
            congratulate_allowed=congratulate_allowed,
            cooldown_until=cooldown_until, evaluated_at=now,
            decision_metadata=immutable_mapping({
                "rulePriority": self._priority(decision, reason),
                "evaluationMs": round((time.perf_counter() - started) * 1000, 3),
                "configuration": {
                    "purchaseCooldownHours": int(
                        self.config.purchase_cooldown.total_seconds() // 3600
                    ),
                    "offerNudgeHours": int(
                        self.config.offer_nudge_delay.total_seconds() // 3600
                    ),
                    "offerExpirationHours": int(
                        self.config.offer_expiration.total_seconds() // 3600
                    ),
                },
                "latestPurchaseIntentId": (
                    str(latest.purchase_intent_id) if latest else None
                ),
                "latestIntentStatus": (
                    latest.status.value if latest else None
                ),
                "offeringSelector": (
                    {
                        "selectionReason": (
                            selector_result.selection_reason.value
                        ),
                        "exclusionReasons": list(
                            selector_result.exclusion_reasons
                        ),
                        **dict(selector_result.selector_metadata),
                    }
                    if selector_result else None
                ),
            }),
            recommended_offering_title=(
                recommendation.title if recommendation else None
            ),
            recommended_offering_short_description=(
                recommendation.short_description if recommendation else None
            ),
            recommended_offering_price_minor=(
                recommendation.price_minor if recommendation else None
            ),
            recommended_offering_currency=(
                recommendation.currency if recommendation else None
            ),
        )
        logger.info(
            "event=decision_generated decision=%s reason_code=%s buyer_stage=%s "
            "buyer_uuid=%s current_offer=%s purchase_state=%s timing_ms=%s",
            decision.value, reason.value, stage.value, buyer_uuid,
            result.active_offering_id, conversion,
            result.decision_metadata["evaluationMs"],
        )
        return result

    @staticmethod
    def _signal(signal):
        if signal is None:
            return {}
        return {
            "buyerUuid": signal.buyer_uuid,
            "telegramUserId": signal.telegram_user_id,
            "identityResolved": signal.identity_resolved,
            "lifetimeSpendMinor": signal.lifetime_spend_minor,
            "purchaseCount": signal.purchase_count,
            "lastPurchaseAt": (
                signal.last_purchase_at.isoformat()
                if signal.last_purchase_at else None
            ),
            "currentActiveOfferId": signal.current_active_offer_id,
            "currentOfferStatus": signal.current_offer_status,
            "conversionState": signal.conversion_state,
            "latestTransaction": signal.latest_transaction,
            "attributionState": signal.attribution_state,
            "reconciliationState": signal.reconciliation_state,
        }

    @staticmethod
    def _priority(decision, reason):
        priorities = {
            CustomerSalesReasonCode.IDENTITY_UNRESOLVED: 1,
            CustomerSalesReasonCode.PAYMENT_RECONCILIATION_PENDING: 2,
            CustomerSalesReasonCode.PAYMENT_ATTRIBUTION_UNKNOWN: 3,
            CustomerSalesReasonCode.PURCHASE_VERIFIED: 4,
            CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN: 5,
            CustomerSalesReasonCode.ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE: 6,
            CustomerSalesReasonCode.ACTIVE_OFFER_NUDGE_ELIGIBLE: 7,
            CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED: 8,
            CustomerSalesReasonCode.NO_ACTIVE_OFFER: 9,
            CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING: 10,
        }
        return priorities.get(reason, 0)

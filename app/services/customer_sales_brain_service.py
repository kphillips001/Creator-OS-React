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
from app.services.commercial_intelligence_context_service import (
    CommercialIntelligenceContextService,
)
from app.services.commercial_intelligence_service import (
    CommercialIntelligenceService,
)
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig


logger = logging.getLogger("customer-sales-brain")


class CustomerSalesBrainService:
    def __init__(
        self, *, customer_repository=None, identity_repository=None,
        intent_repository=None, commerce_signal_service=None,
        offering_selector_service=None, config=None,
        sales_session_repository=None,
        commercial_intelligence_service=None,
        commercial_intelligence_context_service=None,
        photoshoot_lifecycle_service=None,
        autonomous_progression_service=None, progression_repository=None,
        session_runtime_service=None,
        bundle_sales_context_service=None,
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
        self.commercial_intelligence = (
            commercial_intelligence_service or CommercialIntelligenceService()
        )
        self.commercial_context = (
            commercial_intelligence_context_service
            or CommercialIntelligenceContextService()
        )
        self.config = config or CustomerSalesBrainConfig.from_environment()
        self.photoshoot_lifecycles = photoshoot_lifecycle_service
        self.autonomous_progression = autonomous_progression_service
        self.progression_repository = progression_repository
        self.session_runtime = session_runtime_service
        self.bundle_sales_context = bundle_sales_context_service
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
            progression_context=context,
        )
        opportunity = self._apply_photoshoot_opportunity_policy(
            creator_profile_id=creator_profile_id,
            customer_profile=profile,
            context=context,
        )
        if opportunity is not None and opportunity.status.value in {"OBJECTION", "CLOSED", "DECLINED"} and active is not None:
            abandon = getattr(self.intents, "mark_abandoned", None)
            if callable(abandon):
                try:
                    abandon(active.purchase_intent_id, at=now)
                    active = None
                    common["active"] = None
                except Exception as error:
                    logger.warning("event=photoshoot_opportunity_intent_close_failed error_type=%s", type(error).__name__)

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
        intelligence = self._commercial_intelligence_decision(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_buyer_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            conversation_context=context,
            core_user_id=(
                getattr(profile, "core_user_id", None)
                or context.get("core_user_id")
            ),
        )
        if intelligence.strategy is None:
            return self._finish(
                started, now, **common,
                decision=CustomerSalesDecisionType.NO_SALE,
                reason=CustomerSalesReasonCode.NO_SELLING_STRATEGY,
                summary=intelligence.reason_summary,
                commercial_intelligence=intelligence,
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
            strategy_constraints=intelligence.constraints,
            strategy=intelligence.strategy.value,
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
                commercial_intelligence=intelligence,
            )
        return self._finish(
            started, now, **common,
            decision=CustomerSalesDecisionType.NO_SALE,
            reason=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
            summary="No active, live, deliverable offering is available.",
            selector_result=selection,
            commercial_intelligence=intelligence,
        )

    def _commercial_intelligence_decision(
        self, *, creator_profile_id, fanvue_account_id,
        external_fanvue_buyer_uuid, telegram_user_id, conversation_context,
        core_user_id=None,
    ):
        identity = self.identities.get_by_telegram_user_id(telegram_user_id)
        local_fanvue_user_id = getattr(
            identity, "local_fanvue_user_id", None
        )
        session = self.sales_sessions.get_active_for_customer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=local_fanvue_user_id,
        ) if local_fanvue_user_id is not None else None
        session_intents = ()
        roles = ()
        historical_session = None
        selector_repository = getattr(self.offering_selector, "repository", None)
        candidates = (
            selector_repository.list_candidates(
                creator_profile_id=creator_profile_id,
                primary_sales_channel="AI_CHAT",
            )
            if selector_repository is not None else ()
        )
        bundle_compositions = tuple(
            {
                "photoshoot_reference": str(
                    candidate["photoshoot_identifiers"][0]
                ),
                "asset_ids": tuple(
                    int(value) for value in candidate.get("asset_ids") or ()
                ),
                "complete_set": (
                    len(candidate.get("asset_ids") or ())
                    == int(candidate.get("photoshoot_asset_count") or 0)
                    and int(candidate.get("photoshoot_asset_count") or 0) > 0
                ),
                "provenance": (
                    "CommercialOfferingAssetMembership",
                    "PhotoshootAssetMembership",
                ),
            }
            for candidate in candidates
            if str(candidate.get("offering_type") or "") == "BUNDLE"
            and len(candidate.get("photoshoot_identifiers") or ()) == 1
        )
        normalized_conversation = dict(conversation_context or {})
        intended_photoshoot = normalized_conversation.get(
            "requested_photoshoot_reference"
        )
        if intended_photoshoot is None:
            references = tuple(dict.fromkeys(
                value["photoshoot_reference"] for value in bundle_compositions
            ))
            intended_photoshoot = references[0] if len(references) == 1 else None
        if (
            session is None
            and intended_photoshoot is not None
            and local_fanvue_user_id is not None
            and hasattr(self.sales_sessions, "list_for_creator")
        ):
            historical_session = self._resolve_historical_session(
                self.sales_sessions.list_for_creator(
                    creator_profile_id=creator_profile_id, limit=100
                ),
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=local_fanvue_user_id,
                intended_photoshoot_reference=intended_photoshoot,
            )
        evidence_session = session or historical_session
        if session is not None and hasattr(
            self.sales_sessions, "list_purchase_intents"
        ):
            session_intents = self.sales_sessions.list_purchase_intents(
                session_id=session.sales_session_id,
                creator_profile_id=creator_profile_id,
            )
        elif historical_session is not None and hasattr(
            self.sales_sessions, "list_purchase_intents"
        ):
            session_intents = self.sales_sessions.list_purchase_intents(
                session_id=historical_session.sales_session_id,
                creator_profile_id=creator_profile_id,
            )
        if evidence_session is not None and hasattr(
            self.sales_sessions, "commercial_guidance"
        ):
            guidance = self.sales_sessions.commercial_guidance(
                session=evidence_session
            )
            roles = tuple(
                role
                for asset in guidance.get("assets") or ()
                for role in asset.get("effective_commercial_roles") or ()
            )
        available_types = tuple(
            str(candidate.get("offering_type") or "")
            for candidate in candidates
        )
        lineage_asset_ids = tuple(dict.fromkeys(
            int(asset_id)
            for candidate in candidates
            for asset_id in candidate.get("asset_ids") or ()
        ))
        if (
            not available_types
            and getattr(self.offering_selector, "offering", None) is not None
        ):
            available_types = ("SINGLE_IMAGE",)
        if "latest_message" not in normalized_conversation:
            normalized_conversation["latest_message"] = (
                "general request for existing content"
            )
        assembled = self.commercial_context.assemble(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=external_fanvue_buyer_uuid,
            telegram_user_id=telegram_user_id,
            core_user_id=core_user_id,
            legacy_fanvue_user_id=local_fanvue_user_id,
            active_sales_session=session,
            relevant_historical_session=historical_session,
            session_purchase_intents=session_intents,
            available_offering_types=available_types,
            intended_photoshoot_reference=intended_photoshoot,
            bundle_compositions=bundle_compositions,
            approved_commercial_roles=roles,
            conversation_context=normalized_conversation,
            lineage_asset_ids=lineage_asset_ids,
        )
        return self.commercial_intelligence.recommend(assembled)

    @staticmethod
    def _resolve_historical_session(
        sessions, *, fanvue_account_id, fanvue_user_id,
        intended_photoshoot_reference,
    ):
        if intended_photoshoot_reference is None:
            return None
        return next(
            (
                item for item in sessions
                if item.fanvue_account_id == fanvue_account_id
                and item.fanvue_user_id == fanvue_user_id
                and item.commercial_foundation_reference
                == str(intended_photoshoot_reference)
            ),
            None,
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
            "sales_session_foundation_type": getattr(
                session.commercial_foundation_type,
                "value", session.commercial_foundation_type,
            ),
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
        commercial_intelligence=None,
        progression_context=None,
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
                "commercialIntelligence": (
                    {
                        "strategy": (
                            commercial_intelligence.strategy.value
                            if commercial_intelligence.strategy else None
                        ),
                        "reason": commercial_intelligence.reason.value,
                        "reasonSummary": commercial_intelligence.reason_summary,
                        "evidence": list(commercial_intelligence.evidence),
                        "evidenceProvenance": dict(
                            commercial_intelligence.evidence_provenance
                        ),
                        "constraints": {
                            "requiredOfferingTypes": list(
                                commercial_intelligence.constraints
                                .required_offering_types
                            ),
                            "excludedOfferingTypes": list(
                                commercial_intelligence.constraints
                                .excluded_offering_types
                            ),
                            "requiredPhotoshootReference": (
                                commercial_intelligence.constraints
                                .required_photoshoot_reference
                            ),
                            "progression": (
                                commercial_intelligence.constraints.progression
                            ),
                            "completeSetRequired": (
                                commercial_intelligence.constraints
                                .complete_set_required
                            ),
                            "continuationRequired": (
                                commercial_intelligence.constraints
                                .continuation_required
                            ),
                        },
                        "bundleEligibility": (
                            commercial_intelligence.bundle_eligibility.value
                        ),
                        "continuationGuidance": (
                            commercial_intelligence.continuation_guidance
                        ),
                        "evidenceSufficient": (
                            commercial_intelligence.evidence_sufficient
                        ),
                        "conflicts": list(commercial_intelligence.conflicts),
                        "ownershipConsiderations": dict(
                            commercial_intelligence.ownership_considerations
                        ),
                        "salesSessionContext": dict(
                            commercial_intelligence.sales_session_context
                        ),
                        "customerRequestContext": dict(
                            commercial_intelligence.customer_request_context
                        ),
                        "diagnosticContext": dict(
                            commercial_intelligence.diagnostic_context
                        ),
                    }
                    if commercial_intelligence else None
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
            recommended_photoshoot_experience=(
                getattr(recommendation, "photoshoot_experience", None)
                if recommendation else None
            ),
        )
        progression_context=dict(progression_context or {})
        experience = getattr(recommendation, "photoshoot_experience", None) if recommendation else None
        resolved_photoshoot_lifecycle = None
        existing_active_lifecycle = None
        profile = None
        if experience is not None and buyer_uuid is not None:
            try:
                profile = self.customers.get_by_buyer_uuid(
                    creator_profile_id=creator_profile_id,
                    external_fanvue_user_uuid=buyer_uuid,
                )
                if profile is not None:
                    service = self.photoshoot_lifecycles
                    if service is None:
                        from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                        service = CustomerPhotoshootLifecycleService()
                    states=service.context_for_customer(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id)
                    existing_active_lifecycle=next((v for v in states.values() if v.status.value in {'ACTIVE','OBJECTION'}),None)
                    resolved_photoshoot_lifecycle = service.resolve_recommendation(
                        creator_profile_id=creator_profile_id,
                        customer_commerce_profile_id=profile.customer_commerce_profile_id,
                        recommendation=experience,
                        reason=experience.recommendation_explanation,
                    )
            except Exception as error:
                logger.warning("event=photoshoot_lifecycle_resolution_unavailable error_type=%s", type(error).__name__)
        dispatch_mode = None
        dispatch_session_id = (
            resolved_photoshoot_lifecycle.photoshoot_id
            if resolved_photoshoot_lifecycle is not None
            else getattr(experience, "photoshoot_id", None)
        )
        if dispatch_session_id:
            try:
                bundle_service = self.bundle_sales_context
                if bundle_service is None:
                    from app.services.photoshoot_bundle_sales_context_service import PhotoshootBundleSalesContextService
                    bundle_service = PhotoshootBundleSalesContextService()
                dispatch_mode = bundle_service.resolve_mode(dispatch_session_id)
                if dispatch_mode == "BUNDLE" and profile is not None:
                    from app.models.ownership_intelligence import OwnershipIdentity
                    lifecycle_service = self.photoshoot_lifecycles
                    if lifecycle_service is None:
                        from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                        lifecycle_service = CustomerPhotoshootLifecycleService()
                    teaser_presented = bool(
                        resolved_photoshoot_lifecycle
                        and lifecycle_service.bundle_teaser_presented(
                            resolved_photoshoot_lifecycle
                        )
                    )
                    offer_presented_reader = getattr(
                        lifecycle_service, "bundle_offer_presented", None
                    )
                    offer_presented = bool(
                        resolved_photoshoot_lifecycle
                        and callable(offer_presented_reader)
                        and offer_presented_reader(resolved_photoshoot_lifecycle)
                    )
                    bundle_context = bundle_service.build(
                        dispatch_session_id,
                        identity=OwnershipIdentity(
                            creator_profile_id=creator_profile_id,
                            fanvue_account_id=fanvue_account_id,
                            external_fanvue_user_uuid=buyer_uuid,
                            telegram_user_id=telegram_user_id,
                        ),
                        lifecycle_id=(
                            resolved_photoshoot_lifecycle.lifecycle_id
                            if resolved_photoshoot_lifecycle else None
                        ),
                        teaser_presented=teaser_presented,
                        offer_presented=offer_presented,
                    )
                    result = replace(result, bundle_sales_context=bundle_context)
                    if not bundle_context["eligible"]:
                        result = replace(
                            result, decision=CustomerSalesDecisionType.NO_SALE,
                            reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                            reason_summary=",".join(
                                bundle_context["ineligibilityReasons"]
                            ), sell_allowed=False, nudge_allowed=False,
                            recommended_offering_id=None,
                            recommended_publication_id=None,
                            recommended_delivery_url=None,
                        )
            except Exception as error:
                dispatch_mode = "BUNDLE" if dispatch_mode == "BUNDLE" else dispatch_mode
                logger.warning(
                    "event=bundle_sales_context_unavailable error_type=%s",
                    type(error).__name__,
                )
                if dispatch_mode == "BUNDLE":
                    result = replace(
                        result, decision=CustomerSalesDecisionType.NO_SALE,
                        reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                        reason_summary="BUNDLE_CONTEXT_NOT_READY",
                        sell_allowed=False, nudge_allowed=False,
                        recommended_offering_id=None,
                        recommended_publication_id=None,
                        recommended_delivery_url=None,
                    )
                elif dispatch_session_id:
                    dispatch_mode = "UNRESOLVED"
                    result = replace(
                        result, decision=CustomerSalesDecisionType.NO_SALE,
                        reason_code=CustomerSalesReasonCode.NO_ELIGIBLE_OFFERING,
                        reason_summary="PHOTOSHOOT_SELLING_MODE_UNRESOLVED",
                        sell_allowed=False, nudge_allowed=False,
                        recommended_offering_id=None,
                        recommended_publication_id=None,
                        recommended_delivery_url=None,
                    )
        if buyer_uuid is not None:
            try:
                profile = profile or self.customers.get_by_buyer_uuid(creator_profile_id=creator_profile_id,external_fanvue_user_uuid=buyer_uuid)
                lifecycle_service = self.photoshoot_lifecycles
                if lifecycle_service is None:
                    from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                    lifecycle_service = CustomerPhotoshootLifecycleService()
                if profile and resolved_photoshoot_lifecycle is None:
                    states=lifecycle_service.context_for_customer(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id)
                    existing_active_lifecycle=next((v for v in states.values() if v.status.value in {'ACTIVE','OBJECTION'}),None)
                    resolved_photoshoot_lifecycle=existing_active_lifecycle
                current_lifecycle=existing_active_lifecycle or resolved_photoshoot_lifecycle
                target_lifecycle=(resolved_photoshoot_lifecycle if current_lifecycle and resolved_photoshoot_lifecycle and current_lifecycle.photoshoot_id!=resolved_photoshoot_lifecycle.photoshoot_id else None)
                if profile and current_lifecycle and dispatch_mode == "SESSION":
                    repository=self.progression_repository
                    if repository is None:
                        from app.repositories.autonomous_sales_progression_repository import AutonomousSalesProgressionRepository
                        repository=AutonomousSalesProgressionRepository()
                    engine=self.autonomous_progression
                    if engine is None:
                        from app.services.autonomous_sales_progression_service import AutonomousSalesProgressionService
                        engine=AutonomousSalesProgressionService()
                    from app.models.autonomous_sales_progression import BuyingMomentumEvidence
                    assets=repository.ordered_assets(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_id=current_lifecycle.photoshoot_id)
                    session_runtime_state=None
                    try:
                        runtime_service=self.session_runtime
                        if runtime_service is None:
                            from app.services.photoshoot_session_runtime_service import PhotoshootSessionRuntimeService
                            runtime_service=PhotoshootSessionRuntimeService()
                        session_runtime_state=runtime_service.evaluate(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_session_id=current_lifecycle.photoshoot_id)
                        owned=set(session_runtime_state.owned_asset_ids)
                        assets=tuple(replace(asset,owned=asset.asset_id in owned) for asset in assets)
                    except Exception as error:
                        logger.warning("event=photoshoot_session_runtime_unavailable error_type=%s",type(error).__name__)
                    target_assets=(repository.ordered_assets(creator_profile_id=creator_profile_id,customer_commerce_profile_id=profile.customer_commerce_profile_id,photoshoot_id=target_lifecycle.photoshoot_id) if target_lifecycle else ())
                    action=engine.decide(customer_profile_id=profile.customer_commerce_profile_id,lifecycle=current_lifecycle,assets=assets,target_lifecycle=target_lifecycle,target_assets=target_assets,momentum_evidence=BuyingMomentumEvidence(purchases=int(progression_context.get('current_conversation_purchase_count') or (1 if congratulate_allowed else 0)),rapid_purchases=int(progression_context.get('rapid_purchase_count') or 0),explicit_more=bool(progression_context.get('explicit_request_for_more')),declined=bool(progression_context.get('offer_declined')),expired_intents=int(progression_context.get('expired_intent_count') or (1 if reason is CustomerSalesReasonCode.ACTIVE_OFFER_EXPIRED else 0)),consecutive_no_response=int(progression_context.get('consecutive_offer_no_response') or 0),active_intent=active is not None,cooldown=reason is CustomerSalesReasonCode.RECENT_PURCHASE_COOLDOWN,runtime_suppressed=decision in {CustomerSalesDecisionType.MANUAL_REVIEW}),active_purchase_intent_id=(active.purchase_intent_id if active else None),sales_session_id=progression_context.get('sales_session_id'),bridge_recent=bool(progression_context.get('recent_bridge_to_target')),selling_authorized=(sell_allowed or nudge_allowed or decision in {CustomerSalesDecisionType.CONTINUE_CONVERSATION,CustomerSalesDecisionType.NO_SALE}))
                    if session_runtime_state is not None:
                        if (
                            session_runtime_state.status.value == "ACTIVE"
                            and session_runtime_state.current_sales_role == "FREE_TEASER"
                            and session_runtime_state.current_asset_id not in set(session_runtime_state.owned_asset_ids)
                            and active is None
                        ):
                            from app.models.autonomous_sales_progression import NextSalesActionType
                            action=replace(
                                action,action=NextSalesActionType.CONTINUE_PHOTOSHOOT,
                                selected_asset_id=session_runtime_state.current_asset_id,
                                selected_offering_id=None,publication_id=None,delivery_url=None,
                                reason="Execute the persisted Session Sales Strategy free teaser.",
                                decision_trace=("active_lifecycle","session_runtime","free_teaser"),
                            )
                        action=replace(action,metadata={**dict(action.metadata),"sessionRuntime":session_runtime_state.to_context()})
                    result=replace(result,next_sales_action=action)
                    # The opportunity engine is authoritative for fulfillment.
                    # Never leave the generic ranked Offering attached when it
                    # differs from the deterministic current chapter.
                    if action.selected_offering_id is not None and action.selected_offering_id != result.recommended_offering_id:
                        selector_repository=getattr(self.offering_selector,'repository',None)
                        getter=getattr(selector_repository,'get_candidate',None)
                        selected=getter(action.selected_offering_id,creator_profile_id=creator_profile_id) if callable(getter) else None
                        if selected:
                            result=replace(result,recommended_offering_id=action.selected_offering_id,recommended_publication_id=action.publication_id,recommended_delivery_url=action.delivery_url,recommended_offering_title=str(selected.get('title') or ''),recommended_offering_short_description=selected.get('description'),recommended_offering_price_minor=selected.get('price_minor'),recommended_offering_currency=selected.get('currency'))
                    claim=getattr(repository,'claim_action',None)
                    if callable(claim):
                        claimed=claim(action)
                        if claimed and claimed.get('decision'):
                            from app.models.autonomous_sales_progression import NextSalesAction
                            action=NextSalesAction.from_context(claimed['decision'])
                            result=replace(result,next_sales_action=action)
            except Exception as error:
                logger.warning("event=autonomous_sales_progression_unavailable error_type=%s",type(error).__name__)
        logger.info(
            "event=decision_generated decision=%s reason_code=%s buyer_stage=%s "
            "buyer_uuid=%s current_offer=%s purchase_state=%s timing_ms=%s",
            decision.value, reason.value, stage.value, buyer_uuid,
            result.active_offering_id, conversion,
            result.decision_metadata["evaluationMs"],
        )
        return result

    def _apply_photoshoot_opportunity_policy(self, *, creator_profile_id,
                                             customer_profile, context):
        """Apply explicit bounded-opportunity decisions before Offering selection."""
        profile_id = getattr(customer_profile, "customer_commerce_profile_id", None)
        if profile_id is None:
            return None
        try:
            service = self.photoshoot_lifecycles
            if service is None:
                from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
                service = CustomerPhotoshootLifecycleService()
            opportunity = service.active_for_customer(
                creator_profile_id=creator_profile_id,
                customer_commerce_profile_id=profile_id,
            )
            if opportunity is None:
                return None
            requested = context.get("requested_photoshoot_reference")
            close_reason = next((reason for enabled, reason in (
                (context.get("close_photoshoot_opportunity"), "SALES_BRAIN_CLOSE"),
                (context.get("operator_close_photoshoot"), "OPERATOR_CLOSE"),
                (context.get("customer_requests_different_content"), "CUSTOMER_REQUESTED_DIFFERENT_CONTENT"),
                (context.get("stronger_opportunity_available"), "STRONGER_OPPORTUNITY"),
                (requested and str(requested) != opportunity.photoshoot_id, "DIFFERENT_PHOTOSHOOT_REQUESTED"),
                (int(context.get("consecutive_offer_no_response") or 0) >= self.config.photoshoot_objection_recovery_limit, "REPEATED_NON_RESPONSE"),
            ) if enabled), None)
            if close_reason:
                return service.close_opportunity(opportunity, reason=close_reason)
            if context.get("offer_declined") or context.get("photoshoot_objection"):
                opportunity = service.enter_objection(opportunity, reason=str(context.get("objection_type") or "CUSTOMER_OBJECTION"))
            if opportunity.status.value == "OBJECTION":
                if context.get("objection_recovered") or context.get("explicit_request_for_more"):
                    opportunity = service.attempt_recovery(
                        opportunity, recovered=True,
                        recovery_limit=self.config.photoshoot_objection_recovery_limit,
                        reason="CUSTOMER_REENGAGED",
                    )
                elif context.get("objection_recovery_attempted") or context.get("objection_recovery_failed"):
                    opportunity = service.attempt_recovery(
                        opportunity, recovered=False,
                        recovery_limit=self.config.photoshoot_objection_recovery_limit,
                        reason="RECOVERY_DID_NOT_CONVERT",
                    )
            return opportunity
        except Exception as error:
            logger.warning("event=photoshoot_opportunity_policy_unavailable error_type=%s", type(error).__name__)
            return None

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
            CustomerSalesReasonCode.NO_SELLING_STRATEGY: 9,
        }
        return priorities.get(reason, 0)

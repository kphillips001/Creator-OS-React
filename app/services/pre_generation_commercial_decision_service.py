"""Cheap bridge to the existing commercial authority; never generates content."""
from app.models.pre_generation_commercial_decision import PreGenerationCommercialDecision
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.commercial_receptiveness_service import CommercialReceptivenessService
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService
from app.services.active_offer_follow_through_service import ActiveOfferFollowThroughService
from app.services.active_offer_meaningful_turn_service import ActiveOfferMeaningfulTurnService
from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
from datetime import datetime, timezone, timedelta


class PreGenerationCommercialDecisionService:
    SUPPORTED = frozenset({"PRICE_REQUEST", "DIRECT_CONTENT_INTENT",
        "OFFERING_AVAILABILITY_INQUIRY", "SEND_OR_LINK_REQUEST", "PURCHASE_ACCEPTANCE"})

    def __init__(self, *, authority=None, intents=None, turns=None, ledger=None,
                 follow_through=None, config=None, clock=lambda:datetime.now(timezone.utc)):
        progression = ConversationalSalesProgressionService()
        self.authority = authority or CommercialReceptivenessService(
            progression.has_direct_purchase_intent)
        self.intents = intents or PurchaseIntentRepository()
        self.turns=turns or ActiveOfferMeaningfulTurnService()
        self.ledger=ledger or ActiveOfferFollowThroughRepository()
        self.follow_through=follow_through or ActiveOfferFollowThroughService()
        self.config=config or CustomerSalesBrainConfig.from_environment()
        self.clock=clock

    def project(self, *, customer_text, creator_profile_id, fanvue_account_id,
                telegram_user_id, classifier_result=None,
                historical_commercial_interest=False, operation_id=None):
        active = self.intents.get_active_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id)
        classifier = dict(classifier_result or {})
        decision = self.authority.evaluate(context={
            "latest_message": str(customer_text or ""),
            "classifier_result": classifier,
            "historical_commercial_interest": bool(historical_commercial_interest),
        }, recent_purchase=False, cooldown_active=False,
           active_offer=active is not None)
        interest = str(decision.commercial_interest_type or "NONE")
        temporal = bool(decision.deferred_commercial_interest)
        boundary = bool(self.authority.commercial_boundary_type(customer_text))
        deterministic = bool(interest in self.SUPPORTED
            and (interest != "PURCHASE_ACCEPTANCE" or decision.acceptance_grounded))
        rejected = bool(classifier.get("buying_intent") is False)
        eligible = bool(decision.fresh_direct_intent
            and decision.current_commercial_interest and deterministic
            and not temporal and not boundary
            and (not rejected or deterministic))
        from app.services.ava_attention_investment_service import AvaAttentionInvestmentService
        mandatory=bool(AvaAttentionInvestmentService().evaluate(
            [str(customer_text or "")]).meaningful_obligation)
        candidate=False; reserved=False; reservation_reason=None
        if active is not None and operation_id is not None:
            now=self.clock(); turn_projection=self.turns.project(intent=active)
            follow=self.follow_through.evaluate(intent=active,now=now,
                nudge_delay=self.config.offer_nudge_delay,
                contextual_continuation=(interest if eligible else None),
                fresh_direct_intent=eligible,
                meaningful_turns_after_presentation=int(turn_projection['meaningful_turns_since_presentation']))
            candidate=follow.eligible
            if candidate:
                row=self.ledger.reserve(intent=active,reason=follow.mode,
                    eligible_at=follow.next_eligible_at or now,
                    operation_id=operation_id,now=now,direct=eligible)
                reserved=row is not None
                reservation_reason="AUTHORIZED" if reserved else "RESERVATION_DENIED"
        return PreGenerationCommercialDecision(
            fresh_direct_intent=bool(decision.fresh_direct_intent),
            current_commercial_interest=bool(decision.current_commercial_interest),
            commercial_interest_type=interest,
            referent_present=bool(decision.commercial_referent_present),
            grounded_purchase_acceptance=bool(decision.acceptance_grounded),
            temporal_deferred=temporal, no_buy_boundary=boundary,
            classifier_rejected_buying_intent=rejected,
            deterministic_commercial_evidence=deterministic,
            commercial_bypass_eligible=eligible,
            active_offer_nudge_candidate=candidate,
            active_offer_reservation_authorized=reserved,
            active_offer_reservation_reason=reservation_reason,
            mandatory_response_obligation=mandatory)

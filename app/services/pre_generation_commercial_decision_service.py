"""Cheap bridge to the existing commercial authority; never generates content."""
from app.models.pre_generation_commercial_decision import PreGenerationCommercialDecision
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.commercial_receptiveness_service import CommercialReceptivenessService
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService


class PreGenerationCommercialDecisionService:
    SUPPORTED = frozenset({"PRICE_REQUEST", "DIRECT_CONTENT_INTENT",
        "OFFERING_AVAILABILITY_INQUIRY", "SEND_OR_LINK_REQUEST", "PURCHASE_ACCEPTANCE"})

    def __init__(self, *, authority=None, intents=None):
        progression = ConversationalSalesProgressionService()
        self.authority = authority or CommercialReceptivenessService(
            progression.has_direct_purchase_intent)
        self.intents = intents or PurchaseIntentRepository()

    def project(self, *, customer_text, creator_profile_id, fanvue_account_id,
                telegram_user_id, classifier_result=None,
                historical_commercial_interest=False):
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
        return PreGenerationCommercialDecision(
            fresh_direct_intent=bool(decision.fresh_direct_intent),
            current_commercial_interest=bool(decision.current_commercial_interest),
            commercial_interest_type=interest,
            referent_present=bool(decision.commercial_referent_present),
            grounded_purchase_acceptance=bool(decision.acceptance_grounded),
            temporal_deferred=temporal, no_buy_boundary=boundary,
            classifier_rejected_buying_intent=rejected,
            deterministic_commercial_evidence=deterministic,
            commercial_bypass_eligible=eligible)

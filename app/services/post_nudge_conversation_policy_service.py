"""Commercial-attention policy after durable presentation nonconversion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.services.customer_heat_signal_service import CustomerHeatSignalService
from app.services.contextual_customer_tone_service import ContextualCustomerToneService


@dataclass(frozen=True)
class PostNudgeConversationDecision:
    active: bool
    response_purpose: str | None
    sexual_access_gated: bool
    provider_allowed: bool
    suppress_optional_reply: bool
    time_waster: bool
    evidence: dict

    def diagnostics(self):
        return {
            "active": self.active,
            "responsePurpose": self.response_purpose,
            "sexualAccessGated": self.sexual_access_gated,
            "providerAllowed": self.provider_allowed,
            "suppressOptionalReply": self.suppress_optional_reply,
            # Compatibility flag only: reduced free investment, never ignore.
            "timeWaster": self.time_waster,
            **self.evidence,
        }


class PostNudgeConversationPolicyService:
    """Scale free intensity from canonical failed-presentation history."""

    def __init__(self, *, ledger, operations, accounting, intents=None,
                 config=None, clock=lambda: datetime.now(timezone.utc)):
        self.ledger = ledger
        self.operations = operations
        self.accounting = accounting
        self.intents = intents
        self.config = config
        self.clock = clock

    @staticmethod
    def _decision(*, active=True, purpose=None, gated=False, provider=True,
                  reduced=False, evidence=None):
        return PostNudgeConversationDecision(
            active, purpose, gated, provider, False, reduced, evidence or {},
        )

    def evaluate(self, *, operation, commercial_decision, verified_buyer,
                 creator_profile_id, fanvue_account_id):
        scope = {
            "creator_profile_id": creator_profile_id,
            "fanvue_account_id": fanvue_account_id,
            "telegram_user_id": operation.inbound_sender_telegram_user_id,
            "telegram_chat_id": operation.telegram_chat_id,
        }
        nonconversion = self.ledger.relationship_nonconversion(**scope)
        from app.services.customer_sales_brain_config import CustomerSalesBrainConfig
        from app.services.sexual_sales_opportunity_service import SexualSalesOpportunityService

        config = self.config or CustomerSalesBrainConfig.from_environment()
        if self.intents is None:
            from app.repositories.purchase_intent_repository import PurchaseIntentRepository
            self.intents = PurchaseIntentRepository()
        text = str(operation.inbound_message_text or "")
        tone = ContextualCustomerToneService().classify(message=text)
        heat = CustomerHeatSignalService().project(
            message=text, contextual_tone=tone,
        )
        sexual_detected = bool(
            heat.get("detected") or tone.get("sexualOrProvocative")
        )
        sexual_policy = SexualSalesOpportunityService(
            intents=self.intents,
            cooldown=config.sexual_sales_cooldown,
            max_opportunities=config.sexual_sales_max_opportunities,
            episode_separation=config.sexual_sales_episode_separation,
        ).project(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=operation.inbound_sender_telegram_user_id,
            latest_message=text,
            now=self.clock(),
            customer_heat_signal=heat,
        )
        failed_count = max(
            int(nonconversion.get("nonconversion_count") or 0),
            int(sexual_policy.get("unsuccessfulPresentationCount") or 0),
        )
        premium_threshold = int(config.sexual_sales_max_opportunities)
        time_waster_threshold = int(config.time_waster_min_failed_presentations)
        purchased = sexual_policy.get("lastSexualOfferOutcome") == "PURCHASED"
        cooldown = bool(sexual_policy.get("sexualSalesCooldownActive"))
        common = {
            "failedPresentationCount": failed_count,
            "premiumBoundaryThreshold": premium_threshold,
            "timeWasterThreshold": time_waster_threshold,
            "customerHeatSignal": heat,
            "customerHeatDetected": bool(heat.get("detected")),
            "customerHeatInitiationSource": heat.get("initiationSource"),
            "commercialOpportunityEvaluationPerformed": bool(
                heat.get("warmupOverrideEligible")
                or commercial_decision.commercial_bypass_eligible
            ),
            "cooldownActive": cooldown,
            "futureCommercialReentryAllowed": True,
            "relationshipRemainsActive": True,
            "ignoreChanged": False,
            "sexualSalesOpportunity": sexual_policy,
        }
        if verified_buyer or purchased:
            return self._decision(active=False, evidence={
                **common, "investmentTreatment": "BUYER_AUTHORITY",
                "activePresentationBridge": False,
                "supporterBoundaryEligible": False,
                "supporterBoundarySuppressionReason": "VERIFIED_BUYER",
                "timeWasterMeaning": "NOT_APPLICABLE_TO_BUYER",
            })
        if bool(commercial_decision.commercial_bypass_eligible):
            return self._decision(purpose="COMMERCIAL_REENTRY", gated=True,
                evidence={**common, "commercialReentry": True,
                    "commercialSignalOverride": True,
                    "investmentTreatment": "NORMAL_CULTIVATION",
                    "supporterBoundaryEligible": False,
                    "supporterBoundarySuppressionReason": "FRESH_COMMERCIAL_SIGNAL"})
        if sexual_policy.get("activePresentationBridge") is True:
            signal = str(sexual_policy.get("sexualSignalClass") or "NONE")
            return self._decision(purpose="ACTIVE_PRESENTATION_BRIDGE",
                gated=signal == "SEXUAL_ESCALATION", evidence={**common,
                    "activePresentationBridge": True,
                    "sexualSignalClass": signal,
                    "activePresentationId": sexual_policy.get("activePresentationId"),
                    "activePresentationState": sexual_policy.get("activePresentationState"),
                    "bridgeConversationalFunction": (
                        "PLAYFUL_REDIRECT" if signal == "SEXUAL_ESCALATION"
                        else "LIGHT_FLIRT" if signal == "SEXUAL_ATTRACTIVE_COMPLIMENT"
                        else "NORMAL_CONVERSATION"
                    ), "investmentTreatment": "ACTIVE_PRESENTATION_BRIDGE",
                    "supporterBoundaryEligible": False,
                    "supporterBoundarySuppressionReason": "ACTIVE_UNSETTLED_PRESENTATION"})
        if failed_count < 1:
            return self._decision(active=False, evidence={**common,
                "investmentTreatment": "NORMAL_CULTIVATION",
                "activePresentationBridge": False,
                "supporterBoundaryEligible": False})
        if (sexual_policy.get("sexualSalesOpportunityEligible") is True
                and sexual_policy.get("confirmedPresentationCount", 0) > 0):
            return self._decision(active=False, evidence={**common,
                "commercialReentry": False,
                "investmentTreatment": "NORMAL_CULTIVATION",
                "supporterBoundaryEligible": False})
        if failed_count >= premium_threshold:
            time_waster = failed_count >= time_waster_threshold
            return self._decision(purpose="PREMIUM_VALUE_BOUNDARY",
                gated=sexual_detected, reduced=time_waster,
                evidence={**common,
                    "nonconversionScope": "REPEATED_PRESENTATION_PATTERN",
                    "investmentTreatment": (
                        "COOLDOWN_CASUAL" if cooldown else "PREMIUM_VALUE_BOUNDARY"
                    ),
                    "freeHighIntensityInvestmentReduced": True,
                    "premiumValueBoundaryAuthorized": True,
                    "supporterBoundaryEligible": True,
                    "supporterBoundaryReason": "FAILED_PRESENTATION_THRESHOLD_REACHED",
                    "timeWasterMeaning": (
                        "REDUCED_FREE_INVESTMENT_NOT_DISENGAGEMENT"
                        if time_waster else "THRESHOLD_NOT_REACHED"
                    ),
                    "providerSemanticGuidance": {
                        "premiumIntimacyHasValue": True,
                        "supporterValueBoundary": True,
                        "warmConversationRemainsAllowed": True,
                        "nonsexualPolicyNarrationAllowed": False,
                        "internalPolicyNarrationAllowed": False,
                        "inviteFurtherFreeEscalation": False,
                    }})
        intermediate = failed_count >= 2
        purpose = (
            "REDUCED_FREE_INTENSITY" if intermediate and sexual_detected
            else "POST_PPV_RELATIONSHIP_CONTINUATION" if sexual_detected
            else "CASUAL_BACKOFF_CONVERSATION"
        )
        return self._decision(purpose=purpose, gated=sexual_detected,
            evidence={**common,
                "nonconversionScope": "PRESENTATION_SPECIFIC",
                "failedPresentationPreserved": True,
                "investmentTreatment": (
                    "REDUCED_FREE_INTENSITY" if intermediate
                    else "NORMAL_CULTIVATION"
                ),
                "freeHighIntensityInvestmentReduced": intermediate,
                "premiumValueBoundaryAuthorized": False,
                "supporterBoundaryEligible": False,
                "supporterBoundarySuppressionReason": "FAILED_PRESENTATION_THRESHOLD_NOT_REACHED",
                "timeWasterMeaning": "NOT_CLASSIFIED",
                "commercialReentry": False,
                "providerSemanticGuidance": {
                    "warmPlayfulAcknowledgementAllowed": True,
                    "explicitParticipationNotAuthorized": sexual_detected,
                    "inviteIntensification": False,
                    "naturalRedirectAllowed": True,
                    "maintainRelationshipTemperature": True,
                    "remainCommerciallyAttentive": True,
                    "premiumValueBoundary": False,
                    "policyNarrationAllowed": False,
                    "nonsexualPolicyNarrationAllowed": False,
                }})
